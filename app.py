"""
Cross-Course Search — Flask Backend
PDF indexer using pypdf + in-memory full-text search.
Falls back to pdfplumber if pypdf extraction is thin.
"""

import os
import re
import json
import time
import threading
from pathlib import Path
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory

# PDF parsing — prefer pdfplumber (richer text), fall back to pypdf
try:
    import pdfplumber
    PDF_ENGINE = "pdfplumber"
except ImportError:
    import pypdf
    PDF_ENGINE = "pypdf"

PDF_DIR = Path(__file__).parent / "pdfs"
STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# ── IN-MEMORY INDEX ────────────────────────────────────────────
# Structure: list of {file, page, text, title, snippet}
INDEX = []
INDEX_READY = False
INDEX_STATS = {"files": 0, "pages": 0, "build_time": 0}


def extract_text_pdfplumber(path):
    """Returns list of (page_num, text) tuples."""
    pages = []
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                pages.append((i + 1, t))
    except Exception as e:
        print(f"  ⚠ pdfplumber error on {path.name}: {e}")
    return pages


def extract_text_pypdf(path):
    pages = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            pages.append((i + 1, t))
    except Exception as e:
        print(f"  ⚠ pypdf error on {path.name}: {e}")
    return pages


def extract_text(path):
    if PDF_ENGINE == "pdfplumber":
        return extract_text_pdfplumber(path)
    return extract_text_pypdf(path)


def friendly_title(filename):
    """MATH301_Linear_Algebra.pdf → MATH 301 — Linear Algebra"""
    name = Path(filename).stem
    # Insert space before digit runs after letters: MATH301 → MATH 301
    name = re.sub(r'([A-Za-z])(\d)', r'\1 \2', name)
    # Replace underscores with spaces
    name = name.replace('_', ' ')
    # Split on first space sequence after course code
    parts = name.split(' ', 2)
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1]} — {parts[2]}"
    return name


def build_index():
    global INDEX, INDEX_READY, INDEX_STATS
    start = time.time()
    entries = []
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    total_pages = 0

    print(f"\n📚 Indexing {len(pdf_files)} PDFs using {PDF_ENGINE}...")
    for pdf_path in pdf_files:
        title = friendly_title(pdf_path.name)
        print(f"  → {pdf_path.name}")
        pages = extract_text(pdf_path)
        for page_num, text in pages:
            if not text.strip():
                continue
            entries.append({
                "file": pdf_path.name,
                "title": title,
                "page": page_num,
                "text": text,
                # Pre-compute lowercase for fast search
                "text_lower": text.lower(),
            })
            total_pages += 1

    elapsed = round(time.time() - start, 2)
    INDEX = entries
    INDEX_STATS = {"files": len(pdf_files), "pages": total_pages, "build_time": elapsed}
    INDEX_READY = True
    print(f"✅ Indexed {total_pages} pages across {len(pdf_files)} files in {elapsed}s\n")


def make_snippet(text, query, window=200):
    """Extract a snippet around the first match, with <mark> highlights."""
    tl = text.lower()
    ql = query.lower()
    terms = [t.strip() for t in ql.split() if t.strip()]

    # Find best hit position
    pos = -1
    for term in terms:
        p = tl.find(term)
        if p != -1:
            pos = p
            break

    if pos == -1:
        snippet = text[:window]
    else:
        start = max(0, pos - 80)
        end = min(len(text), pos + window)
        snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")

    # Highlight all query terms
    for term in terms:
        snippet = re.sub(
            re.escape(term),
            f'<mark>{term}</mark>',
            snippet,
            flags=re.IGNORECASE
        )
    return snippet


def search_index(query, limit=30):
    """Simple but effective multi-term AND search with scoring."""
    if not query.strip():
        return []

    ql = query.lower()
    terms = [t.strip() for t in ql.split() if len(t.strip()) >= 2]
    if not terms:
        return []

    scored = []
    for entry in INDEX:
        tl = entry["text_lower"]
        # Score = sum of term frequencies
        score = 0
        for term in terms:
            count = tl.count(term)
            if count == 0:
                score = -1
                break
            score += count

        if score > 0:
            scored.append((score, entry))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    results = []
    for score, entry in scored[:limit]:
        results.append({
            "file": entry["file"],
            "title": entry["title"],
            "page": entry["page"],
            "snippet": make_snippet(entry["text"], query),
            "score": score,
        })
    return results


# ── ROUTES ────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "ready": INDEX_READY,
        "stats": INDEX_STATS,
        "engine": PDF_ENGINE,
    })


@app.route("/api/search")
def search():
    if not INDEX_READY:
        return jsonify({"error": "Index building…", "results": []})

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": [], "count": 0, "query": q})

    t0 = time.time()
    results = search_index(q)
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    return jsonify({
        "results": results,
        "count": len(results),
        "query": q,
        "elapsed_ms": elapsed_ms,
    })


@app.route("/api/pdf/<filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)


@app.route("/api/files")
def list_files():
    files = []
    for p in sorted(PDF_DIR.glob("*.pdf")):
        files.append({
            "name": p.name,
            "title": friendly_title(p.name),
            "size_kb": round(p.stat().st_size / 1024, 1),
        })
    return jsonify(files)


# ── STARTUP ───────────────────────────────────────────────────
if __name__ == "__main__":
    STATIC_DIR.mkdir(exist_ok=True)
    # Build index in background thread
    t = threading.Thread(target=build_index, daemon=True)
    t.start()
    print("🚀 Cross-Course Search starting on http://localhost:5000")
    app.run(debug=False, port=5000, use_reloader=False)
