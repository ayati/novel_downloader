#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: MIT
#
# MIT License
#
# Copyright (c) 2026 N.Aono <ayati@ayati.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
"""
novel_downloader.py
小説投稿サイトの作品を一括ダウンロードし、青空文庫書式テキスト＋縦書きePub3に変換します。

使い方:
    # URLから直接ダウンロード
    python novel_downloader.py <URL> [オプション]

    # 既存テキストに続きを追記・ePub再生成（URL指定不要）
    python novel_downloader.py --append <FILE.txt>

    # 新着話数の確認のみ（ダウンロード・上書きなし）
    python novel_downloader.py --check-update <FILE.txt>

    # ローカルテキストファイルからePub3を生成
    python novel_downloader.py --from-file <FILE> [オプション]

対応サイト（URLモード）:
    小説家になろう  https://ncode.syosetu.com/nXXXXxx/
    カクヨム        https://kakuyomu.jp/works/XXXXXXXXXX
    アルファポリス  https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX
    エブリスタ      https://estar.jp/novels/XXXXXXXXX
    野いちご        https://www.no-ichigo.jp/book/nXXXXXX
    ハーメルン      https://syosetu.org/novel/XXXXXXX/
    ノベマ！        https://novema.jp/book/nXXXXXX
    ノベルアップ＋  https://novelup.plus/story/XXXXXXXXX
    ステキブンゲイ  https://sutekibungei.com/novels/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
    NOVEL DAYS      https://novel.daysneo.com/works/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.html
    ネオページ      https://www.neopage.com/book/XXXXXXXXXXXXXXXXX
    ソリスピア      https://solispia.com/title/XXXX
    berry's cafe    https://www.berrys-cafe.jp/book/nXXXXXXX
    monogatary.com  https://monogatary.com/story/XXXXXXX
    青空文庫        https://www.aozora.gr.jp/cards/XXXXXX/cardXXXXXX.html
    プロジェクト杉田玄白  https://www.genpaku.org/XXXXXX/XXXXXXj.html
    結城浩翻訳の部屋      https://www.hyuki.com/trans/XXXXXX

オプション:
    -o FILE          出力ベース名（省略時は作品タイトルから自動生成）
                     例: -o mynovel  → mynovel.txt / mynovel.epub
    --delay SEC      リクエスト間隔（秒、デフォルト 1.5）
    --resume [N]     続きからダウンロード。N省略時は既存.txtから話数を自動検出して再開。
                     N指定時は第N話から開始。全サイト対応（青空文庫・ローカルモードを除く）
    --append FILE    既存.txtに続きを追記・ePub再生成。底本URLを自動抽出するためURL指定不要。
                     新規エピソードがない場合は既存ファイルを上書きしない
    --check-update FILE  既存.txtとサイトの最新話数を比較し、新着のみ表示して終了
    --list-only      エピソード一覧と話数のみ表示して終了（ダウンロードなし）
    --start N        取得開始話数（野いちご・ノベマ！・berry's cafe は章番号）
    --end N          取得終了話数（省略時は最終話まで。野いちご・ノベマ！・berry's cafe は章番号）
    --encoding ENC   テキスト出力エンコーディング（デフォルト utf-8）
    --newline MODE   改行コード（os=OS標準 / lf / crlf）
    --no-epub        ePub出力を省略してテキストのみ出力する
    --cover-bg COLOR 表紙背景色（#RRGGBB形式）
    --cover-image FILE 表紙に使用するローカル画像ファイル（JPEG/PNG）
    --use-site-cover 作品ページのog:imageを表紙として使用する
    --from-file FILE ローカルテキストファイルからePub3を生成（URLモード不要）
    --from-epub FILE ローカルePub3ファイルを青空文庫書式テキストに逆変換
    --title TITLE    タイトルを上書き（--from-file 使用時）
    --author AUTHOR  著者名を上書き（--from-file 使用時）
    --font FILE      ePub本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）
    --toc-at-end     目次ページを奥付の後（末尾）に配置する
    --output-dir DIR 出力先ディレクトリ（存在しない場合は自動作成）
    --kobo           Kobo専用端末向けに拡張子を.kepub.epubにする
"""

import sys
import time
import re
import os
import io
import json
import contextlib
import tempfile
import uuid
import zipfile
import argparse
import unicodedata
from datetime import date, datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse, urljoin, parse_qs
from html import escape as _esc
from html.parser import HTMLParser
from pathlib import Path

# Windows環境でのコンソール文字化け対策
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# カクヨム用ライブラリ（任意インポート）
try:
    import requests
    from bs4 import BeautifulSoup
    _KAKUYOMU_AVAILABLE = True
except ImportError:
    _KAKUYOMU_AVAILABLE = False

# ハーメルン用ライブラリ（任意インポート）
try:
    from playwright.sync_api import sync_playwright as _hameln_playwright
    _HAMELN_AVAILABLE = True
except ImportError:
    _HAMELN_AVAILABLE = False

# 表紙画像生成用ライブラリ（必須推奨）
try:
    from PIL import Image, ImageDraw, ImageFont
    import io as _io
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False
    print(
        "[警告] Pillow がインストールされていないため、JPEG表紙画像を生成できません。\n"
        "       JPEG表紙を有効にするには以下のコマンドでインストールしてください:\n"
        "           [Ubuntu/Debian] sudo apt install python3-pillow\n"
        "           [その他]        pip install Pillow\n"
        "       Pillow がない場合は SVG フォールバックで表紙を生成しますが、\n"
        "       多くの ePub リーダーで SVG 表紙は正しく表示されない場合があります。"
    )


# ══════════════════════════════════════════
#  共通定数
# ══════════════════════════════════════════

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

ENCODING   = "utf-8"
RETRY_MAX  = 3
RETRY_WAIT = 5.0
PAGE_BREAK = "\n\n［＃改ページ］\n\n"


# ══════════════════════════════════════════
#  共通：青空文庫書式ユーティリティ
# ══════════════════════════════════════════

# 半角 → 全角／縦書き向け変換テーブル
_TATE_TABLE = str.maketrans({"!": "！", "?": "？", "~": "〜"})
_RE_ELLIPSIS   = re.compile(r"\.{3}")
_RE_DASH       = re.compile(r"-{2,}")
_RE_EXCL_SPACE = re.compile(r"([！？])([^！？」』）】\s])")


def _parse_hex_color(hex_str: str) -> tuple:
    """#RRGGBB 形式のカラーコードを (R, G, B) タプルに変換する。"""
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"無効なカラーコード: {hex_str}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _darken_color(r: int, g: int, b: int, factor: float = 0.6) -> tuple:
    """色を暗くする。"""
    return int(r * factor), int(g * factor), int(b * factor)


def normalize_tate(text: str) -> str:
    """縦書き用に記号を正規化する。"""
    text = text.translate(_TATE_TABLE)
    text = _RE_ELLIPSIS.sub("……", text)
    text = _RE_DASH.sub("――", text)
    text = _RE_EXCL_SPACE.sub(r"\1　\2", text)
    return text


def aozora_header(title: str, author: str, synopsis: str = "",
                  source_url: str = "") -> str:
    """青空文庫書式のファイル先頭ヘッダーを生成する。
    1行目：題名、2行目：作者名、3行目：空行
    """
    syn_block = f"\n【あらすじ】\n{synopsis}\n" if synopsis else ""
    url_block = f"底本URL：{source_url}\n" if source_url else ""
    return (
        f"{title}\n"
        f"{author}\n"
        f"\n"
        f"{syn_block}"
        f"{url_block}"
        "-------------------------------------------------------\n"
        "【テキスト中に現れる記号について】\n\n"
        "《》：ルビ\n"
        "（例）漢字《かんじ》\n\n"
        "｜：ルビの付く文字列の始まりを特定する記号\n\n"
        "［＃］：入力者注　主に外字の説明や傍点の位置の指定\n"
        "（例）［＃「字」に傍点］\n"
        "-------------------------------------------------------\n\n"
    )


def aozora_colophon(title: str, source_url: str, site_name: str) -> str:
    """青空文庫書式の奥付を生成する。"""
    today = date.today().strftime("%Y年%m月%d日")
    return (
        f"\n\n底本：「{title}」{site_name}\n"
        f"　　　{source_url}\n"
        f"入力：novel_downloader.py\n"
        f"校正：未校正\n"
        f"作成：{today}\n\n"
        f"［＃「{title}」終わり］\n"
    )


def aozora_chapter_title(subtitle: str, level: str = "大見出し") -> str:
    """章タイトルを青空文庫の見出し記法に変換する。"""
    return (
        f"［＃「{subtitle}」は{level}］\n"
        f"{subtitle}\n"
        f"［＃「{subtitle}」は{level}終わり］"
    )


def safe_filename(title: str, fallback: str = "novel") -> str:
    """ファイル名に使えない文字を除去してベース名（拡張子なし）を返す。"""
    name = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
    name = Path(name).name  # ../ 等のパス成分を除去
    return (name[:60] if name else fallback)


class _CheckUpdateDone(Exception):
    """--check-update モードでエピソード一覧を取得したときに送出する例外。"""
    def __init__(self, title: str, author: str, ep_titles: list):
        self.title     = title
        self.author    = author
        self.ep_titles = ep_titles

_CHECK_UPDATE_MODE: bool = False   # --check-update 実行中に True


def _show_episode_list(title: str, author: str, ep_titles: list[str]) -> None:
    """--list-only / --check-update モード: エピソード一覧を表示または取得する。"""
    if _CHECK_UPDATE_MODE:
        raise _CheckUpdateDone(title, author, ep_titles)
    total = len(ep_titles)
    width = len(str(total))
    print(f"\nタイトル : {title}")
    print(f"著者     : {author}")
    print(f"話数     : {total} 話\n")
    for i, t in enumerate(ep_titles, 1):
        print(f"  {i:{width}}. {t}")
    sys.exit(0)


def _dry_run_exit(args):
    """--dry-run 指定時にメッセージを表示してダウンロードをスキップする。"""
    if getattr(args, "dry_run", False):
        print("\n[dry-run] ダウンロードは行いません。")
        sys.exit(0)


def _apply_output_dir(args, base: str) -> str:
    """--output-dir が指定されていれば出力先ディレクトリを適用して返す。
    ディレクトリが存在しない場合は自動作成する。
    """
    d = getattr(args, "output_dir", None)
    if not d:
        return base
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, Path(base).name)


def _load_existing_txt(txt_path: str) -> tuple[list[str], list[dict]]:
    """既存の青空文庫書式 .txt からセクションリストと epub_episodes リストを返す。

    Returns:
        (sections, epub_episodes)
        sections      : write_file の sections 引数に直接渡せる文字列リスト
        epub_episodes : build_epub の episodes 引数に渡せる {title, body} dict リスト
    """
    if not os.path.exists(txt_path):
        return [], []
    try:
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return [], []

    # ヘッダー末尾の区切り線（2 本目）を探して本文開始位置を特定
    SEP = "-------------------------------------------------------\n"
    pos1 = content.find(SEP)
    if pos1 == -1:
        return [], []
    pos2 = content.find(SEP, pos1 + len(SEP))
    body_start = (pos2 + len(SEP)) if pos2 != -1 else (pos1 + len(SEP))

    body = content[body_start:]

    # PAGE_BREAK で分割し、末尾セクションから奥付部分（"\n\n底本："以降）を除去
    # write_file はセクションの直後に PAGE_BREAK なしで colophon を付けるため、
    # 最後の要素は「エピソード内容 + 奥付」が混在している場合がある
    raw = body.split(PAGE_BREAK)
    if raw:
        last = raw[-1]
        col_pos = last.find("\n\n底本：")
        if col_pos != -1:
            trimmed = last[:col_pos]
            if trimmed.strip():
                raw[-1] = trimmed   # セクション部分だけ保持
            else:
                raw.pop()           # セクション内容がない（奥付のみ）
        elif "底本：" in last and not re.search(r"は(?:大|中|小)見出し", last):
            raw.pop()               # 奥付のみのセクション（念のため）

    sections: list[str] = []
    epub_episodes: list[dict] = []
    for sec in raw:
        if not sec.strip():
            continue
        # 見出しマーカーを持たないセクションは除外
        if not re.search(r"は(?:大|中|小)見出し", sec):
            continue
        sections.append(sec)

        # epub_episodes を再構築（見出し終わり行の次行以降が本文）
        lines = sec.strip().split("\n")
        ep_title = ""
        body_start_idx = 0
        for li, ln in enumerate(lines):
            if re.search(r"は(?:大|中|小)見出し終わり］", ln):
                body_start_idx = li + 1
                break
            m = re.search(r"「([^」]+)」は(?:大|中|小)見出し］", ln)
            if m:
                ep_title = m.group(1)
        ep_body = "\n".join(lines[body_start_idx:]).strip()
        epub_episodes.append({"title": ep_title or "（タイトル不明）", "body": ep_body})

    return sections, epub_episodes


def _extract_url_from_txt(txt_path: str) -> str:
    """青空文庫書式 .txt から底本 URL を抽出して返す。

    aozora_header() が出力する「底本URL：https://...」行を優先し、
    見つからなければ aozora_colophon() の「底本：」次行 URL を試みる。
    """
    try:
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return ""

    # ヘッダー内「底本URL：」行（最も確実）
    m = re.search(r"底本URL：(https?://\S+)", content)
    if m:
        return m.group(1).strip()

    # 奥付「底本：「タイトル」サイト名\n　　　URL」形式
    m = re.search(r"底本：「[^」]*」[^\n]*\n[　\s]*(https?://\S+)", content)
    if m:
        return m.group(1).strip()

    return ""


def _apply_resume(
    args, txt_path: str, target_eps: list
) -> tuple[list[str], list[dict], list]:
    """--resume が指定されている場合、既存テキストを読み込み target_eps をスライスする。

    Returns:
        (sections, epub_episodes, new_target_eps)
        sections/epub_episodes : 既存ファイルから読み込んだ内容（空なら新規）
        new_target_eps         : 残りダウンロード対象（スキップ済みを除いた target_eps）
    """
    resume_arg = getattr(args, "resume", None)
    if resume_arg is None:
        return [], [], target_eps

    existing_sections, existing_epub = _load_existing_txt(txt_path)
    n_existing = len(existing_sections)

    if resume_arg == 0:          # 引数なし → 自動検出
        skip = n_existing
        if skip == 0:
            print("      [resume] 既存ファイルなし。最初から取得します。")
            return [], [], target_eps
        print(f"      [resume] 既存 {n_existing} 話を検出。第 {skip + 1} 話から再開します。")
    else:                        # --resume N → 話数指定
        skip = max(0, resume_arg - 1)
        if skip == 0:
            return [], [], target_eps
        if n_existing >= skip:
            print(f"      [resume] 第 {resume_arg} 話から再開（既存 {n_existing} 話を読み込み済み）。")
        else:
            print(f"      [resume] 第 {resume_arg} 話から再開。")

    # skip 話分を既存セクションから取得。target_eps の長さを超えないよう制限
    use_n = min(skip, n_existing, len(target_eps))
    return (
        existing_sections[:use_n],
        existing_epub[:use_n],
        target_eps[skip:],
    )


def _epub_ext(args) -> str:
    """--kobo 指定時は .kepub.epub、それ以外は .epub を返す。"""
    return ".kepub.epub" if getattr(args, "kobo", False) else ".epub"


def write_file(filename: str, header: str, sections: list, colophon: str,
               encoding: str = ENCODING, newline: str = "os"):
    """ヘッダー + 各話（改ページ区切り）+ 奥付 を書き出す。
    newline: 'os'=実行環境の標準改行コード / 'lf'=LF(\\n) / 'crlf'=CRLF(\\r\\n)
    """
    nl = None if newline == "os" else ("\r\n" if newline == "crlf" else "\n")
    with open(filename, "w", encoding=encoding, newline=nl) as f:
        f.write(header)
        f.write(PAGE_BREAK.join(sections))
        f.write(colophon)


# ══════════════════════════════════════════
#  共通：縦書きePub3生成
# ══════════════════════════════════════════

# ── ePub内部で使うXML/HTMLテンプレート ──────────────────────────

def _make_epub_css(font_name: str = "", font_filename: str = "") -> str:
    """
    ePub本文用CSSを生成する。
    font_name / font_filename が指定された場合は @font-face を挿入し、
    body の font-family の先頭に追加する。
    """
    font_face = ""
    if font_name and font_filename:
        ext = Path(font_filename).suffix.lower()
        fmt_map = {".otf": "opentype", ".ttf": "truetype",
                   ".woff": "woff", ".woff2": "woff2"}
        fmt = fmt_map.get(ext, "opentype")
        font_face = (
            f'@font-face {{\n'
            f'  font-family: "{font_name}";\n'
            f'  src: url("../fonts/{font_filename}") format("{fmt}");\n'
            f'  font-weight: normal;\n'
            f'  font-style: normal;\n'
            f'}}\n\n'
        )
        custom_family = f'"{font_name}", '
    else:
        custom_family = ""

    return f"""\
@charset "UTF-8";

{font_face}/* ── 縦書き基本設定（フォールバック: class非対応環境・Amazon Kindle等） ── */
html, body {{
  -epub-writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
  writing-mode: vertical-rl;
}}
html {{
  line-height: 2.0;
  font-size: 1em;
}}

/* ── DPFJガイド準拠: class対応RSはこちらが優先 ── */
html.vrtl,
html.vrtl body {{
  -epub-writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
  writing-mode: vertical-rl;
}}
html.hltr,
html.hltr body {{
  -epub-writing-mode: horizontal-tb;
  -webkit-writing-mode: horizontal-tb;
  writing-mode: horizontal-tb;
}}
html.vrtl {{
  line-height: 2.0;
  font-size: 1em;
}}
html.hltr {{
  line-height: 1.8;
  font-size: 1em;
}}

/* 縦組みページの body フォント（serif-ja-v: RS が解釈する仮想フォント名） */
html.vrtl body {{
  font-family: {custom_family}serif-ja-v, serif-ja, "游明朝", "YuMincho",
               "ヒラギノ明朝 ProN", "HiraMinProN-W3", "Noto Serif CJK JP", serif;
}}

/* 横組みページの body フォント（serif-ja: RS が解釈する仮想フォント名） */
html.hltr body {{
  font-family: {custom_family}serif-ja, "游明朝", "YuMincho",
               "ヒラギノ明朝 ProN", "HiraMinProN-W3", "Noto Serif CJK JP", serif;
}}

/* フォールバック（class非対応環境） */
body {{
  margin: 1em;
  font-family: {custom_family}"游明朝", "YuMincho", "ヒラギノ明朝 ProN", "HiraMinProN-W3",
               "Noto Serif CJK JP", serif;
}}

/* ── 表紙 ── */
.cover-title {{
  font-size: 1.8em;
  font-weight: bold;
  margin-bottom: 1em;
  text-align: center;
}}

.cover-author {{
  font-size: 1.1em;
  text-align: center;
  margin-bottom: 2em;
}}

.cover-synopsis {{
  font-size: 0.9em;
  margin-top: 2em;
  border-top: 1px solid #999;
  padding-top: 1em;
}}

/* ── 本文 ── */
h2.ep-title {{
  font-size: 1.3em;
  font-weight: bold;
  margin-bottom: 1.5em;
  border-bottom: 1px solid #ccc;
  padding-bottom: 0.3em;
}}

p.body-line {{
  margin: 0;
  text-indent: 1em;
}}

p.body-blank {{
  margin: 0;
  height: 1em;
}}

/* ── 本文内見出し（青空文庫 大見出し・中見出し・小見出し） ── */
p.midashi-oo {{
  font-size: 1.1em;
  font-weight: bold;
  text-indent: 0;
  margin: 1em 0;
  text-align: center;
}}

p.midashi-naka {{
  font-size: 1.0em;
  font-weight: bold;
  text-indent: 0;
  margin: 0.8em 0;
}}

p.midashi-sho {{
  font-size: 0.95em;
  font-weight: bold;
  text-indent: 0;
  margin: 0.5em 0;
}}

/* ── 目次（toc.xhtml） ── */
#toc ol {{
  list-style: decimal;
}}
#toc li.toc-prelim {{
  list-style: none;
}}
#toc li.toc-chapter {{
  list-style: none;
  margin-top: 0.8em;
  margin-bottom: 0.2em;
}}
#toc li.toc-chapter > a {{
  font-weight: bold;
  font-size: 0.95em;
}}

/* ── 奥付 ── */
.colophon {{
  font-size: 0.85em;
  border-top: 1px solid #999;
  padding-top: 1em;
  margin-top: 2em;
}}

/* ── リンク共通 ── */
a {{
  color: #4a6fa5;
  text-decoration: underline;
}}

a:visited {{
  color: #7a5fa5;
}}

/* 表紙ページのソースリンク */
.cover-source {{
  font-size: 0.85em;
  margin-top: 2em;
  text-align: center;
}}

/* ── 字下げ（青空文庫書式対応） ── */
/* ここからN字下げ: ブロック内の各段落テキストを先頭字下げなしで均一配置 */
div.aozora-indent > p.body-line,
div.aozora-indent > p.body-blank {{
  text-indent: 0;
}}
div.aozora-indent-1em  {{ padding-top: 1em;  }}
div.aozora-indent-2em  {{ padding-top: 2em;  }}
div.aozora-indent-3em  {{ padding-top: 3em;  }}
div.aozora-indent-4em  {{ padding-top: 4em;  }}
div.aozora-indent-5em  {{ padding-top: 5em;  }}
div.aozora-indent-6em  {{ padding-top: 6em;  }}
div.aozora-indent-7em  {{ padding-top: 7em;  }}
div.aozora-indent-8em  {{ padding-top: 8em;  }}
div.aozora-indent-9em  {{ padding-top: 9em;  }}
div.aozora-indent-10em {{ padding-top: 10em; }}

/* 改行天付き、折り返してN字下げ: 初行は天付き（indent 0）、折り返し行はN字下げ */
div.aozora-hanging-1em  {{ padding-top: 1em;  }}
div.aozora-hanging-1em  > p.body-line {{ text-indent: -1em;  }}
div.aozora-hanging-2em  {{ padding-top: 2em;  }}
div.aozora-hanging-2em  > p.body-line {{ text-indent: -2em;  }}
div.aozora-hanging-3em  {{ padding-top: 3em;  }}
div.aozora-hanging-3em  > p.body-line {{ text-indent: -3em;  }}
div.aozora-hanging-4em  {{ padding-top: 4em;  }}
div.aozora-hanging-4em  > p.body-line {{ text-indent: -4em;  }}
div.aozora-hanging-5em  {{ padding-top: 5em;  }}
div.aozora-hanging-5em  > p.body-line {{ text-indent: -5em;  }}
div.aozora-hanging-6em  {{ padding-top: 6em;  }}
div.aozora-hanging-6em  > p.body-line {{ text-indent: -6em;  }}
div.aozora-hanging-7em  {{ padding-top: 7em;  }}
div.aozora-hanging-7em  > p.body-line {{ text-indent: -7em;  }}
div.aozora-hanging-8em  {{ padding-top: 8em;  }}
div.aozora-hanging-8em  > p.body-line {{ text-indent: -8em;  }}
div.aozora-hanging-9em  {{ padding-top: 9em;  }}
div.aozora-hanging-9em  > p.body-line {{ text-indent: -9em;  }}
div.aozora-hanging-10em {{ padding-top: 10em; }}
div.aozora-hanging-10em > p.body-line {{ text-indent: -10em; }}

/* ── 縦中横（DPFJガイド準拠） ── */
.tcy {{
  -webkit-text-combine: horizontal;
  text-combine-upright: all;
  -epub-text-combine: horizontal;
}}

/* ── 図・イラスト（青空文庫 挿絵対応） ── */
p.illustration,
figure.illustration {{
  text-indent: 0;
  margin: 0.8em 0;
  text-align: center;
}}
img.illustration {{
  max-width: 100%;
}}
p.caption,
figcaption.caption {{
  font-size: 0.9em;
  text-indent: 0;
  text-align: center;
  margin-top: 0.3em;
}}

/* ── 横書き時の字下げ上書き（html.hltr スコープ） ── */
/* 縦書きでは padding-top が行送り方向の字下げになるが、横書きでは padding-left を使う */
html.hltr div.aozora-indent-1em  {{ padding-top: 0; padding-left: 1em;  }}
html.hltr div.aozora-indent-2em  {{ padding-top: 0; padding-left: 2em;  }}
html.hltr div.aozora-indent-3em  {{ padding-top: 0; padding-left: 3em;  }}
html.hltr div.aozora-indent-4em  {{ padding-top: 0; padding-left: 4em;  }}
html.hltr div.aozora-indent-5em  {{ padding-top: 0; padding-left: 5em;  }}
html.hltr div.aozora-indent-6em  {{ padding-top: 0; padding-left: 6em;  }}
html.hltr div.aozora-indent-7em  {{ padding-top: 0; padding-left: 7em;  }}
html.hltr div.aozora-indent-8em  {{ padding-top: 0; padding-left: 8em;  }}
html.hltr div.aozora-indent-9em  {{ padding-top: 0; padding-left: 9em;  }}
html.hltr div.aozora-indent-10em {{ padding-top: 0; padding-left: 10em; }}

html.hltr div.aozora-hanging-1em  {{ padding-top: 0; padding-left: 1em;  }}
html.hltr div.aozora-hanging-1em  > p.body-line {{ text-indent: -1em;  }}
html.hltr div.aozora-hanging-2em  {{ padding-top: 0; padding-left: 2em;  }}
html.hltr div.aozora-hanging-2em  > p.body-line {{ text-indent: -2em;  }}
html.hltr div.aozora-hanging-3em  {{ padding-top: 0; padding-left: 3em;  }}
html.hltr div.aozora-hanging-3em  > p.body-line {{ text-indent: -3em;  }}
html.hltr div.aozora-hanging-4em  {{ padding-top: 0; padding-left: 4em;  }}
html.hltr div.aozora-hanging-4em  > p.body-line {{ text-indent: -4em;  }}
html.hltr div.aozora-hanging-5em  {{ padding-top: 0; padding-left: 5em;  }}
html.hltr div.aozora-hanging-5em  > p.body-line {{ text-indent: -5em;  }}
html.hltr div.aozora-hanging-6em  {{ padding-top: 0; padding-left: 6em;  }}
html.hltr div.aozora-hanging-6em  > p.body-line {{ text-indent: -6em;  }}
html.hltr div.aozora-hanging-7em  {{ padding-top: 0; padding-left: 7em;  }}
html.hltr div.aozora-hanging-7em  > p.body-line {{ text-indent: -7em;  }}
html.hltr div.aozora-hanging-8em  {{ padding-top: 0; padding-left: 8em;  }}
html.hltr div.aozora-hanging-8em  > p.body-line {{ text-indent: -8em;  }}
html.hltr div.aozora-hanging-9em  {{ padding-top: 0; padding-left: 9em;  }}
html.hltr div.aozora-hanging-9em  > p.body-line {{ text-indent: -9em;  }}
html.hltr div.aozora-hanging-10em {{ padding-top: 0; padding-left: 10em; }}
html.hltr div.aozora-hanging-10em > p.body-line {{ text-indent: -10em; }}
"""

_XHTML_TMPL = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="ja" lang="ja"
      class="{html_class}">
<head>
  <meta charset="UTF-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="css/novel.css"/>
</head>
<body{epub_type}>
{body}
</body>
</html>
"""



# ルビベースとして使用できない文構造上の句読点・括弧類。
# クラス9の文字でも ＆ ♪ ★ 等のシンボル文字はルビベース可。
# 自動検出パス（パイプなし《》）でのみ使用する。
_PUNCT_NO_RUBY_BASE = frozenset(
    '。、！？…‥・「」『』（）【】〈〉《》：；―—–\u30fb\uff0e\uff0c\uff01\uff1f'
)


def _char_class(ch: str) -> int:
    """
    文字種を整数で返す（ルビ開始境界の自動判別に使用）。
    同じ値が連続する範囲を「同一文字種ブロック」として扱う。

    0: 漢字（CJK統合漢字・互換漢字・拡張領域）
    1: ひらがな
    2: カタカナ（半角カタカナを含む）
    3: 半角英字
    4: 半角数字
    5: 半角空白・記号
    6: 全角英字
    7: 全角数字
    8: 全角空白・その他記号
    9: 句読点・括弧・記号類（ルビベース不可）
   10: 上記以外のUnicode文字（キリル・ギリシャ文字等、ルビベース可）
    """
    cp = ord(ch)
    # 漢字（CJK統合漢字、互換漢字、拡張A/B/C/D/E/F）
    if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2CEAF
            or 0xF900 <= cp <= 0xFAFF):
        return 0
    # 青空文庫書式規定で漢字扱いとする特殊記号
    # 々(U+3005)=繰り返し、仝(U+4EDD)=同じ、〆(U+3006)=しめ、〇(U+3007)=零、ヶ(U+30F6)=ケ
    # ※仝はCJK範囲(0x4EDD)に含まれ上記で先にclass0になるが明示的に列挙
    if ch in '々仝〆〇ヶ':
        return 0
    # ひらがな
    if 0x3041 <= cp <= 0x309F:
        return 1
    # カタカナ（全角・半角）
    if 0x30A0 <= cp <= 0x30FF or 0xFF65 <= cp <= 0xFF9F:
        return 2
    # 半角英字
    if 0x0041 <= cp <= 0x005A or 0x0061 <= cp <= 0x007A:
        return 3
    # 半角数字
    if 0x0030 <= cp <= 0x0039:
        return 4
    # 半角空白・ASCII記号
    if 0x0020 <= cp <= 0x007E:
        return 5
    # 全角英字
    if 0xFF21 <= cp <= 0xFF3A or 0xFF41 <= cp <= 0xFF5A:
        return 6
    # 全角数字
    if 0xFF10 <= cp <= 0xFF19:
        return 7
    # 全角空白
    if cp == 0x3000:
        return 8
    # キリル・ギリシャ文字等 Unicode 文字（Letter/Number/Mark カテゴリ）
    # → ルビベースとして有効なため class 9 とは区別する
    if unicodedata.category(ch)[0] in ('L', 'N', 'M'):
        return 10
    # 句読点・括弧・記号等（ルビベース不可）
    return 9


def _resolve_ruby_base(preceding: str) -> tuple[str, str]:
    """
    ルビ記号（《》）直前の文字列 preceding から、
    ルビが掛かるベース文字列と、その前の残余テキストを返す。

    ルール:
      - preceding の末尾から文字種が同一である連続ブロックをベースとする
      - ただし「その他(9)」は直前の文字種ブロックと合成しない
        （句読点等がルビベースに含まれないようにするため）

    戻り値: (before, base)
      before : ルビより前の残余テキスト
      base   : ルビのベース文字列
    """
    if not preceding:
        return "", ""
    # 末尾の文字種を基準にして同種ブロックを取り出す
    end_cls = _char_class(preceding[-1])
    i = len(preceding) - 1
    while i > 0 and _char_class(preceding[i - 1]) == end_cls:
        i -= 1
    return preceding[:i], preceding[i:]


def _ruby_needs_pipe(base: str, preceding: str = "", yomi: str = "") -> bool:
    """
    ルビのベース文字列に | を前置する必要があるか判定する。

    以下のいずれかの場合に True を返す:
    1. yomi（ルビテキスト）に漢字が含まれる
       （漢字ルビは _apply_ruby_auto の自動判別で地の文扱いされるため、
         スクレイパー段階で必ずパイプを付けて明示する）
    2. base が複数の文字種を含む
       （_resolve_ruby_base は末尾文字種のブロックしか取れないため、
         「俺以外の」→「の」のみになる）
    3. preceding の末尾文字が base[-1] と同じ文字種
       （自動検出が直前テキストまで延びる; 「氷村心白」→「氷村心白」全体になる）
    4. base の末尾文字がクラス9（記号・句読点）
       （_apply_ruby_auto の自動検出では文構造句読点として地の文扱いになる場合が
         あるため、スクレイパー段階でパイプを付けて明示する。
         例: ＆《アンド》）
    """
    if not base:
        return False
    if yomi and _has_kanji(yomi):
        return True
    end_cls = _char_class(base[-1])
    if end_cls == 9:
        return True
    if any(_char_class(ch) != end_cls for ch in base):
        return True
    if preceding and _char_class(preceding[-1]) == end_cls:
        return True
    return False


def _bs4_prev_text(tag) -> str:
    """
    BS4 タグの直前のテキストを返す（_ruby_needs_pipe の preceding 引数用）。
    直前の NavigableString またはタグのテキストを順に探す。
    """
    node = tag.previous_sibling
    while node is not None:
        if isinstance(node, str):
            if node:
                return node
        else:
            t = node.get_text()
            if t:
                return t
        node = node.previous_sibling
    return ""


def _has_kanji(text: str) -> bool:
    """テキスト内に漢字（CJK文字）が含まれるかを返す。"""
    return any(_char_class(ch) == 0 for ch in text)


def _apply_ruby_auto(text: str) -> str:
    """
    青空文庫ルビ記法を処理してXHTML ruby タグに変換する。

    - 明示記号あり: |ベース《よみ》  → <ruby>ベース<rt>よみ</rt></ruby>
    - 明示記号なし: ベース《よみ》   → 《》直前の同一文字種ブロックを
                                         自動検出してルビベースとする

    ルビでない《》の判定（地の文として《》をそのまま出力）:
      - 《》内に漢字が含まれる場合（例: 《この部屋に誰かが潜んでいる》）
      - 有効なルビベースが見つからない場合（行頭・句読点直後など）

    テキストは _esc() 済みを想定しない（この関数内でエスケープする）。
    """
    result = []
    # パターン: ([|｜]ベース《よみ》) または (ベース《よみ》)
    # ASCII "|" と全角 "｜" の両方をルビ開始記号として認識する
    pattern = re.compile(r"[|｜]([^《|｜]+)《([^》]+)》|《([^》]+)》")
    pos = 0
    for m in pattern.finditer(text):
        chunk = text[pos:m.start()]
        if m.group(1) is not None:
            # "|ベース《よみ》" 形式：明示的ルビ指定はそのまま適用
            result.append(_esc(chunk))
            result.append(
                f"<ruby>{_esc(m.group(1))}<rt>{_esc(m.group(2))}</rt></ruby>"
            )
        else:
            yomi = m.group(3)
            # 《》内に漢字が含まれる → ルビではなく地の文
            if _has_kanji(yomi):
                result.append(_esc(chunk))
                result.append(_esc(f"《{yomi}》"))
            else:
                # "《よみ》" のみ：chunk の末尾から文字種境界でベースを切り出す
                before, base = _resolve_ruby_base(chunk)
                # ベースが文構造上の句読点・括弧類のみの場合は地の文扱い。
                # ＆ ♪ ★ 等のシンボル文字（クラス9だが _PUNCT_NO_RUBY_BASE 外）は
                # ルビベースとして有効とする。
                if base and all(ch in _PUNCT_NO_RUBY_BASE for ch in base):
                    base = ""
                    before = chunk
                result.append(_esc(before))
                if base:
                    result.append(
                        f"<ruby>{_esc(base)}<rt>{_esc(yomi)}</rt></ruby>"
                    )
                else:
                    # 有効なルビベースなし → 《》ごと地の文として出力
                    result.append(_esc(f"《{yomi}》"))
        pos = m.end()
    result.append(_esc(text[pos:]))
    return "".join(result)


# 青空文庫タグ処理用の正規表現（モジュールレベルで一度だけコンパイル）
# 見出し開始マーカー: ［＃「TEXT」は大見出し］ （終わりを含まない）
_MIDASHI_START_RE = re.compile(r"［＃「[^」]*」は(大|中|小)見出し］")
# 見出し終了マーカー: ［＃「TEXT」は大見出し終わり］
_MIDASHI_END_RE   = re.compile(r"［＃「[^」]*」は(大|中|小)見出し終わり］")
# 任意の青空文庫タグ（制御タグ除去用）
_AOZORA_ANY_TAG_RE = re.compile(r"［＃[^］]*］")
# 見出し CSS クラスマップ
_MIDASHI_CLASS = {"大": "midashi-oo", "中": "midashi-naka", "小": "midashi-sho"}

# 図・イラスト（青空文庫書式対応）
# キャプション付きは先にチェック（「の図」がキャプション付きにも含まれるため）
_FIG_CAP_RE = re.compile(
    r"［＃「([^」]*)」のキャプション付きの図（([^、）\s]+)(?:、横(\d+)×縦(\d+))?）入る］")
_FIG_PLAIN_RE = re.compile(
    r"［＃「([^」]*)」の図（([^、）\s]+)(?:、横(\d+)×縦(\d+))?）入る］")
_IS_CAPTION_LINE_RE  = re.compile(r".*［＃「[^」]*」はキャプション］")
_CAPTION_BLOCK_START_RE2 = re.compile(r"［＃ここからキャプション］")
_CAPTION_BLOCK_END_RE2   = re.compile(r"［＃ここでキャプション終わり］")
# 画像ファイル拡張子セット（ZIP 抽出用）
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"}

# 縦中横タグ: ［＃縦中横］TEXT［＃縦中横終わり］ → <span class="tcy">TEXT</span>
# センチネル経由で _apply_ruby_auto のエスケープと干渉しない形で変換する
_TCY_RE          = re.compile(r"［＃縦中横］(.*?)［＃縦中横終わり］")
_TCY_SENTINEL_RE = re.compile(r"\x00TCY\x01(.*?)\x00TCYEND\x01")
# テキストノード内の1-3桁の連続数字・1-3文字の半角英字（縦中横自動検出）
# 数字: (?<!\d)/(?!\d) で4桁以上（年号等）は対象外
# 英字: (?<![A-Za-z])/(?![A-Za-z]) で4文字以上の英単語は対象外
_TCY_DIGITS_RE   = re.compile(r"(?<!\d)\d{1,3}(?!\d)|(?<![A-Za-z])[A-Za-z]{1,3}(?![A-Za-z])")


def _apply_tcy_pre(text: str) -> str:
    """縦中横タグ内容をセンチネルに置換（_apply_ruby_auto 前に適用）。"""
    return _TCY_RE.sub(lambda m: f"\x00TCY\x01{m.group(1)}\x00TCYEND\x01", text)


def _apply_tcy_post(html: str) -> str:
    """センチネルを <span class="tcy"> に置換（_apply_ruby_auto 後に適用）。"""
    return _TCY_SENTINEL_RE.sub(
        lambda m: f'<span class="tcy">{m.group(1)}</span>', html
    )


def _auto_tcy_xhtml(html: str) -> str:
    """XHTML テキストノード内の2-3桁の連続数字を <span class="tcy"> でラップする。
    既存の tcy スパン内の数字は二重ラップしない。
    HTMLエンティティ（&#160; &amp; 等）は分割単位として保護し数値を誤変換しない。"""
    parts = re.split(r'(<[^>]+>|&#\d+;|&[a-zA-Z]+;)', html)
    out = []
    in_tcy = 0
    for part in parts:
        if not part:
            continue
        if part.startswith('<'):
            tag_lower = part.lower()
            if re.match(r'<span\b', tag_lower) and 'tcy' in tag_lower:
                in_tcy += 1
            elif tag_lower.startswith('</span') and in_tcy > 0:
                in_tcy -= 1
            out.append(part)
        elif part.startswith('&'):
            # HTMLエンティティ（&#160; &amp; 等）はそのまま素通し
            out.append(part)
        elif in_tcy > 0:
            out.append(part)
        else:
            out.append(_TCY_DIGITS_RE.sub(
                lambda m: f'<span class="tcy">{m.group()}</span>', part))
    return ''.join(out)


# 字下げ関連タグ（ここから〜 は単独行で使用）
# 改行天付き・折り返しN字下げは ここからN字下げ より先にチェックすること
_JISAGE_HANGING_RE = re.compile(
    r"［＃ここから改行天付き、折り返して([０-９一二三四五六七八九十\d]+)字下げ］")
_JISAGE_BLOCK_RE   = re.compile(
    r"［＃ここから([０-９一二三四五六七八九十\d]+)字下げ］")
_JISAGE_END_RE     = re.compile(r"［＃ここで字下げ終わり］")
_JISAGE_SINGLE_RE  = re.compile(
    r"^［＃([０-９一二三四五六七八九十\d]+)字下げ］")


def _jisage_to_int(s: str) -> int:
    """全角数字・漢数字を int に変換。変換できない場合は 1 を返す。"""
    s2 = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if s2.isdigit():
        return max(1, int(s2))
    kanji_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                 "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    n = sum(kanji_map.get(c, 0) for c in s2)
    return max(1, n) if n else 1


def _body_lines_to_xhtml(text: str, horizontal: bool = False) -> str:
    """
    本文テキスト（改行区切り）をXHTML要素列に変換する。

    - 空行                 → <p class="body-blank">
    - 通常行               → <p class="body-line">（青空文庫タグ除去・ルビ変換済み）
    - 大見出し行           → <p class="midashi-oo">
    - 中見出し行           → <p class="midashi-naka">
    - 小見出し行           → <p class="midashi-sho">

    青空文庫タグの処理:
      - 字下げ（N字下げ）・地付き等のレイアウトタグは全除去
      - 大/中/小見出しタグはインライン形式・ブロック形式の両方に対応
        インライン: TEXT［＃「TEXT」は大見出し］ → 同一行のTEXTを見出しとして出力
        ブロック:   ［＃「TEXT」は大見出し］     → 次の行をTEXTとして見出し出力
                    TEXT                          → 見出しテキスト行
                    ［＃「TEXT」は大見出し終わり］ → スキップ
      - その他の青空文庫タグは除去して地の文として扱う
    """
    result = []
    pending_heading    = None   # ブロック形式の見出し待ち: None or "大"/"中"/"小"
    indent_stack: list = []     # 字下げスタック: ("indent"|"hanging", n)
    pending_fig_html   = None   # キャプション付き図の <img> タグ（キャプション行待ち）
    in_caption_block   = False  # ここからキャプション〜ここでキャプション終わり 収集中
    caption_block_lines: list = []

    for raw in text.split("\n"):
        line = _apply_tcy_pre(raw.rstrip())

        # ── 複数行キャプション収集中 ──
        if in_caption_block:
            if _CAPTION_BLOCK_END_RE2.search(line):
                cap_html = "\n".join(
                    f'<p class="caption">{_apply_ruby_auto(_AOZORA_ANY_TAG_RE.sub("", l).strip())}</p>'
                    for l in caption_block_lines
                    if _AOZORA_ANY_TAG_RE.sub("", l).strip()
                )
                if pending_fig_html is not None:
                    result.append(
                        f'<figure class="illustration">{pending_fig_html}'
                        f'<figcaption class="caption">{cap_html}</figcaption></figure>')
                    pending_fig_html = None
                in_caption_block = False
                caption_block_lines = []
            else:
                caption_block_lines.append(line)
            continue

        # ── キャプション待ち（キャプション付き図の次行以降）──
        if pending_fig_html is not None:
            if _CAPTION_BLOCK_START_RE2.search(line):
                in_caption_block = True
                caption_block_lines = []
                continue
            if _IS_CAPTION_LINE_RE.search(line):
                cap_text = _apply_ruby_auto(_AOZORA_ANY_TAG_RE.sub("", line).strip())
                result.append(
                    f'<figure class="illustration">{pending_fig_html}'
                    f'<figcaption class="caption">{cap_text}</figcaption></figure>')
                pending_fig_html = None
                continue
            # 予期しない行: キャプションなしで図を閉じ、この行は通常処理へ
            result.append(f'<p class="illustration">{pending_fig_html}</p>')
            pending_fig_html = None
            # fall through（この行を通常処理）

        # ── ブロック形式見出し待ち（前行が開始マーカーのみだった場合） ──
        if pending_heading is not None:
            # 終了マーカー行が来た場合はスキップして待ちをリセット
            if _MIDASHI_END_RE.search(line):
                pending_heading = None
                continue
            if not line:
                result.append('<p class="body-blank">&#160;</p>')
                continue  # 空行でも待ち継続
            # この行が見出しテキスト
            cls     = _MIDASHI_CLASS[pending_heading]
            visible = _AOZORA_ANY_TAG_RE.sub("", line).strip()
            if visible:
                result.append(f'<p class="{cls}">{_apply_ruby_auto(visible)}</p>')
            pending_heading = None
            continue

        # ── 字下げ終わり ──
        if _JISAGE_END_RE.search(line):
            if indent_stack:
                indent_stack.pop()
                result.append('</div>')
            continue

        # ── 字下げブロック開始（改行天付き・折り返し）──
        m_hang = _JISAGE_HANGING_RE.search(line)
        if m_hang:
            n = _jisage_to_int(m_hang.group(1))
            indent_stack.append(("hanging", n))
            result.append(f'<div class="aozora-hanging aozora-hanging-{n}em">')
            continue

        # ── 字下げブロック開始（通常）──
        m_blk = _JISAGE_BLOCK_RE.search(line)
        if m_blk:
            n = _jisage_to_int(m_blk.group(1))
            indent_stack.append(("indent", n))
            result.append(f'<div class="aozora-indent aozora-indent-{n}em">')
            continue

        # ── 空行 ──
        if not line:
            result.append('<p class="body-blank">&#160;</p>')
            continue

        # ── 大/中/小見出し判定 ──
        start_m = _MIDASHI_START_RE.search(line)
        end_m   = _MIDASHI_END_RE.search(line)

        if start_m:
            level   = start_m.group(1)
            visible = _AOZORA_ANY_TAG_RE.sub("", line).strip()
            if visible:
                # インライン形式（字下げ等のタグを除去した可視テキストがある）
                cls = _MIDASHI_CLASS[level]
                result.append(f'<p class="{cls}">{_apply_ruby_auto(visible)}</p>')
            else:
                # 開始マーカーのみ → 次の行が見出しテキスト
                pending_heading = level
            continue

        if end_m:
            # 終了マーカーを除去した可視テキストがあれば見出しとして出力
            level   = end_m.group(1)
            visible = _AOZORA_ANY_TAG_RE.sub("", line).strip()
            if visible:
                cls = _MIDASHI_CLASS[level]
                result.append(f'<p class="{cls}">{_apply_ruby_auto(visible)}</p>')
            # 終了マーカーのみ行はスキップ
            continue

        # ── 図・イラスト ──
        m_fig_cap   = _FIG_CAP_RE.search(line)
        m_fig_plain = _FIG_PLAIN_RE.search(line)
        if m_fig_cap:
            alt, fname = m_fig_cap.group(1), m_fig_cap.group(2)
            w, h = m_fig_cap.group(3), m_fig_cap.group(4)
            size_attrs = (f' width="{w}" height="{h}"' if w and h else "")
            pending_fig_html = (
                f'<img class="illustration" src="images/{fname}"'
                f' alt="{_esc(alt)}"{size_attrs}/>')
            continue
        if m_fig_plain:
            alt, fname = m_fig_plain.group(1), m_fig_plain.group(2)
            w, h = m_fig_plain.group(3), m_fig_plain.group(4)
            size_attrs = (f' width="{w}" height="{h}"' if w and h else "")
            img_html = (
                f'<img class="illustration" src="images/{fname}"'
                f' alt="{_esc(alt)}"{size_attrs}/>')
            result.append(f'<p class="illustration">{img_html}</p>')
            continue

        # ── 単行字下げ（行頭に N字下げ タグ）──
        m_single = _JISAGE_SINGLE_RE.match(line)
        if m_single:
            n     = _jisage_to_int(m_single.group(1))
            clean = _AOZORA_ANY_TAG_RE.sub("", line).strip()
            if clean:
                result.append(
                    f'<p class="body-line" style="text-indent:{n}em;">'
                    f'{_apply_ruby_auto(clean)}</p>')
            else:
                result.append('<p class="body-blank">&#160;</p>')
            continue

        # ── 通常行：青空文庫タグを除去してルビ処理 ──
        clean = _AOZORA_ANY_TAG_RE.sub("", line)
        if not clean.strip():
            result.append('<p class="body-blank">&#160;</p>')
        else:
            result.append(f'<p class="body-line">{_apply_ruby_auto(clean)}</p>')

    # 未閉じの字下げブロックを閉じる（不正なテキストへの安全対策）
    for _ in indent_stack:
        result.append('</div>')
    # 未閉じのキャプション付き図を閉じる
    if pending_fig_html is not None:
        result.append(f'<p class="illustration">{pending_fig_html}</p>')

    # 縦中横センチネル→<span class="tcy"> 変換、および2-3桁数字の自動縦中横
    # 横書きモードでは縦中横は不要なのでスキップ
    if horizontal:
        return "\n".join(_apply_tcy_post(r) for r in result)
    return "\n".join(_auto_tcy_xhtml(_apply_tcy_post(r)) for r in result)


def _make_cover_xhtml(title: str, author: str, synopsis: str,
                      source_url: str = "", site_name: str = "",
                      horizontal: bool = False) -> str:
    """テキスト表紙XHTMLを生成する。底本URLをハイパーリンク付きで掲載する。"""
    syn_html = ""
    if synopsis:
        syn_lines = "\n".join(
            f'<p class="body-line">{_esc(l)}</p>' if l.strip()
            else '<p class="body-blank">&#160;</p>'
            for l in synopsis.split("\n")
        )
        syn_html = f'<div class="cover-synopsis">\n{syn_lines}\n</div>'

    source_html = ""
    if source_url:
        label = f'{_esc(site_name)}で読む' if site_name else _esc(source_url)
        source_html = (
            f'<div class="cover-source">'
            f'<a href="{_esc(source_url)}" epub:type="link">{label}</a>'
            f'</div>'
        )

    body = (
        f'<div class="cover-title">{_esc(title)}</div>\n'
        f'<div class="cover-author">{_esc(author)}</div>\n'
        f'{source_html}\n'
        f'{syn_html}'
    )
    return _XHTML_TMPL.format(title=_esc(title), body=body,
                               html_class="hltr" if horizontal else "vrtl",
                               epub_type='')


_VERTICAL_IMAGE_CSS = """\
@charset "UTF-8";

html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
}

body.fit_h {
  text-align: center;
}

span.img, figure.img {
  display: block;
  width: 100%;
  height: 100%;
  text-align: center;
  margin: 0;
  padding: 0;
}

span.img img, figure.img img {
  width: auto;
  height: 100%;
  display: inline-block;
  vertical-align: top;
}
"""


def _make_cover_image_xhtml(title: str, fmt: str = "jpg") -> str:
    """
    ePub3 標準準拠の表紙ページXHTMLを生成する。
      - 画像: images/cover.{fmt}（OEBPS/ からの相対パス）
      - epub:type="cover" を body に、epub:type="cover-image" を img に付与
      - CSS はインライン（別ファイル不要）
    """
    img_src = f"images/cover.{fmt}"
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="ja" lang="ja"
      class="hltr">
<head>
  <meta charset="UTF-8"/>
  <title>{_esc(title)}</title>
  <style type="text/css">
    html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; }}
    img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
  </style>
</head>
<body epub:type="cover">
  <img src="{img_src}" alt="{_esc(title)}" epub:type="cover-image"/>
</body>
</html>
"""


def _make_episode_xhtml(ep_title: str, body_text: str,
                        horizontal: bool = False) -> str:
    """1話分のXHTMLを生成する。"""
    body = (
        f'<h2 class="ep-title">{_esc(ep_title)}</h2>\n'
        + _body_lines_to_xhtml(body_text, horizontal=horizontal)
    )
    return _XHTML_TMPL.format(title=_esc(ep_title), body=body,
                               html_class="hltr" if horizontal else "vrtl",
                               epub_type='')


def _make_colophon_xhtml(title: str, source_url: str, site_name: str,
                         horizontal: bool = False) -> str:
    """奥付XHTMLを生成する。底本URLはハイパーリンクとして出力する。"""
    today = date.today().strftime("%Y年%m月%d日")
    url_link = (
        f'<a href="{_esc(source_url)}" epub:type="link">{_esc(source_url)}</a>'
    )
    # xmlns:epub を body に付与するため XHTML_TMPL を直接使わず個別生成
    body = (
        f'<div class="colophon">\n'
        f'<p class="body-line">底本：「{_esc(title)}」{_esc(site_name)}</p>\n'
        f'<p class="body-line">　　　{url_link}</p>\n'
        f'<p class="body-line">入力：novel_downloader.py</p>\n'
        f'<p class="body-line">校正：未校正</p>\n'
        f'<p class="body-line">作成：{_esc(today)}</p>\n'
        f'</div>'
    )
    return _XHTML_TMPL.format(title="奥付", body=body,
                               html_class="hltr" if horizontal else "vrtl",
                               epub_type='')


def _make_toc_xhtml(title: str, episodes: list, cover_fmt: str = "",
                    horizontal: bool = False) -> str:
    """読者向け目次XHTML（toc.xhtml）を生成する。
    縦組みで spine に含まれる実際に読む目次ページ。
    nav.xhtml（RS向け機械読み取り専用）とは別ファイル。
    episodes: list[str] または list[dict{"title", "body", "group"?}]
    """
    def _norm(ep):
        if isinstance(ep, str):
            return {"title": ep, "group": None}
        return {"title": ep.get("title", ""), "group": ep.get("group") or None}
    normalized = [_norm(ep) for ep in episodes]

    prelim_items = ['<li class="toc-prelim"><a href="cover.xhtml">タイトルページ</a></li>']
    if cover_fmt:
        prelim_items.insert(0, '<li class="toc-prelim"><a href="cover-image.xhtml">表紙</a></li>')

    ep_items  = []
    num       = 0
    prev_group = None
    for ep in normalized:
        num += 1
        group = ep["group"]
        if group is not None and group != prev_group:
            ep_items.append(
                f'<li class="toc-chapter"><a href="ep{num:04d}.xhtml">{_esc(group)}</a></li>'
            )
            prev_group = group
        ep_items.append(
            f'<li value="{num}"><a href="ep{num:04d}.xhtml">{_esc(ep["title"])}</a></li>'
        )

    back_items = ['<li class="toc-prelim"><a href="colophon.xhtml">奥付</a></li>']
    toc_str = "\n    ".join(prelim_items + ep_items + back_items)

    body = (
        f'<h2 class="ep-title">{_esc(title)}</h2>\n'
        f'<ol id="toc">\n'
        f'  {toc_str}\n'
        f'</ol>'
    )
    return _XHTML_TMPL.format(title="目次", body=body,
                               html_class="hltr" if horizontal else "vrtl",
                               epub_type='')


def _make_nav_xhtml(title: str, episodes: list, cover_fmt: str = "",
                    horizontal: bool = False) -> str:
    """ナビゲーションドキュメント（nav.xhtml）を生成する。
    表紙・タイトルページ・奥付はナンバリングなしのリンクのみ。
    本文エピソードは 1 から始まる番号付きリストで表示し、
    episodes 要素に "group" キーがある場合は章/部単位でネストした <ol> にまとめる。

    episodes: list[str] または list[dict{"title", "body", "group"?}]
    """
    # 各エピソードを {"title": str, "group": str|None} に正規化
    def _norm(ep):
        if isinstance(ep, str):
            return {"title": ep, "group": None}
        return {"title": ep.get("title", ""), "group": ep.get("group") or None}
    normalized = [_norm(ep) for ep in episodes]

    # 前付け（ナンバリングなし）
    prelim_items = []
    if cover_fmt:
        prelim_items.append('<li class="toc-prelim"><a href="cover-image.xhtml">表紙</a></li>')
    prelim_items.append('<li class="toc-prelim"><a href="cover.xhtml">タイトルページ</a></li>')
    prelim_items.append('<li class="toc-prelim"><a href="toc.xhtml">目次</a></li>')

    # 本文エピソード
    # group が変わったとき（None→名前付き、または別の名前付き）にフラットな章ヘッダー行を挿入し、
    # エピソード行はすべて同じインデントレベルに並べる（ネストした <ol> は使わない）。
    # value 属性は全話通しの連番（ep{n:04d}.xhtml に対応）を明示する。
    ep_items  = []
    num       = 0   # 通し番号（ファイル名 ep{n:04d}.xhtml の n）
    prev_group = None  # 直前の章グループ名（None = 未設定）

    for ep in normalized:
        num  += 1
        group = ep["group"]
        # 新しい章グループに切り替わったときのみヘッダー行を挿入
        # ePub3 nav の <li> は <a> か (<span>+<ol>) のみ許可されるため、
        # 章ヘッダーはその章の先頭エピソードへのリンク (<a>) として出力する
        if group is not None and group != prev_group:
            ep_items.append(f'<li class="toc-chapter"><a href="ep{num:04d}.xhtml">{_esc(group)}</a></li>')
            prev_group = group
        ep_items.append(
            f'<li value="{num}"><a href="ep{num:04d}.xhtml">{_esc(ep["title"])}</a></li>'
        )

    # 後付け（ナンバリングなし）
    back_items = ['<li class="toc-prelim"><a href="colophon.xhtml">奥付</a></li>']

    toc_str = "\n    ".join(prelim_items + ep_items + back_items)

    # landmarks: カバー・本文開始・目次をリーダーが認識するための必須ナビ
    cover_href = "cover-image.xhtml" if cover_fmt else "cover.xhtml"
    body_start = "ep0001.xhtml" if episodes else "cover.xhtml"
    landmarks = f"""\
<nav epub:type="landmarks" id="landmarks">
  <ol>
    <li><a epub:type="cover"       href="{cover_href}">表紙</a></li>
    <li><a epub:type="toc"         href="toc.xhtml">目次</a></li>
    <li><a epub:type="bodymatter"  href="{body_start}">本文</a></li>
  </ol>
</nav>"""

    _nav_class = "hltr" if horizontal else "vrtl"
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="ja" lang="ja"
      class="{_nav_class}">
<head><meta charset="UTF-8"/><title>{_esc(title)}</title>
<link rel="stylesheet" type="text/css" href="css/novel.css"/>
<style>
  #toc ol {{ list-style: decimal; }}
  #toc li.toc-prelim {{ list-style: none; }}
  #toc li.toc-chapter {{ list-style: none; margin-top: 0.8em; margin-bottom: 0.2em; }}
  #toc li.toc-chapter > a {{ font-weight: bold; font-size: 0.95em; }}
</style>
</head>
<body>
<nav epub:type="toc" id="toc">
  <h1>目次</h1>
  <ol>
    {toc_str}
  </ol>
</nav>
{landmarks}
</body>
</html>
"""


def _make_opf(title: str, author: str, book_id: str, ep_titles: list,
              cover_fmt: str = "", font_filename: str = "",
              toc_at_end: bool = False,
              inline_images: list = None,
              synopsis: str = "",
              horizontal: bool = False) -> str:
    """
    OPF（package.opf）を生成する。
    cover_fmt: "png" | "svg" | "" (表紙画像なし)
    font_filename: 埋め込みフォントのファイル名（例: "AyatiShowaSerif-Regular.otf"）
    toc_at_end: True のとき目次を奥付の後に配置（デフォルト: 表紙の後・本文の前）
    inline_images: 本文中のインライン画像ファイル名リスト（青空文庫 ZIP 内の画像等）
    synopsis: あらすじ（dc:description に設定）
    """
    today    = date.today().strftime("%Y-%m-%d")
    now_iso  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="css" href="css/novel.css" media-type="text/css"/>',
    ]

    if font_filename:
        ext = Path(font_filename).suffix.lower()
        mime_map = {".otf": "font/otf", ".ttf": "font/ttf",
                    ".woff": "font/woff", ".woff2": "font/woff2"}
        font_mime = mime_map.get(ext, "font/otf")
        manifest_items.append(
            f'<item id="embedded-font" href="fonts/{font_filename}"'
            f' media-type="{font_mime}"/>'
        )

    if cover_fmt == "jpg":
        manifest_items += [
            '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
            '<item id="cover-page" href="cover-image.xhtml" media-type="application/xhtml+xml"/>',
        ]
    elif cover_fmt == "png":
        manifest_items += [
            '<item id="cover-image" href="images/cover.png" media-type="image/png" properties="cover-image"/>',
            '<item id="cover-page" href="cover-image.xhtml" media-type="application/xhtml+xml"/>',
        ]
    elif cover_fmt == "svg":
        manifest_items += [
            '<item id="cover-image" href="images/cover.svg" media-type="image/svg+xml" properties="cover-image"/>',
            '<item id="cover-page" href="cover-image.xhtml" media-type="application/xhtml+xml"/>',
        ]

    manifest_items.append(
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
    )

    spine_items = []
    if cover_fmt:
        # 縦書き（RTL）は表紙を右ページに固定。横書き（LTR）はページスプレッド指定不要
        cover_spread = ('' if horizontal
                        else ' properties="page-spread-right"')
        spine_items.append(f'<itemref idref="cover-page" linear="yes"{cover_spread}/>')
    spine_items.append('<itemref idref="cover"/>')

    # 読者向け目次（toc.xhtml）を前配置（デフォルト）: 表紙の直後・本文の前
    if not toc_at_end:
        spine_items.append('<itemref idref="toc"/>')

    for i, _ in enumerate(ep_titles):
        n = i + 1
        manifest_items.append(
            f'<item id="ep{n:04d}" href="ep{n:04d}.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="ep{n:04d}"/>')
    manifest_items.append(
        '<item id="colophon" href="colophon.xhtml" media-type="application/xhtml+xml"/>'
    )
    spine_items.append('<itemref idref="colophon"/>')

    # 読者向け目次（toc.xhtml）を後配置（--toc-at-end）: 奥付の後
    if toc_at_end:
        spine_items.append('<itemref idref="toc"/>')

    # nav.xhtml は spine に含めない（properties="nav" のみで RS が認識、DPFJガイド準拠）

    # インライン画像（青空文庫 ZIP 内の挿絵等）を manifest に追加
    if inline_images:
        _img_mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".gif": "image/gif", ".bmp": "image/bmp", ".svg": "image/svg+xml"}
        for img_name in inline_images:
            ext = Path(img_name).suffix.lower()
            mime = _img_mime.get(ext, "image/png")
            # XML id として使えるよう英数字以外をアンダーバーに置換し先頭に "img-" を付与
            img_id = "img-" + re.sub(r"[^a-zA-Z0-9_-]", "_", img_name)
            manifest_items.append(
                f'<item id="{img_id}" href="images/{img_name}" media-type="{mime}"/>'
            )

    manifest_str = "\n    ".join(manifest_items)
    spine_str    = "\n    ".join(spine_items)
    cover_meta   = ('\n    <meta name="cover" content="cover-image"/>' if cover_fmt else "")
    desc_meta    = (f"\n    <dc:description>{_esc(synopsis)}</dc:description>" if synopsis else "")
    # 縦書き: iPad/iOS Kindle 縦書き対応のため primary-writing-mode を明示。横書きは不要
    writing_mode_meta = (
        "" if horizontal
        else '\n    <meta name="primary-writing-mode" content="horizontal-rl"/>'
    )
    page_dir = "ltr" if horizontal else "rtl"

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         version="3.0"
         unique-identifier="book-id"
         xml:lang="ja">

  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{_esc(title)}</dc:title>
    <dc:creator id="creator">{_esc(author)}</dc:creator>
    <meta refines="#creator" property="role" scheme="marc:relators">aut</meta>
    <dc:language>ja</dc:language>
    <dc:date>{today}</dc:date>{desc_meta}
    <meta property="dcterms:modified">{now_iso}</meta>{cover_meta}
    <meta property="rendition:layout">reflowable</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">none</meta>{writing_mode_meta}
  </metadata>

  <manifest>
    {manifest_str}
  </manifest>

  <spine page-progression-direction="{page_dir}">
    {spine_str}
  </spine>

</package>
"""


# ── フォントパス（Pillow用）─ 起動時に日本語グリフを持つフォントを自動探索 ──
_COVER_W, _COVER_H = 800, 1200

def _find_cjk_fonts() -> tuple:
    """
    日本語グリフを持つ TTC/OTF/TTF フォントを優先順で探して
    (bold_path, bold_index, medium_path, medium_index) を返す。
    見つからなければ (None, 0, None, 0)。

    探索順:
      1. fc-list コマンドで日本語対応フォントを列挙（Linux/macOS）
      2. OS別既知ディレクトリをグロブで再帰検索
      3. matplotlib の FontManager を利用（インストール済みの場合）
    """
    import os
    import glob
    import subprocess

    # ── 探索ディレクトリ（再帰検索） ──────────────────────────────
    search_dirs = [
        # Linux: opentype / truetype
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.local/share/fonts"),
        os.path.expanduser("~/.fonts"),
        # macOS
        "/Library/Fonts",
        "/System/Library/Fonts",
        os.path.expanduser("~/Library/Fonts"),
        # Windows
        r"C:\Windows\Fonts",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
    ]

    def glob_find(pattern: str) -> str | None:
        """パターン（glob可）でフォントファイルを再帰検索し、最初のヒットを返す。"""
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            # まず直下を探し、次にサブディレクトリを再帰探索
            for hit in (glob.glob(os.path.join(d, pattern))
                        + glob.glob(os.path.join(d, "**", pattern), recursive=True)):
                if os.path.isfile(hit):
                    return hit
        return None

    # ── fc-list による探索（Linux / macOS） ────────────────────────
    def fclist_find_jp() -> list[str]:
        """fc-list :lang=ja でパスを列挙して返す。"""
        try:
            out = subprocess.check_output(
                ["fc-list", ":lang=ja", "--format=%{file}\n"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode("utf-8", errors="replace")
            return [p.strip() for p in out.splitlines() if p.strip()]
        except Exception:
            return []

    # ── matplotlib FontManager による探索 ─────────────────────────
    def mpl_find(name_keywords: list[str]) -> str | None:
        """matplotlib.font_manager でキーワードを含むフォントパスを返す。"""
        try:
            from matplotlib import font_manager as fm
            for entry in fm.fontManager.ttflist:
                low = entry.name.lower()
                if any(kw.lower() in low for kw in name_keywords):
                    if os.path.isfile(entry.fname):
                        return entry.fname
        except Exception:
            pass
        return None

    # ── TTCフェイスのJPインデックスを判定 ─────────────────────────
    def jp_index(path: str) -> int:
        """
        TTCファイルに含まれるフェイスのうち "JP" を名前に含むものの
        インデックスを返す。見つからなければ 0。
        """
        try:
            from PIL import ImageFont
            for i in range(20):
                try:
                    f = ImageFont.truetype(path, 12, index=i)
                    name = f.getname()[0].upper()
                    if "JP" in name:
                        return i
                except Exception:
                    break
        except Exception:
            pass
        return 0  # TTCでも index=0 が JP の場合が多い

    # ── 候補リスト: (boldパターン, mediumパターン) ────────────────
    # ファイル名はワイルドカード可。None は bold と同じパスを流用。
    CANDIDATES: list[tuple[str, str | None]] = [
        # Noto Serif CJK（明朝体・推奨）
        ("NotoSerifCJK-Bold.ttc",      "NotoSerifCJK-Medium.ttc"),
        ("NotoSerifCJK-Black.ttc",     "NotoSerifCJK-Regular.ttc"),
        ("Noto Serif CJK JP Bold.ttf", "Noto Serif CJK JP Regular.ttf"),
        # Noto Sans CJK（ゴシック体）
        ("NotoSansCJK-Bold.ttc",       "NotoSansCJK-Medium.ttc"),
        ("NotoSansCJK-Black.ttc",      "NotoSansCJK-Regular.ttc"),
        ("Noto Sans CJK JP Bold.ttf",  "Noto Sans CJK JP Regular.ttf"),
        # IPAex（日本語専用フリーフォント）
        ("ipaexg.ttf",                 "ipaexg.ttf"),
        ("ipaexm.ttf",                 "ipaexm.ttf"),
        ("ipag.ttf",                   "ipag.ttf"),
        ("ipam.ttf",                   "ipam.ttf"),
        # 源ノ明朝 / Source Han Serif
        ("SourceHanSerif*Bold*.otf",   "SourceHanSerif*Regular*.otf"),
        ("SourceHanSerif*Bold*.ttf",   "SourceHanSerif*Regular*.ttf"),
        # 源ノ角ゴシック / Source Han Sans
        ("SourceHanSans*Bold*.otf",    "SourceHanSans*Regular*.otf"),
        # ── Windows 標準・Office付属フォント ──────────────────────
        # BIZ UDP明朝 (BIZ UD Mincho) - Windows 11標準明朝体
        ("BIZ-UDMINCHOM*.TTC",         "BIZ-UDMINCHOM*.TTC"),
        # 游明朝 (Yu Mincho) - Windows + Microsoft Office付属明朝体
        ("yumindb.ttf",                "yumin.ttf"),
        # MS 明朝 (MS Mincho / MS PMincho) - Windows標準明朝体（常備）
        ("MSMINCHOM*.TTC",             "MSMINCHOM*.TTC"),
        ("msmincho.ttc",               "msmincho.ttc"),
        # HGS明朝E / HGP明朝E - Microsoft Office付属
        ("HGSMINCE.TTC",               "HGSMINCE.TTC"),
        ("HGPMINCE.TTC",               "HGPMINCE.TTC"),
        # 游ゴシック (Yu Gothic) - Windows 8.1以降
        ("YuGothB.ttc",                "YuGothM.ttc"),
        ("yugothb.ttf",                "yugothr.ttf"),
        # MS ゴシック (MS Gothic) - Windows標準ゴシック体（常備）
        ("msgothic.ttc",               "msgothic.ttc"),
        # Meiryo - Windows Vista以降
        ("meiryob.ttc",                "meiryo.ttc"),
        # ── 最終手段 ──────────────────────────────────────────────
        # WenQuanYi（Linux）
        ("wqy-zenhei.ttc",             "wqy-zenhei.ttc"),
        ("wqy-microhei.ttc",           "wqy-microhei.ttc"),
    ]

    # fc-list で日本語フォントのパスを取得しておく
    jp_paths = fclist_find_jp()

    def _resolve(pattern: str, fallback: str | None = None) -> tuple[str, int] | tuple[None, int]:
        """
        1) glob_find でファイルを探す
        2) 見つからなければ fc-list 結果からファイル名でマッチ
        3) それも失敗なら None
        """
        # glob にワイルドカードが含まれる場合は glob_find が対応
        path = glob_find(pattern)
        if path is None and jp_paths:
            # fc-list の結果からベース名でマッチ（ワイルドカードなし部分を使用）
            bare = pattern.replace("*", "").lower()
            for p in jp_paths:
                if bare in os.path.basename(p).lower():
                    path = p
                    break
        if path is None:
            return None, 0
        ext = os.path.splitext(path)[1].lower()
        idx = jp_index(path) if ext == ".ttc" else 0
        return path, idx

    bold_path = bold_idx = medium_path = medium_idx = None
    for bold_pat, med_pat in CANDIDATES:
        bp, bi = _resolve(bold_pat)
        if bp is None:
            continue
        if med_pat:
            mp, mi = _resolve(med_pat)
            if mp is None:
                mp, mi = bp, bi   # medium が見つからなければ bold で代替
        else:
            mp, mi = bp, bi
        bold_path, bold_idx     = bp, bi
        medium_path, medium_idx = mp, mi
        break

    # グロブ・fc-list で見つからなかった場合は matplotlib で最終試行
    if bold_path is None:
        for kws in [
            ["noto serif cjk", "jp"], ["noto sans cjk", "jp"],
            ["ipaex"], ["source han serif"], ["wenquanyi"],
            # Windows フォント
            ["biz ud mincho"], ["biz udp mincho"],
            ["yu mincho"], ["yumin"],
            ["ms mincho"], ["ms pmincho"],
            ["hgs mincho"], ["hgp mincho"],
            ["yu gothic"], ["ms gothic"],
            ["meiryo"],
        ]:
            p = mpl_find(kws)
            if p:
                bold_path = medium_path = p
                ext = os.path.splitext(p)[1].lower()
                bold_idx = medium_idx = jp_index(p) if ext == ".ttc" else 0
                break

    return bold_path, bold_idx, medium_path, medium_idx

_FONT_BOLD_PATH, _FONT_BOLD_IDX, _FONT_MEDIUM_PATH, _FONT_MEDIUM_IDX = _find_cjk_fonts()

if _FONT_BOLD_PATH:
    _b = os.path.basename(_FONT_BOLD_PATH)
    _m = os.path.basename(_FONT_MEDIUM_PATH) if _FONT_MEDIUM_PATH else _b
    print(f"[情報] 日本語フォント検出: bold={_b}[{_FONT_BOLD_IDX}]  medium={_m}[{_FONT_MEDIUM_IDX}]")
else:
    print(
        "[警告] 日本語フォントが見つかりませんでした。JPEG表紙はSVGで代替されます。\n"
        "       フォントをインストールすると JPEG 表紙が生成されます:\n"
        "       [Linux]   sudo apt install fonts-noto-cjk\n"
        "                 または: sudo apt install fonts-ipafont\n"
        "       [Windows] BIZ UDP明朝 / MS明朝 / 游明朝 など日本語フォントが\n"
        "                 C:\\Windows\\Fonts に存在するか確認してください。\n"
        "                 Microsoft Office をインストールすると游明朝が追加されます。"
    )


def _make_cover_svg(title: str, author: str, cover_bg: str = "#16234b") -> bytes:
    """
    Pillow不要のSVG表紙を生成する。
    標準ライブラリのみで動作するフォールバック。
    """
    W, H = 800, 1200

    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))

    # タイトルを折り返す（1行20文字目安）
    MAX_CH = 14
    t_lines = []
    buf = ""
    for ch in title:
        buf += ch
        if len(buf) >= MAX_CH:
            t_lines.append(buf)
            buf = ""
    if buf:
        t_lines.append(buf)

    title_fs  = 72
    title_y0  = int(H * 0.25)
    line_gap  = title_fs + 20
    title_els = "\n".join(
        f'  <text x="400" y="{title_y0 + i * line_gap}" '
        f'font-size="{title_fs}" fill="#fff8d7" '
        f'text-anchor="middle" font-family="serif" font-weight="bold">'
        f'{esc(l)}</text>'
        for i, l in enumerate(t_lines)
    )

    # 作者名は下飾り線(H*0.80)より下のエリア中央に固定配置
    LINE_Y2  = int(H * 0.80)
    BOTTOM   = H - 50   # 下枠内側
    author_y = LINE_Y2 + (BOTTOM - LINE_Y2) // 2 + 56 // 3
    author_el = (
        f'  <text x="400" y="{author_y}" '
        f'font-size="56" fill="#dccda8" '
        f'text-anchor="middle" font-family="serif">'
        f'{esc(author)}</text>'
    )

    _r0, _g0, _b0 = _parse_hex_color(cover_bg)
    _r1, _g1, _b1 = _darken_color(_r0, _g0, _b0)
    _color_top    = f"#{_r1:02x}{_g1:02x}{_b1:02x}"
    _color_bottom = f"#{_r0:02x}{_g0:02x}{_b0:02x}"

    svg = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="{_color_top}"/>
      <stop offset="100%" stop-color="{_color_bottom}"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <rect x="38" y="38" width="{W-76}" height="{H-76}" fill="none" stroke="#c8b482" stroke-width="3"/>
  <rect x="50" y="50" width="{W-100}" height="{H-100}" fill="none" stroke="#b4a06e" stroke-width="1"/>
  <line x1="68" y1="{int(H*0.14)}" x2="{W-68}" y2="{int(H*0.14)}" stroke="#c8b482" stroke-width="1"/>
  <line x1="68" y1="{int(H*0.80)}" x2="{W-68}" y2="{int(H*0.80)}" stroke="#c8b482" stroke-width="1"/>
{title_els}
{author_el}
</svg>"""
    return svg.encode("utf-8")


def make_cover_image(title: str, author: str, cover_bg: str = "#16234b"):
    """
    書籍表紙を模したカバー画像を生成してバイト列で返す。
    戻り値: (data: bytes, fmt: str)
      fmt = "jpg"  Pillow利用可能時（JPEG形式）
      fmt = "svg"  Pillowなし時のフォールバック
    例外は捕捉して SVG フォールバックに切り替える。
    """
    if _PILLOW_AVAILABLE:
        try:
            W, H = _COVER_W, _COVER_H
            img  = Image.new("RGB", (W, H))
            draw = ImageDraw.Draw(img)

            # 背景グラデーション（上: 暗め / 下: 指定色）
            _r0, _g0, _b0 = _parse_hex_color(cover_bg)
            _r1, _g1, _b1 = _darken_color(_r0, _g0, _b0)
            for y in range(H):
                t = y / H
                r = int(_r1 + (_r0 - _r1) * t)
                g = int(_g1 + (_g0 - _g1) * t)
                b = int(_b1 + (_b0 - _b1) * t)
                draw.line([(0, y), (W, y)], fill=(r, g, b))

            # 外枠（二重線）
            M    = 38
            GOLD     = (200, 180, 130)
            GOLD_DIM = (180, 160, 110)
            draw.rectangle([M,    M,    W-M,    H-M   ], outline=GOLD,     width=3)
            draw.rectangle([M+12, M+12, W-M-12, H-M-12], outline=GOLD_DIM, width=1)

            # レイアウト定数
            # LINE_Y1: タイトル領域の上端飾り線
            # LINE_Y2: タイトル領域の下端飾り線 ＝ 作者名エリアの上境界
            # 作者名は LINE_Y2 より下（下枠マージン内）に固定配置する
            LINE_Y1   = int(H * 0.14)
            LINE_Y2   = int(H * 0.80)
            AUTHOR_SZ = 56
            # 作者名エリア: LINE_Y2 ～ 下枠(H-M) の中央に配置
            # getbbox で ascent 分の余白を考慮し、視覚的中央を求める
            AUTHOR_AREA_TOP = LINE_Y2
            AUTHOR_AREA_BOT = H - M - 10          # 下枠内側ギリギリ
            draw.line([(M+30, LINE_Y1), (W-M-30, LINE_Y1)], fill=GOLD, width=1)
            draw.line([(M+30, LINE_Y2), (W-M-30, LINE_Y2)], fill=GOLD, width=1)

            def load_font(path, idx, size):
                """CJKフォントを読み込む。パスがNoneまたは失敗時はNoneを返す。"""
                if path is None:
                    return None
                try:
                    return ImageFont.truetype(path, size, index=idx)
                except Exception:
                    return None

            def wrap_text(text, font, max_w):
                lines, cur = [], ""
                for ch in text:
                    test = cur + ch
                    try:
                        w = font.getbbox(test)[2]
                    except Exception:
                        w = len(test) * (getattr(font, "size", 12))
                    if w > max_w:
                        lines.append(cur)
                        cur = ch
                    else:
                        cur = test
                if cur:
                    lines.append(cur)
                return lines

            max_title_w = W - M * 2 - 50
            # タイトル描画可能な縦幅（LINE_Y1 ～ LINE_Y2、上下に余白を確保）
            TITLE_PAD_TOP = int((LINE_Y2 - LINE_Y1) * 0.08)
            TITLE_PAD_BOT = int((LINE_Y2 - LINE_Y1) * 0.08)
            title_region_h = (LINE_Y2 - LINE_Y1) - TITLE_PAD_TOP - TITLE_PAD_BOT

            # CJKフォントが見つからない場合はSVGフォールバックへ
            if _FONT_BOLD_PATH is None:
                raise RuntimeError("CJK font not found")

            # タイトルが収まる最大フォントサイズを算出
            title_sz = 92
            while True:
                font_t = load_font(_FONT_BOLD_PATH, _FONT_BOLD_IDX, title_sz)
                if font_t is None:
                    raise RuntimeError("Failed to load bold font")
                lines  = wrap_text(title, font_t, max_title_w)
                if len(lines) * (title_sz + 18) <= title_region_h or title_sz <= 28:
                    break
                title_sz -= 4
            line_h = title_sz + 18
            # タイトルブロック全体を LINE_Y1～LINE_Y2 の中央に縦配置
            block_h   = len(lines) * line_h
            title_top = LINE_Y1 + TITLE_PAD_TOP + max(0, (title_region_h - block_h) // 2)
            for i, line in enumerate(lines):
                try:
                    lw = font_t.getbbox(line)[2]
                except Exception:
                    lw = len(line) * title_sz
                x = (W - lw) / 2
                y = title_top + i * line_h
                draw.text((x+3, y+3), line, font=font_t, fill=(0, 0, 0, 100))
                draw.text((x,   y  ), line, font=font_t, fill=(255, 248, 215))

            # ── 作者名：LINE_Y2 より下のエリア中央に固定配置 ──────────
            # 著者名が横幅に収まるようにフォントサイズを縮小
            author_sz = AUTHOR_SZ
            while author_sz >= 20:
                font_a = load_font(_FONT_MEDIUM_PATH, _FONT_MEDIUM_IDX, author_sz)
                if font_a is None:
                    font_a = font_t
                    break
                try:
                    _aw_test = font_a.getbbox(author)[2]
                except Exception:
                    _aw_test = len(author) * author_sz
                if _aw_test <= max_title_w:
                    break
                author_sz -= 4
            try:
                ab = font_a.getbbox(author)   # (left, top, right, bottom)
                aw = ab[2] - ab[0]
                ah = ab[3] - ab[1]
            except Exception:
                aw = len(author) * author_sz
                ah = author_sz
            ax = (W - aw) / 2
            # 作者名エリアの視覚的中央（ascent オフセットを補正）
            area_h = AUTHOR_AREA_BOT - AUTHOR_AREA_TOP
            ay = AUTHOR_AREA_TOP + (area_h - ah) / 2 - (ab[1] if 'ab' in locals() else 0)
            draw.text((ax+2, ay+2), author, font=font_a, fill=(0, 0, 0, 100))
            draw.text((ax,   ay  ), author, font=font_a, fill=(220, 205, 170))

            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=90, optimize=True)
            return buf.getvalue(), "jpg"

        except Exception as _png_err:
            import traceback as _tb
            print(
                "[警告] PillowでのJPEG表紙生成中にエラーが発生しました。SVGで代替します。\n"
                f"       エラー内容: {_png_err}\n"
                "       詳細:\n"
                + "".join(f"         {l}" for l in _tb.format_exc().splitlines(keepends=True))
            )

    # Pillow不在 or PNG生成失敗 → SVGフォールバック
    print(
        "[警告] SVGフォールバックで表紙を生成します。"
        "多くのePubリーダーではSVG表紙が正しく表示されない場合があります。"
    )
    return _make_cover_svg(title, author, cover_bg), "svg"


def build_epub(
    epub_path: str,
    title: str,
    author: str,
    synopsis: str,
    source_url: str,
    site_name: str,
    episodes: list,          # [{"title": str, "body": str}, ...]
    cover_bg: str = "#16234b",
    cover_image_path: str = "",  # ローカル表紙画像ファイルパス（JPEG/PNG）
    font_path: str = "",
    toc_at_end: bool = False,
    images: dict = None,     # {"filename.png": bytes} — 本文中のインライン画像
    horizontal: bool = False,  # True: 横書きePub3を生成
):
    """
    ePub3ファイルを生成する。horizontal=True で横書き、False（デフォルト）で縦書き。

    ePub3構造（画像表紙あり）:
      mimetype
      META-INF/container.xml
      OEBPS/package.opf
      OEBPS/nav.xhtml
      OEBPS/css/novel.css           ← 本文CSS
      OEBPS/css/vertical_image.css  ← 画像表紙専用CSS
      OEBPS/images/0000.png         ← 表紙画像
      OEBPS/cover-image.xhtml       ← 【spine先頭】画像表紙ページ
      OEBPS/cover.xhtml             ← テキスト表紙（タイトル・著者・あらすじ）
      OEBPS/ep0001.xhtml … ep{N}.xhtml
      OEBPS/colophon.xhtml
    """
    book_id   = str(uuid.uuid4())
    ep_titles = [ep["title"] for ep in episodes]

    # 表紙画像：外部ファイル指定があればそちらを使用、なければ自動生成
    if cover_image_path:
        if not os.path.isfile(cover_image_path):
            print(f"[警告] 表紙画像ファイルが見つかりません: {cover_image_path}")
            print("       自動生成の表紙を使用します。")
            cover_data, cover_fmt = make_cover_image(title, author, cover_bg)
        else:
            _ext = Path(cover_image_path).suffix.lower()
            if _ext in (".jpg", ".jpeg"):
                cover_fmt = "jpg"
            elif _ext == ".png":
                cover_fmt = "png"
            else:
                print(f"[警告] 非対応の画像形式です: {_ext}（対応: .jpg / .jpeg / .png）")
                print("       自動生成の表紙を使用します。")
                cover_data, cover_fmt = make_cover_image(title, author, cover_bg)
            if cover_fmt in ("jpg", "png"):
                with open(cover_image_path, "rb") as _f:
                    cover_data = _f.read()
                print(f"  表紙画像: {cover_image_path}")
    else:
        # 表紙画像を自動生成（Pillow利用可能時JPEG、なければSVGフォールバック）
        cover_data, cover_fmt = make_cover_image(title, author, cover_bg)

    # 埋め込みフォントの準備（CSS注入対策: " \ 改行を除去）
    if font_path and not os.path.isfile(font_path):
        print(f"[警告] フォントファイルが見つかりません: {font_path}")
        print("       埋め込みフォントなしで ePub を生成します。")
        font_path = ""
    _css_unsafe = re.compile(r'["\\\n\r]')
    font_filename = _css_unsafe.sub("", Path(font_path).name) if font_path else ""
    font_name     = _css_unsafe.sub("", Path(font_path).stem) if font_path else ""

    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype は圧縮なし・先頭に配置（ePub仕様）
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                    compress_type=zipfile.ZIP_STORED)

        # META-INF/container.xml
        zf.writestr("META-INF/container.xml", """\
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""")

        # package.opf（cover_fmt / font_filename を渡して manifest/spine を決定）
        zf.writestr("OEBPS/package.opf",
                    _make_opf(title, author, book_id, ep_titles, cover_fmt,
                              font_filename=font_filename,
                              toc_at_end=toc_at_end,
                              inline_images=list(images.keys()) if images else None,
                              synopsis=synopsis,
                              horizontal=horizontal))

        # nav.xhtml（RS向け機械読み取り専用、spine には linear="no" で含める）
        zf.writestr("OEBPS/nav.xhtml",
                    _make_nav_xhtml(title, episodes, cover_fmt,
                                    horizontal=horizontal))

        # toc.xhtml（読者向け目次、spine に linear="yes" で含める）
        zf.writestr("OEBPS/toc.xhtml",
                    _make_toc_xhtml(title, episodes, cover_fmt,
                                    horizontal=horizontal))

        # 本文CSS（フォント指定あり時は @font-face を追加）
        zf.writestr("OEBPS/css/novel.css",
                    _make_epub_css(font_name, font_filename))

        # 埋め込みフォント
        if font_path:
            with open(font_path, "rb") as _ff:
                zf.writestr(f"OEBPS/fonts/{font_filename}", _ff.read())

        # 表紙画像 + 表紙XHTML → spine 1ページ目
        zf.writestr(f"OEBPS/images/cover.{cover_fmt}", cover_data)
        zf.writestr("OEBPS/cover-image.xhtml",
                    _make_cover_image_xhtml(title, cover_fmt))

        # テキスト表紙（タイトル・著者・あらすじ）→ spine 2ページ目
        zf.writestr("OEBPS/cover.xhtml",
                    _make_cover_xhtml(title, author, synopsis,
                                      source_url=source_url, site_name=site_name,
                                      horizontal=horizontal))

        # 各話
        for i, ep in enumerate(episodes):
            zf.writestr(f"OEBPS/ep{i+1:04d}.xhtml",
                        _make_episode_xhtml(ep["title"], ep["body"],
                                            horizontal=horizontal))

        # インライン画像（青空文庫 ZIP 内の挿絵等）
        if images:
            for img_name, img_bytes in images.items():
                zf.writestr(f"OEBPS/images/{img_name}", img_bytes)

        # 奥付
        zf.writestr("OEBPS/colophon.xhtml",
                    _make_colophon_xhtml(title, source_url, site_name,
                                         horizontal=horizontal))


# ══════════════════════════════════════════
#  なろう専用：HTTP ユーティリティ（標準ライブラリのみ）
# ══════════════════════════════════════════

def narou_fetch(url: str) -> str:
    """リトライ付きHTTP GET。HTML文字列を返す。"""
    for attempt in range(1, RETRY_MAX + 2):
        try:
            req = Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ja,en;q=0.9",
            })
            with urlopen(req, timeout=30) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, errors="replace")
        except HTTPError as e:
            if e.code == 404:
                raise
            print(f"    HTTPError {e.code} (attempt {attempt})")
        except Exception as e:
            print(f"    Error: {e} (attempt {attempt})")
        if attempt <= RETRY_MAX:
            time.sleep(RETRY_WAIT)
    raise URLError(f"Failed after {RETRY_MAX} retries: {url}")


# ══════════════════════════════════════════
#  なろう専用：作品情報パーサー
# ══════════════════════════════════════════

class NarouInfoParser(HTMLParser):
    """
    なろう作品情報ページ（/novelview/infotop/ncode/NCODE/）から
    タイトル・著者・あらすじを抽出する。
    """

    def __init__(self):
        super().__init__()
        self.novel_title  = ""
        self.novel_author = ""
        self.synopsis     = ""

        self._in_h1       = False
        self._in_title_a  = False
        self._in_dt       = False
        self._dt_text     = ""
        self._in_dd       = False
        self._want_author = False
        self._want_syn    = False
        self._in_ex_td    = False

    def handle_starttag(self, tag, attrs):
        d   = dict(attrs)
        cls = d.get("class", "")

        if tag == "h1":
            if "title" in cls or not cls:
                self._in_h1 = True
            return

        if tag == "a" and self._in_h1 and not self.novel_title:
            self._in_title_a = True
            return

        if tag == "dt":
            self._in_dt   = True
            self._dt_text = ""
            return

        if tag == "dd":
            self._in_dd    = True
            return

        if tag == "td" and cls == "ex":
            self._in_ex_td = True

    def handle_endtag(self, tag):
        if tag == "h1":
            self._in_h1      = False
            self._in_title_a = False
            self.novel_title = self.novel_title.strip()
            return

        if tag == "a" and self._in_title_a:
            self._in_title_a = False
            return

        if tag == "dt":
            self._in_dt = False
            t = self._dt_text.strip()
            self._want_author = (t == "作者名")
            self._want_syn    = (t in ("あらすじ", "ストーリー"))
            return

        if tag == "dd":
            self._in_dd       = False
            self._want_author = False
            self._want_syn    = False
            return

        if tag == "td" and self._in_ex_td:
            self._in_ex_td = False

    def handle_data(self, data):
        s = data

        if self._in_h1 and self._in_title_a:
            self.novel_title += s.strip()
            return

        if self._in_h1 and not self.novel_title:
            self.novel_title += s.strip()
            return

        if self._in_dt:
            self._dt_text += s
            return

        if self._in_dd:
            if self._want_author:
                self.novel_author += s.strip()
            elif self._want_syn:
                self.synopsis += s
            return

        if self._in_ex_td:
            self.synopsis += s


def narou_get_novel_info(ncode: str) -> tuple:
    """作品情報ページからタイトル・著者・あらすじを取得する。"""
    info_url = f"https://ncode.syosetu.com/novelview/infotop/ncode/{ncode}/"
    print(f"  作品情報取得: {info_url}")
    html = narou_fetch(info_url)

    p = NarouInfoParser()
    p.feed(html)

    title    = p.novel_title.strip()
    author   = p.novel_author.strip()
    synopsis = p.synopsis.strip()

    if not title:
        m = re.search(r'<title>\s*([^｜\[【<]+)', html)
        if m:
            title = m.group(1).strip().rstrip("　 ")

    if not author:
        m = re.search(r'作者名[^<]*</d[dt]>\s*<dd[^>]*>\s*(?:<a[^>]*>)?([^<\n]+)', html)
        if m:
            author = m.group(1).strip()

    return title, author, synopsis


# ══════════════════════════════════════════
#  なろう専用：目次パーサー（エピソードリスト）
# ══════════════════════════════════════════

class NarouEpisodeListParser(HTMLParser):
    """なろう目次ページからエピソードリンク一覧を抽出する。"""

    def __init__(self):
        super().__init__()
        self.episodes          = []   # [(path, title, chapter), ...]
        self._in_ep_link       = False
        self._ep_path          = ""
        self._current_chapter  = ""   # 直前の章/部タイトル（div.p-eplist__chapter-title）
        self._in_chapter_title = False
        self._chapter_buf      = []

    def handle_starttag(self, tag, attrs):
        d   = dict(attrs)
        cls = d.get("class", "")
        # 章/部区切り: <div class="p-eplist__chapter-title"> または同クラスを含む div
        if tag == "div" and "p-eplist__chapter-title" in cls:
            self._in_chapter_title = True
            self._chapter_buf      = []
            return
        if tag == "a" and "href" in d:
            href = d["href"]
            if re.match(r"^/[a-z0-9]+/\d+/$", href):
                self._in_ep_link = True
                self._ep_path    = href

    def handle_endtag(self, tag):
        if self._in_chapter_title and tag == "div":
            self._current_chapter  = "".join(self._chapter_buf).strip()
            self._in_chapter_title = False
            return
        if tag == "a":
            self._in_ep_link = False

    def handle_data(self, data):
        if self._in_chapter_title:
            self._chapter_buf.append(data)
        elif self._in_ep_link and self._ep_path:
            s = data.strip()
            if s:
                self.episodes.append((self._ep_path, s, self._current_chapter))
                self._ep_path    = ""
                self._in_ep_link = False


def narou_get_all_episodes(base_url: str, ncode: str, index_wait: float = 1.0) -> tuple:
    """作品情報 + 目次全ページを取得して (title, author, synopsis, episodes) を返す。"""
    title, author, synopsis = narou_get_novel_info(ncode)
    time.sleep(index_wait)

    all_eps      = []
    page         = 1
    prev_chapter = ""  # ページをまたいで章情報を引き継ぐ

    while True:
        url  = f"{base_url}?p={page}" if page > 1 else base_url
        print(f"  目次 p.{page} 取得: {url}")
        html = narou_fetch(url)

        p = NarouEpisodeListParser()
        p._current_chapter = prev_chapter  # 前ページ末尾の章名を引き継ぐ
        p.feed(html)

        if not p.episodes:
            # エピソードが0件 → 最終ページを超えた
            break

        all_eps.extend(p.episodes)
        prev_chapter = p._current_chapter  # 次ページへ引き継ぐ
        print(f"    → {len(p.episodes)} 話（累計 {len(all_eps)} 話）")

        if len(p.episodes) < 100:
            # 100件未満 → 最終ページ
            break

        page += 1
        time.sleep(index_wait)

    return title, author, synopsis, all_eps


# ══════════════════════════════════════════
#  なろう専用：本文パーサー
# ══════════════════════════════════════════

class NarouEpisodeParser(HTMLParser):
    """なろう話ページから本文・サブタイトルを抽出する。"""

    def __init__(self):
        super().__init__()
        self.subtitle   = ""
        self.paragraphs = []

        self._in_subtitle   = False
        self._in_novel_view = False
        self._view_depth    = 0
        self._in_p          = False
        self._cur_para      = []
        self._in_ruby       = False  # <ruby>...</ruby> 内
        self._in_rb         = False  # <rb>...</rb> 内（明示ルビベース）
        self._in_rt         = False  # <rt>...</rt> 内（ルビ読み）
        self._in_rp         = False  # <rp>...</rp> 内（非対応ブラウザ向け括弧）
        self._rb_buf        = ""
        self._rt_buf        = ""

    def handle_starttag(self, tag, attrs):
        d   = dict(attrs)
        cls = d.get("class", "")
        id_ = d.get("id",    "")

        # 旧サイト: class="novel_subtitle"
        # 新サイト: class="p-novel__title" 等
        if tag == "p" and (cls == "novel_subtitle" or "p-novel__title" in cls):
            self._in_subtitle = True
            return

        # 旧サイト: class="novel_view"
        # 新サイト: class="js-novel-text p-novel__text" 等
        if tag == "div" and (cls == "novel_view" or "p-novel__text" in cls):
            self._in_novel_view = True
            self._view_depth    = 1
            return

        if self._in_novel_view:
            if tag == "div":
                self._view_depth += 1
                return
            if tag == "p" and re.match(r"^L\d+$", id_):
                self._in_p     = True
                self._cur_para = []
                return
            if self._in_p:
                if tag == "br":
                    self._cur_para.append("\n")
                elif tag == "ruby":
                    # <ruby>ベース<rt>よみ</rt></ruby> 形式（<rb>なし）に対応
                    self._in_ruby = True
                    self._rb_buf  = ""
                    self._rt_buf  = ""
                elif tag == "rb":
                    self._in_rb  = True
                    self._rb_buf = ""
                elif tag == "rt":
                    self._in_rt  = True
                    self._rt_buf = ""
                elif tag == "rp":
                    # <rp> は非対応ブラウザ向けの括弧：内容を無視する
                    self._in_rp = True

    def handle_endtag(self, tag):
        if tag == "p" and self._in_subtitle:
            self._in_subtitle = False
            return

        if self._in_novel_view:
            if tag == "div":
                self._view_depth -= 1
                if self._view_depth <= 0:
                    self._in_novel_view = False
                return

            if tag == "p" and self._in_p:
                self._in_p = False
                self.paragraphs.append("".join(self._cur_para).strip())
                self._cur_para = []
                return

            if self._in_p:
                if tag == "ruby":
                    # <rt>なしで終了した場合はベーステキストだけ出力
                    if self._rb_buf:
                        self._cur_para.append(self._rb_buf)
                    self._in_ruby = False
                    self._rb_buf  = ""
                    self._rt_buf  = ""
                elif tag == "rb":
                    self._in_rb = False
                elif tag == "rt":
                    self._in_rt = False
                    if self._rb_buf:
                        if self._rt_buf:
                            prev = "".join(self._cur_para)
                            pipe = "|" if _ruby_needs_pipe(self._rb_buf, prev, self._rt_buf) else ""
                            ruby = f"{pipe}{self._rb_buf}《{self._rt_buf}》"
                        else:
                            ruby = self._rb_buf
                        self._cur_para.append(ruby)
                    self._rb_buf = ""
                    self._rt_buf = ""
                elif tag == "rp":
                    self._in_rp = False

    def handle_data(self, data):
        if self._in_subtitle:
            self.subtitle += data
            return
        if self._in_novel_view and self._in_p:
            if self._in_rp:
                pass  # <rp> 内の括弧は無視
            elif self._in_rb:
                self._rb_buf += data
            elif self._in_rt:
                self._rt_buf += data
            elif self._in_ruby:
                # <rb>なし形式: <ruby>ベース<rt>よみ</rt> のベース部分を蓄積
                self._rb_buf += data
            else:
                self._cur_para.append(data)

    def get_text(self) -> str:
        return "\n".join(self.paragraphs)


def _ruby_inner_to_aozora(inner: str, preceding: str = "") -> str:
    """
    <ruby>...</ruby> の中身を青空文庫ルビ記法「ベース《よみ》」に変換する。
    <rb>ベース</rb><rt>よみ</rt> と ベース<rt>よみ</rt>（<rb>なし）の両形式に対応。
    preceding にはルビ直前のテキストを渡す（| 要否判定に使用）。
    """
    rt_m = re.search(r"<rt>(.*?)</rt>", inner, re.DOTALL)
    if not rt_m:
        return re.sub(r"<[^>]+>", "", inner)
    reading = re.sub(r"<[^>]+>", "", rt_m.group(1)).strip()
    # <rp>...</rp> と <rt>...</rt> ブロックを除去してベーステキストを取得
    base = re.sub(r"<rp>.*?</rp>", "", inner, flags=re.DOTALL)
    base = re.sub(r"<rt>.*?</rt>", "", base, flags=re.DOTALL)
    base = re.sub(r"<[^>]+>", "", base).strip()
    if not reading:
        return base
    pipe = "|" if _ruby_needs_pipe(base, preceding, reading) else ""
    return f"{pipe}{base}《{reading}》"


def narou_extract_body_fallback(html: str) -> str:
    """EpisodeParserで本文が空だった場合の正規表現フォールバック。"""
    raw_ps = re.findall(
        r'<p[^>]+id=["\']?L\d+["\']?[^>]*>(.*?)</p>',
        html, re.DOTALL
    )
    lines = []
    for p_html in raw_ps:
        # <ruby>...</ruby> ブロックを逐次変換（preceding を追跡して | 要否を判定）
        parts = []
        pos = 0
        for m in re.finditer(r"<ruby>(.*?)</ruby>", p_html, re.DOTALL):
            before_html = p_html[pos:m.start()]
            parts.append(before_html)
            preceding = re.sub(r"<[^>]+>", "", "".join(parts))
            parts.append(_ruby_inner_to_aozora(m.group(1), preceding))
            pos = m.end()
        parts.append(p_html[pos:])
        p_html = "".join(parts)
        clean = re.sub(r"<br\s*/?>", "\n", p_html)
        clean = re.sub(r"<[^>]+>", "", clean)
        lines.append(clean.strip())
    return "\n".join(lines).strip()


# ══════════════════════════════════════════
#  なろう：メイン処理
# ══════════════════════════════════════════

def run_narou(args):
    """なろう小説のダウンロード処理。"""
    url   = args.url.rstrip("/") + "/"
    m     = re.search(r"ncode\.syosetu\.com/([a-z0-9]+)", url, re.I)
    if not m:
        print("エラー: URLからNコードを取得できません。")
        sys.exit(1)
    ncode    = m.group(1).lower()
    base_url = f"https://ncode.syosetu.com/{ncode}/"

    print(f"\n[Step 1] 作品情報・目次取得開始")
    title, author, synopsis, episodes = narou_get_all_episodes(
        base_url, ncode, index_wait=args.delay
    )

    if not episodes:
        print("エラー: 話が見つかりません。URLを確認してください。")
        sys.exit(1)

    print(f"\n  タイトル : {title}")
    print(f"  作者     : {author}")
    print(f"  総話数   : {len(episodes)} 話")

    base     = _apply_output_dir(args, args.output or safe_filename(title, "narou_novel"))
    txt_path = base + ".txt"
    epub_path= base + _epub_ext(args)
    header   = aozora_header(title, author, synopsis, source_url=base_url)
    colophon = aozora_colophon(title, base_url, "小説家になろう")

    # 範囲絞り込み
    start_idx = max(0, (args.start or 1) - 1)
    end_idx   = args.end if args.end else len(episodes)
    target    = episodes[start_idx:end_idx]
    total     = len(target)

    if args.list_only:
        _show_episode_list(title, author, [ep[1] for ep in target])
    _dry_run_exit(args)

    # 再開処理
    resume_arg = getattr(args, "resume", None)
    if resume_arg == 0:          # 自動検出
        existing_sections, existing_epub = _load_existing_txt(txt_path)
        n_existing = len(existing_sections)
        if n_existing > 0:
            resume_from = start_idx + n_existing + 1
            sections     = existing_sections
            epub_episodes = existing_epub
            print(f"\n[Step 2] 既存 {n_existing} 話を検出。第 {resume_from} 話から再開")
        else:
            resume_from  = 1
            sections     = []
            epub_episodes= []
            print(f"\n[Step 2] 既存ファイルなし。最初から取得します。")
    elif resume_arg and resume_arg > 1 and os.path.exists(txt_path):
        resume_from = resume_arg
        print(f"\n[Step 2] 第{resume_from}話から再開")
        sections, epub_episodes = _load_existing_txt(txt_path)
        if not sections:
            # フォールバック: ヘッダーベースの旧ロジック
            with open(txt_path, "r", encoding=ENCODING) as f:
                content = f.read()
            body = content[len(header):] if content.startswith(header) else content
            sections = body.split(PAGE_BREAK)
            if sections and "底本：" in sections[-1]:
                sections.pop()
            epub_episodes = []
            for sec in sections:
                lines = sec.strip().split("\n")
                ep_t = ""
                body_start = 0
                for li, ln in enumerate(lines):
                    if "は大見出し終わり］" in ln or "は中見出し終わり］" in ln:
                        body_start = li + 1
                        break
                    if "は大見出し］" in ln or "は中見出し］" in ln:
                        m = re.search(r"「(.+?)」は", ln)
                        if m:
                            ep_t = m.group(1)
                epub_episodes.append({
                    "title": ep_t or "（タイトル不明）",
                    "body":  "\n".join(lines[body_start:]).strip(),
                })
    else:
        resume_from  = 1
        sections     = []
        epub_episodes= []
        print(f"\n[Step 2] 本文ダウンロード開始")

    for idx, (path, ep_title, ep_group) in enumerate(target, start_idx + 1):
        if idx < resume_from:
            continue

        ep_url = f"https://ncode.syosetu.com{path}"
        print(f"  [{idx:5d}/{len(episodes)}] {ep_title[:50]}")

        try:
            html = narou_fetch(ep_url)
        except Exception as e:
            print(f"    !! 取得失敗（スキップ）: {e}")
            sections.append(aozora_chapter_title(ep_title) + "\n\n（取得失敗）\n")
            epub_episodes.append({"title": ep_title, "body": "（取得失敗）",
                                  "group": ep_group or None})
            time.sleep(args.delay)
            continue

        ep       = NarouEpisodeParser()
        ep.feed(html)
        subtitle = ep.subtitle.strip() or ep_title
        body     = ep.get_text().strip()

        if not body:
            body = narou_extract_body_fallback(html)
            if body:
                print("    (フォールバック抽出)")

        if not body:
            print("    !! 本文が空。")
            body = "（本文取得失敗）"
        else:
            body = normalize_tate(body)

        sections.append(f"{aozora_chapter_title(subtitle)}\n\n{body}\n")
        epub_episodes.append({"title": subtitle, "body": body,
                              "group": ep_group or None})

        if idx % 50 == 0:
            write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))
            print(f"    → 中間保存 ({idx}/{len(episodes)}話)")

        if idx < len(episodes):
            time.sleep(args.delay)

    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   総話数   : {len(sections)} 話")
    print(f"   総文字数 : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print(f"📖 ePub生成中...")
        build_epub(epub_path, title, author, synopsis,
                   base_url, "小説家になろう", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")

    if resume_from == 1:
        print(f"\n  途中で中断した場合は以下で再開できます:")
        print(f"  python novel_downloader.py --resume N {url}")


# ══════════════════════════════════════════
#  カクヨム専用：スクレイピング
# ══════════════════════════════════════════

_KKY_BASE = "https://kakuyomu.jp"
_KKY_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def kky_fetch(session, url: str, retries: int = 3):
    """URLを取得してBeautifulSoupオブジェクトを返す。"""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=_KKY_HEADERS, timeout=20)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            resp.encoding = ct.split("charset=")[-1].split(";")[0].strip() if "charset=" in ct else "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"  [警告] 取得失敗 (試行 {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(3)
    raise RuntimeError(f"URLの取得に失敗しました: {url}")


def kky_extract_next_data(soup) -> dict:
    """<script id="__NEXT_DATA__"> からJSONを抽出する。"""
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return {}
    try:
        return json.loads(tag.string)
    except (json.JSONDecodeError, TypeError):
        return {}


def kky_normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def kky_to_aozora_ruby(match) -> str:
    return f"|{match.group(1)}《{match.group(2)}》"


def kky_get_work_info(soup, next_data: dict, work_url: str) -> dict:
    """作品トップページから基本情報を取得する。"""
    info = {"title": "", "author": "", "description": "", "url": work_url}

    try:
        apollo = (next_data.get("props", {})
                           .get("pageProps", {})
                           .get("__APOLLO_STATE__", {}))
        if apollo:
            work_id  = work_url.rstrip("/").split("/works/")[-1]
            work_obj = apollo.get(f"Work:{work_id}")
            if not work_obj:
                for k, v in apollo.items():
                    if k.startswith("Work:") and isinstance(v, dict):
                        if str(v.get("id", "")) == work_id:
                            work_obj = v
                            break
            if work_obj:
                # alternateTitle が存在する場合はそちらが正式タイトル
                # （title は "作品名／著者名" 形式になっている場合がある）
                alt_title = work_obj.get("alternateTitle", "")
                info["title"] = alt_title if alt_title else work_obj.get("title", "")
                info["description"] = work_obj.get("introduction", "")
                author_ref = work_obj.get("author", {})
                if isinstance(author_ref, dict):
                    akey = author_ref.get("__ref", "")
                    if akey and akey in apollo:
                        activity_name = apollo[akey].get("activityName", "")
                        # alternateAuthorName が存在する場合は実際の著者名として優先
                        alt_author = work_obj.get("alternateAuthorName", "")
                        if alt_author and activity_name and alt_author != activity_name:
                            info["author"] = f"{alt_author}／{activity_name}"
                        elif alt_author:
                            info["author"] = alt_author
                        else:
                            info["author"] = activity_name
    except Exception:
        pass

    if not info["title"]:
        t = (soup.find("h1", class_=re.compile(r"WorkTitle")) or
             soup.find("h1", {"itemprop": "name"}) or soup.find("h1"))
        if t:
            info["title"] = kky_normalize(t.get_text())

    if not info["author"]:
        a = (soup.find("span", class_=re.compile(r"Author")) or
             soup.find("a", {"itemprop": "author"}) or
             soup.find(class_=re.compile(r"author", re.I)))
        if a:
            info["author"] = kky_normalize(a.get_text())

    if not info["description"]:
        d = (soup.find("p", class_=re.compile(r"WorkIntroduction|Description|introduction")) or
             soup.find(class_=re.compile(r"synopsis|introduction|description", re.I)))
        if d:
            info["description"] = kky_normalize(d.get_text())

    return info


def kky_get_episode_urls(next_data: dict, work_url: str) -> list:
    """__NEXT_DATA__ から全エピソードURLを順序付きで取得する。"""
    episodes = []
    try:
        apollo = (next_data.get("props", {})
                           .get("pageProps", {})
                           .get("__APOLLO_STATE__", {}))
        if not apollo:
            return episodes

        work_id  = work_url.rstrip("/").split("/works/")[-1]
        work_obj = apollo.get(f"Work:{work_id}")
        if not work_obj:
            for k, v in apollo.items():
                if k.startswith("Work:") and isinstance(v, dict):
                    if str(v.get("id", "")) == work_id:
                        work_obj = v
                        break

        # tableOfContents 構造（新形式）: Work → TableOfContentsChapter[] → episode[]
        toc_refs = []
        if work_obj:
            for ref in work_obj.get("tableOfContents", []):
                if isinstance(ref, dict) and "__ref" in ref:
                    toc_refs.append(ref["__ref"])

        if toc_refs:
            chapter_count = 0
            for toc_ref in toc_refs:
                toc_obj = apollo.get(toc_ref)
                if not toc_obj or not isinstance(toc_obj, dict):
                    continue
                # 章名: chapter.__ref → Chapter:xxx → title
                current_chapter = ""
                ch_ref_obj = toc_obj.get("chapter")
                if isinstance(ch_ref_obj, dict) and "__ref" in ch_ref_obj:
                    ch_obj = apollo.get(ch_ref_obj["__ref"])
                    if ch_obj and isinstance(ch_obj, dict):
                        current_chapter = kky_normalize(ch_obj.get("title", ""))
                if current_chapter:
                    chapter_count += 1
                # エピソード列挙
                for ep_ref in toc_obj.get("episodeUnions", []):
                    if not (isinstance(ep_ref, dict) and "__ref" in ep_ref):
                        continue
                    ep_obj = apollo.get(ep_ref["__ref"])
                    if not ep_obj or not isinstance(ep_obj, dict):
                        continue
                    ep_id    = ep_obj.get("id", "")
                    ep_title = kky_normalize(ep_obj.get("title", ""))
                    if ep_id:
                        episodes.append({
                            "url":     f"{_KKY_BASE}/works/{work_id}/episodes/{ep_id}",
                            "title":   ep_title or "（タイトル不明）",
                            "chapter": current_chapter,
                        })
            if chapter_count:
                print(f"      章を {chapter_count} 件検出しました")
        elif work_obj and work_obj.get("episodeUnions"):
            # 旧形式フォールバック: Work.episodeUnions に直接エピソードが並ぶ
            current_chapter = ""
            chapter_count   = 0
            for ref in work_obj.get("episodeUnions", []):
                if not (isinstance(ref, dict) and "__ref" in ref):
                    continue
                ref_key  = ref["__ref"]
                ep_obj   = apollo.get(ref_key)
                if not ep_obj or not isinstance(ep_obj, dict):
                    continue
                ep_id    = ep_obj.get("id", "")
                ep_title = kky_normalize(ep_obj.get("title", ""))
                is_ch    = not ref_key.startswith("Episode:") or not ep_id
                if is_ch and ep_title:
                    current_chapter = ep_title
                    chapter_count  += 1
                    continue
                if ep_id:
                    episodes.append({
                        "url":     f"{_KKY_BASE}/works/{work_id}/episodes/{ep_id}",
                        "title":   ep_title or "（タイトル不明）",
                        "chapter": current_chapter,
                    })
            if chapter_count:
                print(f"      章を {chapter_count} 件検出しました")
        else:
            print("  [警告] tableOfContents / episodeUnions が見つかりません。Episode を直接列挙します。")
            for k, v in apollo.items():
                if k.startswith("Episode:") and isinstance(v, dict):
                    ep_id = v.get("id", "")
                    if ep_id:
                        episodes.append({
                            "url":     f"{_KKY_BASE}/works/{work_id}/episodes/{ep_id}",
                            "title":   kky_normalize(v.get("title", "（タイトル不明）")),
                            "chapter": "",
                        })
    except Exception as e:
        print(f"  [警告] __NEXT_DATA__ からのエピソード取得に失敗: {e}")

    return episodes


def kky_get_episode_urls_fallback(soup, work_url: str) -> list:
    """フォールバック: HTMLからエピソードリンクを取得する。"""
    episodes = []
    seen     = set()
    for a in (soup.select("a[href*='/episodes/']") or
              soup.find_all("a", href=re.compile(r"/episodes/\d+"))):
        href = a.get("href", "")
        if not href or href in seen:
            continue
        full_url = urljoin(_KKY_BASE, href)
        if "/episodes/" not in full_url:
            continue
        seen.add(href)
        episodes.append({"url": full_url,
                         "title": kky_normalize(a.get_text()) or "（タイトル不明）",
                         "chapter": ""})
    return episodes


def kky_extract_episode_body(soup, next_data: dict, ep_url: str) -> tuple:
    """エピソードページから (タイトル, 章名, 本文) を抽出する。"""
    ep_title = ""

    if next_data:
        try:
            apollo = (next_data.get("props", {})
                               .get("pageProps", {})
                               .get("__APOLLO_STATE__", {}))
            if apollo:
                ep_id  = ep_url.rstrip("/").split("/episodes/")[-1] if "/episodes/" in ep_url else ""
                ep_obj = apollo.get(f"Episode:{ep_id}") if ep_id else None
                if not ep_obj and ep_id:
                    for k, v in apollo.items():
                        if k.startswith("Episode:") and isinstance(v, dict):
                            if str(v.get("id", "")) == ep_id:
                                ep_obj = v
                                break
                if not ep_obj and ep_id:
                    for k, v in apollo.items():
                        if k.startswith("Episode:") and isinstance(v, dict):
                            if v.get("title", ""):
                                ep_obj = v
                                break
                if ep_obj:
                    ep_title = kky_normalize(ep_obj.get("title", ""))
        except Exception:
            pass

    if not ep_title:
        t = (soup.find("h2", class_=re.compile(r"EpisodeTitle|episodeTitle")) or
             soup.find("h2") or
             soup.find("h1", class_=re.compile(r"EpisodeTitle|episodeTitle")))
        if t:
            ep_title = kky_normalize(t.get_text())

    chapter = ""
    ch_tag  = soup.find(class_="chapterTitle level2 js-vertical-composition-item")
    if ch_tag:
        chapter = kky_normalize(ch_tag.get_text())

    body_tag = (
        soup.find("div", class_=re.compile(r"widget-episodeBody|EpisodeBody|js-episode-body", re.I)) or
        soup.find("div", {"id": re.compile(r"episode-body", re.I)}) or
        soup.find("div", class_=re.compile(r"novel_body|story|content", re.I))
    )
    if not body_tag:
        all_divs = soup.find_all("div")
        body_tag = max(all_divs, key=lambda d: len(d.find_all("p")), default=None)

    if not body_tag:
        return ep_title, chapter, ""

    lines = []
    for elem in body_tag.find_all(["p", "br"], recursive=True):
        if elem.name == "br":
            lines.append("")
        else:
            # <ruby> タグを青空文庫記法に変換してから get_text() する。
            # get_text() で平坦化すると rb/rt が区別できなくなるため、
            # <ruby> を先にインライン変換しておく。
            for ruby in elem.find_all("ruby"):
                rb_tag = ruby.find("rb")
                rt_tag = ruby.find("rt")
                if rt_tag:
                    base = rb_tag.get_text() if rb_tag else "".join(
                        c.get_text() if hasattr(c, "get_text") else str(c)
                        for c in ruby.children
                        if getattr(c, "name", None) not in ("rt", "rp")
                    )
                    base = kky_normalize(base)
                    rt   = kky_normalize(rt_tag.get_text())
                    prev = _bs4_prev_text(ruby)
                    pipe = "|" if _ruby_needs_pipe(base, prev, rt) else ""
                    ruby.replace_with(f"{pipe}{base}《{rt}》")
                else:
                    # rt がない場合はルビなしテキストとして展開
                    ruby.replace_with(ruby.get_text())
            text = kky_normalize(elem.get_text())
            lines.append(text if text else "")

    body = "\n".join(lines)
    return ep_title, chapter, body


# ══════════════════════════════════════════
#  カクヨム：メイン処理
# ══════════════════════════════════════════

def run_kakuyomu(args):
    """カクヨム小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: カクヨムのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    session  = requests.Session()
    session.headers.update(_KKY_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup  = kky_fetch(session, work_url)
    next_data = kky_extract_next_data(top_soup)
    if next_data:
        print("      __NEXT_DATA__ の取得に成功しました。")
    else:
        print("      [警告] __NEXT_DATA__ が見つかりません。HTMLから直接取得を試みます。")

    info = kky_get_work_info(top_soup, next_data, work_url)
    if info["title"]:
        print(f"      タイトル: {info['title']}")
    if info["author"]:
        print(f"      著者    : {info['author']}")

    print("[2/3] エピソード一覧を取得中...")
    episode_list = kky_get_episode_urls(next_data, work_url)
    if episode_list:
        print(f"      __NEXT_DATA__ から {len(episode_list)} 話を検出しました。")
    else:
        print("      フォールバック: HTMLからエピソードリンクを取得します...")
        episode_list = kky_get_episode_urls_fallback(top_soup, work_url)
        if episode_list:
            print(f"      HTMLから {len(episode_list)} 話を検出しました。")

    if not episode_list:
        print("エラー: エピソードが見つかりませんでした。")
        sys.exit(1)

    # 範囲絞り込み
    total_all    = len(episode_list)
    start_idx    = max(0, (args.start or 1) - 1)
    end_idx      = args.end if args.end else total_all
    episode_list = episode_list[start_idx:end_idx]
    total        = len(episode_list)
    print(f"      {total} 話を取得します（全 {total_all} 話中）")

    if args.list_only:
        _show_episode_list(info["title"], info["author"], [ep["title"] for ep in episode_list])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info.get("description", ""),
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "カクヨム")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "kakuyomu_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    _old_sections, _old_epub, episode_list = _apply_resume(args, txt_path, episode_list)
    if not episode_list and _old_sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print("[3/3] 各エピソードを取得中...")
    episodes_data = []

    for i, ep in enumerate(episode_list, 1):
        print(f"  [{i:4d}/{len(episode_list)}] {ep['title'][:50]}")
        try:
            ep_soup   = kky_fetch(session, ep["url"])
            ep_next   = kky_extract_next_data(ep_soup)
            ep_title_p, ep_chapter, body = kky_extract_episode_body(ep_soup, ep_next, ep["url"])
            fallback  = ep["title"].split(" - ")[0].split("　-　")[0].strip()
            final_ttl = ep_title_p or fallback
            episodes_data.append({"title": final_ttl,
                                  "chapter": ep_chapter or ep.get("chapter", ""),
                                  "body": body})
        except RuntimeError as e:
            print(f"  [エラー] スキップします: {e}")
            episodes_data.append({"title": ep["title"], "chapter": ep.get("chapter", ""),
                                  "body": "（取得失敗）"})
        if i < len(episode_list):
            time.sleep(args.delay)

    # 青空文庫テキスト組み立て
    sections     = list(_old_sections)
    epub_episodes= list(_old_epub)
    for ep in episodes_data:
        chapter = ep.get("chapter", "")
        heading = f"{chapter}　{ep['title']}" if chapter else ep["title"]
        sec_title = aozora_chapter_title(heading, level="中見出し")
        body = normalize_tate(ep["body"]) if ep["body"] and ep["body"] != "（取得失敗）" else ep["body"]
        sections.append(f"{sec_title}\n\n{body}\n")
        # ePub 目次: 章を group フィールドに分離してネスト表示。テキストは heading（章込み）を維持
        epub_episodes.append({"title": ep["title"], "body": body,
                              "group": chapter or None})
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得話数 : {len(episodes_data)} 話")
    print(f"   総文字数 : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print(f"📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info.get("description", ""),
                   work_url, "カクヨム", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  アルファポリス専用：スクレイピング
# ══════════════════════════════════════════

_ALP_BASE = "https://www.alphapolis.co.jp"
_ALP_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def alp_fetch(session, url: str, retries: int = 3):
    """URLを取得してBeautifulSoupオブジェクトを返す。"""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=_ALP_HEADERS, timeout=20)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            resp.encoding = (ct.split("charset=")[-1].split(";")[0].strip()
                             if "charset=" in ct else "utf-8")
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"  [警告] 取得失敗 (試行 {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(3)
    raise RuntimeError(f"URLの取得に失敗しました: {url}")


def alp_get_work_info(soup) -> dict:
    """作品トップページからタイトル・著者・あらすじを取得する。"""
    info = {"title": "", "author": "", "description": ""}

    h1 = soup.find("h1", class_="title")
    if h1:
        info["title"] = h1.get_text(strip=True)

    author_div = soup.find("div", class_="author")
    if author_div:
        a = author_div.find("a")
        if a:
            info["author"] = a.get_text(strip=True)

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        info["description"] = meta["content"].strip()

    return info


def alp_get_episode_list(soup) -> list:
    """作品トップページからエピソードURLとタイトルのリストを取得する。"""
    import json as _json

    # ── 新形式: script[type="application/json"] に chapterEpisodes が埋め込まれる ──
    for script in soup.find_all("script", type="application/json"):
        txt = (script.string or "").strip()
        if not txt or "chapterEpisodes" not in txt:
            continue
        try:
            data = _json.loads(txt)
        except Exception:
            continue
        chapter_episodes = data.get("chapterEpisodes")
        if not isinstance(chapter_episodes, list):
            continue
        episodes = []
        for chapter in chapter_episodes:
            chapter_title = chapter.get("title", "").strip()
            for ep in chapter.get("episodes", []):
                if not ep.get("isPublic", True):
                    continue
                href = ep.get("url", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = _ALP_BASE + href
                main_title = ep.get("mainTitle", "").strip()
                sub_title  = ep.get("subTitle", "").strip()
                title = f"{main_title}　{sub_title}" if sub_title else main_title
                episodes.append({"url": href, "title": title, "chapter": chapter_title})
        if episodes:
            return episodes

    # ── 旧形式フォールバック: div.episodes > div.episode ──
    episodes = []
    episodes_div = soup.find("div", class_="episodes")
    if not episodes_div:
        return episodes

    for ep_div in episodes_div.find_all("div", class_="episode"):
        a = ep_div.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = _ALP_BASE + href
        if "/episode/" not in href:
            continue

        title_span = a.find("span", class_="title")
        if title_span:
            dummy = title_span.find("span", class_="bookmark-dummy")
            if dummy:
                dummy.decompose()
            ep_title = title_span.get_text(strip=True)
        else:
            ep_title = a.get_text(strip=True)

        episodes.append({"url": href, "title": ep_title})

    return episodes


def alp_html_to_aozora(html: str) -> str:
    """エピソード本文HTMLを青空文庫書式テキストに変換する。"""
    if not html.strip():
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # <ruby> → 青空文庫ルビ記法
    for ruby in soup.find_all("ruby"):
        base = ""
        reading = ""
        for child in ruby.children:
            if hasattr(child, "name"):
                if child.name == "rt":
                    reading = child.get_text()
                elif child.name != "rp":
                    base += child.get_text()
            else:
                base += str(child)
        base    = base.strip()
        reading = reading.strip()
        ruby.replace_with(f"|{base}《{reading}》" if (base and reading) else base)

    # <p> タグが存在すれば段落ごとに処理
    paras = soup.find_all("p")
    if paras:
        lines = [p.get_text("\n").strip() for p in paras if p.get_text(strip=True)]
        return "\n\n".join(lines)

    # <p> がない場合は <br> を改行に変換
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup.get_text().strip()


def alp_extract_episode(session, ep_url: str) -> tuple:
    """
    エピソードページを取得し (エピソードタイトル, 本文テキスト) を返す。

    サーバーはセッション状態によって2通りのレスポンスを返す：
      (A) 本文が div#novelBody に直接埋め込まれている（Cookie あり）
      (B) novelBody が空で JS が /novel/episode_body へ AJAX POST する（Cookie なし）
    まず (A) を試み、本文がなければ (B) にフォールバックする。
    """
    soup = alp_fetch(session, ep_url)

    title_tag = soup.find("h2", class_="episode-title")
    ep_title  = title_tag.get_text(strip=True) if title_tag else ""

    # ── (A) 本文が HTML に直接埋め込まれているか確認 ──────────────
    novel_body = soup.find("div", id="novelBody")
    if novel_body:
        # ローディングインジケーター以外のテキストがあれば直接埋め込み
        loading = novel_body.find("div", id="LoadingEpisode")
        if loading:
            loading.decompose()
        if novel_body.get_text(strip=True):
            return ep_title, alp_html_to_aozora(str(novel_body))

    # ── (B) AJAX POST で本文を取得 ─────────────────────────────────
    page_js = "\n".join(
        s.string for s in soup.find_all("script") if s.string
    )

    csrf_m = re.search(r"X-CSRF-TOKEN['\"]?\s*:\s*['\"]([^'\"]+)['\"]", page_js)
    if not csrf_m:
        raise RuntimeError(f"CSRFトークンが見つかりません: {ep_url}")
    csrf_token = csrf_m.group(1)

    # .load() / $.ajax() 形式、URL フル・相対パス、パラメータ順序の違いに対応
    _ALP_LOAD_PATTERNS = [
        (r"\.load\s*\(\s*['\"][^'\"]*episode_body['\"]"
         r"\s*,\s*\{\s*['\"]?episode['\"]?\s*:\s*(\d+)"
         r"\s*,\s*['\"]?token['\"]?\s*:\s*['\"]([^'\"]+)['\"]",
         1, 2),
        (r"\.load\s*\(\s*['\"][^'\"]*episode_body['\"]"
         r"\s*,\s*\{\s*['\"]?token['\"]?\s*:\s*['\"]([^'\"]+)['\"]"
         r"\s*,\s*['\"]?episode['\"]?\s*:\s*(\d+)",
         2, 1),
        (r"episode_body['\"]?\s*[,\}][^}]*['\"]?episode['\"]?\s*:\s*(\d+)"
         r"\s*,\s*['\"]?token['\"]?\s*:\s*['\"]([^'\"]+)['\"]",
         1, 2),
        (r"episode_body['\"]?\s*[,\}][^}]*['\"]?token['\"]?\s*:\s*['\"]([^'\"]+)['\"]"
         r"\s*,\s*['\"]?episode['\"]?\s*:\s*(\d+)",
         2, 1),
    ]
    load_m    = None
    ep_id_grp = 1
    ep_tok_grp = 2
    for pattern, id_grp, tok_grp in _ALP_LOAD_PATTERNS:
        m = re.search(pattern, page_js)
        if m:
            load_m     = m
            ep_id_grp  = id_grp
            ep_tok_grp = tok_grp
            break
    if not load_m:
        raise RuntimeError(f"エピソードIDまたはトークンが見つかりません: {ep_url}")
    episode_id = load_m.group(ep_id_grp)
    ep_token   = load_m.group(ep_tok_grp)

    resp = session.post(
        _ALP_BASE + "/novel/episode_body",
        data={"episode": episode_id, "token": ep_token},
        headers={
            **_ALP_HEADERS,
            "X-CSRF-TOKEN": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": ep_url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        timeout=20,
    )
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "")
    resp.encoding = (ct.split("charset=")[-1].split(";")[0].strip()
                     if "charset=" in ct else "utf-8")

    return ep_title, alp_html_to_aozora(resp.text)


def run_alphapolis(args):
    """アルファポリス小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: アルファポリスのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    session  = requests.Session()
    session.headers.update(_ALP_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup = alp_fetch(session, work_url)
    info     = alp_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル: {info['title']}")
    if info["author"]:
        print(f"      著者    : {info['author']}")

    print("[2/3] エピソード一覧を取得中...")
    episode_list = alp_get_episode_list(top_soup)
    if not episode_list:
        print("エラー: エピソードが見つかりませんでした。")
        sys.exit(1)

    total_all    = len(episode_list)
    start_idx    = max(0, (args.start or 1) - 1)
    end_idx      = args.end if args.end else total_all
    episode_list = episode_list[start_idx:end_idx]
    total        = len(episode_list)
    print(f"      {total} 話を取得します（全 {total_all} 話中）")

    if args.list_only:
        _show_episode_list(info["title"], info["author"], [ep["title"] for ep in episode_list])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info.get("description", ""),
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "アルファポリス")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "alphapolis_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, episode_list = _apply_resume(args, txt_path, episode_list)
    if not episode_list and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print("[3/3] 各エピソードを取得中...")
    episodes_data = []

    for i, ep in enumerate(episode_list, 1):
        print(f"  [{i:4d}/{len(episode_list)}] {ep['title'][:50]}")
        try:
            ep_title, body = alp_extract_episode(session, ep["url"])
            episodes_data.append({"title": ep_title or ep["title"], "body": body,
                                  "chapter": ep.get("chapter", "")})
        except RuntimeError as e:
            print(f"  [エラー] スキップします: {e}")
            episodes_data.append({"title": ep["title"], "body": "（取得失敗）",
                                  "chapter": ep.get("chapter", "")})
        if i < len(episode_list):
            time.sleep(args.delay)

    for ep in episodes_data:
        sec_title = aozora_chapter_title(ep["title"])
        body = (normalize_tate(ep["body"])
                if ep["body"] and ep["body"] != "（取得失敗）" else ep["body"])
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep["title"], "body": body,
                               "group": ep.get("chapter") or None})
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得話数 : {len(episodes_data)} 話")
    print(f"   総文字数 : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info.get("description", ""),
                   work_url, "アルファポリス", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  エブリスタ専用：スクレイピング
# ══════════════════════════════════════════

_EST_BASE = "https://estar.jp"
_EST_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def est_fetch(session, url: str, retries: int = 3):
    """URLを取得して (BeautifulSoup, html_text) を返す。"""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=_EST_HEADERS, timeout=20)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            resp.encoding = (ct.split("charset=")[-1].split(";")[0].strip()
                             if "charset=" in ct else "utf-8")
            return BeautifulSoup(resp.text, "html.parser"), resp.text
        except Exception as e:
            print(f"  [警告] 取得失敗 (試行 {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(3)
    raise RuntimeError(f"URLの取得に失敗しました: {url}")


def est_get_work_info(soup, html: str) -> dict:
    """作品トップページからタイトル・著者・あらすじ・総ページ数を取得する。"""
    info = {"title": "", "author": "", "description": "", "page_count": 0}

    h1 = soup.find("h1")
    if h1:
        info["title"] = h1.get_text(strip=True)

    # og:title の形式: "タイトル／著者名"
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        content = og_title["content"]
        if "／" in content:
            info["author"] = content.split("／")[-1].strip()

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        info["description"] = meta_desc["content"].strip()

    m = re.search(r'publishedPageCount:(\d+)', html)
    if m:
        info["page_count"] = int(m.group(1))

    return info


def est_extract_nuxt(html: str) -> str:
    """HTML から window.__NUXT__ のスクリプト内容を抽出する。"""
    start = html.find("window.__NUXT__")
    end   = html.find("</script>", start)
    return html[start:end] if start >= 0 else ""


def _est_parse_nuxt_vars(nuxt_src: str) -> dict:
    """
    NUXT IIFE の引数リストを解析して letter→int のマッピングを返す。
    例: (function(a,b,c,...){...}(false,null,0,...,1,...)) → {'c':0,'g':1,...}
    """
    sig_m = re.search(r'\(function\(([a-z,]+)\)', nuxt_src)
    if not sig_m:
        return {}
    params = sig_m.group(1).split(',')
    # 末尾の }(args) を探す（IIFE末尾の引数リスト）
    idx = nuxt_src.rfind('}(')
    if idx < 0:
        return {}
    args_str = nuxt_src[idx + 2:]
    # 末尾の );, )); 等を除去
    args_str = re.sub(r'\)+\s*;?\s*$', '', args_str)
    # 簡易 JS 引数パーサー（{} や "" 内のカンマを無視して分割）
    args, current, depth, in_str = [], [], 0, False
    for ch in args_str:
        if in_str:
            current.append(ch)
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            current.append(ch)
        elif ch in '{[(':
            depth += 1
            current.append(ch)
        elif ch in '}])':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append(''.join(current).strip())
    return {p: int(v) for p, v in zip(params, args) if v.isdigit()}


def est_parse_viewer_page(nuxt_src: str, batch_page: int = 1) -> dict:
    """
    ビューアページの __NUXT__ から各ページの pageNo・body を抽出する。
    戻り値: {pageNo: body_str}
    """
    var_map = _est_parse_nuxt_vars(nuxt_src)
    result = {}
    for m in re.finditer(
        r'novelPageId:"\d+",body:"((?:[^"\\]|\\.)*?)",bodyParsed', nuxt_src
    ):
        body = m.group(1).replace("\\n", "\n").replace("\\r", "")
        rest = nuxt_src[m.end():m.end() + 500]
        pageno_m = re.search(r',pageNo:(\d+|[a-z])', rest)
        if not pageno_m:
            continue
        raw = pageno_m.group(1)
        page_no = int(raw) if raw.isdigit() else var_map.get(raw, batch_page)
        result[page_no] = body
    return result


def est_parse_episode_titles(nuxt_src: str, batch_page: int = 1) -> dict:
    """
    ビューアページの __NUXT__ からエピソード開始ページのタイトルを抽出する。
    戻り値: {pageNo: episodeTitle}（タイトルのあるページのみ）
    """
    var_map = _est_parse_nuxt_vars(nuxt_src)
    result = {}
    for m in re.finditer(
        r'novelPageId:"\d+",body:"(?:[^"\\]|\\.)*?",bodyParsed', nuxt_src
    ):
        rest = nuxt_src[m.end():m.end() + 500]
        pageno_m = re.search(r',pageNo:(\d+|[a-z])', rest)
        title_m  = re.search(r',title:"([^"]+)"', rest)
        if not pageno_m or not title_m:
            continue
        raw = pageno_m.group(1)
        page_no = int(raw) if raw.isdigit() else var_map.get(raw, batch_page)
        result[page_no] = title_m.group(1)
    return result


def est_parse_chapter_titles(nuxt_src: str, batch_page: int = 1) -> dict:
    """
    ビューアページの __NUXT__ から各ページの chapterTitle を抽出する。
    chapterTitle はエピソードオブジェクトの最終フィールドなので、
    直前 1500 文字以内の pageNo を参照して対応付ける。
    戻り値: {pageNo: chapterTitle}
    """
    var_map = _est_parse_nuxt_vars(nuxt_src)
    result = {}
    for m in re.finditer(r',chapterTitle:"([^"]+)"', nuxt_src):
        chapter = m.group(1).strip()
        if not chapter:
            continue
        # chapterTitle より手前 1500 文字以内の pageNo を取得
        ctx = nuxt_src[max(0, m.start() - 1500):m.start()]
        pageno_m = re.search(r',pageNo:(\d+|[a-z])[,}]', ctx)
        if not pageno_m:
            continue
        raw = pageno_m.group(1)
        page_no = int(raw) if raw.isdigit() else var_map.get(raw, batch_page)
        result[page_no] = chapter
    return result


def run_estar(args):
    """エブリスタ小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: エブリスタのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r'/novels/(\d+)', work_url)
    if not wid_m:
        print(f"エラー: エブリスタの作品URLとして認識できません: {work_url}")
        sys.exit(1)
    work_id = wid_m.group(1)

    session = requests.Session()
    session.headers.update(_EST_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup, top_html = est_fetch(session, work_url)
    info = est_get_work_info(top_soup, top_html)
    if info["title"]:
        print(f"      タイトル  : {info['title']}")
    if info["author"]:
        print(f"      著者      : {info['author']}")

    total_pages = info["page_count"]
    if not total_pages:
        print("エラー: 総ページ数を取得できませんでした。")
        sys.exit(1)
    print(f"      総ページ数: {total_pages}")
    _dry_run_exit(args)

    start_page   = max(1, args.start or 1)
    end_page     = min(total_pages, args.end or total_pages)
    target_pages = list(range(start_page, end_page + 1))
    print(f"[2/3] エピソードを取得中（{len(target_pages)} ページ / 全 {total_pages} ページ）...")

    all_bodies         = {}   # {pageNo: body_str}
    all_titles         = {}   # {pageNo: episodeTitle}（エピソード開始ページのみ）
    all_chapter_titles = {}   # {pageNo: chapterTitle}

    batch_list = list(range(start_page, end_page + 1, 15))
    for batch_i, batch_page in enumerate(batch_list, 1):
        viewer_url = f"{_EST_BASE}/novels/{work_id}/viewer?page={batch_page}"
        print(f"  [{batch_i:3d}/{len(batch_list)}] page={batch_page}")
        try:
            _, viewer_html = est_fetch(session, viewer_url)
            nuxt_src = est_extract_nuxt(viewer_html)
            all_bodies.update(est_parse_viewer_page(nuxt_src, batch_page))
            all_titles.update(est_parse_episode_titles(nuxt_src, batch_page))
            all_chapter_titles.update(est_parse_chapter_titles(nuxt_src, batch_page))
        except RuntimeError as e:
            print(f"    [エラー] バッチ取得失敗: {e}")
        if batch_i < len(batch_list):
            time.sleep(args.delay)

    if args.list_only:
        # ページ単位取得のためタイトルをここで組み立て
        _ep_list_estar = []
        _cur_title = ""
        _page_in_ep = 0
        for _p in target_pages:
            _t = all_titles.get(_p, "")
            if _t:
                _cur_title = _t
                _page_in_ep = 1
                _ep_list_estar.append(_cur_title)
            else:
                _page_in_ep += 1
        _show_episode_list(info["title"], info["author"], _ep_list_estar)

    # 青空文庫テキスト組み立て
    print("[3/3] テキスト・ePub を生成中...")
    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "エブリスタ")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "estar_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_pages = _apply_resume(args, txt_path, target_pages)
    if not target_pages and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    current_ep_title = ""
    current_chapter  = ""
    page_in_episode  = 0

    for page_no in target_pages:
        body_raw = all_bodies.get(page_no, "（取得失敗）")
        body = (normalize_tate(body_raw)
                if body_raw != "（取得失敗）" else body_raw)

        ep_start = all_titles.get(page_no, "")
        if ep_start:
            current_ep_title = ep_start
            page_in_episode  = 1
        else:
            page_in_episode += 1

        chapter_upd = all_chapter_titles.get(page_no, "")
        if chapter_upd:
            current_chapter = chapter_upd

        if page_in_episode <= 1:
            ep_title = current_ep_title or f"第{page_no}話"
        else:
            ep_title = (f"{current_ep_title}（{page_in_episode}）"
                        if current_ep_title else f"第{page_no}話")
        sec_title = aozora_chapter_title(ep_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep_title, "body": body,
                               "group": current_chapter or None})

    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    got = sum(1 for p in target_pages if p in all_bodies)
    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得ページ数: {got} / {len(target_pages)}")
    print(f"   総文字数   : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "エブリスタ", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ハーメルン スクレーパー
# ══════════════════════════════════════════

_HAM_BASE = "https://syosetu.org"
_HAM_UA   = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/131.0.0.0 Safari/537.36")
# エピソードページはCloudflare Managed Challengeのため、
# Playwrightで新規コンテキストを作成して各話を取得する。
_HAM_CF_WAIT = 5  # Cloudflareチャレンジ解決待機秒数


def hameln_get_work_info(soup) -> dict:
    """トップページから作品情報（タイトル・著者・あらすじ）を返す。"""
    maind = soup.find("div", id="maind")
    title, author, synopsis = "", "", ""
    if maind:
        title_el = maind.find(attrs={"itemprop": "name"})
        if title_el:
            title = title_el.get_text(strip=True)
        author_el = maind.find(attrs={"itemprop": "author"})
        if author_el:
            author = author_el.get_text(strip=True)
        # あらすじ: 2番目の div.ss
        ss_divs = maind.find_all("div", class_="ss")
        if len(ss_divs) >= 2:
            syp = ss_divs[1]
            for br in syp.find_all("br"):
                br.replace_with("\n")
            synopsis = syp.get_text().strip()
    return {"title": title, "author": author, "description": synopsis}


def hameln_get_episode_list(soup) -> list:
    """トップページからエピソード一覧を [(ep_num, href, title, chapter), ...] で返す。"""
    episodes = []
    current_chapter = ""
    table = soup.find("table")
    if not table:
        return episodes
    for row in table.find_all("tr"):
        span = row.find("span", id=True)
        a    = row.find("a", href=True)
        if span and a and span["id"].isdigit():
            episodes.append((int(span["id"]), a["href"], a.get_text(strip=True), current_chapter))
        else:
            # 章ヘッダー行: <td colspan=2><strong>章名</strong></td>
            td = row.find("td", attrs={"colspan": True})
            if td:
                strong = td.find("strong")
                if strong:
                    chapter_text = strong.get_text(strip=True)
                    if chapter_text:
                        current_chapter = chapter_text
    return episodes


def hameln_html_to_aozora(honbun_div, maegaki_div=None, atogaki_div=None) -> str:
    """本文div（<p>タグ）を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby><rb>底</rb><rt>そこ</rt></ruby> → 底《そこ》
    for ruby in honbun_div.find_all("ruby"):
        rb = ruby.find("rb")
        rt = ruby.find("rt")
        if rt:
            rt_text = rt.get_text()
            base_text = rb.get_text() if rb else ruby.get_text()
            prev = _bs4_prev_text(ruby)
            pipe = "|" if _ruby_needs_pipe(base_text, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base_text}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    parts = []

    # 前書き（画像URLのみの行は除去）
    if maegaki_div:
        for br in maegaki_div.find_all("br"):
            br.replace_with("\n")
        maegaki_text = maegaki_div.get_text().strip()
        lines = [l for l in maegaki_text.split("\n")
                 if not re.match(r'https?://\S+$', l.strip()) and l.strip()]
        if lines:
            parts.append("【前書き】\n" + "\n".join(lines))

    # 本文（各<p>を段落として取得）
    body_lines = []
    for p in honbun_div.find_all("p"):
        text    = p.get_text()
        stripped = text.strip()
        if not stripped or stripped == "　":
            body_lines.append("")
        else:
            body_lines.append(stripped)
    while body_lines and body_lines[-1] == "":
        body_lines.pop()
    parts.append("\n".join(body_lines))

    # 後書き
    if atogaki_div:
        for br in atogaki_div.find_all("br"):
            br.replace_with("\n")
        atogaki_text = atogaki_div.get_text().strip()
        if atogaki_text:
            parts.append("【後書き】\n" + atogaki_text)

    return "\n\n".join(p for p in parts if p)


def run_hameln(args):
    """ハーメルン小説のダウンロード処理。"""
    if not _HAMELN_AVAILABLE:
        print("エラー: ハーメルンのダウンロードには playwright が必要です。")
        print("  pip install playwright")
        print("  python -m playwright install chromium")
        sys.exit(1)
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: ハーメルンのダウンロードには beautifulsoup4 が必要です。")
        print("  pip install beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r'/novel/(\d+)', work_url)
    if not wid_m:
        print(f"エラー: ハーメルンの作品URLとして認識できません: {work_url}")
        sys.exit(1)
    work_id = wid_m.group(1)
    top_url = f"{_HAM_BASE}/novel/{work_id}/"

    print(f"\n[1/3] 作品情報を取得中: {top_url}")
    # トップページはCloudflare保護なし → requestsで取得
    rq_sess = requests.Session()
    rq_sess.headers.update({"User-Agent": _HAM_UA, "Accept-Language": "ja,en;q=0.9"})
    rq_resp = rq_sess.get(top_url, timeout=30)
    rq_resp.encoding = rq_resp.apparent_encoding or "utf-8"
    top_soup = BeautifulSoup(rq_resp.text, "html.parser")

    info = hameln_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    all_eps = hameln_get_episode_list(top_soup)
    if not all_eps:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)
    total_eps = len(all_eps)
    print(f"      エピソード数: {total_eps}")

    start_ep = max(1, args.start or 1)
    end_ep   = min(total_eps, args.end or total_eps)
    target   = [ep for ep in all_eps if start_ep <= ep[0] <= end_ep]

    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep[2] for ep in target])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ハーメルン")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "hameln_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target = _apply_resume(args, txt_path, target)
    if not target and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target)} 話）...")
    print(f"      ※ Cloudflare対策のため1話あたり約{_HAM_CF_WAIT}秒の待機が発生します")

    got           = 0

    with _hameln_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        for ep_i, (ep_num, ep_href, ep_title_list, ep_chapter) in enumerate(target, 1):
            ep_file = ep_href.lstrip("./")   # "./N.html" → "N.html"
            ep_url  = f"{_HAM_BASE}/novel/{work_id}/{ep_file}"
            print(f"  [{ep_i:3d}/{len(target)}] {ep_title_list}")

            ep_title = ep_title_list
            ctx = None
            try:
                ctx = browser.new_context(user_agent=_HAM_UA, locale="ja-JP")
                pg  = ctx.new_page()
                pg.goto(ep_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(_HAM_CF_WAIT)
                ep_html = pg.content()
                ctx.close()
                ctx = None

                ep_soup = BeautifulSoup(ep_html, "html.parser")

                # エピソードタイトル（ページ内のspan[style*=120%]から取得）
                ss = ep_soup.find("div", class_="ss")
                if ss:
                    for child in ss.children:
                        if (hasattr(child, "name") and child.name == "span"
                                and "120%" in child.get("style", "")
                                and child.get("id") != "analytics_start"):
                            candidate = child.get_text(strip=True)
                            if candidate:
                                ep_title = candidate
                                break

                honbun  = ep_soup.find("div", id="honbun")
                maegaki = ep_soup.find("div", id="maegaki")
                atogaki = ep_soup.find("div", id="atogaki")

                if honbun:
                    body = hameln_html_to_aozora(honbun, maegaki, atogaki)
                    body = normalize_tate(body)
                    sec_title = aozora_chapter_title(ep_title)
                    sections.append(f"{sec_title}\n\n{body}\n")
                    epub_episodes.append({"title": ep_title, "body": body,
                                          "group": ep_chapter or None})
                    got += 1
                else:
                    print(f"    [警告] 本文が見つかりません（CF未解決の可能性）")
                    sec_title = aozora_chapter_title(ep_title)
                    sections.append(f"{sec_title}\n\n（取得失敗）\n")
                    epub_episodes.append({"title": ep_title, "body": "（取得失敗）",
                                          "group": ep_chapter or None})

            except Exception as e:
                print(f"    [エラー] {e}")
                sec_title = aozora_chapter_title(ep_title)
                sections.append(f"{sec_title}\n\n（取得失敗）\n")
                epub_episodes.append({"title": ep_title, "body": "（取得失敗）",
                                      "group": ep_chapter or None})
                if ctx:
                    try:
                        ctx.close()
                    except Exception:
                        pass

            if ep_i < len(target):
                time.sleep(args.delay)

        browser.close()

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得エピソード: {got} / {len(target)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "ハーメルン", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ネオページ スクレーパー
# ══════════════════════════════════════════
# 依存: requests + beautifulsoup4（playwright 不要）
# 作品情報: /book/{id} の __next_f (Next.js RSC) から取得
# 章本文: /v1/book/content/{chapter_id} API から取得（content フィールド）
# チェーン: API レスポンスの next.chapter_id を辿る

_NEOPAGE_BASE    = "https://www.neopage.com"
_NEOPAGE_HEADERS = {
    "User-Agent":      UA,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
}


def _neopage_fetch(url: str, retries: int = 3) -> str:
    """requests でページ HTML を取得する。失敗時は RuntimeError。"""
    sess = requests.Session()
    sess.headers.update(_NEOPAGE_HEADERS)
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, timeout=30)
            resp.raise_for_status()
            # サーバーが charset=utf-8 を明示しているため apparent_encoding は使わない
            # （chardet が Windows-1254 等に誤検出してタイトル文字化けが起きる）
            resp.encoding = resp.encoding or "utf-8"
            return resp.text
        except Exception as e:
            if attempt >= retries:
                raise RuntimeError(f"取得失敗: {url} ({e})")
            time.sleep(5)
    return ""


def _neopage_parse_next_f(html: str) -> list:
    """
    self.__next_f.push([1,"KEY:JSON\\n"]) から JSON オブジェクトを抽出する。
    各プッシュのペイロードを展開して行ごとに解析し、dict/list 型の値を収集する。
    """
    objects = []
    for m in re.finditer(
        r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html
    ):
        raw = m.group(1)
        try:
            text = json.loads(f'"{raw}"')
        except Exception:
            continue
        for line in text.splitlines():
            colon = line.find(":")
            if colon < 0:
                continue
            val = line[colon + 1:].strip()
            if val and val[0] in ("{", "["):
                try:
                    obj = json.loads(val)
                    if isinstance(obj, (dict, list)):
                        objects.append(obj)
                except Exception:
                    pass
    return objects


def _neopage_find_book_obj(obj, book_id: str, depth: int = 0):
    """
    book_id が一致し、かつ name と first_chapter_id を持つ
    辞書を再帰探索して返す。見つからない場合は None。
    """
    if depth > 15:
        return None
    if isinstance(obj, dict):
        if (obj.get("book_id") == book_id
                and isinstance(obj.get("name"), str) and obj["name"]
                and isinstance(obj.get("first_chapter_id"), str) and obj["first_chapter_id"]):
            return obj
        for v in obj.values():
            found = _neopage_find_book_obj(v, book_id, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _neopage_find_book_obj(item, book_id, depth + 1)
            if found:
                return found
    return None


def neopage_get_work_info(html: str, book_id: str) -> dict:
    """
    /book/{id} ページの __next_f から作品情報を返す。
    keys: title / author / synopsis / first_chapter_id / total_chapter
    """
    objects = _neopage_parse_next_f(html)

    book_obj = None
    for obj in objects:
        book_obj = _neopage_find_book_obj(obj, book_id)
        if book_obj:
            break

    if book_obj is None:
        return {"title": "", "author": "", "synopsis": "",
                "first_chapter_id": "", "total_chapter": 0}

    title            = book_obj.get("name") or ""
    synopsis         = book_obj.get("intro") or ""
    first_chapter_id = book_obj.get("first_chapter_id") or ""
    total_chapter    = int(book_obj.get("total_chapter") or 0)

    author_obj = book_obj.get("author") or {}
    author = (author_obj.get("author_name") or "") if isinstance(author_obj, dict) else ""

    return {
        "title":            title,
        "author":           author,
        "synopsis":         synopsis,
        "first_chapter_id": first_chapter_id,
        "total_chapter":    total_chapter,
    }


def neopage_fetch_chapter(chapter_id: str, retries: int = 3) -> dict:
    """
    /v1/book/content/{chapter_id} API から章データを返す。
    keys: name / content / next_chapter_id / is_last / volume_name
    content が null（有料章等）の場合は空文字。
    """
    url  = f"{_NEOPAGE_BASE}/v1/book/content/{chapter_id}"
    sess = requests.Session()
    sess.headers.update({**_NEOPAGE_HEADERS, "Accept": "application/json"})
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"API エラー: {data.get('message')}")
            ch      = data["data"]
            next_ch = ch.get("next") or {}
            return {
                "name":            ch.get("name") or "",
                "content":         ch.get("content") or "",
                "next_chapter_id": (next_ch.get("chapter_id") or "")
                                   if isinstance(next_ch, dict) else "",
                "is_last":         bool(ch.get("isLastChapter")),
                "volume_name":     ch.get("volume_name") or "",
            }
        except RuntimeError:
            raise
        except Exception as e:
            if attempt >= retries:
                raise RuntimeError(f"章取得失敗: {chapter_id} ({e})")
            time.sleep(5)
    return {"name": "", "content": "", "next_chapter_id": "", "is_last": True,
            "volume_name": ""}


def neopage_content_to_aozora(content_html: str) -> str:
    """
    /v1/book/content/ API の content フィールド（<p> タグ HTML）を
    青空文庫書式テキストに変換する。
    """
    soup = BeautifulSoup(content_html, "html.parser")

    # ルビ変換: <ruby><rb>底</rb><rt>そこ</rt></ruby> → |底《そこ》
    for ruby in soup.find_all("ruby"):
        rb = ruby.find("rb")
        rt = ruby.find("rt")
        if rt:
            rt_text = rt.get_text()
            base_text = rb.get_text() if rb else ruby.get_text()
            prev = _bs4_prev_text(ruby)
            pipe = "|" if _ruby_needs_pipe(base_text, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base_text}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    lines = []
    for p in soup.find_all("p"):
        text = p.get_text(separator="\n").strip()
        lines.append(text if text else "")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def run_neopage(args):
    """ネオページ小説のダウンロード処理（requests のみ、playwright 不要）。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: ネオページのダウンロードには beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r'/book/(\w+)', work_url)
    if not wid_m:
        print(f"エラー: ネオページの作品URLとして認識できません: {work_url}")
        sys.exit(1)
    book_id = wid_m.group(1)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    book_html = _neopage_fetch(work_url)
    info = neopage_get_work_info(book_html, book_id)

    if not info["title"]:
        print("エラー: タイトルを取得できませんでした。")
        sys.exit(1)
    print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")
    if info["total_chapter"]:
        print(f"      総話数      : {info['total_chapter']}")

    if not info["first_chapter_id"]:
        print("エラー: 第1話のIDを取得できませんでした。")
        sys.exit(1)

    # ── /v1/book/content/ API でチェーン探索・全章リスト構築 ─────────────────
    # --end が指定されていればその分だけ取得して打ち切る（高速化）
    end_arg   = getattr(args, "end", None) or 0
    start_arg = max(1, getattr(args, "start", None) or 1)
    max_chain = end_arg if end_arg else (info["total_chapter"] or 9999) + 50

    print("[2/3] 章リストを構築中...")
    chapters       = []  # [(chapter_id, chapter_title, volume_name), ...]
    content_cache  = {}  # {chapter_id: content_html}  ← 本文キャッシュ
    cur_id         = info["first_chapter_id"]
    current_volume = ""  # volume_name は各章の先頭話にのみ設定されるため引き継ぐ

    while cur_id and len(chapters) < max_chain:
        try:
            ch_data = neopage_fetch_chapter(cur_id)
        except RuntimeError as e:
            print(f"  [警告] 章情報取得失敗 (id={cur_id}): {e}")
            break
        if ch_data["volume_name"]:
            current_volume = ch_data["volume_name"]
        ch_title = ch_data["name"] or f"第{len(chapters) + 1}話"
        chapters.append((cur_id, ch_title, current_volume))
        content_cache[cur_id] = ch_data["content"]  # キャッシュ
        n = len(chapters)
        if n % 20 == 0:
            print(f"  ... {n} 章取得済み")
        if ch_data["is_last"] or not ch_data["next_chapter_id"] or ch_data["next_chapter_id"] == cur_id:
            break
        cur_id = ch_data["next_chapter_id"]
        time.sleep(0.3)  # チェーン探索は軽量なので短め

    if not chapters:
        print("エラー: 章リストを構築できませんでした。")
        sys.exit(1)

    total_chapters = len(chapters)
    print(f"      章数        : {total_chapters}")

    start_ep = max(1, start_arg)
    end_ep   = min(total_chapters, end_arg or total_chapters)
    target   = chapters[start_ep - 1:end_ep]

    if args.list_only:
        _show_episode_list(info["title"], info["author"], [ch[1] for ch in target])  # ch[1]=title
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"],
                             info["synopsis"], source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ネオページ")
    base      = _apply_output_dir(
        args, args.output or safe_filename(info["title"], "neopage_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target = _apply_resume(args, txt_path, target)
    if not target and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    # ── 本文組み立て（キャッシュ済みコンテンツを使用） ───────────────────────
    print(f"[3/3] テキスト・ePub を生成中（{len(target)} 話）...")
    got           = 0

    for ep_i, (ch_id, ch_title, ch_volume) in enumerate(target, 1):
        content = content_cache.get(ch_id, "")
        if content:
            body = neopage_content_to_aozora(content)
            body = normalize_tate(body)
        else:
            body = "（有料章または非公開）"

        sec_title = aozora_chapter_title(ch_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ch_title, "body": body, "group": ch_volume or None})
        if body not in ("（取得失敗）", "（有料章または非公開）"):
            got += 1

    write_file(txt_path, header, sections, colophon,
               args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得話数  : {got} / {len(target)}")
    print(f"   総文字数  : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["synopsis"],
                   work_url, "ネオページ", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ソリスピア スクレーパー
# ══════════════════════════════════════════
# 依存: requests + beautifulsoup4（playwright 不要、SSR）
# 作品URL: /title/{id}
# エピソードURL: /novel/{episode_id}（→作品ページ /title/{id} へ正規化）
# 本文: div#novelContent 最深divにテキストノードと <br> が交互

_SOLISPIA_BASE    = "https://solispia.com"
_SOLISPIA_HEADERS = {
    "User-Agent":      UA,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
}


def _solispia_fetch(url: str, retries: int = 3):
    """requests でページを取得して BeautifulSoup を返す。失敗時は RuntimeError。"""
    sess = requests.Session()
    sess.headers.update(_SOLISPIA_HEADERS)
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt >= retries:
                raise RuntimeError(f"取得失敗: {url} ({e})")
            time.sleep(5)


def solispia_get_work_info(soup) -> dict:
    """タイトルページから作品情報（タイトル・著者・あらすじ）を返す。"""
    title_el  = soup.find("h1", class_="text-title")
    title     = title_el.get_text(strip=True) if title_el else ""
    # 著者: 最初の main-user-underline リンク
    author_el = soup.find("a", class_="main-user-underline")
    author    = author_el.get_text(strip=True) if author_el else ""
    syn_el    = soup.find("div", class_="summary")
    synopsis  = syn_el.get_text().strip() if syn_el else ""
    return {"title": title, "author": author, "description": synopsis}


def solispia_get_episode_list(soup) -> list:
    """
    タイトルページから全エピソードの (url, title, chapter_name) リストを返す。
    div.chapters > details.chapter-group の2階層構造から章名を取得する。
    章グループがない場合は chapter_name = "" のフラットフォールバックを使用。
    """
    chapters_div = soup.find("div", class_="chapters")
    if chapters_div:
        episodes  = []
        seen_urls = set()
        for group in chapters_div.find_all("details", class_="chapter-group"):
            # 章名: summary > span.chapter-title
            summary = group.find("summary", class_="chapter-summary")
            ch_span = summary.find("span", class_="chapter-title") if summary else None
            chapter_name = ch_span.get_text(strip=True) if ch_span else ""
            # エピソードリンク
            for a in group.find_all("a", class_=lambda c: c and "row-link" in c):
                href = a.get("href", "").strip()
                if not href or href in seen_urls:
                    continue
                title_span = a.find("span", class_="textleft")
                ep_title   = title_span.get_text(strip=True) if title_span else a.get_text(strip=True)
                if ep_title:
                    episodes.append((href, ep_title, chapter_name))
                    seen_urls.add(href)
        if episodes:
            return episodes

    # フォールバック: デスクトップ用 div.episode から章情報なしで収集
    container = soup.find("div", class_="episode") or soup
    episodes  = []
    seen_urls = set()
    for a in container.find_all("a", class_=lambda c: c and "row-link" in c):
        href = a.get("href", "").strip()
        if not href or href in seen_urls:
            continue
        title_span = a.find("span", class_="textleft")
        ep_title   = title_span.get_text(strip=True) if title_span else a.get_text(strip=True)
        if ep_title:
            episodes.append((href, ep_title, ""))
            seen_urls.add(href)
    return episodes


def _solispia_deepest_text_div(el):
    """
    div#novelContent 以下で、テキストノードと <br> を直接子に持つ
    最深の div を返す。
    """
    while True:
        child_divs = [c for c in el.children
                      if getattr(c, "name", None) == "div"]
        if not child_divs:
            return el
        el = child_divs[0]


def solispia_html_to_aozora(soup) -> str:
    """
    エピソードページの div#novelContent から本文を青空文庫書式で返す。
    テキストノードと <br> タグを走査し、<br> 2個以上で空行を挿入する。
    """
    content_el = soup.find(id="novelContent")
    if not content_el:
        return ""

    # ルビ変換（存在する場合）
    for ruby in content_el.find_all("ruby"):
        rb = ruby.find("rb")
        rt = ruby.find("rt")
        if rt:
            rt_text = rt.get_text()
            base_text = rb.get_text() if rb else ruby.get_text()
            prev = _bs4_prev_text(ruby)
            pipe = "|" if _ruby_needs_pipe(base_text, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base_text}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    deepest  = _solispia_deepest_text_div(content_el)
    lines    = []
    br_count = 0

    for child in deepest.children:
        child_name = getattr(child, "name", None)
        if child_name == "br":
            br_count += 1
        elif child_name is None:  # NavigableString（テキストノード）
            text = str(child)
            if text.strip():
                if br_count >= 2:
                    lines.append("")
                lines.append(text.rstrip())
                br_count = 0
        else:
            # span 等の他タグ（テキスト抽出）
            text = child.get_text()
            if text.strip():
                if br_count >= 2:
                    lines.append("")
                lines.append(text.rstrip())
                br_count = 0

    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def run_solispia(args):
    """ソリスピア小説のダウンロード処理（requests + BS4 のみ、playwright 不要）。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: ソリスピアのダウンロードには beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")

    # エピソードURL（/novel/ID）が指定された場合は作品トップへ正規化
    if re.search(r"/novel/\d+", work_url):
        print(f"\n[情報] エピソードURLを検出。作品トップページを探しています...")
        try:
            ep_soup  = _solispia_fetch(work_url)
            title_a  = ep_soup.find("a", href=lambda h: h and re.search(r"/title/\d+$", h))
            if title_a:
                work_url = title_a["href"].split("?")[0].rstrip("/")
                print(f"       作品トップ: {work_url}")
            else:
                print("  [警告] 作品トップページへのリンクを検出できませんでした。")
        except RuntimeError as e:
            print(f"  [警告] 正規化失敗: {e}")

    tid_m = re.search(r"/title/(\d+)", work_url)
    if not tid_m:
        print(f"エラー: ソリスピアの作品URLとして認識できません: {work_url}")
        sys.exit(1)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup = _solispia_fetch(work_url)

    info = solispia_get_work_info(top_soup)
    if not info["title"]:
        print("エラー: タイトルを取得できませんでした。")
        sys.exit(1)
    print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    all_eps = solispia_get_episode_list(top_soup)
    if not all_eps:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)
    total_eps = len(all_eps)
    print(f"      エピソード数: {total_eps}")

    start_ep = max(1, getattr(args, "start", None) or 1)
    end_ep   = min(total_eps, getattr(args, "end", None) or total_eps)
    target   = all_eps[start_ep - 1:end_ep]

    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep[1] for ep in target])  # ep[1]=title
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"],
                             info["description"], source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ソリスピア")
    base     = _apply_output_dir(
        args, args.output or safe_filename(info["title"], "solispia_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target = _apply_resume(args, txt_path, target)
    if not target and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target)} 話）...")
    got           = 0

    for ep_i, (ep_url, ep_title, ep_chapter) in enumerate(target, 1):
        print(f"  [{ep_i:3d}/{len(target)}] {ep_title[:40]}")
        try:
            ep_soup = _solispia_fetch(ep_url)
            body    = solispia_html_to_aozora(ep_soup)
            body    = normalize_tate(body)
        except RuntimeError as e:
            print(f"    [エラー] 取得失敗: {e}")
            body = "（取得失敗）"

        sec_title = aozora_chapter_title(ep_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep_title, "body": body, "group": ep_chapter or None})
        if body != "（取得失敗）":
            got += 1
        if ep_i < len(target):
            time.sleep(args.delay)

    print(f"[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon,
               args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得話数  : {got} / {len(target)}")
    print(f"   総文字数  : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "ソリスピア", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  野いちご スクレーパー
# ══════════════════════════════════════════

_NIC_BASE = "https://www.no-ichigo.jp"
_NIC_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.no-ichigo.jp/",
}


def noichigo_fetch(session, url, retries=3):
    """野いちごのページを取得して (BeautifulSoup, html) を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser"), resp.text
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def noichigo_get_work_info(soup) -> dict:
    """作品情報（タイトル・著者・あらすじ）を返す。"""
    og_title = soup.find("meta", property="og:title")
    title, author = "", ""
    if og_title:
        content = og_title.get("content", "")
        # "タイトル　著者名／著 | 野いちご" 形式
        m = re.match(r"^(.+?)　([^　]+?)／著", content)
        if m:
            title  = m.group(1).strip()
            author = m.group(2).strip()
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""

    synopsis_div = soup.find("div", class_="bookSummary-01")
    synopsis = synopsis_div.get_text(strip=True) if synopsis_div else ""

    return {"title": title, "author": author, "description": synopsis}


def noichigo_get_chapter_list(soup) -> list:
    """
    チャプター一覧を [(page_num, chapter_title, group_name), ...] で返す。
    bookChapterList の2階層構造を解析する：
      - 外側の <li> に <p> + 内側 <ul><li> がある場合: <p> テキストを group_name として付与
      - 外側の <li> が単独 <a> の場合: group_name = ""
    """
    chapter_list = soup.find("div", class_="bookChapterList")
    if not chapter_list:
        return []
    chapters = []
    outer_ul = chapter_list.find("ul")
    if not outer_ul:
        # フォールバック: 全 <a> をフラット収集
        for a in chapter_list.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"/book/[^/]+/(\d+)$", href)
            if m:
                chapters.append((int(m.group(1)), a.get_text(strip=True), ""))
        return chapters

    for outer_li in outer_ul.find_all("li", recursive=False):
        inner_ul = outer_li.find("ul")
        inner_items = inner_ul.find_all("li", recursive=False) if inner_ul else []
        if inner_items:
            # 章グループ: 外側 <a> タグから章名を取得して各チャプターに付与
            outer_a = outer_li.find("a", href=True, recursive=False)
            group_name = outer_a.get_text(strip=True) if outer_a else ""
            for inner_li in inner_items:
                a = inner_li.find("a", href=True)
                if a:
                    href = a["href"]
                    m = re.search(r"/book/[^/]+/(\d+)$", href)
                    if m:
                        chapters.append((int(m.group(1)), a.get_text(strip=True), group_name))
        else:
            # 単独チャプター（グループなし）
            a = outer_li.find("a", href=True)
            if a:
                href = a["href"]
                m = re.search(r"/book/[^/]+/(\d+)$", href)
                if m:
                    chapters.append((int(m.group(1)), a.get_text(strip=True), ""))
    return chapters


def noichigo_html_to_aozora(body_div) -> str:
    """本文div（<br>区切りテキスト）を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby>底<rt>そこ</rt></ruby> → 底《そこ》
    for ruby in body_div.find_all("ruby"):
        rt = ruby.find("rt")
        if rt:
            rt_text = rt.get_text()
            prev = _bs4_prev_text(ruby)
            rt.decompose()
            for rp in ruby.find_all("rp"):
                rp.decompose()
            base = ruby.get_text()
            pipe = "|" if _ruby_needs_pipe(base, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    for br in body_div.find_all("br"):
        br.replace_with("\n")

    lines = body_div.get_text().split("\n")
    out_lines = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped:
            out_lines.append(stripped)
            prev_blank = False
        else:
            if not prev_blank:
                out_lines.append("")
            prev_blank = True

    while out_lines and out_lines[0] == "":
        out_lines.pop(0)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()

    return "\n".join(out_lines)


def run_noichigo(args):
    """野いちご小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: 野いちごのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r"/book/([^/]+)$", work_url)
    if not wid_m:
        print(f"エラー: 野いちごの作品URLとして認識できません: {work_url}")
        sys.exit(1)
    work_id = wid_m.group(1)

    session = requests.Session()
    session.headers.update(_NIC_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup, _ = noichigo_fetch(session, work_url)
    info = noichigo_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    chapters = noichigo_get_chapter_list(top_soup)
    if not chapters:
        print("エラー: チャプター一覧を取得できませんでした。")
        sys.exit(1)
    total_chapters = len(chapters)
    print(f"      チャプター数: {total_chapters}")

    # 1ページ目から総ページ数を取得
    time.sleep(args.delay)
    first_soup, _ = noichigo_fetch(session, f"{_NIC_BASE}/book/{work_id}/1")
    total_pages = 0
    aside_el = first_soup.find("article", class_="bookText")
    if aside_el:
        aside_tag = aside_el.find("aside")
        if aside_tag:
            p_tag = aside_tag.find("p")
            if p_tag:
                m = re.match(r"\d+\s*/\s*(\d+)", p_tag.get_text(strip=True))
                if m:
                    total_pages = int(m.group(1))
    if total_pages:
        print(f"      総ページ数  : {total_pages}")

    # チャプター範囲を構築 [(page_start, page_end, title, group_name), ...]
    chapter_ranges = []
    for i, (page_start, ch_title, ch_group) in enumerate(chapters):
        if i + 1 < len(chapters):
            page_end = chapters[i + 1][0] - 1
        else:
            page_end = total_pages if total_pages else page_start
        chapter_ranges.append((page_start, page_end, ch_title, ch_group))

    start_ch = max(1, args.start or 1)
    end_ch   = min(total_chapters, args.end or total_chapters)
    target_chapters = chapter_ranges[start_ch - 1:end_ch]
    total_targets   = sum(e - s + 1 for s, e, _t, _g in target_chapters)

    if args.list_only:
        _show_episode_list(info["title"], info["author"], [ch[2] for ch in target_chapters])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "野いちご")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "noichigo_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_chapters = _apply_resume(args, txt_path, target_chapters)
    if not target_chapters and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] チャプターを取得中（{len(target_chapters)} チャプター）...")

    got_chapters  = 0

    for ch_i, (page_start, page_end, ch_title, ch_group) in enumerate(target_chapters, 1):
        print(f"  [{ch_i:3d}/{len(target_chapters)}] {ch_title}（p.{page_start}–{page_end}）")
        page_bodies = []
        for page_no in range(page_start, page_end + 1):
            try:
                ep_url  = f"{_NIC_BASE}/book/{work_id}/{page_no}"
                ep_soup, _ = noichigo_fetch(session, ep_url)
                art = ep_soup.find("article", class_="bookText")
                if art:
                    aside_inner = art.find("aside")
                    if aside_inner:
                        aside_inner.decompose()
                    body_div = art.find("div")
                    if body_div:
                        page_bodies.append(noichigo_html_to_aozora(body_div))
                    else:
                        page_bodies.append("（本文取得失敗）")
                else:
                    page_bodies.append("（本文取得失敗）")
            except RuntimeError as e:
                print(f"    [エラー] {e}")
                page_bodies.append("（取得失敗）")
            if page_no < page_end:
                time.sleep(args.delay)

        body = "\n\n".join(b for b in page_bodies if b)
        body = normalize_tate(body)
        sec_title = aozora_chapter_title(ch_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ch_title, "body": body, "group": ch_group or None})
        got_chapters += 1
        if ch_i < len(target_chapters):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得チャプター: {got_chapters} / {len(target_chapters)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "野いちご", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  berry's cafe スクレーパー
# ══════════════════════════════════════════

_BERRYS_BASE = "https://www.berrys-cafe.jp"
_BERRYS_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.berrys-cafe.jp/",
}


def berrys_fetch(session, url, retries=3):
    """berry's cafe のページを取得して BeautifulSoup を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def berrys_get_work_info(soup) -> dict:
    """作品情報（タイトル・著者・あらすじ・総ページ数）を返す。"""
    # タイトル: div.title-wrap > div.title > h2
    title = ""
    title_el = soup.select_one("div.title-wrap div.title h2")
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        h2 = soup.find("h2")
        title = h2.get_text(strip=True) if h2 else ""

    # 著者: div.subDetails-02 > div.name > a
    author = ""
    author_el = soup.select_one("div.subDetails-02 div.name a")
    if author_el:
        author = author_el.get_text(strip=True)

    # あらすじ
    synopsis_div = soup.find("div", class_="bookSummary-01")
    synopsis = ""
    if synopsis_div:
        for br in synopsis_div.find_all("br"):
            br.replace_with("\n")
        synopsis = synopsis_div.get_text(strip=True)

    # 総ページ数: div.bookInfo dl dd の中から "NNページ" を探す
    total_pages = 0
    for dd in soup.find_all("dd"):
        m = re.match(r"(\d+)ページ", dd.get_text(strip=True))
        if m:
            total_pages = int(m.group(1))
            break

    return {"title": title, "author": author, "description": synopsis,
            "total_pages": total_pages}


def run_berrys(args):
    """berry's cafe 小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: berry's cafeのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r"/book/([^/]+)$", work_url)
    if not wid_m:
        print(f"エラー: berry's cafeの作品URLとして認識できません: {work_url}")
        sys.exit(1)
    work_id = wid_m.group(1)

    session = requests.Session()
    session.headers.update(_BERRYS_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup = berrys_fetch(session, work_url)
    info = berrys_get_work_info(top_soup)
    if not info["title"]:
        print("エラー: タイトルを取得できませんでした。")
        sys.exit(1)
    print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    # チャプター一覧（野いちごと同構造: div.bookChapterList）
    chapters = noichigo_get_chapter_list(top_soup)
    if not chapters:
        print("エラー: チャプター一覧を取得できませんでした。")
        sys.exit(1)
    total_chapters = len(chapters)
    print(f"      チャプター数: {total_chapters}")

    total_pages = info["total_pages"]
    if total_pages:
        print(f"      総ページ数  : {total_pages}")
    else:
        # フォールバック: 1ページ目の og:title "(1/N)" から取得
        time.sleep(args.delay)
        first_soup = berrys_fetch(session, f"{_BERRYS_BASE}/book/{work_id}/1")
        og_title = first_soup.find("meta", property="og:title")
        if og_title:
            m = re.search(r"\((\d+)/(\d+)\)", og_title.get("content", ""))
            if m:
                total_pages = int(m.group(2))
        if total_pages:
            print(f"      総ページ数  : {total_pages}")

    # チャプター範囲を構築 [(page_start, page_end, title, group_name), ...]
    chapter_ranges = []
    for i, (page_start, ch_title, ch_group) in enumerate(chapters):
        if i + 1 < len(chapters):
            page_end = chapters[i + 1][0] - 1
        else:
            page_end = total_pages if total_pages else page_start
        chapter_ranges.append((page_start, page_end, ch_title, ch_group))

    start_ch = max(1, args.start or 1)
    end_ch   = min(total_chapters, args.end or total_chapters)
    target_chapters = chapter_ranges[start_ch - 1:end_ch]
    total_targets   = sum(e - s + 1 for s, e, _t, _g in target_chapters)

    if args.list_only:
        _show_episode_list(info["title"], info["author"], [ch[2] for ch in target_chapters])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "berry's cafe")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "berrys_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_chapters = _apply_resume(args, txt_path, target_chapters)
    if not target_chapters and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] チャプターを取得中（{len(target_chapters)} チャプター）...")

    got_chapters  = 0

    for ch_i, (page_start, page_end, ch_title, ch_group) in enumerate(target_chapters, 1):
        print(f"  [{ch_i:3d}/{len(target_chapters)}] {ch_title}（p.{page_start}–{page_end}）")
        page_bodies = []
        for page_no in range(page_start, page_end + 1):
            try:
                ep_url  = f"{_BERRYS_BASE}/book/{work_id}/{page_no}"
                ep_soup = berrys_fetch(session, ep_url)
                body_div = ep_soup.select_one("div.bookContent div.bookBody")
                if body_div:
                    page_bodies.append(noichigo_html_to_aozora(body_div))
                else:
                    page_bodies.append("（本文取得失敗）")
            except RuntimeError as e:
                print(f"    [エラー] {e}")
                page_bodies.append("（取得失敗）")
            if page_no < page_end:
                time.sleep(args.delay)

        body = "\n\n".join(b for b in page_bodies if b)
        body = normalize_tate(body)
        sec_title = aozora_chapter_title(ch_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ch_title, "body": body, "group": ch_group or None})
        got_chapters += 1
        if ch_i < len(target_chapters):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得チャプター: {got_chapters} / {len(target_chapters)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "berry's cafe", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  monogatary.com スクレイパー
# ══════════════════════════════════════════

_MONOGATARY_BASE = "https://monogatary.com"
_MONOGATARY_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://monogatary.com/",
}


def _monogatary_fetch_json(session, url, retries=3):
    """monogatary.com の JSON API を取得して dict を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def _monogatary_fetch_html(session, url, retries=3):
    """monogatary.com の HTML を取得して文字列を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def monogatary_text_to_aozora(text: str) -> str:
    """API のエピソード本文（\\n 区切りテキスト）を青空文庫書式に変換する。"""
    lines = text.split("\n")
    out = []
    prev_blank = False
    for line in lines:
        s = line.strip()
        if s:
            out.append(s)
            prev_blank = False
        else:
            if not prev_blank:
                out.append("")
            prev_blank = True
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def run_monogatary(args):
    """monogatary.com 小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: monogatary.comのダウンロードには requests が必要です。")
        print("  pip install requests")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    ep_m = re.search(r"/episode/(\d+)$", work_url)
    st_m = re.search(r"/story/(\d+)$", work_url)
    if not ep_m and not st_m:
        print(f"エラー: monogatary.comのURLとして認識できません: {work_url}")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(_MONOGATARY_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")

    story_id    = None
    story_title = ""
    author      = ""

    if ep_m:
        ep_id    = ep_m.group(1)
        ep_data  = _monogatary_fetch_json(session, f"{_MONOGATARY_BASE}/api/episode/{ep_id}")
        contents = ep_data.get("episodeContents", {})
        story_id    = str(contents.get("storyId", ""))
        story_title = contents.get("storyTitle", "")
        author      = contents.get("userName", "")
    else:
        story_id = st_m.group(1)

    # ストーリー API でエピソード一覧取得
    story_data    = _monogatary_fetch_json(session, f"{_MONOGATARY_BASE}/api/story/{story_id}")
    episodes_list = story_data.get("episodes", [])
    if not episodes_list:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)

    # ストーリータイトル・著者が未取得の場合は最初のエピソード API から取得
    if not story_title or not author:
        first_data = _monogatary_fetch_json(
            session, f"{_MONOGATARY_BASE}/api/episode/{episodes_list[0]['episodeId']}"
        )
        c = first_data.get("episodeContents", {})
        if not story_title:
            story_title = c.get("storyTitle", "")
        if not author:
            author = c.get("userName", "")

    if not story_title:
        print("エラー: タイトルを取得できませんでした。")
        sys.exit(1)

    print(f"      タイトル    : {story_title}")
    if author:
        print(f"      著者        : {author}")

    # あらすじ: ストーリーページ og:description から取得（React SPA のため regex でパース）
    synopsis  = ""
    story_url = f"{_MONOGATARY_BASE}/story/{story_id}"
    try:
        html_text = _monogatary_fetch_html(session, story_url)
        m = re.search(
            r'<meta\b[^>]+\bproperty=["\']og:description["\'][^>]+\bcontent=["\']([^"\']*)["\']',
            html_text)
        if not m:
            m = re.search(
                r'<meta\b[^>]+\bcontent=["\']([^"\']*)["\'][^>]+\bproperty=["\']og:description["\']',
                html_text)
        if m:
            import html as _html
            synopsis = _html.unescape(m.group(1)).strip()
    except Exception:
        pass

    total_episodes = len(episodes_list)
    print(f"      エピソード数: {total_episodes}")

    start_ep = max(1, args.start or 1)
    end_ep   = min(total_episodes, args.end or total_episodes)
    target   = episodes_list[start_ep - 1:end_ep]

    if args.list_only:
        _show_episode_list(story_title, author,
                           [ep.get("episodeTitle", f"第{i}話")
                            for i, ep in enumerate(target, start_ep)])
    _dry_run_exit(args)

    header   = aozora_header(story_title, author, synopsis, source_url=story_url)
    colophon = aozora_colophon(story_title, story_url, "monogatary.com")
    base      = _apply_output_dir(args, args.output or safe_filename(story_title, "monogatary_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target = _apply_resume(args, txt_path, target)
    if not target and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target)} 話）...")

    got           = 0

    for ep_i, ep_info in enumerate(target, 1):
        ep_id    = str(ep_info["episodeId"])
        ep_title = ep_info.get("episodeTitle", f"第{ep_i + start_ep - 1}話")
        print(f"  [{ep_i:3d}/{len(target)}] {ep_title}")
        try:
            ep_data  = _monogatary_fetch_json(
                session, f"{_MONOGATARY_BASE}/api/episode/{ep_id}")
            body_raw = ep_data.get("episodeContents", {}).get("episode", "")
            body     = normalize_tate(monogatary_text_to_aozora(body_raw))
        except RuntimeError as e:
            print(f"    [エラー] {e}")
            body = "（取得失敗）"

        sec_title = aozora_chapter_title(ep_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep_title, "body": body})
        got += 1
        if ep_i < len(target):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得エピソード: {got} / {len(target)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, story_title, author,
                   synopsis,
                   story_url, "monogatary.com", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ノベマ！スクレイパー
# ══════════════════════════════════════════

_NOVEMA_BASE = "https://novema.jp"
_NOVEMA_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://novema.jp/",
}


def novema_fetch(session, url, retries=3):
    """ノベマ！のページを取得して (BeautifulSoup, html) を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser"), resp.text
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def novema_get_work_info(soup) -> dict:
    """作品情報（タイトル・著者・あらすじ）を返す。"""
    og_title = soup.find("meta", property="og:title")
    title, author = "", ""
    if og_title:
        content = og_title.get("content", "")
        # "タイトル　著者名／著 | ノベマ！" 形式
        m = re.match(r"^(.+?)　([^　]+?)／著", content)
        if m:
            title  = m.group(1).strip()
            author = m.group(2).strip()
    if not title:
        h2 = soup.find("div", class_="title")
        if h2:
            h2_tag = h2.find("h2")
            title = h2_tag.get_text(strip=True) if h2_tag else h2.get_text(strip=True)
    if not author:
        name_div = soup.find("div", class_="name")
        if name_div:
            a_tag = name_div.find("a")
            author = a_tag.get_text(strip=True) if a_tag else name_div.get_text(strip=True)

    synopsis_div = soup.find("div", class_="bookSummary-01")
    synopsis = synopsis_div.get_text(strip=True) if synopsis_div else ""

    return {"title": title, "author": author, "description": synopsis}


def novema_get_episode_list(soup) -> list:
    """
    エピソード一覧を [(page_num, episode_title, chapter_name), ...] で返す。
    bookChapterList の2階層構造を解析する：
      - 外側の <li> に <p> + 内側 <ul><li> がある場合: 章グループ名を chapter_name として付与
      - 外側の <li> に内側の <ul><li> がない場合: 単独エピソード（chapter_name = ""）
    """
    chapter_list = soup.find("div", class_="bookChapterList")
    if not chapter_list:
        return []

    episodes = []
    outer_ul = chapter_list.find("ul")
    if not outer_ul:
        return []

    for outer_li in outer_ul.find_all("li", recursive=False):
        inner_ul = outer_li.find("ul")
        inner_items = inner_ul.find_all("li", recursive=False) if inner_ul else []
        if inner_items:
            # 章グループ: 外側 <a> タグから章名を取得して各エピソードに付与
            outer_a = outer_li.find("a", href=True, recursive=False)
            chapter_name = outer_a.get_text(strip=True) if outer_a else ""
            for inner_li in inner_items:
                a = inner_li.find("a", href=True)
                if a:
                    href = a["href"]
                    m = re.search(r"/book/[^/]+/(\d+)$", href)
                    if m:
                        episodes.append((int(m.group(1)), a.get_text(strip=True), chapter_name))
        else:
            # 単独エピソード（章グループなし）
            a = outer_li.find("a", href=True)
            if a:
                href = a["href"]
                m = re.search(r"/book/[^/]+/(\d+)$", href)
                if m:
                    episodes.append((int(m.group(1)), a.get_text(strip=True), ""))

    return episodes


def run_novema(args):
    """ノベマ！小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: ノベマ！のダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r"/book/([^/]+)$", work_url)
    if not wid_m:
        print(f"エラー: ノベマ！の作品URLとして認識できません: {work_url}")
        sys.exit(1)
    work_id = wid_m.group(1)

    session = requests.Session()
    session.headers.update(_NOVEMA_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup, _ = novema_fetch(session, work_url)
    info = novema_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    episodes = novema_get_episode_list(top_soup)
    if not episodes:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)
    total_eps = len(episodes)
    print(f"      エピソード数: {total_eps}")

    start_ep = max(1, args.start or 1)
    end_ep   = min(total_eps, args.end or total_eps)
    target_eps = episodes[start_ep - 1:end_ep]
    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep[1] for ep in target_eps])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ノベマ！")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "novema_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_eps = _apply_resume(args, txt_path, target_eps)
    if not target_eps and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target_eps)} / {total_eps}）...")

    got_eps       = 0

    for ep_i, (page_num, ep_title, ep_chapter) in enumerate(target_eps, 1):
        print(f"  [{ep_i:3d}/{len(target_eps)}] {ep_title}")
        try:
            ep_url  = f"{_NOVEMA_BASE}/book/{work_id}/{page_num}"
            ep_soup, _ = novema_fetch(session, ep_url)
            art = ep_soup.find("article", class_="bookText")
            if art:
                aside_inner = art.find("aside")
                if aside_inner:
                    aside_inner.decompose()
                body_div = art.find("div")
                if body_div:
                    body = noichigo_html_to_aozora(body_div)
                else:
                    body = "（本文取得失敗）"
            else:
                body = "（本文取得失敗）"
        except RuntimeError as e:
            print(f"    [エラー] {e}")
            body = "（取得失敗）"

        body = normalize_tate(body)
        sec_title = aozora_chapter_title(ep_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep_title, "body": body, "group": ep_chapter or None})
        got_eps += 1
        if ep_i < len(target_eps):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得エピソード: {got_eps} / {len(target_eps)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "ノベマ！", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ノベルアップ＋スクレイパー
# ══════════════════════════════════════════

_NOVELUP_BASE = "https://novelup.plus"
_NOVELUP_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://novelup.plus/",
}


def novelup_fetch(session, url, retries=3):
    """ノベルアップ＋のページを取得して (BeautifulSoup, html) を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser"), resp.text
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def novelup_get_work_info(soup) -> dict:
    """作品情報（タイトル・著者・あらすじ）を返す。"""
    og_title = soup.find("meta", property="og:title")
    title, author = "", ""
    if og_title:
        content = og_title.get("content", "")
        # "タイトル（著者名） | 小説投稿サイトノベルアップ＋" 形式
        m = re.match(r"^(.+?)（(.+?)）", content)
        if m:
            title  = m.group(1).strip()
            author = m.group(2).strip()
    if not title:
        h1 = soup.find("h1", class_="storyTitle")
        title = h1.get_text(strip=True) if h1 else ""
    if not author:
        a_author = soup.find("a", class_="storyAuthor")
        author = a_author.get_text(strip=True) if a_author else ""

    synopsis_div = soup.find("div", class_="novel_synopsis")
    synopsis = synopsis_div.get_text(strip=True) if synopsis_div else ""

    return {"title": title, "author": author, "description": synopsis}


def novelup_get_episode_list(soup) -> list:
    """
    エピソード一覧を [(episode_id, episode_title, chapter), ...] で返す。
    div.episodeList 内の div.episodeListItem を順に走査し、
    class="episodeListItem chapter" は章ヘッダーとして current_chapter を更新する。
    """
    ep_list_div = soup.find("div", class_="episodeList")
    if not ep_list_div:
        return []
    episodes = []
    current_chapter = ""
    for item in ep_list_div.find_all("div", class_="episodeListItem"):
        classes = item.get("class", [])
        if "chapter" in classes:
            current_chapter = item.get_text(strip=True)
            continue
        a = item.find("a", class_="episodeTitle")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/story/[^/]+/(\d+)$", href)
        if m:
            episodes.append((m.group(1), a.get_text(strip=True), current_chapter))
    return episodes


def novelup_html_to_aozora(content_p) -> str:
    """本文 <p id="episode_content"> を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby><rb>漢字</rb><rp>(</rp><rt>かんじ</rt></ruby> → 漢字《かんじ》
    for ruby in content_p.find_all("ruby"):
        rb  = ruby.find("rb")
        rt  = ruby.find("rt")
        if rt:
            base    = rb.get_text() if rb else ""
            rt_text = rt.get_text()
            prev = _bs4_prev_text(ruby)
            pipe = "|" if _ruby_needs_pipe(base, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    # テキスト取得（\n 区切りの段落）
    text  = content_p.get_text()
    lines = text.split("\n")
    out_lines  = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped:
            out_lines.append(stripped)
            prev_blank = False
        else:
            if not prev_blank:
                out_lines.append("")
            prev_blank = True

    while out_lines and out_lines[0] == "":
        out_lines.pop(0)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()

    return "\n".join(out_lines)


def novelup_get_episode_body(soup) -> str:
    """エピソードページから本文（前書き＋本文＋後書き）を青空文庫書式で返す。"""
    parts = []

    foreword = soup.find("div", class_="novel_foreword")
    if foreword:
        text = foreword.get_text(strip=True)
        if text:
            parts.append(text)

    content_p = soup.find("p", id="episode_content")
    if content_p:
        parts.append(novelup_html_to_aozora(content_p))
    else:
        parts.append("（本文取得失敗）")

    afterword = soup.find("div", class_="novel_afterword")
    if afterword:
        text = afterword.get_text(strip=True)
        if text:
            parts.append(text)

    return "\n\n".join(parts)


def run_novelup(args):
    """ノベルアップ＋小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: ノベルアップ＋のダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    wid_m = re.search(r"/story/(\d+)$", work_url)
    if not wid_m:
        print(f"エラー: ノベルアップ＋の作品URLとして認識できません: {work_url}")
        sys.exit(1)
    work_id = wid_m.group(1)

    session = requests.Session()
    session.headers.update(_NOVELUP_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup, _ = novelup_fetch(session, work_url)
    info = novelup_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    episodes = novelup_get_episode_list(top_soup)
    if not episodes:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)
    total_eps = len(episodes)
    print(f"      エピソード数: {total_eps}")

    start_ep = max(1, args.start or 1)
    end_ep   = min(total_eps, args.end or total_eps)
    target_eps = episodes[start_ep - 1:end_ep]
    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep[1] for ep in target_eps])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ノベルアップ＋")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "novelup_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_eps = _apply_resume(args, txt_path, target_eps)
    if not target_eps and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target_eps)} / {total_eps}）...")

    got_eps       = 0

    for ep_i, (ep_id, ep_title, ep_chapter) in enumerate(target_eps, 1):
        print(f"  [{ep_i:3d}/{len(target_eps)}] {ep_title}")
        try:
            ep_url  = f"{_NOVELUP_BASE}/story/{work_id}/{ep_id}"
            ep_soup, _ = novelup_fetch(session, ep_url)
            body = novelup_get_episode_body(ep_soup)
        except RuntimeError as e:
            print(f"    [エラー] {e}")
            body = "（取得失敗）"

        body = normalize_tate(body)
        sec_title = aozora_chapter_title(ep_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep_title, "body": body,
                               "group": ep_chapter or None})
        got_eps += 1
        if ep_i < len(target_eps):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得エピソード: {got_eps} / {len(target_eps)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "ノベルアップ＋", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ステキブンゲイ：定数・ヘッダー
# ══════════════════════════════════════════

_SUTEKI_BASE = "https://sutekibungei.com"
_SUTEKI_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://sutekibungei.com/",
}


def suteki_fetch(session, url, retries=3):
    """ステキブンゲイのページを取得して (BeautifulSoup, html_text) を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=_SUTEKI_HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser"), resp.text
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def suteki_get_work_info(soup) -> dict:
    """作品情報（タイトル・著者・あらすじ）を返す。"""
    # タイトル: og:title から "タイトル - ステキブンゲイ" 形式
    og_title = soup.find("meta", property="og:title")
    title = og_title.get("content", "").strip() if og_title else ""
    title = re.sub(r"\s*[-–]\s*ステキブンゲイ$", "", title).strip()

    # あらすじ: og:description
    og_desc = soup.find("meta", property="og:description")
    description = og_desc.get("content", "").strip() if og_desc else ""

    # 著者: /users/{username} へのリンクテキスト（SSR レンダリング済み）
    author = ""
    author_a = soup.find("a", href=re.compile(r"^/users/"))
    if author_a:
        author = author_a.get_text(strip=True)

    # フォールバック: window.__NUXT__ から "name":"著者名" パターンを抽出
    if not author:
        nuxt_script = soup.find("script", string=re.compile(r"window\.__NUXT__"))
        if nuxt_script:
            m = re.search(r'"name"\s*:\s*"([^"]+)"', nuxt_script.string or "")
            if m:
                author = m.group(1)

    return {"title": title, "author": author, "description": description}


def suteki_get_episode_list(soup) -> list:
    """
    エピソード一覧を [{"title": str, "url": str}, ...] で返す。
    作品トップページの a.v-list-item--link から /novels/{uuid}/{uuid} 形式のリンクを取得。
    """
    episodes = []
    for a in soup.find_all("a", href=re.compile(
            r"^/novels/[0-9a-f-]{36}/[0-9a-f-]{36}$")):
        span = a.find("span", class_=re.compile(r"text-left"))
        if span:
            for icon in span.find_all("i"):
                icon.decompose()
            ep_title = span.get_text(strip=True)
        else:
            ep_title = a.get_text(strip=True)
        if ep_title:
            episodes.append({"title": ep_title,
                              "url": _SUTEKI_BASE + a["href"]})
    return episodes


def suteki_html_to_aozora(body_div) -> str:
    """#episodeBody の内容を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby><rb>漢字</rb><rt>かんじ</rt></ruby> → 漢字《かんじ》
    for ruby in body_div.find_all("ruby"):
        rb = ruby.find("rb")
        rt = ruby.find("rt")
        for rp in ruby.find_all("rp"):
            rp.decompose()
        if rt:
            rt_text = rt.get_text()
            base = rb.get_text() if rb else ""
            prev = _bs4_prev_text(ruby)
            pipe = "|" if _ruby_needs_pipe(base, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    text = body_div.get_text("\n")
    lines = text.split("\n")
    out_lines = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped:
            out_lines.append(stripped)
            prev_blank = False
        else:
            if not prev_blank:
                out_lines.append("")
            prev_blank = True

    while out_lines and out_lines[0] == "":
        out_lines.pop(0)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()

    return "\n".join(out_lines)


def suteki_get_episode_body(soup) -> str:
    """エピソードページから本文を青空文庫書式で返す。"""
    body_div = soup.find("div", id="episodeBody")
    if body_div:
        return suteki_html_to_aozora(body_div)
    return "（本文取得失敗）"


def run_sutekibungei(args):
    """ステキブンゲイ小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: ステキブンゲイのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url.rstrip("/")
    if not re.search(r"/novels/[0-9a-f-]{36}$", work_url):
        print(f"エラー: ステキブンゲイの作品URLとして認識できません: {work_url}")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(_SUTEKI_HEADERS)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup, _ = suteki_fetch(session, work_url)
    info = suteki_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    episodes = suteki_get_episode_list(top_soup)
    if not episodes:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)
    total_eps = len(episodes)
    print(f"      エピソード数: {total_eps}")

    start_ep   = max(1, args.start or 1)
    end_ep     = min(total_eps, args.end or total_eps)
    target_eps = episodes[start_ep - 1:end_ep]
    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep["title"] for ep in target_eps])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ステキブンゲイ")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "suteki_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_eps = _apply_resume(args, txt_path, target_eps)
    if not target_eps and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target_eps)} / {total_eps}）...")

    got_eps       = 0

    for ep_i, ep in enumerate(target_eps, 1):
        print(f"  [{ep_i:3d}/{len(target_eps)}] {ep['title']}")
        try:
            ep_soup, _ = suteki_fetch(session, ep["url"])
            body = suteki_get_episode_body(ep_soup)
        except RuntimeError as e:
            print(f"    [エラー] {e}")
            body = "（取得失敗）"

        body = normalize_tate(body)
        sec_title = aozora_chapter_title(ep["title"])
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep["title"], "body": body,
                               "group": ep.get("chapter") or None})
        got_eps += 1
        if ep_i < len(target_eps):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得エピソード: {got_eps} / {len(target_eps)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "ステキブンゲイ", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  NOVEL DAYS：定数・ヘッダー
# ══════════════════════════════════════════

_DAYS_BASE = "https://novel.daysneo.com"
_DAYS_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://novel.daysneo.com/",
}


def days_fetch(session, url, retries=3):
    """NOVEL DAYS のページを取得して (BeautifulSoup, html_text) を返す。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=_DAYS_HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser"), resp.text
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(2)


def days_get_work_info(soup) -> dict:
    """作品情報（タイトル・著者・あらすじ）を返す。"""
    # タイトル: div.detail h2 → フォールバック og:title
    title = ""
    h2 = soup.select_one("div.detail h2")
    if h2:
        title = h2.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").strip()

    # 著者: div.author a span.f18px
    author = ""
    author_span = soup.select_one("div.author a span.f18px")
    if author_span:
        author = author_span.get_text(strip=True)

    # あらすじ: p.readmore（<br> を改行に変換）
    description = ""
    synopsis_p = soup.select_one("p.readmore")
    if synopsis_p:
        for br in synopsis_p.find_all("br"):
            br.replace_with("\n")
        description = synopsis_p.get_text().strip()

    return {"title": title, "author": author, "description": description}


def days_get_episode_list(soup) -> list:
    """
    エピソード一覧を [{"title": str, "url": str, "chapter": str}, ...] で返す。
    div.contents ol 内の h4（章ヘッダー）と a（エピソードリンク）を文書順に走査する。
    <li> のネストが不正な HTML のため <li> 階層には依存せずフラット走査する。
    """
    episodes = []
    current_chapter = ""
    ol = soup.select_one("div.contents ol")
    if not ol:
        return episodes
    for tag in ol.find_all(["h4", "a"]):
        if tag.name == "h4":
            current_chapter = tag.get_text(strip=True)
        else:  # a
            href = tag.get("href", "")
            if not re.search(r"/works/episode/[0-9a-f]{32}\.html$", href):
                continue
            # 日付 span (.date) を除いた最初の span からタイトルを取得
            ep_title = ""
            for span in tag.find_all("span"):
                if "date" not in span.get("class", []):
                    ep_title = span.get_text(strip=True)
                    break
            if not ep_title:
                ep_title = tag.get_text(strip=True)
            url = (_DAYS_BASE + href) if href.startswith("/") else href
            if ep_title:
                episodes.append({"title": ep_title, "url": url,
                                  "chapter": current_chapter})
    return episodes


def days_html_to_aozora(body_div) -> str:
    """div.episode div.inner の内容を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby><rb>漢字</rb><rp>(</rp><rt>かんじ</rt><rp>)</rp></ruby> → 漢字《かんじ》
    for ruby in body_div.find_all("ruby"):
        rb = ruby.find("rb")
        rt = ruby.find("rt")
        for rp in ruby.find_all("rp"):
            rp.decompose()
        if rt:
            rt_text = rt.get_text()
            base = rb.get_text() if rb else ""
            prev = _bs4_prev_text(ruby)
            pipe = "|" if _ruby_needs_pipe(base, prev, rt_text) else ""
            ruby.replace_with(f"{pipe}{base}《{rt_text}》")
        else:
            ruby.replace_with(ruby.get_text())

    # <br> を改行に変換
    for br in body_div.find_all("br"):
        br.replace_with("\n")

    text = body_div.get_text()
    lines = text.split("\n")
    out_lines = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped:
            out_lines.append(stripped)
            prev_blank = False
        else:
            if not prev_blank:
                out_lines.append("")
            prev_blank = True

    while out_lines and out_lines[0] == "":
        out_lines.pop(0)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()

    return "\n".join(out_lines)


def days_get_episode_body(soup) -> str:
    """エピソードページから本文を青空文庫書式で返す。"""
    body_div = soup.select_one("div.episode div.inner")
    if body_div:
        return days_html_to_aozora(body_div)
    return "（本文取得失敗）"


def run_days(args):
    """NOVEL DAYS 小説のダウンロード処理。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: NOVEL DAYSのダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url
    session = requests.Session()
    session.headers.update(_DAYS_HEADERS)

    # エピソードURLが渡された場合は作品トップページへ誘導
    if re.search(r"/works/episode/[0-9a-f]{32}\.html$", work_url):
        print(f"\n[情報] エピソードURLが指定されました。作品トップページURLを取得中...")
        ep_soup, _ = days_fetch(session, work_url)
        work_link = ep_soup.select_one("a[href*='/works/'][href$='.html']:not([href*='/episode/'])")
        if work_link:
            href = work_link.get("href", "")
            work_url = (_DAYS_BASE + href) if href.startswith("/") else href
            print(f"       作品トップ: {work_url}")
        else:
            print("エラー: 作品トップページへのリンクが見つかりません。作品URLを直接指定してください。")
            sys.exit(1)

    if not re.search(r"/works/[0-9a-f]{32}\.html$", work_url):
        print(f"エラー: NOVEL DAYSの作品URLとして認識できません: {work_url}")
        sys.exit(1)

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    top_soup, _ = days_fetch(session, work_url)
    info = days_get_work_info(top_soup)
    if info["title"]:
        print(f"      タイトル    : {info['title']}")
    if info["author"]:
        print(f"      著者        : {info['author']}")

    episodes = days_get_episode_list(top_soup)
    if not episodes:
        print("エラー: エピソード一覧を取得できませんでした。")
        sys.exit(1)
    total_eps = len(episodes)
    print(f"      エピソード数: {total_eps}")

    start_ep   = max(1, args.start or 1)
    end_ep     = min(total_eps, args.end or total_eps)
    target_eps = episodes[start_ep - 1:end_ep]
    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep["title"] for ep in target_eps])
    _dry_run_exit(args)

    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "NOVEL DAYS")
    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "days_novel"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)
    sections, epub_episodes, target_eps = _apply_resume(args, txt_path, target_eps)
    if not target_eps and sections:
        print("\n[情報] 新規エピソードがありません。ファイルは上書きしません。")
        return

    print(f"[2/3] エピソードを取得中（{len(target_eps)} / {total_eps}）...")

    got_eps       = 0

    for ep_i, ep in enumerate(target_eps, 1):
        print(f"  [{ep_i:3d}/{len(target_eps)}] {ep['title']}")
        try:
            ep_soup, _ = days_fetch(session, ep["url"])
            body = days_get_episode_body(ep_soup)
        except RuntimeError as e:
            print(f"    [エラー] {e}")
            body = "（取得失敗）"

        body = normalize_tate(body)
        sec_title = aozora_chapter_title(ep["title"])
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep["title"], "body": body,
                               "group": ep.get("chapter") or None})
        got_eps += 1
        if ep_i < len(target_eps):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   取得エピソード: {got_eps} / {len(target_eps)}")
    print(f"   総文字数      : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "NOVEL DAYS", epub_episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  プロジェクト杉田玄白：定数・ヘルパー
# ══════════════════════════════════════════

_GENPAKU_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
}


def genpaku_fetch(url: str, retries: int = 3):
    """genpaku.org のページを取得して BeautifulSoup を返す。"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_GENPAKU_HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(RETRY_WAIT)


def genpaku_ruby_to_aozora(text: str) -> str:
    r"""\ruby{base}{ruby} 形式を |base《ruby》（青空文庫ルビ記法）に変換する。"""
    return re.sub(r"\\ruby\{([^}]*)\}\{([^}]*)\}", r"|\1《\2》", text)


def genpaku_get_work_info(soup) -> dict:
    """タイトル・著者（原著者＋訳者）・あらすじ（原題）を返す。"""
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    author = ""
    translator = ""
    original_title = ""

    # h1 直後の最初の div または p が情報ブロック
    if h1:
        for sib in h1.next_siblings:
            if not hasattr(sib, "name"):
                continue
            if sib.name in ("div", "p"):
                info_text = sib.get_text(separator="\n")

                # 訳者: cruel.org リンクまたは "翻訳:" テキスト
                for a_tag in sib.find_all("a"):
                    href = a_tag.get("href", "")
                    a_text = a_tag.get_text(strip=True)
                    if "cruel.org" in href and a_text:
                        translator = a_text
                        break
                if not translator:
                    m = re.search(r"翻訳[：:]\s*([^\n<（(]+)", info_text)
                    if m:
                        translator = m.group(1).strip()

                # 原著者: 行末が "著" のパターン
                for line in info_text.splitlines():
                    line = line.strip()
                    if line.endswith("著"):
                        author = line[:-1].strip()
                        break

                # 原題: アルファベットを含む最初の行
                for line in info_text.splitlines():
                    line = line.strip()
                    if line and re.search(r"[A-Za-z]", line) and len(line) > 5:
                        original_title = line
                        break
                break

    if author and translator:
        full_author = f"{author}（{translator} 訳）"
    elif translator:
        full_author = f"{translator} 訳"
    elif author:
        full_author = author
    else:
        full_author = "山形浩生"

    return {"title": title, "author": full_author, "description": original_title}


def genpaku_extract_chapters(soup, work_title: str) -> list:
    """
    HTML から章ごとに本文を抽出して [{"title": str, "body": str}, ...] を返す。

    - <h2> を章区切りとして使用。toc アンカーを持つ <h2> は目次と判定してスキップ
    - <h3>/<h4> は章内見出し（中見出し/小見出し）として処理
    - \\ruby{base}{ruby} を |base《ruby》 に変換
    - フラグメントリンクのみの段落（「目次に戻る」等）はスキップ
    """
    episodes = []
    current_title = ""
    current_lines = []

    def flush():
        nonlocal current_title, current_lines
        body_text = "\n".join(current_lines).strip()
        if body_text:
            episodes.append({
                "title": current_title if current_title else work_title,
                "body": body_text,
            })
        current_title = ""
        current_lines = []

    body_tag = soup.find("body") or soup
    h1_found = False
    info_skipped = False
    in_toc_section = False

    for elem in body_tag.children:
        if not hasattr(elem, "name"):
            continue
        name = elem.name

        if name == "h1":
            h1_found = True
            continue
        if not h1_found:
            continue

        # h1 直後の最初の div/p は情報ブロック → スキップ
        if not info_skipped and name in ("div", "p"):
            info_skipped = True
            continue

        if name == "h2":
            anchor = elem.find("a")
            anchor_id = ""
            if anchor:
                anchor_id = (anchor.get("name") or anchor.get("id") or "").lower()
            if anchor_id == "toc":
                in_toc_section = True
                continue
            in_toc_section = False
            flush()
            current_title = elem.get_text(strip=True)
            continue

        if in_toc_section:
            continue

        if name == "h3":
            text = genpaku_ruby_to_aozora(elem.get_text(strip=True))
            if text:
                current_lines.append(aozora_chapter_title(text, "中見出し"))
                current_lines.append("")

        elif name == "h4":
            text = genpaku_ruby_to_aozora(elem.get_text(strip=True))
            if text:
                current_lines.append(aozora_chapter_title(text, "小見出し"))
                current_lines.append("")

        elif name == "p":
            p_text_plain = elem.get_text(strip=True)
            if not p_text_plain:
                continue
            # フラグメントリンクのみの短い段落はナビゲーション → スキップ
            links = elem.find_all("a")
            non_frag = [a for a in links if not a.get("href", "").startswith("#")]
            if links and not non_frag and len(re.sub(r"\s+", "", p_text_plain)) < 30:
                continue
            for br in elem.find_all("br"):
                br.replace_with("\n")
            text = genpaku_ruby_to_aozora(elem.get_text().strip())
            for line in text.split("\n"):
                current_lines.append(line.strip())
            current_lines.append("")

        elif name == "blockquote":
            text = elem.get_text().strip()
            if text:
                current_lines.append(genpaku_ruby_to_aozora(text))
                current_lines.append("")

        elif name in ("ul", "ol"):
            for li in elem.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                if text:
                    current_lines.append(f"・{genpaku_ruby_to_aozora(text)}")
            current_lines.append("")

        # <hr> は無視（章区切りは <h2> で管理）

    flush()
    return episodes


def run_genpaku(args):
    """プロジェクト杉田玄白 の作品をダウンロードする。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: プロジェクト杉田玄白のダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url

    print(f"\n[1/3] 作品ページを取得中: {work_url}")
    try:
        soup = genpaku_fetch(work_url)
    except RuntimeError as e:
        print(f"エラー: {e}")
        sys.exit(1)

    info = genpaku_get_work_info(soup)
    if not info["title"]:
        print("エラー: タイトルを取得できませんでした。")
        sys.exit(1)

    print(f"      タイトル: {info['title']}")
    print(f"      著者    : {info['author']}")
    if info["description"]:
        print(f"      原題    : {info['description']}")

    print("[2/3] 本文を解析中...")
    episodes = genpaku_extract_chapters(soup, info["title"])

    if not episodes:
        print("エラー: 本文を抽出できませんでした。")
        sys.exit(1)

    print(f"      章数    : {len(episodes)}")

    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep["title"] for ep in episodes])
    _dry_run_exit(args)

    print("[3/3] テキスト・ePub を生成中...")
    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "プロジェクト杉田玄白")

    sections = []
    for ep in episodes:
        sec_title = aozora_chapter_title(ep["title"])
        sections.append(f"{sec_title}\n\n{ep['body']}\n")

    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "genpaku"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)

    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   章数        : {len(episodes)}")
    print(f"   総文字数    : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "プロジェクト杉田玄白", episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  結城浩翻訳の部屋：定数・ヘルパー
# ══════════════════════════════════════════

_HYUKI_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
}


def hyuki_fetch(url: str, retries: int = 3):
    """hyuki.com のページを取得して BeautifulSoup を返す。"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HYUKI_HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"取得失敗: {url} — {e}") from e
            time.sleep(RETRY_WAIT)


def hyuki_get_work_info(soup) -> dict:
    """
    タイトル・著者（原著者＋訳者）・あらすじを返す。

    Bootstrap設計 (leaf, magi 等):
      jumbotron の <h1> + <p>（"原作：XXX　翻訳：XXX" 形式）
    XHTML設計 (bedtime 等):
      <h1 class="title"> + <p class="author">（"XXX\\n結城浩訳" 形式）
    """
    title = ""
    author_raw = ""
    description = ""

    # ── Bootstrap 設計 ────────────────────────────
    jumbotron = soup.find("div", class_="jumbotron")
    if jumbotron:
        h1 = jumbotron.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        for p in jumbotron.find_all("p"):
            text = p.get_text(strip=True)
            if "翻訳" in text or "訳" in text or "原作" in text:
                author_raw = text
                break
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "").strip()

    # ── XHTML 設計 ────────────────────────────────
    if not title:
        h1 = soup.find("h1", class_="title")
        if h1:
            title = h1.get_text(strip=True)
        p_author = soup.find("p", class_="author")
        if p_author:
            author_raw = p_author.get_text(separator="\n").strip()

    # フォールバック: og:title / <title>
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").strip()
    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)

    # ── 著者フィールド組み立て ─────────────────────
    # Bootstrap: "原作：オー・ヘンリー　翻訳：結城浩"
    # XHTML    : "イギリス伝承童謡\n結城浩訳"
    orig = ""
    trans = ""
    if author_raw:
        m_orig  = re.search(r"原作[：:]\s*([^\s　翻訳\n]+)", author_raw)
        m_trans = re.search(r"翻訳[：:]\s*([^\s　\n]+)", author_raw)
        if m_orig:
            orig = m_orig.group(1).strip()
        if m_trans:
            trans = m_trans.group(1).strip()
        if not orig and not trans:
            # "XXX\n結城浩訳" 形式
            lines = [l.strip() for l in author_raw.splitlines() if l.strip()]
            if len(lines) >= 2:
                orig  = lines[0]
                trans = re.sub(r"訳$", "", lines[-1]).strip()
            elif len(lines) == 1:
                trans = re.sub(r"訳$", "", lines[0]).strip()

    if orig and trans:
        full_author = f"{orig}（{trans} 訳）"
    elif trans:
        full_author = f"{trans} 訳"
    elif orig:
        full_author = orig
    else:
        full_author = "結城浩 訳"

    return {"title": title, "author": full_author, "description": description}


def _hyuki_p_is_meta(p_elem) -> bool:
    """著作権・ライセンス表示など本文でない <p> を判定する。"""
    text = p_elem.get_text(strip=True)
    return (
        not text
        or text.startswith("Copyright")
        or text.startswith("©")
        or "クリエイティブ・コモンズ" in text
        or text.startswith("この作品は")
    )


def hyuki_extract_episodes(soup, work_title: str) -> list:
    """
    本文を [{"title": str, "body": str}, ...] として返す。

    Bootstrap 設計 (jumbotron あり):
      div.col-md-12 内の <p> を 1 エピソードとして抽出。
      div.panel（版権表示）が現れたら終了。

    XHTML 設計 (h1.title あり):
      h2.section を章区切りとして使用。
      <blockquote><table> がある場合は最初の <td>（日本語側）のみ抽出。
      目次見出し（アンカー id/name == "toc"）と直後の <ul> はスキップ。
    """
    # ── Bootstrap 設計 ────────────────────────────
    if soup.find("div", class_="jumbotron"):
        col = soup.select_one("div.col-md-12")
        if not col:
            return []
        lines = []
        for elem in col.children:
            if not hasattr(elem, "name") or elem.name is None:
                continue
            # panel（版権表示等）が来たら終了
            if "panel" in elem.get("class", []):
                break
            if elem.name == "p":
                if not _hyuki_p_is_meta(elem):
                    lines.append(elem.get_text(strip=True))
                    lines.append("")
            elif elem.name in ("h2", "h3", "h4"):
                text = elem.get_text(strip=True)
                if text:
                    level = {"h2": "中見出し", "h3": "小見出し", "h4": "小見出し"}.get(elem.name, "中見出し")
                    lines.append(aozora_chapter_title(text, level))
                    lines.append("")
        body = "\n".join(lines).strip()
        return [{"title": work_title, "body": body}] if body else []

    # ── XHTML 設計 ────────────────────────────────
    episodes = []
    current_title = ""
    current_lines = []

    def flush():
        nonlocal current_title, current_lines
        body = "\n".join(current_lines).strip()
        if body:
            episodes.append({
                "title": current_title if current_title else work_title,
                "body": body,
            })
        current_title = ""
        current_lines = []

    body_tag = soup.find("body") or soup
    # div.titles を過ぎた後から処理開始
    titles_div = soup.find("div", class_="titles")
    in_content = titles_div is None
    in_toc_section = False

    for elem in body_tag.children:
        if not hasattr(elem, "name"):
            continue
        name = elem.name

        # ナビゲーションテーブルはスキップ
        if name == "table" and "navigation" in elem.get("class", []):
            continue

        # titles div を過ぎたら本文処理開始
        if not in_content:
            if elem == titles_div:
                in_content = True
            continue

        # フッター・著作権エリアで終了
        if name == "div" and any(
            c in elem.get("class", []) for c in ("footer", "display")
        ):
            break
        if name == "hr":
            # hr の後に著作権 p が続く場合があるので、残テキストを flush して終了
            flush()
            break

        if name == "h2":
            anchor = elem.find("a")
            anchor_id = (anchor.get("name") or anchor.get("id") or "").lower() if anchor else ""
            heading_text = elem.get_text(strip=True)
            if anchor_id == "toc" or heading_text in ("目次", "TOC"):
                in_toc_section = True
                continue
            in_toc_section = False
            flush()
            current_title = heading_text
            continue

        if in_toc_section:
            # TOC の ul（またはアンカーリンクのみの p）をスキップ
            if name in ("ul", "p"):
                in_toc_section = False if name == "ul" else in_toc_section
            continue

        if name == "blockquote":
            # 対訳テーブル: 最初の <td>（日本語側）のみ抽出
            table = elem.find("table")
            if table:
                first_td = table.find("td")
                if first_td:
                    pre = first_td.find("pre")
                    text = (pre.get_text() if pre else first_td.get_text()).strip()
                    if text:
                        current_lines.append(text)
                        current_lines.append("")
            else:
                # テーブルなし: 通常の引用ブロック
                for br in elem.find_all("br"):
                    br.replace_with("\n")
                text = elem.get_text().strip()
                if text:
                    current_lines.append(text)
                    current_lines.append("")

        elif name == "p":
            if not _hyuki_p_is_meta(elem):
                current_lines.append(elem.get_text(strip=True))
                current_lines.append("")

        elif name in ("ul", "ol"):
            for li in elem.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                if text:
                    current_lines.append(f"・{text}")
            current_lines.append("")

    flush()
    return episodes


def run_hyuki(args):
    """結城浩翻訳の部屋の作品をダウンロードする。"""
    if not _KAKUYOMU_AVAILABLE:
        print("エラー: 結城浩翻訳の部屋のダウンロードには requests と beautifulsoup4 が必要です。")
        print("  pip install requests beautifulsoup4")
        sys.exit(1)

    work_url = args.url
    if not re.search(r"hyuki\.com/trans/[^/?#]+", work_url):
        print(f"エラー: 結城浩翻訳の部屋の作品URLとして認識できません: {work_url}")
        print("  例: https://www.hyuki.com/trans/leaf")
        sys.exit(1)

    print(f"\n[1/3] 作品ページを取得中: {work_url}")
    try:
        soup = hyuki_fetch(work_url)
    except RuntimeError as e:
        print(f"エラー: {e}")
        sys.exit(1)

    info = hyuki_get_work_info(soup)
    if not info["title"]:
        print("エラー: タイトルを取得できませんでした。")
        sys.exit(1)

    print(f"      タイトル: {info['title']}")
    print(f"      著者    : {info['author']}")

    print("[2/3] 本文を解析中...")
    episodes = hyuki_extract_episodes(soup, info["title"])

    if not episodes:
        print("エラー: 本文を抽出できませんでした。")
        sys.exit(1)

    print(f"      章数    : {len(episodes)}")

    if getattr(args, "list_only", False):
        _show_episode_list(info["title"], info["author"], [ep["title"] for ep in episodes])
    _dry_run_exit(args)

    print("[3/3] テキスト・ePub を生成中...")
    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "結城浩翻訳の部屋")

    sections = []
    for ep in episodes:
        sec_title = aozora_chapter_title(ep["title"])
        sections.append(f"{sec_title}\n\n{ep['body']}\n")

    base      = _apply_output_dir(args, args.output or safe_filename(info["title"], "hyuki"))
    txt_path  = base + ".txt"
    epub_path = base + _epub_ext(args)

    write_file(txt_path, header, sections, colophon, args.encoding, getattr(args, "newline", "os"))

    full_len = (len(header)
                + sum(len(s) for s in sections)
                + len(PAGE_BREAK) * max(len(sections) - 1, 0)
                + len(colophon))
    print(f"\n✅ テキスト出力完了: {txt_path}")
    print(f"   章数        : {len(episodes)}")
    print(f"   総文字数    : {full_len:,} 文字")

    if not getattr(args, "no_epub", False):
        print("📖 ePub生成中...")
        build_epub(epub_path, info["title"], info["author"],
                   info["description"],
                   work_url, "結城浩翻訳の部屋", episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  青空文庫：定数・ヘッダー
# ══════════════════════════════════════════

_AOZORA_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
}


def aozora_fetch_html(url: str) -> str:
    """urllib で青空文庫カードページ HTML を取得する（stdlib のみ）。"""
    for attempt in range(1, RETRY_MAX + 2):
        try:
            req = Request(url, headers=_AOZORA_HEADERS)
            with urlopen(req, timeout=30) as r:
                charset = r.headers.get_content_charset() or "shift_jis"
                return r.read().decode(charset, errors="replace")
        except HTTPError as e:
            if e.code == 404:
                raise
            print(f"    HTTPError {e.code} (attempt {attempt})")
        except Exception as e:
            print(f"    Error: {e} (attempt {attempt})")
        if attempt <= RETRY_MAX:
            time.sleep(RETRY_WAIT)
    raise URLError(f"Failed after {RETRY_MAX} retries: {url}")


def aozora_get_work_info(html: str) -> dict:
    """
    カードページ HTML からタイトル・著者を抽出する。
    旧サイト: <h1>図書カード：タイトル</h1>
    新サイト: h1 は「図書カード：No.XXXXX」のため「作品名：タイトル」テキストを使用。
    著者は /index_pages/person リンクテキストで共通。
    """
    title = ""
    m = re.search(r"<h1[^>]*>図書カード[：:]\s*([^<]+)</h1>", html)
    if m:
        candidate = m.group(1).strip()
        if not re.match(r"No\.\d+", candidate):
            title = candidate
    if not title:
        m = re.search(r"作品名[：:]\s*([^\n<]+)", html)
        if m:
            title = m.group(1).strip()

    author = ""
    m = re.search(
        r'<a[^>]+href="[^"]*index_pages/person[^"]*"[^>]*>([^<]+)</a>', html
    )
    if m:
        author = m.group(1).strip()

    return {"title": title, "author": author}


def aozora_find_zip_url(html: str, card_url: str) -> str | None:
    """カードページ HTML からルビ付き ZIP URL を抽出する（なければ任意の ZIP）。"""
    parsed = urlparse(card_url)
    base_dir = card_url.rsplit("/", 1)[0]

    def resolve(href: str) -> str:
        if href.startswith("http"):
            return href
        if href.startswith("//"):
            return parsed.scheme + ":" + href
        if href.startswith("/"):
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        if href.startswith("./"):
            return base_dir + "/" + href[2:]
        return base_dir + "/" + href

    for pattern in (r'href="([^"]*_ruby_[^"]*\.zip)"', r'href="([^"]*\.zip)"'):
        m = re.search(pattern, html)
        if m:
            return resolve(m.group(1))
    return None


def aozora_download_extract(zip_url: str) -> tuple:
    """ZIP をダウンロードして (txt_filename, txt_bytes, images) を返す。
    images: {"filename.png": bytes, ...}（ZIP 内の画像ファイル）
    """
    req = Request(zip_url, headers=_AOZORA_HEADERS)
    with urlopen(req, timeout=60) as r:
        zip_bytes = r.read()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        txt_names = [n for n in names if n.lower().endswith(".txt")]
        if not txt_names:
            raise RuntimeError(f"ZIP 内にテキストファイルが見つかりません: {zip_url}")
        txt_name = txt_names[0]
        images = {
            Path(n).name: zf.read(n)
            for n in names
            if Path(n).suffix.lower() in _IMG_EXTS
        }
        return Path(txt_name).name, zf.read(txt_name), images


def aozora_decode(txt_bytes: bytes) -> tuple:
    """テキストバイト列をデコードして (text_str, encoding_name) を返す。"""
    for enc in ("shift_jis", "cp932", "utf-8", "euc_jp"):
        try:
            return txt_bytes.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return txt_bytes.decode("shift_jis", errors="replace"), "shift_jis"


def _strip_heading_block(lines: list) -> int:
    """先頭から見出しブロックを読み飛ばし、本文開始行インデックスを返す。"""
    i = 0
    # 先頭空行をスキップ
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return i
    ln = lines[i]
    start_m = _MIDASHI_START_RE.search(ln)
    if not start_m:
        return i
    visible = _AOZORA_ANY_TAG_RE.sub("", ln).strip()
    if visible:
        # インライン形式（タグ除去後も可視テキストがある）→ 1行だけスキップ
        return i + 1
    # ブロック形式: 開始タグ行 → テキスト行 → 終了タグ行
    i += 1  # 開始タグ行
    if i < len(lines):
        i += 1  # テキスト行
    if i < len(lines) and _MIDASHI_END_RE.search(lines[i]):
        i += 1  # 終了タグ行
    return i


def _split_aozora_by_headings(body_text: str) -> list:
    """
    青空文庫本文を大/中/小見出しタグの位置でチャプター分割する。
    見出しが存在しない場合は [] を返す。
    各セクションの body は見出し行を除いた本文のみ。
    Returns: [{"title": str, "body": str}, ...]
    """
    lines = body_text.split("\n")

    # 見出し行インデックスとタイトルを収集（終わりマーカーは除外）
    heading_positions: list = []
    for i, ln in enumerate(lines):
        m = re.search(r"「([^」]+)」は(大|中|小)見出し］", ln)
        if m and "終わり" not in ln:
            heading_positions.append((i, m.group(1)))

    if not heading_positions:
        return []

    sections: list = []

    # 最初の見出し前のテキスト（前文等）
    pre_text = "\n".join(lines[: heading_positions[0][0]]).strip()
    if pre_text:
        sections.append({"title": "", "body": pre_text})

    for j, (line_idx, title) in enumerate(heading_positions):
        next_idx = heading_positions[j + 1][0] if j + 1 < len(heading_positions) else len(lines)
        section_lines = lines[line_idx:next_idx]
        body_start = _strip_heading_block(section_lines)
        section_body = "\n".join(section_lines[body_start:]).strip()
        sections.append({"title": title, "body": section_body})

    return sections


def aozora_text_to_episodes(text: str) -> tuple:
    """
    青空文庫テキストをパースして (title, author, episodes) を返す。
    episodes: [{"title": str, "body": str}, ...]

    テキスト形式:
      1行目: タイトル
      次の非空行: 著者名
      ---（区切り線）…記号説明…---（区切り線）   ← 省略可
      本文（［＃改ページ］で章分割、または大/中/小見出しでチャプター分割）
      底本：…（末尾、除去する）
    """
    lines = text.split("\n")

    # タイトル・著者: 先頭2つの非空行
    title, author = "", ""
    non_blank = [i for i, l in enumerate(lines) if l.strip()]
    if non_blank:
        title = lines[non_blank[0]].strip()
    if len(non_blank) > 1:
        author = lines[non_blank[1]].strip()
    body_start = (non_blank[1] + 1) if len(non_blank) > 1 else 0

    # -------区切り線2本の間（記号説明ブロック）をスキップ
    sep_re = re.compile(r"^-{10,}$")
    body_lines = lines[body_start:]
    sep_idx = [i for i, l in enumerate(body_lines) if sep_re.match(l.strip())]
    if len(sep_idx) >= 2:
        body_lines = body_lines[sep_idx[1] + 1:]
    elif len(sep_idx) == 1:
        body_lines = body_lines[sep_idx[0] + 1:]

    body_text = "\n".join(body_lines).strip()

    # 末尾の底本情報をカット
    m_col = re.search(r"\n底本[：:].+", body_text, re.DOTALL)
    if m_col:
        body_text = body_text[:m_col.start()].rstrip()

    # ｜（全角ルビ開始記号）は除去せず保持する。
    # _apply_ruby_auto が [|｜] をルビ範囲の明示マーカーとして正しく処理する。

    # ［＃改ページ］で章分割し、各セクションをさらに大/中/小見出しで分割
    episode_texts = body_text.split("［＃改ページ］")

    episodes = []
    for et in episode_texts:
        et = et.strip()
        if not et:
            continue
        subsections = _split_aozora_by_headings(et)
        if subsections:
            for sub in subsections:
                episodes.append({"title": sub["title"], "body": sub["body"]})
        else:
            # 見出しなし → 大見出しタグからタイトルを取得（従来の挙動）
            m_t = re.search(r"「(.+?)」は大見出し", et)
            episodes.append({"title": m_t.group(1) if m_t else "", "body": et})

    # タイトルが取れなかった場合の補完
    if not episodes:
        episodes = [{"title": title, "body": body_text}]
    elif all(not ep["title"] for ep in episodes):
        if len(episodes) == 1:
            episodes[0]["title"] = title
        else:
            for i, ep in enumerate(episodes, 1):
                ep["title"] = f"第{i}部"
    else:
        # 一部のエピソードにタイトルがない場合（前段テキスト等）は番号を補完
        for i, ep in enumerate(episodes, 1):
            if not ep["title"]:
                ep["title"] = f"第{i}部"

    return title, author, episodes


def run_aozora(args):
    """青空文庫（aozora.gr.jp / aozora-renewal.cloud）のダウンロード処理。"""
    work_url = args.url

    print(f"\n[1/3] 作品情報を取得中: {work_url}")
    try:
        card_html = aozora_fetch_html(work_url)
    except Exception as e:
        print(f"エラー: カードページの取得に失敗しました — {e}")
        sys.exit(1)

    info = aozora_get_work_info(card_html)
    if info["title"]:
        print(f"      タイトル: {info['title']}")
    if info["author"]:
        print(f"      著者    : {info['author']}")

    zip_url = aozora_find_zip_url(card_html, work_url)
    if not zip_url:
        print("エラー: ZIP ファイルのリンクが見つかりません。")
        sys.exit(1)

    print(f"[2/3] ZIP をダウンロード中: {zip_url}")
    try:
        txt_filename, txt_bytes, images = aozora_download_extract(zip_url)
    except Exception as e:
        print(f"エラー: ZIP 取得・展開に失敗しました — {e}")
        sys.exit(1)

    text, enc = aozora_decode(txt_bytes)
    img_msg = f"  画像 {len(images)} 件" if images else ""
    print(f"      ファイル名: {txt_filename}  エンコーディング: {enc}{img_msg}")

    if getattr(args, "list_only", False):
        ep_title, ep_author, episodes = aozora_text_to_episodes(text)
        title  = ep_title  or info.get("title",  "（タイトル不明）")
        author = ep_author or info.get("author", "（著者不明）")
        _show_episode_list(title, author, [ep["title"] for ep in episodes])
    _dry_run_exit(args)

    # テキストファイルを UTF-8 に変換して保存
    # テキストは ZIP 内ファイル名ベース（または -o 指定）を使用
    _txt_base = _apply_output_dir(args, args.output or Path(txt_filename).stem)
    txt_path = _txt_base + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\n✅ テキスト出力完了: {txt_path}  （{enc} → UTF-8 変換済み）")

    if not getattr(args, "no_epub", False):
        print("[3/3] ePub を生成中...")
        ep_title, ep_author, episodes = aozora_text_to_episodes(text)
        title  = ep_title  or info.get("title",  "（タイトル不明）")
        author = ep_author or info.get("author", "（著者不明）")

        # ePub は作品タイトルをファイル名に使用（-o 指定時はその名前を優先）
        _epub_base = _apply_output_dir(args, args.output or safe_filename(title, fallback=Path(txt_filename).stem))
        epub_path = _epub_base + _epub_ext(args)
        build_epub(epub_path, title, author, "",
                   work_url, "青空文庫", episodes,
                   cover_bg=args.cover_bg,
                   cover_image_path=getattr(args, "cover_image", None) or "",
                   font_path=getattr(args, "font", "") or "",
                   toc_at_end=getattr(args, "toc_at_end", False),
                   images=images or None,
                   horizontal=getattr(args, "horizontal", False))
        print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ファイルモード：テキスト解析・ePub生成
# ══════════════════════════════════════════

def parse_aozora_text(content: str) -> tuple:
    """
    青空文庫書式テキスト（このツールが出力する形式）を解析して
    (title, author, synopsis, episodes) を返す。

    対応形式:
      - このツールが出力する青空文庫書式（見出しマーカー・PAGE_BREAK付き）
      - 先頭2行にタイトル・著者があるシンプルなテキスト

    episodes: [{"title": str, "body": str}, ...]
    """
    lines = content.split("\n")

    # 1行目: タイトル、2行目: 著者
    title  = lines[0].strip() if len(lines) > 0 else "（タイトル不明）"
    author = lines[1].strip() if len(lines) > 1 else "（作者不明）"

    # ヘッダー区切り線（---...）を2つ探してヘッダー範囲を確定する
    synopsis      = ""
    body_start_ln = 3          # ヘッダーが検出できなかった場合のデフォルト
    sep_count     = 0
    in_synopsis   = False
    for i in range(2, min(len(lines), 60)):
        ln = lines[i]
        if ln.startswith("----------"):   # 10文字以上のダッシュ列
            sep_count += 1
            in_synopsis = False
            if sep_count == 2:
                body_start_ln = i + 1
                break
        elif "【あらすじ】" in ln:
            in_synopsis = True
        elif in_synopsis:
            synopsis += ln + "\n"

    synopsis     = synopsis.strip()
    body_content = "\n".join(lines[body_start_ln:])

    # 奥付（"底本："で始まるブロック）を末尾から除去
    col_pos = body_content.rfind("\n\n底本：")
    if col_pos >= 0:
        body_content = body_content[:col_pos]

    # PAGE_BREAK で章・話に分割し、各セクションをさらに大/中/小見出しで分割
    raw_sections = body_content.split("［＃改ページ］")

    episodes = []
    for sec in raw_sections:
        sec = sec.strip()
        if not sec:
            continue

        subsections = _split_aozora_by_headings(sec)
        if subsections:
            for sub in subsections:
                ep_num = len(episodes) + 1
                episodes.append({
                    "title": sub["title"] or f"第{ep_num}話",
                    "body":  sub["body"],
                })
        else:
            ep_lines   = sec.split("\n")
            ep_title   = ""
            body_start = 0

            for li, ln in enumerate(ep_lines):
                # 見出し終わりマーカーが見つかったらその次行から本文
                if re.search(r"は(?:大|中|小)見出し終わり］", ln):
                    body_start = li + 1
                    break
                # 見出し開始マーカーからタイトルを取得
                m = re.search(r"「(.+?)」は(?:大|中|小)見出し］", ln)
                if m:
                    ep_title = m.group(1)

            body_text = "\n".join(ep_lines[body_start:]).strip()
            episodes.append({
                "title": ep_title or f"第{len(episodes) + 1}話",
                "body":  body_text,
            })

    # 見出しマーカーがなく1セクションしかない場合はタイトルをそのまま使用
    if len(episodes) == 1 and episodes[0]["title"].startswith("第1話"):
        episodes[0]["title"] = title

    # エピソードが空 → ファイル全体を1エピソードとして扱う
    if not episodes and body_content.strip():
        episodes.append({"title": title, "body": body_content.strip()})

    return title, author, synopsis, episodes


def run_from_file(args):
    """
    ローカルテキストファイルを読み込んでePub3を生成する。
    テキストは青空文庫書式（このツールの出力形式）を想定するが、
    先頭2行にタイトル・著者を持つシンプルな形式にも対応する。
    """
    txt_path = args.from_file
    if not os.path.exists(txt_path):
        print(f"エラー: ファイルが見つかりません: {txt_path}")
        sys.exit(1)

    # エンコーディング自動検出（--encoding 指定を優先）
    enc_candidates = [args.encoding] + [
        e for e in ["utf-8-sig", "utf-8", "cp932", "shift_jis"]
        if e != args.encoding
    ]
    content = None
    used_enc = None
    for enc in enc_candidates:
        try:
            with open(txt_path, "r", encoding=enc) as f:
                content = f.read()
            used_enc = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        print(f"エラー: ファイルを読み込めません（エンコーディング不明）: {txt_path}")
        sys.exit(1)

    print(f"\n[Step 1] テキストファイルを解析中: {txt_path}  (encoding={used_enc})")
    title, author, synopsis, episodes = parse_aozora_text(content)

    # --title / --author オプションで上書き可能
    if getattr(args, "title_override", None):
        title = args.title_override
    if getattr(args, "author_override", None):
        author = args.author_override

    # タイトルが空の場合はファイルのベース名で代替
    if not title:
        title = Path(txt_path).stem

    if not episodes:
        print("エラー: テキストファイルから本文を抽出できませんでした。")
        sys.exit(1)

    print(f"  タイトル : {title}")
    print(f"  作者     : {author}")
    print(f"  話数     : {len(episodes)} 話")

    base      = _apply_output_dir(args, args.output or safe_filename(title, "novel"))
    epub_path = base + _epub_ext(args)
    cover_bg  = args.cover_bg or "#16234b"

    print(f"📖 ePub生成中...")
    build_epub(epub_path, title, author, synopsis,
               "", "ローカルファイル", episodes, cover_bg=cover_bg,
               cover_image_path=getattr(args, "cover_image", None) or "",
               font_path=getattr(args, "font", "") or "",
               toc_at_end=getattr(args, "toc_at_end", False),
               horizontal=getattr(args, "horizontal", False))
    print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  ローカルePub3 → 青空文庫テキスト変換
# ══════════════════════════════════════════

def _ruby_to_aozora(text: str) -> str:
    """
    <ruby>…</ruby> を 親文字《ルビ》 形式に変換する共通ヘルパー。
    標準形式 <ruby>漢字<rt>かんじ</rt></ruby> と
    Kobo 形式 <ruby><span>編</span><rt>へん</rt><span>年</span><rt>ねん</rt>…</ruby>
    の両方に対応する。
    """
    text = re.sub(r'<rp>[^<]*</rp>', '', text)

    def _conv(m):
        inner = m.group(1)
        readings = re.findall(r'<rt>(.*?)</rt>', inner, re.DOTALL)
        base = re.sub(r'<rt>.*?</rt>', '', inner, flags=re.DOTALL)
        base = re.sub(r'<[^>]+>', '', base).strip()
        return f"{base}《{''.join(readings)}》"

    return re.sub(r'<ruby>(.*?)</ruby>', _conv, text, flags=re.DOTALL)


def _epub_xhtml_to_episode(xhtml: str) -> tuple:
    """
    エピソードXHTMLを解析してエピソードタイトルと本文テキスト（青空文庫書式）を返す。
    <ruby>漢字<rt>かんじ</rt></ruby> → 漢字《かんじ》 に逆変換。
    Returns: (ep_title, body_text)
    """
    import html as _html

    def strip_tags(text: str) -> str:
        return re.sub(r'<[^>]+>', '', text)

    ep_title = ""
    m = re.search(r'<h2[^>]*class="ep-title"[^>]*>(.*?)</h2>', xhtml, re.DOTALL)
    if m:
        ep_title = _html.unescape(strip_tags(m.group(1))).strip()

    body_lines = []
    for pm in re.finditer(r'<p class="(body-line|body-blank)">(.*?)</p>', xhtml, re.DOTALL):
        if pm.group(1) == "body-blank":
            body_lines.append("")
        else:
            line = _ruby_to_aozora(pm.group(2))
            line = strip_tags(line)
            line = _html.unescape(line)
            body_lines.append(line)

    while body_lines and not body_lines[-1]:
        body_lines.pop()

    return ep_title, "\n".join(body_lines)


def _epub_cover_to_synopsis(xhtml: str) -> str:
    """cover.xhtml を解析してあらすじテキストを返す。"""
    import html as _html

    def strip_tags(text: str) -> str:
        return re.sub(r'<[^>]+>', '', text)

    syn_m = re.search(r'<div class="cover-synopsis">(.*?)</div>', xhtml, re.DOTALL)
    if not syn_m:
        return ""

    lines = []
    for pm in re.finditer(r'<p class="(body-line|body-blank)">(.*?)</p>', syn_m.group(1), re.DOTALL):
        if pm.group(1) == "body-blank":
            lines.append("")
        else:
            lines.append(_html.unescape(strip_tags(pm.group(2))).strip())
    return "\n".join(lines).strip()


def _epub_colophon_to_source(xhtml: str) -> tuple:
    """
    colophon.xhtml を解析して (source_url, site_name) を返す。
    Returns: (source_url, site_name)
    """
    import html as _html

    source_url = ""
    site_name = ""

    m = re.search(r'底本：「[^」]*」([^<\n]*)', xhtml)
    if m:
        site_name = _html.unescape(m.group(1)).strip()

    m = re.search(r'<a href="([^"]+)"', xhtml)
    if m:
        source_url = _html.unescape(m.group(1))

    return source_url, site_name


def _epub_generic_to_text(xhtml: str) -> tuple:
    """
    汎用 XHTML を解析してエピソードタイトルと本文テキストを返す。
    <ruby>漢字<rt>かんじ</rt></ruby> → 漢字《かんじ》 に変換。
    Returns: (ep_title, body_text)
    """
    import html as _html

    _BR = '\x00'  # <br> の一時プレースホルダ

    def _process_inline(text: str) -> str:
        """インライン HTML を青空文庫テキストに変換する共通処理。
        <br> → 改行、それ以外のタグ内改行 → 空白（HTML 的空白正規化）。
        """
        # <br> → プレースホルダ（他の改行と区別）
        text = re.sub(r'<br\s*/?>', _BR, text, flags=re.IGNORECASE)
        # HTML 的空白正規化: タグ内の \r\n は表示上の空白に過ぎないため除去
        text = re.sub(r'[\r\n]+', ' ', text)
        # ruby → 《》 変換・タグ除去・実体参照復元
        text = _ruby_to_aozora(text)
        text = re.sub(r'<[^>]+>', '', text)
        text = _html.unescape(text)
        text = text.replace('\xa0', '')
        # 複数空白（タブ含む）を1つにまとめる
        text = re.sub(r'[ \t]+', ' ', text)
        # 日本語文字に隣接するスペースを除去（HTML空白正規化の副産物）
        text = re.sub(r' (?=[\u3000-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF])'
                      r'|(?<=[\u3000-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]) ', '', text)
        return text

    # タイトル: h1/h2 優先、なければ <title> から
    ep_title = ""
    for tag in ('h1', 'h2'):
        m = re.search(fr'<{tag}[^>]*>(.*?)</{tag}>', xhtml, re.DOTALL | re.IGNORECASE)
        if m:
            ep_title = _process_inline(m.group(1)).strip()
            break
    if not ep_title:
        m = re.search(r'<title[^>]*>(.*?)</title>', xhtml, re.DOTALL | re.IGNORECASE)
        if m:
            ep_title = _process_inline(m.group(1)).strip()

    # 本文: body 内の p タグを全収集
    body_m = re.search(r'<body[^>]*>(.*?)</body>', xhtml, re.DOTALL | re.IGNORECASE)
    body_src = body_m.group(1) if body_m else xhtml
    body_lines = []
    for pm in re.finditer(r'<p[^>]*>(.*?)</p>', body_src, re.DOTALL | re.IGNORECASE):
        content = _process_inline(pm.group(1))
        for line in content.split(_BR):
            body_lines.append(line.rstrip())

    while body_lines and not body_lines[-1]:
        body_lines.pop()

    return ep_title, "\n".join(body_lines)


def _extract_synopsis_from_text(text: str) -> str:
    """本文テキストから【あらすじ】ブロックを抽出する。"""
    lines = text.split('\n')
    synopsis_lines = []
    in_synopsis = False
    for line in lines:
        stripped = line.strip()
        if '【あらすじ】' in stripped:
            in_synopsis = True
            continue
        if in_synopsis:
            if re.match(r'【[^】]+】', stripped):
                break
            synopsis_lines.append(line)
    return '\n'.join(synopsis_lines).strip()


def _read_streaming_zip(path: str) -> dict:
    """
    中央ディレクトリ（Central Directory）を持たないストリーミングZIPを読み込む。
    ローカルファイルヘッダを順に走査し、STORED/DEFLATE ファイルを解凍して
    {filename: bytes} 辞書を返す。
    """
    import zlib as _zlib
    import struct as _struct

    with open(path, "rb") as _f:
        data = _f.read()

    files: dict = {}
    pos = 0
    n = len(data)

    while pos <= n - 30:
        if data[pos:pos + 4] != b'PK\x03\x04':
            pos += 1
            continue

        # ローカルファイルヘッダ解析 (30バイト固定部)
        flags      = _struct.unpack_from('<H', data, pos + 6)[0]
        method     = _struct.unpack_from('<H', data, pos + 8)[0]
        comp_size  = _struct.unpack_from('<I', data, pos + 18)[0]
        fname_len  = _struct.unpack_from('<H', data, pos + 26)[0]
        extra_len  = _struct.unpack_from('<H', data, pos + 28)[0]

        header_end = pos + 30 + fname_len + extra_len
        if header_end > n:
            break

        fname_raw = data[pos + 30: pos + 30 + fname_len]
        try:
            fname = fname_raw.decode('utf-8')
        except UnicodeDecodeError:
            fname = fname_raw.decode('cp437', errors='replace')

        has_dd = bool(flags & 0x08)   # bit3: data descriptor 付き
        pos = header_end               # データ開始位置

        if method == 0:  # STORED
            if has_dd and comp_size == 0:
                # PK\x07\x08 または次の PK\x03\x04 まで
                end = pos
                while end <= n - 4:
                    sig = data[end:end + 4]
                    if sig == b'PK\x07\x08':
                        files[fname] = data[pos:end]
                        end += 16
                        break
                    if sig in (b'PK\x03\x04', b'PK\x01\x02', b'PK\x05\x06'):
                        files[fname] = data[pos:end]
                        break
                    end += 1
                else:
                    files[fname] = data[pos:n]
                    end = n
                pos = end
            else:
                files[fname] = data[pos:pos + comp_size]
                pos += comp_size
                if has_dd:
                    pos += 16 if data[pos:pos + 4] == b'PK\x07\x08' else 12

        elif method == 8:  # DEFLATE
            if has_dd and comp_size == 0:
                # 圧縮サイズ不明: EOF まで解凍し unused_data で消費量を計算
                remaining = data[pos:]
                decomp = _zlib.decompressobj(wbits=-15)
                try:
                    out = decomp.decompress(remaining)
                    consumed = len(remaining) - len(decomp.unused_data)
                    pos += consumed
                    files[fname] = out
                except _zlib.error:
                    files[fname] = b''
                    nxt = data.find(b'PK\x03\x04', pos)
                    pos = nxt if nxt != -1 else n
                # data descriptor をスキップ
                if pos <= n - 4 and data[pos:pos + 4] == b'PK\x07\x08':
                    pos += 16
                elif pos <= n - 12:
                    pos += 12
            else:
                compressed = data[pos:pos + comp_size]
                try:
                    files[fname] = _zlib.decompress(compressed, wbits=-15)
                except _zlib.error:
                    files[fname] = b''
                pos += comp_size
                if has_dd:
                    pos += 16 if data[pos:pos + 4] == b'PK\x07\x08' else 12

        else:
            # サポート外圧縮: 次の PK ヘッダまでスキップ
            if has_dd and comp_size == 0:
                nxt = pos
                while nxt <= n - 4:
                    if data[nxt:nxt + 4] in (b'PK\x03\x04', b'PK\x01\x02', b'PK\x05\x06'):
                        break
                    nxt += 1
                pos = nxt
            else:
                pos += comp_size
                if has_dd:
                    pos += 16 if data[pos:pos + 4] == b'PK\x07\x08' else 12

    return files


class _ZipLike:
    """_read_streaming_zip() の戻り値を zipfile.ZipFile 互換インタフェースでラップする。"""

    def __init__(self, files: dict):
        self._files = files

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def namelist(self) -> list:
        return list(self._files.keys())

    def read(self, name: str) -> bytes:
        return self._files[name]


def parse_epub(epub_path: str) -> tuple:
    """
    ePub3ファイルを解析して (title, author, synopsis, source_url, site_name, episodes) を返す。
    このツールが出力した ePub3（ep*.xhtml 形式）を優先処理し、
    それ以外の汎用 ePub3 は OPF spine 順に p タグを抽出するフォールバック処理を行う。
    ストリーミングZIP（中央ディレクトリなし）には _read_streaming_zip でフォールバック。
    episodes: [{"title": str, "body": str}, ...]
    """
    import html as _html

    try:
        _zip_ctx = zipfile.ZipFile(epub_path, "r")
    except zipfile.BadZipFile:
        _zip_ctx = _ZipLike(_read_streaming_zip(epub_path))

    with _zip_ctx as zf:
        namelist = zf.namelist()

        # container.xml から OPF パスを取得
        opf_path = "OEBPS/package.opf"
        if "META-INF/container.xml" in namelist:
            try:
                container = zf.read("META-INF/container.xml").decode("utf-8")
                m = re.search(r'full-path="([^"]+)"', container)
                if m:
                    opf_path = m.group(1)
            except Exception:
                pass

        # OPF のディレクトリ（spine href を絶対パスに変換するため）
        opf_dir = str(Path(opf_path).parent)
        if opf_dir == ".":
            opf_dir = ""

        # OPF からタイトル・著者・manifest・spine を取得
        title, author = "", ""
        nav_href_rel = ""
        spine_hrefs = []   # OPF 相対パス
        manifest = {}      # id -> {"href": str, "props": str}

        if opf_path in namelist:
            opf = zf.read(opf_path).decode("utf-8")

            m = re.search(r'<dc:title[^>]*>(.*?)</dc:title>', opf, re.DOTALL)
            if m:
                title = _html.unescape(m.group(1)).strip()
            m = re.search(r'<dc:creator[^>]*>(.*?)</dc:creator>', opf, re.DOTALL)
            if m:
                author = _html.unescape(m.group(1)).strip()

            for im in re.finditer(r'<item\b([^>]+?)/?>', opf, re.DOTALL):
                attrs = im.group(1)
                id_m    = re.search(r'\bid="([^"]+)"', attrs)
                href_m  = re.search(r'\bhref="([^"]+)"', attrs)
                props_m = re.search(r'\bproperties="([^"]+)"', attrs)
                if id_m and href_m:
                    props = props_m.group(1) if props_m else ""
                    manifest[id_m.group(1)] = {"href": href_m.group(1), "props": props}
                    if "nav" in props:
                        nav_href_rel = href_m.group(1)

            for sr in re.finditer(r'<itemref\b[^>]*\bidref="([^"]+)"', opf):
                idref = sr.group(1)
                if idref in manifest:
                    spine_hrefs.append(manifest[idref]["href"])

        def full_zip_path(rel_href: str) -> str:
            """OPF 相対パス → ZIP 内フルパスに変換"""
            return (opf_dir + "/" + rel_href) if opf_dir else rel_href

        # nav ファイルを解析して {zip_path → chapter_title} マップを構築
        # nav href は nav ファイル自身からの相対パスなので nav のディレクトリを基点にする
        _NAV_SKIP_TITLES = frozenset({
            "表紙", "カバー", "奥付", "目次", "CONTENTS", "TOC",
            "ナビゲーション", "Navigation", "タイトルページ",
        })
        nav_title_map: dict = {}  # zip_path → chapter_title
        if nav_href_rel:
            nav_zip = full_zip_path(nav_href_rel)
            nav_base = str(Path(nav_zip).parent)  # nav ファイルのあるディレクトリ
            if nav_zip in namelist:
                nav_xhtml = zf.read(nav_zip).decode("utf-8", errors="replace")
                for nm in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
                                      nav_xhtml):
                    href_raw   = nm.group(1)
                    nav_label  = _html.unescape(nm.group(2)).strip()
                    href_file  = href_raw.split('#')[0]  # アンカーを除去
                    fp2 = (nav_base + "/" + href_file) if nav_base else href_file
                    if fp2 not in nav_title_map:
                        nav_title_map[fp2] = nav_label

        # ── このツール独自形式かチェック（OEBPS/ep*.xhtml パターン） ──────
        own_ep_paths = sorted(
            n for n in namelist if re.match(r'OEBPS/ep\d+\.xhtml$', n)
        )

        if own_ep_paths:
            synopsis = ""
            if "OEBPS/cover.xhtml" in namelist:
                synopsis = _epub_cover_to_synopsis(
                    zf.read("OEBPS/cover.xhtml").decode("utf-8")
                )
            source_url, site_name = "", ""
            if "OEBPS/colophon.xhtml" in namelist:
                source_url, site_name = _epub_colophon_to_source(
                    zf.read("OEBPS/colophon.xhtml").decode("utf-8")
                )
            episodes = []
            for ep_path in own_ep_paths:
                ep_title, body_text = _epub_xhtml_to_episode(
                    zf.read(ep_path).decode("utf-8")
                )
                if ep_title or body_text:
                    episodes.append({"title": ep_title, "body": body_text})

        else:
            # ── 汎用形式: OPF spine 順に p タグを抽出 ──────────────────
            synopsis = ""
            source_url, site_name = "", ""
            episodes = []

            # nav に「真のチャプターエントリ（skip対象でなく書名とも異なる）」が
            # 2件以上あれば nav 完備と判断し、nav 未登録ファイルをスキップする
            genuine_nav_count = sum(
                1 for t in nav_title_map.values()
                if t not in _NAV_SKIP_TITLES and t != title
            )
            nav_only_mode = genuine_nav_count >= 2

            for href_rel in spine_hrefs:
                if href_rel == nav_href_rel:
                    continue
                fp = full_zip_path(href_rel)
                if fp not in namelist:
                    continue

                nav_title = nav_title_map.get(fp, "")

                # nav にスキップ対象タイトル（表紙・奥付・目次等）として登録されていればスキップ
                if nav_title in _NAV_SKIP_TITLES:
                    continue

                # nav 完備モードでは nav 未登録ファイルをスキップ
                if nav_only_mode and not nav_title:
                    continue

                xhtml = zf.read(fp).decode("utf-8", errors="replace")
                ep_title_detected, body_text = _epub_generic_to_text(xhtml)

                if not body_text.strip():
                    continue

                # 【あらすじ】を含むページからあらすじを抽出してスキップ
                if "【あらすじ】" in body_text:
                    synopsis = _extract_synopsis_from_text(body_text)
                    continue

                # nav タイトルが書名と異なる場合に優先、それ以外は検出タイトルを使用
                ep_title = (nav_title if nav_title and nav_title != title
                            else ep_title_detected)

                # fallback モードで本文が極端に少ない先頭ページをスキップ
                if not nav_only_mode and not nav_title \
                        and len(body_text.strip()) < 100 and not episodes:
                    continue

                episodes.append({"title": ep_title, "body": body_text})

    return title, author, synopsis, source_url, site_name, episodes


def run_from_epub(args):
    """
    ローカルePub3ファイルを読み込んで青空文庫書式テキストを生成する。
    このツールが出力した ePub3 を想定する。
    """
    epub_path = args.from_epub
    if not os.path.exists(epub_path):
        print(f"エラー: ファイルが見つかりません: {epub_path}")
        sys.exit(1)

    print(f"\n[Step 1] ePub3ファイルを解析中: {epub_path}")
    try:
        title, author, synopsis, source_url, site_name, episodes = parse_epub(epub_path)
    except Exception as e:
        print(f"エラー: ePub3 ファイルを読み込めませんでした: {e}")
        sys.exit(1)

    if getattr(args, "title_override", None):
        title = args.title_override
    if getattr(args, "author_override", None):
        author = args.author_override

    if not title:
        title = Path(epub_path).stem

    if not episodes:
        print("エラー: ePub3 ファイルから本文を抽出できませんでした。")
        sys.exit(1)

    print(f"  タイトル : {title}")
    print(f"  作者     : {author}")
    print(f"  話数     : {len(episodes)} 話")

    base     = _apply_output_dir(args, args.output or safe_filename(title, "novel"))
    txt_path = base + ".txt"

    header   = aozora_header(title, author, synopsis, source_url)
    sections = [
        aozora_chapter_title(ep["title"]) + "\n\n" + ep["body"]
        for ep in episodes
    ]
    colophon = aozora_colophon(
        title,
        source_url or epub_path,
        site_name or "ローカルePub3"
    )

    write_file(txt_path, header, sections, colophon,
               encoding=args.encoding, newline=args.newline)
    print(f"✅ テキスト出力完了: {txt_path}")


# ══════════════════════════════════════════
#  エントリポイント
# ══════════════════════════════════════════

def _host_matches(host: str, domain: str) -> bool:
    """host が domain またはその正規サブドメインかを判定する。
    'in' 演算子による部分一致（例: evil.syosetu.com.attacker.com）を防ぐ。
    """
    return host == domain or host.endswith("." + domain)


# 短縮URL サービスのドメイン一覧
_SHORT_URL_HOSTS = {
    # 当初対応分
    "share.google",
    "search.app",
    "bit.ly",
    "tinyurl.com",
    "00m.in",
    "ow.ly",
    # SNS系
    "t.co",           # Twitter/X
    "lin.ee",         # LINE
    "fb.me",          # Facebook
    "lnkd.in",        # LinkedIn
    "wp.me",          # WordPress
    # 汎用短縮サービス
    "goo.gl",         # Google（旧・廃止済みだが既存リンクは動作）
    "is.gd",
    "v.gd",
    "s.id",
    "cutt.ly",
    "rebrand.ly",
    "short.io",
    "clck.ru",
    "x.gd",
    "qr.ae",
    # Eコマース系
    "amzn.to",
    "amzn.asia",
    # マーケティング系
    "buff.ly",        # Buffer
    "ift.tt",         # IFTTT
    "dlvr.it",
    "po.st",
}


def _unwrap_query_url(url: str) -> str:
    """中間リダイレクト先URLのクエリパラメータに本来のURLが埋め込まれている場合に取り出す。

    例: https://www.google.com/share.google?q=https://kakuyomu.jp/works/...
         → https://kakuyomu.jp/works/...
    対象キー: q / url / u / link / target / redirect / next
    """
    params = parse_qs(urlparse(url).query, keep_blank_values=False)
    for key in ("q", "url", "u", "link", "target", "redirect", "next"):
        candidates = params.get(key, [])
        if candidates:
            candidate = candidates[0]
            if candidate.startswith("http://") or candidate.startswith("https://"):
                return candidate
    return url


_SHORT_URL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def _extract_url_from_html(html: str) -> str | None:
    """HTMLページ内のリダイレクト先URLを抽出する。
    meta http-equiv="refresh" と window.location(.href) の両方を試みる。
    """
    # <meta http-equiv="refresh" content="0; url=...">
    m = re.search(
        r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+'
        r'content=["\']?\d*\s*;\s*url=([^"\'>\s]+)',
        html, re.I
    )
    if m:
        return m.group(1).strip("'\"")
    # window.location = "..." または window.location.href = "..."
    m = re.search(
        r'window\.location(?:\.href)?\s*=\s*["\']([^"\']{10,})["\']',
        html
    )
    if m:
        return m.group(1)
    return None


def _follow_one_redirect(url: str) -> tuple[str, str | None]:
    """1回のHTTPリクエストでリダイレクト後のURLとHTML本文を返す。

    HEAD でリダイレクトが確認できた場合はそのURLと None を返す。
    HEAD でリダイレクトがなかった（同一URL）場合は GET でページ本文も取得する。
    失敗した場合は (url, None) を返す。
    """
    try:
        req = Request(url, headers=_SHORT_URL_HEADERS, method="HEAD")
        with urlopen(req, timeout=15) as resp:
            landed = resp.geturl()
        if landed != url:
            return landed, None
    except Exception:
        pass

    # HEAD でリダイレクトなし（または失敗）→ GET でページ本文も取得
    try:
        req = Request(url, headers=_SHORT_URL_HEADERS)
        with urlopen(req, timeout=15) as resp:
            landed = resp.geturl()
            body = resp.read(65536).decode("utf-8", errors="replace")
        return landed, body
    except Exception:
        pass

    return url, None


def _fetch_ogp_cover(page_url: str) -> str:
    """作品ページの og:image をダウンロードして一時ファイルパスを返す。
    取得失敗時は "" を返す。呼び出し元が一時ファイルを削除すること。"""
    # ── ページ HTML 取得 ──────────────────────────────────────────
    html = ""
    try:
        import requests as _rq
        _r = _rq.get(page_url,
                     headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"},
                     timeout=15)
        _r.raise_for_status()
        html = _r.text
    except Exception:
        try:
            import urllib.request as _ur
            _req = _ur.Request(page_url, headers={"User-Agent": UA})
            with _ur.urlopen(_req, timeout=15) as _res:
                html = _res.read().decode("utf-8", errors="replace")
        except Exception as _e:
            print(f"[警告] サイト公式サムネイル: ページ取得失敗 ({_e})")
            print("       自動生成の表紙を使用します。")
            return ""

    # ── og:image URL 抽出 ─────────────────────────────────────────
    # property が先のパターン
    _m = re.search(
        r'<meta\b[^>]+\bproperty=["\']og:image["\'][^>]+\bcontent=["\']([^"\']+)["\']',
        html, re.I)
    # content が先のパターン
    if not _m:
        _m = re.search(
            r'<meta\b[^>]+\bcontent=["\']([^"\']+)["\'][^>]+\bproperty=["\']og:image["\']',
            html, re.I)
    if not _m:
        print("[警告] サイト公式サムネイル: og:image が見つかりませんでした。")
        print("       自動生成の表紙を使用します。")
        return ""

    img_url = _m.group(1).strip()
    # スキーム補完
    if img_url.startswith("//"):
        img_url = "https:" + img_url
    elif img_url.startswith("/"):
        from urllib.parse import urlparse as _up
        _p = _up(page_url)
        img_url = f"{_p.scheme}://{_p.netloc}{img_url}"

    # ── 画像データ取得 ─────────────────────────────────────────────
    img_data = b""
    content_type = ""
    try:
        import requests as _rq
        _ir = _rq.get(img_url,
                      headers={"User-Agent": UA, "Referer": page_url},
                      timeout=15)
        _ir.raise_for_status()
        img_data     = _ir.content
        content_type = _ir.headers.get("Content-Type", "")
    except Exception:
        try:
            import urllib.request as _ur
            _ireq = _ur.Request(img_url, headers={"User-Agent": UA, "Referer": page_url})
            with _ur.urlopen(_ireq, timeout=15) as _ir:
                img_data     = _ir.read()
                content_type = _ir.headers.get("Content-Type", "")
        except Exception as _e:
            print(f"[警告] サイト公式サムネイル: 画像ダウンロード失敗 ({_e})")
            print("       自動生成の表紙を使用します。")
            return ""

    if not img_data:
        print("[警告] サイト公式サムネイル: 画像データが空です。自動生成の表紙を使用します。")
        return ""

    # ── 拡張子判定 ─────────────────────────────────────────────────
    ct_lower = content_type.lower()
    url_lower = img_url.split("?")[0].lower()
    if "png" in ct_lower or url_lower.endswith(".png"):
        ext = ".png"
    else:
        ext = ".jpg"

    # ── 一時ファイルに書き出し ─────────────────────────────────────
    try:
        _fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(_fd)
        with open(tmp_path, "wb") as _f:
            _f.write(img_data)
    except OSError as _e:
        print(f"[警告] サイト公式サムネイル: 一時ファイル作成失敗 ({_e})")
        print("       自動生成の表紙を使用します。")
        return ""

    print(f"  サイト公式サムネイル: {img_url}")
    return tmp_path


def expand_short_url(url: str) -> str:
    """短縮URLを展開して実際のURLを返す。短縮URLでなければそのまま返す。

    最大5ホップまで中間リダイレクトを追跡する。
    HTTP リダイレクトがない場合は HTML 本文の meta refresh / window.location も確認する
    （例: share.google/ID → google.com/share.google?q=ID → 実URL）。
    いずれも失敗した場合は元の URL を返す。
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not any(_host_matches(host, d) for d in _SHORT_URL_HOSTS):
        return url

    print(f"[情報] 短縮URLを展開中: {url}")
    current = url

    for _ in range(5):  # 最大5ホップ
        next_url, body = _follow_one_redirect(current)

        # クエリパラメータに実URLが埋め込まれている中間URLを展開
        next_url = _unwrap_query_url(next_url)

        if next_url == current:
            # HTTP リダイレクトなし → HTML本文からリダイレクト先を探す
            if body:
                from_html = _extract_url_from_html(body)
                if from_html and from_html.startswith("http") and from_html != current:
                    current = from_html
                    continue
            break  # これ以上展開できない

        current = next_url

    if current != url:
        print(f"       展開後URL: {current}")
    return current


def detect_site(url: str) -> str:
    """URLからサイト種別を判定する。'narou' | 'kakuyomu' | 'alphapolis' | 'estar' | 'noichigo' | 'hameln' | 'novema' | 'neopage' | 'genpaku' | 'unknown'"""
    parsed = urlparse(url)
    host   = parsed.netloc.lower()
    if _host_matches(host, "syosetu.com"):
        return "narou"
    if _host_matches(host, "kakuyomu.jp"):
        return "kakuyomu"
    if _host_matches(host, "alphapolis.co.jp"):
        return "alphapolis"
    if _host_matches(host, "estar.jp"):
        return "estar"
    if _host_matches(host, "no-ichigo.jp"):
        return "noichigo"
    if _host_matches(host, "berrys-cafe.jp"):
        return "berrys"
    if _host_matches(host, "monogatary.com"):
        return "monogatary"
    if _host_matches(host, "syosetu.org"):
        return "hameln"
    if _host_matches(host, "novema.jp"):
        return "novema"
    if _host_matches(host, "novelup.plus"):
        return "novelup"
    if _host_matches(host, "sutekibungei.com"):
        return "sutekibungei"
    if _host_matches(host, "novel.daysneo.com"):
        return "days"
    if _host_matches(host, "aozora.gr.jp") or _host_matches(host, "aozora-renewal.cloud"):
        return "aozora"
    if _host_matches(host, "genpaku.org"):
        return "genpaku"
    if _host_matches(host, "hyuki.com") and parsed.path.startswith("/trans/"):
        return "hyuki"
    if _host_matches(host, "neopage.com"):
        return "neopage"
    if _host_matches(host, "solispia.com"):
        return "solispia"
    return "unknown"


def normalize_url(url: str, site: str) -> str:
    """
    話数ページURLが指定された場合に作品トップページURLへ正規化する。

    なろう:
      https://ncode.syosetu.com/n9623lp/1/   → https://ncode.syosetu.com/n9623lp/
      https://ncode.syosetu.com/n9623lp/1    → https://ncode.syosetu.com/n9623lp/
    カクヨム:
      https://kakuyomu.jp/works/16817330661134507300/episodes/16817330661143545431
                                              → https://kakuyomu.jp/works/16817330661134507300
    トップページURLはそのまま返す。
    """
    if site == "narou":
        # パスが /{ncode}/{数字}/ または /{ncode}/{数字} の形式なら話数ページ
        m = re.match(
            r"(https?://[^/]*syosetu\.com/([a-z0-9]+))/\d+/?$",
            url.rstrip("/"), re.I
        )
        if m:
            top_url = m.group(1).rstrip("/") + "/"
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "kakuyomu":
        # パスに /episodes/ が含まれる場合は話数ページ
        m = re.match(
            r"(https?://kakuyomu\.jp/works/[0-9]+)/episodes/[0-9]+",
            url, re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "alphapolis":
        # パスに /episode/ が含まれる場合は話数ページ
        m = re.match(
            r"(https?://www\.alphapolis\.co\.jp/novel/[0-9]+/[0-9]+)/episode/[0-9]+",
            url, re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "estar":
        # viewer?page=N の形式はトップページへ正規化
        m = re.match(
            r"(https?://estar\.jp/novels/[0-9]+)/viewer",
            url, re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] ビューアURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "noichigo":
        # /book/nXXX/NUM の形式はトップページへ正規化
        m = re.match(
            r"(https?://www\.no-ichigo\.jp/book/[^/?#]+)/\d+/?$",
            url.rstrip("/"), re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "berrys":
        # /book/nXXX/NUM の形式はトップページへ正規化
        m = re.match(
            r"(https?://www\.berrys-cafe\.jp/book/[^/?#]+)/\d+/?$",
            url.rstrip("/"), re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "hameln":
        # /novel/NNNNN/N.html の形式はトップページへ正規化
        m = re.match(
            r"(https?://syosetu\.org/novel/\d+)/\d+\.html",
            url, re.I
        )
        if m:
            top_url = m.group(1) + "/"
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "novema":
        # /book/nXXX/NUM の形式はトップページへ正規化
        m = re.match(
            r"(https?://novema\.jp/book/[^/?#]+)/\d+/?$",
            url.rstrip("/"), re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "novelup":
        # /story/NNNNN/MMMMM の形式はトップページへ正規化
        m = re.match(
            r"(https?://novelup\.plus/story/\d+)/\d+/?$",
            url.rstrip("/"), re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "sutekibungei":
        # /novels/{work_uuid}/{episode_uuid} の形式はトップページへ正規化
        m = re.match(
            r"(https?://sutekibungei\.com/novels/[0-9a-f-]{36})/[0-9a-f-]{36}/?$",
            url.rstrip("/"), re.I
        )
        if m:
            top_url = m.group(1)
            print(f"[情報] 話数ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    # NOVEL DAYS はエピソードURLと作品URLで ID が異なるため run_days 内で解決する

    elif site == "neopage":
        # /chapter/{bookId}/{chapterId} の形式はトップページへ正規化
        m = re.match(
            r"(https?://www\.neopage\.com)/chapter/(\w+)/\w+",
            url, re.I
        )
        if m:
            top_url = f"{m.group(1)}/book/{m.group(2)}"
            print(f"[情報] 章ページURLを作品トップページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    elif site == "monogatary":
        # /episode/{id} 形式はそのまま受け付ける（run_monogatary 内で story_id を解決）
        pass

    elif site == "aozora":
        # /cards/{id}/files/{work_id}_{num}.html → /cards/{id}/card{work_id}.html
        m = re.match(
            r"(https?://[^/]+/cards/\d+)/files/(\d+)_\d+\.html$",
            url, re.I
        )
        if m:
            top_url = f"{m.group(1)}/card{m.group(2)}.html"
            print(f"[情報] テキストページURLを図書カードページに正規化しました。")
            print(f"       指定URL : {url}")
            print(f"       正規化後: {top_url}")
            return top_url

    return url


# ══════════════════════════════════════════
#  サイトディスパッチテーブル
# ══════════════════════════════════════════

# (表示名, デフォルト表紙色, run_関数)
_SITE_DISPATCH: dict[str, tuple[str, str, callable]] = {
    "narou":      ("小説家になろう",       "#18b7cd", run_narou),
    "kakuyomu":   ("カクヨム",             "#4BAAE0", run_kakuyomu),
    "alphapolis": ("アルファポリス",       "#e05c2c", run_alphapolis),
    "estar":      ("エブリスタ",           "#00A0E9", run_estar),
    "noichigo":   ("野いちご",             "#FA8296", run_noichigo),
    "berrys":     ("berry's cafe",         "#C8245A", run_berrys),
    "monogatary": ("monogatary.com",       "#231815", run_monogatary),
    "hameln":     ("ハーメルン",           "#6E654C", run_hameln),
    "novema":     ("ノベマ！",             "#595757", run_novema),
    "novelup":    ("ノベルアップ＋",       "#0CBF97", run_novelup),
    "sutekibungei": ("ステキブンゲイ",     "#E4097D", run_sutekibungei),
    "days":       ("NOVEL DAYS",           "#CBA13F", run_days),
    "aozora":     ("青空文庫",             "#000066", run_aozora),
    "genpaku":    ("プロジェクト杉田玄白", "#1D3461", run_genpaku),
    "hyuki":      ("結城浩翻訳の部屋",     "#2D6A4F", run_hyuki),
    "neopage":    ("ネオページ",           "#E94F37", run_neopage),
    "solispia":   ("ソリスピア",           "#7C3AED", run_solispia),
}


def _check_update_one(txt_path: str, delay: float = 1.5) -> dict:
    """1 ファイルの更新チェックを実行し結果辞書を返す。

    Returns:
        {"file": str, "title": str, "author": str,
         "existing": int, "total": int, "new": int,
         "new_titles": list[str], "status": "updated"|"uptodate"|"error",
         "error": str}
    """
    result = {
        "file": os.path.basename(txt_path),
        "title": "", "author": "",
        "existing": 0, "total": 0, "new": 0,
        "new_titles": [],
        "status": "error", "error": "",
    }

    # URL 抽出
    url = _extract_url_from_txt(txt_path)
    if not url:
        result["error"] = "底本URL が見つかりません"
        return result

    # 既存話数カウント
    existing_sections, _ = _load_existing_txt(txt_path)
    n_existing = len(existing_sections)
    result["existing"] = n_existing

    # サイト判定
    try:
        url = expand_short_url(url)
        site = detect_site(url)
        url  = normalize_url(url, site)
    except Exception as e:
        result["error"] = f"URL 解析失敗: {e}"
        return result

    entry = _SITE_DISPATCH.get(site)
    if not entry:
        result["error"] = f"未対応サイト: {site}"
        return result

    label, default_color, runner = entry

    # argparse の Namespace を組み立てて check-update 相当のディスパッチを行う
    fake_args = argparse.Namespace(
        url=url, output=None, delay=delay,
        resume=None, start=1, end=None,
        encoding="utf-8", newline="os",
        no_epub=True, list_only=True,
        cover_bg=default_color,
        from_file=None, from_epub=None,
        title_override=None, author_override=None,
        cover_image=None, use_site_cover=False,
        font=None, toc_at_end=False,
        output_dir=None, kobo=False, horizontal=False,
        append_file=None, check_update_file=None,
        dry_run=False,
    )

    global _CHECK_UPDATE_MODE
    _CHECK_UPDATE_MODE = True
    try:
        runner(fake_args)
        # _CheckUpdateDone が来なかった場合 — list_only で sys.exit(0) が来るはず
        # だが _show_episode_list が _CHECK_UPDATE_MODE 時は例外を送出するのでここには来ない
        result["error"] = "エピソード一覧を取得できませんでした"
    except _CheckUpdateDone as cu:
        n_total = len(cu.ep_titles)
        n_new   = n_total - n_existing
        result["title"]    = cu.title
        result["author"]   = cu.author
        result["total"]    = n_total
        result["new"]      = max(0, n_new)
        result["new_titles"] = cu.ep_titles[n_existing:] if n_new > 0 else []
        result["status"]   = "updated" if n_new > 0 else "uptodate"
    except SystemExit:
        # _show_episode_list が _CHECK_UPDATE_MODE でないパスや dry_run_exit 等
        result["error"] = "エピソード一覧を取得できませんでした"
    except Exception as e:
        result["error"] = str(e)
    finally:
        _CHECK_UPDATE_MODE = False

    return result


def _append_one(txt_path: str, base_args: argparse.Namespace) -> dict:
    """1 ファイルの追記処理を実行し結果辞書を返す。

    base_args から delay / no_epub / cover_image / use_site_cover / font /
    toc_at_end / kobo / horizontal / encoding / newline を引き継ぐ。

    Returns:
        {"file": str, "title": str,
         "status": "ok"|"nochange"|"error", "error": str,
         "added": int}
    """
    result = {
        "file": os.path.basename(txt_path),
        "title": "",
        "status": "error", "error": "",
        "added": 0,
    }

    ap = Path(txt_path).resolve()

    # URL 抽出
    url = _extract_url_from_txt(str(ap))
    if not url:
        result["error"] = "底本URL が見つかりません"
        return result

    # 既存話数（追記後との差分計算用）
    existing_before, _ = _load_existing_txt(str(ap))
    n_before = len(existing_before)

    # サイト判定
    try:
        url = expand_short_url(url)
        site = detect_site(url)
        url  = normalize_url(url, site)
    except Exception as e:
        result["error"] = f"URL 解析失敗: {e}"
        return result

    entry = _SITE_DISPATCH.get(site)
    if not entry:
        result["error"] = f"未対応サイト: {site}"
        return result

    label, default_color, runner = entry

    # --append 相当の args を組み立てる
    fake_args = argparse.Namespace(
        url=url, output=ap.stem, delay=base_args.delay,
        resume=0,                     # 既存話数を自動検出
        start=1, end=None,
        encoding=getattr(base_args, "encoding", "utf-8"),
        newline=getattr(base_args, "newline", "os"),
        no_epub=getattr(base_args, "no_epub", False),
        list_only=False,
        cover_bg=getattr(base_args, "cover_bg", None) or default_color,
        from_file=None, from_epub=None,
        title_override=None, author_override=None,
        cover_image=getattr(base_args, "cover_image", None),
        use_site_cover=getattr(base_args, "use_site_cover", False),
        font=getattr(base_args, "font", None),
        toc_at_end=getattr(base_args, "toc_at_end", False),
        output_dir=str(ap.parent) if str(ap.parent) != "." else None,
        kobo=getattr(base_args, "kobo", False),
        horizontal=getattr(base_args, "horizontal", False),
        append_file=None, check_update_file=None,
        dry_run=False,
    )

    # og:image 取得（--use-site-cover 指定時）
    ogp_tmp = ""
    if fake_args.use_site_cover and not fake_args.cover_image:
        ogp_tmp = _fetch_ogp_cover(url)
        if ogp_tmp:
            fake_args.cover_image = ogp_tmp

    print(f"[情報] 追記モード: {ap.name}")
    print(f"       底本URL   : {url}")
    print(f"サイト判別: {label}")

    try:
        runner(fake_args)
    except SystemExit:
        pass  # run_* 内部の sys.exit(1) 等を吸収
    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        if ogp_tmp and os.path.exists(ogp_tmp):
            os.unlink(ogp_tmp)

    # 追記後の話数を取得して差分を計算
    existing_after, _ = _load_existing_txt(str(ap))
    n_after = len(existing_after)
    added = n_after - n_before

    # タイトルをテキストのヘッダーから取得
    try:
        with open(str(ap), "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
        result["title"] = first_line
    except OSError:
        pass

    if added > 0:
        result["status"] = "ok"
        result["added"]  = added
    else:
        result["status"] = "nochange"

    return result


# ══════════════════════════════════════════════════════════════════════
#  ウォッチモード（--watch）
# ══════════════════════════════════════════════════════════════════════

def _parse_watch_list(path: str) -> list:
    """ウォッチリストファイルをパースして [{url, title, auto}] を返す。

    フォーマット:
        # コメント（行頭・行末どちらもOK）
        https://...  | title=表示名 | auto=true
        https://...  | auto=false
    """
    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise SystemExit(f"[エラー] ウォッチリストを読み込めません: {e}")

    for lineno, raw in enumerate(lines, 1):
        # インラインコメント除去（# より前を使う）
        line = raw.split("#")[0].strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]
        url = parts[0]
        if not url.startswith("http"):
            print(f"[警告] {Path(path).name}:{lineno}: URL として認識できません（スキップ）: {url!r}")
            continue

        entry = {"url": url, "title": None, "auto": None}
        for field in parts[1:]:
            if "=" not in field:
                continue
            key, _, val = field.partition("=")
            key = key.strip().lower()
            val = val.strip()
            if key == "title":
                entry["title"] = val or None
            elif key == "auto":
                entry["auto"] = val.lower() in ("true", "1", "yes")
        entries.append(entry)

    return entries


def _load_watch_cache(path: str) -> dict:
    """ウォッチキャッシュ JSON を読み込む。ファイルがなければ空辞書を返す。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[警告] キャッシュ読み込み失敗（新規扱い）: {e}")
        return {}


def _save_watch_cache(path: str, data: dict) -> None:
    """ウォッチキャッシュをアトミックに書き込む（一時ファイル → rename）。"""
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    try:
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        print(f"[警告] キャッシュ書き込み失敗: {e}")


def _check_update_url(url: str, n_cached: int, delay: float) -> dict:
    """URL 直接指定でエピソード数をチェックし結果辞書を返す。

    _check_update_one の .txt ファイルなし版。
    n_cached = 0 のとき「初回登録」として status="init" を返す。

    Returns:
        {"url": str, "title": str, "author": str,
         "total": int, "new": int, "new_titles": list[str],
         "status": "updated"|"uptodate"|"init"|"error",
         "error": str}
    """
    result = {
        "url": url,
        "title": "", "author": "",
        "total": 0, "new": 0, "new_titles": [],
        "status": "error", "error": "",
    }

    try:
        expanded = expand_short_url(url)
        site     = detect_site(expanded)
        norm_url = normalize_url(expanded, site)
    except Exception as e:
        result["error"] = f"URL 解析失敗: {e}"
        return result

    entry = _SITE_DISPATCH.get(site)
    if not entry:
        result["error"] = f"未対応サイト: {site}"
        return result

    label, default_color, runner = entry

    fake_args = argparse.Namespace(
        url=norm_url, output=None, delay=delay,
        resume=None, start=1, end=None,
        encoding="utf-8", newline="os",
        no_epub=True, list_only=True,
        cover_bg=default_color,
        from_file=None, from_epub=None,
        title_override=None, author_override=None,
        cover_image=None, use_site_cover=False,
        font=None, toc_at_end=False,
        output_dir=None, kobo=False, horizontal=False,
        append_file=None, check_update_file=None,
        dry_run=False,
    )

    global _CHECK_UPDATE_MODE
    _CHECK_UPDATE_MODE = True
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            runner(fake_args)
        result["error"] = "エピソード一覧を取得できませんでした"
    except _CheckUpdateDone as cu:
        n_total = len(cu.ep_titles)
        result["title"]  = cu.title
        result["author"] = cu.author
        result["total"]  = n_total
        if n_cached == 0:
            # 初回: 全話数をキャッシュに登録するだけ、通知しない
            result["status"] = "init"
        else:
            n_new = n_total - n_cached
            result["new"]        = max(0, n_new)
            result["new_titles"] = cu.ep_titles[n_cached:] if n_new > 0 else []
            result["status"]     = "updated" if n_new > 0 else "uptodate"
    except SystemExit:
        result["error"] = "エピソード一覧を取得できませんでした"
    except Exception as e:
        result["error"] = str(e)
    finally:
        _CHECK_UPDATE_MODE = False

    return result


def _find_txt_by_url(directory: str, url: str) -> str:
    """ディレクトリ内の .txt から「底本URL：」が url と一致するものを返す。なければ ""。"""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return ""
    norm = url.rstrip("/")
    for txt in sorted(dir_path.glob("*.txt")):
        found_url = _extract_url_from_txt(str(txt))
        if found_url and found_url.rstrip("/") == norm:
            return str(txt)
    return ""


def _notify_stdout(notify_results: list) -> None:
    """新着・エラーを標準出力に出力する。新着なし・エラーなしなら何も出力しない。"""
    for r in notify_results:
        if r["status"] == "updated":
            label = r.get("list_title") or r.get("title") or r["url"]
            print(f"[NEW] {label} (+{r['new']}話)")
            for t in r["new_titles"]:
                print(f"  + {t}")
        elif r["status"] == "error":
            label = r.get("list_title") or r["url"]
            print(f"[ERROR] {label}")
            print(f"  ! {r['error']}")


def _notify_webhook(notify_results: list, webhook_url: str, fmt: str = "discord") -> None:
    """新着エントリをまとめて Webhook に 1 回 POST する。

    fmt="discord" → {"content": "..."}  （Discord Webhook 互換）
    fmt="slack"   → {"text": "..."}     （Slack Incoming Webhook 互換）
    """
    lines = []
    for r in notify_results:
        if r["status"] == "updated":
            label = r.get("list_title") or r.get("title") or r["url"]
            lines.append(f"【{label}】+{r['new']}話")
            for t in r["new_titles"][:5]:
                lines.append(f"  {t}")
            if r["new"] > 5:
                lines.append(f"  … 他 {r['new'] - 5} 話")
    for r in notify_results:
        if r["status"] == "error":
            label = r.get("list_title") or r["url"]
            lines.append(f"[ERROR] {label}: {r['error']}")

    if not lines:
        return

    text = "\n".join(lines)
    payload = {"text": text} if fmt == "slack" else {"content": text}
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "novel-downloader-watch/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                print(f"[警告] Webhook 送信失敗: HTTP {resp.status}")
    except Exception as e:
        print(f"[警告] Webhook 送信失敗: {e}")


def run_watch(args) -> int:
    """--watch モードのメイン処理。終了コードを返す。"""
    import datetime as _dt

    watch_file   = args.watch
    cache_file   = getattr(args, "watch_cache", ".novel_watch_cache.json")
    notify_mode  = getattr(args, "notify", "stdout")
    webhook_url  = getattr(args, "webhook_url", None)
    webhook_fmt  = getattr(args, "webhook_format", "discord")
    auto_default = getattr(args, "watch_auto_default", False)
    output_dir   = getattr(args, "output_dir", None) or "."

    entries = _parse_watch_list(watch_file)
    if not entries:
        print("[情報] ウォッチリストにエントリがありません。")
        return 0

    cache = _load_watch_cache(cache_file)
    notify_results = []
    has_error = False

    for i, entry in enumerate(entries):
        raw_url    = entry["url"]
        list_title = entry["title"]
        auto       = entry["auto"] if entry["auto"] is not None else auto_default

        # URL 正規化（キャッシュキーの確定）
        try:
            expanded = expand_short_url(raw_url)
            site     = detect_site(expanded)
            norm_url = normalize_url(expanded, site)
        except Exception as e:
            r = {
                "url": raw_url, "list_title": list_title,
                "title": "", "author": "",
                "total": 0, "new": 0, "new_titles": [],
                "status": "error", "error": str(e),
            }
            notify_results.append(r)
            has_error = True
            if i < len(entries) - 1:
                time.sleep(args.delay)
            continue

        cached   = cache.get(norm_url, {})
        n_cached = cached.get("last_episode", 0)

        result = _check_update_url(norm_url, n_cached, args.delay)
        result["list_title"] = list_title
        now_iso = _dt.datetime.now().replace(microsecond=0).isoformat()

        if result["status"] == "error":
            has_error = True
            if norm_url in cache:
                cache[norm_url]["last_checked"] = now_iso
            _save_watch_cache(cache_file, cache)
            notify_results.append(result)

        elif result["status"] == "init":
            # 初回: キャッシュ登録のみ、通知・自動DL なし
            display = list_title or result["title"] or norm_url
            last_title = result.get("new_titles", [""])[-1] if result.get("new_titles") else ""
            print(f"[INIT] {display}: 全{result['total']}話をキャッシュに登録しました"
                  f"（次回チェックから新着を通知します）")
            cache[norm_url] = {
                "title":        result["title"],
                "last_episode": result["total"],
                "last_title":   last_title,
                "last_checked": now_iso,
                "output_file":  None,
            }
            _save_watch_cache(cache_file, cache)

        elif result["status"] == "uptodate":
            cache.setdefault(norm_url, {})
            cache[norm_url]["last_checked"] = now_iso
            _save_watch_cache(cache_file, cache)

        else:  # updated
            notify_results.append(result)

            last_title = result["new_titles"][-1] if result["new_titles"] else cached.get("last_title", "")
            cache.setdefault(norm_url, {})
            cache[norm_url].update({
                "title":        result["title"],
                "last_episode": result["total"],
                "last_title":   last_title,
                "last_checked": now_iso,
            })

            # ── 自動ダウンロード ──────────────────────────────────────
            if auto:
                existing_txt = cache[norm_url].get("output_file") or ""
                if existing_txt and not Path(existing_txt).exists():
                    existing_txt = ""  # ファイルが消えた場合は再探索

                if not existing_txt:
                    existing_txt = _find_txt_by_url(output_dir, norm_url)

                if existing_txt:
                    print(f"\n[AUTO-DL] {result['title']} — 追記: {Path(existing_txt).name}")
                    ar = _append_one(existing_txt, args)
                    if ar["status"] == "ok":
                        cache[norm_url]["output_file"] = str(Path(existing_txt).resolve())
                        print(f"  → {ar['added']} 話追記完了")
                    else:
                        print(f"  → 追記失敗: {ar['error']}")
                        has_error = True
                else:
                    # 既存 .txt なし → 新規フルダウンロード
                    print(f"\n[AUTO-DL] {result['title']} — 新規ダウンロード")
                    dl_entry = _SITE_DISPATCH.get(site)
                    if dl_entry:
                        _, default_color, runner = dl_entry
                        fresh_args = argparse.Namespace(
                            url=norm_url, output=None, delay=args.delay,
                            resume=None, start=1, end=None,
                            encoding=getattr(args, "encoding", "utf-8"),
                            newline=getattr(args, "newline", "os"),
                            no_epub=getattr(args, "no_epub", False),
                            list_only=False,
                            cover_bg=default_color,
                            from_file=None, from_epub=None,
                            title_override=None, author_override=None,
                            cover_image=getattr(args, "cover_image", None),
                            use_site_cover=getattr(args, "use_site_cover", False),
                            font=getattr(args, "font", None),
                            toc_at_end=getattr(args, "toc_at_end", False),
                            output_dir=output_dir if output_dir != "." else None,
                            kobo=getattr(args, "kobo", False),
                            horizontal=getattr(args, "horizontal", False),
                            append_file=None, check_update_file=None,
                            dry_run=False,
                        )
                        try:
                            runner(fresh_args)
                            found = _find_txt_by_url(output_dir, norm_url)
                            if found:
                                cache[norm_url]["output_file"] = str(Path(found).resolve())
                                print(f"  → ダウンロード完了: {Path(found).name}")
                        except Exception as e:
                            print(f"  → ダウンロード失敗: {e}")
                            has_error = True

            _save_watch_cache(cache_file, cache)

        if i < len(entries) - 1:
            time.sleep(args.delay)

    # ── 通知 ─────────────────────────────────────────────────────────
    if notify_mode == "webhook" and webhook_url:
        _notify_webhook(notify_results, webhook_url, webhook_fmt)
    else:
        _notify_stdout(notify_results)

    return 1 if has_error else 0


def main():
    parser = argparse.ArgumentParser(
        description=(
            "小説家になろう・カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン 共通ダウンローダー\n"
            "指定URLのサイトを自動判別して全話を\n"
            "青空文庫書式テキスト（.txt）と縦書きePub3（.epub）に出力します。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python novel_downloader.py https://ncode.syosetu.com/n0022gd/\n"
            "  python novel_downloader.py https://kakuyomu.jp/works/16816700428110685787\n"
            "  python novel_downloader.py https://www.alphapolis.co.jp/novel/243223524/173169133\n"
            "  python novel_downloader.py https://estar.jp/novels/26384598\n"
            "  python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --resume 51\n"
            "  python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --no-epub\n"
            "  python novel_downloader.py --from-file mynovel.txt\n"
            "  python novel_downloader.py --from-file mynovel.txt --title \"タイトル\" --author \"著者名\"\n"
            "  python novel_downloader.py --from-file mynovel.txt --cover-bg \"#2d4073\"\n"
            "  python novel_downloader.py --from-epub mynovel.epub\n"
            "  python novel_downloader.py --from-epub mynovel.epub -o output\n"
        )
    )
    parser.add_argument("url", nargs="?", default=None,
                        help="作品のURL（小説家になろう・カクヨム・アルファポリス・エブリスタ）"
                             "。--from-file 指定時は省略可")
    parser.add_argument("-o", "--output",
                        help="出力ベース名（省略時は作品タイトルから自動生成）"
                             " 例: -o mynovel → mynovel.txt / mynovel.epub")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="リクエスト間隔（秒、デフォルト: 1.5）")
    parser.add_argument("--resume", dest="resume", nargs="?", const=0, type=int,
                        default=None, metavar="N",
                        help="続きからダウンロード。"
                             "N を省略すると既存 .txt から話数を自動検出して再開。"
                             "N を指定すると第 N 話から開始（なろうの従来動作も維持）")
    parser.add_argument("--start", type=int, default=1, metavar="N",
                        help="取得開始話数（デフォルト: 1）")
    parser.add_argument("--end", type=int, default=None, metavar="N",
                        help="取得終了話数（省略時は最終話まで）")
    parser.add_argument("--encoding", default="utf-8",
                        choices=["utf-8", "utf-8-sig", "shift_jis", "cp932"],
                        help="テキスト出力エンコーディング（デフォルト: utf-8）")
    parser.add_argument("--newline", default="os",
                        choices=["os", "lf", "crlf"],
                        help="テキスト出力の改行コード（デフォルト: os=実行環境標準）"
                             "。lf=LF(Unix形式) / crlf=CRLF(Windows形式)")
    parser.add_argument("--no-epub", dest="no_epub", action="store_true",
                        help="ePub出力を省略してテキストのみ出力する")
    parser.add_argument("--list-only", dest="list_only", action="store_true",
                        help="ダウンロードせずエピソード一覧と話数のみ表示して終了する")
    parser.add_argument("--cover-bg", dest="cover_bg", default=None, metavar="COLOR",
                        help="表紙背景色（#RRGGBB形式。"
                             "省略時はなろう: #18b7cd, カクヨム: #4BAAE0, "
                             "ファイルモード: #16234b）")
    parser.add_argument("--from-file", dest="from_file", default=None, metavar="FILE",
                        help="ローカルテキストファイル（青空文庫書式）からePub3を生成する。"
                             "指定時はURLは不要")
    parser.add_argument("--from-epub", dest="from_epub", default=None, metavar="FILE",
                        help="ローカルePub3ファイル（このツールの出力）から"
                             "青空文庫書式テキストを生成する。指定時はURLは不要")
    parser.add_argument("--title", dest="title_override", default=None, metavar="TITLE",
                        help="タイトルを上書き（--from-file 使用時）")
    parser.add_argument("--author", dest="author_override", default=None, metavar="AUTHOR",
                        help="著者名を上書き（--from-file 使用時）")
    parser.add_argument("--cover-image", dest="cover_image", default=None, metavar="FILE",
                        help="表紙に使用するローカル画像ファイル（JPEG/PNG）。"
                             "指定するとPillowによる自動生成表紙の代わりに使用される。"
                             "ファイルが存在しない・非対応形式の場合は自動生成にフォールバック")
    parser.add_argument("--use-site-cover", dest="use_site_cover", action="store_true",
                        help="作品ページの公式サムネイル画像（og:image）を表紙として使用する。"
                             "--cover-image が指定されている場合は --cover-image が優先される")
    parser.add_argument("--font", dest="font", default=None, metavar="FILE",
                        help="ePub本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）。"
                             "指定したフォントを body のデフォルトフォントとして CSS に設定する")
    parser.add_argument("--toc-at-end", dest="toc_at_end", action="store_true",
                        help="目次ページを本文の後（奥付の後）に配置する。"
                             "デフォルトは表紙の直後・本文の前")
    parser.add_argument("--output-dir", dest="output_dir", default=None, metavar="DIR",
                        help="出力先ディレクトリを指定する（省略時はカレントディレクトリ）。"
                             "指定したディレクトリが存在しない場合は自動作成する。"
                             "ファイル名は従来通りタイトルから自動生成（-o と併用可）")
    parser.add_argument("--kobo", dest="kobo", action="store_true",
                        help="Kobo端末向けにePubの拡張子を .kepub.epub にする。"
                             "Kobo Clara / Kobo Sage 等のKobo専用リーダーで"
                             "縦書きや目次を正しく処理させるために使用する")
    parser.add_argument("--horizontal", dest="horizontal", action="store_true",
                        help="横書きePub3を生成する。縦中横（tcy）処理をスキップし、"
                             "全ページを横組み（html.hltr）で出力する。"
                             "page-progression-direction は ltr に設定される")
    parser.add_argument("--append", dest="append_file", default=None, metavar="FILE",
                        help="既存の青空文庫書式 .txt ファイルを指定し、続きのエピソードを追記する。"
                             "ファイル内の「底本URL：」からサイトと URL を自動検出し、"
                             "未取得エピソードをダウンロードして .txt に追加、"
                             "ePub を新規生成（上書き）する。URL の指定は不要")
    parser.add_argument("--append-dir", dest="append_dir", default=None, metavar="DIR",
                        help="ディレクトリ内の全 .txt ファイルを走査し、新着エピソードがある"
                             "作品だけ差分ダウンロード・追記・ePub 再生成する。"
                             "実行前に対象一覧を表示して確認を求める（--yes でスキップ可）")
    parser.add_argument("--yes", dest="yes", action="store_true",
                        help="--append-dir の確認プロンプトをスキップする（自動化用）")
    parser.add_argument("--check-update", dest="check_update_file", default=None, metavar="FILE",
                        help="既存の .txt ファイルを指定し、サイトの最新話数と比較して"
                             "新着エピソード数を表示する。ダウンロードは行わない。"
                             "--append の前に更新確認したいときに使う")
    parser.add_argument("--check-update-dir", dest="check_update_dir", default=None, metavar="DIR",
                        help="指定ディレクトリ内の全 .txt ファイルを走査し、"
                             "各作品の新着エピソードを一括確認する。"
                             "ダウンロードは行わない")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="作品情報（タイトル・著者・総話数）を確認して終了する。"
                             "ダウンロード・ファイル出力は一切行わない")
    parser.add_argument("--watch", dest="watch", default=None, metavar="FILE",
                        help="ウォッチリストファイル（URLリスト）を指定して新着を監視する。"
                             "新着があれば通知し、auto=true のエントリは自動 DL する。"
                             "キャッシュは --watch-cache で指定したファイルに保存される")
    parser.add_argument("--notify", dest="notify", default="stdout",
                        choices=["stdout", "webhook"],
                        help="通知方法（stdout: 標準出力（デフォルト）/ webhook: Webhook POST）")
    parser.add_argument("--webhook-url", dest="webhook_url", default=None, metavar="URL",
                        help="Webhook 送信先 URL（--notify webhook 時に必須）。"
                             "Discord / Slack の Incoming Webhook URL を指定する")
    parser.add_argument("--webhook-format", dest="webhook_format", default="discord",
                        choices=["discord", "slack"],
                        help="Webhook ペイロード形式（discord: content フィールド（デフォルト）"
                             " / slack: text フィールド）")
    parser.add_argument("--watch-cache", dest="watch_cache",
                        default=".novel_watch_cache.json", metavar="FILE",
                        help="ウォッチキャッシュファイルのパス"
                             "（デフォルト: .novel_watch_cache.json）")
    parser.add_argument("--watch-auto-default", dest="watch_auto_default", action="store_true",
                        help="ウォッチリストで auto= を指定しなかったエントリに"
                             "自動 DL を適用する（デフォルトは自動 DL なし）")

    args = parser.parse_args()

    # ── --watch: ウォッチモード ──────────────────────────────────────
    if getattr(args, "watch", None):
        if not Path(args.watch).exists():
            parser.error(f"--watch: ファイルが見つかりません: {args.watch}")
        if args.notify == "webhook" and not args.webhook_url:
            parser.error("--notify webhook には --webhook-url が必要です")
        sys.exit(run_watch(args))

    # ── --check-update-dir: ディレクトリ一括更新チェック ──────────
    if getattr(args, "check_update_dir", None):
        cu_dir = Path(args.check_update_dir).resolve()
        if not cu_dir.is_dir():
            parser.error(f"--check-update-dir: ディレクトリが見つかりません: {args.check_update_dir}")
        txt_files = sorted(cu_dir.glob("*.txt"))
        if not txt_files:
            print(f"[情報] {cu_dir} に .txt ファイルがありません。")
            sys.exit(0)

        # 底本URL を持つファイルのみフィルタ
        targets = []
        for tf in txt_files:
            if _extract_url_from_txt(str(tf)):
                targets.append(tf)
            else:
                print(f"[スキップ] {tf.name} — 底本URL なし")
        if not targets:
            print("[情報] 更新チェック対象のファイルがありません。")
            sys.exit(0)

        print(f"\n{'=' * 60}")
        print(f" 一括更新チェック: {len(targets)} 作品")
        print(f"{'=' * 60}\n")

        results = []
        for i, tf in enumerate(targets):
            print(f"── [{i + 1}/{len(targets)}] {tf.name} ──")
            r = _check_update_one(str(tf), delay=args.delay)
            results.append(r)
            if i < len(targets) - 1:
                time.sleep(args.delay)

        # ── サマリー表示 ─────────────────────────────────────────
        updated  = [r for r in results if r["status"] == "updated"]
        uptodate = [r for r in results if r["status"] == "uptodate"]
        errors   = [r for r in results if r["status"] == "error"]

        print(f"\n{'=' * 60}")
        print(f" チェック結果: {len(targets)} 作品")
        print(f"{'=' * 60}")

        if updated:
            print(f"\n[更新あり] {len(updated)} 作品:")
            for r in updated:
                titles = r["new_titles"]
                first = titles[0] if titles else ""
                last  = titles[-1] if titles else ""
                rng   = f"（{first}）" if r["new"] == 1 else f"（{first}〜{last}）"
                title_str = r["title"] or r["file"]
                print(f"  {title_str} — 新着 {r['new']} 話 {rng}")

        if uptodate:
            print(f"\n[最新]     {len(uptodate)} 作品:")
            for r in uptodate:
                title_str = r["title"] or r["file"]
                print(f"  {title_str} — {r['existing']} 話（最新話まで取得済み）")

        if errors:
            print(f"\n[エラー]   {len(errors)} 作品:")
            for r in errors:
                print(f"  {r['file']} — {r['error']}")

        print()
        sys.exit(1 if errors else 0)

    # ── --append-dir: ディレクトリ一括追記 ───────────────────────
    if getattr(args, "append_dir", None):
        ad_dir = Path(args.append_dir).resolve()
        if not ad_dir.is_dir():
            parser.error(f"--append-dir: ディレクトリが見つかりません: {args.append_dir}")
        txt_files = sorted(ad_dir.glob("*.txt"))
        if not txt_files:
            print(f"[情報] {ad_dir} に .txt ファイルがありません。")
            sys.exit(0)

        # 底本URL を持つファイルのみフィルタ
        targets = []
        skipped_no_url = []
        for tf in txt_files:
            if _extract_url_from_txt(str(tf)):
                targets.append(tf)
            else:
                skipped_no_url.append(tf.name)
        for name in skipped_no_url:
            print(f"[スキップ] {name} — 底本URL なし")
        if not targets:
            print("[情報] 追記対象のファイルがありません。")
            sys.exit(0)

        # ── Phase 1: 事前チェック ────────────────────────────────
        print(f"\n{'=' * 60}")
        print(f" 一括追記チェック: {len(targets)} 作品")
        print(f"{'=' * 60}\n")

        check_results = []   # (Path, _check_update_one の結果)
        candidates = []      # 新着ありの (Path, result)
        for i, tf in enumerate(targets):
            print(f"── [{i + 1}/{len(targets)}] {tf.name} ──")
            r = _check_update_one(str(tf), delay=args.delay)
            check_results.append((tf, r))
            if r["status"] == "updated":
                titles = r["new_titles"]
                first = titles[0] if titles else ""
                last  = titles[-1] if titles else ""
                rng   = f"（{first}）" if r["new"] == 1 else f"（{first}〜{last}）"
                print(f"  → 新着 {r['new']} 話 {rng}")
                candidates.append((tf, r))
            elif r["status"] == "uptodate":
                print(f"  → 新着なし")
            else:
                print(f"  → エラー: {r['error']}")
            if i < len(targets) - 1:
                time.sleep(args.delay)

        if not candidates:
            print(f"\n[情報] 新着のある作品がありません。")
            # エラーがあった場合は報告
            check_errors = [(tf, r) for tf, r in check_results if r["status"] == "error"]
            if check_errors:
                print(f"\n[エラー] {len(check_errors)} 作品:")
                for tf, r in check_errors:
                    print(f"  {tf.name} — {r['error']}")
            sys.exit(1 if check_errors else 0)

        # ── 確認プロンプト ───────────────────────────────────────
        summary_parts = []
        for tf, r in candidates:
            title_str = r["title"] or tf.stem
            summary_parts.append(f"{title_str}: {r['new']}話")
        print(f"\n{'─' * 60}")
        print(f"更新対象: {len(candidates)} 作品（{', '.join(summary_parts)}）")

        if not getattr(args, "yes", False):
            try:
                answer = input("続行しますか？ [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n中断しました。")
                sys.exit(0)
            if answer != "y":
                print("中断しました。")
                sys.exit(0)

        print(f"{'─' * 60}\n")

        # ── Phase 2: 差分ダウンロード ────────────────────────────
        append_results = []
        for i, (tf, cu_r) in enumerate(candidates):
            print(f"\n{'═' * 2} [{i + 1}/{len(candidates)}] {tf.name} {'═' * 40}")
            ar = _append_one(str(tf), args)
            append_results.append((tf, cu_r, ar))
            if i < len(candidates) - 1:
                time.sleep(args.delay)

        # ── Phase 3: サマリー ────────────────────────────────────
        ok_list       = [(tf, cu, ar) for tf, cu, ar in append_results if ar["status"] == "ok"]
        nochange_list = [(tf, cu, ar) for tf, cu, ar in append_results if ar["status"] == "nochange"]
        err_list      = [(tf, cu, ar) for tf, cu, ar in append_results if ar["status"] == "error"]
        uptodate_list = [(tf, r) for tf, r in check_results if r["status"] == "uptodate"]
        check_err_list = [(tf, r) for tf, r in check_results if r["status"] == "error"]

        print(f"\n{'=' * 60}")
        print(f" 一括追記結果: {len(targets)} 作品")
        print(f"{'=' * 60}")

        if ok_list:
            print(f"\n[更新完了] {len(ok_list)} 作品:")
            for tf, cu, ar in ok_list:
                title_str = ar["title"] or tf.stem
                print(f"  {title_str} — {ar['added']} 話追加")

        if nochange_list:
            print(f"\n[変更なし] {len(nochange_list)} 作品:")
            for tf, cu, ar in nochange_list:
                title_str = ar["title"] or tf.stem
                print(f"  {title_str} — ダウンロード完了（新規エピソードなし）")

        if uptodate_list:
            print(f"\n[最新]     {len(uptodate_list)} 作品:")
            for tf, r in uptodate_list:
                title_str = r["title"] or tf.stem
                print(f"  {title_str} — {r['existing']} 話（最新話まで取得済み）")

        all_errors = err_list + [(tf, r, None) for tf, r in check_err_list]
        if all_errors:
            print(f"\n[エラー]   {len(all_errors)} 作品:")
            for item in all_errors:
                if len(item) == 3:
                    tf, _, ar = item
                    err_msg = ar["error"] if ar else ""
                else:
                    tf, r = item
                    err_msg = r["error"]
                print(f"  {tf.name} — {err_msg}")

        print()
        sys.exit(1 if all_errors else 0)

    if args.from_epub:
        # ── ePub → テキスト変換モード ──────────────────────────
        run_from_epub(args)
    elif args.from_file:
        # ── テキスト → ePub 変換モード ─────────────────────────
        if args.cover_bg is None:
            args.cover_bg = "#16234b"
        run_from_file(args)
    else:
        # ── --append または URL モード ───────────────────────────
        if getattr(args, "append_file", None):
            # 既存 .txt から URL・出力先を自動設定して resume ダウンロード
            ap = Path(args.append_file).resolve()
            if not ap.exists():
                parser.error(f"--append: ファイルが見つかりません: {args.append_file}")
            extracted_url = _extract_url_from_txt(str(ap))
            if not extracted_url:
                parser.error(
                    f"--append: テキストファイルから底本 URL を取得できませんでした: {args.append_file}\n"
                    "  novel_downloader.py が生成した「底本URL：」行を含むファイルを指定してください。"
                )
            print(f"[情報] 追記モード: {ap.name}")
            print(f"       底本URL   : {extracted_url}")
            args.url    = extracted_url
            args.resume = 0                    # 既存話数を自動検出
            args.output = ap.stem              # 元ファイルと同名で上書き
            if not getattr(args, "output_dir", None):
                parent = str(ap.parent)
                if parent != ".":
                    args.output_dir = parent

        # ── --check-update モード ────────────────────────────────
        _cu_n_existing = 0
        if getattr(args, "check_update_file", None):
            cu_txt = Path(args.check_update_file).resolve()
            if not cu_txt.exists():
                parser.error(f"--check-update: ファイルが見つかりません: {args.check_update_file}")
            cu_url = _extract_url_from_txt(str(cu_txt))
            if not cu_url:
                parser.error(
                    f"--check-update: テキストファイルから底本 URL を取得できませんでした: {args.check_update_file}\n"
                    "  novel_downloader.py が生成した「底本URL：」行を含むファイルを指定してください。"
                )
            existing_sections, _ = _load_existing_txt(str(cu_txt))
            _cu_n_existing = len(existing_sections)
            args.url      = cu_url
            args.list_only = True
            args.no_epub  = True
            args.resume   = None

        if not args.url:
            parser.error(
                "URLを指定するか、--from-file / --append でローカルファイルを指定してください。"
            )
        args.url = expand_short_url(args.url)
        site = detect_site(args.url)
        args.url = normalize_url(args.url, site)
        # サイト別デフォルト表紙色
        if args.cover_bg is None:
            entry = _SITE_DISPATCH.get(site)
            args.cover_bg = entry[1] if entry else "#18b7cd"

        # ── --use-site-cover: og:image を表紙に使用 ────────────────
        _use_site_cover_tmp = ""
        if getattr(args, "use_site_cover", False) and not getattr(args, "cover_image", None):
            _use_site_cover_tmp = _fetch_ogp_cover(args.url)
            if _use_site_cover_tmp:
                args.cover_image = _use_site_cover_tmp

        global _CHECK_UPDATE_MODE
        _CHECK_UPDATE_MODE = getattr(args, "check_update_file", None) is not None
        try:
            entry = _SITE_DISPATCH.get(site)
            if entry:
                label, _, runner = entry
                print(f"サイト判別: {label}")
                runner(args)
            else:
                print("エラー: 対応しているURLを指定してください。")
                for s_id, (s_label, _, _) in _SITE_DISPATCH.items():
                    print(f"  {s_label}")
                sys.exit(1)
        except _CheckUpdateDone as _cu:
            # --check-update: 取得したエピソード一覧を既存話数と比較して表示
            n_total = len(_cu.ep_titles)
            n_new   = n_total - _cu_n_existing
            print(f"\nタイトル : {_cu.title}")
            print(f"著者     : {_cu.author}")
            print(f"既存     : {_cu_n_existing} 話 / サイト全話: {n_total} 話")
            if n_new <= 0:
                print("[情報] 新着なし（最新話まで取得済み）")
            else:
                new_titles = _cu.ep_titles[_cu_n_existing:]
                first = new_titles[0]
                last  = new_titles[-1]
                range_str = f"（{first}）" if n_new == 1 else f"（{first}〜{last}）"
                print(f"[情報] 新着エピソード: {n_new} 話 {range_str}")
            sys.exit(0)
        finally:
            _CHECK_UPDATE_MODE = False
            if _use_site_cover_tmp and os.path.exists(_use_site_cover_tmp):
                os.unlink(_use_site_cover_tmp)


if __name__ == "__main__":
    main()
