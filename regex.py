"""
PDF / TXT Document Searcher
============================
Aplicação desktop para busca de documentos em pastas locais.
Modo atual: arquivos TXT (fácil de trocar para PDF).

Requisitos:
    pip install customtkinter

Uso:
    python pdf_searcher.py
"""

import os
import re
import zipfile
import threading
import subprocess
import platform
import tkinter as tk
from tkinter import filedialog, messagebox
from collections import defaultdict
from pathlib import Path
from typing import Optional

import customtkinter as ctk

# ──────────────────────────────────────────────
# Modo de busca — troque para ".pdf" quando quiser
# ──────────────────────────────────────────────
TARGET_EXT = ".txt"   # <- altere para ".pdf" para voltar ao modo PDF

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg_primary":    "#0f1117",
    "bg_secondary":  "#161b22",
    "bg_card":       "#1c2333",
    "bg_hover":      "#21262d",
    "accent":        "#2f81f7",
    "accent_hover":  "#388bfd",
    "accent_dim":    "#1f4f8a",
    "text_primary":  "#e6edf3",
    "text_secondary":"#8b949e",
    "text_muted":    "#484f58",
    "success":       "#3fb950",
    "warning":       "#d29922",
    "error":         "#f85149",
    "border":        "#30363d",
    "zip_badge":     "#d2a14e",
    "file_badge":    "#2f81f7",
}


# ══════════════════════════════════════════════
#  Modelo de dados
# ══════════════════════════════════════════════
class IndexEntry:
    __slots__ = ("nome", "caminho", "tipo", "zip_path")

    def __init__(self, nome: str, caminho: str,
                 tipo: str = "TXT", zip_path: Optional[str] = None):
        self.nome = nome
        self.caminho = caminho
        self.tipo = tipo          # "TXT" / "PDF" / "ZIP"
        self.zip_path = zip_path

    def full_path(self) -> str:
        if self.tipo != "ZIP":
            return os.path.join(self.caminho, self.nome)
        return self.zip_path or ""


# ══════════════════════════════════════════════
#  Motor de indexação
# ══════════════════════════════════════════════
class IndexEngine:
    _NUM_RE = re.compile(r"\d+")

    def __init__(self):
        self.index: dict[str, list[IndexEntry]] = defaultdict(list)
        self.total_files = 0
        self.total_codes = 0

    def reset(self):
        self.index.clear()
        self.total_files = 0
        self.total_codes = 0

    def scan(self, root: str, progress_cb=None, status_cb=None) -> None:
        self.reset()
        all_items = list(self._walk_items(root))
        total = len(all_items)

        for idx, (item_type, filepath) in enumerate(all_items):
            if progress_cb:
                progress_cb(idx + 1, total)

            if item_type == "file":
                self._index_file(filepath)
            elif item_type == "zip":
                if status_cb:
                    status_cb(f"Lendo ZIP: {os.path.basename(filepath)}")
                self._index_zip(filepath)

        self.total_codes = len(self.index)
        if status_cb:
            status_cb(
                f"✓ Concluído — {self.total_files} arquivos, "
                f"{self.total_codes} códigos"
            )

    def _walk_items(self, root: str):
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                low = fname.lower()
                full = os.path.join(dirpath, fname)
                if low.endswith(TARGET_EXT):
                    yield ("file", full)
                elif low.endswith(".zip"):
                    yield ("zip", full)

    def _index_file(self, filepath: str) -> None:
        nome = os.path.basename(filepath)
        pasta = os.path.dirname(filepath)
        tipo = TARGET_EXT.lstrip(".").upper()
        entry = IndexEntry(nome=nome, caminho=pasta, tipo=tipo)
        self._add_to_index(nome, entry)
        self.total_files += 1

    def _index_zip(self, zip_filepath: str) -> None:
        try:
            with zipfile.ZipFile(zip_filepath, "r") as zf:
                for info in zf.infolist():
                    if info.filename.lower().endswith(TARGET_EXT):
                        nome = os.path.basename(info.filename)
                        pasta_interna = os.path.dirname(info.filename)
                        entry = IndexEntry(
                            nome=nome,
                            caminho=pasta_interna or "/",
                            tipo="ZIP",
                            zip_path=zip_filepath,
                        )
                        self._add_to_index(nome, entry)
                        self.total_files += 1
        except (zipfile.BadZipFile, PermissionError, OSError):
            pass

    def _add_to_index(self, filename: str, entry: IndexEntry) -> None:
        stem = Path(filename).stem
        for code in self._NUM_RE.findall(stem):
            self.index[code].append(entry)

    def search(self, query: str) -> list[IndexEntry]:
        q = query.strip()
        if not q or not q.isdigit():
            return []
        return [e for key, entries in self.index.items()
                if key.startswith(q) for e in entries]


# ══════════════════════════════════════════════
#  Linha de resultado
# ══════════════════════════════════════════════
class ResultRow(ctk.CTkFrame):
    def __init__(self, master, entry: IndexEntry, on_double_click, row_index: int):
        bg = COLORS["bg_card"] if row_index % 2 == 0 else COLORS["bg_secondary"]
        super().__init__(master, fg_color=bg, corner_radius=0)
        self._bg = bg

        self.bind("<Enter>", lambda _: self.configure(fg_color=COLORS["bg_hover"]))
        self.bind("<Leave>", lambda _: self.configure(fg_color=self._bg))

        badge_color = COLORS["zip_badge"] if entry.tipo == "ZIP" else COLORS["file_badge"]
        badge = ctk.CTkLabel(
            self, text=f" {entry.tipo} ",
            fg_color=badge_color, corner_radius=4,
            text_color="#ffffff",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=38,
        )
        badge.pack(side="left", padx=(10, 6), pady=8)

        name_lbl = ctk.CTkLabel(
            self, text=entry.nome,
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        name_lbl.pack(side="left", padx=(0, 8), pady=8, fill="x", expand=True)

        path_text = (f"📦 {os.path.basename(entry.zip_path or '')}"
                     if entry.tipo == "ZIP"
                     else self._short_path(entry.caminho))
        path_lbl = ctk.CTkLabel(
            self, text=path_text,
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            anchor="e",
        )
        path_lbl.pack(side="right", padx=10, pady=8)

        for w in (self, badge, name_lbl, path_lbl):
            w.bind("<Double-Button-1>", lambda _: on_double_click(entry))
            w.bind("<Button-1>", self._flash)

    @staticmethod
    def _short_path(path: str) -> str:
        parts = Path(path).parts
        return os.path.join(*parts[-2:]) if len(parts) >= 2 else path

    def _flash(self, _):
        self.configure(fg_color=COLORS["accent_dim"])
        self.after(150, lambda: self.configure(fg_color=self._bg))


# ══════════════════════════════════════════════
#  Janela principal
# ══════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.engine = IndexEngine()
        self._scanning = False

        self.title("PDF Searcher")
        self.geometry("980x680")
        self.minsize(820, 540)
        self.configure(fg_color=COLORS["bg_primary"])
        self._center()

        self._build_ui()

    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 980, 680
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ══════════════════════════════════════════
    #  UI — tudo com PACK para evitar sobreposição
    # ══════════════════════════════════════════
    def _build_ui(self):
        self._build_header()
        self._build_toolbar()
        self._build_search()
        self._build_results()   # fill + expand
        self._build_statusbar()

    # ── Header ────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"],
                            corner_radius=0, height=58)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="🔍",
                     font=ctk.CTkFont(size=24)
                     ).pack(side="left", padx=(16, 6), pady=10)

        ctk.CTkLabel(hdr, text="PDF Searcher",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=COLORS["text_primary"]
                     ).pack(side="left", pady=10)

        ctk.CTkLabel(hdr,
                     text="Busca inteligente por códigos em documentos",
                     font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_secondary"]
                     ).pack(side="right", padx=20, pady=10)

        # divisória
        ctk.CTkFrame(self, fg_color=COLORS["border"],
                     height=1, corner_radius=0).pack(fill="x", side="top")

    # ── Toolbar ───────────────────────────────
    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"],
                            corner_radius=0, height=54)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Botão selecionar pasta
        self.btn_select = ctk.CTkButton(
            bar,
            text="📂  Selecionar Pasta",
            command=self._select_folder,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            height=34,
            width=190,
        )
        self.btn_select.pack(side="left", padx=(14, 10), pady=10)

        # Divisória vertical
        ctk.CTkFrame(bar, fg_color=COLORS["border"], width=1,
                     corner_radius=0).pack(side="left", fill="y", pady=10, padx=4)

        # Label do caminho
        self.lbl_folder = ctk.CTkLabel(
            bar,
            text="Nenhuma pasta selecionada",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.lbl_folder.pack(side="left", padx=10, fill="x", expand=True)

        # Barra de progresso
        self.progressbar = ctk.CTkProgressBar(
            bar, mode="determinate", height=6, width=160,
            fg_color=COLORS["bg_primary"],
            progress_color=COLORS["accent"],
        )
        self.progressbar.set(0)
        self.progressbar.pack(side="right", padx=(0, 8))

        # Stats
        self.lbl_stats = ctk.CTkLabel(
            bar, text="",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
        )
        self.lbl_stats.pack(side="right", padx=(0, 12))

        # divisória
        ctk.CTkFrame(self, fg_color=COLORS["border"],
                     height=1, corner_radius=0).pack(fill="x", side="top")

    # ── Search bar ────────────────────────────
    def _build_search(self):
        outer = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"],
                              corner_radius=0)
        outer.pack(fill="x", side="top", padx=16, pady=(10, 0))

        card = ctk.CTkFrame(outer, fg_color=COLORS["bg_card"], corner_radius=10)
        card.pack(fill="x")

        ctk.CTkLabel(card, text="🔍",
                     font=ctk.CTkFont(size=16),
                     text_color=COLORS["text_secondary"]
                     ).pack(side="left", padx=(14, 4))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)

        self.entry_search = ctk.CTkEntry(
            card,
            textvariable=self._search_var,
            placeholder_text="Digite um código numérico…",
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=14),
            height=42,
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            card, text="✕", width=30, height=26,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._clear_search,
        ).pack(side="right", padx=(0, 8))

        # contador
        self.lbl_count = ctk.CTkLabel(
            outer, text="",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            anchor="e",
        )
        self.lbl_count.pack(fill="x", pady=(4, 0))

    # ── Área de resultados ────────────────────
    def _build_results(self):
        outer = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"],
                              corner_radius=0)
        outer.pack(fill="both", expand=True, padx=16, pady=(6, 6))

        # Cabeçalho
        thead = ctk.CTkFrame(outer, fg_color=COLORS["bg_secondary"],
                              corner_radius=8)
        thead.pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(thead, text=" Tipo",
                     text_color=COLORS["text_muted"],
                     font=ctk.CTkFont(size=10, weight="bold")
                     ).pack(side="left", padx=8, pady=5)
        ctk.CTkLabel(thead, text="Nome do Arquivo",
                     text_color=COLORS["text_muted"],
                     font=ctk.CTkFont(size=10, weight="bold")
                     ).pack(side="left", padx=8, pady=5)
        ctk.CTkLabel(thead, text="Pasta / Arquivo ZIP",
                     text_color=COLORS["text_muted"],
                     font=ctk.CTkFont(size=10, weight="bold")
                     ).pack(side="right", padx=10, pady=5)

        # Scroll
        self.scroll = ctk.CTkScrollableFrame(
            outer,
            fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
            corner_radius=8,
        )
        self.scroll.pack(fill="both", expand=True)

        self._placeholder("empty")

    # ── Status bar ────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"],
                            corner_radius=0, height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.lbl_status = ctk.CTkLabel(
            bar, text="Pronto",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=10),
            anchor="w",
        )
        self.lbl_status.pack(side="left", padx=12)

        ext_label = TARGET_EXT.upper().lstrip(".")
        ctk.CTkLabel(
            bar, text=f"Modo: {ext_label}  •  PDF Searcher v1.2",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=12)

    # ══════════════════════════════════════════
    #  Lógica
    # ══════════════════════════════════════════
    def _select_folder(self):
        if self._scanning:
            return
        folder = filedialog.askdirectory(title="Selecionar Pasta Principal")
        if not folder:
            return
        display = folder if len(folder) <= 70 else "…" + folder[-67:]
        self.lbl_folder.configure(text=display,
                                   text_color=COLORS["text_primary"])
        self._clear_search()
        self._placeholder("scanning")
        self._start_scan(folder)

    def _start_scan(self, folder: str):
        self._scanning = True