"""
Cross-Course Search -- Flask Backend
PDF indexer using pypdf + in-memory full-text search.
Handles filenames with spaces, brackets, unicode, and special characters.
Tries multiple PDF engines per file for maximum compatibility.
"""

import os
import re
import json
import time
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

# ── PDF ENGINE DETECTION ───────────────────────────────────────
# Detect all available engines at startup
ENGINES = []
try:
    import pdfplumber
    ENGINES.append("pdfplumber")
except ImportError:
    pass
try:
    import fitz  # PyMuPDF
    ENGINES.append("pymupdf")
except ImportError:
    pass
try:
    from pypdf import PdfReader
    ENGINES.append("pypdf")
except ImportError:
    pass

PDF_ENGINE = ENGINES[0] if ENGINES else None

# ── PATHS ──────────────────────────────────────────────────────
# Always resolve relative to app.py location, not cwd
BASE_DIR   = Path(__file__).parent.resolve()
PDF_DIR    = BASE_DIR / "pdfs"
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# ── IN-MEMORY INDEX ────────────────────────────────────────────
INDEX       = []
INDEX_READY = False
INDEX_STATS = {"files": 0, "pages": 0, "build_time": 0, "skipped": 0}


def extract_text_pdfplumber(path):
    """Extract (page_num, text) using pdfplumber."""
    pages = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    t = page.extract_text() or ""
                    pages.append((i + 1, t))
                except Exception:
                    pages.append((i + 1, ""))
    except Exception as e:
        print(f"  [pdfplumber] failed on {path.name}: {e}")
    return pages


def extract_text_pymupdf(path):
    """Extract (page_num, text) using PyMuPDF."""
    pages = []
    try:
        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            try:
                t = page.get_text() or ""
                pages.append((i + 1, t))
            except Exception:
                pages.append((i + 1, ""))
        doc.close()
    except Exception as e:
        print(f"  [pymupdf] failed on {path.name}: {e}")
    return pages


def extract_text_pypdf(path):
    """Extract (page_num, text) using pypdf."""
    pages = []
    try:
        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
                pages.append((i + 1, t))
            except Exception:
                pages.append((i + 1, ""))
    except Exception as e:
        print(f"  [pypdf] failed on {path.name}: {e}")
    return pages


def extract_text(path):
    """
    Try all available engines in order.
    Falls back to next engine if the result is empty or an error occurs.
    Handles filenames with spaces, brackets, parentheses, unicode, etc.
    """
    path = Path(path).resolve()

    for engine in ENGINES:
        try:
            if engine == "pdfplumber":
                pages = extract_text_pdfplumber(path)
            elif engine == "pymupdf":
                pages = extract_text_pymupdf(path)
            elif engine == "pypdf":
                pages = extract_text_pypdf(path)
            else:
                continue

            # Check if we got any real text content
            total_text = "".join(t for _, t in pages).strip()
            if total_text:
                return pages  # Success

            print(f"  [{engine}] returned empty text for {path.name}, trying next engine...")
        except Exception as e:
            print(f"  [{engine}] exception for {path.name}: {e}")
            continue

    print(f"  WARNING: No text extracted from {path.name} (may be a scanned/image PDF)")
    return []


def friendly_title(filename):
    """
    Convert any filename to a readable title.
    Handles: spaces, brackets, parentheses, underscores, dashes, version numbers.
    Examples:
      MATH301_Linear_Algebra.pdf        -> MATH 301 - Linear Algebra
      Notes - Print Version (1).pdf     -> Notes - Print Version
      lecture_week3_data_structures.pdf -> Lecture Week3 Data Structures
      CS201DataStructures.pdf           -> CS 201 Data Structures
    """
    name = Path(filename).stem

    # Remove common noise patterns like (1), (2), _v2, _final, _copy
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)        # trailing (1), (2)
    name = re.sub(r'[\s_-]+(v\d+|final|copy|draft|print|version)[\s_-]*$',
                  '', name, flags=re.IGNORECASE)

    # Replace underscores and hyphens with spaces
    name = name.replace('_', ' ').replace('-', ' - ')

    # Insert space before digit runs after letters: MATH301 -> MATH 301
    name = re.sub(r'([A-Za-z])(\d)', r'\1 \2', name)

    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()

    # Title case if all lowercase or all uppercase
    if name == name.lower() or name == name.upper():
        name = name.title()

    return name if name else Path(filename).stem


def build_index():
    global INDEX, INDEX_READY, INDEX_STATS
    start    = time.time()
    entries  = []
    skipped  = 0

    # Create pdfs dir if it doesn't exist
    PDF_DIR.mkdir(exist_ok=True)

    # Find ALL pdfs recursively (including subfolders)
    pdf_files = sorted(PDF_DIR.rglob("*.pdf"))

    # Also handle uppercase .PDF extension
    pdf_files += [p for p in sorted(PDF_DIR.rglob("*.PDF"))
                  if p not in pdf_files]

    total = len(pdf_files)
    print(f"\nIndexing {total} PDF(s) from: {PDF_DIR}")
    print(f"Engines available: {ENGINES}\n")

    for pdf_path in pdf_files:
        title = friendly_title(pdf_path.name)
        print(f"  -> {pdf_path.name}")
        pages = extract_text(pdf_path)

        if not pages:
            skipped += 1
            continue

        pages_added = 0
        for page_num, text in pages:
            if not text.strip():
                continue
            entries.append({
                "file":       pdf_path.name,
                "title":      title,
                "page":       page_num,
                "text":       text,
                "text_lower": text.lower(),
            })
            pages_added += 1

        if pages_added == 0:
            skipped += 1
            print(f"     (no extractable text - possibly scanned)")

    elapsed = round(time.time() - start, 2)
    INDEX   = entries
    INDEX_STATS = {
        "files":      total - skipped,
        "pages":      len(entries),
        "build_time": elapsed,
        "skipped":    skipped,
    }
    INDEX_READY = True
    print(f"\nIndexed {len(entries)} pages from {total - skipped} files in {elapsed}s")
    if skipped:
        print(f"Skipped {skipped} files (scanned/unreadable PDFs)")


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
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        snippet = prefix + text[start:end] + suffix

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
    # Use rglob to find PDFs in subfolders too, handle all filename types
    for p in sorted(PDF_DIR.rglob("*.pdf")):
        files.append({
            "name": p.name,
            "title": friendly_title(p.name),
            "size_kb": round(p.stat().st_size / 1024, 1),
        })
    return jsonify(files)


# ── STARTUP ───────────────────────────────────────────────────
if __name__ == "__main__":
    STATIC_DIR.mkdir(exist_ok=True)
    PDF_DIR.mkdir(exist_ok=True)

    if not ENGINES:
        print("ERROR: No PDF library found.")
        print("Run: pip install pdfplumber pypdf")
        exit(1)

    print("Cross-Course Search starting on http://localhost:5000")
    print("PDF folder: " + str(PDF_DIR))
    print("PDF engines: " + str(ENGINES))

    # Build index in background thread so server starts immediately
    t = threading.Thread(target=build_index, daemon=True)
    t.start()
    app.run(debug=False, port=5000, use_reloader=False)
