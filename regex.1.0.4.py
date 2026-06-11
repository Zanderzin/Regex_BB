"""
Buscador de Documentos  —  Banco do Brasil  v1.4
=================================================
Interface no tema visual BB (azul escuro + amarelo).

Requisitos:
    pip install customtkinter Pillow

Uso:
    python buscador_documentos.py
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
# Logo BB embutida em base64 (48x48 PNG)
# ──────────────────────────────────────────────
LOGO_BB_B64 = (
    "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"
)

# ──────────────────────────────────────────────
# Configurações
# ──────────────────────────────────────────────
TARGET_EXT    = ".txt"          # <- troque para ".pdf" quando quiser
CACHE_DIR     = Path.home() / ".buscador_bb"
CACHE_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = CACHE_DIR / "configuracoes.json"

# Tema claro para combinar com a identidade BB
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ── Paleta Banco do Brasil ─────────────────────
#   Azul escuro  #003882   Amarelo  #F7C325
#   Azul médio   #005BAA   Cinza claro #F2F4F7
COLORS = {
    # Fundos
    "bg_primary":     "#F2F4F7",   # cinza clarinho (corpo)
    "bg_secondary":   "#003882",   # azul BB (header / toolbar)
    "bg_card":        "#E2E1E1",   # branco (cards)
    "bg_hover":       "#E8EDF5",   # hover suave
    "bg_thead":       "#005BAA",   # azul médio (cabeçalho da tabela)
    "bg_row_alt":     "#F7F9FC",   # linha alternada

    # Acentos
    "accent":         "#F7C325",   # amarelo BB (botão principal)
    "accent_hover":   "#E0AE1A",   # amarelo escuro (hover)
    "accent_text":    "#003882",   # texto sobre amarelo
    "accent_dim":     "#FFF3C4",   # seleção suave

    # Textos
    "text_primary":   "#1A1A2E",   # quase preto
    "text_secondary": "#4A5568",   # cinza médio
    "text_muted":     "#9AA5B4",   # cinza claro
    "text_header":    "#FFFFFF",   # branco (sobre azul)

    # Estados
    "success":        "#2E7D32",
    "warning":        "#E65100",
    "error":          "#C62828",
    "info":           "#005BAA",

    # Bordas / badges
    "border":         "#CBD5E0",
    "zip_badge":      "#E65100",
    "file_badge":     "#005BAA",
    "cache_badge":    "#6B46C1",

    # Barra amarela decorativa
    "bb_stripe":      "#F7C325",
}


# ══════════════════════════════════════════════
#  Helpers de normalização numérica
# ══════════════════════════════════════════════
_STRIP_SEP = re.compile(r"(?<=\d)[.\-_/\\,](?=\d)")
_NUM_RE    = re.compile(r"\d+")


def normalize_number(text: str) -> str:
    return _STRIP_SEP.sub("", text)


def extract_codes(filename: str) -> set[str]:
    stem  = Path(filename).stem
    codes: set[str] = set()
    for m in _NUM_RE.finditer(stem):
        codes.add(m.group())
    for m in _NUM_RE.finditer(normalize_number(stem)):
        codes.add(m.group())
    return codes


# ══════════════════════════════════════════════
#  Cache em disco
# ══════════════════════════════════════════════
class CacheManager:
    @staticmethod
    def _cache_path(root: str) -> Path:
        h = hashlib.md5(root.encode()).hexdigest()[:12]
        return CACHE_DIR / f"indice_{h}.json"

    @staticmethod
    def _folder_signature(root: str) -> str:
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

    def save(self, root: str, index: dict,
             total_files: int, total_codes: int) -> None:
        data = {
            "version":     2,
            "root":        root,
            "signature":   self._folder_signature(root),
            "saved_at":    datetime.now().isoformat(),
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
            self._cache_path(root).write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def load(self, root: str) -> Optional[dict]:
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
            return None
        return data

    @staticmethod
    def save_settings(folder: str) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps({"ultima_pasta": folder}), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def load_settings() -> Optional[str]:
        try:
            d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return d.get("ultima_pasta")
        except (OSError, json.JSONDecodeError):
            return None


# ══════════════════════════════════════════════
#  Modelo de dados
# ══════════════════════════════════════════════
class EntradaIndice:
    __slots__ = ("nome", "caminho", "tipo", "zip_path")

    def __init__(self, nome: str, caminho: str,
                 tipo: str = "TXT", zip_path: Optional[str] = None):
        self.nome     = nome
        self.caminho  = caminho
        self.tipo     = tipo
        self.zip_path = zip_path

    def caminho_completo(self) -> str:
        if self.tipo != "ZIP":
            return os.path.join(self.caminho, self.nome)
        return self.zip_path or ""


# ══════════════════════════════════════════════
#  Motor de indexação  (worker thread)
# ══════════════════════════════════════════════
class MotorIndexacao:
    def __init__(self):
        self.indice: dict[str, list[EntradaIndice]] = defaultdict(list)
        self.total_arquivos = 0
        self.total_codigos  = 0
        self._cache = CacheManager()

    def resetar(self):
        self.indice.clear()
        self.total_arquivos = 0
        self.total_codigos  = 0

    def escanear(self, raiz: str,
                 cb_progresso=None, cb_status=None) -> bool:
        """Retorna True se carregou do cache."""
        if cb_status:
            cb_status("Verificando índice em cache…")
        cached = self._cache.load(raiz)
        if cached:
            self._carregar_cache(cached)
            if cb_status:
                cb_status(
                    f"✓ Índice carregado — "
                    f"{self.total_arquivos} arquivos, "
                    f"{self.total_codigos} códigos"
                )
            if cb_progresso:
                cb_progresso(1, 1)
            return True

        self.resetar()
        if cb_status:
            cb_status("Iniciando varredura de documentos…")

        itens = list(self._percorrer(raiz))
        total = len(itens)

        for idx, (tipo_item, caminho) in enumerate(itens):
            if cb_progresso:
                cb_progresso(idx + 1, total)
            if tipo_item == "arquivo":
                self._indexar_arquivo(caminho)
            elif tipo_item == "zip":
                if cb_status:
                    cb_status(f"Lendo ZIP: {os.path.basename(caminho)}")
                self._indexar_zip(caminho)

        self.total_codigos = len(self.indice)
        self._cache.save(raiz, self.indice,
                         self.total_arquivos, self.total_codigos)
        self._cache.save_settings(raiz)

        if cb_status:
            cb_status(
                f"✓ Varredura concluída — "
                f"{self.total_arquivos} arquivos, "
                f"{self.total_codigos} códigos indexados"
            )
        return False

    def _carregar_cache(self, data: dict) -> None:
        self.resetar()
        for code, entries in data["index"].items():
            for e in entries:
                self.indice[code].append(EntradaIndice(
                    nome=e["nome"], caminho=e["caminho"],
                    tipo=e["tipo"], zip_path=e.get("zip_path"),
                ))
        self.total_arquivos = data["total_files"]
        self.total_codigos  = data["total_codes"]

    def _percorrer(self, raiz: str):
        for dirpath, _dirs, files in os.walk(raiz):
            for fname in files:
                low  = fname.lower()
                full = os.path.join(dirpath, fname)
                if low.endswith(TARGET_EXT):
                    yield ("arquivo", full)
                elif low.endswith(".zip"):
                    yield ("zip", full)

    def _indexar_arquivo(self, caminho: str) -> None:
        nome  = os.path.basename(caminho)
        pasta = os.path.dirname(caminho)
        tipo  = TARGET_EXT.lstrip(".").upper()
        self._adicionar(nome, EntradaIndice(nome=nome, caminho=pasta, tipo=tipo))
        self.total_arquivos += 1

    def _indexar_zip(self, zip_path: str) -> None:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if info.filename.lower().endswith(TARGET_EXT):
                        nome   = os.path.basename(info.filename)
                        pasta  = os.path.dirname(info.filename)
                        entry  = EntradaIndice(
                            nome=nome, caminho=pasta or "/",
                            tipo="ZIP", zip_path=zip_path,
                        )
                        self._adicionar(nome, entry)
                        self.total_arquivos += 1
        except (zipfile.BadZipFile, PermissionError, OSError):
            pass

    def _adicionar(self, filename: str, entry: EntradaIndice) -> None:
        for code in extract_codes(filename):
            self.indice[code].append(entry)

    def buscar(self, consulta: str) -> list[EntradaIndice]:
        q = normalize_number(consulta.strip())
        if not q or not q.isdigit():
            return []
        seen: set[int] = set()
        resultado: list[EntradaIndice] = []
        for chave, entradas in self.indice.items():
            if chave.startswith(q):
                for e in entradas:
                    eid = id(e)
                    if eid not in seen:
                        seen.add(eid)
                        resultado.append(e)
        return resultado

    def invalidar_cache(self, raiz: str) -> None:
        path = CacheManager._cache_path(raiz)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


# ══════════════════════════════════════════════
#  Linha de resultado  (tema BB)
# ══════════════════════════════════════════════
class LinhaResultado(ctk.CTkFrame):
    def __init__(self, master, entrada: EntradaIndice,
                 ao_duplo_clique, ao_abrir_pasta, indice_linha: int):
        bg = COLORS["bg_card"] if indice_linha % 2 == 0 else COLORS["bg_row_alt"]
        super().__init__(master, fg_color=bg, corner_radius=0)
        self._bg = bg

        self.bind("<Enter>", lambda _: self.configure(fg_color=COLORS["bg_hover"]))
        self.bind("<Leave>", lambda _: self.configure(fg_color=self._bg))

        # Badge tipo
        badge_cor = (COLORS["zip_badge"] if entrada.tipo == "ZIP"
                     else COLORS["file_badge"])
        badge = ctk.CTkLabel(
            self, text=f" {entrada.tipo} ",
            fg_color=badge_cor, corner_radius=4,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=38,
        )
        badge.pack(side="left", padx=(10, 6), pady=9)

        # Nome do arquivo
        nome_lbl = ctk.CTkLabel(
            self, text=entrada.nome,
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        nome_lbl.pack(side="left", padx=(0, 8), pady=9,
                      fill="x", expand=True)

        # Botão abrir pasta
        btn_pasta = ctk.CTkButton(
            self, text="📁",
            width=30, height=26,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["info"],
            font=ctk.CTkFont(size=13),
            corner_radius=6,
            command=lambda: ao_abrir_pasta(entrada),
        )
        btn_pasta.pack(side="right", padx=(0, 10))

        # Caminho resumido
        path_text = (f"📦 {os.path.basename(entrada.zip_path or '')}"
                     if entrada.tipo == "ZIP"
                     else self._caminho_curto(entrada.caminho))
        path_lbl = ctk.CTkLabel(
            self, text=path_text,
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            anchor="e",
        )
        path_lbl.pack(side="right", padx=(0, 4))

        for w in (self, badge, nome_lbl, path_lbl):
            w.bind("<Double-Button-1>",
                   lambda _: ao_duplo_clique(entrada))
            w.bind("<Button-1>", self._flash)

    @staticmethod
    def _caminho_curto(path: str) -> str:
        parts = Path(path).parts
        return os.path.join(*parts[-2:]) if len(parts) >= 2 else path

    def _flash(self, _):
        self.configure(fg_color=COLORS["accent_dim"])
        self.after(150, lambda: self.configure(fg_color=self._bg))


# ══════════════════════════════════════════════
#  Logo BB desenhado em Canvas (SVG-like)
# ══════════════════════════════════════════════
def criar_logo_bb(parent, size: int = 48) -> tk.Label:
    """
    Exibe o logo oficial do BB (PNG embutido em base64).
    Retorna um tk.Label com a imagem — sem arquivo externo.
    """
    import base64, io
    from PIL import Image, ImageTk

    data = base64.b64decode(LOGO_BB_B64)
    img  = Image.open(io.BytesIO(data)).convert("RGBA")
    img  = img.resize((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)

    lbl = tk.Label(parent, image=photo,
                   bg=COLORS["bg_secondary"],
                   bd=0, highlightthickness=0)
    lbl.image = photo   # mantém referência — evita GC
    return lbl


# ══════════════════════════════════════════════
#  Janela principal
# ══════════════════════════════════════════════
class Aplicacao(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.motor          = MotorIndexacao()
        self._escaneando    = False
        self._buscando      = False
        self._pasta_atual: Optional[str] = None

        self._fila: queue.Queue = queue.Queue()

        self.title("Buscador de Documentos — Banco do Brasil")
        self.geometry("1020x700")
        self.minsize(860, 560)
        self.configure(fg_color=COLORS["bg_primary"])
        self._centralizar()

        self._construir_interface()

        threading.Thread(target=self._loop_worker, daemon=True).start()
        self.after(250, self._carregar_ultima_pasta)

    def _centralizar(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"1020x700+{(sw-1020)//2}+{(sh-700)//2}")

    # ══════════════════════════════════════════
    #  Worker
    # ══════════════════════════════════════════
    def _loop_worker(self):
        while True:
            tarefa, args = self._fila.get()
            try:
                tarefa(*args)
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror(
                    "Erro interno", str(e)))
            finally:
                self._fila.task_done()

    def _enfileirar(self, tarefa, *args):
        self._fila.put((tarefa, args))

    # ══════════════════════════════════════════
    #  Construção da Interface
    # ══════════════════════════════════════════
    def _construir_interface(self):
        self._construir_header()
        self._construir_barra_amarela()
        self._construir_toolbar()
        self._construir_pesquisa()
        self._construir_resultados()
        self._construir_statusbar()

    # ── Header azul BB ────────────────────────
    def _construir_header(self):
        hdr = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"],
                            corner_radius=0, height=68)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        # Logo BB (canvas)
        logo = criar_logo_bb(hdr, size=42)
        logo.pack(side="left", padx=(18, 10), pady=13)

        # Bloco de texto
        bloco = ctk.CTkFrame(hdr, fg_color="transparent")
        bloco.pack(side="left", pady=10)

        ctk.CTkLabel(bloco,
                     text="Buscador de Documentos",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=COLORS["text_header"]
                     ).pack(anchor="w")

        ctk.CTkLabel(bloco,
                     text="Banco do Brasil  —  Localização de Arquivos",
                     font=ctk.CTkFont(size=10),
                     text_color="#A8C4E8"
                     ).pack(anchor="w")

        # Versão no canto direito
        ctk.CTkLabel(hdr,
                     text="v1.4",
                     font=ctk.CTkFont(size=10),
                     text_color="#5B8DB8"
                     ).pack(side="right", padx=20)

    # ── Faixa decorativa amarela ──────────────
    def _construir_barra_amarela(self):
        ctk.CTkFrame(self, fg_color=COLORS["bb_stripe"],
                     height=4, corner_radius=0).pack(fill="x", side="top")

    # ── Toolbar ───────────────────────────────
    def _construir_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"],
                            corner_radius=0, height=56)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Botão principal (amarelo BB)
        self.btn_selecionar = ctk.CTkButton(
            bar,
            text="📂  Selecionar Pasta",
            command=self._selecionar_pasta,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6, height=36, width=200,
        )
        self.btn_selecionar.pack(side="left", padx=(16, 6), pady=10)

        # Botão re-escanear
        self.btn_reescanear = ctk.CTkButton(
            bar,
            text="🔄  Atualizar",
            command=self._reescanear_pasta,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["info"],
            border_width=1,
            border_color=COLORS["border"],
            font=ctk.CTkFont(size=11),
            corner_radius=6, height=36, width=110,
            state="disabled",
        )
        self.btn_reescanear.pack(side="left", padx=(0, 10))

        # Divisória
        ctk.CTkFrame(bar, fg_color=COLORS["border"], width=1,
                     corner_radius=0).pack(side="left", fill="y",
                                           pady=10, padx=4)

        # Caminho da pasta
        self.lbl_pasta = ctk.CTkLabel(
            bar, text="Nenhuma pasta selecionada",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self.lbl_pasta.pack(side="left", padx=12, fill="x", expand=True)

        # Barra de progresso
        self.progressbar = ctk.CTkProgressBar(
            bar, mode="determinate", height=6, width=160,
            fg_color=COLORS["bg_primary"],
            progress_color=COLORS["accent"],
        )
        self.progressbar.set(0)
        self.progressbar.pack(side="right", padx=(0, 10))

        # Stats
        self.lbl_stats = ctk.CTkLabel(
            bar, text="",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
        )
        self.lbl_stats.pack(side="right", padx=(0, 8))

        # Linha inferior da toolbar
        ctk.CTkFrame(self, fg_color=COLORS["border"],
                     height=1, corner_radius=0).pack(fill="x", side="top")

    # ── Barra de Pesquisa ─────────────────────
    def _construir_pesquisa(self):
        outer = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"],
                              corner_radius=0)
        outer.pack(fill="x", side="top", padx=18, pady=(14, 0))

        # Label acima
        ctk.CTkLabel(outer,
                     text="Pesquisar por Código",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["info"],
                     anchor="w"
                     ).pack(fill="x", pady=(0, 4))

        # Card de entrada
        card = ctk.CTkFrame(outer,
                             fg_color=COLORS["bg_card"],
                             border_width=1,
                             border_color=COLORS["border"],
                             corner_radius=8)
        card.pack(fill="x")

        # Ícone de lupa azul BB
        ctk.CTkLabel(card, text="🔍",
                     font=ctk.CTkFont(size=16),
                     text_color=COLORS["info"]
                     ).pack(side="left", padx=(14, 4))

        self._var_pesquisa = tk.StringVar()

        self.campo_pesquisa = ctk.CTkEntry(
            card,
            textvariable=self._var_pesquisa,
            placeholder_text="Ex: 1234  ou  1.234  ou  1-234  — Enter ou clique em Pesquisar",
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=14),
            height=44,
        )
        self.campo_pesquisa.pack(side="left", fill="x",
                                  expand=True, padx=(0, 4))
        self.campo_pesquisa.bind("<Return>",
                                  lambda _: self._disparar_busca())

        # Botão Pesquisar (amarelo)
        self.btn_pesquisar = ctk.CTkButton(
            card,
            text="🔍  Pesquisar",
            command=self._disparar_busca,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6, height=34, width=130,
        )
        self.btn_pesquisar.pack(side="right", padx=(0, 8))

        # Botão limpar
        ctk.CTkButton(
            card, text="✕", width=32, height=34,
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._limpar_pesquisa,
        ).pack(side="right", padx=(0, 4))

        # Contador
        self.lbl_contagem = ctk.CTkLabel(
            outer, text="",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(size=11), anchor="e",
        )
        self.lbl_contagem.pack(fill="x", pady=(5, 0))

    # ── Área de Resultados ────────────────────
    def _construir_resultados(self):
        outer = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"],
                              corner_radius=0)
        outer.pack(fill="both", expand=True, padx=18, pady=(8, 6))

        # Cabeçalho da tabela (azul médio)
        thead = ctk.CTkFrame(outer, fg_color=COLORS["bg_thead"],
                              corner_radius=6)
        thead.pack(fill="x", pady=(0, 2))

        for texto, lado in [
            ("  Tipo",        "left"),
            ("Nome do Arquivo", "left"),
            ("Localização",   "right"),
        ]:
            ctk.CTkLabel(thead, text=texto,
                         text_color=COLORS["text_header"],
                         font=ctk.CTkFont(size=10, weight="bold")
                         ).pack(side=lado, padx=10, pady=6)

        self.scroll = ctk.CTkScrollableFrame(
            outer,
            fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
            corner_radius=6,
        )
        self.scroll.pack(fill="both", expand=True)
        self._placeholder("vazio")

    # ── Status bar ────────────────────────────
    def _construir_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"],
                            corner_radius=0, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.lbl_status = ctk.CTkLabel(
            bar, text="Pronto",
            text_color="#A8C4E8",
            font=ctk.CTkFont(size=10), anchor="w",
        )
        self.lbl_status.pack(side="left", padx=14)

        self.lbl_badge_cache = ctk.CTkLabel(
            bar, text="",
            text_color=COLORS["bb_stripe"],
            font=ctk.CTkFont(size=10),
        )
        self.lbl_badge_cache.pack(side="left", padx=(4, 0))

        ext_label = TARGET_EXT.upper().lstrip(".")
        ctk.CTkLabel(
            bar,
            text=f"Modo: {ext_label}  •  Banco do Brasil  •  Buscador v1.4",
            text_color="#5B8DB8",
            font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=14)

    # ══════════════════════════════════════════
    #  Carregamento automático
    # ══════════════════════════════════════════
    def _carregar_ultima_pasta(self):
        ultima = CacheManager.load_settings()
        if ultima and os.path.isdir(ultima):
            self._iniciar_scan(ultima)

    # ══════════════════════════════════════════
    #  Scan
    # ══════════════════════════════════════════
    def _selecionar_pasta(self):
        if self._escaneando:
            return
        pasta = filedialog.askdirectory(title="Selecionar Pasta de Documentos")
        if not pasta:
            return
        self._iniciar_scan(pasta)

    def _reescanear_pasta(self):
        if not self._pasta_atual or self._escaneando:
            return
        if messagebox.askyesno(
            "Atualizar Índice",
            "O índice em cache será descartado e a pasta será\n"
            "varrida novamente.\n\nDeseja continuar?",
        ):
            self.motor.invalidar_cache(self._pasta_atual)
            self._iniciar_scan(self._pasta_atual)

    def _iniciar_scan(self, pasta: str):
        self._pasta_atual = pasta
        exib = pasta if len(pasta) <= 72 else "…" + pasta[-69:]
        self.lbl_pasta.configure(text=exib,
                                  text_color=COLORS["text_primary"])
        self._limpar_pesquisa()
        self._placeholder("escaneando")
        self._escaneando = True
        self.btn_selecionar.configure(state="disabled",
                                       text="⏳  Carregando…")
        self.btn_reescanear.configure(state="disabled")
        self.progressbar.set(0)
        self.lbl_stats.configure(text="")
        self.lbl_badge_cache.configure(text="")

        self._enfileirar(self._exec_scan, pasta)

    def _exec_scan(self, pasta: str):
        def cb_prog(atual, total):
            pct = atual / total if total else 0
            self.after(0, lambda p=pct: self.progressbar.set(p))

        def cb_status(msg):
            self.after(0, lambda m=msg: self.lbl_status.configure(text=m))

        do_cache = self.motor.escanear(
            pasta, cb_progresso=cb_prog, cb_status=cb_status)
        CacheManager.save_settings(pasta)
        self.after(0, lambda c=do_cache: self._scan_concluido(c))

    def _scan_concluido(self, do_cache: bool):
        self._escaneando = False
        self.btn_selecionar.configure(state="normal",
                                       text="📂  Selecionar Pasta")
        self.btn_reescanear.configure(state="normal")
        self.progressbar.set(1)
        self.lbl_stats.configure(
            text=(f"📄 {self.motor.total_arquivos} arquivos  "
                  f"🔑 {self.motor.total_codigos} códigos"),
            text_color=COLORS["success"],
        )
        if do_cache:
            self.lbl_badge_cache.configure(
                text="⚡ índice em cache",
                text_color=COLORS["bb_stripe"],
            )
        else:
            self.lbl_badge_cache.configure(
                text="💾 índice salvo",
                text_color=COLORS["success"],
            )
        self._placeholder("pronto")

    # ══════════════════════════════════════════
    #  Pesquisa
    # ══════════════════════════════════════════
    def _disparar_busca(self):
        q = self._var_pesquisa.get().strip()
        if not q:
            estado = "pronto" if self.motor.total_arquivos > 0 else "vazio"
            self._placeholder(estado)
            self.lbl_contagem.configure(text="")
            return

        if not re.fullmatch(r"[\d.\-_,/]+", q):
            self.lbl_contagem.configure(
                text="⚠  Utilize apenas números (separadores . - _ são aceitos)",
                text_color=COLORS["warning"])
            return

        if self._buscando:
            return

        self._buscando = True
        self.btn_pesquisar.configure(state="disabled", text="⏳ Buscando…")
        self.lbl_contagem.configure(text="Pesquisando…",
                                     text_color=COLORS["text_muted"])
        self.lbl_status.configure(text=f"Pesquisando código: {q}")
        self._enfileirar(self._exec_busca, q)

    def _exec_busca(self, consulta: str):
        resultados = self.motor.buscar(consulta)
        self.after(0, lambda r=resultados: self._busca_concluida(r))

    def _busca_concluida(self, resultados: list[EntradaIndice]):
        self._buscando = False
        self.btn_pesquisar.configure(state="normal",
                                      text="🔍  Pesquisar")
        n = len(resultados)
        self.lbl_contagem.configure(
            text=(f"{n} documento{'s' if n != 1 else ''} "
                  f"encontrado{'s' if n != 1 else ''}"),
            text_color=COLORS["success"] if n > 0 else COLORS["text_secondary"],
        )
        self.lbl_status.configure(
            text=f"Pesquisa concluída — {n} resultado(s)")
        self._renderizar(resultados)

    def _limpar_pesquisa(self):
        self._var_pesquisa.set("")
        self.lbl_contagem.configure(text="")
        estado = "pronto" if self.motor.total_arquivos > 0 else "vazio"
        self._placeholder(estado)
        self.campo_pesquisa.focus()

    # ══════════════════════════════════════════
    #  Renderização
    # ══════════════════════════════════════════
    def _limpar_scroll(self):
        for w in self.scroll.winfo_children():
            w.destroy()

    def _placeholder(self, estado: str):
        self._limpar_scroll()
        msgs = {
            "vazio":      ("📂", "Selecione uma Pasta para Começar",
                           "Clique em 'Selecionar Pasta' para indexar os documentos."),
            "escaneando": ("⚙️",  "Carregando Documentos…",
                           "Verificando índice ou realizando varredura na pasta."),
            "pronto":     ("✅",  "Índice Carregado com Sucesso",
                           "Digite um código e clique em Pesquisar ou pressione Enter."),
        }
        icone, titulo, sub = msgs.get(estado, msgs["vazio"])
        f = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f.pack(expand=True, pady=60)

        ctk.CTkLabel(f, text=icone,
                     font=ctk.CTkFont(size=48)).pack()

        ctk.CTkLabel(f, text=titulo,
                     text_color=COLORS["info"],
                     font=ctk.CTkFont(size=15, weight="bold")
                     ).pack(pady=(12, 4))

        ctk.CTkLabel(f, text=sub,
                     text_color=COLORS["text_muted"],
                     font=ctk.CTkFont(size=12)
                     ).pack()

        # Faixa amarela decorativa na parte inferior do placeholder
        ctk.CTkFrame(f, fg_color=COLORS["bb_stripe"],
                     height=3, width=120,
                     corner_radius=2).pack(pady=(14, 0))

    def _renderizar(self, resultados: list[EntradaIndice]):
        self._limpar_scroll()
        if not resultados:
            self._placeholder("vazio")
            return
        for i, entrada in enumerate(resultados):
            LinhaResultado(
                self.scroll, entrada,
                self._abrir_entrada,
                self._abrir_pasta_entrada,
                i,
            ).pack(fill="x", pady=(0, 1))

    # ══════════════════════════════════════════
    #  Abertura de arquivos
    # ══════════════════════════════════════════
    def _abrir_pasta_entrada(self, entrada: EntradaIndice):
        alvo = (entrada.zip_path if entrada.tipo == "ZIP"
                else entrada.caminho_completo())
        self._abrir_no_gerenciador(alvo)

    def _abrir_entrada(self, entrada: EntradaIndice):
        if entrada.tipo == "ZIP":
            self._abrir_no_gerenciador(entrada.zip_path)
            return
        caminho = entrada.caminho_completo()
        if not os.path.isfile(caminho):
            messagebox.showerror(
                "Arquivo Não Encontrado",
                f"O arquivo abaixo não foi localizado no disco:\n\n{caminho}")
            return
        self._abrir_com_so(caminho)

    @staticmethod
    def _abrir_com_so(caminho: str):
        try:
            sistema = platform.system()
            if sistema == "Windows":
                os.startfile(caminho)
            elif sistema == "Darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception as e:
            messagebox.showerror("Erro ao Abrir Arquivo", str(e))

    @staticmethod
    def _abrir_no_gerenciador(caminho_alvo: str):
        if not caminho_alvo or not os.path.exists(caminho_alvo):
            messagebox.showerror(
                "Caminho Não Encontrado",
                f"O caminho abaixo não foi localizado:\n\n{caminho_alvo}")
            return
        try:
            sistema = platform.system()
            if sistema == "Windows":
                win = os.path.normpath(caminho_alvo)
                subprocess.Popen(f'explorer /select,"{win}"', shell=True)
            elif sistema == "Darwin":
                subprocess.Popen(["open", "-R", caminho_alvo])
            else:
                pasta = os.path.dirname(caminho_alvo)
                try:
                    subprocess.Popen(["nautilus", "--select", caminho_alvo])
                except FileNotFoundError:
                    try:
                        subprocess.Popen(["dolphin", "--select", caminho_alvo])
                    except FileNotFoundError:
                        subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            messagebox.showerror("Erro ao Abrir Gerenciador", str(e))


# ══════════════════════════════════════════════
#  Ponto de entrada
# ══════════════════════════════════════════════
if __name__ == "__main__":
    app = Aplicacao()
    app.mainloop()
