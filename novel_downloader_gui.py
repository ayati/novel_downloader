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
import shutil
import subprocess
import tempfile
import webbrowser
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
# 受信箱・本棚（§8.3 / §8.4）も同じスクロール一覧なので QUEUE_* を共用する。
# 別の定数を建てても値が同じまま増えるだけで、ずれたときに理由が説明できない

# ジョブ種別 → 行頭の記号。本棚の「続きを取得」は kind="append"
_JOB_KIND_ICON = {"download": "", "append": "＋"}
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
# 受信箱・本棚は詳細設定と同じ「▸ 見出しを押すと開く」折りたたみ節（§8.5）。
# CTkTabview にしないのは、タブ化するとルートの winfo_reqheight が全タブの
# 最大になり、_fit_window の高さ配分が壊れるため（§8.0 (3)）
# 詳細ログは**補助ボタン行の直下**に置く。以前は詳細設定パネルより下にあり、
# 「詳細を表示」を押すと詳細設定の中（実際は下）に出ているように見えて、
# 何を開いたのか分からなかった（実機確認での指摘・§8.9）
ROW_LOG_BTN    = 8
ROW_LOG        = 9
ROW_GRIP       = 10
ROW_INBOX_BTN  = 11
ROW_INBOX      = 12
ROW_SHELF_BTN  = 13
ROW_SHELF      = 14
ROW_OUTDIR     = 15
ROW_DETAIL_BTN = 16
ROW_DETAIL     = 17

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
    "cover_font": ("表紙の文字", "Cover lettering"),
    "cover_font_default": ("標準（自動で選ぶ）", "Default (auto)"),
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
    "ft_cover_font": ("表紙用フォント", "Cover fonts"),
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
    "logsec_closed": ("▸ 📄 詳細ログ", "▸ 📄 Details"),
    "logsec_open":   ("▾ 📄 詳細ログ", "▾ 📄 Details"),
    "site_short": ("短縮URL — 開いてから判定します", "Short URL — will resolve on download"),
    # ── 受信箱（§8.3）──────────────────────────────────
    "inbox_closed": ("▸ 📥 受信箱", "▸ 📥 Inbox"),
    "inbox_open":   ("▾ 📥 受信箱", "▾ 📥 Inbox"),
    "inbox_count":  ("（{n}件）", " ({n})"),
    "inbox_reload": ("🔄 取り込む", "🔄 Import"),
    "inbox_pick":   ("フォルダを選ぶ", "Choose folder"),
    "inbox_nodir":  ("監視フォルダが未設定です。右の「フォルダを選ぶ」で指定してください。",
                     "No watch folder set. Use “Choose folder” on the right."),
    "inbox_empty":  ("新しいファイルはありません。", "No new files."),
    "inbox_nourl":  ("URL が見つかりません", "No URL found"),
    "inbox_have":   ("取得済み", "Already downloaded"),
    "inbox_checking": ("確認中…", "Checking…"),
    "inbox_fetch":  ("✅ 選んだ {n} 件を取得", "✅ Fetch {n} selected"),
    "inbox_fetch0": ("✅ 取得", "✅ Fetch"),
    "inbox_moved":  ("[受信箱] {name} を done へ移しました", "[inbox] moved {name} to done"),
    "inbox_movefail": ("[受信箱] {name} を移動できませんでした（次回に持ち越します）",
                       "[inbox] could not move {name} (will retry next time)"),
    "inbox_ng":     ("未対応のサイト", "Unsupported site"),
    "inbox_scanned": ("　最終確認 {t}", "  last checked {t}"),
    "inbox_scan_min": ("受信箱を見に行く間隔（分・0で無効）",
                       "Check the inbox every N minutes (0 = off)"),
    "inbox_auto":   ("受信箱に入った作品を自動で取得する",
                     "Automatically fetch works dropped into the inbox"),
    "inbox_dir":    ("受信箱フォルダ", "Inbox folder"),
    # ── 本棚（§8.4）────────────────────────────────────
    "shelf_closed": ("▸ 📚 本棚", "▸ 📚 Bookshelf"),
    "shelf_open":   ("▾ 📚 本棚", "▾ 📚 Bookshelf"),
    "shelf_count":  ("（{n}件）", " ({n})"),
    "shelf_count_new": ("（{n}件・新着{u}）", " ({n}, {u} updated)"),
    "shelf_refresh": ("一覧を更新", "Refresh list"),
    "sort_updated": ("更新が新しい順", "Recently updated"),
    "sort_name":    ("名前順", "By name"),
    "sort_episodes": ("話数が多い順", "Most episodes"),
    "shelf_check_stop": ("■ 中止", "■ Stop"),
    "shelf_check_stopping": ("中止しています…", "Stopping…"),
    "shelf_check_stopped": ("中止しました（{n} 件まで確認済み）",
                            "Stopped ({n} checked)"),
    "shelf_checking_now": ("確認中 {n}/{m}：{name}", "Checking {n}/{m}: {name}"),
    "shelf_row_checking": ("確認中…", "Checking…"),
    "shelf_row_error": ("確認できず", "Check failed"),
    "shelf_partial": ("部分（{n}番目から）", "Partial (from #{n})"),
    "tip_shelf_partial": ("途中から取得したファイルです。先頭が欠けているため"
                          "「続きを取得」は使えません。",
                          "Fetched from partway, so the beginning is missing. "
                          "“Get new episodes” is unavailable."),
    "ep_start_note": ("選んだ話から最新までを取得します（あとから続きの追記はできません）",
                      "Fetches from the selected episode to the latest "
                      "(appending more later is not possible)"),
    "tip_shelf_list": ("話の一覧を見る（手元のファイルから）",
                       "Show the episode list (from the local file)"),
    "tip_shelf_open": ("ePub を開く", "Open the EPUB"),
    "shelf_noepub": ("ePub がありません（テキストのみ）", "No EPUB (text only)"),
    "shelf_listing": ("一覧を読み込み中…", "Loading the episode list…"),
    "shelf_list_fail": ("一覧を読み込めませんでした。", "Could not load the episode list."),
    "shelf_list_title": ("{title} — 話の一覧", "{title} — Episodes"),
    "shelf_list_sub": ("手元に {n} 話　{author}", "{n} episodes here　{author}"),
    "shelf_last": ("最後の話: {t}", "Last episode: {t}"),
    "inbox_list_sub": ("サイトに {n} 話　{author}", "{n} episodes on the site　{author}"),
    "ep_open_site": ("🔗 元サイトを開く", "🔗 Open on the site"),
    "ep_pick_hint": ("行を選ぶと ここから取得", "Pick a line to fetch from"),
    "ep_start_from": ("⬇ {n} 番目から取得", "⬇ Fetch from #{n}"),
    "q_from": ("（{n} 番目から）", " (from #{n})"),
    "tip_inbox_list": ("話の一覧を見る（サイトに問い合わせます）",
                       "Show the episode list (queries the site)"),
    "tip_inbox_have": ("取得済みです。一覧は本棚から見られます",
                       "Already downloaded — see the list in the bookshelf"),
    "shelf_check":  ("🔄 新着チェック", "🔄 Check for updates"),
    "shelf_checking": ("確認中 {n}/{m}…", "Checking {n}/{m}…"),
    "shelf_empty":  ("保存先にダウンロード済みの作品がありません。",
                     "No downloaded works in the output folder."),
    "shelf_new":    ("🆕 +{n}", "🆕 +{n}"),
    "shelf_latest": ("最新", "Up to date"),
    "shelf_unknown": ("未チェック", "Not checked"),
    "shelf_append": ("続きを取得", "Get new episodes"),
    "shelf_append_all": ("✅ 新着のある {n} 件をまとめて取得", "✅ Get updates for {n} works"),
    "shelf_eps":    ("{n}話", "{n} eps"),
    "shelf_busy":   ("ダウンロード中はチェックできません。", "Cannot check while downloading."),
    "no_images":    ("挿絵を取り込まない", "Skip inline illustrations"),
    "notify_taskbar": ("終わったらタスクバーを光らせる（窓を見ていないときだけ）",
                       "Flash the taskbar when finished (only while unfocused)"),
    "notify_sound": ("終わったら音を鳴らす", "Play a sound when finished"),
    "notice_done_one": ("✅ 完了", "✅ Done"),
    "notice_done":  ("✅ {n} 件完了", "✅ {n} done"),
    "notice_mixed": ("✅ {ok} 件 / ⚠ {ng} 件", "✅ {ok} / ⚠ {ng}"),
    "notice_failed": ("⚠ 失敗", "⚠ Failed"),
    "notice_new":   ("🆕 新着 {n} 件", "🆕 {n} updated"),
    "notice_nonew": ("新着なし", "No updates"),
    "notice_inbox": ("📥 受信箱から {n} 件を取得中", "📥 Fetching {n} from the inbox"),
    "notify_webhook": ("完了・新着を Webhook で知らせる（Discord / Slack）",
                       "Notify on completion and updates via webhook (Discord / Slack)"),
    "webhook_ph":   ("https://discord.com/api/webhooks/…",
                     "https://discord.com/api/webhooks/…"),
    "webhook_need_url": ("宛先の URL を入れると送られるようになります",
                         "Enter the webhook URL to start sending"),
    "shelf_scan_fail": ("本棚を読み込めませんでした。もう一度お試しください。",
                        "Could not read the bookshelf. Please try again."),
    "inbox_need_shelf": ("本棚を読めなかったため、取得済みかどうかを判定できませんでした。",
                         "Could not read the bookshelf, so downloaded works cannot be identified."),
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


# エンジンへ渡す表示言語（design_gui_v2 §8.13）。_engine_env() は _run_capture の
# ようなモジュール関数からも呼ばれて設定 dict に手が届かないため、
# アプリ側が言語を変えるたびにここへ反映する。
_ENGINE_LANG = "ja"


def set_engine_lang(lang: str) -> None:
    """以後起動するエンジンの表示言語を決める。"""
    global _ENGINE_LANG
    _ENGINE_LANG = "en" if lang == "en" else "ja"


def _engine_env() -> dict:
    """エンジン起動用の環境変数。ライブ進捗と UTF-8 出力を保証（§9.3 / §2.3）。"""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"   # ライブ進捗（バッファさせない）
    env["PYTHONUTF8"] = "1"         # 日本語出力を UTF-8 に固定
    env["PYTHONIOENCODING"] = "utf-8"
    # **エンジン側の表示言語。** これが無いと GUI を English にしてもエンジンは
    # 日本語のままで、_error_detail() が stderr から拾ってステータス行に出す
    # 失敗理由だけが日本語になる（§8.13）。--lang より環境変数を使うのは、
    # ダウンロード以外（--detect-site / --shelf-scan / --check-update-dir）にも
    # まとめて効かせるため
    env["NOVEL_DOWNLOADER_LANG"] = _ENGINE_LANG
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


def normalize_webhook(s: dict) -> dict:
    """Webhook 設定の**書式だけ**整えて返す（design_gui_v2 §8.13a）。

    **「通知には宛先が要る」をここで適用してはいけない。** 以前はここで
    「URL が空なら notify を False に戻す」「URL 形式が違えば空にする」を
    やっていたが、これは**画面の状態に制約をかけてしまう**:

      チェックを入れる → URL がまだ空 → notify が False に戻る →
      チェックが即座に外れる → URL 欄が disabled のまま → URL を入れられない

    URL が無いと有効にできず、有効にしないと URL を入れられない詰みだった
    （実機で踏んだ）。**利用可能かどうかの判断は `webhook_ready()` に置き、
    CLI 引数を組む瞬間にだけ効かせる。** 入力中の値は勝手に消さない。
    """
    if s.get("webhook_format") not in ("discord", "slack"):
        s["webhook_format"] = "discord"
    s["webhook_url"] = str(s.get("webhook_url") or "").strip()
    s["notify_webhook"] = bool(s.get("notify_webhook"))
    return s


def webhook_ready(s: dict) -> bool:
    """Webhook 通知を実際に使える状態か（チェック済み＋宛先が http(s)）。"""
    return bool(s.get("notify_webhook")) and \
        str(s.get("webhook_url") or "").startswith(("http://", "https://"))


def default_settings() -> dict:
    return {
        "schema": SETTINGS_SCHEMA,
        "output_dir": default_output_dir(),
        "cover_mode": "auto",          # "auto" | "site" | "file"
        "cover_image_path": "",
        "cover_font_path": "",         # おまかせ表紙の題名・著者名のフォント（--cover-font）
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
        # design_gui_v2 §8.6
        "inbox_dir": "",               # 受信箱の監視フォルダ（既定なし・§8.3）
        "inbox_auto": False,           # 取り込んだ作品を自動取得する（既定 OFF・§8.3）
        "inbox_scan_min": 5,           # 受信箱を見に行く間隔（分・0 で無効・§8.10）
        "inbox_open": False,           # 受信箱の節を開いた状態で起動する
        "shelf_open": False,           # 本棚の節を開いた状態で起動する
        # design_gui_v2 §8.17。表示の並び順＝新着チェックの確認順
        "shelf_sort": "updated",       # "updated" | "name" | "episodes"
        # design_gui_v2 §8.18。窓を見ていないときだけ知らせる
        "notify_taskbar": True,        # タスクバーを点滅させる
        "notify_sound": False,         # 音を鳴らす（好みが割れるので既定 OFF）
        # design_gui_v2 §8.13
        "no_inline_images": False,     # 本文中の挿絵を取り込まない（避難口）
        "notify_webhook": False,       # 完了・新着を Webhook で通知する
        "webhook_url": "",             # Discord / Slack の Incoming Webhook URL
        "webhook_format": "discord",   # "discord" | "slack"
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
    if s.get("cover_font_path") and not os.path.isfile(s["cover_font_path"]):
        s["cover_font_path"] = ""      # 無くなっていれば自動で選ぶ表紙フォントへ
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
    if s.get("shelf_sort") not in ("updated", "name", "episodes"):
        s["shelf_sort"] = "updated"
    for k in ("inbox_auto", "inbox_open", "shelf_open",
              "no_inline_images", "notify_webhook", "notify_sound"):
        s[k] = bool(s.get(k, False))
    s["notify_taskbar"] = bool(s.get("notify_taskbar", True))
    normalize_webhook(s)
    try:
        s["inbox_scan_min"] = max(0, min(int(s.get("inbox_scan_min", 5)), 1440))
    except Exception:
        s["inbox_scan_min"] = 5
    # **inbox_dir は存在しなくても消さない。** 外付け・クラウドが未マウントの
    # ままで起動すると一時的に見えないだけで、ここで空にすると次の _persist() が
    # その空を保存してしまい**設定が永久に失われる**。使えるかどうかは
    # 走査の直前（_inbox_maybe_scan / _inbox_reload）で見る
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


def canon_url(url: str) -> str:
    """重複判定用に URL を畳む（design_gui_v2 §8.12）。

    エンジンの `_find_txt_by_url` は `rstrip("/")` して比べている。GUI 側も
    揃えないと、**末尾スラッシュの有無や大文字の ncode だけで「未取得」に化け**、
    自動取得が既にある作品を第1話から落とし直して `.txt` を上書きする。

    対応 17 サイトの作品 ID は数字・16進・なろうの ncode（大小区別なし）で、
    大小で別作品になるものが無いため、まるごと小文字化してよい。
    """
    return (url or "").strip().rstrip("/").lower()


def is_unsupported(info) -> bool:
    """`--detect-site` の結果が「確かに未対応」かを返す（design_gui_v2 §8.8）。

    **`site is None` だけで未対応と決めてはいけない。** `--detect-site` は
    オフライン契約なので短縮URL（`share.google/…` 等）の先を判定できず、
    必ず `site: null` を返す。エンジン本体は `expand_short_url()` で展開できるので、
    ここで弾くと**実際には落とせる URL をエンジンを起動する前に捨てる**ことになる
    （§3.4 でハーメルンについて直したのと同じ失敗）。
    """
    if not info:
        return True
    return info.get("site") is None and not info.get("short_url")


def _webhook_args(s: dict) -> list:
    """Webhook 通知の CLI 引数を返す（design_gui_v2 §8.13）。

    宛先が空のまま `--notify webhook` を渡すとエンジンが起動直後に
    parser.error で落ちるので、**URL が揃っているときだけ**渡す。
    ここが「通知には宛先が要る」を効かせる唯一の場所（§8.13a）。
    """
    if not webhook_ready(s):
        return []
    return ["--notify", "webhook",
            "--webhook-url", s["webhook_url"],
            "--webhook-format", s.get("webhook_format", "discord")]


def shelf_scan(dir_path: str, timeout=180) -> list:
    """--shelf-scan を呼び本棚の行リストを返す。失敗時 []（design_gui_v2 §8.1b）。

    青空文庫書式の解析を GUI 側に持たないのが要点。話数のカウントは
    区切り線・改ページ・奥付切り落としの合わせ技で、書式が変わると黙ってずれる。
    既定のタイムアウトが長いのは、1 作品 4MB 級の .txt を全部読むため。
    """
    try:
        out = _run_capture(["--shelf-scan", dir_path], timeout=timeout)
        line = [ln for ln in out.splitlines() if ln.strip()][-1]
        rows = json.loads(line)
        return rows if isinstance(rows, list) else None
    except Exception:
        # **失敗は None。空リストを返してはいけない**（design_gui_v2 §8.12）。
        # 呼び出し側が「本棚は空」と解釈すると、受信箱の重複判定が全滅し、
        # 自動取得が取得済みの作品を丸ごと落とし直す
        return None


# 受信箱のファイルは「URL を書いたメモ」なので、これを超えるものは読まない。
# 監視フォルダにはスクリーンショット等の巻き添えファイルが普通に入る（実例あり）
INBOX_MAX_BYTES = 1 << 20      # 1MiB


def read_text_any(path: str) -> str:
    """受信箱のファイルを読む。UTF-8（BOM 可）→ cp932 の順（design_gui_v2 §8.3）。

    スマホから投げたメモは UTF-8 が通常だが、Windows のメモ帳由来は cp932 がある。

    **画像などのバイナリを読まされる前提で書くこと。** 監視フォルダには
    スクリーンショットが一緒に置かれることがあり、cp932 は多くのバイト列を
    黙って復号してしまうので、NUL を含む結果はテキストでないとみなして捨てる。
    """
    try:
        if os.path.getsize(path) > INBOX_MAX_BYTES:
            return ""
    except OSError:
        return ""
    for enc in ("utf-8-sig", "cp932"):
        try:
            with open(path, "r", encoding=enc) as f:
                text = f.read()
        except (UnicodeDecodeError, LookupError):
            continue
        except OSError:
            return ""
        return "" if "\x00" in text else text
    return ""


def dry_run_info(url: str, timeout=180) -> dict:
    """`--dry-run --progress-json` を叩いて workinfo を返す。失敗時 {}。

    受信箱が「出先で投げた URL が何の作品か」を取得前に見せるために使う
    （design_gui_v2 §8.3）。**人間向け表示は読まない。** workinfo イベントは
    そのために足したもの（design_progress_json.md §3.1）。
    """
    try:
        out = _run_capture([url, "--dry-run", "--progress-json"], timeout=timeout)
    except Exception:
        return {}
    info = {}
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except Exception:
            continue
        if ev.get("event") == "workinfo":
            info = ev
    return info


def _row_recency(row) -> float:
    """本棚の 1 行の「新しさ」を秒で返す（エンジンの `_txt_recency` と同じ基準）。

    サイト側の `更新日` を優先し、**無ければファイルの更新時刻で代用する**。
    日付文字列と mtime を別要素のタプルで比べると、更新日を持たないサイトが
    常に最後へ回って代用にならない。同じ尺度に載せて比べる。
    """
    upd = str((row.get("meta") or {}).get("updated") or "")
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return time.mktime(time.strptime(upd[:n], fmt))
        except Exception:
            continue
    try:
        return float(row.get("mtime") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def flash_taskbar(window) -> bool:
    """タスクバーのボタンを点滅させる（Windows のみ・依存ゼロ・§8.18）。

    Windows 標準の「終わりました」の出し方。**ウィンドウを前面に引き出さない**ので
    作業の邪魔をしない。完了時にフォルダを開く（`open_folder_on_done`）が
    フォーカスを奪うのとは対照的。

    他の OS では何もせず False を返す。ここで失敗してもアプリを止めない
    （通知が出ないだけで、やるべきことは終わっている）。
    """
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                        ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                        ("dwTimeout", wintypes.DWORD)]

        # タスクバーのボタンは Tk の子ウィンドウではなく WM のフレームが持つので、
        # winfo_id() ではなく wm_frame() を優先する
        hwnd = 0
        try:
            hwnd = int(window.wm_frame(), 16)
        except Exception:
            hwnd = int(window.winfo_id())
        FLASHW_ALL, FLASHW_TIMERNOFG = 0x03, 0x0C
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), wintypes.HWND(hwnd),
                          FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
        return bool(ctypes.windll.user32.FlashWindowEx(ctypes.byref(info)))
    except Exception:
        return False


def open_external_url(url: str) -> bool:
    """作品ページをブラウザで開く。**http(s) 以外は開かない**（§8.16）。

    ここに来る URL は `.txt` の `底本URL：` や受信箱のメモ由来で、こちらが
    作った値ではない。`file://` や `javascript:` をブラウザに渡さないための門で、
    `_open_epub_path()` の拡張子ゲートと同じ考え方。
    """
    if not str(url or "").lower().startswith(("http://", "https://")):
        return False
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def episode_list(target: str, from_file: bool = False, timeout=300) -> dict:
    """`--list-only` の `episodes` イベントを返す。失敗時 {}（§8.15）。

    `from_file=True` なら手元の `.txt` を読むだけで**通信しない**。本棚の
    一覧はこちらを使う。人間向けの表示は読まない（`workinfo` と同じ理由）。
    """
    args = (["--from-file", target] if from_file else [target])
    args += ["--list-only", "--progress-json"]
    try:
        out = _run_capture(args, timeout=timeout)
    except Exception:
        return {}
    info = {}
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except Exception:
            continue
        if ev.get("event") == "episodes":
            info = ev
    return info


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
        # ── 受信箱・本棚（design_gui_v2 §8）──
        self._shelf = []               # --shelf-scan の行（そのまま保持）
        self._shelf_new = {}           # path → checkresult（新着チェックの結果）
        self._shelf_open = False
        self._shelf_loaded = False     # 一度でも走査したか（開いた時に初回だけ走らせる）
        self._shelf_scanning = False
        self._shelf_proc = None        # 新着チェックのプロセス（終了時に殺す）
        self._shelf_rows = []
        self._shelf_dirty = False      # 追記・DL でずれたので走査し直したい（キュー終了後）
        self._shelf_dir_mtime = None   # 走査した時点の出力先フォルダの更新時刻
        self._shelf_listing = False    # 話一覧を読み込み中（§8.15）
        self._shelf_checking = ""      # いま確認中の作品のパス（§8.17）
        self._shelf_stop = False       # 新着チェックの中止要求
        self._focused = True           # 窓を見ているか（§8.18）
        self._notice = ""              # タイトルに出している結果
        self._shelf_chk_done = 0       # checkresult の到着数（§8.2: stage は使わない）
        self._shelf_chk_total = 0
        self._h_before_shelf = 0
        self._inbox = []               # 受信箱の行（URL 1 本 = 1 行）
        self._inbox_open = False
        self._inbox_scanning = False
        self._inbox_rows = []
        self._inbox_after = None       # 定期スキャンの予約（§8.10）
        self._inbox_last_scan = 0.0    # 直近に走査した時刻（フォーカス連打よけ）
        self._inbox_pending = False    # 本棚の走査待ちで保留中
        self._inbox_tried = set()      # 自動取得を一度試したファイル（無限再試行よけ）
        self._inbox_listing = False    # 話一覧を読み込み中（§8.15）
        self._h_before_inbox = 0

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
        self.bind("<FocusOut>", self._on_focus_out, add="+")

        # 起動時クリップボード自動入力（別スレッドで判定・§7.2）
        self._maybe_autofill_from_clipboard()
        # エンジンの版を名乗らせる（exe 起動を伴うので別スレッド・§6）
        threading.Thread(target=self._load_engine_version, daemon=True).start()
        # 受信箱・本棚の開閉状態を復元する（§8.5）。ウィジェットが揃ってから
        # 走らせたいので after(0) 越しにする
        self.after(0, self._restore_panels)
        # 受信箱の監視（§8.10）。節の開閉に関係なく、起動時に 1 回見てから周期に入る
        self.after(0, self._inbox_boot)
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
        self.btn_savelog = ctk.CTkButton(self.frm_aux, text="📄 ログを保存",
                                         width=110, fg_color="gray30",
                                         command=self._save_log)
        self.btn_retry = ctk.CTkButton(self.frm_aux, text="", width=150,
                                       command=self._retry_failed)

        # 受信箱・本棚の折りたたみ節（§8.3 / §8.4）
        self._build_inbox_panel()
        self._build_shelf_panel()

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
        # 詳細ログの折りたたみ見出し（§8.9）。受信箱・本棚・詳細設定と同じ意匠に
        # して「開いたものが何か」を見た目で分かるようにする。ログがあるときだけ出す
        self.btn_logsec = self._section_button(ROW_LOG_BTN, self._toggle_log)
        self.btn_logsec.grid_remove()

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
        self.rad_cover_site.grid(row=5, column=0, sticky="w", padx=24, pady=1)
        self.rad_cover_file.grid(row=6, column=0, sticky="w", padx=24, pady=1)

        # おまかせ表紙の題名・著者名のフォント（--cover-font）。表紙を自動で
        # 作るときにしか意味が無いので「おまかせ」の直下に置き、他では押せなくする
        self.frm_cover_font = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        self.frm_cover_font.grid(row=4, column=0, sticky="w", padx=(52, 24))
        self._cover_font_path = ""
        self.lbl_cover_font = ctk.CTkLabel(self.frm_cover_font, text="表紙の文字")
        self.lbl_cover_font.pack(side="left")
        self.var_cover_font_name = ctk.StringVar(value="標準（自動で選ぶ）")
        self.lbl_cover_font_name = ctk.CTkLabel(self.frm_cover_font,
                                                textvariable=self.var_cover_font_name,
                                                text_color="gray")
        self.lbl_cover_font_name.pack(side="left", padx=(8, 0))
        self.btn_cover_font_pick = ctk.CTkButton(self.frm_cover_font, text="選ぶ", width=56,
                                                 command=self._pick_cover_font)
        self.btn_cover_font_pick.pack(side="left", padx=(8, 0))
        self.btn_cover_font_clear = ctk.CTkButton(self.frm_cover_font, text="標準に戻す",
                                                  width=84, fg_color="gray40",
                                                  command=self._clear_cover_font)
        self.btn_cover_font_clear.pack(side="left", padx=(6, 0))

        self.frm_cover_file = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        self.frm_cover_file.grid(row=7, column=0, sticky="ew", padx=24)
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
        self.lbl_behavior.grid(row=8, column=0, sticky="ew", padx=12, pady=(12, 0))
        beh = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        beh.grid(row=9, column=0, sticky="ew", padx=24)
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
        # 受信箱を見に行く間隔（§8.10）。0 で監視を止められるようにしておく
        scanbox = ctk.CTkFrame(beh, fg_color="transparent")
        scanbox.grid(row=2, column=0, sticky="w", pady=(4, 1))
        self.lbl_inbox_scan = ctk.CTkLabel(scanbox, text="", anchor="w")
        self.lbl_inbox_scan.pack(side="left")
        self.var_inbox_scan = ctk.StringVar(value="5")
        self.ent_inbox_scan = ctk.CTkEntry(scanbox, textvariable=self.var_inbox_scan,
                                           width=60)
        self.ent_inbox_scan.pack(side="left", padx=(8, 0))
        # Entry には command が無いので、確定の契機を自前で拾う
        self.ent_inbox_scan.bind("<Return>", self._on_inbox_scan_changed, add="+")
        self.ent_inbox_scan.bind("<FocusOut>", self._on_inbox_scan_changed, add="+")

        # Webhook 通知（§8.13）。エンジンは前から対応していたが GUI から設定できず、
        # 完了・新着を手元のスマホへ飛ばす手段が GUI 利用者だけ無かった
        self.var_notify = ctk.BooleanVar(value=False)
        self.chk_notify = ctk.CTkCheckBox(beh, text="", variable=self.var_notify,
                                          command=self._on_notify_changed)
        self.chk_notify.grid(row=3, column=0, sticky="w", pady=(6, 1))
        # 知らせ方（§8.18）。窓を見ていないときだけ光る／鳴る
        self.var_flash = ctk.BooleanVar(value=True)
        self.chk_flash = ctk.CTkCheckBox(beh, text="", variable=self.var_flash,
                                         command=self._persist)
        self.chk_flash.grid(row=5, column=0, sticky="w", pady=(6, 1))
        self.var_sound = ctk.BooleanVar(value=False)
        self.chk_sound = ctk.CTkCheckBox(beh, text="", variable=self.var_sound,
                                         command=self._persist)
        self.chk_sound.grid(row=6, column=0, sticky="w", pady=1)
        whbox = ctk.CTkFrame(beh, fg_color="transparent")
        whbox.grid(row=4, column=0, sticky="ew", padx=(24, 0))
        whbox.grid_columnconfigure(0, weight=1)
        self.var_webhook_url = ctk.StringVar()
        self.ent_webhook = ctk.CTkEntry(whbox, textvariable=self.var_webhook_url,
                                        placeholder_text="https://discord.com/api/webhooks/…")
        self.ent_webhook.grid(row=0, column=0, sticky="ew")
        self.ent_webhook.bind("<Return>", self._on_notify_changed, add="+")
        self.ent_webhook.bind("<FocusOut>", self._on_notify_changed, add="+")
        self._attach_context_menu(self.ent_webhook)
        self.var_webhook_fmt = ctk.StringVar(value="discord")
        self.opt_webhook_fmt = ctk.CTkOptionMenu(
            whbox, values=["discord", "slack"], variable=self.var_webhook_fmt,
            width=100, command=lambda *_: self._on_notify_changed())
        self.opt_webhook_fmt.grid(row=0, column=1, padx=(8, 0))
        # 「チェックは入っているが宛先が無いので送られない」を黙らせない
        self.lbl_webhook_hint = ctk.CTkLabel(whbox, text="", anchor="w",
                                             text_color=("#8a6d00", "#e3b341"),
                                             font=ctk.CTkFont(size=11))
        self.lbl_webhook_hint.grid(row=1, column=0, columnspan=2, sticky="w",
                                   pady=(2, 0))
        self.lbl_webhook_hint.grid_remove()

        sep = ctk.CTkFrame(self.frm_detail, height=1, fg_color="gray70")
        sep.grid(row=10, column=0, sticky="ew", padx=12, pady=10)
        self.lbl_rarely = ctk.CTkLabel(self.frm_detail, text="ここから下は普段は変更不要",
                                       text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_rarely.grid(row=11, column=0, sticky="w", padx=12)

        opt = ctk.CTkFrame(self.frm_detail, fg_color="transparent")
        opt.grid(row=12, column=0, sticky="ew", padx=12, pady=(2, 12))
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
        self.chk_toc.grid(row=1, column=0, sticky="w", pady=2)
        # 挿絵の取得はサイト側の作りに依存するので、壊れたときの避難口を
        # GUI からも触れるようにする（CLI に逃げられない利用者ほど必要・§8.13）
        self.var_no_images = ctk.BooleanVar(value=False)
        self.chk_no_images = ctk.CTkCheckBox(opt, text="挿絵を取り込まない",
                                             variable=self.var_no_images,
                                             command=self._persist)
        self.chk_no_images.grid(row=1, column=1, sticky="w", padx=(16, 0), pady=2)

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

    # ══════════════════════════════════════════
    #  受信箱（§8.3）と本棚（§8.4）
    # ══════════════════════════════════════════
    # どちらも「▸ 見出しを押すと開く」折りたたみ節で、詳細設定とまったく同じ
    # 作りにしてある。CTkTabview にしないのは §8.0 (3) の理由（タブ化すると
    # ルートの winfo_reqheight が全タブの最大になり _fit_window が壊れる）。

    def _section_button(self, row: int, command):
        """折りたたみ節の見出しボタン（詳細設定と同じ意匠）。"""
        btn = ctk.CTkButton(
            self, text="", anchor="w",
            fg_color=("gray90", "gray25"), text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray35"), cursor="hand2", command=command)
        btn.grid(row=row, column=0, sticky="ew", padx=16, pady=(4, 0))
        return btn

    def _build_inbox_panel(self):
        self.btn_inbox = self._section_button(ROW_INBOX_BTN, self._toggle_inbox)

        self.frm_inbox = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_inbox.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self.frm_inbox, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        self.lbl_inbox_status = ctk.CTkLabel(head, text="", anchor="w",
                                             text_color="gray", wraplength=330,
                                             justify="left",
                                             font=ctk.CTkFont(size=11))
        self.lbl_inbox_status.grid(row=0, column=0, sticky="ew")
        self.btn_inbox_reload = ctk.CTkButton(head, text="", width=104, height=24,
                                              command=self._inbox_reload)
        self.btn_inbox_reload.grid(row=0, column=1, sticky="e", padx=(6, 0))
        self.btn_inbox_pick = ctk.CTkButton(head, text="", width=112, height=24,
                                            fg_color="gray40",
                                            command=self._pick_inbox_dir)
        self.btn_inbox_pick.grid(row=0, column=2, sticky="e", padx=(6, 0))
        # どのフォルダを見ているのかは画面に出しておかないと分からない。
        # 一覧の幅を食わないようツールチップにする
        _Tooltip(self.btn_inbox_pick,
                 lambda: "%s: %s" % (self._t("inbox_dir"),
                                     self.settings.get("inbox_dir") or "—"))

        self.frm_inbox_list = ctk.CTkScrollableFrame(self.frm_inbox, height=QUEUE_LIST_PX)
        self.frm_inbox_list.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.frm_inbox_list.grid_columnconfigure(1, weight=1)

        foot = ctk.CTkFrame(self.frm_inbox, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        foot.grid_columnconfigure(0, weight=1)
        self.var_inbox_auto = ctk.BooleanVar(value=False)
        self.chk_inbox_auto = ctk.CTkCheckBox(foot, text="", variable=self.var_inbox_auto,
                                              command=self._persist)
        self.chk_inbox_auto.grid(row=0, column=0, sticky="w")
        self.btn_inbox_fetch = ctk.CTkButton(foot, text="", height=28,
                                             command=self._inbox_fetch_selected)
        self.btn_inbox_fetch.grid(row=0, column=1, sticky="e")

    def _build_shelf_panel(self):
        self.btn_shelf = self._section_button(ROW_SHELF_BTN, self._toggle_shelf)

        self.frm_shelf = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_shelf.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self.frm_shelf, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        self.lbl_shelf_status = ctk.CTkLabel(head, text="", anchor="w",
                                             text_color="gray", wraplength=330,
                                             justify="left",
                                             font=ctk.CTkFont(size=11))
        self.lbl_shelf_status.grid(row=0, column=0, sticky="ew")
        # 一覧の読み直し（手元のフォルダを見るだけ・オフライン）。
        # 「新着チェック」はサイトへ問い合わせる別の操作なので、絵文字を重ねず
        # 文言で区別する（§8.14）
        # 並び順（表示＝確認順）。新着が出やすいものを先に確認できる（§8.17）
        self.var_shelf_sort = ctk.StringVar(value=self._t("sort_updated"))
        self.opt_shelf_sort = ctk.CTkOptionMenu(
            head, values=[], width=100, height=24,
            variable=self.var_shelf_sort, command=self._on_shelf_sort_pick)
        self.opt_shelf_sort.grid(row=0, column=1, sticky="e", padx=(6, 0))
        self.btn_shelf_reload = ctk.CTkButton(head, text="", width=92, height=24,
                                              fg_color="gray40",
                                              command=self._shelf_reload)
        self.btn_shelf_reload.grid(row=0, column=2, sticky="e", padx=(6, 0))
        self.btn_shelf_check = ctk.CTkButton(head, text="", width=124, height=24,
                                             command=self._shelf_check_updates)
        self.btn_shelf_check.grid(row=0, column=3, sticky="e", padx=(6, 0))

        self.frm_shelf_list = ctk.CTkScrollableFrame(self.frm_shelf, height=QUEUE_LIST_PX)
        self.frm_shelf_list.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.frm_shelf_list.grid_columnconfigure(1, weight=1)

        self.btn_shelf_all = ctk.CTkButton(self.frm_shelf, text="", height=28,
                                           command=self._shelf_append_all)
        self.btn_shelf_all.grid(row=2, column=0, sticky="e", pady=(4, 0))
        self.btn_shelf_all.grid_remove()

    def _restore_panels(self):
        """保存された開閉状態を復元する（§8.5）。"""
        if self.settings.get("inbox_open"):
            self._toggle_inbox()
        if self.settings.get("shelf_open"):
            self._toggle_shelf()
        self._sync_inbox_header()
        self._sync_shelf_header()

    # ── 開閉 ─────────────────────────────────────────────────
    def _toggle_inbox(self):
        self._inbox_open = not self._inbox_open
        if self._inbox_open:
            self._h_before_inbox = self._logical_size()[1]
            self.frm_inbox.grid(row=ROW_INBOX, column=0, sticky="ew",
                                padx=16, pady=(2, 6))
            self._fit_window(grow_only=True)
            if not self._inbox and not self._inbox_scanning:
                self._inbox_reload()
        else:
            self.frm_inbox.grid_forget()
            self._fit_window(restore_to=self._h_before_inbox)
        self._sync_inbox_header()
        self._persist()

    def _toggle_shelf(self):
        self._shelf_open = not self._shelf_open
        if self._shelf_open:
            self._h_before_shelf = self._logical_size()[1]
            self.frm_shelf.grid(row=ROW_SHELF, column=0, sticky="ew",
                                padx=16, pady=(2, 6))
            self._fit_window(grow_only=True)
            if self._shelf_stale() and not self._shelf_scanning:
                self._shelf_reload()
        else:
            self.frm_shelf.grid_forget()
            self._fit_window(restore_to=self._h_before_shelf)
        self._sync_shelf_header()
        self._persist()

    # ══════════════════════════════════════════
    #  本棚
    # ══════════════════════════════════════════
    def _shelf_works(self) -> list:
        """本棚に出す行（＝底本URL を持つ .txt）だけを返す。

        `--shelf-scan` は URL の無い .txt も返してくる（ユーザーが保存先に
        置いた無関係なテキスト）。**出すかどうかは GUI 側の判断**（§8.1b）。
        """
        return [r for r in self._shelf if r.get("url")]

    @staticmethod
    def _recency(row) -> float:
        return _row_recency(row)

    def _shelf_sorted_works(self) -> list:
        """本棚に出す順番（§8.17）。**この並びがそのまま確認順になる。**

        既定は更新日の新しい順。新着が出やすい作品が先に確認され、
        待っている間に結果が出はじめる。サイト側の更新日が無ければ
        ファイルの更新時刻で代用する。
        """
        works = self._shelf_works()
        mode = self.settings.get("shelf_sort", "updated")
        if mode == "name":
            # **ファイル名で並べる。** エンジン側の `name` は
            # sorted(glob("*.txt")) すなわちファイル名順なので、題名で並べると
            # 表示と確認順がずれる（題名とファイル名は safe_filename や -o で
            # 別々に決まりうる）
            return sorted(works, key=lambda r: r.get("file", "").lower())
        if mode == "episodes":
            return sorted(works, key=lambda r: int(r.get("episodes") or 0),
                          reverse=True)
        return sorted(works, key=_row_recency, reverse=True)

    _SORT_KEYS = ("updated", "name", "episodes")

    def _sort_labels(self) -> list:
        return [self._t("sort_" + k) for k in self._SORT_KEYS]

    def _on_shelf_sort_pick(self, value=None):
        """選ばれた表示名からキーを引く（表示名は言語で変わる）。"""
        labels = self._sort_labels()
        key = self._SORT_KEYS[labels.index(value)] if value in labels else "updated"
        self.settings["shelf_sort"] = key
        self._persist()
        self._refresh_shelf_list()

    def _sync_shelf_sort_widget(self):
        self.opt_shelf_sort.configure(values=self._sort_labels())
        key = self.settings.get("shelf_sort", "updated")
        self.var_shelf_sort.set(self._t("sort_" + key))

    @staticmethod
    def _shelf_partial_from(row) -> int:
        """途中から取得したファイルなら開始位置、そうでなければ 0（§8.19）。

        先頭が欠けているので「既存の節数＝取得済みの話数」が成り立たず、
        `--append` は**サイト側の先頭から**継ぎ足して重複・順序崩れを起こす。
        本棚では印を付けて「続きを取得」を押せなくする。
        """
        try:
            return int((row.get("meta") or {}).get("start_offset") or 0)
        except (TypeError, ValueError):
            return 0

    def _shelf_new_count(self) -> int:
        # 部分取得のファイルは数に入れない。追記できないので「新着あり」と
        # 数えても押せるボタンが無い（§8.19）
        return sum(1 for r in self._shelf_works()
                   if (self._shelf_new.get(r["path"]) or {}).get("new", 0) > 0
                   and not self._shelf_partial_from(r))

    def _sync_shelf_header(self):
        n = len(self._shelf_works())
        u = self._shelf_new_count()
        label = self._t("shelf_open" if self._shelf_open else "shelf_closed")
        if u:
            label += self._t("shelf_count_new", n=n, u=u)
        elif n or self._shelf_loaded:
            label += self._t("shelf_count", n=n)
        self.btn_shelf.configure(text=label)
        self._sync_shelf_sort_widget()
        self.btn_shelf_reload.configure(text=self._t("shelf_refresh"))
        self.btn_shelf_check.configure(text=self._t("shelf_check"))

    def _output_dir_mtime(self):
        """出力先フォルダの更新時刻。取れなければ None。"""
        try:
            return os.stat(self.settings.get("output_dir", "")).st_mtime
        except OSError:
            return None

    def _shelf_stale(self) -> bool:
        """本棚の表示が実体とずれている可能性があるか（§8.14）。

        一度読んだら二度と読み直さない作りだったため、**節を閉じて開き直しても
        更新されなかった**。ダウンロード後の `_shelf_dirty` に加えて、
        フォルダ自体の更新時刻も見る。CLI で落とした・別のPCから同期された・
        手で消した、のいずれもここで拾える（中身の書き換えは mtime が動かないが、
        それは追記後の `_shelf_dirty` が受け持つ）。
        """
        if not self._shelf_loaded or self._shelf_dirty:
            return True
        now = self._output_dir_mtime()
        return now is None or now != self._shelf_dir_mtime

    def _shelf_reload(self):
        """--shelf-scan を別スレッドで叩いて一覧を作り直す。"""
        if self._shelf_scanning:
            return
        d = self.settings.get("output_dir", "")
        self._shelf_scanning = True
        self.lbl_shelf_status.configure(text=self._t("inbox_checking"))
        threading.Thread(target=self._shelf_scan_worker, args=(d,), daemon=True).start()

    def _shelf_scan_worker(self, d: str):
        rows = shelf_scan(d) if d and os.path.isdir(d) else []
        self._queue.put(("shelf", rows))

    def _apply_shelf_rows(self, rows):
        self._shelf_scanning = False
        if rows is None:
            # 走査に失敗した。**空の本棚として扱ってはいけない**（§8.12）。
            # _shelf_loaded を立てないので次回やり直す。保留中の受信箱走査も、
            # 重複判定の土台が無いまま走らせず、ここで畳む
            self.lbl_shelf_status.configure(text=self._t("shelf_scan_fail"))
            if self._inbox_pending:
                self._inbox_pending = False
                self._inbox_scanning = False
                self.lbl_inbox_status.configure(text=self._t("inbox_need_shelf"))
            return
        self._shelf = rows
        self._shelf_loaded = True
        self._shelf_dir_mtime = self._output_dir_mtime()
        # 消えたファイルのチェック結果は落とす（残すと存在しない行の新着が数に乗る）
        alive = {r["path"] for r in rows}
        self._shelf_new = {k: v for k, v in self._shelf_new.items() if k in alive}
        self._refresh_shelf_list()
        self._sync_shelf_header()
        if self._inbox_pending:
            # 本棚待ちで保留していた受信箱の走査を、ここで初めて走らせる（§8.10）
            self._inbox_pending = False
            d = self.settings.get("inbox_dir", "")
            if d and os.path.isdir(d):
                self._inbox_start_worker(d)
            else:
                self._inbox_scanning = False

    def _refresh_shelf_list(self):
        """一覧を組み直す。**行の中身の更新は _update_shelf_row() に任せる。**

        ここは行を全部 destroy して作り直すので、結果が 1 件届くたびに呼ぶと
        作品数の二乗の手間になり、スクロール位置も先頭へ飛ぶ（§8.17）。
        """
        for w in self.frm_shelf_list.winfo_children():
            w.destroy()
        self._shelf_rows = []
        works = self._shelf_sorted_works()
        if not works:
            self.lbl_shelf_status.configure(text=self._t("shelf_empty"))
            self.btn_shelf_all.grid_remove()
            return
        self.lbl_shelf_status.configure(text="")
        for i, r in enumerate(works):
            icon = ctk.CTkLabel(self.frm_shelf_list, text="", width=18, anchor="w")
            icon.grid(row=i, column=0, sticky="w", padx=(2, 4), pady=1)
            name = self._ellipsis(r.get("title") or r.get("file", ""), 20)
            if r.get("display_name"):
                name = "%s  [%s]" % (name, r["display_name"])
            ctk.CTkLabel(self.frm_shelf_list, text=name, anchor="w",
                         font=ctk.CTkFont(size=11)).grid(row=i, column=1,
                                                         sticky="ew", pady=1)
            lbl_eps = ctk.CTkLabel(self.frm_shelf_list,
                                   text=self._t("shelf_eps", n=r.get("episodes", 0)),
                                   anchor="e", text_color="gray",
                                   font=ctk.CTkFont(size=11))
            lbl_eps.grid(row=i, column=2, sticky="e", padx=(6, 4), pady=1)
            # 件数だけでは「どこまで持っているか」が分からないので、最後の話の題を
            # ツールチップで添える。行を広げずに済む（§8.15）
            if r.get("last_title"):
                _Tooltip(lbl_eps, lambda t=r["last_title"]: self._t("shelf_last", t=t))
            state = ctk.CTkLabel(self.frm_shelf_list, text="", anchor="e",
                                 font=ctk.CTkFont(size=11))
            state.grid(row=i, column=3, sticky="e", padx=(4, 4), pady=1)
            # 「部分」とだけ出しても理由が分からないので添える（§8.19）
            if self._shelf_partial_from(r):
                _Tooltip(state, lambda: self._t("tip_shelf_partial"))
            # 話の一覧（手元の .txt を読むだけ・通信しない）
            b_list = ctk.CTkButton(self.frm_shelf_list, text="☰", width=28, height=22,
                                   fg_color="gray40", font=ctk.CTkFont(size=11),
                                   command=lambda row=r: self._shelf_show_episodes(row))
            b_list.grid(row=i, column=4, sticky="e", padx=(4, 0), pady=1)
            _Tooltip(b_list, lambda: self._t("tip_shelf_list"))
            # ePub を開く。--shelf-scan が返したパスをそのまま使う
            b_open = ctk.CTkButton(self.frm_shelf_list, text="📖", width=28, height=22,
                                   fg_color="gray40", font=ctk.CTkFont(size=11),
                                   command=lambda row=r: self._shelf_open_epub(row))
            b_open.grid(row=i, column=5, sticky="e", padx=(4, 0), pady=1)
            if not r.get("epub"):
                b_open.configure(state="disabled")
            _Tooltip(b_open, lambda row=r: self._t(
                "tip_shelf_open" if row.get("epub") else "shelf_noepub"))
            btn = ctk.CTkButton(self.frm_shelf_list, text=self._t("shelf_append"),
                                width=92, height=22, font=ctk.CTkFont(size=11),
                                command=lambda row=r: self._shelf_append([row]))
            btn.grid(row=i, column=6, sticky="e", padx=(4, 2), pady=1)
            self._shelf_rows.append({"row": r, "button": btn, "icon": icon,
                                     "state": state, "list": b_list, "open": b_open,
                                     "btn_fg": btn.cget("fg_color")})
            self._update_shelf_row(i)
        self._sync_shelf_all_button()

    def _update_shelf_row(self, i: int):
        """1 行だけ描き直す（§8.17）。

        新着チェックの結果は 1 件ずつ届くので、**届いたその行だけ**を直す。
        全体を作り直すと作品数ぶんの再構築が積み上がり、スクロール位置も飛ぶ。
        """
        if not 0 <= i < len(self._shelf_rows):
            return
        e = self._shelf_rows[i]
        r = e["row"]
        cr = self._shelf_new.get(r["path"]) or {}
        new = int(cr.get("new", 0) or 0)
        partial = self._shelf_partial_from(r)
        checking = bool(self._shelf_checking) and self._shelf_checking == r["path"]
        e["icon"].configure(text="⏳" if checking else ("●" if new and not partial
                                                       else "○"))
        if checking:
            text, color = self._t("shelf_row_checking"), ("#8a6d00", "#e3b341")
        elif partial:
            # 追記できないので、新着の件数より「部分である」ことを先に伝える
            text, color = self._t("shelf_partial", n=partial), ("#8a6d00", "#e3b341")
        elif cr.get("status") == "error":
            text, color = self._t("shelf_row_error"), ("#b3261e", "#f2b8b5")
        elif new:
            text, color = self._t("shelf_new", n=new), ("#1a7f37", "#3fb950")
        elif cr:
            text, color = self._t("shelf_latest"), "gray"
        else:
            text, color = self._t("shelf_unknown"), "gray"
        e["state"].configure(text=text, text_color=color)
        can_append = bool(new) and not partial
        e["button"].configure(state="normal" if can_append else "disabled",
                              fg_color=e["btn_fg"] if can_append else "gray40")

    def _shelf_row_index(self, path: str) -> int:
        for i, e in enumerate(self._shelf_rows):
            if e["row"].get("path") == path:
                return i
        return -1

    def _sync_shelf_all_button(self):
        n_new = self._shelf_new_count()
        if n_new:
            self.btn_shelf_all.configure(text=self._t("shelf_append_all", n=n_new))
            self.btn_shelf_all.grid()
        else:
            self.btn_shelf_all.grid_remove()

    # ── 新着チェック（--check-update-dir + checkresult）──────
    def _shelf_check_updates(self):
        """本棚の全作品の新着をまとめて確認する（§8.4）。

        **stage / progress は見ない。** ディレクトリモードでは作品ごとに
        繰り返されるので全体進捗にならない（design_progress_json.md §3.3）。
        数えるのは checkresult の到着数。
        """
        if self._proc is not None or self._shelf_proc is not None:
            self.lbl_shelf_status.configure(text=self._t("shelf_busy"))
            return
        d = self.settings.get("output_dir", "")
        if not (d and os.path.isdir(d)) or not self._shelf_works():
            return
        self._shelf_chk_total = len(self._shelf_works())
        self._shelf_chk_done = 0
        self._shelf_stop = False
        self._shelf_checking = ""
        # 押したボタンがそのまま中止になる。長いときに止められないのがいちばん辛い
        self.btn_shelf_check.configure(text=self._t("shelf_check_stop"),
                                       command=self._shelf_check_cancel)
        self.lbl_shelf_status.configure(
            text=self._t("shelf_checking", n=0, m=self._shelf_chk_total))
        threading.Thread(target=self._shelf_check_worker, args=(d,), daemon=True).start()

    def _shelf_check_cancel(self):
        """確認中のプロセスを止める。**届いた分の結果は残す**（§8.17）。"""
        self._shelf_stop = True
        self.lbl_shelf_status.configure(text=self._t("shelf_check_stopping"))
        if self._shelf_proc is not None:
            threading.Thread(target=_terminate_tree, args=(self._shelf_proc,),
                             daemon=True).start()

    def _shelf_check_worker(self, d: str):
        try:
            proc = subprocess.Popen(
                engine_cmd("--check-update-dir", d, "--progress-json",
                           "--check-update-order",
                           self.settings.get("shelf_sort", "updated"),
                           *_webhook_args(self.settings)),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=_engine_env(), creationflags=_CREATE_NO_WINDOW,
                bufsize=1, universal_newlines=True, encoding="utf-8", errors="replace")
        except Exception as e:
            self._queue.put(("rawlog", f"[本棚] 起動失敗: {e}"))
            self._queue.put(("shelfcheck_done", 1))
            return
        self._shelf_proc = proc
        # **起動と中止の競合を閉じる。** Popen が返る前に「中止」を押されると
        # _shelf_check_cancel は殺す相手がおらず、engine は最後まで走りきるのに
        # 「中止しました」と表示されてしまう（§8.19）
        if self._shelf_stop:
            _terminate_tree(proc)
        rc = 1
        # **_read_log は使わない。** あれは進捗行と ePub 完了行を拾って
        # ダウンロード用のイベントに変えるので、作品ごとに進捗行を出す
        # --check-update-dir に噛ませると本棚のチェック中にダウンロードの
        # 進捗バーとステータス行が動いてしまう
        t_err = threading.Thread(target=self._read_log_plain, args=(proc.stderr,),
                                 daemon=True)
        t_err.start()
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    self._queue.put(("rawlog", line))
                    continue
                if ev.get("event") == "checkresult":
                    self._queue.put(("checkresult", ev))
                elif ev.get("event") == "checkstart":
                    self._queue.put(("checkstart", ev))
            rc = proc.wait()
        except Exception as e:
            self._queue.put(("rawlog", f"[本棚] {e}"))
        finally:
            # **必ず通す。** ここを抜けないと _shelf_proc が None に戻らず、
            # チェックボタンが無効のまま・受信箱の定期スキャンも
            # （_inbox_maybe_scan の見送り条件に引っかかって）永久に止まる
            t_err.join(timeout=5)
            self._shelf_proc = None
            self._queue.put(("shelfcheck_done", rc))

    def _apply_checkstart(self, ev: dict):
        """いまどの作品を確認しているかを出す（§8.17）。"""
        prev = self._shelf_checking
        self._shelf_checking = ev.get("path") or ""
        for p in (prev, self._shelf_checking):
            i = self._shelf_row_index(p) if p else -1
            if i >= 0:
                self._update_shelf_row(i)
        i = self._shelf_row_index(self._shelf_checking)
        name = (self._shelf_rows[i]["row"].get("title") if i >= 0
                else ev.get("file", "")) or ev.get("file", "")
        self.lbl_shelf_status.configure(
            text=self._t("shelf_checking_now", n=int(ev.get("index", 0)),
                         m=int(ev.get("total", 0)), name=self._ellipsis(name, 18)))

    def _apply_checkresult(self, ev: dict):
        path = ev.get("path") or ""
        if path:
            self._shelf_new[path] = ev
        self._shelf_chk_done += 1
        if self._shelf_checking == path:
            self._shelf_checking = ""
        # **届いた行だけを直す。** 全体の作り直しはしない（§8.17）
        i = self._shelf_row_index(path)
        if i >= 0:
            self._update_shelf_row(i)
        self._sync_shelf_all_button()
        self._sync_shelf_header()
        self.lbl_shelf_status.configure(
            text=self._t("shelf_checking", n=self._shelf_chk_done,
                         m=max(self._shelf_chk_total, self._shelf_chk_done)))

    def _shelf_check_finished(self, _rc: int):
        self.btn_shelf_check.configure(text=self._t("shelf_check"),
                                       command=self._shelf_check_updates,
                                       state="normal")
        stopped = self._shelf_stop
        self._shelf_stop = False
        self._shelf_checking = ""
        self._refresh_shelf_list()
        self._sync_shelf_header()
        # **状況表示は一覧を組み直した後に入れる。** _refresh_shelf_list() は
        # 作品があるときに状況表示を空にするので、先に書くと即座に消える
        self.lbl_shelf_status.configure(
            text=self._t("shelf_check_stopped", n=self._shelf_chk_done)
            if stopped else "")
        if not stopped:
            n_new = self._shelf_new_count()
            self._notify("notice_new" if n_new else "notice_nonew", n=n_new)

    def _shelf_open_epub(self, row):
        """本棚の行の ePub を開く。無ければ保存先フォルダに退避する。"""
        if not self._open_epub_path(row.get("epub") or ""):
            self._open_folder()

    def _shelf_show_episodes(self, row):
        """行の話一覧を出す。**手元の .txt から読むので通信しない**（§8.15）。"""
        if self._shelf_listing:
            return
        self._shelf_listing = True
        self.lbl_shelf_status.configure(text=self._t("shelf_listing"))
        threading.Thread(target=self._shelf_list_worker, args=(row,),
                         daemon=True).start()

    def _shelf_list_worker(self, row):
        self._queue.put(("episodelist", "shelf", row,
                         episode_list(row["path"], from_file=True)))

    def _apply_episode_list(self, where: str, row, info):
        """一覧の受け取り。本棚（手元の .txt）と受信箱（サイト）で共用する。"""
        if where == "shelf":
            self._shelf_listing = False
            status, sub_key = self.lbl_shelf_status, "shelf_list_sub"
        else:
            self._inbox_listing = False
            status, sub_key = self.lbl_inbox_status, "inbox_list_sub"
        self._refresh_inbox_list()          # ボタンの活殺を戻す
        if not info or not info.get("titles"):
            status.configure(text=self._t("shelf_list_fail"))
            return
        status.configure(text="")
        inbox = (where == "inbox")
        self._show_episode_window(
            info.get("title") or row.get("title", ""),
            self._t(sub_key, n=info.get("total", 0),
                    author=info.get("author") or row.get("author", "")),
            info["titles"],
            source_url=(row.get("resolved") or row.get("url", "")),
            # **「ここから取得」は受信箱だけ。** 本棚は手元にある作品なので、
            # 続きは --append が担う。ここで部分ファイルを作らせない（§8.16）
            #
            # さらに、**一覧の行番号をそのまま --start に渡せるサイトに限る**
            # （§8.19）。エブリスタは一覧が「話」で --start が「ページ」を刻むため
            # 行番号を渡すとずれ、杉田玄白・結城浩・青空文庫は --start を読まない
            on_start=((lambda n, it=row: self._inbox_fetch_from(it, n))
                      if inbox and (row.get("site_info") or {}).get("start_from_list")
                      else None))

    def _show_episode_window(self, title: str, subtitle: str, titles: list,
                             *, source_url: str = "", on_start=None):
        """話一覧の窓（§8.15 / §8.16）。

        **ラベルを話数ぶん並べない。** 900 話で CTkLabel を 900 個作ると生成に
        数秒かかり操作感が壊れる。1 枚のテキストボックスに流し込む
        （選択・コピーもできる）。

        `source_url` があれば「元サイトを開く」を出す。`on_start` を渡すと
        行をクリックして「ここから取得」できる（受信箱だけ・本棚は `--append`
        が続きを担うので出さない）。
        """
        win = ctk.CTkToplevel(self)
        win.title(self._t("shelf_list_title", title=self._ellipsis(title, 40)))
        win.geometry("480x560")
        win.transient(self)
        ctk.CTkLabel(win, text=subtitle, anchor="w", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(fill="x", padx=12, pady=(10, 2))
        box = ctk.CTkTextbox(win, wrap="none")
        box.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        w = len(str(len(titles)))
        box.insert("end", "\n".join(f"{i:{w}}. {t}"
                                    for i, t in enumerate(titles, 1)))
        box.configure(state="disabled")
        # 明暗どちらの外観でも読める固定色（tag_config はタプル色を受けない）
        box.tag_config("pick", background="#3b6ea5", foreground="#ffffff")
        win.episode_box = box          # テストから中身を確かめる用

        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.pack(fill="x", padx=12, pady=(0, 12))
        win.site_button = None
        if source_url:
            win.site_button = ctk.CTkButton(
                foot, text=self._t("ep_open_site"), height=28, width=150,
                fg_color="gray40",
                command=lambda u=source_url: open_external_url(u))
            win.site_button.pack(side="left")

        win.picked = 0
        if on_start is not None:
            btn = ctk.CTkButton(foot, text=self._t("ep_pick_hint"), height=28,
                                state="disabled")
            btn.pack(side="right")
            win.start_button = btn
            # あとから追記できないことは、押す前に伝えておく（§8.19）
            ctk.CTkLabel(win, text=self._t("ep_start_note"), anchor="w",
                         text_color="gray", wraplength=440, justify="left",
                         font=ctk.CTkFont(size=11)).pack(fill="x", padx=12,
                                                         pady=(0, 10))

            def fetch():
                if win.picked:
                    on_start(win.picked)
                    win.destroy()

            def select(n: int):
                """n 行目を選んだ状態にする。"""
                if not 1 <= n <= len(titles):
                    return
                box.tag_remove("pick", "1.0", "end")
                box.tag_add("pick", f"{n}.0", f"{n}.end")
                win.picked = n
                btn.configure(text=self._t("ep_start_from", n=n), state="normal",
                              command=fetch)

            def pick(event):
                # state="disabled" でも index("@x,y") は効くので、
                # 読み取り専用のまま行を選べる
                try:
                    select(int(box.index(f"@{event.x},{event.y}").split(".")[0]))
                except Exception:
                    pass

            box.bind("<Button-1>", pick, add="+")
            # クリック座標の計算とは切り離して確かめられるようにしておく
            win.select_line = select
        return win

    # ── 続きを取得（kind="append" のジョブとしてキューへ）────
    def _shelf_append(self, rows):
        jobs = []
        for r in rows:
            job = self._make_job(r["path"], kind="append")
            job["label"] = r.get("title") or r.get("file", "")
            job["site_name"] = r.get("display_name") or ""
            job["info"] = {"site": r.get("site"), "display_name": r.get("display_name")}
            job["shelf_path"] = r["path"]
            jobs.append(job)
        self._start_or_enqueue(self._add_jobs(jobs))

    def _shelf_append_all(self):
        rows = [r for r in self._shelf_works()
                if (self._shelf_new.get(r["path"]) or {}).get("new", 0) > 0
                and not self._shelf_partial_from(r)]
        if rows:
            self._shelf_append(rows)

    def _shelf_after_append(self, job):
        """追記が終わった行の新着表示を落とし、走査のやり直しを予約する（§8.4）。

        **ここで shelf_scan を呼んではいけない。** `_job_finished()` は UI スレッドで
        走るうえ、走査は本棚ぶんの .txt を全部読む（1 作品 4MB 級）。同期で呼ぶと
        1 件追記するたびに画面が固まる。まとめ取得なら件数ぶん繰り返される。
        走査は**キューを流し終えてから 1 回だけ**行う（`_shelf_flush_pending`）。
        """
        path = job.get("shelf_path")
        if not path:
            return
        self._shelf_new.pop(path, None)
        self._shelf_dirty = True
        self._refresh_shelf_list()
        self._sync_shelf_header()

    def _shelf_flush_pending(self):
        """キュー終了後に本棚を 1 回だけ作り直す（話数を実態へ合わせる）。"""
        if not self._shelf_dirty:
            return
        self._shelf_dirty = False
        if self._shelf_open:
            self._shelf_reload()
        else:
            self._shelf_loaded = False   # 次に開いたときに読み直す

    # ══════════════════════════════════════════
    #  受信箱
    # ══════════════════════════════════════════
    def _sync_inbox_header(self):
        n = len(self._inbox)
        label = self._t("inbox_open" if self._inbox_open else "inbox_closed")
        if n:
            label += self._t("inbox_count", n=n)
        self.btn_inbox.configure(text=label)
        self.btn_inbox_reload.configure(text=self._t("inbox_reload"))
        self.btn_inbox_pick.configure(text=self._t("inbox_pick"))
        self.chk_inbox_auto.configure(text=self._t("inbox_auto"))
        sel = sum(1 for it in self._inbox if it["sel"].get() and not it["have"])
        self.btn_inbox_fetch.configure(
            text=self._t("inbox_fetch", n=sel) if sel else self._t("inbox_fetch0"),
            state="normal" if sel else "disabled")

    def _pick_inbox_dir(self):
        d = filedialog.askdirectory(initialdir=self.settings.get("inbox_dir") or None)
        if not d:
            return
        self.settings["inbox_dir"] = d
        save_settings(self.settings)
        self._inbox_reload()

    # ── 監視（§8.10）────────────────────────────────────────
    # スマホからトリガーフォルダへ置いたものを、GUI を立ち上げたまま拾うための仕組み。
    # OS のファイル監視 API は使わない。入口Bの本命は OneDrive / Google ドライブの
    # 同期フォルダで、**同期で現れるファイルはイベントが素直に飛んでこない**ため
    # 当てにならない。周期で見に行くほうが確実（watcher.bat の 2 秒間隔は過剰）。

    def _inbox_scan_min_from_widget(self) -> int:
        try:
            return max(0, min(int(float(self.var_inbox_scan.get())), 1440))
        except Exception:
            return int(self.settings.get("inbox_scan_min", 5) or 0)

    def _on_notify_changed(self, _event=None):
        """Webhook 設定の確定。**入力中の値は書き戻さない**（§8.13a）。"""
        self._persist()
        self._sync_notify_enabled()

    def _sync_notify_enabled(self):
        """チェックの有無で入力欄の可否を、宛先の有無で注意書きを切り替える。

        チェックは**宛先が無くても自由に入れられる**。入れられないと
        URL 欄が disabled のままで宛先を貼れない（実機で踏んだ詰み）。
        代わりに、有効なのに宛先が揃っていないことを注意書きで知らせる。
        """
        on = bool(self.var_notify.get())
        state = "normal" if on else "disabled"
        self.ent_webhook.configure(state=state)
        self.opt_webhook_fmt.configure(state=state)
        if on and not webhook_ready(self.settings):
            self.lbl_webhook_hint.configure(text=self._t("webhook_need_url"))
            self.lbl_webhook_hint.grid()
        else:
            self.lbl_webhook_hint.grid_remove()

    def _on_inbox_scan_changed(self, _event=None):
        """間隔を変えたら保存して予約を取り直す（次の周期から効く）。"""
        self._persist()
        self.var_inbox_scan.set(str(self.settings.get("inbox_scan_min", 5)))
        self._inbox_schedule()

    def _inbox_boot(self):
        """起動時に 1 回見てから周期スキャンに入る。"""
        self._inbox_maybe_scan()
        self._inbox_schedule()

    def _inbox_schedule(self):
        """次の自動スキャンを予約し直す（0 分なら止める）。"""
        if self._inbox_after is not None:
            try:
                self.after_cancel(self._inbox_after)
            except Exception:
                pass
            self._inbox_after = None
        minutes = int(self.settings.get("inbox_scan_min", 5) or 0)
        if minutes and not self._closing:
            self._inbox_after = self.after(minutes * 60_000, self._inbox_tick)

    def _inbox_tick(self):
        self._inbox_after = None
        if self._closing:
            return
        self._inbox_maybe_scan()
        self._inbox_schedule()

    def _inbox_maybe_scan(self, min_gap: float = 0.0) -> bool:
        """条件が揃っているときだけ受信箱を見に行く。

        ダウンロード中・本棚の新着チェック中は見送る。先読みの `--dry-run` が
        同じサイトへ重ねて当たるのを避けるためで、取りこぼしても次の周期で拾える。
        """
        if self._closing:
            return False
        d = self.settings.get("inbox_dir", "")
        if not (d and os.path.isdir(d)):
            return False
        if self._inbox_scanning or self._inbox_pending:
            return False
        if self._proc is not None or self._shelf_proc is not None:
            return False
        if min_gap and (time.time() - self._inbox_last_scan) < min_gap:
            return False
        self._inbox_reload()
        return True

    def _inbox_reload(self):
        d = self.settings.get("inbox_dir", "")
        if not (d and os.path.isdir(d)):
            self._inbox = []
            self._refresh_inbox_list()
            self.lbl_inbox_status.configure(text=self._t("inbox_nodir"))
            self._sync_inbox_header()
            return
        if self._inbox_scanning:
            return
        self._inbox_scanning = True
        self.lbl_inbox_status.configure(text=self._t("inbox_checking"))
        # **重複判定には本棚の URL が要る（§8.3）。本棚が未走査なら、その結果が
        # 届くまで受信箱の走査を保留する。** 空の本棚のまま進めると取得済みの作品を
        # 「未取得」と判定してしまい、自動取得が入っていると丸ごと落とし直す。
        # 起動時スキャンでは本棚も未走査なので、ここを詰めないと毎回起きる
        if not self._shelf_loaded:
            self._inbox_pending = True
            if not self._shelf_scanning:
                self._shelf_reload()
            return
        self._inbox_start_worker(d)

    def _inbox_start_worker(self, d: str):
        # 末尾スラッシュ・大小の違いで「未取得」に化けないよう畳んで比べる（§8.12）
        known = {canon_url(r["url"]) for r in self._shelf if r.get("url")}
        threading.Thread(target=self._inbox_worker, args=(d, known), daemon=True).start()

    def _inbox_worker(self, d: str, known: set):
        """監視フォルダを読み、URL を抜き、作品情報を先読みする（§8.3）。

        `--detect-site` はオフラインなので全 URL に掛けて正規化と重複判定を先に済ませ、
        **本棚にすでにある作品にはネットワークを使わない**。
        """
        try:
            self._inbox_worker_inner(d, known)
        finally:
            # **必ず通す。** ここを抜けないと _inbox_scanning が True のまま残り、
            # 以後の走査が全部早期 return して受信箱が黙って死ぬ（§8.12）
            self._queue.put(("inboxdone",))

    def _inbox_worker_inner(self, d: str, known: set):
        items = []
        try:
            names = sorted(os.listdir(d))
        except OSError:
            names = []
        for name in names:
            path = os.path.join(d, name)
            # os.path.isdir はリンクを辿るので、シンボリックリンクは別に弾く。
            # 受信箱は共有フォルダでありうる（§8.11）
            if name.startswith(".") or os.path.islink(path) or os.path.isdir(path):
                continue      # done\ はここで自然に外れる
            urls = self._extract_urls(read_text_any(path))
            if not urls:
                items.append({"path": path, "file": name, "url": "",
                              "error": "nourl"})
                continue
            for u in urls:
                items.append({"path": path, "file": name, "url": u})
        self._queue.put(("inbox", items))

        seen = {}
        for it in items:
            u = it.get("url")
            if not u:
                continue
            if u in seen:
                self._queue.put(("inboxinfo", u, seen[u]))
                continue
            info = detect_site(u) or {}
            norm = info.get("normalized_url") or u
            have = (canon_url(norm) in known) or (canon_url(u) in known)
            payload = {"site": info, "have": have, "url": u,
                       "resolved": "", "work": {}}
            # 短縮URL（share.google 等）は --detect-site では正体が分からない。
            # --dry-run に通すとエンジンが展開し workinfo["url"] で本当の作品 URL を
            # 返すので、**重複判定はそれを受け取ってからやり直す**（§8.8）
            if not have and (info.get("site") or info.get("short_url")):
                work = dry_run_info(norm)
                payload["work"] = work
                resolved = work.get("url") or ""
                if resolved and resolved != norm:
                    payload["resolved"] = resolved
                    payload["have"] = canon_url(resolved) in known
                    # 展開後の URL でサイト名を取り直す（オフライン・即時）
                    payload["site"] = detect_site(resolved) or info
                time.sleep(1.0)     # 先読みでもサイトに連打しない
            seen[u] = payload
            self._queue.put(("inboxinfo", u, payload))

    def _apply_inbox_items(self, items):
        self._inbox = []
        for it in items:
            self._inbox.append({
                "path": it["path"], "file": it["file"], "url": it.get("url", ""),
                "error": it.get("error", ""), "title": "", "author": "",
                "total": 0, "unit": "", "site_name": "", "site_info": None,
                "resolved": "", "unsupported": False,
                "have": False, "checking": bool(it.get("url")),
                "sel": ctk.BooleanVar(value=bool(it.get("url"))),
            })
        self._refresh_inbox_list()
        self._sync_inbox_header()

    def _apply_inbox_info(self, url: str, payload: dict):
        info = payload.get("site") or {}
        work = payload.get("work") or {}
        for it in self._inbox:
            if it["url"] != url:
                continue
            it["checking"] = False
            it["site_info"] = info or None
            it["site_name"] = info.get("display_name") or ""
            it["resolved"] = payload.get("resolved") or ""
            it["have"] = bool(payload.get("have"))
            it["unsupported"] = is_unsupported(info)
            if it["have"] or it["unsupported"]:
                it["sel"].set(False)   # 取れないものを自動取得の対象にしない
            it["title"] = work.get("title") or ""
            it["author"] = work.get("author") or ""
            it["total"] = work.get("total") or 0
            it["unit"] = work.get("unit") or ""
        self._refresh_inbox_list()
        self._sync_inbox_header()

    def _inbox_scan_finished(self):
        self._inbox_scanning = False
        self._inbox_last_scan = time.time()
        stamp = self._t("inbox_scanned", t=time.strftime("%H:%M"))
        if not self._inbox:
            self.lbl_inbox_status.configure(text=self._t("inbox_empty") + stamp)
        else:
            self.lbl_inbox_status.configure(text=stamp.strip())
        # 自動取得（既定 OFF・§8.3）
        if self.settings.get("inbox_auto") and self._proc is None:
            self._inbox_fetch_selected(auto=True)

    def _refresh_inbox_list(self):
        for w in self.frm_inbox_list.winfo_children():
            w.destroy()
        self._inbox_rows = []
        for i, it in enumerate(self._inbox):
            if it.get("error") == "nourl" or not it["url"]:
                ctk.CTkLabel(self.frm_inbox_list, text="⚠", width=18,
                             anchor="w").grid(row=i, column=0, sticky="w",
                                              padx=(2, 4), pady=1)
                ctk.CTkLabel(self.frm_inbox_list, text=self._ellipsis(it["file"], 26),
                             anchor="w", font=ctk.CTkFont(size=11)).grid(
                                 row=i, column=1, sticky="ew", pady=1)
                ctk.CTkLabel(self.frm_inbox_list, text=self._t("inbox_nourl"),
                             anchor="e", text_color="gray",
                             font=ctk.CTkFont(size=11)).grid(
                                 row=i, column=2, columnspan=2, sticky="e",
                                 padx=(6, 2), pady=1)
                continue
            chk = ctk.CTkCheckBox(self.frm_inbox_list, text="", width=20,
                                  variable=it["sel"], command=self._sync_inbox_header)
            chk.grid(row=i, column=0, sticky="w", padx=(2, 4), pady=1)
            if it["have"] or it.get("unsupported"):
                chk.configure(state="disabled")
            name = it["title"] or it.get("resolved") or it["url"]
            name = self._ellipsis(name, 26)
            if it["site_name"]:
                name = "%s  [%s]" % (name, it["site_name"])
            ctk.CTkLabel(self.frm_inbox_list, text=name, anchor="w",
                         font=ctk.CTkFont(size=11)).grid(row=i, column=1,
                                                         sticky="ew", pady=1)
            if it["checking"]:
                state = self._t("inbox_checking")
            elif it.get("unsupported"):
                state = self._t("inbox_ng")
            elif it["have"]:
                state = self._t("inbox_have")
            elif it["total"]:
                state = self._t("shelf_eps", n=it["total"])
            else:
                state = ""
            ctk.CTkLabel(self.frm_inbox_list, text=state, anchor="e",
                         text_color="gray", font=ctk.CTkFont(size=11)).grid(
                             row=i, column=2, sticky="e", padx=(6, 4), pady=1)
            # 話の一覧（サイトに取りに行く・押したときだけ）
            b_list = ctk.CTkButton(self.frm_inbox_list, text="☰", width=28, height=22,
                                   fg_color="gray40", font=ctk.CTkFont(size=11),
                                   command=lambda item=it: self._inbox_show_episodes(item))
            b_list.grid(row=i, column=3, sticky="e", padx=(4, 2), pady=1)
            can = self._inbox_can_list(it) and not self._inbox_listing
            if not can:
                b_list.configure(state="disabled")
            _Tooltip(b_list, lambda item=it: self._t(
                "tip_inbox_list" if not item.get("have") else "tip_inbox_have"))
            # 本棚（_shelf_rows）と同じ持ち方に揃える。行の item だけ持っても
            # ボタンの活殺を後から確かめられない
            self._inbox_rows.append({"row": it, "list": b_list, "check": chk})

    def _inbox_can_list(self, it) -> bool:
        """その行で話一覧を出せるか（§8.15）。

        **取得済みの作品には出さない。** 手元にあるものは本棚の一覧が
        通信せずに見せられるので、同じものをサイトへ取りに行く意味がない。
        """
        return bool(it.get("url")) and not it.get("checking") \
            and not it.get("unsupported") and not it.get("have")

    def _inbox_show_episodes(self, it):
        """受信箱の行の話一覧を出す。**サイトに取りに行く**（§8.15）。

        自動スキャン（5 分ごと）は `--dry-run` のままで、こちらは利用者が
        押したときだけ走る。一覧のために定期実行を重くしない。
        """
        if self._inbox_listing or not self._inbox_can_list(it):
            return
        self._inbox_listing = True
        self.lbl_inbox_status.configure(text=self._t("shelf_listing"))
        self._refresh_inbox_list()          # 読み込み中はボタンを伏せる
        threading.Thread(target=self._inbox_list_worker, args=(it,),
                         daemon=True).start()

    def _inbox_list_worker(self, it):
        target = it.get("resolved") or it["url"]
        self._queue.put(("episodelist", "inbox", it, episode_list(target)))

    def _inbox_fetch_from(self, it, start: int):
        """一覧で選んだ話から**最新まで**を取得する（§8.16）。

        サイトで既に読んだ分を飛ばす用途。終わりは常に最新でよいので
        `--end` は付けない。
        """
        job = self._make_job(it.get("resolved") or it["url"],
                             info=it.get("site_info"))
        if it.get("title"):
            job["label"] = it["title"]
        job["site_name"] = it.get("site_name") or job.get("site_name") or ""
        job["inbox_file"] = it["path"]
        job["start"] = max(1, int(start))
        self._start_or_enqueue(self._add_jobs([job]))

    def _inbox_fetch_selected(self, auto: bool = False):
        items = [it for it in self._inbox
                 if it["url"] and it["sel"].get() and not it["have"]]
        if auto:
            # **同じファイルを周期ごとに叩き続けない。** 取れない URL（削除済み・
            # 未対応）はダウンロードが失敗し done へ移らないので、素直に書くと
            # 5 分おきに永久に再試行することになる。自動で一度試したファイルは
            # この起動中は見送る（手動の「取得」は従来どおり効く）。
            # 印を付けるのは実際に積めた後（下）
            items = [it for it in items if it["path"] not in self._inbox_tried]
        if not items:
            return
        jobs = []
        for it in items:
            # 展開済みなら短縮URLではなく実URLを投げる。短縮URLのままだと
            # エンジンが毎回リダイレクトを追い直すうえ、一覧に正体が出ない
            job = self._make_job(it.get("resolved") or it["url"],
                                 info=it.get("site_info"))
            if it["title"]:
                job["label"] = it["title"]
            job["site_name"] = it.get("site_name") or job.get("site_name") or ""
            job["inbox_file"] = it["path"]
            jobs.append(job)
        added = self._start_or_enqueue(self._add_jobs(jobs))
        if auto and added:
            # 頼んでいないのに動いているので、黙って落とさない（§8.18）
            self._notify("notice_inbox", n=len(added))
        if auto:
            # **積めたものだけ「試した」印を付ける。** _add_jobs は既に同じ対象が
            # キューにあると黙って捨てるので、投入前に印を付けると
            # 一度も落としていないファイルが二度と自動取得されなくなる（§8.12）
            for job in added:
                if job.get("inbox_file"):
                    self._inbox_tried.add(job["inbox_file"])

    def _inbox_settle(self, job):
        """受信箱由来のジョブが終わったら、元ファイルを done\\ へ移す（§8.3）。

        1 つのファイルに複数 URL が入っていることがあるので、**そのファイル由来の
        ジョブが全部成功したときだけ**動かす。1 本でも失敗したら残して次回もう一度出す。
        """
        src = job.get("inbox_file")
        if not src:
            return
        sibs = [j for j in self._jobs if j.get("inbox_file") == src]
        if any(j["status"] in ("waiting", "running") for j in sibs):
            return
        if not all(j["status"] == "done" for j in sibs):
            return
        threading.Thread(target=self._inbox_move_done, args=(src,), daemon=True).start()

    def _inbox_move_done(self, src: str):
        """クラウド同期でロックされうるので 3 回まで粘る（§8.3）。

        **`done` が本物のディレクトリであることを必ず確かめる。** 受信箱は共有
        フォルダでありうるので、`done` をシンボリックリンクに差し替えられると
        `os.makedirs(exist_ok=True)` が成功してしまい、**中身も名前も第三者が
        決めたファイルがリンク先に置かれる**（`~/.ssh/authorized_keys` など）。
        移動先が受信箱の外を指したら何もしない（§8.11）。
        """
        inbox = os.path.realpath(os.path.dirname(src))
        dest_dir = os.path.join(inbox, "done")
        name = os.path.basename(src)
        if os.path.islink(dest_dir):
            self._queue.put(("rawlog", self._t("inbox_movefail", name=name)))
            return
        for attempt in range(3):
            try:
                os.makedirs(dest_dir, exist_ok=True)
                dst = os.path.join(dest_dir, name)
                if os.path.exists(dst):
                    stem, ext = os.path.splitext(name)
                    dst = os.path.join(dest_dir, f"{stem}_{int(time.time())}{ext}")
                if not os.path.realpath(dst).startswith(inbox + os.sep):
                    break                  # 受信箱の外へ出る宛先には書かない
                shutil.move(src, dst)      # 別ボリュームでも動くよう os.replace は使わない
                self._queue.put(("rawlog", self._t("inbox_moved", name=name)))
                return
            except OSError:
                time.sleep(0.5 * (attempt + 1))
        self._queue.put(("rawlog", self._t("inbox_movefail", name=name)))

    # ── 設定 ⇔ ウィジェット ───────────────────────────────────
    def _apply_settings_to_widgets(self):
        s = self.settings
        self.var_outdir.set(s["output_dir"])
        self.var_cover.set(s["cover_mode"])
        self._cover_image_path = s.get("cover_image_path", "")
        if self._cover_image_path:
            self.var_cover_file.set(os.path.basename(self._cover_image_path))
        self._cover_font_path = s.get("cover_font_path", "")
        self.var_cover_font_name.set(os.path.basename(self._cover_font_path)
                                     if self._cover_font_path
                                     else self._t("cover_font_default"))
        self.var_horizontal.set(bool(s["horizontal"]))
        self.var_kobo.set(bool(s["kobo"]))
        self.var_toc_at_end.set(bool(s.get("toc_at_end", False)))
        self._font_path = s.get("font_path", "")
        if self._font_path:
            self.var_font_name.set(os.path.basename(self._font_path))
        else:
            self.var_font_name.set(self._t("font_default"))
        self.var_inbox_auto.set(bool(s.get("inbox_auto", False)))
        self.var_inbox_scan.set(str(s.get("inbox_scan_min", 5)))
        self.var_no_images.set(bool(s.get("no_inline_images", False)))
        self.var_flash.set(bool(s.get("notify_taskbar", True)))
        self.var_sound.set(bool(s.get("notify_sound", False)))
        self.var_notify.set(bool(s.get("notify_webhook", False)))
        self.var_webhook_url.set(s.get("webhook_url", ""))
        self.var_webhook_fmt.set(s.get("webhook_format", "discord"))
        self._sync_notify_enabled()
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
        return normalize_webhook({
            "schema": SETTINGS_SCHEMA,
            "output_dir": self.var_outdir.get().strip() or default_output_dir(),
            "cover_mode": self.var_cover.get(),
            "cover_image_path": self._cover_image_path,
            "cover_font_path": self._cover_font_path,
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
            # 受信箱・本棚（§8.6）。inbox_dir はフォルダ選択ボタンで入るので
            # ウィジェットではなく settings 側を正とする
            "inbox_dir": self.settings.get("inbox_dir", ""),
            "inbox_auto": bool(self.var_inbox_auto.get()),
            "inbox_scan_min": self._inbox_scan_min_from_widget(),
            "no_inline_images": bool(self.var_no_images.get()),
            "notify_taskbar": bool(self.var_flash.get()),
            "notify_sound": bool(self.var_sound.get()),
            "notify_webhook": bool(self.var_notify.get()),
            "webhook_url": self.var_webhook_url.get().strip(),
            "webhook_format": self.var_webhook_fmt.get(),
            "inbox_open": bool(self._inbox_open),
            "shelf_open": bool(self._shelf_open),
            "shelf_sort": self.settings.get("shelf_sort", "updated"),
        })

    def _persist(self):
        self.settings = self._collect_settings()
        self.lbl_outdir.configure(text=self._t("save_prefix") + self.settings["output_dir"])
        save_settings(self.settings)

    # ── 状態遷移（§4） ───────────────────────────────────────
    _AUX_BUTTONS = ("btn_retry", "btn_open_epub", "btn_open", "btn_sites",
                    "btn_savelog")

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
        self._sync_log_section()
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
        self._sync_log_section()

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
        aux += [self.btn_open, self.btn_savelog]
        self._show_aux(*aux)
        self._sync_log_section()
        self._notify("notice_done_one")

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
            self._show_aux(self.btn_savelog)
        self.lbl_status.configure(text=msg, text_color=("#b3261e", "#f2b8b5"))
        self._sync_log_section()
        self._notify("notice_failed")

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
                       and is_unsupported(self._site_info))
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
            "start": 0,            # --start（0 = 先頭から・§8.16）
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

    def _add_jobs(self, jobs, staged: bool = True) -> list:
        """組み立て済みのジョブをそのまま積む（受信箱・本棚から・§8）。

        `_add_urls()` は URL 専用（サイト判定スレッドへ投げる）なので、
        判定済み／URL ですらない（append）ジョブのために分けてある。
        """
        if self._jobs and self._proc is None and not any(
                j["status"] in ("waiting", "running") for j in self._jobs):
            self._jobs = []
            self._queue_staged = False
            self._reset_result_view()
        if staged:
            self._queue_staged = True
        added = []
        for job in jobs:
            if any(j["target"] == job["target"] and j["kind"] == job["kind"]
                   for j in self._jobs):
                continue        # 同じ対象を二重に積まない（§7.8）
            self._jobs.append(job)
            added.append(job)
        if added:
            self._refresh_queue_list()
            self._sync_queue_visibility()
            self._update_download_enabled()
        return added        # 呼び出し側が「実際に積めたもの」を知る必要がある（§8.12）

    def _start_or_enqueue(self, added: list) -> list:
        """積んだジョブを、**空いているときだけ**流し始める（§8.12）。

        本棚の「続きを取得」と受信箱の「取得」は、ダウンロード実行中でも押せる
        （行のボタンは実行状態で無効化していない）。無条件に `_queue_start()` を
        呼ぶと `_abort_event.clear()` で進行中の中止要求を握り潰したうえ、
        `_start_job()` が `self._proc` を上書きして**エンジンが 2 本同時に走る**。
        走っている最中に積んだものは、今のジョブが終われば `_advance()` が拾う。
        """
        if added and self._proc is None:
            self._queue_start()
        return added

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
        if job.get("kind") == "append":
            # 本棚からの「続きを取得」。対象がパスなので、そのままだと
            # 一覧に長いファイルパスが並んで何の作品か分からない
            label = _JOB_KIND_ICON["append"] + (job.get("label") or os.path.basename(
                job["target"]))
        if job.get("site_name"):
            label = "%s  [%s]" % (self._ellipsis(label, 30), job["site_name"])
        else:
            label = self._ellipsis(label)
        if job.get("start"):
            label += self._t("q_from", n=job["start"])
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
        if is_unsupported(info):
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
        aux += [self.btn_open, self.btn_savelog]
        self._show_aux(*aux)
        self._sync_log_section()
        self._update_download_enabled()
        if ng == 0 and rest == 0:
            self._notify("notice_done", n=ok)
        else:
            self._notify("notice_mixed", ok=ok, ng=ng + rest)

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
            # §8: 受信箱の元ファイルを done へ／本棚の該当行を更新する。
            # ここに置くのは、終端が必ずこの 1 箇所を通るから（§7.5）
            try:
                self._inbox_settle(job)
                if status == "done":
                    # **追記だけでなく新規ダウンロードでも本棚はずれる**
                    # （出力先に新しい .txt が増える）。kind で絞っていたため、
                    # 落とした作品が本棚に出てこなかった（実機指摘・§8.14）
                    self._shelf_dirty = True
                    if job.get("kind") == "append":
                        self._shelf_after_append(job)
            except Exception as e:
                self._raw_log.append(f"[アプリ内エラー] {e}")
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
        self._shelf_flush_pending()      # 追記があったなら本棚を 1 回だけ読み直す
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

        `kind="append"`（本棚の「続きを取得」・§8.4）は URL ではなく
        `.txt` のパスを `--append` に渡す。**`--output-dir` は付けない。**
        エンジンは `--output-dir` が無いときだけ元ファイルの親フォルダへ書き戻すので、
        付けると走査した場所と別の場所に出力され、本棚に同じ作品が 2 つ並ぶ。
        """
        if job.get("kind") == "append":
            args = ["--append", job["target"]]
        else:
            target = job["info"].get("normalized_url") if job.get("info") else None
            args = [target or job["target"], "--output-dir", s["output_dir"]]
        if s["cover_mode"] == "site":
            args.append("--use-site-cover")
        elif s["cover_mode"] == "file" and s.get("cover_image_path") and \
                os.path.isfile(s["cover_image_path"]):
            args += ["--cover-image", s["cover_image_path"]]
        elif s["cover_mode"] == "auto" and s.get("cover_font_path") and \
                os.path.isfile(s["cover_font_path"]):
            # 設定したときだけ渡す（未設定の人の起動コマンドは従来と同じ）
            args += ["--cover-font", s["cover_font_path"]]
        if s["horizontal"]:
            args.append("--horizontal")
        if s["kobo"]:
            args.append("--kobo")
        if s.get("toc_at_end"):
            args.append("--toc-at-end")
        if s.get("font_path") and os.path.isfile(s["font_path"]):
            args += ["--font", s["font_path"]]
        if job.get("start"):
            # 一覧で選んだ話から取得する。**単位はサイトによって違う**（話/章/ページ）が、
            # 一覧に出ている行と --start の刻みは一致するので利用者は意識しないで済む
            args += ["--start", str(job["start"])]
        if s.get("no_inline_images"):
            args.append("--no-inline-images")
        args += ["--delay", str(s["delay"]), "--encoding", s["encoding"]]
        args += _webhook_args(s)
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
        # append は対象が URL ではなく .txt のパスなので --detect-site に掛けない
        # （掛けると必ず site:None になり「未対応サイト」で門前払いになる）。
        # 底本URL の有無はエンジン側が --append で検査する
        if job.get("kind") == "append":
            info = job.get("info") or {}
            self._needs_playwright = bool(info.get("needs_playwright"))
            if self._abort_event.is_set():
                self._queue.put(("aborted",))
                return
            rc, _ = self._run_engine(self._build_cli_args(job, s))
            if rc is not None:
                self._queue.put(("finished", rc))
            return
        info = job.get("info")
        if info is None:
            info = detect_site(job["target"])
            job["info"] = info
        if is_unsupported(info):
            self._queue.put(("precheck", "unsupported"))
            return
        # 短縮URL（site:null かつ short_url:true）はここで止めない。
        # エンジンが expand_short_url() で展開し、未対応ならその時点で失敗する
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

    def _read_log_plain(self, stream):
        """補助プロセス（本棚の新着チェック）の stderr を生ログへ流すだけ。

        進捗行・ePub 完了行の抽出はしない（§8.12）。ダウンロードのイベントと
        混ぜると、本棚を確認しているだけで進捗バーが動く。
        """
        for line in stream:
            self._queue.put(("rawlog", line.rstrip("\n")))

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
        # ── 受信箱・本棚（§8）。ダウンロードの中止フラグとは無関係 ──
        if kind == "shelf":
            self._apply_shelf_rows(msg[1])
            return
        if kind == "checkstart":
            self._apply_checkstart(msg[1])
            return
        if kind == "checkresult":
            self._apply_checkresult(msg[1])
            return
        if kind == "episodelist":
            self._apply_episode_list(msg[1], msg[2], msg[3])
            return
        if kind == "shelfcheck_done":
            self._shelf_check_finished(msg[1])
            return
        if kind == "inbox":
            self._apply_inbox_items(msg[1])
            return
        if kind == "inboxinfo":
            self._apply_inbox_info(msg[1], msg[2])
            return
        if kind == "inboxdone":
            self._inbox_scan_finished()
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
        if not self._open_epub_path(self._epub_path):
            self._open_folder()

    def _open_epub_path(self, path: str) -> bool:
        """拡張子を確かめたうえで ePub を開く。開けなければ False を返す。

        本棚の行からも呼ぶので、`self._epub_path` に依存しない形に切り出した（§8.15）。
        """
        # **拡張子を必ず確かめる。** os.startfile は関連付けに従って何でも起動するため、
        # ここは「表示」ではなく「実行」のシンクになる。_epub_path には
        # stdout の JSON イベントのほかに、stderr を _RE_EPUB_DONE で拾う経路があり
        # （design_progress_json §4.1 の版ずれ対策として残している）、stderr には
        # --progress-json 時にサイト由来の作品名・話タイトルがそのまま流れ込む。
        # 現状はイベント順序のおかげで偽装が最後に来ないが、それはエンジン側の
        # 都合であって GUI が保証できる不変条件ではない。ここで断つ。
        if not (path and os.path.isfile(path)
                and path.lower().endswith(_EPUB_EXTS)):
            return False
        try:
            if IS_WINDOWS:
                os.startfile(path)       # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", path])
            return True
        except Exception:
            return False                 # 関連付けが無ければ呼び出し側で退避

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

    def _flex_panels(self) -> list:
        """開いている伸縮パネルを**画面の並び順**で返す。

        要素は `[ウィジェット, want, min, floor]`。`want` が None のものは
        「中身の自然な高さ」を実測して決める（詳細設定がこれ）。
        一覧・受信箱・本棚はどれも同じスクロール一覧なので寸法を共用する。
        """
        out = []
        if self._queue_shown:
            out.append([self.frm_queue_list, QUEUE_LIST_PX, QUEUE_MIN_PX, QUEUE_FLOOR_PX])
        if self._inbox_open:
            out.append([self.frm_inbox_list, QUEUE_LIST_PX, QUEUE_MIN_PX, QUEUE_FLOOR_PX])
        if self._shelf_open:
            out.append([self.frm_shelf_list, QUEUE_LIST_PX, QUEUE_MIN_PX, QUEUE_FLOOR_PX])
        if self._detail_open:
            out.append([self.frm_detail, None, DETAIL_MIN_PX, DETAIL_FLOOR_PX])
        return out

    @staticmethod
    def _allocate_heights(spec: list, avail: int) -> list:
        """開いているパネルに高さを配る（design_gui_v2 §8.5）。

        v1.3 までは「詳細設定・一覧」の 2 枠決め打ちだった。§8 で受信箱・本棚が
        増えるため N 枠へ一般化した。段階は 3 つ:

          1. 全部の希望が入る → 希望どおり
          2. 入らないが**快適な下限**の合計は入る → 下限を配り、余りを
             画面の並び順に希望まで足す
          3. それも入らない → **絶対最小**を配り、同じ要領で余りを足す

        どの段でも足りなければ絶対最小のまま。はみ出した分は各パネルの中で
        スクロールできるので、画面外に押し出すよりこの方が実害がない。
        """
        wants  = [p[1] for p in spec]
        mins   = [p[2] for p in spec]
        floors = [p[3] for p in spec]
        if sum(wants) <= avail:
            return wants
        for base in (mins, floors):
            if sum(base) <= avail:
                h = list(base)
                extra = avail - sum(base)
                for i in range(len(h)):
                    if extra <= 0:
                        break
                    add = min(extra, max(0, wants[i] - h[i]))
                    h[i] += add
                    extra -= add
                return h
        return list(floors)

    def _fit_flexible_panels(self):
        """伸縮パネル（一覧・受信箱・本棚・詳細設定）の**見える**高さを決める。

        中身が全部入るならその高さ。画面に収まらないなら詰めて、足りない分は
        パネル内でスクロールさせる。**まとめて配分する**のが要点で、
        片方ずつ決めると他のパネルの存在を無視して画面からはみ出す。
        """
        spec = self._flex_panels()
        if not spec:
            return
        scale = self._window_scale()
        self.update_idletasks()
        # 中身の自然な高さ。CTkScrollableFrame 自身が内側の内容フレームなので、
        # winfo_reqheight() が中身の高さを返す（見える高さは configure(height=) 側）
        for p in spec:
            if p[1] is None:
                p[1] = int(p[0].winfo_reqheight() / scale + 0.999)
        # 全部 1px に潰して「パネル以外に要る高さ」を測る
        for p in spec:
            p[0].configure(height=1)
        self.update_idletasks()
        base = int(self.winfo_reqheight() / scale + 0.999)
        avail = self._max_logical_height() - base - FIT_MARGIN_PX
        for p, h in zip(spec, self._allocate_heights(spec, avail)):
            p[0].configure(height=max(1, h))

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
        if restore_to and not self._any_panel_open():
            # **入れ子で開閉したときに戻りきらないのを防ぐ。**
            # restore_to は「そのパネルを開く直前の高さ」だが、別のパネルが
            # 既に開いていればその分だけ嵩上げされた値になる。外側を先に閉じて
            # 内側を後から閉じると、最後に残るのが嵩上げ済みの値になり、
            # 全部閉じたのに窓だけ広いままになる（パネルが 4 枠になって顕在化した）。
            # 何も開いていない状態へ戻るときは「何も開いていないときの高さ」を使う。
            restore_to = min(restore_to, self._base_height or restore_to)
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

    def _any_panel_open(self) -> bool:
        """伸縮パネル（一覧・受信箱・本棚・詳細設定・ログ）が 1 つでも開いているか。"""
        return bool(self._detail_open or self._log_open or self._queue_shown
                    or self._inbox_open or self._shelf_open)

    def _remember_base_height(self, height: int = None):
        """パネルを何も開いていないときの高さを覚える。

        終了時に保存する高さはこれ。固定値を引き算する方式だと、
        値がずれた瞬間に「次回は縦に間延びした窓で開く」が復活する。
        """
        if self._any_panel_open():
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

    def _sync_log_section(self):
        """詳細ログの見出しを、ログがあるときだけ出す（§8.9）。

        実行中は `_start_job()` が `_raw_log` を空にするので自動的に隠れる。
        見出しが消えるときに開きっぱなしにしない（本体だけ宙に浮く）。
        """
        if self._raw_log:
            self.btn_logsec.configure(
                text=self._t("logsec_open" if self._log_open else "logsec_closed"))
            self.btn_logsec.grid()
            return
        if self._log_open:
            self._toggle_log()     # _toggle_log は _sync_log_section を呼ばない（再帰しない）
        self.btn_logsec.grid_remove()

    def _toggle_log(self):
        self._log_open = not self._log_open
        if self._log_open:
            self._h_before_log = self._logical_size()[1]
            self.btn_logsec.configure(text=self._t("logsec_open"))
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
            self.btn_logsec.configure(text=self._t("logsec_closed"))
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
        is_auto = (self.var_cover.get() == "auto")
        font_state = "normal" if is_auto else "disabled"
        self.btn_cover_font_pick.configure(state=font_state)
        self.btn_cover_font_clear.configure(state=font_state)
        self.lbl_cover_font.configure(text_color=("gray10", "gray90") if is_auto else "gray")
        self._persist()

    def _reload_shelf_if_open(self):
        """保存先が変わったら本棚を作り直す（本棚は保存先フォルダそのもの）。"""
        self._shelf_loaded = False
        self._shelf_new = {}
        if self._shelf_open:
            self._shelf_reload()
        else:
            self._shelf = []
            self._sync_shelf_header()

    def _pick_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_outdir.get() or default_output_dir())
        if d:
            self.var_outdir.set(d)
            self._persist()
            self._reload_shelf_if_open()   # 本棚は保存先フォルダそのもの（§8.4）

    def _pick_cover_image(self):
        f = filedialog.askopenfilename(
            filetypes=[(self._t("ft_image"), "*.jpg *.jpeg *.png"),
                        (self._t("ft_all"), "*.*")])
        if f:
            self._cover_image_path = f
            self.var_cover_file.set(os.path.basename(f))
            self._persist()

    def _pick_cover_font(self):
        f = filedialog.askopenfilename(
            filetypes=[(self._t("ft_cover_font"), "*.ttf *.otf *.ttc"),
                        (self._t("ft_all"), "*.*")])
        if f:
            self._cover_font_path = f
            self.var_cover_font_name.set(os.path.basename(f))
            self._persist()

    def _clear_cover_font(self):
        self._cover_font_path = ""
        self.var_cover_font_name.set(self._t("cover_font_default"))
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
        self._focused = True
        # 見たのだから知らせは役目を終えている（§8.18）
        if self._notice:
            self._notice = ""
            self._sync_title()
        self._maybe_autofill_from_clipboard()
        # 受信箱も見直す（§8.10）。<FocusIn> は alt-tab のたびに飛ぶので
        # 直近に走査していれば見送る
        self._inbox_maybe_scan(min_gap=30.0)

    def _on_focus_out(self, event):
        # <FocusOut> は子ウィジェットでも飛ぶ。窓そのものから外れたときだけ見る
        if event.widget is self:
            self._focused = False

    def _sync_title(self):
        base = self._t("title")
        self.title(f"{self._notice} — {base}" if self._notice else base)

    def _notify(self, key: str, **kw):
        """結果を知らせる（§8.18）。

        タイトルには常に出す（雑音にならない）。**タスクバーの点滅と音は、
        窓を見ていないときだけ。** 見ている人に点滅を出すのはただの雑音で、
        「完了したらフォルダを開く」がフォーカスを奪うのと同じ失敗になる。
        """
        self._notice = self._t(key, **kw) if key else ""
        self._sync_title()
        if not self._notice or self._focused:
            return
        if self.settings.get("notify_taskbar", True):
            flash_taskbar(self)
        if self.settings.get("notify_sound"):
            try:
                self.bell()
            except Exception:
                pass          # 音が出せない環境でも本筋は済んでいる

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
        if is_unsupported(info):
            self.lbl_site.configure(text=self._t("site_ng"), text_color=("#b3261e", "#f2b8b5"))
        elif (info or {}).get("site") is None:
            # 短縮URL。開いてみないと分からないので赤にはしない
            self.lbl_site.configure(text=self._t("site_short"),
                                    text_color=("#8a6d00", "#e3b341"))
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
        set_engine_lang(self._lang())   # 以後のエンジン起動に効かせる（§8.13）
        self._sync_title()
        self.lbl_url.configure(text=self._t("paste_url"))
        self.ent_url.configure(placeholder_text=self._t("url_ph"))
        if self._proc is None:
            self.btn_main.configure(text=self._t("download"))
        self.btn_open.configure(text=self._t("open_folder"))
        self.btn_open_epub.configure(text=self._t("open_epub"))
        self.btn_savelog.configure(text=self._t("save_log"))
        self.btn_sites.configure(text=self._t("sites"))
        self._sync_log_section()
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
        self.lbl_cover_font.configure(text=self._t("cover_font"))
        if not self._cover_font_path:
            self.var_cover_font_name.set(self._t("cover_font_default"))
        self.btn_cover_font_pick.configure(text=self._t("pick"))
        self.btn_cover_font_clear.configure(text=self._t("font_reset"))
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
        # 受信箱・本棚（§8）。見出しは件数を含むので専用の同期関数を通す
        self._sync_inbox_header()
        self._sync_shelf_header()
        self._refresh_inbox_list()
        self._refresh_shelf_list()
        self.chk_auto_paste.configure(text=self._t("auto_paste"))
        self.chk_open_on_done.configure(text=self._t("open_on_done"))
        self.lbl_inbox_scan.configure(text=self._t("inbox_scan_min"))
        self.chk_no_images.configure(text=self._t("no_images"))
        self.chk_flash.configure(text=self._t("notify_taskbar"))
        self.chk_sound.configure(text=self._t("notify_sound"))
        self.chk_notify.configure(text=self._t("notify_webhook"))
        self.ent_webhook.configure(placeholder_text=self._t("webhook_ph"))
        self._sync_notify_enabled()
        if self._engine_ver:
            self.lbl_ver.configure(text=self._t("engine_ver", ver=self._engine_ver))
        # サイト判定バッジは言語に依存するので、判定済みなら出し直す
        if self._site_info is not None and self._site_info_url:
            self._apply_site_info(self._detect_seq, self._site_info_url, self._site_info)

    # ── 終了 ─────────────────────────────────────────────────
    def _unfinished_count(self) -> int:
        return sum(1 for j in self._jobs if j["status"] in ("waiting", "running"))

    def _on_close(self):
        # 本棚の新着チェックは終了を待たずに殺す（§8.4）。読み取り専用なので
        # 途中で止めても手元のファイルは壊れない
        if self._shelf_proc is not None:
            threading.Thread(target=_terminate_tree, args=(self._shelf_proc,),
                             daemon=True).start()
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
        for attr in ("_poll_after", "_detect_after", "_inbox_after"):
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
