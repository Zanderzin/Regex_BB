"""
PDF / TXT Document Searcher  v1.4
===================================
Novidades:
  - Busca normalizada: digitar "1234" acha "1.234", "1-234", "1_234" etc.
  - Cache em disco (JSON) — índice salvo automaticamente após cada scan.
    Na próxima abertura, se a pasta não mudou, carrega do cache em ~ms.
  - Worker thread persistente para todas as operações pesadas.

Requisitos:
    pip install customtkinter

Uso:
    python pdf_searcher.py
"""

import os
import re
import json
import queue
import hashlib
import zipfile
import threading
import subprocess
import platform
import tkinter as tk
from tkinter import filedialog, messagebox
from collections import defaultdict
from pathlib import Path
from typing import Optional
from datetime import datetime

import customtkinter as ctk

# ──────────────────────────────────────────────
# Configurações
# ──────────────────────────────────────────────
TARGET_EXT  = ".txt"          # <- troque para ".pdf" quando quiser
CACHE_DIR   = Path.home() / ".pdf_searcher"   # ~/.pdf_searcher/
CACHE_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = CACHE_DIR / "settings.json"   # última pasta usada

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
    "cache_badge":   "#6e40c9",
}


# ══════════════════════════════════════════════
#  Helpers de normalização numérica
# ══════════════════════════════════════════════
# Remove qualquer separador entre dígitos: "1.234" → "1234"
_STRIP_SEP = re.compile(r"(?<=\d)[.\-_/\\,](?=\d)")
# Extrai blocos de dígitos após normalizar separadores internos
_NUM_RE    = re.compile(r"\d+")


def normalize_number(text: str) -> str:
    """Remove separadores internos de números: '1.234-5' → '12345'."""
    return _STRIP_SEP.sub("", text)


def extract_codes(filename: str) -> set[str]:
    """
    Extrai todos os códigos numéricos de um nome de arquivo,
    considerando tanto o texto bruto quanto a versão normalizada.

    Exemplos:
        "NF 1.234 pagamento.txt"  → {"1", "234", "1234"}
        "Processo-456.txt"        → {"456"}
        "Nota 1-234-5.txt"        → {"1", "234", "5", "12345"}
    """
    stem = Path(filename).stem
    codes: set[str] = set()

    # 1) Extrai números do nome bruto (preserva cada parte separada)
    for m in _NUM_RE.finditer(stem):
        codes.add(m.group())

    # 2) Normaliza separadores e extrai de novo (captura o número completo)
    normalized = normalize_number(stem)
    for m in _NUM_RE.finditer(normalized):
        codes.add(m.group())

    return codes


# ══════════════════════════════════════════════
#  Cache em disco
# ══════════════════════════════════════════════
class CacheManager:
    """
    Salva e carrega o índice em JSON no diretório ~/.pdf_searcher/.
    O nome do arquivo de cache é um hash do caminho da pasta raiz,
    então cada pasta tem seu próprio cache independente.
    """

    @staticmethod
    def _cache_path(root: str) -> Path:
        h = hashlib.md5(root.encode()).hexdigest()[:12]
        return CACHE_DIR / f"index_{h}.json"

    @staticmethod
    def _folder_signature(root: str) -> str:
        """
        Assinatura rápida da pasta: conta arquivos + soma de mtimes.
        Se a pasta não mudou, a assinatura será idêntica → cache válido.
        """
        total_mtime = 0.0
        total_files = 0
        for dirpath, _, files in os.walk(root):
            for fname in files:
                low = fname.lower()
                if low.endswith(TARGET_EXT) or low.endswith(".zip"):
                    try:
                        total_mtime += os.path.getmtime(
                            os.path.join(dirpath, fname))
                        total_files += 1
                    except OSError:
                        pass
        return f"{total_files}:{total_mtime:.0f}"

    def save(self, root: str, index: dict, total_files: int,
             total_codes: int) -> None:
        """Serializa o índice para JSON."""
        data = {
            "version":    2,
            "root":       root,
            "signature":  self._folder_signature(root),
            "saved_at":   datetime.now().isoformat(),
            "total_files": total_files,
            "total_codes": total_codes,
            "index": {
                code: [
                    {"nome": e.nome, "caminho": e.caminho,
                     "tipo": e.tipo, "zip_path": e.zip_path}
                    for e in entries
                ]
                for code, entries in index.items()
            },
        }
        try:
            path = self._cache_path(root)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass   # falha silenciosa — cache é opcional

    def load(self, root: str) -> Optional[dict]:
        """
        Carrega o cache se existir E a assinatura da pasta bater.
        Retorna None se inválido ou desatualizado.
        """
        path = self._cache_path(root)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if data.get("version") != 2:
            return None
        if data.get("root") != root:
            return None
        if data.get("signature") != self._folder_signature(root):
            return None   # pasta foi modificada → re-escanear

        return data

    @staticmethod
    def save_settings(folder: str) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps({"last_folder": folder}), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def load_settings() -> Optional[str]:
        try:
            d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return d.get("last_folder")
        except (OSError, json.JSONDecodeError):
            return None


# ══════════════════════════════════════════════
#  Modelo de dados
# ══════════════════════════════════════════════
class IndexEntry:
    __slots__ = ("nome", "caminho", "tipo", "zip_path")

    def __init__(self, nome: str, caminho: str,
                 tipo: str = "TXT", zip_path: Optional[str] = None):
        self.nome     = nome
        self.caminho  = caminho
        self.tipo     = tipo
        self.zip_path = zip_path

    def full_path(self) -> str:
        if self.tipo != "ZIP":
            return os.path.join(self.caminho, self.nome)
        return self.zip_path or ""


# ══════════════════════════════════════════════
#  Motor de indexação  (worker thread)
# ══════════════════════════════════════════════
class IndexEngine:
    def __init__(self):
        self.index: dict[str, list[IndexEntry]] = defaultdict(list)
        self.total_files = 0
        self.total_codes = 0
        self._cache = CacheManager()

    def reset(self):
        self.index.clear()
        self.total_files = 0
        self.total_codes = 0

    # ── Scan principal ────────────────────────
    def scan(self, root: str,
             progress_cb=None, status_cb=None) -> bool:
        """
        Retorna True se carregou do cache, False se fez scan completo.
        """
        # 1) Tenta carregar do cache
        if status_cb:
            status_cb("Verificando cache…")
        cached = self._cache.load(root)
        if cached:
            self._load_from_cache(cached)
            if status_cb:
                status_cb(
                    f"✓ Cache carregado — {self.total_files} arquivos, "
                    f"{self.total_codes} códigos"
                )
            if progress_cb:
                progress_cb(1, 1)
            return True

        # 2) Cache inválido → scan completo
        self.reset()
        if status_cb:
            status_cb("Cache não encontrado — iniciando varredura…")

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

        # 3) Salva o cache para a próxima abertura
        if status_cb:
            status_cb("Salvando cache…")
        self._cache.save(root, self.index, self.total_files, self.total_codes)
        self._cache.save_settings(root)

        if status_cb:
            status_cb(
                f"✓ Concluído — {self.total_files} arquivos, "
                f"{self.total_codes} códigos"
            )
        return False

    def _load_from_cache(self, data: dict) -> None:
        """Reconstrói o índice a partir do JSON salvo."""
        self.reset()
        for code, entries in data["index"].items():
            for e in entries:
                self.index[code].append(IndexEntry(
                    nome=e["nome"],
                    caminho=e["caminho"],
                    tipo=e["tipo"],
                    zip_path=e.get("zip_path"),
                ))
        self.total_files = data["total_files"]
        self.total_codes = data["total_codes"]

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
        nome  = os.path.basename(filepath)
        pasta = os.path.dirname(filepath)
        tipo  = TARGET_EXT.lstrip(".").upper()
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
        """
        Indexa todos os códigos numéricos do arquivo,
        incluindo versões normalizadas (sem separadores).
        """
        for code in extract_codes(filename):
            self.index[code].append(entry)

    # ── Pesquisa normalizada ──────────────────
    def search(self, query: str) -> list[IndexEntry]:
        """
        Normaliza a query antes de buscar:
          "1.234" → busca "1234"
          "1-234" → busca "1234"
          "1234"  → busca "1234"
        Usa prefix match para achar "12345" ao digitar "123".
        """
        q = normalize_number(query.strip())
        if not q or not q.isdigit():
            return []

        seen: set[int] = set()
        results: list[IndexEntry] = []
        for key, entries in self.index.items():
            if key.startswith(q):
                for e in entries:
                    eid = id(e)
                    if eid not in seen:
                        seen.add(eid)
                        results.append(e)
        return results

    def invalidate_cache(self, root: str) -> None:
        """Remove o cache da pasta para forçar re-scan."""
        path = CacheManager._cache_path(root)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


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
    def __init__(self):
        super().__init__()
        self.engine       = IndexEngine()
        self._scanning    = False
        self._searching   = False
        self._current_folder: Optional[str] = None

        self._task_queue: queue.Queue = queue.Queue()

        self.title("PDF Searcher")
        self.geometry("980x680")
        self.minsize(820, 540)
        self.configure(fg_color=COLORS["bg_primary"])
        self._center()

        self._build_ui()

        # Worker thread persistente
        threading.Thread(target=self._worker_loop, daemon=True).start()

        # Carrega última pasta usada
        self.after(200, self._auto_load_last_folder)

    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"980x680+{(sw-980)//2}+{(sh-680)//2}")

    # ══════════════════════════════════════════
    #  Worker thread
    # ══════════════════════════════════════════
    def _worker_loop(self):
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
        self._task_queue.put((task, args))

    # ══════════════════════════════════════════
    #  UI
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
                     ).pack(side="left")
        ctk.CTkLabel(hdr,
                     text="Busca inteligente por códigos em documentos",
                     font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_secondary"]
                     ).pack(side="right", padx=20)

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
            corner_radius=8, height=34, width=190,
        )
        self.btn_select.pack(side="left", padx=(14, 6), pady=10)

        # Botão re-escanear (força novo scan mesmo com cache válido)
        self.btn_rescan = ctk.CTkButton(
            bar,
            text="🔄",
            command=self._rescan_folder,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=14),
            corner_radius=8, height=34, width=36,
            state="disabled",
        )
        self.btn_rescan.pack(side="left", padx=(0, 8))

        ctk.CTkFrame(bar, fg_color=COLORS["border"], width=1,
                     corner_radius=0).pack(side="left", fill="y", pady=10, padx=4)

        self.lbl_folder = ctk.CTkLabel(
            bar, text="Nenhuma pasta selecionada",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11), anchor="w",
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
            bar, text="", text_color=COLORS["text_secondary"],
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
            placeholder_text="Ex: 1234  ou  1.234  ou  1-234  — pressione Enter ou clique Buscar",
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=14),
            height=42,
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_search.bind("<Return>", lambda _: self._trigger_search())

        self.btn_search = ctk.CTkButton(
            card,
            text="🔍  Buscar",
            command=self._trigger_search,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8, height=32, width=110,
        )
        self.btn_search.pack(side="right", padx=(0, 6))

        ctk.CTkButton(
            card, text="✕", width=30, height=32,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._clear_search,
        ).pack(side="right", padx=(0, 4))

        self.lbl_count = ctk.CTkLabel(
            outer, text="",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11), anchor="e",
        )
        self.lbl_count.pack(fill="x", pady=(4, 0))

    # ── Resultados ────────────────────────────
    def _build_results(self):
        outer = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"],
                              corner_radius=0)
        outer.pack(fill="both", expand=True, padx=16, pady=(6, 6))

        thead = ctk.CTkFrame(outer, fg_color=COLORS["bg_secondary"],
                              corner_radius=8)
        thead.pack(fill="x", pady=(0, 2))

        for text, side in [(" Tipo", "left"), ("Nome do Arquivo", "left"),
                            ("Pasta / Arquivo ZIP", "right")]:
            ctk.CTkLabel(thead, text=text,
                         text_color=COLORS["text_muted"],
                         font=ctk.CTkFont(size=10, weight="bold")
                         ).pack(side=side, padx=8, pady=5)

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
            font=ctk.CTkFont(size=10), anchor="w",
        )
        self.lbl_status.pack(side="left", padx=12)

        # Badge indicador de cache
        self.lbl_cache_badge = ctk.CTkLabel(
            bar, text="",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=10),
        )
        self.lbl_cache_badge.pack(side="left", padx=(6, 0))

        ext_label = TARGET_EXT.upper().lstrip(".")
        ctk.CTkLabel(
            bar, text=f"Modo: {ext_label}  •  PDF Searcher v1.4",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=12)

    # ══════════════════════════════════════════
    #  Auto-carregamento da última pasta
    # ══════════════════════════════════════════
    def _auto_load_last_folder(self):
        """
        Ao abrir o app, verifica se existe uma pasta salva.
        Se sim, tenta carregar do cache (rápido).
        """
        last = CacheManager.load_settings()
        if last and os.path.isdir(last):
            self._start_scan(last)

    # ══════════════════════════════════════════
    #  Seleção e scan
    # ══════════════════════════════════════════
    def _select_folder(self):
        if self._scanning:
            return
        folder = filedialog.askdirectory(title="Selecionar Pasta Principal")
        if not folder:
            return
        self._start_scan(folder)

    def _rescan_folder(self):
        """Força re-scan ignorando o cache existente."""
        if not self._current_folder or self._scanning:
            return
        if messagebox.askyesno(
            "Re-escanear",
            "Isso irá ignorar o cache e varrer a pasta novamente.\n\nContinuar?",
        ):
            self.engine.invalidate_cache(self._current_folder)
            self._start_scan(self._current_folder)

    def _start_scan(self, folder: str):
        self._current_folder = folder
        display = folder if len(folder) <= 70 else "…" + folder[-67:]
        self.lbl_folder.configure(text=display,
                                   text_color=COLORS["text_primary"])
        self._clear_search()
        self._placeholder("scanning")
        self._scanning = True
        self.btn_select.configure(state="disabled", text="⏳  Carregando…")
        self.btn_rescan.configure(state="disabled")
        self.progressbar.set(0)
        self.lbl_stats.configure(text="")
        self.lbl_cache_badge.configure(text="")

        self._enqueue(self._do_scan, folder)

    def _do_scan(self, folder: str):
        """Worker thread — scan ou carga de cache."""
        def progress_cb(current, total):
            pct = current / total if total else 0
            self.after(0, lambda p=pct: self.progressbar.set(p))

        def status_cb(msg):
            self.after(0, lambda m=msg: self.lbl_status.configure(text=m))

        from_cache = self.engine.scan(
            folder, progress_cb=progress_cb, status_cb=status_cb)

        # Salva as configurações (última pasta)
        CacheManager.save_settings(folder)

        self.after(0, lambda c=from_cache: self._scan_done(c))

    def _scan_done(self, from_cache: bool):
        self._scanning = False
        self.btn_select.configure(state="normal", text="📂  Selecionar Pasta")
        self.btn_rescan.configure(state="normal")
        self.progressbar.set(1)
        self.lbl_stats.configure(
            text=f"📄 {self.engine.total_files}  🔑 {self.engine.total_codes}",
            text_color=COLORS["success"],
        )
        if from_cache:
            self.lbl_cache_badge.configure(
                text="⚡ cache",
                text_color=COLORS["cache_badge"],
            )
        else:
            self.lbl_cache_badge.configure(
                text="💾 salvo",
                text_color=COLORS["success"],
            )
        self._placeholder("ready")

    # ══════════════════════════════════════════
    #  Pesquisa
    # ══════════════════════════════════════════
    def _trigger_search(self):
        q = self._search_var.get().strip()
        if not q:
            state = "ready" if self.engine.total_files > 0 else "empty"
            self._placeholder(state)
            self.lbl_count.configure(text="")
            return

        # Aceita dígitos e separadores válidos
        if not re.fullmatch(r"[\d.\-_,/]+", q):
            self.lbl_count.configure(
                text="⚠  Use apenas números (separadores como . - _ são aceitos)",
                text_color=COLORS["warning"])
            return

        if self._searching:
            return

        self._searching = True
        self.btn_search.configure(state="disabled", text="⏳ Buscando…")
        self.lbl_count.configure(text="Pesquisando…",
                                  text_color=COLORS["text_muted"])
        self.lbl_status.configure(text=f"Buscando: {q}")

        self._enqueue(self._do_search, q)

    def _do_search(self, query: str):
        results = self.engine.search(query)
        self.after(0, lambda r=results: self._search_done(r))

    def _search_done(self, results: list[IndexEntry]):
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
    #  Renderização
    # ══════════════════════════════════════════
    def _clear_scroll(self):
        for w in self.scroll.winfo_children():
            w.destroy()

    def _placeholder(self, state: str):
        self._clear_scroll()
        msgs = {
            "empty":    ("📂", "Selecione uma pasta para começar",
                         "Clique em 'Selecionar Pasta' para indexar os documentos."),
            "scanning": ("⚙️",  "Carregando…",
                         "Verificando cache ou varrendo arquivos."),
            "ready":    ("✅",  "Pronto para pesquisar",
                         "Digite um código e pressione Enter ou clique em Buscar."),
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
        target = entry.zip_path if entry.tipo == "ZIP" else entry.full_path()
        self._open_folder_select(target)

    def _open_entry(self, entry: IndexEntry):
        if entry.tipo == "ZIP":
            self._open_folder_select(entry.zip_path)
            return
        path = entry.full_path()
        if not os.path.isfile(path):
            messagebox.showerror("Não encontrado", f"Arquivo não existe:\n{path}")
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
