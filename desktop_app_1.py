"""
Cross-Course Search -- Windows Desktop App
A full-featured GUI application built with tkinter (included in Python on Windows).

Usage:
    python desktop_app.py

Requirements:
    pip install pdfplumber pypdf  (PyMuPDF optional but faster)
"""

import os
import re
import sys
import time
import threading
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    from tkinter.font import Font
except ImportError:
    print("tkinter not found. On Debian/Ubuntu: sudo apt-get install python3-tk")
    sys.exit(1)

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
    except Exception:
        pass
    return pages

# ── COLOUR PALETTE ────────────────────────────────────────────
COLORS = {
    "bg":         "#0f1318",
    "bg2":        "#161c24",
    "bg3":        "#1e2730",
    "border":     "#2a3540",
    "accent":     "#e8621a",
    "accent2":    "#ff8c42",
    "teal":       "#2ec4b6",
    "gold":       "#f4b942",
    "text":       "#e8ddd0",
    "text2":      "#9aabb8",
    "text3":      "#566a78",
    "green":      "#52d68a",
    "red":        "#ff4d6d",
    "highlight":  "#3d2810",
    "select":     "#2a3d52",
    "sidebar_bg": "#0c1016",
}

# ── INDEX ENGINE ──────────────────────────────────────────────
class SearchIndex:
    def __init__(self):
        self.entries = []
        self.file_list = []
        self.stats = {"files": 0, "pages": 0, "build_time": 0}
        self.ready = False

    def friendly_title(self, filename):
        name = Path(filename).stem
        name = re.sub(r'([A-Za-z])(\d)', r'\1 \2', name)
        name = name.replace('_', ' ')
        parts = name.split(' ', 2)
        if len(parts) >= 3:
            return f"{parts[0]} {parts[1]} -- {parts[2]}"
        return name

    def build(self, folder, progress_cb=None, done_cb=None):
        t0 = time.time()
        self.entries = []
        self.file_list = []
        pdf_files = sorted(Path(folder).glob("*.pdf"))
        total = len(pdf_files)

        for i, pdf_path in enumerate(pdf_files):
            if progress_cb:
                progress_cb(i, total, pdf_path.name)
            title = self.friendly_title(pdf_path.name)
            self.file_list.append({"name": pdf_path.name, "title": title, "path": str(pdf_path)})
            for page_num, text in extract_pages(pdf_path):
                if text.strip():
                    self.entries.append({
                        "file": pdf_path.name,
                        "title": title,
                        "page": page_num,
                        "text": text,
                        "text_lower": text.lower(),
                        "path": str(pdf_path),
                    })

        self.stats = {
            "files": len(pdf_files),
            "pages": len(self.entries),
            "build_time": round(time.time() - t0, 2),
        }
        self.ready = True
        if done_cb:
            done_cb()

    def search(self, query, limit=50):
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

    def get_snippet(self, text, query, window=300):
        tl = text.lower()
        terms = [t.strip().lower() for t in query.split() if t.strip()]
        pos = -1
        for term in terms:
            p = tl.find(term)
            if p != -1:
                pos = p
                break
        if pos == -1:
            return text[:window].strip()
        start = max(0, pos - 80)
        end = min(len(text), pos + window)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end].strip() + suffix


# ── CUSTOM WIDGETS ────────────────────────────────────────────
class PlaceholderEntry(tk.Entry):
    """Entry widget with placeholder text."""
    def __init__(self, master, placeholder="", *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.placeholder = placeholder
        self.placeholder_color = COLORS["text3"]
        self.default_fg = kwargs.get("fg", COLORS["text"])
        self._showing_placeholder = False
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()

    def _show_placeholder(self):
        if not self.get():
            self.insert(0, self.placeholder)
            self.config(fg=self.placeholder_color)
            self._showing_placeholder = True

    def _on_focus_in(self, event):
        if self._showing_placeholder:
            self.delete(0, tk.END)
            self.config(fg=self.default_fg)
            self._showing_placeholder = False

    def _on_focus_out(self, event):
        if not self.get():
            self._show_placeholder()

    def get_value(self):
        if self._showing_placeholder:
            return ""
        return self.get()


class Tooltip:
    """Hover tooltips."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text,
                       bg=COLORS["bg3"], fg=COLORS["text2"],
                       font=("Consolas", 9), padx=8, pady=4,
                       relief="flat", bd=0)
        lbl.pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ── MAIN APPLICATION ──────────────────────────────────────────
class CrossCourseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cross-Course Search")
        self.configure(bg=COLORS["bg"])
        self.geometry("1200x780")
        self.minsize(900, 600)

        # State
        self.index = SearchIndex()
        self.pdf_folder = tk.StringVar(value=str(Path(__file__).parent / "pdfs"))
        self.search_query = tk.StringVar()
        self.search_after_id = None
        self.selected_result = None
        self.results_data = []
        self.current_view = "search"  # "search" | "reader" | "files"

        # Fonts
        self._setup_fonts()
        self._setup_styles()
        self._build_ui()
        self._apply_window_chrome()

        # Start indexing
        self.after(200, self._start_indexing)

    def _setup_fonts(self):
        self.font_title  = Font(family="Georgia",  size=14, weight="bold")
        self.font_head   = Font(family="Georgia",  size=11, weight="bold")
        self.font_mono   = Font(family="Consolas", size=10)
        self.font_mono_s = Font(family="Consolas", size=9)
        self.font_body   = Font(family="Segoe UI", size=10)
        self.font_body_s = Font(family="Segoe UI", size=9)
        self.font_search = Font(family="Segoe UI", size=16)
        self.font_logo   = Font(family="Georgia",  size=18, weight="bold")
        self.font_badge  = Font(family="Consolas", size=8, weight="bold")

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=COLORS["bg3"],
                        troughcolor=COLORS["bg"],
                        bordercolor=COLORS["bg"],
                        arrowcolor=COLORS["text3"],
                        relief="flat")
        style.configure("TProgressbar",
                        background=COLORS["accent"],
                        troughcolor=COLORS["bg3"],
                        bordercolor=COLORS["bg"],
                        lightcolor=COLORS["accent"],
                        darkcolor=COLORS["accent"])

    def _apply_window_chrome(self):
        """Windows-specific window styling."""
        if sys.platform == "win32":
            try:
                from ctypes import windll
                hwnd = windll.user32.GetParent(self.winfo_id())
                windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_bool(True)), sizeof(c_bool))
            except Exception:
                pass
        self.iconbitmap(default="")

    # ── UI CONSTRUCTION ───────────────────────────────────────
    def _build_ui(self):
        # Root grid: sidebar | main
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=COLORS["sidebar_bg"], width=220)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(5, weight=1)

        # Logo
        logo_frame = tk.Frame(sb, bg=COLORS["sidebar_bg"], pady=20)
        logo_frame.grid(row=0, column=0, sticky="ew", padx=18)
        tk.Label(logo_frame, text="Cross", font=self.font_logo,
                 bg=COLORS["sidebar_bg"], fg=COLORS["accent"]).pack(side="left")
        tk.Label(logo_frame, text="-Course", font=self.font_logo,
                 bg=COLORS["sidebar_bg"], fg=COLORS["text"]).pack(side="left")

        tk.Label(sb, text="PDF SEARCH ENGINE",
                 font=self.font_badge, bg=COLORS["sidebar_bg"],
                 fg=COLORS["text3"]).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 16))

        # Divider
        tk.Frame(sb, bg=COLORS["border"], height=1).grid(row=2, column=0, sticky="ew", padx=14)

        # Nav buttons
        nav_frame = tk.Frame(sb, bg=COLORS["sidebar_bg"])
        nav_frame.grid(row=3, column=0, sticky="ew", pady=8)

        self._nav_btns = {}
        nav_items = [
            ("🔍  Search",    "search"),
            ("📄  Documents", "files"),
            ("📖  Reader",    "reader"),
        ]
        for label, view in nav_items:
            btn = tk.Button(
                nav_frame, text=label, anchor="w",
                font=self.font_body, padx=18, pady=8,
                bg=COLORS["sidebar_bg"], fg=COLORS["text2"],
                activebackground=COLORS["bg3"],
                activeforeground=COLORS["text"],
                relief="flat", bd=0, cursor="hand2",
                command=lambda v=view: self._switch_view(v)
            )
            btn.pack(fill="x")
            self._nav_btns[view] = btn

        # Divider
        tk.Frame(sb, bg=COLORS["border"], height=1).grid(row=4, column=0, sticky="ew", padx=14)

        # Stats panel
        self.stats_frame = tk.Frame(sb, bg=COLORS["sidebar_bg"], pady=12)
        self.stats_frame.grid(row=5, column=0, sticky="nsew", padx=14)

        tk.Label(self.stats_frame, text="INDEX STATS",
                 font=self.font_badge, bg=COLORS["sidebar_bg"],
                 fg=COLORS["text3"]).pack(anchor="w", pady=(0, 8))

        self.stat_labels = {}
        for key, label in [("files", "Documents"), ("pages", "Pages"), ("engine", "Engine"), ("time", "Build time")]:
            row = tk.Frame(self.stats_frame, bg=COLORS["sidebar_bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=self.font_body_s,
                     bg=COLORS["sidebar_bg"], fg=COLORS["text3"]).pack(side="left")
            lbl = tk.Label(row, text="--", font=self.font_mono_s,
                           bg=COLORS["sidebar_bg"], fg=COLORS["accent"])
            lbl.pack(side="right")
            self.stat_labels[key] = lbl

        # Folder selector at bottom
        folder_frame = tk.Frame(sb, bg=COLORS["sidebar_bg"], pady=12)
        folder_frame.grid(row=6, column=0, sticky="ew", padx=14)

        tk.Label(folder_frame, text="PDF FOLDER",
                 font=self.font_badge, bg=COLORS["sidebar_bg"],
                 fg=COLORS["text3"]).pack(anchor="w", pady=(0, 6))

        self.folder_lbl = tk.Label(folder_frame, text=".../pdfs",
                                   font=self.font_mono_s,
                                   bg=COLORS["sidebar_bg"], fg=COLORS["text2"],
                                   wraplength=180, justify="left")
        self.folder_lbl.pack(anchor="w")

        btn_row = tk.Frame(folder_frame, bg=COLORS["sidebar_bg"])
        btn_row.pack(fill="x", pady=(6, 0))
        self._sidebar_btn("Browse", btn_row, self._browse_folder).pack(side="left", padx=(0, 6))
        self._sidebar_btn("Re-index", btn_row, self._start_indexing).pack(side="left")

    def _sidebar_btn(self, text, parent, cmd):
        return tk.Button(
            parent, text=text, font=self.font_body_s,
            bg=COLORS["bg3"], fg=COLORS["text2"],
            activebackground=COLORS["border"],
            activeforeground=COLORS["text"],
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2", command=cmd
        )

    def _build_main(self):
        main = tk.Frame(self, bg=COLORS["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # Three views stacked, only one shown at a time
        self.view_search = self._build_search_view(main)
        self.view_files  = self._build_files_view(main)
        self.view_reader = self._build_reader_view(main)

        for v in [self.view_search, self.view_files, self.view_reader]:
            v.grid(row=0, column=0, sticky="nsew")

        self._switch_view("search")

    def _build_search_view(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # ── Top bar ──
        topbar = tk.Frame(frame, bg=COLORS["bg2"], pady=16)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(0, weight=1)

        tk.Label(topbar, text="Search your lecture library",
                 font=self.font_title, bg=COLORS["bg2"],
                 fg=COLORS["text"]).grid(row=0, column=0, sticky="w", padx=24)
        tk.Label(topbar, text="Type to search across all indexed PDFs",
                 font=self.font_body_s, bg=COLORS["bg2"],
                 fg=COLORS["text3"]).grid(row=1, column=0, sticky="w", padx=24, pady=(2, 0))

        # ── Search bar ──
        search_outer = tk.Frame(frame, bg=COLORS["bg3"], pady=16)
        search_outer.grid(row=1, column=0, sticky="ew")
        search_outer.grid_columnconfigure(0, weight=1)

        search_inner = tk.Frame(search_outer, bg=COLORS["bg3"])
        search_inner.grid(row=0, column=0, sticky="ew", padx=24)
        search_inner.grid_columnconfigure(0, weight=1)

        entry_wrap = tk.Frame(search_inner, bg=COLORS["border"], padx=1, pady=1)
        entry_wrap.grid(row=0, column=0, sticky="ew")
        entry_wrap.grid_columnconfigure(0, weight=1)

        self.search_entry = tk.Entry(
            entry_wrap, font=self.font_search,
            bg=COLORS["bg2"], fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            relief="flat", bd=0
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        self.search_entry.insert(0, "Search eigenvalues, DNA replication, Nash equilibrium...")
        self.search_entry.config(fg=COLORS["text3"])

        def _focus_in(e):
            if self.search_entry.get() == "Search eigenvalues, DNA replication, Nash equilibrium...":
                self.search_entry.delete(0, tk.END)
                self.search_entry.config(fg=COLORS["text"])
        def _focus_out(e):
            if not self.search_entry.get():
                self.search_entry.insert(0, "Search eigenvalues, DNA replication, Nash equilibrium...")
                self.search_entry.config(fg=COLORS["text3"])

        self.search_entry.bind("<FocusIn>",  _focus_in)
        self.search_entry.bind("<FocusOut>", _focus_out)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        self.search_entry.bind("<Return>",     self._do_search_now)
        self.search_entry.bind("<Escape>",     lambda e: self._clear_search())

        # Quick searches
        chips_frame = tk.Frame(search_inner, bg=COLORS["bg3"])
        chips_frame.grid(row=1, column=0, sticky="w", pady=(10, 0))
        tk.Label(chips_frame, text="TRY: ",
                 font=self.font_badge, bg=COLORS["bg3"],
                 fg=COLORS["text3"]).pack(side="left")
        for term in ["eigenvalue", "hash table", "DNA replication", "Nash equilibrium", "Schrödinger"]:
            btn = tk.Button(
                chips_frame, text=term, font=self.font_body_s,
                bg=COLORS["bg3"], fg=COLORS["text2"],
                activebackground=COLORS["accent"],
                activeforeground="#000",
                relief="flat", bd=0, padx=8, pady=3,
                cursor="hand2",
                command=lambda t=term: self._quick_search(t)
            )
            btn.pack(side="left", padx=3)

        # ── Results pane ──
        results_outer = tk.Frame(frame, bg=COLORS["bg"])
        results_outer.grid(row=2, column=0, sticky="nsew")
        results_outer.grid_rowconfigure(1, weight=1)
        results_outer.grid_columnconfigure(0, weight=1)

        # Results meta bar
        self.results_meta = tk.Label(results_outer, text="",
                                     font=self.font_mono_s,
                                     bg=COLORS["bg"], fg=COLORS["text3"],
                                     anchor="w")
        self.results_meta.grid(row=0, column=0, sticky="ew", padx=24, pady=(10, 4))

        # Canvas + scrollbar for results
        canvas_frame = tk.Frame(results_outer, bg=COLORS["bg"])
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.results_canvas = tk.Canvas(canvas_frame, bg=COLORS["bg"],
                                        highlightthickness=0, bd=0)
        vscroll = ttk.Scrollbar(canvas_frame, orient="vertical",
                                command=self.results_canvas.yview)
        self.results_canvas.configure(yscrollcommand=vscroll.set)
        self.results_canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")

        self.results_inner = tk.Frame(self.results_canvas, bg=COLORS["bg"])
        self.results_window = self.results_canvas.create_window(
            (0, 0), window=self.results_inner, anchor="nw"
        )

        def _on_configure(e):
            self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))
            self.results_canvas.itemconfig(self.results_window, width=self.results_canvas.winfo_width())

        self.results_inner.bind("<Configure>", _on_configure)
        self.results_canvas.bind("<Configure>", lambda e: self.results_canvas.itemconfig(
            self.results_window, width=e.width))
        self.results_canvas.bind("<MouseWheel>", lambda e: self.results_canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))

        # Progress bar (shown during indexing)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var,
                                            maximum=100, style="TProgressbar")
        self.progress_label = tk.Label(frame, text="", font=self.font_mono_s,
                                       bg=COLORS["bg"], fg=COLORS["text3"])

        self._show_welcome()
        return frame

    def _build_files_view(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        topbar = tk.Frame(frame, bg=COLORS["bg2"], pady=16)
        topbar.grid(row=0, column=0, sticky="ew")
        tk.Label(topbar, text="Indexed Documents",
                 font=self.font_title, bg=COLORS["bg2"],
                 fg=COLORS["text"]).pack(anchor="w", padx=24)
        tk.Label(topbar, text="All PDFs currently in the search index",
                 font=self.font_body_s, bg=COLORS["bg2"],
                 fg=COLORS["text3"]).pack(anchor="w", padx=24, pady=(2, 0))

        # Files list
        list_frame = tk.Frame(frame, bg=COLORS["bg"])
        list_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=16)
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self.files_listbox = tk.Listbox(
            list_frame,
            font=self.font_body,
            bg=COLORS["bg2"], fg=COLORS["text"],
            selectbackground=COLORS["select"],
            selectforeground=COLORS["text"],
            activestyle="none",
            relief="flat", bd=0,
            highlightthickness=1,
            highlightcolor=COLORS["border"],
            highlightbackground=COLORS["border"],
        )
        files_scroll = ttk.Scrollbar(list_frame, orient="vertical",
                                     command=self.files_listbox.yview)
        self.files_listbox.configure(yscrollcommand=files_scroll.set)
        self.files_listbox.grid(row=0, column=0, sticky="nsew")
        files_scroll.grid(row=0, column=1, sticky="ns")

        self.files_listbox.bind("<Double-Button-1>", self._open_selected_file)
        self.files_listbox.bind("<Return>", self._open_selected_file)

        btn_row = tk.Frame(frame, bg=COLORS["bg"], pady=10)
        btn_row.grid(row=2, column=0, sticky="ew", padx=24)
        tk.Button(btn_row, text="Open in File Explorer",
                  font=self.font_body, bg=COLORS["bg3"], fg=COLORS["text2"],
                  activebackground=COLORS["border"], relief="flat", bd=0,
                  padx=14, pady=6, cursor="hand2",
                  command=self._open_pdf_folder).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Add PDFs...",
                  font=self.font_body, bg=COLORS["accent"], fg="#000",
                  activebackground=COLORS["accent2"], relief="flat", bd=0,
                  padx=14, pady=6, cursor="hand2",
                  command=self._browse_folder).pack(side="left")

        return frame

    def _build_reader_view(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        topbar = tk.Frame(frame, bg=COLORS["bg2"], pady=12)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        tk.Label(topbar, text="📖  Text Reader",
                 font=self.font_title, bg=COLORS["bg2"],
                 fg=COLORS["text"]).grid(row=0, column=0, sticky="w", padx=24)
        self.reader_title = tk.Label(topbar, text="Select a result to read",
                                     font=self.font_body_s, bg=COLORS["bg2"],
                                     fg=COLORS["accent"])
        self.reader_title.grid(row=0, column=1, sticky="w", padx=12)

        self.reader_text = scrolledtext.ScrolledText(
            frame, font=("Georgia", 12),
            bg=COLORS["bg2"], fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            relief="flat", bd=0, padx=28, pady=24,
            wrap="word", state="disabled",
            spacing3=4
        )
        self.reader_text.grid(row=1, column=0, sticky="nsew")
        self.reader_text.tag_configure("highlight", background=COLORS["highlight"],
                                       foreground=COLORS["accent2"])
        self.reader_text.tag_configure("header", font=("Georgia", 14, "bold"),
                                       foreground=COLORS["accent"])

        return frame

    # ── INDEXING ──────────────────────────────────────────────
    def _start_indexing(self):
        folder = self.pdf_folder.get()
        if not os.path.isdir(folder):
            messagebox.showwarning("Folder not found",
                                   f"Could not find:\n{folder}\n\nPlease select a valid PDF folder.")
            self._browse_folder()
            return

        self._show_progress(True)
        self.index.ready = False

        def progress_cb(i, total, name):
            pct = (i / max(total, 1)) * 100
            self.after(0, lambda: self._update_progress(pct, name))

        def done_cb():
            self.after(0, self._on_index_done)

        t = threading.Thread(
            target=self.index.build,
            args=(folder,),
            kwargs={"progress_cb": progress_cb, "done_cb": done_cb},
            daemon=True
        )
        t.start()

    def _show_progress(self, show):
        if show:
            self.progress_bar.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 4))
            self.progress_label.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 8))
        else:
            self.progress_bar.grid_remove()
            self.progress_label.grid_remove()

    def _update_progress(self, pct, name):
        self.progress_var.set(pct)
        self.progress_label.config(text=f"  Indexing: {name}")

    def _on_index_done(self):
        self._show_progress(False)
        s = self.index.stats
        self.stat_labels["files"].config(text=str(s["files"]))
        self.stat_labels["pages"].config(text=str(s["pages"]))
        self.stat_labels["engine"].config(text=get_pdf_engine() or "none")
        self.stat_labels["time"].config(text=f"{s['build_time']}s")
        self.folder_lbl.config(text=f".../{Path(self.pdf_folder.get()).name}")
        self._refresh_files_list()
        self._show_welcome()

    # ── SEARCH ────────────────────────────────────────────────
    def _on_search_key(self, event):
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        q = self.search_entry.get()
        if q == "Search eigenvalues, DNA replication, Nash equilibrium...":
            return
        if not q.strip():
            self._show_welcome()
            return
        self.search_after_id = self.after(200, self._do_search_now)

    def _do_search_now(self, event=None):
        q = self.search_entry.get().strip()
        if q == "Search eigenvalues, DNA replication, Nash equilibrium...":
            return
        if not q:
            self._show_welcome()
            return
        if not self.index.ready:
            self._show_message("⏳", "Index building...", "Please wait a moment.")
            return
        t0 = time.time()
        results = self.index.search(q)
        elapsed = round((time.time() - t0) * 1000, 1)
        self.results_data = results
        self._render_results(results, q, elapsed)

    def _quick_search(self, term):
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, term)
        self.search_entry.config(fg=COLORS["text"])
        self._switch_view("search")
        self._do_search_now()

    def _clear_search(self):
        self.search_entry.delete(0, tk.END)
        self._show_welcome()

    # ── RESULT RENDERING ──────────────────────────────────────
    def _clear_results(self):
        for w in self.results_inner.winfo_children():
            w.destroy()

    def _show_welcome(self):
        self._clear_results()
        self.results_meta.config(text="")
        f = self.results_inner
        tk.Label(f, text="📚", font=Font(size=40),
                 bg=COLORS["bg"], fg=COLORS["text2"]).pack(pady=(60, 10))
        tk.Label(f, text="Search your course library",
                 font=Font(family="Georgia", size=16, weight="bold"),
                 bg=COLORS["bg"], fg=COLORS["text"]).pack()
        tk.Label(f, text="Type a concept, formula, or keyword above.",
                 font=self.font_body, bg=COLORS["bg"],
                 fg=COLORS["text3"]).pack(pady=(6, 0))

    def _show_message(self, icon, title, body):
        self._clear_results()
        f = self.results_inner
        tk.Label(f, text=icon, font=Font(size=36),
                 bg=COLORS["bg"]).pack(pady=(60, 10))
        tk.Label(f, text=title, font=self.font_head,
                 bg=COLORS["bg"], fg=COLORS["text"]).pack()
        tk.Label(f, text=body, font=self.font_body,
                 bg=COLORS["bg"], fg=COLORS["text3"]).pack(pady=(6, 0))

    def _render_results(self, results, query, elapsed_ms):
        self._clear_results()
        if not results:
            self._show_message('No results', 'No results for: ' + query,
                               "Try different keywords or broader terms.")
            self.results_meta.config(text="")
            return

        count = len(results)
        self.results_meta.config(text='  {} result{} for: {}   -   {}ms'.format(count, 's' if count != 1 else '', query, elapsed_ms))



        # Group by file
        groups = {}
        for score, entry in results:
            f = entry["file"]
            if f not in groups:
                groups[f] = {"title": entry["title"], "hits": []}
            groups[f]["hits"].append((score, entry))

        for gidx, (fname, gdata) in enumerate(groups.items()):
            self._render_file_group(gdata, query, gidx)

    def _render_file_group(self, group, query, idx):
        f = self.results_inner

        # Group header
        gh = tk.Frame(f, bg=COLORS["bg2"], pady=0)
        gh.pack(fill="x", padx=20, pady=(14 if idx == 0 else 20, 0))

        left = tk.Frame(gh, bg=COLORS["bg2"])
        left.pack(side="left", padx=12, pady=10)

        icon = tk.Label(left, text="📄",
                        font=Font(size=18),
                        bg=COLORS["bg2"])
        icon.pack(side="left", padx=(0, 10))

        tk.Label(left, text=group["title"],
                 font=self.font_head,
                 bg=COLORS["bg2"], fg=COLORS["text"]).pack(side="left")

        match_count = len(group["hits"])
        tk.Label(gh, text=f"{match_count} match{'es' if match_count != 1 else ''}",
                 font=self.font_mono_s,
                 bg=COLORS["bg2"], fg=COLORS["text3"]).pack(side="right", padx=14)

        # Hit cards
        for cidx, (score, entry) in enumerate(group["hits"]):
            self._render_card(entry, query, score)

    def _render_card(self, entry, query, score):
        f = self.results_inner
        card = tk.Frame(f, bg=COLORS["bg3"], cursor="hand2",
                        highlightthickness=1,
                        highlightbackground=COLORS["border"],
                        highlightcolor=COLORS["accent"])
        card.pack(fill="x", padx=20, pady=3)

        card.bind("<Enter>",  lambda e, c=card: c.config(highlightbackground=COLORS["accent"]))
        card.bind("<Leave>",  lambda e, c=card: c.config(highlightbackground=COLORS["border"]))
        card.bind("<Button-1>", lambda e, en=entry, q=query: self._open_in_reader(en, q))

        inner = tk.Frame(card, bg=COLORS["bg3"], padx=16, pady=10)
        inner.pack(fill="x")
        inner.bind("<Button-1>", lambda e, en=entry, q=query: self._open_in_reader(en, q))

        # Header row
        hrow = tk.Frame(inner, bg=COLORS["bg3"])
        hrow.pack(fill="x")
        hrow.bind("<Button-1>", lambda e, en=entry, q=query: self._open_in_reader(en, q))

        page_badge = tk.Label(hrow,
                              text=f"  pg.{entry['page']}  ",
                              font=self.font_badge,
                              bg=COLORS["teal"], fg="#000")
        page_badge.pack(side="left")
        page_badge.bind("<Button-1>", lambda e, en=entry, q=query: self._open_in_reader(en, q))

        tk.Label(hrow, text=f"  relevance {score}",
                 font=self.font_mono_s,
                 bg=COLORS["bg3"], fg=COLORS["text3"]).pack(side="right")

        # Snippet
        snip = self.index.get_snippet(entry["text"], query)
        snip_clean = snip[:250].replace('\n', ' ').strip()

        snippet_lbl = tk.Label(inner, text=snip_clean,
                               font=self.font_body_s,
                               bg=COLORS["bg3"], fg=COLORS["text2"],
                               wraplength=800, justify="left", anchor="w")
        snippet_lbl.pack(fill="x", pady=(6, 0))
        snippet_lbl.bind("<Button-1>", lambda e, en=entry, q=query: self._open_in_reader(en, q))

    # ── READER ────────────────────────────────────────────────
    def _open_in_reader(self, entry, query):
        self._switch_view("reader")
        self.reader_title.config(
            text=f"{entry['title']}  --  Page {entry['page']}"
        )
        text = entry["text"]
        self.reader_text.config(state="normal")
        self.reader_text.delete("1.0", tk.END)

        # Insert header
        self.reader_text.insert("end", f"{entry['title']}\n", "header")
        self.reader_text.insert("end", f"Page {entry['page']}  ·  {entry['file']}\n\n")

        # Insert text with highlights
        terms = [t.strip().lower() for t in query.split() if t.strip()]
        segments = []
        remaining = text
        while remaining:
            best_pos = len(remaining)
            best_term = None
            for term in terms:
                p = remaining.lower().find(term)
                if p != -1 and p < best_pos:
                    best_pos = p
                    best_term = term
            if best_term is None:
                segments.append((remaining, False))
                break
            if best_pos > 0:
                segments.append((remaining[:best_pos], False))
            segments.append((remaining[best_pos:best_pos + len(best_term)], True))
            remaining = remaining[best_pos + len(best_term):]

        for seg, is_highlight in segments:
            tag = "highlight" if is_highlight else ""
            self.reader_text.insert("end", seg, tag)

        self.reader_text.config(state="disabled")

        # Scroll to first match
        idx = self.reader_text.search(query.split()[0] if query.split() else "", "1.0",
                                      nocase=True, stopindex=tk.END)
        if idx:
            self.reader_text.see(idx)

    # ── FILES VIEW ────────────────────────────────────────────
    def _refresh_files_list(self):
        self.files_listbox.delete(0, tk.END)
        for fi in self.index.file_list:
            self.files_listbox.insert(tk.END, f"  {fi['title']}")

    def _open_selected_file(self, event=None):
        sel = self.files_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.index.file_list):
            path = self.index.file_list[idx]["path"]
            try:
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    os.system(f"open '{path}'")
                else:
                    os.system(f"xdg-open '{path}'")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _open_pdf_folder(self):
        folder = self.pdf_folder.get()
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                os.system(f"open '{folder}'")
            else:
                os.system(f"xdg-open '{folder}'")
        except Exception:
            pass

    # ── NAVIGATION ───────────────────────────────────────────
    def _switch_view(self, view):
        self.current_view = view
        views = {
            "search": self.view_search,
            "files":  self.view_files,
            "reader": self.view_reader,
        }
        for v in views.values():
            v.grid_remove()
        views[view].grid(row=0, column=0, sticky="nsew")

        for name, btn in self._nav_btns.items():
            if name == view:
                btn.config(bg=COLORS["bg3"], fg=COLORS["accent"])
            else:
                btn.config(bg=COLORS["sidebar_bg"], fg=COLORS["text2"])

    # ── FOLDER ────────────────────────────────────────────────
    def _browse_folder(self):
        folder = filedialog.askdirectory(
            title="Select PDF Folder",
            initialdir=self.pdf_folder.get()
        )
        if folder:
            self.pdf_folder.set(folder)
            self._start_indexing()


# ── ENTRY POINT ──────────────────────────────────────────────
def main():
    if not get_pdf_engine():
        print("No PDF library found. Install: pip install pdfplumber")
        sys.exit(1)

    app = CrossCourseApp()
    app.mainloop()


if __name__ == "__main__":
    main()

