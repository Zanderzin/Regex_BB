"""
PDF / TXT Document Searcher
============================
Aplicação desktop para busca de documentos em pastas locais.
Modo atual: arquivos TXT (altere TARGET_EXT para ".pdf" quando quiser).

Requisitos:
    pip install customtkinter

Uso:
    python pdf_searcher.py
"""

import os
import re
import queue
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
# Modo de busca
# ──────────────────────────────────────────────
TARGET_EXT = ".txt"   # <- altere para ".pdf" quando quiser

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
        self.tipo = tipo
        self.zip_path = zip_path

    def full_path(self) -> str:
        if self.tipo != "ZIP":
            return os.path.join(self.caminho, self.nome)
        return self.zip_path or ""


# ══════════════════════════════════════════════
#  Motor de indexação  (roda em worker thread)
# ══════════════════════════════════════════════
class IndexEngine:
    """
    Toda a lógica pesada (I/O de disco, regex, zip) roda aqui.
    Nunca toca em widgets Tkinter — comunica via callbacks que
    a UI agenda com .after().
    """
    _NUM_RE = re.compile(r"\d+")

    def __init__(self):
        self.index: dict[str, list[IndexEntry]] = defaultdict(list)
        self.total_files = 0
        self.total_codes = 0

    def reset(self):
        self.index.clear()
        self.total_files = 0
        self.total_codes = 0

    # ── Varredura ─────────────────────────────
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
        self._add_to_index(nome, IndexEntry(nome=nome, caminho=pasta, tipo=tipo))
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

    # ── Pesquisa (roda na worker thread) ──────
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
    def __init__(self, master, entry: IndexEntry,
                 on_double_click, on_show_folder, row_index: int):
        bg = COLORS["bg_card"] if row_index % 2 == 0 else COLORS["bg_secondary"]
        super().__init__(master, fg_color=bg, corner_radius=0)
        self._bg = bg

        self.bind("<Enter>", lambda _: self.configure(fg_color=COLORS["bg_hover"]))
        self.bind("<Leave>", lambda _: self.configure(fg_color=self._bg))

        # Badge tipo
        badge_color = COLORS["zip_badge"] if entry.tipo == "ZIP" else COLORS["file_badge"]
        badge = ctk.CTkLabel(
            self, text=f" {entry.tipo} ",
            fg_color=badge_color, corner_radius=4,
            text_color="#ffffff",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=38,
        )
        badge.pack(side="left", padx=(10, 6), pady=8)

        # Nome do arquivo
        name_lbl = ctk.CTkLabel(
            self, text=entry.nome,
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        name_lbl.pack(side="left", padx=(0, 8), pady=8, fill="x", expand=True)

        # Botão abrir pasta no gerenciador
        btn_folder = ctk.CTkButton(
            self, text="📁",
            width=30, height=26,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=13),
            corner_radius=6,
            command=lambda: on_show_folder(entry),
        )
        btn_folder.pack(side="right", padx=(0, 8))

        # Caminho resumido
        path_text = (f"📦 {os.path.basename(entry.zip_path or '')}"
                     if entry.tipo == "ZIP"
                     else self._short_path(entry.caminho))
        path_lbl = ctk.CTkLabel(
            self, text=path_text,
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            anchor="e",
        )
        path_lbl.pack(side="right", padx=(0, 4))

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
    """
    UI roda na thread principal do Tkinter.
    Toda operação pesada (scan, search) é despachada para
    self._worker_thread via self._task_queue.
    Resultados voltam para a UI via self.after() — thread-safe.
    """

    def __init__(self):
        super().__init__()
        self.engine = IndexEngine()
        self._scanning = False
        self._searching = False

        # Fila de tarefas para o worker thread
        self._task_queue: queue.Queue = queue.Queue()

        self.title("PDF Searcher")
        self.geometry("980x680")
        self.minsize(820, 540)
        self.configure(fg_color=COLORS["bg_primary"])
        self._center()

        self._build_ui()

        # Inicia o worker thread persistente
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 980, 680
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ══════════════════════════════════════════
    #  Worker thread persistente
    #  Consome tarefas da fila e executa o backend
    # ══════════════════════════════════════════
    def _worker_loop(self):
        """Roda em background; processa uma tarefa por vez."""
        while True:
            task, args = self._task_queue.get()
            try:
                task(*args)
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror(
                    "Erro interno", str(e)))
            finally:
                self._task_queue.task_done()

    def _enqueue(self, task, *args):
        """Envia uma tarefa para o worker thread."""
        self._task_queue.put((task, args))

    # ══════════════════════════════════════════
    #  Construção da UI (thread principal)
    # ══════════════════════════════════════════
    def _build_ui(self):
        self._build_header()
        self._build_toolbar()
        self._build_search()
        self._build_results()
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

        ctk.CTkFrame(self, fg_color=COLORS["border"],
                     height=1, corner_radius=0).pack(fill="x", side="top")

    # ── Toolbar ───────────────────────────────
    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"],
                            corner_radius=0, height=54)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

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

        ctk.CTkFrame(bar, fg_color=COLORS["border"], width=1,
                     corner_radius=0).pack(side="left", fill="y", pady=10, padx=4)

        self.lbl_folder = ctk.CTkLabel(
            bar,
            text="Nenhuma pasta selecionada",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.lbl_folder.pack(side="left", padx=10, fill="x", expand=True)

        self.progressbar = ctk.CTkProgressBar(
            bar, mode="determinate", height=6, width=160,
            fg_color=COLORS["bg_primary"],
            progress_color=COLORS["accent"],
        )
        self.progressbar.set(0)
        self.progressbar.pack(side="right", padx=(0, 8))

        self.lbl_stats = ctk.CTkLabel(
            bar, text="",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
        )
        self.lbl_stats.pack(side="right", padx=(0, 12))

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

        self.entry_search = ctk.CTkEntry(
            card,
            textvariable=self._search_var,
            placeholder_text="Digite um código numérico e pressione Enter ou clique em Buscar…",
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=14),
            height=42,
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 4))
        # Enter dispara a busca
        self.entry_search.bind("<Return>", lambda _: self._trigger_search())

        # Botão Buscar
        self.btn_search = ctk.CTkButton(
            card,
            text="🔍  Buscar",
            command=self._trigger_search,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            height=32,
            width=110,
        )
        self.btn_search.pack(side="right", padx=(0, 6))

        # Botão limpar
        ctk.CTkButton(
            card, text="✕", width=30, height=32,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._clear_search,
        ).pack(side="right", padx=(0, 4))

        # Contador de resultados
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
            bar, text=f"Modo: {ext_label}  •  PDF Searcher v1.3",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=12)

    # ══════════════════════════════════════════
    #  Seleção de pasta — dispara scan no worker
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
        self._scanning = True
        self.btn_select.configure(state="disabled", text="⏳  Indexando…")
        self.progressbar.set(0)
        self.lbl_stats.configure(text="")

        # Despacha o scan para o worker thread
        self._enqueue(self._do_scan, folder)

    def _do_scan(self, folder: str):
        """Executa no worker thread — sem tocar em widgets."""
        def progress_cb(current, total):
            pct = current / total if total else 0
            self.after(0, lambda p=pct: self.progressbar.set(p))

        def status_cb(msg):
            self.after(0, lambda m=msg: self.lbl_status.configure(text=m))

        self.engine.scan(folder, progress_cb=progress_cb, status_cb=status_cb)
        self.after(0, self._scan_done)

    def _scan_done(self):
        """Chamado de volta na thread principal via .after()."""
        self._scanning = False
        self.btn_select.configure(state="normal", text="📂  Selecionar Pasta")
        self.progressbar.set(1)
        self.lbl_stats.configure(
            text=f"📄 {self.engine.total_files}  🔑 {self.engine.total_codes}",
            text_color=COLORS["success"],
        )
        self._placeholder("ready")

    # ══════════════════════════════════════════
    #  Pesquisa — só dispara no Enter/botão
    # ══════════════════════════════════════════
    def _trigger_search(self):
        """Chamado pelo botão Buscar ou tecla Enter."""
        q = self._search_var.get().strip()

        if not q:
            state = "ready" if self.engine.total_files > 0 else "empty"
            self._placeholder(state)
            self.lbl_count.configure(text="")
            return

        if not q.isdigit():
            self.lbl_count.configure(text="⚠  Digite apenas números",
                                      text_color=COLORS["warning"])
            return

        if self._searching:
            return  # evita buscas paralelas

        # Feedback imediato na UI
        self._searching = True
        self.btn_search.configure(state="disabled", text="⏳ Buscando…")
        self.lbl_count.configure(text="Pesquisando…",
                                  text_color=COLORS["text_muted"])
        self.lbl_status.configure(text=f"Buscando código: {q}")

        # Despacha a busca para o worker thread
        self._enqueue(self._do_search, q)

    def _do_search(self, query: str):
        """Executa no worker thread — faz a busca no índice."""
        results = self.engine.search(query)
        # Devolve os resultados para a thread principal
        self.after(0, lambda r=results: self._search_done(r))

    def _search_done(self, results: list[IndexEntry]):
        """Chamado na thread principal com os resultados prontos."""
        self._searching = False
        self.btn_search.configure(state="normal", text="🔍  Buscar")

        n = len(results)
        self.lbl_count.configure(
            text=f"{n} resultado{'s' if n != 1 else ''} encontrado{'s' if n != 1 else ''}",
            text_color=COLORS["success"] if n > 0 else COLORS["text_secondary"],
        )
        self.lbl_status.configure(text=f"Busca concluída — {n} resultado(s)")
        self._render(results)

    def _clear_search(self):
        self._search_var.set("")
        self.lbl_count.configure(text="")
        state = "ready" if self.engine.total_files > 0 else "empty"
        self._placeholder(state)
        self.entry_search.focus()

    # ══════════════════════════════════════════
    #  Renderização (thread principal)
    # ══════════════════════════════════════════
    def _clear_scroll(self):
        for w in self.scroll.winfo_children():
            w.destroy()

    def _placeholder(self, state: str):
        self._clear_scroll()
        msgs = {
            "empty":    ("📂", "Selecione uma pasta para começar",
                         "Clique em 'Selecionar Pasta' para indexar os documentos."),
            "scanning": ("⚙️",  "Indexando documentos…",
                         "Aguarde enquanto os arquivos são varridos."),
            "ready":    ("✅",  "Indexação concluída",
                         "Digite um código e clique em Buscar ou pressione Enter."),
        }
        icon, title, sub = msgs.get(state, msgs["empty"])
        f = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f.pack(expand=True, pady=60)
        ctk.CTkLabel(f, text=icon, font=ctk.CTkFont(size=44)).pack()
        ctk.CTkLabel(f, text=title,
                     text_color=COLORS["text_primary"],
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(10, 4))
        ctk.CTkLabel(f, text=sub,
                     text_color=COLORS["text_muted"],
                     font=ctk.CTkFont(size=12)).pack()

    def _render(self, results: list[IndexEntry]):
        self._clear_scroll()
        if not results:
            self._placeholder("empty")
            return
        for i, entry in enumerate(results):
            ResultRow(self.scroll, entry, self._open_entry,
                      self._show_folder_for_entry, i).pack(
                fill="x", pady=(0, 1))

    # ══════════════════════════════════════════
    #  Abertura de arquivos
    # ══════════════════════════════════════════
    def _show_folder_for_entry(self, entry: IndexEntry):
        """Abre o gerenciador de arquivos selecionando o arquivo."""
        if entry.tipo == "ZIP":
            self._open_folder_select(entry.zip_path)
        else:
            self._open_folder_select(entry.full_path())

    def _open_entry(self, entry: IndexEntry):
        """Duplo clique — abre o arquivo diretamente."""
        if entry.tipo == "ZIP":
            self._open_folder_select(entry.zip_path)
            return
        path = entry.full_path()
        if not os.path.isfile(path):
            messagebox.showerror("Não encontrado",
                                 f"Arquivo não existe:\n{path}")
            return
        self._open_file_os(path)

    @staticmethod
    def _open_file_os(path: str):
        try:
            sys_name = platform.system()
            if sys_name == "Windows":
                os.startfile(path)
            elif sys_name == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Erro ao abrir", str(e))

    @staticmethod
    def _open_folder_select(target_path: str):
        """
        Abre o gerenciador de arquivos com o arquivo selecionado.
        Funciona para ZIPs e arquivos físicos.
        """
        if not target_path or not os.path.exists(target_path):
            messagebox.showerror("Não encontrado",
                                 f"Caminho não localizado:\n{target_path}")
            return
        try:
            sys_name = platform.system()
            if sys_name == "Windows":
                win_path = os.path.normpath(target_path)
                subprocess.Popen(f'explorer /select,"{win_path}"', shell=True)
            elif sys_name == "Darwin":
                subprocess.Popen(["open", "-R", target_path])
            else:
                pasta = os.path.dirname(target_path)
                try:
                    subprocess.Popen(["nautilus", "--select", target_path])
                except FileNotFoundError:
                    try:
                        subprocess.Popen(["dolphin", "--select", target_path])
                    except FileNotFoundError:
                        subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            messagebox.showerror("Erro ao abrir gerenciador", str(e))


# ══════════════════════════════════════════════
#  Ponto de entrada
# ══════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
