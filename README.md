# 📚 Cross-Course Search

> Lightning-fast full-text search across all your university PDFs.  
> No cloud. No login. No Elasticsearch. Runs entirely on your machine.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Flask](https://img.shields.io/badge/Flask-2.3+-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Mac%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-orange)

## ✨ Features
- 🔍 Instant search across every PDF in a folder simultaneously
- ⚡ Results in under 10ms with relevance ranking and page numbers
- 🌐 Web UI — browser-based, works on any OS
- 💻 Desktop App — native Windows GUI, zero extra install
- 🖥️ Terminal UI — colored interactive shell interface
- 🔒 100% local — your files never leave your machine

## 🚀 Quick Start
```bash
git clone https://github.com/YOUR_USERNAME/cross-course-search.git
cd cross-course-search
pip install flask pdfplumber pypdf
python app.py
```
Open http://localhost:5000

## 🎮 Three Interfaces

| Command | Interface |
|---|---|
| `python app.py` | Web UI at localhost:5000 |
| `python terminal_ui.py` | Interactive terminal |
| `python desktop_app.py` | Windows desktop app |

## 📁 Add Your PDFs
Drop any `.pdf` files into the `pdfs/` folder and restart.

## 🛠️ Built With
Python · Flask · pdfplumber · tkinter · Vanilla JS

## 📄 License
MIT
