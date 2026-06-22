#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel_downloader_gui.py — 小説ePubダウンローダー（GUI 皮）

CLI ツール novel_downloader.py を、コマンドラインを使わない一般ユーザー向けに
包む Windows 向け GUI フロントエンド。設計は gui_v1_design.md を参照。

方針（gui_v1_design.md より）:
  ① エンジンはサブプロセスで起動（本体無改修）
  ② CustomTkinter による単一ウィンドウ
  ③ URL欄＋大ボタンの徹底ミニマル。全オプションは「詳細設定」の奥
  ＋ 起動時クリップボード自動入力 / 出力先固定 / 完了時フォルダ自動オープン /
     やさしい進捗・エラー / 設定の永続化

依存: customtkinter（必須）, Pillow（任意・表紙プレビュー用）
"""

import io
import os
import re
import sys
import json
import queue
import threading
import subprocess
import tempfile
from pathlib import Path

try:
    import customtkinter as ctk
    from tkinter import filedialog
except Exception as e:  # pragma: no cover - 起動環境依存
    sys.stderr.write(
        "customtkinter が必要です: pip install customtkinter\n"
        f"  詳細: {e}\n"
    )
    raise

# ══════════════════════════════════════════
#  定数
# ══════════════════════════════════════════
APP_NAME      = "小説ePubダウンローダー"
APP_DIR_NAME  = "NovelDownloader"          # %APPDATA%\NovelDownloader
ICON_FILENAME = "novel_downloader.ico"
SETTINGS_SCHEMA = 1

IS_WINDOWS = (os.name == "nt")
# 子プロセスに黒いコンソール窓を出さない（Windows のみ）
_CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

# 進捗行: 先頭空白必須（ステージ見出し [1/3] を弾く）／[N/M] を抽出（gui_v1_design §9.2）
_RE_PROGRESS = re.compile(r"^\s+\[\s*(\d+)\s*/\s*(\d+)\s*\]")
# 完了時の epub パス行（gui_v1_design §6 / §9.2）
_RE_EPUB_DONE = re.compile(r"✅\s*ePub出力完了:\s*(.+)$")

ENCODING_CHOICES = ["utf-8", "utf-8-sig", "shift_jis", "cp932"]


# ══════════════════════════════════════════
#  パス解決（gui_v1_design §12.2）
# ══════════════════════════════════════════
def _app_base_dir() -> str:
    """凍結時は exe のあるディレクトリ、開発時はこのスクリプトのディレクトリ。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _resource_path(name: str) -> str:
    """同梱リソース（アイコン等）の絶対パス。onefile は sys._MEIPASS に展開される。"""
    base = getattr(sys, "_MEIPASS", _app_base_dir())
    return os.path.join(base, name)


def engine_cmd(*cli_args) -> list:
    """エンジン（CLI）を起動するコマンド配列を返す。

    凍結時: 隣の novel_downloader.exe を呼ぶ。
    開発時: python で novel_downloader.py を呼ぶ。
    """
    if getattr(sys, "frozen", False):
        exe = os.path.join(_app_base_dir(), "novel_downloader.exe")
        return [exe, *cli_args]
    script = os.path.join(_app_base_dir(), "novel_downloader.py")
    return [sys.executable, script, *cli_args]


def _engine_env() -> dict:
    """エンジン起動用の環境変数。ライブ進捗と UTF-8 出力を保証（§9.3 / §2.3）。"""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"   # ライブ進捗（バッファさせない）
    env["PYTHONUTF8"] = "1"         # 日本語出力を UTF-8 に固定
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def default_output_dir() -> str:
    """既定保存先: ダウンロード\\小説（gui_v1_design §3.1）。"""
    if IS_WINDOWS:
        home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    else:
        home = os.path.expanduser("~")
    return os.path.join(home, "Downloads", "小説")


# ══════════════════════════════════════════
#  設定の永続化（gui_v1_design §13）
# ══════════════════════════════════════════
def settings_path() -> str:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA", _app_base_dir())
        return os.path.join(base, APP_DIR_NAME, "settings.json")
    cfg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(cfg, "novel_downloader_gui", "settings.json")


def default_settings() -> dict:
    return {
        "schema": SETTINGS_SCHEMA,
        "output_dir": default_output_dir(),
        "cover_mode": "auto",          # "auto" | "site" | "file"
        "cover_image_path": "",
        "horizontal": False,
        "kobo": False,
        "toc_at_end": False,
        "font_path": "",
        "delay": 1.5,
        "encoding": "utf-8",
    }


def load_settings() -> dict:
    """壊れていても既定で起動。欠損キーは既定で補完（§13.3）。"""
    s = default_settings()
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("schema") == SETTINGS_SCHEMA:
            for k in s:
                if k in data:
                    s[k] = data[k]
    except Exception:
        pass  # 無い／壊れている → 既定のまま
    # 妥当性
    if not s.get("output_dir"):
        s["output_dir"] = default_output_dir()
    if s.get("cover_mode") == "file" and not (
        s.get("cover_image_path") and os.path.isfile(s["cover_image_path"])
    ):
        s["cover_mode"] = "auto"       # 画像が無ければ auto へフォールバック（§13.3）
    if s.get("font_path") and not os.path.isfile(s["font_path"]):
        s["font_path"] = ""            # フォントファイルが無ければ埋め込みなしへ
    try:
        s["delay"] = float(s.get("delay", 1.5))
    except Exception:
        s["delay"] = 1.5
    if s.get("encoding") not in ENCODING_CHOICES:
        s["encoding"] = "utf-8"
    return s


def save_settings(s: dict) -> None:
    """アトミック書き込み（tempfile + os.replace, §13.3）。"""
    try:
        p = settings_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass  # 保存失敗は致命ではない


# ══════════════════════════════════════════
#  エンジン呼び出し（読み取り専用モード）
# ══════════════════════════════════════════
def _run_capture(cli_args, timeout=30) -> str:
    """エンジンを起動し stdout を文字列で返す（--detect-site / --list-sites 用）。"""
    proc = subprocess.run(
        engine_cmd(*cli_args),
        capture_output=True, env=_engine_env(),
        creationflags=_CREATE_NO_WINDOW, timeout=timeout,
    )
    return proc.stdout.decode("utf-8", "replace")


def detect_site(url: str):
    """--detect-site を呼び結果 dict を返す。失敗時 None。"""
    try:
        out = _run_capture(["--detect-site", url])
        line = [ln for ln in out.splitlines() if ln.strip()][-1]  # JSON は最終行
        return json.loads(line)
    except Exception:
        return None


def list_sites():
    """--list-sites を呼び [{site, display_name}] を返す。失敗時 []。"""
    try:
        out = _run_capture(["--list-sites"])
        line = [ln for ln in out.splitlines() if ln.strip()][-1]
        return json.loads(line)
    except Exception:
        return []


# ══════════════════════════════════════════
#  メインアプリ
# ══════════════════════════════════════════
class NovelDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self._proc = None              # 実行中のダウンロードプロセス
        self._worker = None
        self._abort_event = threading.Event()  # 中止フラグ（事前チェック中の中止にも対応）
        self._queue = queue.Queue()
        self._epub_path = None         # 完了時に開く epub
        self._raw_log = []             # 生ログ（詳細表示用）
        self._detail_open = False
        self._log_open = False

        self.title(APP_NAME)
        self.geometry("560x420")
        self.minsize(520, 360)
        try:
            ico = _resource_path(ICON_FILENAME)
            if IS_WINDOWS and os.path.isfile(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

        ctk.set_appearance_mode("system")
        self._build_widgets()
        self._apply_settings_to_widgets()
        self._set_state_idle()

        # 起動時クリップボード自動入力（別スレッドで判定・§7.2）
        self._start_clipboard_autofill()
        # キュー監視
        self.after(100, self._poll_queue)
        # 終了時に設定保存
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── ウィジェット構築（gui_v1_design §10） ──────────────────
    def _build_widgets(self):
        self.grid_columnconfigure(0, weight=1)

        # URL 欄
        self.lbl_url = ctk.CTkLabel(self, text="小説のURLを貼り付け", anchor="w")
        self.lbl_url.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 2))

        self.var_url = ctk.StringVar()
        self.ent_url = ctk.CTkEntry(self, textvariable=self.var_url,
                                    placeholder_text="ここにURLを貼り付けてください…")
        self.ent_url.grid(row=1, column=0, sticky="ew", padx=20)
        self.var_url.trace_add("write", lambda *_: self._update_download_enabled())

        # 大ボタン（ダウンロード / 中止）
        self.btn_main = ctk.CTkButton(self, text="⬇ ダウンロード", height=44,
                                      font=ctk.CTkFont(size=16, weight="bold"),
                                      command=self._on_main_button)
        self.btn_main.grid(row=2, column=0, padx=20, pady=14)

        # ステータス行（進捗テキスト / 完了 / エラー）
        self.lbl_status = ctk.CTkLabel(self, text="", anchor="w", justify="left")
        self.lbl_status.grid(row=3, column=0, sticky="ew", padx=20)

        # 進捗バー
        self.bar = ctk.CTkProgressBar(self)
        self.bar.grid(row=4, column=0, sticky="ew", padx=20, pady=(4, 2))
        self.bar.set(0)
        self.bar.grid_remove()

        # 補助ボタン行（フォルダを開く / 対応サイト / 詳細を表示）
        self.frm_aux = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_aux.grid(row=5, column=0, sticky="ew", padx=20, pady=2)
        self.frm_aux.grid_remove()   # 空のときは隠す（CTkFrame の既定サイズで居座らせない）
        self.btn_open = ctk.CTkButton(self.frm_aux, text="📂 フォルダを開く",
                                      width=140, command=self._open_folder)
        self.btn_sites = ctk.CTkButton(self.frm_aux, text="対応サイトを見る",
                                       width=140, fg_color="gray40",
                                       command=self._show_sites)
        self.btn_log = ctk.CTkButton(self.frm_aux, text="詳細を表示",
                                     width=110, fg_color="gray30",
                                     command=self._toggle_log)

        # 保存先表示（小）
        self.lbl_outdir = ctk.CTkLabel(self, text="", anchor="w",
                                       text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_outdir.grid(row=6, column=0, sticky="ew", padx=20, pady=(6, 0))

        # 詳細設定トグル
        self.btn_detail = ctk.CTkButton(
            self, text="▸ 詳細設定（保存先・表紙などの変更）", anchor="w",
            fg_color=("gray90", "gray25"), text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray35"), cursor="hand2",
            command=self._toggle_detail)
        self.btn_detail.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 0))

        # 詳細設定パネル（§10.2）
        self._build_detail_panel()

        # 生ログ（§10.1 トグル先）
        self.txt_log = ctk.CTkTextbox(self, height=120)

    def _build_detail_panel(self):
        self.frm_detail = ctk.CTkFrame(self)
        self.frm_detail.grid_columnconfigure(0, weight=1)

        # 保存先
        ctk.CTkLabel(self.frm_detail, text="保存先", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        row = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=12)
        row.grid_columnconfigure(0, weight=1)
        self.var_outdir = ctk.StringVar()
        self.ent_outdir = ctk.CTkEntry(row, textvariable=self.var_outdir)
        self.ent_outdir.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(row, text="変更", width=60,
                      command=self._pick_output_dir).grid(row=0, column=1, padx=(8, 0))

        # 表紙（排他ラジオ・§10.2）
        ctk.CTkLabel(self.frm_detail, text="表紙（ePubの“顔”）", anchor="w").grid(
            row=2, column=0, sticky="ew", padx=12, pady=(12, 0))
        self.var_cover = ctk.StringVar(value="auto")
        for i, (val, label) in enumerate([
            ("auto", "おまかせ（自動で作る）"),
            ("site", "サイトの公式表紙を使う"),
            ("file", "自分の画像を選ぶ…"),
        ]):
            ctk.CTkRadioButton(self.frm_detail, text=label, value=val,
                               variable=self.var_cover,
                               command=self._on_cover_change).grid(
                row=3 + i, column=0, sticky="w", padx=24, pady=1)

        # 画像選択行
        self.frm_cover_file = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        self.frm_cover_file.grid(row=6, column=0, sticky="ew", padx=24)
        self.frm_cover_file.grid_columnconfigure(0, weight=1)
        self.var_cover_file = ctk.StringVar(value="画像が未選択です")
        self.lbl_cover_file = ctk.CTkLabel(self.frm_cover_file,
                                           textvariable=self.var_cover_file,
                                           anchor="w", text_color="gray")
        self.lbl_cover_file.grid(row=0, column=0, sticky="ew")
        self.btn_cover_pick = ctk.CTkButton(self.frm_cover_file, text="画像を選ぶ",
                                            width=90, command=self._pick_cover_image)
        self.btn_cover_pick.grid(row=0, column=1, padx=(8, 0))
        self._cover_image_path = ""

        # 区切り線
        sep = ctk.CTkFrame(self.frm_detail, height=1, fg_color="gray70")
        sep.grid(row=7, column=0, sticky="ew", padx=12, pady=10)
        ctk.CTkLabel(self.frm_detail, text="ここから下は普段は変更不要",
                     text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=8, column=0, sticky="w", padx=12)

        # 下段オプション
        opt = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        opt.grid(row=9, column=0, sticky="ew", padx=12, pady=(2, 12))
        self.var_horizontal = ctk.BooleanVar(value=False)
        self.var_kobo = ctk.BooleanVar(value=False)
        self.var_toc_at_end = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opt, text="横書きにする", variable=self.var_horizontal,
                        command=self._persist).grid(row=0, column=0, sticky="w", pady=2)
        ctk.CTkCheckBox(opt, text="Kobo端末向け (.kepub.epub)", variable=self.var_kobo,
                        command=self._persist).grid(row=0, column=1, sticky="w", padx=(16, 0), pady=2)
        ctk.CTkCheckBox(opt, text="目次を本の最後に置く", variable=self.var_toc_at_end,
                        command=self._persist).grid(row=1, column=0, columnspan=2,
                                                    sticky="w", pady=2)

        # 本文フォント（ePub に埋め込むフォント・見た目に直結）
        ctk.CTkLabel(opt, text="本文のフォント").grid(row=2, column=0, sticky="w", pady=(6, 0))
        fontbox = ctk.CTkFrame(opt, fg_color="transparent")
        fontbox.grid(row=2, column=1, sticky="w", padx=(16, 0), pady=(6, 0))
        self._font_path = ""
        self.var_font_name = ctk.StringVar(value="標準（埋め込みなし）")
        ctk.CTkLabel(fontbox, textvariable=self.var_font_name,
                     text_color="gray").pack(side="left")
        ctk.CTkButton(fontbox, text="選ぶ", width=56,
                      command=self._pick_font).pack(side="left", padx=(8, 0))
        ctk.CTkButton(fontbox, text="標準に戻す", width=84, fg_color="gray40",
                      command=self._clear_font).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(opt, text="取得間隔（秒）").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.var_delay = ctk.StringVar(value="1.5")
        ctk.CTkEntry(opt, textvariable=self.var_delay, width=70).grid(
            row=3, column=1, sticky="w", padx=(16, 0), pady=(6, 0))
        ctk.CTkLabel(opt, text="文字コード").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.var_encoding = ctk.StringVar(value="utf-8")
        ctk.CTkOptionMenu(opt, values=ENCODING_CHOICES, variable=self.var_encoding,
                          width=130, command=lambda *_: self._persist()).grid(
            row=4, column=1, sticky="w", padx=(16, 0), pady=(6, 0))

    # ── 設定 ⇔ ウィジェット ───────────────────────────────────
    def _apply_settings_to_widgets(self):
        s = self.settings
        self.var_outdir.set(s["output_dir"])
        self.var_cover.set(s["cover_mode"])
        self._cover_image_path = s.get("cover_image_path", "")
        if self._cover_image_path:
            self.var_cover_file.set(os.path.basename(self._cover_image_path))
        self.var_horizontal.set(bool(s["horizontal"]))
        self.var_kobo.set(bool(s["kobo"]))
        self.var_toc_at_end.set(bool(s.get("toc_at_end", False)))
        self._font_path = s.get("font_path", "")
        self.var_font_name.set(os.path.basename(self._font_path)
                               if self._font_path else "標準（埋め込みなし）")
        self.var_delay.set(str(s["delay"]))
        self.var_encoding.set(s["encoding"])
        self.lbl_outdir.configure(text=f"保存先： {s['output_dir']}")
        self._on_cover_change()

    def _collect_settings(self) -> dict:
        try:
            delay = float(self.var_delay.get())
        except Exception:
            delay = 1.5
        return {
            "schema": SETTINGS_SCHEMA,
            "output_dir": self.var_outdir.get().strip() or default_output_dir(),
            "cover_mode": self.var_cover.get(),
            "cover_image_path": self._cover_image_path,
            "horizontal": bool(self.var_horizontal.get()),
            "kobo": bool(self.var_kobo.get()),
            "toc_at_end": bool(self.var_toc_at_end.get()),
            "font_path": self._font_path,
            "delay": delay,
            "encoding": self.var_encoding.get(),
        }

    def _persist(self):
        self.settings = self._collect_settings()
        self.lbl_outdir.configure(text=f"保存先： {self.settings['output_dir']}")
        save_settings(self.settings)

    # ── 状態遷移（§4） ───────────────────────────────────────
    def _hide_aux(self):
        for b in (self.btn_open, self.btn_sites, self.btn_log):
            b.grid_forget()
        self.frm_aux.grid_remove()   # 空のフレームが高さを占有しないよう隠す

    def _set_state_idle(self):
        self.btn_main.configure(text="⬇ ダウンロード", state="normal")
        self.lbl_status.configure(text="", text_color=("gray10", "gray90"))
        self.bar.grid_remove()
        self.bar.stop()
        self._hide_aux()
        self.ent_url.configure(state="normal")
        self._update_download_enabled()

    def _set_state_running(self):
        self.btn_main.configure(text="⏸ 中止", state="normal")
        self.ent_url.configure(state="disabled")
        self.lbl_status.configure(text="準備中…", text_color=("gray10", "gray90"))
        self.bar.grid()
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self._hide_aux()

    def _set_state_done(self):
        self.btn_main.configure(text="⬇ ダウンロード", state="normal")
        self.ent_url.configure(state="normal")
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar.set(1)
        name = os.path.basename(self._epub_path) if self._epub_path else "ファイル"
        self.lbl_status.configure(text=f"✅ 完了しました！  「{name}」を保存しました",
                                  text_color=("#1a7f37", "#3fb950"))
        self._hide_aux()
        self.frm_aux.grid()
        self.btn_open.grid(row=0, column=0, padx=(0, 8))

    def _set_state_error(self, kind: str):
        """kind: 'unsupported' | 'hameln' | 'failed'"""
        self.btn_main.configure(text="⬇ もう一度", state="normal")
        self.ent_url.configure(state="normal")
        self.bar.stop()
        self.bar.grid_remove()
        self._hide_aux()
        if kind == "unsupported":
            msg = ("⚠ このサイトには対応していません\n"
                   "URLが正しいか、対応しているサイトかをご確認ください。")
            self.frm_aux.grid()
            self.btn_sites.grid(row=0, column=0, padx=(0, 8))
        elif kind == "hameln":
            msg = ("⚠ ハーメルンには対応していません\n"
                   "申し訳ありませんが、別のサイトのURLでお試しください。")
        else:
            msg = ("⚠ うまくいきませんでした\n"
                   "通信状態を確認して、もう一度お試しください。")
            self.frm_aux.grid()
            self.btn_log.grid(row=0, column=0, padx=(0, 8))
        self.lbl_status.configure(text=msg, text_color=("#b3261e", "#f2b8b5"))

    def _update_download_enabled(self):
        if self._proc is not None:
            return
        has_url = bool(self.var_url.get().strip())
        self.btn_main.configure(state=("normal" if has_url else "disabled"))

    # ── 大ボタン（ダウンロード / 中止） ─────────────────────────
    def _on_main_button(self):
        if self._proc is not None:        # 実行中 → 中止
            self._abort()
            return
        url = self.var_url.get().strip()
        if not url:
            return
        self._persist()
        self._epub_path = None
        self._raw_log = []
        self._abort_event.clear()
        self._set_state_running()
        self._proc = "starting"           # 二重起動防止のプレースホルダ
        self._worker = threading.Thread(target=self._download_worker,
                                        args=(url, self._collect_settings()),
                                        daemon=True)
        self._worker.start()

    def _abort(self):
        self._abort_event.set()           # ワーカーが起動前チェックで参照する
        proc = self._proc
        if hasattr(proc, "terminate"):     # 実プロセス起動済みなら停止（finished で中止判定）
            try:
                proc.terminate()
            except Exception:
                pass

    # ── ダウンロードワーカー（別スレッド・§6） ──────────────────
    def _build_cli_args(self, target_url: str, s: dict) -> list:
        args = [target_url, "--output-dir", s["output_dir"]]
        if s["cover_mode"] == "site":
            args.append("--use-site-cover")
        elif s["cover_mode"] == "file" and s.get("cover_image_path") and \
                os.path.isfile(s["cover_image_path"]):
            args += ["--cover-image", s["cover_image_path"]]
        if s["horizontal"]:
            args.append("--horizontal")
        if s["kobo"]:
            args.append("--kobo")
        if s.get("toc_at_end"):
            args.append("--toc-at-end")
        if s.get("font_path") and os.path.isfile(s["font_path"]):
            args += ["--font", s["font_path"]]
        args += ["--delay", str(s["delay"]), "--encoding", s["encoding"]]
        return args

    def _download_worker(self, url: str, s: dict):
        # 1) 事前チェック（未対応 / ハーメルン）
        info = detect_site(url)
        if not info or info.get("site") is None:
            self._queue.put(("precheck", "unsupported"))
            return
        if info.get("needs_playwright"):
            self._queue.put(("precheck", "hameln"))
            return
        target_url = info.get("normalized_url") or url

        # 事前チェック中に中止されていたらダウンロードを起動しない
        if self._abort_event.is_set():
            self._queue.put(("aborted",))
            return

        # 2) ダウンロード起動
        try:
            proc = subprocess.Popen(
                engine_cmd(*self._build_cli_args(target_url, s)),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=_engine_env(), creationflags=_CREATE_NO_WINDOW,
                bufsize=1, universal_newlines=True, encoding="utf-8", errors="replace",
            )
        except Exception as e:
            self._queue.put(("rawlog", f"[起動失敗] {e}"))
            self._queue.put(("finished", 1))
            return
        self._proc = proc
        # 起動と中止が競合した場合、起動直後でも止める
        if self._abort_event.is_set():
            try:
                proc.terminate()
            except Exception:
                pass

        # 3) stdout を1行ずつ読む（§9）
        for line in proc.stdout:
            line = line.rstrip("\n")
            self._queue.put(("rawlog", line))
            m = _RE_PROGRESS.match(line)
            if m:
                self._queue.put(("progress", int(m.group(1)), int(m.group(2))))
                continue
            md = _RE_EPUB_DONE.search(line)
            if md:
                self._queue.put(("epub", md.group(1).strip()))
        rc = proc.wait()
        self._queue.put(("finished", rc))

    # ── キュー監視（UIスレッド・§6） ──────────────────────────
    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_msg(self, msg):
        kind = msg[0]
        if kind == "autofill":
            if not self.var_url.get().strip():
                self.var_url.set(msg[1])
            return
        if kind == "progress":
            n, m = msg[1], msg[2]
            if self.bar.cget("mode") != "determinate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
            self.bar.set(n / m if m else 0)
            self.lbl_status.configure(text=f"取得中…  第 {n} 話 / 全 {m} 話")
        elif kind == "epub":
            self._epub_path = msg[1]
        elif kind == "rawlog":
            self._raw_log.append(msg[1])
            if self._log_open:
                self.txt_log.insert("end", msg[1] + "\n")
                self.txt_log.see("end")
        elif kind == "precheck":
            self._proc = None
            self._set_state_error(msg[1])
        elif kind == "aborted":
            self._proc = None
            self._set_state_idle()
            self.lbl_status.configure(text="中止しました。")
        elif kind == "finished":
            rc = msg[1]
            self._proc = None
            if self._abort_event.is_set():   # 中止後の終了は「中止」として扱う
                self._set_state_idle()
                self.lbl_status.configure(text="中止しました。")
                return
            if rc == 0:
                self._fallback_epub_path()
                self._set_state_done()
                self._open_folder()          # 完了と同時に自動オープン
            else:
                self._set_state_error("failed")

    def _fallback_epub_path(self):
        """epub パス未捕捉なら出力先の最新 .epub を採用（§6）。"""
        if self._epub_path and os.path.isfile(self._epub_path):
            return
        try:
            d = self.settings["output_dir"]
            epubs = [os.path.join(d, f) for f in os.listdir(d)
                     if f.lower().endswith((".epub", ".kepub.epub"))]
            if epubs:
                self._epub_path = max(epubs, key=os.path.getmtime)
        except Exception:
            pass

    # ── 各種アクション ────────────────────────────────────────
    def _open_folder(self):
        path = self._epub_path
        try:
            if IS_WINDOWS and path and os.path.isfile(path):
                subprocess.run(["explorer", "/select,", os.path.normpath(path)])
            elif IS_WINDOWS:
                os.startfile(self.settings["output_dir"])  # type: ignore[attr-defined]
            else:
                target = os.path.dirname(path) if path else self.settings["output_dir"]
                subprocess.run(["xdg-open", target])
        except Exception:
            pass

    def _show_sites(self):
        sites = list_sites()
        win = ctk.CTkToplevel(self)
        win.title("対応サイト")
        win.geometry("320x420")
        win.transient(self)
        frm = ctk.CTkScrollableFrame(win, label_text="このアプリが対応しているサイト")
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        if not sites:
            ctk.CTkLabel(frm, text="一覧を取得できませんでした。").pack(anchor="w")
        for s in sites:
            ctk.CTkLabel(frm, text="・" + s.get("display_name", ""),
                         anchor="w").pack(fill="x", anchor="w", pady=1)

    def _toggle_detail(self):
        self._detail_open = not self._detail_open
        if self._detail_open:
            self.btn_detail.configure(text="▾ 詳細設定（保存先・表紙などの変更）")
            self.frm_detail.grid(row=8, column=0, sticky="ew", padx=16, pady=(2, 10))
            self.geometry("560x720")
        else:
            self.btn_detail.configure(text="▸ 詳細設定（保存先・表紙などの変更）")
            self.frm_detail.grid_forget()
            self.geometry("560x420")

    def _toggle_log(self):
        self._log_open = not self._log_open
        if self._log_open:
            self.btn_log.configure(text="詳細を隠す")
            self.txt_log.grid(row=9, column=0, sticky="ew", padx=20, pady=(2, 10))
            self.txt_log.delete("1.0", "end")
            self.txt_log.insert("end", "\n".join(self._raw_log) + "\n")
            self.txt_log.see("end")
        else:
            self.btn_log.configure(text="詳細を表示")
            self.txt_log.grid_forget()

    def _on_cover_change(self):
        is_file = (self.var_cover.get() == "file")
        state = "normal" if is_file else "disabled"
        self.btn_cover_pick.configure(state=state)
        self.lbl_cover_file.configure(text_color=("gray10", "gray90") if is_file else "gray")
        self._persist()

    def _pick_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_outdir.get() or default_output_dir())
        if d:
            self.var_outdir.set(d)
            self._persist()

    def _pick_cover_image(self):
        f = filedialog.askopenfilename(
            filetypes=[("画像ファイル", "*.jpg *.jpeg *.png"), ("すべて", "*.*")])
        if f:
            self._cover_image_path = f
            self.var_cover_file.set(os.path.basename(f))
            self._persist()

    def _pick_font(self):
        f = filedialog.askopenfilename(
            filetypes=[("フォントファイル", "*.otf *.ttf *.woff *.woff2"), ("すべて", "*.*")])
        if f:
            self._font_path = f
            self.var_font_name.set(os.path.basename(f))
            self._persist()

    def _clear_font(self):
        self._font_path = ""
        self.var_font_name.set("標準（埋め込みなし）")
        self._persist()

    # ── 起動時クリップボード自動入力（§7.2） ───────────────────
    def _start_clipboard_autofill(self):
        try:
            text = self.clipboard_get()       # clipboard_get は UIスレッドで
        except Exception:
            return
        text = (text or "").strip()
        if not (text.startswith("http://") or text.startswith("https://")):
            return
        threading.Thread(target=self._clipboard_worker, args=(text,),
                         daemon=True).start()

    def _clipboard_worker(self, url: str):
        info = detect_site(url)
        if info and info.get("site") and not info.get("needs_playwright"):
            self._queue.put(("autofill", url))

    # ── 終了 ─────────────────────────────────────────────────
    def _on_close(self):
        self._persist()
        if hasattr(self._proc, "terminate"):
            try:
                self._proc.terminate()
            except Exception:
                pass
        self.destroy()


def main():
    app = NovelDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
