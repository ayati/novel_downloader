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
import time
import queue
import threading
import subprocess
import tempfile
from pathlib import Path

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception as e:  # pragma: no cover - 起動環境依存
    sys.stderr.write(
        "customtkinter is required: pip install customtkinter\n"
        "customtkinter が必要です: pip install customtkinter\n"
        f"  {e}\n"
    )
    raise

# ══════════════════════════════════════════
#  定数
# ══════════════════════════════════════════
APP_NAME_JA    = "小説ePubダウンローダー"
APP_NAME_EN    = "Novel EPUB Downloader"
APP_NAME      = APP_NAME_JA
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

# パネル（詳細設定・ログ・一覧）の開閉でウィンドウ高さを**固定値で増減しては
# いけない**。v1 は詳細設定を +300px としていたが、その後パネルに項目を足した
# ため実際には収まらなくなり、開いても中身が全部見えずスクロールもできない
# 状態になっていた（実測: 詳細設定だけで 80px、一覧＋詳細で 162px はみ出す）。
# 内容が必要とする高さ（winfo_reqheight）に合わせる ＝ _fit_window() を使う。
QUEUE_LIST_PX   = 150          # 一覧そのものの高さ（これを超えたらスクロール）
# 詳細設定パネルの見える高さの**絶対下限**と、画面端に残す余白。
# 中身が全部入るならその高さ、画面に収まらないなら詰めてスクロールさせる。
# 下限は「これ以上小さいとパネルとして使えない」値であって、
# **利用できる高さより優先してはいけない**（優先すると画面からはみ出す）
# 「快適な下限」と「絶対最小」の 2 段構え。前者を使える高さより優先すると
# 画面からはみ出すので、入らないときは後者まで詰めて分け合う
DETAIL_MIN_PX   = 120
DETAIL_FLOOR_PX = 60
QUEUE_MIN_PX    = 90           # 一覧も詰められる（詰めた分は中でスクロール）
QUEUE_FLOOR_PX  = 40
FIT_MARGIN_PX   = 24

# ジョブ状態 → 行頭の記号（design_gui_v2 §7.3）
_JOB_ICON = {
    "waiting": "⏳", "checking": "…", "running": "⏬",
    "done": "✅", "error": "⚠", "skipped": "✕", "aborted": "⏹",
}
# URL の取り出し（複数 URL の一括投入・§7.2）
_RE_URL = re.compile(r"""https?://[^\s\u3000"'<>]+""")
MIN_HEIGHT_PX   = 360          # minsize（ユーザーは手でここまで縮められる）
# パネルを閉じたときにここより小さくはしない。内容だけに合わせると 360 まで
# 縮んでしまい、開閉のたびに窓が初期サイズより小さくなって落ち着かない
BASE_HEIGHT_PX  = 420
# ウィンドウ位置・サイズの妥当性チェック（壊れた設定で画面外に飛ばさない）
_RE_GEOMETRY = re.compile(r"^\d{2,5}x\d{2,5}(?:[+-]\d{1,5}[+-]\d{1,5})?$")
# メイン画面のグリッド行。_build_widgets と _toggle_detail / _toggle_log の
# 3 箇所から参照するため定数にする（行を 1 つ挿すたびに追従漏れを起こす）
ROW_URL_LABEL  = 0
ROW_URL        = 1
ROW_SITE       = 2
ROW_MAIN_BTN   = 3
ROW_STATUS     = 4
ROW_BAR        = 5
ROW_QUEUE      = 6
ROW_AUX        = 7
ROW_OUTDIR     = 8
ROW_DETAIL_BTN = 9
ROW_DETAIL     = 10
ROW_LOG        = 11
ROW_GRIP       = 12

# ePub として開いてよい拡張子（_open_epub の実行ゲート）
_EPUB_EXTS = (".epub", ".kepub.epub")

# エラー要約として拾う行の目印（design_gui_v2 §3.3）。
# **絵文字ではない。** エンジンの失敗出力は「エラー:」「[エラー]」で、
# ❌ は novel_downloader.py に 1 箇所も無い（実測）。
_ERR_MARKS  = ("エラー:", "[エラー]", "Error:", "error:")
# 未捕捉例外の最終行（例: urllib.error.HTTPError: HTTP Error 404: Not Found）。
# 「Traceback (most recent call last):」を拾っても情報量がゼロなので、
# 例外そのものの行を採る
_RE_EXC_LINE = re.compile(r"^[\w.]+(?:Error|Exception|Interrupt|Timeout)\b[^:]*:")
# 非致命の警告。致命的なエラーが 1 件も無いときだけ使う。
# エンジンの ⚠ は青空文庫外字注記の警告（全4箇所）で、これを失敗理由として
# 見せるとかえって誤解を招く
_WARN_MARKS = ("[警告]", "⚠")

# User-facing GUI strings. Keys are stable; values are ja / en.
UI = {
    "title": ("小説ePubダウンローダー", "Novel EPUB Downloader"),
    "paste_url": ("小説のURLを貼り付け", "Paste a novel URL"),
    "url_ph": ("ここにURLを貼り付けてください…", "Paste a URL here…"),
    # 大ボタンは CTkFont(size=16, weight="bold")。**太字だと Tk の
    # フォントフォールバックが絵文字フォントに落ちず、⬇(U+2B07) や ⏸(U+23F8) が
    # 豆腐になる**（Windows 実機で確認）。一覧の ⏳ や補助ボタンの 📂 は
    # 通常ウェイトなので描画できている。大ボタンだけ基本フォントにある
    # 矢印(U+2193)・四角(U+25A0)に替える
    "download": ("↓ ダウンロード", "↓ Download"),
    "cancel": ("■ 中止", "■ Cancel"),
    "retry": ("↓ もう一度", "↓ Try again"),
    "open_folder": ("📂 フォルダを開く", "📂 Open folder"),
    "sites": ("対応サイトを見る", "Supported sites"),
    "show_log": ("詳細を表示", "Show details"),
    "hide_log": ("詳細を隠す", "Hide log"),
    "adv_closed": ("▸ 詳細設定（保存先・表紙などの変更）", "▸ Advanced (folder, cover, …)"),
    "adv_open": ("▾ 詳細設定（保存先・表紙などの変更）", "▾ Advanced (folder, cover, …)"),
    "save_prefix": ("保存先： ", "Save to: "),
    "outdir": ("保存先", "Save folder"),
    "change": ("変更", "Browse"),
    "cover": ("表紙（ePubの“顔”）", "Cover (EPUB front)"),
    "cover_auto": ("おまかせ（自動で作る）", "Auto-generate"),
    "cover_site": ("サイトの公式表紙を使う", "Use the site cover"),
    "cover_file": ("自分の画像を選ぶ…", "Choose my own image…"),
    "cover_none": ("画像が未選択です", "No image selected"),
    "pick_image": ("画像を選ぶ", "Choose image"),
    "rarely": ("ここから下は普段は変更不要", "Rarely needed below"),
    "horizontal": ("横書きにする", "Horizontal layout"),
    "kobo": ("Kobo端末向け (.kepub.epub)", "For Kobo (.kepub.epub)"),
    "toc_end": ("目次を本の最後に置く", "Put the table of contents at the end"),
    "body_font": ("本文のフォント", "Body font"),
    "font_default": ("標準（埋め込みなし）", "Default (not embedded)"),
    "pick": ("選ぶ", "Choose"),
    "font_reset": ("標準に戻す", "Reset"),
    "delay": ("取得間隔（秒）", "Request interval (sec)"),
    "encoding": ("文字コード", "Text encoding"),
    "preparing": ("準備中…", "Preparing…"),
    "progress": ("取得中…  第 {n} 話 / 全 {m} 話", "Downloading…  {n} / {m}"),
    "done": ("✅ 完了しました！  「{name}」を保存しました", "✅ Finished. Saved “{name}”"),
    "file_fallback": ("ファイル", "file"),
    "aborted": ("中止しました。", "Cancelled."),
    "err_unsupported": (
        "⚠ このサイトには対応していません\nURLが正しいか、対応しているサイトかをご確認ください。",
        "⚠ This site is not supported\nCheck the URL and the supported-site list.",
    ),
    "err_hameln": (
        "⚠ 取得できませんでした\nこのサイトの取得には playwright の導入が必要です。",
        "⚠ Download failed\nThis site needs playwright to be installed.",
    ),
    "err_failed": (
        "⚠ うまくいきませんでした\n通信状態を確認して、もう一度お試しください。",
        "⚠ The download failed\nCheck the network and try again.",
    ),
    "sites_title": ("対応サイト", "Supported sites"),
    "sites_label": ("このアプリが対応しているサイト", "Sites this app can download"),
    "sites_fail": ("一覧を取得できませんでした。", "Could not load the site list."),
    "ft_image": ("画像ファイル", "Image files"),
    "ft_font": ("フォントファイル", "Font files"),
    "ft_all": ("すべて", "All files"),
    # ── v1.1: 入力まわり（design_gui_v2 §5.8） ──
    "ctx_cut": ("切り取り", "Cut"),
    "ctx_copy": ("コピー", "Copy"),
    "ctx_paste": ("貼り付け", "Paste"),
    "ctx_selectall": ("すべて選択", "Select All"),
    "ctx_clear": ("クリア", "Clear"),
    "tip_paste": ("クリップボードのURLを貼り付け", "Paste the URL from the clipboard"),
    "paste_dl": ("↓ 貼り付けてダウンロード", "↓ Paste & Download"),
    "clip_empty": ("クリップボードにURLがありません", "No URL in the clipboard"),
    "detecting": ("判定中…", "Checking…"),
    "site_ok": ("✓ {name}", "✓ {name}"),
    "site_ng": ("✗ このサイトには対応していません", "✗ This site is not supported"),
    "site_pw": ("⚠ {name}（playwright が必要・時間がかかります）",
                "⚠ {name} (needs playwright; this will be slow)"),
    "stage1": ("作品情報を取得中…", "Fetching work info…"),
    "stage2": ("エピソード一覧を取得中…", "Fetching episode list…"),
    "stage3": ("本文を取得中…", "Downloading episodes…"),
    # ── v1.2: 結果まわり（design_gui_v2 §6） ──
    "open_epub": ("📖 ePubを開く", "📖 Open EPUB"),
    "save_log": ("📄 ログを保存", "📄 Save log"),
    "log_saved": ("ログを保存しました", "Log saved"),
    "eta": ("  （残り約 {min} 分）", "  (about {min} min left)"),
    "auto_paste": ("URLを自動で貼り付ける", "Auto-paste URLs from the clipboard"),
    "open_on_done": ("完了したらフォルダを開く", "Open the folder when finished"),
    "behavior": ("動作", "Behavior"),
    "engine_ver": ("エンジン {ver}", "engine {ver}"),
    "ft_text": ("テキストファイル", "Text files"),
    # ── v1.3: キュー（design_gui_v2 §7.14） ──
    "add": ("＋", "+"),
    "tip_add": ("一覧に追加する（すぐには始めない）", "Add to the list (don't start yet)"),
    "queue_title": ("ダウンロード一覧", "Download list"),
    "queue_count": ("{done} / {total} 件", "{done} / {total}"),
    "queue_clear": ("✕ 消す", "✕ Clear"),
    "queue_dup": ("すでに一覧にあります", "Already in the list"),
    "queue_added": ("{n} 件を一覧に追加しました", "Added {n} to the list"),
    "q_waiting": ("待機中", "Waiting"),
    "q_checking": ("確認中…", "Checking…"),
    "q_running": ("取得中", "Downloading"),
    "q_done": ("完了", "Done"),
    "q_error": ("失敗", "Failed"),
    "q_skipped": ("未対応のサイト", "Unsupported site"),
    "q_aborted": ("中止", "Cancelled"),
    "q_progress": ("第 {n} 話 / 全 {m} 話", "{n} / {m}"),
    "resume": ("↓ 再開", "↓ Resume"),
    "queue_running": ("[{i}/{n}] {label}", "[{i}/{n}] {label}"),
    "queue_summary": ("{total} 件中 {ok} 件完了 / {ng} 件失敗",
                      "{ok} of {total} done / {ng} failed"),
    "queue_all_ok": ("✅ {total} 件すべて完了しました", "✅ All {total} finished"),
    # 3 つ全部出す。ok と rest だけだと、失敗が混ざったとき合計が total に
    # ならず「1 件完了 / 1 件未処理」＝全 3 件、と数が合わなくなる
    "queue_stopped": ("■ 中止しました（完了 {ok} / 失敗 {ng} / 未処理 {rest}）",
                      "■ Stopped (done {ok} / failed {ng} / pending {rest})"),
    "retry_failed": ("↻ 失敗した {n} 件を再試行", "↻ Retry {n} failed"),
    "close_title": ("確認", "Confirm"),
    "confirm_close": ("ダウンロードが {n} 件残っています。終了しますか？",
                      "{n} download(s) still pending. Quit anyway?"),
}


def ui_text(key: str, lang: str, **kwargs) -> str:
    pair = UI[key]
    text = pair[1] if lang == "en" else pair[0]
    return text.format(**kwargs) if kwargs else text


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


def _terminate_tree(proc) -> None:
    """エンジンをプロセスツリーごと止める。

    配布 exe は PyInstaller の onefile（gui_v1_design.md §12.5）。onefile の exe は
    ブートローダの親プロセスで、実処理は展開先で起動される**子プロセス**が行う。
    親だけ terminate しても子は走り続けるため、中止ボタンが効かずダウンロードが
    最後まで進んでしまう。Windows では taskkill /T でツリーごと落とす。
    """
    if proc is None or not hasattr(proc, "poll") or proc.poll() is not None:
        return
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=5,
                           creationflags=_CREATE_NO_WINDOW)
            return
        except Exception:
            pass          # taskkill が無い等は下の terminate/kill にフォールバック
    for stop in ("terminate", "kill"):
        try:
            getattr(proc, stop)()
            if proc.poll() is not None or proc.wait(timeout=3) is not None:
                return
        except Exception:
            pass


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
        "ui_lang": "ja",
        # design_gui_v2 §5.9。キーを足すだけなら SETTINGS_SCHEMA は据え置いてよい
        # （欠損キーは既定で補完されるため）。
        "auto_paste": True,            # クリップボードの URL を自動で入れる（§5.4）
        "open_folder_on_done": True,   # 完了時にフォルダを開く（§6）
        "window_geometry": "",         # ウィンドウ位置・サイズの記憶（§6）
    }


# 読み込んだ設定が「この版より新しい schema」だったことを覚えておく。
# 新しい版が足した設定を古い版が読めないまま上書き保存して消すのを防ぐ（design_gui_v2 §3.1）。
_SETTINGS_FROM_FUTURE = False


def load_settings() -> dict:
    """壊れていても既定で起動。欠損キーは既定で補完（§13.3）。

    schema は **完全一致で見てはいけない**（design_gui_v2 §3.1）。
    v1 は `data.get("schema") == SETTINGS_SCHEMA` だったため、SETTINGS_SCHEMA を
    上げた瞬間に既存ユーザーの settings.json が丸ごと無視され、保存先もフォントも
    無言で初期化される作りになっていた。古い schema は読んで補完し、
    新しい schema は読まずに既定で起動する（そして上書き保存もしない）。
    """
    global _SETTINGS_FROM_FUTURE
    _SETTINGS_FROM_FUTURE = False
    s = default_settings()
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            found = data.get("schema", 0)
            found = found if isinstance(found, int) else 0
            if found <= SETTINGS_SCHEMA:
                for k in s:
                    if k in data:
                        s[k] = data[k]
            else:
                _SETTINGS_FROM_FUTURE = True   # 未来の版の設定 → 触らない
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
    if s.get("ui_lang") not in ("ja", "en"):
        s["ui_lang"] = "ja"
    for k in ("auto_paste", "open_folder_on_done"):
        s[k] = bool(s.get(k, True))
    geo = s.get("window_geometry") or ""
    s["window_geometry"] = geo if _RE_GEOMETRY.match(str(geo)) else ""
    return s


def save_settings(s: dict) -> None:
    """アトミック書き込み（tempfile + os.replace, §13.3）。"""
    if _SETTINGS_FROM_FUTURE:
        return          # 新しい版が書いた設定を、読めていないまま潰さない
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


def engine_version() -> str:
    """エンジンの版を返す（`novel_downloader 2.11.2` → `2.11.2`）。失敗時は ""。

    GUI 側に版数を持たないのは意図的。版数の単一ソースは novel_downloader.py の
    `__version__` であり（CLAUDE.md「リリース手順」）、GUI に2つ目の版数を置くと
    release.sh が更新しないまま食い違う。実際に動いているエンジンの版を名乗らせる。
    """
    try:
        out = _run_capture(["--version"], timeout=20).strip()
        return out.split()[-1] if out else ""
    except Exception:
        return ""


# ══════════════════════════════════════════
#  入力欄の補助部品（design_gui_v2 §5.1 / §5.3）
# ══════════════════════════════════════════
def _menu_colors() -> dict:
    """tkinter.Menu は CustomTkinter の外なので、配色を手で合わせる（§5.1）。"""
    if ctk.get_appearance_mode() == "Dark":
        return dict(bg="#2b2b2b", fg="#dce4ee", activebackground="#1f6aa5",
                    activeforeground="#ffffff", disabledforeground="#6e6e6e",
                    relief="flat", borderwidth=0)
    return dict(bg="#fbfbfb", fg="#1a1a1a", activebackground="#3b8ed0",
                activeforeground="#ffffff", disabledforeground="#a0a0a0",
                relief="flat", borderwidth=0)


def _inner_entry(widget):
    """CTkEntry の中身の tkinter.Entry を返す。

    select_range / selection_present のような Tk 由来の操作は CTkEntry が
    転送するとは限らない（customtkinter の版で差がある）ため、中身を直接触る。
    """
    return getattr(widget, "_entry", widget)


class _Tooltip:
    """CustomTkinter にツールチップが無いので最小実装（アイコンボタンの説明用）。"""

    def __init__(self, widget, text_fn):
        self._widget = widget
        self._text_fn = text_fn      # 言語切替に追従させるため呼び出し時に評価する
        self._win = None
        self._after = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after = self._widget.after(500, self._show)

    def _cancel(self):
        if self._after is not None:
            try:
                self._widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        self._after = None
        if self._win is not None:
            return
        try:
            text = self._text_fn()
            x = self._widget.winfo_rootx()
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
            win = tk.Toplevel(self._widget)
            win.wm_overrideredirect(True)
            win.wm_geometry(f"+{x}+{y}")
            c = _menu_colors()
            tk.Label(win, text=text, bg=c["bg"], fg=c["fg"], padx=8, pady=4,
                     relief="solid", borderwidth=1).pack()
            self._win = win
        except Exception:
            self._win = None        # ツールチップの失敗で操作を止めない

    def _hide(self, _event=None):
        self._cancel()
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


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
        # ── v1.1 追加分 ──
        self._started_at = 0.0         # DL 開始時刻（§3.2 の ePub 取り違え防止）
        self._needs_playwright = False # 今回の対象が playwright 必須サイトか（§3.4）
        self._last_clip = ""           # 直近に見たクリップボード（§5.4 の連打防止）
        self._last_url = ""            # 直前にダウンロードした URL（§5.4 の上書き判定）
        self._detect_after = None      # サイト判定のデバウンス予約（§5.5）
        self._detect_seq = 0           # サイト判定の世代カウンタ（§5.5）
        self._site_info = None         # 直近の --detect-site 結果
        self._site_info_url = ""       # その結果がどの URL のものか
        self._prog_t0 = None           # 残り時間推定の基準時刻（§6）
        self._prog_n0 = 0
        self._engine_ver = ""
        self._base_height = 0          # パネルを開いていないときの高さ（終了時に保存）
        # 各パネルを開く直前の高さ。閉じるときに戻す（手で広げた分を失わない）
        self._h_before_detail = 0
        self._h_before_log = 0
        self._h_before_queue = 0
        self._grip_y = None            # ログ欄グリップのドラッグ開始位置
        self._grip_h = 0
        self._closing = False          # 終了処理中（予約済み after を走らせない）
        self._poll_after = None
        # ── ジョブキュー（design_gui_v2 §7）──
        # v1.3 Step 1 では常に 1 件だが、終端処理を 1 箇所に集約するための土台。
        # §8 の受信箱・本棚の一括処理もこの上に乗せる
        self._jobs = []
        self._job_i = -1               # 実行中ジョブの添字（-1 = 未開始）
        self._queue_settings = None    # キュー開始時に固めた設定（§7.10）

        self.title(APP_NAME)
        self.geometry(self.settings.get("window_geometry") or "560x420")
        self.minsize(520, MIN_HEIGHT_PX)
        try:
            ico = _resource_path(ICON_FILENAME)
            if IS_WINDOWS and os.path.isfile(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

        ctk.set_appearance_mode("system")
        self._build_widgets()
        self._apply_settings_to_widgets()
        self._apply_ui_lang()
        self._set_state_idle()
        self.after(0, self._remember_base_height)

        # サイト判定を直列化する専用スレッド（§7.9）
        self._start_detect_thread()
        # ウィンドウ全体のキー操作（§5.2）
        self.bind("<Escape>", self._on_escape, add="+")
        # ウィンドウがフォーカスを得るたびにクリップボードを見直す（§5.4）
        self.bind("<FocusIn>", self._on_focus_in, add="+")

        # 起動時クリップボード自動入力（別スレッドで判定・§7.2）
        self._maybe_autofill_from_clipboard()
        # エンジンの版を名乗らせる（exe 起動を伴うので別スレッド・§6）
        threading.Thread(target=self._load_engine_version, daemon=True).start()
        # キュー監視
        self._poll_after = self.after(100, self._poll_queue)
        # 終了時に設定保存
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── ウィジェット構築（gui_v1_design §10） ──────────────────
    def _build_widgets(self):
        self.grid_columnconfigure(0, weight=1)

        # URL 欄（row0: 見出し＋言語切替 / row1: 入力＋貼り付け / row2: 判定バッジ）
        self.lbl_url = ctk.CTkLabel(self, text="小説のURLを貼り付け", anchor="w")
        self.lbl_url.grid(row=ROW_URL_LABEL, column=0, sticky="ew", padx=20, pady=(18, 2))

        self.frm_url = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_url.grid(row=ROW_URL, column=0, sticky="ew", padx=20)
        self.frm_url.grid_columnconfigure(0, weight=1)

        self.var_url = ctk.StringVar()
        self.ent_url = ctk.CTkEntry(self.frm_url, textvariable=self.var_url,
                                    placeholder_text="ここにURLを貼り付けてください…")
        self.ent_url.grid(row=0, column=0, sticky="ew")
        self.var_url.trace_add("write", lambda *_: self._on_url_changed())

        # 貼り付けボタン（§5.3）。アイコンのみだと用途が伝わらないのでツールチップを付ける
        self.btn_paste = ctk.CTkButton(self.frm_url, text="📋", width=38,
                                       command=self._paste_url)
        self.btn_paste.grid(row=0, column=1, padx=(6, 0))
        _Tooltip(self.btn_paste, lambda: self._t("tip_paste"))

        # 一覧に積むだけのボタン（§7.3）。実行中は大ボタンが「中止」になるので、
        # 追加手段はこれしかない
        self.btn_add = ctk.CTkButton(self.frm_url, text="＋", width=38,
                                     fg_color="gray40", command=self._add_from_entry)
        self.btn_add.grid(row=0, column=2, padx=(4, 0))
        _Tooltip(self.btn_add, lambda: self._t("tip_add"))

        # 右クリックメニュー・キー操作（§5.1 / §5.2）
        self._attach_context_menu(self.ent_url)
        self.ent_url.bind("<Return>", self._on_return, add="+")
        # 貼り付け直後にもサイト判定を走らせる（Tk が貼り終わるのを待つため after 越し）
        self.ent_url.bind("<<Paste>>", lambda e: self.after(20, self._request_detect),
                          add="+")

        self.seg_lang = ctk.CTkSegmentedButton(
            self, values=["日本語", "English"],
            command=self._on_ui_lang)
        self.seg_lang.grid(row=ROW_URL_LABEL, column=0, sticky="e", padx=20, pady=(18, 2))
        self.seg_lang.set("English" if self.settings.get("ui_lang") == "en" else "日本語")

        # サイト判定バッジ（§5.5）
        self.lbl_site = ctk.CTkLabel(self, text="", anchor="w",
                                     font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_site.grid(row=ROW_SITE, column=0, sticky="ew", padx=22, pady=(3, 0))

        # 大ボタン（ダウンロード / 中止）
        self.btn_main = ctk.CTkButton(self, text="⬇ ダウンロード", height=44,
                                      font=ctk.CTkFont(size=16, weight="bold"),
                                      command=self._on_main_button)
        self.btn_main.grid(row=ROW_MAIN_BTN, column=0, padx=20, pady=12)

        # ステータス行（進捗テキスト / 完了 / エラー）
        # wraplength: エラー要約（§3.3）を添えると長くなるので折り返させる
        self.lbl_status = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                       wraplength=500)
        self.lbl_status.grid(row=ROW_STATUS, column=0, sticky="ew", padx=20)

        # 進捗バー
        self.bar = ctk.CTkProgressBar(self)
        self.bar.grid(row=ROW_BAR, column=0, sticky="ew", padx=20, pady=(4, 2))
        self.bar.set(0)
        self.bar.grid_remove()

        # キュー一覧（§7.3）。2 件以上、または待機中があるときだけ出す
        self.frm_queue = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_queue.grid_columnconfigure(0, weight=1)
        qhead = ctk.CTkFrame(self.frm_queue, fg_color="transparent")
        qhead.grid(row=0, column=0, sticky="ew")
        qhead.grid_columnconfigure(1, weight=1)
        self.lbl_queue_title = ctk.CTkLabel(qhead, text="ダウンロード一覧", anchor="w",
                                            font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_queue_title.grid(row=0, column=0, sticky="w")
        self.lbl_queue_count = ctk.CTkLabel(qhead, text="", anchor="w",
                                            text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_queue_count.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.btn_queue_clear = ctk.CTkButton(qhead, text="✕ 消す", width=72, height=24,
                                             fg_color="gray40",
                                             command=self._clear_queue)
        self.btn_queue_clear.grid(row=0, column=2, sticky="e")
        self.frm_queue_list = ctk.CTkScrollableFrame(self.frm_queue, height=QUEUE_LIST_PX)
        self.frm_queue_list.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.frm_queue_list.grid_columnconfigure(1, weight=1)
        self._queue_rows = []          # 行ウィジェット（ジョブと同じ並び）
        self._queue_shown = False
        self._queue_staged = False     # ＋ / まとめ貼り付けで積んだバッチか

        # 補助ボタン行（ePubを開く / フォルダを開く / 対応サイト / 詳細 / ログ保存）
        self.frm_aux = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_aux.grid(row=ROW_AUX, column=0, sticky="ew", padx=20, pady=2)
        self.frm_aux.grid_remove()   # 空のときは隠す（CTkFrame の既定サイズで居座らせない）
        self.btn_open_epub = ctk.CTkButton(self.frm_aux, text="📖 ePubを開く",
                                           width=118, command=self._open_epub)
        self.btn_open = ctk.CTkButton(self.frm_aux, text="📂 フォルダを開く",
                                      width=130, fg_color="gray40",
                                      command=self._open_folder)
        self.btn_sites = ctk.CTkButton(self.frm_aux, text="対応サイトを見る",
                                       width=140, fg_color="gray40",
                                       command=self._show_sites)
        self.btn_log = ctk.CTkButton(self.frm_aux, text="詳細を表示",
                                     width=100, fg_color="gray30",
                                     command=self._toggle_log)
        self.btn_savelog = ctk.CTkButton(self.frm_aux, text="📄 ログを保存",
                                         width=110, fg_color="gray30",
                                         command=self._save_log)
        self.btn_retry = ctk.CTkButton(self.frm_aux, text="", width=150,
                                       command=self._retry_failed)

        # 保存先表示（小）＋ エンジン版数（右端）
        self.lbl_outdir = ctk.CTkLabel(self, text="", anchor="w",
                                       text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_outdir.grid(row=ROW_OUTDIR, column=0, sticky="ew", padx=20, pady=(6, 0))
        self.lbl_ver = ctk.CTkLabel(self, text="", anchor="e",
                                    text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_ver.grid(row=ROW_OUTDIR, column=0, sticky="e", padx=20, pady=(6, 0))

        # 詳細設定トグル
        self.btn_detail = ctk.CTkButton(
            self, text="▸ 詳細設定（保存先・表紙などの変更）", anchor="w",
            fg_color=("gray90", "gray25"), text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray35"), cursor="hand2",
            command=self._toggle_detail)
        self.btn_detail.grid(row=ROW_DETAIL_BTN, column=0, sticky="ew", padx=16, pady=(4, 0))

        # 詳細設定パネル（§10.2）
        self._build_detail_panel()

        # 生ログ（§10.1 トグル先）と、その高さを変えるグリップ
        # 既定の高さ。内容フィット方式では**この値がそのままログの見える量**に
        # なる（120 だと初期ウィンドウの余白に収まってしまい、開いても
        # 窓が広がらず以前より狭くなる）。足りなければ下端のグリップで伸ばせる
        self.txt_log = ctk.CTkTextbox(self, height=180)
        self.grip_log = ctk.CTkFrame(self, height=8, corner_radius=4,
                                     fg_color=("gray78", "gray32"),
                                     cursor="sb_v_double_arrow")
        self.grip_log.bind("<Button-1>", self._grip_press)
        self.grip_log.bind("<B1-Motion>", self._grip_drag)
        self.grip_log.bind("<ButtonRelease-1>", self._grip_release)

    def _lang(self) -> str:
        return "en" if self.settings.get("ui_lang") == "en" else "ja"

    def _t(self, key: str, **kwargs) -> str:
        return ui_text(key, self._lang(), **kwargs)

    def _build_detail_panel(self):
        # **スクロール可能にする。** 固定フレームだと、画面の高さが足りないときに
        # 下の項目（横書き・Kobo・フォント・取得間隔・文字コード）へ到達できない。
        # 内容フィット（§6.1b）でウィンドウは広がるが、画面の高さが上限なので
        # そこで頭打ちになり、はみ出した分は見る手段が無くなる。
        self.frm_detail = ctk.CTkScrollableFrame(self, height=DETAIL_MIN_PX)
        self.frm_detail.grid_columnconfigure(0, weight=1)

        self.lbl_save = ctk.CTkLabel(self.frm_detail, text="保存先", anchor="w")
        self.lbl_save.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        row = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=12)
        row.grid_columnconfigure(0, weight=1)
        self.var_outdir = ctk.StringVar()
        self.ent_outdir = ctk.CTkEntry(row, textvariable=self.var_outdir)
        self.ent_outdir.grid(row=0, column=0, sticky="ew")
        self.btn_outdir = ctk.CTkButton(row, text="変更", width=60,
                                        command=self._pick_output_dir)
        self.btn_outdir.grid(row=0, column=1, padx=(8, 0))
        self._attach_context_menu(self.ent_outdir)

        self.lbl_cover = ctk.CTkLabel(self.frm_detail, text="表紙（ePubの“顔”）", anchor="w")
        self.lbl_cover.grid(row=2, column=0, sticky="ew", padx=12, pady=(12, 0))
        self.var_cover = ctk.StringVar(value="auto")
        self.rad_cover_auto = ctk.CTkRadioButton(
            self.frm_detail, text="おまかせ（自動で作る）", value="auto",
            variable=self.var_cover, command=self._on_cover_change)
        self.rad_cover_site = ctk.CTkRadioButton(
            self.frm_detail, text="サイトの公式表紙を使う", value="site",
            variable=self.var_cover, command=self._on_cover_change)
        self.rad_cover_file = ctk.CTkRadioButton(
            self.frm_detail, text="自分の画像を選ぶ…", value="file",
            variable=self.var_cover, command=self._on_cover_change)
        self.rad_cover_auto.grid(row=3, column=0, sticky="w", padx=24, pady=1)
        self.rad_cover_site.grid(row=4, column=0, sticky="w", padx=24, pady=1)
        self.rad_cover_file.grid(row=5, column=0, sticky="w", padx=24, pady=1)

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

        # 動作（§5.9 / §6）。よく触る設定なので「普段は変更不要」の区切りより上に置く
        self.lbl_behavior = ctk.CTkLabel(self.frm_detail, text="動作", anchor="w")
        self.lbl_behavior.grid(row=7, column=0, sticky="ew", padx=12, pady=(12, 0))
        beh = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        beh.grid(row=8, column=0, sticky="ew", padx=24)
        self.var_auto_paste = ctk.BooleanVar(value=True)
        self.var_open_on_done = ctk.BooleanVar(value=True)
        self.chk_auto_paste = ctk.CTkCheckBox(beh, text="URLを自動で貼り付ける",
                                              variable=self.var_auto_paste,
                                              command=self._persist)
        self.chk_open_on_done = ctk.CTkCheckBox(beh, text="完了したらフォルダを開く",
                                                variable=self.var_open_on_done,
                                                command=self._persist)
        self.chk_auto_paste.grid(row=0, column=0, sticky="w", pady=1)
        self.chk_open_on_done.grid(row=1, column=0, sticky="w", pady=1)

        sep = ctk.CTkFrame(self.frm_detail, height=1, fg_color="gray70")
        sep.grid(row=9, column=0, sticky="ew", padx=12, pady=10)
        self.lbl_rarely = ctk.CTkLabel(self.frm_detail, text="ここから下は普段は変更不要",
                                       text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_rarely.grid(row=10, column=0, sticky="w", padx=12)

        opt = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        opt.grid(row=11, column=0, sticky="ew", padx=12, pady=(2, 12))
        self.var_horizontal = ctk.BooleanVar(value=False)
        self.var_kobo = ctk.BooleanVar(value=False)
        self.var_toc_at_end = ctk.BooleanVar(value=False)
        self.chk_horizontal = ctk.CTkCheckBox(opt, text="横書きにする",
                                              variable=self.var_horizontal,
                                              command=self._persist)
        self.chk_kobo = ctk.CTkCheckBox(opt, text="Kobo端末向け (.kepub.epub)",
                                        variable=self.var_kobo, command=self._persist)
        self.chk_toc = ctk.CTkCheckBox(opt, text="目次を本の最後に置く",
                                      variable=self.var_toc_at_end, command=self._persist)
        self.chk_horizontal.grid(row=0, column=0, sticky="w", pady=2)
        self.chk_kobo.grid(row=0, column=1, sticky="w", padx=(16, 0), pady=2)
        self.chk_toc.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)

        self.lbl_font = ctk.CTkLabel(opt, text="本文のフォント")
        self.lbl_font.grid(row=2, column=0, sticky="w", pady=(6, 0))
        fontbox = ctk.CTkFrame(opt, fg_color="transparent")
        fontbox.grid(row=2, column=1, sticky="w", padx=(16, 0), pady=(6, 0))
        self._font_path = ""
        self.var_font_name = ctk.StringVar(value="標準（埋め込みなし）")
        ctk.CTkLabel(fontbox, textvariable=self.var_font_name,
                     text_color="gray").pack(side="left")
        self.btn_font_pick = ctk.CTkButton(fontbox, text="選ぶ", width=56,
                                           command=self._pick_font)
        self.btn_font_pick.pack(side="left", padx=(8, 0))
        self.btn_font_clear = ctk.CTkButton(fontbox, text="標準に戻す", width=84,
                                            fg_color="gray40", command=self._clear_font)
        self.btn_font_clear.pack(side="left", padx=(6, 0))

        self.lbl_delay = ctk.CTkLabel(opt, text="取得間隔（秒）")
        self.lbl_delay.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.var_delay = ctk.StringVar(value="1.5")
        ctk.CTkEntry(opt, textvariable=self.var_delay, width=70).grid(
            row=3, column=1, sticky="w", padx=(16, 0), pady=(6, 0))
        self.lbl_encoding = ctk.CTkLabel(opt, text="文字コード")
        self.lbl_encoding.grid(row=4, column=0, sticky="w", pady=(6, 0))
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
        if self._font_path:
            self.var_font_name.set(os.path.basename(self._font_path))
        else:
            self.var_font_name.set(self._t("font_default"))
        self.var_auto_paste.set(bool(s.get("auto_paste", True)))
        self.var_open_on_done.set(bool(s.get("open_folder_on_done", True)))
        self.var_delay.set(str(s["delay"]))
        self.var_encoding.set(s["encoding"])
        self.lbl_outdir.configure(text=self._t("save_prefix") + s["output_dir"])
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
            "ui_lang": self.settings.get("ui_lang", "ja"),
            "auto_paste": bool(self.var_auto_paste.get()),
            "open_folder_on_done": bool(self.var_open_on_done.get()),
            "window_geometry": self.settings.get("window_geometry", ""),
        }

    def _persist(self):
        self.settings = self._collect_settings()
        self.lbl_outdir.configure(text=self._t("save_prefix") + self.settings["output_dir"])
        save_settings(self.settings)

    # ── 状態遷移（§4） ───────────────────────────────────────
    _AUX_BUTTONS = ("btn_retry", "btn_open_epub", "btn_open", "btn_sites",
                    "btn_log", "btn_savelog")

    def _hide_aux(self):
        for name in self._AUX_BUTTONS:
            getattr(self, name).grid_forget()
        self.frm_aux.grid_remove()   # 空のフレームが高さを占有しないよう隠す

    def _show_aux(self, *buttons):
        """補助ボタン行に渡されたボタンだけを左から並べる。"""
        self._hide_aux()
        self.frm_aux.grid()
        for i, b in enumerate(buttons):
            b.grid(row=0, column=i, padx=(0, 8))

    def _set_url_entry_enabled(self, enabled: bool):
        """実行中は readonly にする（disabled だと選択もコピーもできない・§5.6）。"""
        try:
            self.ent_url.configure(state="normal" if enabled else "readonly")
        except Exception:
            self.ent_url.configure(state="normal" if enabled else "disabled")
        self.btn_paste.configure(state="normal" if enabled else "disabled")

    def _set_state_idle(self):
        self.btn_main.configure(text=self._t("download"), state="normal")
        self.lbl_status.configure(text="", text_color=("gray10", "gray90"))
        self.bar.grid_remove()
        self.bar.stop()
        self._hide_aux()
        self._set_url_entry_enabled(True)
        self._update_download_enabled()

    def _set_state_running(self):
        self.btn_main.configure(text=self._t("cancel"), state="normal")
        self._set_url_entry_enabled(False)
        self.lbl_status.configure(text=self._t("preparing"), text_color=("gray10", "gray90"))
        self.bar.grid()
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self._hide_aux()

    def _set_state_done(self):
        self.btn_main.configure(text=self._t("download"), state="normal")
        self._set_url_entry_enabled(True)
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar.set(1)
        has_epub = bool(self._epub_path and os.path.isfile(self._epub_path))
        name = os.path.basename(self._epub_path) if has_epub else self._t("file_fallback")
        self.lbl_status.configure(text=self._t("done", name=name),
                                  text_color=("#1a7f37", "#3fb950"))
        aux = [self.btn_open_epub] if has_epub else []
        aux += [self.btn_open, self.btn_log, self.btn_savelog]
        self._show_aux(*aux)

    @staticmethod
    def _clip_line(text: str) -> str:
        return text if len(text) <= 160 else text[:157] + "…"

    def _error_detail(self) -> str:
        """生ログから失敗理由の行を拾う（design_gui_v2 §3.3）。

        v1 はどんな失敗も「うまくいきませんでした」の 1 文に潰していたため、
        通信断・作品削除・サイト構造変化の区別が画面から一切つかなかった。

        致命的なエラー行 → 未捕捉例外の行 → 警告行、の順に探す。
        警告を先に拾うと、外字注記の ⚠ を失敗理由として見せてしまう。
        """
        tail = [ln.strip() for ln in self._raw_log[-300:] if ln.strip()]
        for line in reversed(tail):
            if line.startswith(_ERR_MARKS) or _RE_EXC_LINE.match(line):
                return self._clip_line(line)
        for line in reversed(tail):
            if line.startswith(_WARN_MARKS):
                return self._clip_line(line)
        return ""

    def _set_state_error(self, kind: str):
        """kind: 'unsupported' | 'hameln' | 'failed'"""
        self.btn_main.configure(text=self._t("retry"), state="normal")
        self._set_url_entry_enabled(True)
        self.bar.stop()
        self.bar.grid_remove()
        self._hide_aux()
        if kind == "unsupported":
            msg = self._t("err_unsupported")
            self._show_aux(self.btn_sites)
        else:
            msg = self._t("err_hameln") if kind == "hameln" else self._t("err_failed")
            detail = self._error_detail()
            if detail:
                msg += "\n" + detail
            self._show_aux(self.btn_log, self.btn_savelog)
        self.lbl_status.configure(text=msg, text_color=("#b3261e", "#f2b8b5"))

    def _update_download_enabled(self):
        """大ボタンの活殺と文言を決める（§5.3 / §5.5）。

        URL が空でもクリップボードに URL があれば「貼り付けてダウンロード」に化ける。
        未対応と判定済みのサイトは押せないようにする（exe を起動する前に止める）。
        """
        if self._proc is not None:
            return
        # 一覧に待機中があれば、入力欄が空でも流せる（§7.3）
        if any(j["status"] == "waiting" for j in self._jobs):
            finished = any(j["status"] in ("done", "error", "skipped", "aborted")
                           for j in self._jobs)
            self.btn_main.configure(
                text=self._t("resume") if finished else self._t("download"),
                state="normal")
            return
        url = self.var_url.get().strip()
        if not url:
            if self._clipboard_url():
                self.btn_main.configure(text=self._t("paste_dl"), state="normal")
            else:
                self.btn_main.configure(text=self._t("download"), state="disabled")
            return
        unsupported = (self._site_info is not None
                       and self._site_info_url == url
                       and self._site_info.get("site") is None)
        self.btn_main.configure(text=self._t("download"),
                                state=("disabled" if unsupported else "normal"))

    # ── 大ボタン（ダウンロード / 中止） ─────────────────────────
    def _on_main_button(self):
        if self._proc is not None:        # 実行中 → 中止
            self._abort()
            return
        text = self.var_url.get().strip()
        urls = self._extract_urls(text) or ([text] if text else [])
        if not urls:
            # **待機中があるならクリップボードは見ない。** ボタンは「再開」に
            # なっており、押した人は積んだものを流すつもりでいる。ここで
            # クリップボードを拾うと、途中でコピーした無関係な URL が
            # 黙ってキューに足されてダウンロードされる
            if any(j["status"] == "waiting" for j in self._jobs):
                self._queue_start()
                return
            # 「貼り付けてダウンロード」状態（§5.3）
            urls = self._extract_urls(self._clipboard_text())
            if not urls:
                self.lbl_site.configure(text=self._t("clip_empty"), text_color="gray")
                return
            if len(urls) == 1:
                self.var_url.set(urls[0])
        added, dup = self._add_urls(urls, info=self._site_info)
        if len(urls) > 1:
            self.var_url.set("")       # まとめ投入時は入力欄を空ける
        if not any(j["status"] == "waiting" for j in self._jobs):
            if dup and not added:
                self.lbl_site.configure(text=self._t("queue_dup"), text_color="gray")
            return
        self._queue_start()

    # ── ジョブキュー（design_gui_v2 §7）──────────────────────
    def _make_job(self, target: str, kind: str = "download", info=None) -> dict:
        """キューに積むジョブを 1 つ作る（§7.4）。"""
        return {
            "kind": kind,          # "download"（§8 で "append" が増える）
            "target": target,      # URL、または kind="append" の .txt パス
            "label": target,
            # **info を渡されたら site_name もここで埋める。**
            # 入力欄のバッジで判定済みの URL は判定スレッドに投げない
            # （_add_urls の使い回し経路）ので _apply_job_info を通らない。
            # ここで埋めないと、その行だけサイト名が出ない
            "site_name": (info or {}).get("display_name") or "",
            "info": info,          # --detect-site の結果。実行時に使い回す
            "status": "waiting",   # waiting/running/done/error/skipped/aborted
            "detail": "",
            "epub": None,
            "n": 0, "total": 0,
        }

    # ── キューへの投入（§7.2 / §7.8）────────────────────────
    @staticmethod
    def _extract_urls(text: str) -> list:
        """テキストから URL を順序を保って取り出す（重複は畳む）。

        クリップボードは「URL 1 本」とは限らない。X やブログからのコピーは
        本文混じりだし、メモに溜めた複数行を一度に投げたいこともある（§7.2）。
        """
        out = []
        for u in _RE_URL.findall(text or ""):
            u = u.rstrip("、。，．)）]】>＞")   # 文中の URL に付きやすい後続記号を落とす
            if u not in out:
                out.append(u)
        return out

    def _job_index(self, job) -> int:
        """同値ではなく**同一性**で探す（内容が同じ別ジョブと取り違えないため）。"""
        for i, j in enumerate(self._jobs):
            if j is job:
                return i
        return -1

    def _find_job(self, url: str):
        for j in self._jobs:
            if j["target"] == url:
                return j
            info = j.get("info") or {}
            if info.get("normalized_url") and info["normalized_url"] == url:
                return j
        return None

    def _add_urls(self, urls, info=None, staged=False) -> tuple:
        """URL を一覧に積む。戻り値は (追加した数, 重複で弾いた数)。

        staged=True は「ユーザーが明示的に積んだ」印（＋ / まとめ貼り付け）。
        """
        # 前のバッチが完全に終わっているなら作り直す。そうしないと
        # 1 本ずつ落とすたびに済んだ行が溜まり、一覧が出っぱなしになる
        if self._jobs and self._proc is None and not any(
                j["status"] in ("waiting", "running") for j in self._jobs):
            self._jobs = []
            self._queue_staged = False
            self._reset_result_view()
        if staged:
            self._queue_staged = True
        added = dup = 0
        for u in urls:
            u = (u or "").strip()
            if not u:
                continue
            if self._find_job(u) is not None:
                dup += 1
                continue
            # 入力欄で済ませた判定があれば使い回す（§5.5）。exe の起動 1 回分を省く
            reuse = info if (info is not None and u == self._site_info_url) else None
            job = self._make_job(u, info=reuse)
            self._jobs.append(job)
            if reuse is None:
                self._enqueue_detect(job)
            added += 1
        if added or dup:
            self._refresh_queue_list()
            self._sync_queue_visibility()
            self._update_download_enabled()
        return added, dup

    def _add_from_entry(self):
        """＋ ボタン。積むだけで実行はしない。"""
        text = self.var_url.get().strip()
        urls = self._extract_urls(text) or ([text] if text else [])
        if not urls:
            urls = self._extract_urls(self._clipboard_text())
        if not urls:
            self.lbl_site.configure(text=self._t("clip_empty"), text_color="gray")
            return
        added, dup = self._add_urls(urls, info=self._site_info, staged=True)
        if added:
            self.var_url.set("")
            self.lbl_site.configure(text=self._t("queue_added", n=added), text_color="gray")
        elif dup:
            self.lbl_site.configure(text=self._t("queue_dup"), text_color="gray")

    def _reset_result_view(self):
        """前のバッチの結果表示を消す。

        新しいバッチを積むと一覧は作り直されるが、**ステータス行・補助ボタン・
        進捗バーは前のバッチのまま残る**。「4 件すべて完了しました」の下に
        「0 / 3 件 待機中」が並ぶ、という食い違いが実機で出た。
        「ログを保存」も前のバッチのログを出すので、見た目だけの問題ではない。
        """
        self.lbl_status.configure(text="", text_color=("gray10", "gray90"))
        self.bar.stop()
        self.bar.grid_remove()
        self._hide_aux()
        self._epub_path = None

    def _clear_queue(self):
        """一覧を空にする。実行中のジョブだけは残す。"""
        running = [j for j in self._jobs if j["status"] == "running"]
        self._jobs = running
        self._job_i = 0 if running else -1
        if not running:
            self._queue_staged = False
            self._reset_result_view()
        self._refresh_queue_list()
        self._sync_queue_visibility()
        self._update_download_enabled()

    # ── 一覧の描画（§7.3）──────────────────────────────────
    def _queue_should_show(self) -> bool:
        """一覧を出すか。

        1 本だけ落とすときは v1 と同じ見た目にする。
        **ユーザーが明示的に積んだ（＋ / まとめ貼り付け）ものは常に出す。**
        「待機中があるなら出す」だけにすると、1 件積んだ直後に未対応と判明した
        瞬間に waiting → skipped となって一覧ごと消え、入力欄も空なので
        **その URL が画面から完全に消えて何が起きたか分からなくなる**。
        """
        return len(self._jobs) >= 2 or (self._queue_staged and bool(self._jobs))

    def _sync_queue_visibility(self):
        show = self._queue_should_show()
        if show == self._queue_shown:
            return
        self._queue_shown = show
        if show:
            self._h_before_queue = self._logical_size()[1]
            self.frm_queue.grid(row=ROW_QUEUE, column=0, sticky="ew",
                                padx=20, pady=(6, 2))
            self._fit_window(grow_only=True)
        else:
            self.frm_queue.grid_forget()
            self._fit_window(restore_to=self._h_before_queue)

    def _refresh_queue_list(self):
        for w in self.frm_queue_list.winfo_children():
            w.destroy()
        self._queue_rows = []
        for i, _job in enumerate(self._jobs):
            icon = ctk.CTkLabel(self.frm_queue_list, text="", width=20, anchor="w")
            icon.grid(row=i, column=0, sticky="w", padx=(2, 4), pady=1)
            lab = ctk.CTkLabel(self.frm_queue_list, text="", anchor="w",
                               font=ctk.CTkFont(size=11))
            lab.grid(row=i, column=1, sticky="ew", pady=1)
            sta = ctk.CTkLabel(self.frm_queue_list, text="", anchor="e",
                               text_color="gray", font=ctk.CTkFont(size=11))
            sta.grid(row=i, column=2, sticky="e", padx=(6, 2), pady=1)
            self._queue_rows.append({"icon": icon, "label": lab, "status": sta})
            self._update_queue_row(i)
        self._update_queue_count()

    @staticmethod
    def _ellipsis(text: str, limit: int = 38) -> str:
        text = (text or "").replace("\n", " ")
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _job_status_text(self, job) -> str:
        s = job["status"]
        if s == "waiting" and job.get("info") is None:
            return self._t("q_checking")
        if s == "running" and job.get("total"):
            return self._t("q_progress", n=job["n"], m=job["total"])
        if s in ("error", "skipped") and job.get("detail"):
            return self._ellipsis(job["detail"], 34)
        key = "q_" + s
        return self._t(key) if key in UI else s

    def _update_queue_row(self, i: int):
        if not (0 <= i < len(self._queue_rows) and i < len(self._jobs)):
            return
        job, row = self._jobs[i], self._queue_rows[i]
        row["icon"].configure(text=_JOB_ICON.get(job["status"], "・"))
        label = job.get("label") or job["target"]
        if job.get("site_name"):
            label = "%s  [%s]" % (self._ellipsis(label, 30), job["site_name"])
        else:
            label = self._ellipsis(label)
        row["label"].configure(text=label)
        row["status"].configure(text=self._job_status_text(job))

    def _update_queue_count(self):
        done = sum(1 for j in self._jobs
                   if j["status"] in ("done", "error", "skipped", "aborted"))
        self.lbl_queue_count.configure(
            text=self._t("queue_count", done=done, total=len(self._jobs)))

    # ── サイト判定を 1 本のスレッドで直列化する（§7.9）────────
    def _start_detect_thread(self):
        self._detect_jobs_q = queue.Queue()
        threading.Thread(target=self._queue_detect_worker, daemon=True).start()

    def _queue_detect_worker(self):
        """積まれた順に 1 件ずつ判定する。

        積むたびにスレッドを立てると 5 本で 5 プロセスが同時に上がる。
        --detect-site はオフライン・即時だが exe の起動コストはある。
        """
        while True:
            job = self._detect_jobs_q.get()
            if job is None:
                return
            try:
                info = detect_site(job["target"])
            except Exception:
                info = None
            self._queue.put(("jobinfo", job, info))

    def _enqueue_detect(self, job):
        if job.get("info") is None:
            self._detect_jobs_q.put(job)

    def _apply_job_info(self, job, info):
        i = self._job_index(job)
        if i < 0 or job["status"] != "waiting":
            return          # 一覧から消された / すでに走り出している
        job["info"] = info or {}
        if not info or info.get("site") is None:
            job["status"] = "skipped"
            job["detail"] = self._t("q_skipped")
        else:
            job["site_name"] = info.get("display_name") or ""
        self._update_queue_row(i)
        self._update_queue_count()
        self._sync_queue_visibility()
        self._update_download_enabled()

    def _start_download(self, url: str):
        """URL 1 本を積んでキューを流す（従来の単発ダウンロード経路）。"""
        self._add_urls([url], info=self._site_info)
        self._queue_start()

    def _queue_start(self):
        """キューの実行を始める。設定はここで 1 回だけ固める（§7.10）。"""
        self._persist()
        self._queue_settings = self._collect_settings()
        self._abort_event.clear()
        if self._log_open:      # 前回分は破棄されるうえ、実行中は開閉ボタンが出ない
            self._toggle_log()
        self._advance()

    def _advance(self):
        """次の待機ジョブへ進む。無ければキュー終了。"""
        for i, job in enumerate(self._jobs):
            if job["status"] == "waiting":
                self._start_job(i)
                return
        self._queue_done()

    def _start_job(self, i: int):
        self._job_i = i
        job = self._jobs[i]
        job["status"] = "running"
        # ここから下はジョブ単位でリセットする値
        self._epub_path = None
        self._raw_log = []
        self._needs_playwright = False
        self._prog_t0 = None
        self._prog_n0 = 0
        self._last_url = job["target"]
        # §3.2: この時刻より古い .epub は「今回の成果物」ではない
        self._started_at = time.time()
        self._set_state_running()
        self._update_queue_row(i)
        self._update_queue_count()
        if len(self._jobs) > 1:
            self.lbl_status.configure(text=self._t(
                "queue_running", i=i + 1, n=len(self._jobs),
                label=self._ellipsis(job.get("label") or job["target"], 28)))
        self._proc = "starting"           # 二重起動防止のプレースホルダ
        self._worker = threading.Thread(
            target=self._download_worker,
            args=(job, self._queue_settings or self._collect_settings()),
            daemon=True)
        self._worker.start()

    def _queue_done_summary(self):
        """複数件を流し終えたときのまとめ表示（§7.7）。"""
        total = len(self._jobs)
        ok = sum(1 for j in self._jobs if j["status"] == "done")
        ng = sum(1 for j in self._jobs if j["status"] in ("error", "skipped"))
        # **中止・未処理を数え落とさない。** §7.6 のとおり中止すると残りは
        # waiting のまま残るので、done でも error でもないジョブが出る。
        # これを無視すると「1 件も落とせていないのに緑で全件完了」と出る
        rest = total - ok - ng
        self.btn_main.configure(text=self._t("download"), state="normal")
        self._set_url_entry_enabled(True)
        self.bar.stop()
        self.bar.grid_remove()
        self._update_queue_count()
        if rest:
            self.lbl_status.configure(
                text=self._t("queue_stopped", ok=ok, ng=ng, rest=rest),
                text_color=("#8a6d00", "#e3b341"))
        elif ng == 0:
            self.lbl_status.configure(text=self._t("queue_all_ok", total=total),
                                      text_color=("#1a7f37", "#3fb950"))
        else:
            self.lbl_status.configure(
                text=self._t("queue_summary", total=total, ok=ok, ng=ng),
                text_color=("#8a6d00", "#e3b341"))
        # 最後に成功したジョブの成果物を「開く」対象にする
        last_ok = [j for j in self._jobs if j["status"] == "done" and j.get("epub")]
        self._epub_path = last_ok[-1]["epub"] if last_ok else None
        aux = []
        # 再試行は error だけを対象にする。skipped（未対応サイト）は
        # 何度やっても結果が変わらないので混ぜない
        n_err = sum(1 for j in self._jobs if j["status"] == "error")
        if n_err:
            self.btn_retry.configure(text=self._t("retry_failed", n=n_err))
            aux.append(self.btn_retry)
        if self._epub_path and os.path.isfile(self._epub_path):
            aux.append(self.btn_open_epub)
        aux += [self.btn_open, self.btn_log, self.btn_savelog]
        self._show_aux(*aux)
        self._update_download_enabled()

    def _retry_failed(self):
        """失敗した分だけ待機に戻して流し直す（§7.7）。"""
        n = 0
        for job in self._jobs:
            if job["status"] == "error":
                job.update(status="waiting", detail="", n=0, total=0, epub=None)
                n += 1
        if not n:
            return
        self._refresh_queue_list()
        self._sync_queue_visibility()
        self._queue_start()

    def _current_job(self):
        """実行中のジョブ。走っていなければ None。"""
        if 0 <= self._job_i < len(self._jobs):
            return self._jobs[self._job_i]
        return None

    def _job_finished(self, status: str, err_kind: str = ""):
        """**ダウンロードの唯一の出口**（§7.5）。

        終端は precheck / aborted / finished の 3 経路あり、それぞれに
        「次へ進む」を書くと必ず取りこぼす。すべてここを通す。
        """
        job = self._current_job()
        if job is not None:
            job["status"] = status
            job["epub"] = self._epub_path
            job["err_kind"] = err_kind or ("hameln" if self._needs_playwright else "")
            if status in ("error", "skipped"):
                job["detail"] = self._error_detail() or self._t("q_" + status)
            self._update_queue_row(self._job_i)
            self._update_queue_count()
        if status == "aborted":
            self._queue_done()            # 中止はキュー全体を止める（§7.6）
            return
        self._advance()

    def _queue_done(self):
        """キューが終わったときの表示。

        1 件だけのときは v1.2 とまったく同じ画面遷移にする（§7.3）。
        """
        self._job_i = -1
        self._sync_queue_visibility()
        job = self._jobs[-1] if self._jobs else None
        if job is None:
            self._set_state_idle()
            return
        if len(self._jobs) > 1:
            self._queue_done_summary()
            return
        status = job["status"]
        if status == "aborted":
            self._set_state_idle()
            self.lbl_status.configure(text=self._t("aborted"))
        elif status == "done":
            self._set_state_done()
            if self.settings.get("open_folder_on_done", True):
                self._open_folder()      # 完了と同時に自動オープン（設定で切れる）
        elif status == "skipped":
            self._set_state_error(job.get("err_kind") or "unsupported")
        else:
            self._set_state_error(job.get("err_kind") or "failed")

    def _abort(self):
        self._abort_event.set()           # ワーカーが起動前チェックで参照する
        # 停止処理は taskkill / wait でブロックしうるため UI スレッドで走らせない。
        # ここで同期実行すると中止ボタンを押した瞬間に画面が固まる。
        threading.Thread(target=_terminate_tree, args=(self._proc,),
                         daemon=True).start()

    # ── ダウンロードワーカー（別スレッド・§6） ──────────────────
    def _build_cli_args(self, job: dict, s: dict) -> list:
        """ジョブ 1 件分の CLI 引数を組む。

        job を受け取るのは §8 への布石（`kind="append"` は `--append FILE` になる）。
        v1.3 の時点では "download" しか作らないので分岐は置かない。
        """
        target = job["info"].get("normalized_url") if job.get("info") else None
        args = [target or job["target"], "--output-dir", s["output_dir"]]
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
        # 進捗・完了は JSON イベントで受け取る（design_progress_json.md）
        args.append("--progress-json")
        return args

    def _download_worker(self, job: dict, s: dict):
        """ワーカー本体。どんな失敗でも finished を送り、UI を実行中のまま残さない。"""
        try:
            self._download_worker_inner(job, s)
        except Exception as e:
            self._queue.put(("rawlog", f"[アプリ内エラー] {e}"))
            self._queue.put(("finished", 1))

    def _download_worker_inner(self, job: dict, s: dict):
        # 1) 事前チェック（未対応かどうかだけ）
        info = job.get("info")
        if info is None:
            info = detect_site(job["target"])
            job["info"] = info
        if not info or info.get("site") is None:
            self._queue.put(("precheck", "unsupported"))
            return
        # playwright が要るサイトでも**ここでは止めない**（design_gui_v2 §3.4）。
        # --detect-site の needs_playwright は「このサイトの性質」であって
        # 「この環境で動かない」ではない。v1 は導入済みの環境でも門前払いしていた。
        # 実行してみて、失敗したときに専用の案内を出す。
        self._needs_playwright = bool(info.get("needs_playwright"))

        # 事前チェック中に中止されていたらダウンロードを起動しない
        if self._abort_event.is_set():
            self._queue.put(("aborted",))
            return

        # 2) ダウンロード起動（イベント方式）
        cli = self._build_cli_args(job, s)
        rc, got_events = self._run_engine(cli)
        if rc is None:
            return
        # 版ずれ対策: 古いエンジンは --progress-json を知らず argparse エラー(2)で即死する。
        # 1 度だけフラグ無しで再実行し、旧方式（stderr の正規表現）で拾う。
        if rc == 2 and not got_events and "--progress-json" in cli:
            self._queue.put(("rawlog",
                             "[情報] エンジンが --progress-json 非対応のため旧方式で再実行します"))
            rc, _ = self._run_engine([a for a in cli if a != "--progress-json"])
            if rc is None:
                return
        self._queue.put(("finished", rc))

    # ── エンジン起動と 2 ストリーム読み取り（design_progress_json.md §4） ──

    def _run_engine(self, cli_args):
        """エンジンを起動し (終了コード, イベントを受信したか) を返す。

        stdout は JSON Lines のイベント、stderr は人間向けログ。
        起動に失敗した場合は (None, False) を返し、呼び出し側は打ち切る。
        """
        try:
            proc = subprocess.Popen(
                engine_cmd(*cli_args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=_engine_env(), creationflags=_CREATE_NO_WINDOW,
                bufsize=1, universal_newlines=True, encoding="utf-8", errors="replace",
            )
        except Exception as e:
            self._queue.put(("rawlog", f"[起動失敗] {e}"))
            self._queue.put(("finished", 1))
            return None, False
        self._proc = proc
        # 起動と中止が競合した場合、起動直後でも止める
        if self._abort_event.is_set():
            _terminate_tree(proc)

        t_err = threading.Thread(target=self._read_log, args=(proc.stderr,), daemon=True)
        t_err.start()
        got_events = self._read_events(proc.stdout)
        rc = proc.wait()
        t_err.join(timeout=5)
        return rc, got_events

    def _read_events(self, stream) -> bool:
        """stdout の JSON Lines を読む。1 件でも受信したら True。"""
        got = False
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                self._queue.put(("rawlog", line))   # 想定外の行はログへ流す
                continue
            got = True
            # 1 件の異常でループを抜けるとワーカースレッドごと死に、finished が
            # 送られず GUI が「実行中」のまま固まる。イベント単位で握りつぶす。
            try:
                kind = ev.get("event")
                if kind == "progress":
                    self._queue.put(("progress",
                                     int(ev.get("n", 0)), int(ev.get("total", 0))))
                elif kind == "output" and ev.get("kind") == "epub":
                    self._queue.put(("epub", str(ev.get("path", "")).strip()))
                elif kind == "workinfo":
                    self._queue.put(("workinfo", {
                        "title": str(ev.get("title") or ""),
                        "author": str(ev.get("author") or ""),
                        "total": ev.get("total"),
                        "unit": str(ev.get("unit") or "episode"),
                    }))
                elif kind == "stage":
                    # label は使わない。_print_stage() の呼び出し側は日本語ハードコードで
                    # i18n されていないため、英語 UI に日本語が出る（design_gui_v2 §5.7）。
                    # n だけ使い、GUI 側の対訳に差し替える。label 全文は stderr の生ログに残る。
                    self._queue.put(("stage", int(ev.get("n", 0))))
                # 未知のイベントは無視する（人間向けの見出しは stderr に出る）
            except Exception:
                self._queue.put(("rawlog", f"[警告] イベントを解釈できません: {line}"))
        return got

    def _read_log(self, stream):
        """stderr の人間向けログを読む。

        旧正規表現も残す。新エンジンでも人間向け出力はこちらに来るので
        イベントと二重に拾うことになるが、値は同じで害がない。
        古いエンジンへフォールバックしたときはこちらだけが頼りになる。
        """
        for line in stream:
            line = line.rstrip("\n")
            self._queue.put(("rawlog", line))
            m = _RE_PROGRESS.match(line)
            if m:
                self._queue.put(("progress", int(m.group(1)), int(m.group(2))))
                continue
            md = _RE_EPUB_DONE.search(line)
            if md:
                self._queue.put(("epub", md.group(1).strip()))

    # ── キュー監視（UIスレッド・§6） ──────────────────────────
    def _poll_queue(self):
        if self._closing:
            return          # destroy 済みのウィジェットを触らない
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self._poll_after = self.after(100, self._poll_queue)

    def _handle_msg(self, msg):
        kind = msg[0]
        if kind == "autofill":
            # 判定が返ってくるまでの間に状況が変わっていることがあるので、ここで再確認する。
            # **実行中かどうかも見直す。** 判定は _maybe_autofill_from_clipboard が
            # 実行前に始めるが、結果は数秒後に届くため、その間にダウンロードが始まって
            # いることがある。実行中の URL 欄は走っている作品を指しているべきで、
            # ここで差し替えると「何を落としているのか」が画面と食い違う
            if self._proc is not None:
                return
            cur = self.var_url.get().strip()
            if not cur or cur == self._last_url:
                self.var_url.set(msg[1])
                self._request_detect()
            return
        if kind == "site":
            self._apply_site_info(msg[1], msg[2], msg[3])
            return
        if kind == "engine_ver":
            self._engine_ver = msg[1]
            if msg[1]:
                self.lbl_ver.configure(text=self._t("engine_ver", ver=msg[1]))
            return
        # 中止後にパイプへ残っていた分で表示が進まないようにする
        if kind in ("progress", "epub", "stage") and self._abort_event.is_set():
            return
        if kind == "jobinfo":
            self._apply_job_info(msg[1], msg[2])
            return
        if kind == "workinfo":
            # 作品情報をジョブに控える（§7.4 の label / §7.3 の一覧表示に使う）。
            # エンジンが作品情報を取り終えた時点で 1 回だけ届く
            job = self._current_job()
            if job is not None:
                info = msg[1]
                if info["title"]:
                    job["label"] = info["title"]
                job["author"] = info["author"]
                job["total_known"] = info["total"]
                job["unit"] = info["unit"]
                self._update_queue_row(self._job_i)
        elif kind == "stage":
            key = "stage%d" % msg[1]
            if key in UI:
                self.lbl_status.configure(text=self._t(key),
                                          text_color=("gray10", "gray90"))
        elif kind == "progress":
            n, m = msg[1], msg[2]
            if self.bar.cget("mode") != "determinate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
            self.bar.set(n / m if m else 0)
            job = self._current_job()
            if job is not None:
                job["n"], job["total"] = n, m
                self._update_queue_row(self._job_i)
            text = self._t("progress", n=n, m=m) + self._eta(n, m)
            if len(self._jobs) > 1:
                text = "[%d/%d] %s" % (self._job_i + 1, len(self._jobs), text)
            self.lbl_status.configure(text=text, text_color=("gray10", "gray90"))
        elif kind == "epub":
            self._epub_path = msg[1]
        elif kind == "rawlog":
            self._raw_log.append(msg[1])
            if self._log_open:
                self.txt_log.insert("end", msg[1] + "\n")
                self.txt_log.see("end")
        # ── 終端は必ず _job_finished を通す（§7.5）──
        elif kind == "precheck":
            self._proc = None
            self._job_finished("skipped", err_kind=msg[1])
        elif kind == "aborted":
            self._proc = None
            self._job_finished("aborted")
        elif kind == "finished":
            rc = msg[1]
            self._proc = None
            if self._abort_event.is_set():   # 中止後の終了は「中止」として扱う
                self._job_finished("aborted")
            elif rc == 0:
                self._fallback_epub_path()
                self._job_finished("done")
            else:
                self._job_finished("error")

    def _eta(self, n: int, m: int) -> str:
        """実測ペースから残り時間の目安を出す（design_gui_v2 §6）。

        delay から計算すると取得時間を無視することになるので、実際に進んだ
        話数と経過時間から割り出す。300 話の待ち時間が読めないのは不安になる。
        """
        now = time.monotonic()
        if self._prog_t0 is None:
            self._prog_t0, self._prog_n0 = now, n
            return ""
        if not m or n <= self._prog_n0:
            return ""
        per = (now - self._prog_t0) / (n - self._prog_n0)
        remain = per * (m - n)
        if remain < 45:
            return ""
        return self._t("eta", min=max(1, int(round(remain / 60))))

    def _fallback_epub_path(self):
        """epub パス未捕捉なら出力先の最新 .epub を採用（§6）。

        **今回の実行より古いファイルは採らない**（design_gui_v2 §3.2）。
        v1 は出力先の最新 .epub を無条件に拾っていたため、ePub が作られなかった
        実行のあとに「前回の別作品」を完了として開いてしまうことがあった。
        """
        if self._epub_path and os.path.isfile(self._epub_path):
            return
        self._epub_path = None
        try:
            d = self.settings["output_dir"]
            epubs = [os.path.join(d, f) for f in os.listdir(d)
                     if f.lower().endswith((".epub", ".kepub.epub"))]
            # mtime の粒度と時計のずれを考え 2 秒だけ猶予を持たせる
            fresh = [f for f in epubs
                     if os.path.getmtime(f) >= self._started_at - 2]
            if fresh:
                self._epub_path = max(fresh, key=os.path.getmtime)
        except Exception:
            pass

    # ── 各種アクション ────────────────────────────────────────
    def _open_epub(self):
        """出来た ePub を既定のアプリで開く（§6）。

        「フォルダを開く」の先がゴールなので、そこまで 1 クリックで届かせる。
        """
        path = self._epub_path
        # **拡張子を必ず確かめる。** os.startfile は関連付けに従って何でも起動するため、
        # ここは「表示」ではなく「実行」のシンクになる。_epub_path には
        # stdout の JSON イベントのほかに、stderr を _RE_EPUB_DONE で拾う経路があり
        # （design_progress_json §4.1 の版ずれ対策として残している）、stderr には
        # --progress-json 時にサイト由来の作品名・話タイトルがそのまま流れ込む。
        # 現状はイベント順序のおかげで偽装が最後に来ないが、それはエンジン側の
        # 都合であって GUI が保証できる不変条件ではない。ここで断つ。
        if not (path and os.path.isfile(path)
                and path.lower().endswith(_EPUB_EXTS)):
            self._open_folder()
            return
        try:
            if IS_WINDOWS:
                os.startfile(path)       # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", path])
        except Exception:
            self._open_folder()          # 関連付けが無ければフォルダを開くに退避

    def _save_log(self):
        """生ログをファイルへ書き出す（§6）。

        v1 は _raw_log をメモリに溜めるだけで、不具合を報告してもらう手段が無かった。
        """
        name = "novel_downloader_log_%s.txt" % time.strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            initialfile=name, defaultextension=".txt",
            initialdir=self.settings.get("output_dir") or default_output_dir(),
            filetypes=[(self._t("ft_text"), "*.txt"), (self._t("ft_all"), "*.*")])
        if not path:
            return
        # 保存の報せでエラー文を消さない。数秒だけ差し替えて元に戻す
        prev = (self.lbl_status.cget("text"), self.lbl_status.cget("text_color"))
        try:
            header = [
                "# %s" % APP_NAME_EN,
                "# engine: %s" % (self._engine_ver or "unknown"),
                "# url: %s" % self._last_url,
                "# saved: %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
                "",
            ]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(header + self._raw_log) + "\n")
            self.lbl_status.configure(text="%s: %s" % (self._t("log_saved"), path),
                                      text_color=("#1a7f37", "#3fb950"))
        except Exception as e:
            self.lbl_status.configure(text="%s" % e, text_color=("#b3261e", "#f2b8b5"))
        self.after(5000, lambda: self._restore_status(*prev))

    def _restore_status(self, text, color):
        if self._closing:
            return
        self.lbl_status.configure(text=text, text_color=color)

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
        win.title(self._t("sites_title"))
        win.geometry("320x420")
        win.transient(self)
        frm = ctk.CTkScrollableFrame(win, label_text=self._t("sites_label"))
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        if not sites:
            ctk.CTkLabel(frm, text=self._t("sites_fail")).pack(anchor="w")
        for s in sites:
            ctk.CTkLabel(frm, text="・" + s.get("display_name", ""),
                         anchor="w").pack(fill="x", anchor="w", pady=1)

    # ── ウィンドウサイズ（DPI スケーリングに注意） ─────────────
    def _window_scale(self) -> float:
        try:
            return float(ctk.ScalingTracker.get_window_scaling(self)) or 1.0
        except Exception:
            return 1.0

    def _logical_size(self):
        """現在のウィンドウサイズを geometry() と同じ単位で返す。

        **winfo_width()/winfo_height() と geometry() を混ぜてはいけない。**
        CustomTkinter の `CTk.geometry(文字列)` は値に DPI 倍率を掛けて Tk に渡すが、
        `winfo_*` が返すのは掛けたあとの実ピクセル。winfo の値をそのまま geometry に
        渡すと倍率が二重にかかり、**開閉のたびにウィンドウが倍率ぶん増殖する**
        （150% 表示の Windows で実際に起きた）。
        引数なしの `geometry()` は逆変換済みの値を返すので、こちらを使う。
        """
        try:
            m = re.match(r"^(\d+)x(\d+)", self.geometry())
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
        return 560, 420

    def _max_logical_height(self) -> int:
        """画面からはみ出さない高さの上限（geometry と同じ単位）。"""
        try:
            return max(MIN_HEIGHT_PX,
                       int(self.winfo_screenheight() / self._window_scale()) - 80)
        except Exception:
            return 2000

    def _content_height(self) -> int:
        """内容が必要とする高さ（geometry と同じ論理単位）。

        `winfo_reqheight()` は**実ピクセル**を返すので倍率で割る（§6.1）。
        """
        self.update_idletasks()
        return int(self.winfo_reqheight() / self._window_scale() + 0.999)

    def _fit_flexible_panels(self):
        """伸縮する 2 つのパネル（詳細設定・一覧）の**見える**高さを決める。

        どちらも中身が全部入るならその高さ。画面に収まらないなら詰めて、
        足りない分はパネル内でスクロールさせる。
        **両方開くと画面に入らない**ことがあるので、まとめて配分する
        （片方ずつ決めると、もう片方の存在を無視して画面からはみ出す）。
        """
        d_open, q_open = self._detail_open, self._queue_shown
        if not (d_open or q_open):
            return
        scale = self._window_scale()
        self.update_idletasks()
        # 中身の自然な高さ。CTkScrollableFrame 自身が内側の内容フレームなので、
        # winfo_reqheight() が中身の高さを返す（見える高さは configure(height=) 側）
        d_want = int(self.frm_detail.winfo_reqheight() / scale + 0.999) if d_open else 0
        q_want = QUEUE_LIST_PX if q_open else 0
        # 両方 1px に潰して「パネル以外に要る高さ」を測る
        if d_open:
            self.frm_detail.configure(height=1)
        if q_open:
            self.frm_queue_list.configure(height=1)
        self.update_idletasks()
        base = int(self.winfo_reqheight() / scale + 0.999)
        avail = self._max_logical_height() - base - FIT_MARGIN_PX

        q_h = min(q_want, max(QUEUE_MIN_PX, avail - DETAIL_MIN_PX)) if q_open else 0
        d_h = min(d_want, max(DETAIL_MIN_PX, avail - q_h)) if d_open else 0
        if d_h + q_h > avail:
            # 快適な下限の合計すら入らない（1366x768 のノート等）。
            # 絶対最小まで詰めて分け合う。中身はどちらもスクロールで届く
            if d_open and q_open:
                q_h = max(QUEUE_FLOOR_PX, min(q_h, avail - DETAIL_FLOOR_PX))
                d_h = max(DETAIL_FLOOR_PX, avail - q_h)
            elif d_open:
                d_h = max(DETAIL_FLOOR_PX, avail)
            else:
                q_h = max(QUEUE_FLOOR_PX, avail)
        if d_open:
            self.frm_detail.configure(height=d_h)
        if q_open:
            self.frm_queue_list.configure(height=q_h)

    def _fit_window(self, grow_only: bool = False, restore_to: int = 0):
        """内容が収まる高さにウィンドウを合わせる。

        固定値で増減する方式はやめた。パネルに項目を足すたびに値が合わなくなり、
        **開いても中身が全部見えない**のにスクロールもできない状態になる。

        grow_only=True は「広げるだけ」。パネルを開くときに使い、
        ユーザーが手で広げた分を勝手に縮めない。
        restore_to は「閉じるときに戻したい高さ」。開く直前の高さを渡すことで、
        **ユーザーが手で設定した大きさを開閉で失わない**。内容に足りなければ
        内容側が優先される（＝どちらにせよはみ出さない）。
        """
        try:
            # 一覧やログの開閉で使える高さが変わるので、毎回計り直す
            self._fit_flexible_panels()
            need = self._content_height()
        except Exception:
            return
        w, h = self._logical_size()
        if grow_only:
            target = max(h, need)
        else:
            target = max(need, restore_to or 0)
        target = max(BASE_HEIGHT_PX, min(target, self._max_logical_height()))
        if target != h:
            self.geometry(f"{w}x{target}")
        # **geometry() で読み直さない。** 設定した直後は WM が反映するまで
        # 古い値が返るため、基準高さが 1 世代ずれる
        self._remember_base_height(target)

    def _remember_base_height(self, height: int = None):
        """パネルを何も開いていないときの高さを覚える。

        終了時に保存する高さはこれ。固定値を引き算する方式だと、
        値がずれた瞬間に「次回は縦に間延びした窓で開く」が復活する。
        """
        if self._detail_open or self._log_open or self._queue_shown:
            return
        self._base_height = height if height is not None else self._logical_size()[1]

    def _toggle_detail(self):
        """詳細設定の開閉。

        高さは**絶対値ではなく増減で**指定する（design_gui_v2 §6）。
        v1 は `geometry("560x720")` / `("560x420")` と決め打ちだったため、
        ユーザーがリサイズした幅も高さも開閉のたびに捨てられていた。
        """
        self._detail_open = not self._detail_open
        if self._detail_open:
            self._h_before_detail = self._logical_size()[1]
            self.btn_detail.configure(text=self._t("adv_open"))
            self.frm_detail.grid(row=ROW_DETAIL, column=0, sticky="ew", padx=16, pady=(2, 10))
            self._fit_window(grow_only=True)
        else:
            self.btn_detail.configure(text=self._t("adv_closed"))
            self.frm_detail.grid_forget()
            self._fit_window(restore_to=self._h_before_detail)

    def _toggle_log(self):
        self._log_open = not self._log_open
        if self._log_open:
            self._h_before_log = self._logical_size()[1]
            self.btn_log.configure(text=self._t("hide_log"))
            # sticky="nsew" ＋ weight=1 で、ウィンドウの余った高さをログ欄が吸う。
            # これが無いと窓をいくら大きくしてもログ欄は 120px のままだった
            self.txt_log.grid(row=ROW_LOG, column=0, sticky="nsew", padx=20, pady=(2, 2))
            self.grip_log.grid(row=ROW_GRIP, column=0, sticky="ew", padx=20, pady=(0, 8))
            self.grid_rowconfigure(ROW_LOG, weight=1)
            self.txt_log.delete("1.0", "end")
            self.txt_log.insert("end", "\n".join(self._raw_log) + "\n")
            self.txt_log.see("end")
            self._fit_window(grow_only=True)
        else:
            self.btn_log.configure(text=self._t("show_log"))
            self.txt_log.grid_forget()
            self.grip_log.grid_forget()
            self.grid_rowconfigure(ROW_LOG, weight=0)
            self._fit_window(restore_to=self._h_before_log)

    # ── ログ欄のサイズ変更グリップ ────────────────────────────
    def _grip_press(self, event):
        self._grip_y = event.y_root
        self._grip_h = self._logical_size()[1]

    def _grip_drag(self, event):
        """グリップのドラッグで窓の高さを変える。

        ログ行に weight=1 が入っているので、増えた高さはそのままログ欄になる。
        event.y_root は実ピクセルなので、geometry に渡す前に倍率で割る。
        """
        if self._grip_y is None:
            return
        dy = (event.y_root - self._grip_y) / self._window_scale()
        w = self._logical_size()[0]
        h = max(MIN_HEIGHT_PX, min(int(self._grip_h + dy), self._max_logical_height()))
        self.geometry(f"{w}x{h}")

    def _grip_release(self, _event=None):
        self._grip_y = None

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
            filetypes=[(self._t("ft_image"), "*.jpg *.jpeg *.png"),
                        (self._t("ft_all"), "*.*")])
        if f:
            self._cover_image_path = f
            self.var_cover_file.set(os.path.basename(f))
            self._persist()

    def _pick_font(self):
        f = filedialog.askopenfilename(
            filetypes=[(self._t("ft_font"), "*.otf *.ttf *.woff *.woff2"),
                        (self._t("ft_all"), "*.*")])
        if f:
            self._font_path = f
            self.var_font_name.set(os.path.basename(f))
            self._persist()

    def _clear_font(self):
        self._font_path = ""
        self.var_font_name.set(self._t("font_default"))
        self._persist()

    # ── 右クリックメニュー・キー操作（design_gui_v2 §5.1 / §5.2） ──
    def _attach_context_menu(self, widget):
        """入力欄に右クリックメニューと Ctrl+A を付ける。

        CustomTkinter に Menu 相当が無いので tkinter.Menu を直接使う。
        操作の実体は Tk の仮想イベントに投げる（自前で clipboard を触ると
        選択範囲の置換や IME 変換中の挙動を取りこぼす）。
        """
        inner = _inner_entry(widget)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="", command=lambda: inner.event_generate("<<Cut>>"))
        menu.add_command(label="", command=lambda: inner.event_generate("<<Copy>>"))
        menu.add_command(label="", command=lambda: inner.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="", command=lambda: self._select_all(inner))
        menu.add_command(label="", command=lambda: inner.delete(0, "end"))
        # ラベルはポップアップのたびに入れ直す（言語切替に追従させるため）
        inner.bind("<Button-3>", lambda e: self._popup_menu(menu, inner, e), add="+")
        # Tk の既定では Ctrl+A は「行頭へ移動」で全選択にならない（§5.2）
        inner.bind("<Control-a>", lambda e: self._select_all(inner), add="+")
        inner.bind("<Control-A>", lambda e: self._select_all(inner), add="+")
        return menu

    @staticmethod
    def _select_all(inner):
        try:
            inner.select_range(0, "end")
            inner.icursor("end")
        except Exception:
            pass
        return "break"     # Tk 既定のカーソル移動と二重に動かさない

    def _popup_menu(self, menu, inner, event):
        inner.focus_set()
        try:
            has_sel = bool(inner.selection_present())
        except Exception:
            has_sel = False
        has_clip = bool(self._clipboard_text())
        has_text = bool(inner.get())
        editable = str(inner.cget("state")) not in ("disabled", "readonly")
        labels = ("ctx_cut", "ctx_copy", "ctx_paste", None, "ctx_selectall", "ctx_clear")
        states = (has_sel and editable, has_sel, has_clip and editable,
                  None, has_text, has_text and editable)
        for i, (key, ok) in enumerate(zip(labels, states)):
            if key is None:
                continue
            menu.entryconfigure(i, label=self._t(key),
                                state=("normal" if ok else "disabled"))
        menu.configure(**_menu_colors())
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            # grab を握ったままだと以降のクリックを全部吸ってアプリが無反応になる
            menu.grab_release()
        return "break"

    def _on_return(self, _event=None):
        """Enter でダウンロード開始。実行中は無視する（中止の暴発を防ぐ・§5.2）。"""
        if self._proc is None and str(self.btn_main.cget("state")) == "normal":
            self._on_main_button()
        return "break"

    def _on_escape(self, _event=None):
        if self._proc is not None:
            self._abort()

    # ── クリップボード（§5.3 / §5.4） ──────────────────────────
    def _clipboard_text(self) -> str:
        try:
            return (self.clipboard_get() or "").strip()
        except Exception:
            return ""        # 選択が無いと TclError になる

    def _clipboard_url(self) -> str:
        """クリップボードの先頭が URL ならそれを返す。そうでなければ ""。

        X やブログからのコピーは「本文 + URL」ではなく「URL + 付随テキスト」に
        なることが多いので、空白・改行の手前までを URL として切り出す。
        """
        text = self._clipboard_text()
        if not text.startswith(("http://", "https://")):
            return ""
        return text.split()[0]

    def _paste_url(self):
        urls = self._extract_urls(self._clipboard_text())
        if len(urls) > 1:              # まとめてコピーされていたら一覧へ（§7.2）
            added, dup = self._add_urls(urls, info=self._site_info, staged=True)
            if added:
                # 一覧へ移したものが入力欄にも残っていると、どちらが対象か分からない。
                # ＋ ボタン（_add_from_entry）と挙動を揃える
                self.var_url.set("")
            self.lbl_site.configure(
                text=self._t("queue_added", n=added) if added else self._t("queue_dup"),
                text_color="gray")
            return
        url = urls[0] if urls else ""
        if not url:
            self.lbl_site.configure(text=self._t("clip_empty"), text_color="gray")
            return
        self.var_url.set(url)
        self._last_clip = url
        self.ent_url.focus_set()
        self._request_detect()

    def _on_focus_in(self, event):
        """ウィンドウがフォーカスを得たらクリップボードを見直す（§5.4）。

        v1 は起動時 1 回だけだったため、「アプリを開いたままブラウザで次の URL を
        コピーする」という最も自然な使い方で自動入力がまったく効かなかった。
        """
        # <FocusIn> は子ウィジェットでも発火する。これが無いと入力欄をクリック
        # するたびに走る（必須のガード）
        if event.widget is not self:
            return
        self._maybe_autofill_from_clipboard()

    def _maybe_autofill_from_clipboard(self):
        """条件を全部満たしたときだけクリップボードの URL を入れる（§5.4）。"""
        if not self.settings.get("auto_paste", True):
            return
        if self._proc is not None:
            return
        url = self._clipboard_url()
        if not url or url == self._last_clip:
            return
        cur = self.var_url.get().strip()
        if cur == url:
            return
        # ユーザーが手で入力・編集した文字列は絶対に消さない。
        # 空か、直前にダウンロードした URL のままのときだけ差し替える
        if cur and cur != self._last_url:
            return
        # **_last_clip は実際に貼ると決めてから記録する。**
        # 判定より前に書くと、入力中だったせいで見送ったクリップボードが
        # 「処理済み」になり、欄を消して戻ってきても二度と貼られない
        self._last_clip = url
        threading.Thread(target=self._clipboard_worker, args=(url,),
                         daemon=True).start()

    def _clipboard_worker(self, url: str):
        info = detect_site(url)
        # playwright 必須サイトも入れる（§3.4）。バッジで注意を出したうえで押させる
        if info and info.get("site"):
            self._queue.put(("autofill", url))

    # ── サイト判定バッジ（§5.5） ──────────────────────────────
    def _on_url_changed(self):
        self._update_download_enabled()
        self._request_detect()

    def _request_detect(self):
        """入力が 400ms 止まったらサイト判定する（デバウンス）。"""
        if self._detect_after is not None:
            try:
                self.after_cancel(self._detect_after)
            except Exception:
                pass
            self._detect_after = None
        url = self.var_url.get().strip()
        if not url:
            self._detect_seq += 1          # 進行中の結果を無効にする
            self._site_info = None
            self._site_info_url = ""
            self.lbl_site.configure(text="")
            self._update_download_enabled()
            return
        if self._site_info_url == url:
            return                          # 判定済みの URL は叩き直さない
        self._detect_after = self.after(400, self._start_detect)

    def _start_detect(self):
        self._detect_after = None
        url = self.var_url.get().strip()
        if not url:
            return
        self._detect_seq += 1
        self._site_info = None
        self._site_info_url = ""
        self.lbl_site.configure(text=self._t("detecting"), text_color="gray")
        self._update_download_enabled()
        threading.Thread(target=self._detect_worker,
                         args=(url, self._detect_seq), daemon=True).start()

    def _detect_worker(self, url: str, seq: int):
        self._queue.put(("site", seq, url, detect_site(url)))

    def _apply_site_info(self, seq: int, url: str, info):
        # 世代カウンタ。遅れて返った古い結果が新しい入力の判定を上書きしないようにする
        if seq != self._detect_seq or url != self.var_url.get().strip():
            return
        self._site_info = info or {}
        self._site_info_url = url
        name = (info or {}).get("display_name") or ""
        if not info or info.get("site") is None:
            self.lbl_site.configure(text=self._t("site_ng"), text_color=("#b3261e", "#f2b8b5"))
        elif info.get("needs_playwright"):
            self.lbl_site.configure(text=self._t("site_pw", name=name),
                                    text_color=("#8a6d00", "#e3b341"))
        else:
            self.lbl_site.configure(text=self._t("site_ok", name=name),
                                    text_color=("#1a7f37", "#3fb950"))
        self._update_download_enabled()

    # ── エンジン版数（§6） ────────────────────────────────────
    def _load_engine_version(self):
        self._queue.put(("engine_ver", engine_version()))

    def _on_ui_lang(self, value: str):
        self.settings["ui_lang"] = "en" if value == "English" else "ja"
        self._apply_ui_lang()
        self._persist()

    def _apply_ui_lang(self):
        self.title(self._t("title"))
        self.lbl_url.configure(text=self._t("paste_url"))
        self.ent_url.configure(placeholder_text=self._t("url_ph"))
        if self._proc is None:
            self.btn_main.configure(text=self._t("download"))
        self.btn_open.configure(text=self._t("open_folder"))
        self.btn_open_epub.configure(text=self._t("open_epub"))
        self.btn_savelog.configure(text=self._t("save_log"))
        self.btn_sites.configure(text=self._t("sites"))
        self.btn_log.configure(text=self._t("hide_log" if self._log_open else "show_log"))
        self.btn_detail.configure(text=self._t("adv_open" if self._detail_open else "adv_closed"))
        self.lbl_outdir.configure(
            text=self._t("save_prefix") + str(self.settings.get("output_dir", "")))
        self.lbl_save.configure(text=self._t("outdir"))
        self.btn_outdir.configure(text=self._t("change"))
        self.lbl_cover.configure(text=self._t("cover"))
        self.rad_cover_auto.configure(text=self._t("cover_auto"))
        self.rad_cover_site.configure(text=self._t("cover_site"))
        self.rad_cover_file.configure(text=self._t("cover_file"))
        if not self._cover_image_path:
            self.var_cover_file.set(self._t("cover_none"))
        self.btn_cover_pick.configure(text=self._t("pick_image"))
        self.lbl_rarely.configure(text=self._t("rarely"))
        self.chk_horizontal.configure(text=self._t("horizontal"))
        self.chk_kobo.configure(text=self._t("kobo"))
        self.chk_toc.configure(text=self._t("toc_end"))
        self.lbl_font.configure(text=self._t("body_font"))
        if not self._font_path:
            self.var_font_name.set(self._t("font_default"))
        self.btn_font_pick.configure(text=self._t("pick"))
        self.btn_font_clear.configure(text=self._t("font_reset"))
        self.lbl_delay.configure(text=self._t("delay"))
        self.lbl_encoding.configure(text=self._t("encoding"))
        self.lbl_behavior.configure(text=self._t("behavior"))
        self.btn_add.configure(text=self._t("add"))
        self.lbl_queue_title.configure(text=self._t("queue_title"))
        self.btn_queue_clear.configure(text=self._t("queue_clear"))
        n_err = sum(1 for j in self._jobs if j["status"] == "error")
        if n_err:
            self.btn_retry.configure(text=self._t("retry_failed", n=n_err))
        if self._jobs:
            self._refresh_queue_list()
        self.chk_auto_paste.configure(text=self._t("auto_paste"))
        self.chk_open_on_done.configure(text=self._t("open_on_done"))
        if self._engine_ver:
            self.lbl_ver.configure(text=self._t("engine_ver", ver=self._engine_ver))
        # サイト判定バッジは言語に依存するので、判定済みなら出し直す
        if self._site_info is not None and self._site_info_url:
            self._apply_site_info(self._detect_seq, self._site_info_url, self._site_info)

    # ── 終了 ─────────────────────────────────────────────────
    def _unfinished_count(self) -> int:
        return sum(1 for j in self._jobs if j["status"] in ("waiting", "running"))

    def _on_close(self):
        # 未完了のキューがあるなら確認する（§7.12）。キューは保存しないので、
        # ここで黙って閉じると積んだものが消える
        n = self._unfinished_count()
        if n and not self._closing:
            try:
                if not messagebox.askokcancel(self._t("close_title"),
                                              self._t("confirm_close", n=n)):
                    return
            except Exception:
                pass    # ダイアログを出せない環境では止めない
        # 予約済みの after を止めてから閉じる。残っていると destroy 後に発火して
        # 「invalid command name」のトレースが stderr に出る
        self._closing = True
        try:
            self._detect_jobs_q.put(None)      # 判定スレッドを終わらせる
        except Exception:
            pass
        for attr in ("_poll_after", "_detect_after"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        # ウィンドウ位置・サイズを覚える（§6）。_persist より先に settings へ入れる。
        # 詳細設定・ログを開いたままの高さを覚えると、次回は閉じた状態なのに
        # 縦に間延びした窓で開いてしまうので、開いている分を差し引いてから保存する
        try:
            w, h = self._logical_size()
            # パネルを開いたままの高さを覚えると、次回は閉じた状態なのに
            # 縦に間延びした窓で開く。**固定値を引く方式はやめた**
            # （パネルに項目を足すと値がずれて破綻する）。
            # 何も開いていないときに記録しておいた高さを使う
            if self._detail_open or self._log_open or self._queue_shown:
                h = self._base_height or h
            geo = "%dx%d" % (w, max(MIN_HEIGHT_PX, h))
            m = re.search(r"([+-]\d+[+-]\d+)$", self.geometry())
            if m:
                geo += m.group(1)
            if _RE_GEOMETRY.match(geo):
                self.settings["window_geometry"] = geo
        except Exception:
            pass
        self._persist()
        _terminate_tree(self._proc)
        self.destroy()


def main():
    app = NovelDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
