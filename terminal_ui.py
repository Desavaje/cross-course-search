"""
Cross-Course Search — Terminal UI
A fully interactive terminal interface with ANSI styling.
Works on Windows Terminal, PowerShell (Win10+), macOS Terminal, Linux.

Usage:
    python terminal_ui.py
    python terminal_ui.py --folder ./my_pdfs
    python terminal_ui.py --query "eigenvalue"
"""

import os
import sys
import time
import shutil
import argparse
import threading
import re
from pathlib import Path

# ── ANSI COLOUR PALETTE ───────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    # Foreground
    BLACK   = "\033[30m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    GREY    = "\033[90m"
    # Background
    BG_BLACK  = "\033[40m"
    BG_RED    = "\033[41m"
    BG_BLUE   = "\033[44m"
    BG_DARK   = "\033[48;5;235m"
    BG_RUST   = "\033[48;5;130m"
    BG_TEAL   = "\033[48;5;23m"
    # 256-color foreground shorthands
    RUST      = "\033[38;5;166m"
    TEAL      = "\033[38;5;37m"
    GOLD      = "\033[38;5;136m"
    CREAM     = "\033[38;5;230m"
    MUTED     = "\033[38;5;245m"
    HIGHLIGHT = "\033[38;5;214m"

def supports_color():
    """Detect if the terminal supports ANSI colors."""
    if sys.platform == "win32":
        try:
            import colorama
            colorama.init(autoreset=True)
            return True
        except ImportError:
            pass
        # Windows 10+ supports ANSI natively
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

USE_COLOR = supports_color()

def c(code, text):
    return f"{code}{text}{C.RESET}" if USE_COLOR else text

def bold(t):    return c(C.BOLD, t)
def dim(t):     return c(C.DIM + C.GREY, t)
def rust(t):    return c(C.RUST + C.BOLD, t)
def teal(t):    return c(C.TEAL, t)
def gold(t):    return c(C.GOLD, t)
def green(t):   return c(C.GREEN, t)
def red(t):     return c(C.RED, t)
def yellow(t):  return c(C.YELLOW, t)
def muted(t):   return c(C.MUTED, t)
def cream(t):   return c(C.CREAM, t)
def highlight(t): return c(C.HIGHLIGHT + C.BOLD, t)

def term_width():
    return shutil.get_terminal_size((100, 40)).columns

def hr(char="─", color=None):
    w = term_width()
    line = char * w
    return c(color or C.MUTED, line)

def centered(text, width=None, fill=" "):
    w = width or term_width()
    # Strip ANSI for length calculation
    clean = re.sub(r'\033\[[0-9;]*m', '', text)
    pad = max(0, (w - len(clean)) // 2)
    return fill * pad + text

# ── PDF ENGINE ────────────────────────────────────────────────
def get_pdf_engine():
    try:
        import fitz
        return "PyMuPDF"
    except ImportError:
        pass
    try:
        import pdfplumber
        return "pdfplumber"
    except ImportError:
        pass
    try:
        import pypdf
        return "pypdf"
    except ImportError:
        pass
    return None

def extract_pages(pdf_path):
    """Extract (page_num, text) pairs from a PDF."""
    engine = get_pdf_engine()
    pages = []
    try:
        if engine == "PyMuPDF":
            import fitz
            doc = fitz.open(str(pdf_path))
            for i, page in enumerate(doc):
                pages.append((i + 1, page.get_text()))
        elif engine == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    pages.append((i + 1, page.extract_text() or ""))
        elif engine == "pypdf":
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            for i, page in enumerate(reader.pages):
                pages.append((i + 1, page.extract_text() or ""))
    except Exception as e:
        print(f"  {red('✗')} Error reading {pdf_path.name}: {e}")
    return pages

# ── INDEXER ───────────────────────────────────────────────────
class Index:
    def __init__(self):
        self.entries = []
        self.stats = {"files": 0, "pages": 0, "build_time": 0}
        self.ready = False

    def friendly_title(self, filename):
        name = Path(filename).stem
        name = re.sub(r'([A-Za-z])(\d)', r'\1 \2', name)
        name = name.replace('_', ' ')
        parts = name.split(' ', 2)
        if len(parts) >= 3:
            return f"{parts[0]} {parts[1]} — {parts[2]}"
        return name

    def build(self, folder, progress_cb=None):
        t0 = time.time()
        pdf_files = sorted(Path(folder).glob("*.pdf"))
        total_pages = 0

        for pdf_path in pdf_files:
            if progress_cb:
                progress_cb(pdf_path.name)
            title = self.friendly_title(pdf_path.name)
            for page_num, text in extract_pages(pdf_path):
                if text.strip():
                    self.entries.append({
                        "file": pdf_path.name,
                        "title": title,
                        "page": page_num,
                        "text": text,
                        "text_lower": text.lower(),
                    })
                    total_pages += 1

        self.stats = {
            "files": len(pdf_files),
            "pages": total_pages,
            "build_time": round(time.time() - t0, 2),
        }
        self.ready = True

    def search(self, query, limit=20):
        if not query.strip():
            return []
        terms = [t.strip().lower() for t in query.split() if len(t.strip()) >= 2]
        if not terms:
            return []
        scored = []
        for e in self.entries:
            tl = e["text_lower"]
            score = 0
            for term in terms:
                cnt = tl.count(term)
                if cnt == 0:
                    score = -1
                    break
                score += cnt
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        return scored[:limit]

    def snippet(self, text, query, window=180):
        tl = text.lower()
        terms = [t.strip().lower() for t in query.split() if t.strip()]
        pos = -1
        for term in terms:
            p = tl.find(term)
            if p != -1:
                pos = p
                break
        if pos == -1:
            snip = text[:window]
        else:
            start = max(0, pos - 60)
            end = min(len(text), pos + window)
            snip = ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")
        # Highlight terms
        for term in terms:
            snip = re.sub(
                re.escape(term),
                lambda m: highlight(m.group(0)),
                snip,
                flags=re.IGNORECASE
            )
        return snip


# ── SPLASH SCREEN ─────────────────────────────────────────────
LOGO = r"""
   ___                  ___                          
  / __\ _ __  ___  ___ / __\___  _   _ _ __ ___  ___  
 / /   | '__/ _ \/ __/ /   / _ \| | | | '__/ __|/ _ \ 
/ /____| | | (_) \__ \ /___| (_) | |_| | |  \__ \  __/
\______|_|  \___/|___/\____/\___/ \__,_|_|  |___/\___|
"""

def print_splash():
    os.system('cls' if sys.platform == 'win32' else 'clear')
    w = term_width()
    print()
    for line in LOGO.strip('\n').split('\n'):
        print(centered(rust(line)))
    print(centered(muted("PDF Search Engine  ·  Edge-Fast  ·  No Cloud")))
    print()
    print(hr("═"))
    print()

# ── PROGRESS BAR ─────────────────────────────────────────────
def progress_bar(current, total, width=40, label=""):
    pct = current / max(total, 1)
    filled = int(pct * width)
    bar = green("█" * filled) + dim("░" * (width - filled))
    pct_str = f"{int(pct*100):3d}%"
    return f"  [{bar}] {rust(pct_str)}  {muted(label)}"

# ── RESULT RENDERER ───────────────────────────────────────────
def render_result(rank, score, entry, snippet_text, query):
    w = term_width()
    rank_badge = c(C.BG_RUST + C.WHITE + C.BOLD, f" {rank:02d} ")
    page_badge  = c(C.TEAL, f"pg.{entry['page']}")
    score_badge = muted(f"score:{score}")
    title       = bold(entry['title'])
    file_name   = muted(f"  {entry['file']}")

    print(f"  {rank_badge}  {title}  {page_badge}  {score_badge}")
    print(f"       {file_name}")
    # Wrap snippet
    snip_lines = snippet_text.replace('\n', ' ').strip()
    # Print with indent
    print(f"       {dim('│')}  {snip_lines[:w - 12]}")
    print()

# ── BUILD WITH LIVE PROGRESS ──────────────────────────────────
def build_with_progress(index, folder):
    pdf_files = sorted(Path(folder).glob("*.pdf"))
    total = len(pdf_files)
    if total == 0:
        print(f"\n  {yellow('⚠')}  No PDFs found in {rust(folder)}\n")
        print(f"  Drop .pdf files into that folder and run again.\n")
        return False

    print(f"\n  {teal('◈')} Indexing {bold(str(total))} PDF{'s' if total != 1 else ''} from {rust(folder)}\n")
    current = [0]

    def cb(name):
        current[0] += 1
        bar = progress_bar(current[0], total, 36, name[:35])
        print(f"\r{bar}", end="", flush=True)

    t0 = time.time()
    index.build(folder, progress_cb=cb)
    elapsed = time.time() - t0
    print(f"\r{' ' * term_width()}\r", end="")  # clear progress line

    s = index.stats
    print(f"  {green('✓')} Indexed {bold(str(s['pages']))} pages "
          f"from {bold(str(s['files']))} files "
          f"in {gold(str(s['build_time']) + 's')}\n")
    return True

# ── INTERACTIVE SEARCH LOOP ───────────────────────────────────
def interactive_loop(index):
    w = term_width()
    print(hr("─"))
    print(f"  {muted('Commands:')}  "
          f"{rust(':q')} quit  "
          f"{rust(':r')} reindex  "
          f"{rust(':files')} list files  "
          f"{rust(':help')} help")
    print(hr("─"))
    print()

    while True:
        try:
            raw = input(f"  {rust('⌕')}  {bold('Search')} {muted('›')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {muted('Goodbye.')}\n")
            break

        if not raw:
            continue

        # Commands
        if raw.lower() in (':q', ':quit', 'exit', 'quit'):
            print(f"\n  {muted('Goodbye.')}\n")
            break

        if raw.lower() == ':files':
            print()
            for e in sorted(set(en['title'] for en in index.entries)):
                print(f"  {teal('▸')}  {e}")
            print()
            continue

        if raw.lower() == ':help':
            print_help()
            continue

        if raw.lower() == ':clear':
            os.system('cls' if sys.platform == 'win32' else 'clear')
            print_header(index)
            continue

        # Search
        t0 = time.time()
        results = index.search(raw)
        elapsed_ms = round((time.time() - t0) * 1000, 1)

        print()
        if not results:
            print(f"  {yellow('○')}  No results for {rust(repr(raw))}")
            print(f"  {muted('Tip: try fewer or broader keywords')}")
        else:
            count = len(results)
            print(f"  {green('●')}  {bold(str(count))} result{'s' if count != 1 else ''} "
                  f"for {rust(repr(raw))}  {muted(f'({elapsed_ms}ms)')}")
            print()
            # Group by file
            seen_files = {}
            rank = 0
            for score, entry in results:
                fname = entry['file']
                if fname not in seen_files:
                    seen_files[fname] = True
                rank += 1
                snip = index.snippet(entry['text'], raw)
                render_result(rank, score, entry, snip, raw)

        print(hr("·"))
        print()

def print_header(index):
    s = index.stats
    w = term_width()
    print(hr("═"))
    parts = [
        f"  {teal('◈')} {bold('Cross-Course Search')}",
        f"  {muted('Files:')} {rust(str(s['files']))}",
        f"  {muted('Pages:')} {rust(str(s['pages']))}",
        f"  {muted('Engine:')} {gold(get_pdf_engine() or 'none')}",
    ]
    print("".join(parts))
    print(hr("═"))
    print()

def print_help():
    print()
    print(f"  {bold('CROSS-COURSE SEARCH — HELP')}")
    print()
    items = [
        ("eigenvalue",       "Simple keyword search"),
        ("hash table",       "Multi-word search (AND logic)"),
        ("DNA replication",  "Phrase-style search"),
        (":files",           "List all indexed documents"),
        (":r",               "Re-index the PDF folder"),
        (":clear",           "Clear the screen"),
        (":q",               "Quit"),
    ]
    for cmd, desc in items:
        print(f"  {rust(cmd.ljust(22))}  {muted(desc)}")
    print()

# ── MAIN ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Cross-Course Search — Terminal UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python terminal_ui.py --folder ./pdfs --query eigenvalue"
    )
    parser.add_argument("--folder", "-f", default="./pdfs",
                        help="Folder containing PDF files (default: ./pdfs)")
    parser.add_argument("--query", "-q", default=None,
                        help="Run a single query and exit")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable colored output")
    args = parser.parse_args()

    global USE_COLOR
    if args.no_color:
        USE_COLOR = False

    folder = args.folder
    if not os.path.isdir(folder):
        print(f"\n  {red('✗')} Folder not found: {folder}")
        print(f"  Create it and add PDFs, or use --folder <path>\n")
        sys.exit(1)

    if not get_pdf_engine():
        print(f"\n  {red('✗')} No PDF library found.")
        print(f"  Install one: pip install pdfplumber\n")
        sys.exit(1)

    print_splash()
    print(f"  {muted('PDF folder:')} {rust(os.path.abspath(folder))}")
    print(f"  {muted('PDF engine:')} {gold(get_pdf_engine())}")
    print()

    index = Index()
    ok = build_with_progress(index, folder)
    if not ok:
        sys.exit(1)

    # Single query mode
    if args.query:
        results = index.search(args.query)
        if not results:
            print(f"  {yellow('○')}  No results for '{args.query}'\n")
        else:
            print(f"  {green('●')}  {len(results)} result(s) for '{args.query}'\n")
            for i, (score, entry) in enumerate(results, 1):
                snip = index.snippet(entry['text'], args.query)
                render_result(i, score, entry, snip, args.query)
        return

    # Interactive mode
    print_header(index)
    interactive_loop(index)


if __name__ == "__main__":
    main()
