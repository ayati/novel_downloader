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
小説家になろう・カクヨム 共通ダウンローダー
全話を青空文庫書式テキスト＋縦書きePub3（各1ファイル）に出力します。

使い方:
    # URLから直接ダウンロード
    python novel_downloader.py <URL> [オプション]

    # ローカルテキストファイルからePub3を生成
    python novel_downloader.py --from-file <FILE> [オプション]

対応サイト（URLモード）:
    小説家になろう  https://ncode.syosetu.com/nXXXXxx/
    カクヨム        https://kakuyomu.jp/works/XXXXXXXXXX

オプション:
    -o FILE          出力ベース名（省略時は作品タイトルから自動生成）
                     例: -o mynovel  → mynovel.txt / mynovel.epub
    --delay SEC      リクエスト間隔（秒、デフォルト 1.5）
    --resume N       第N話から再開（なろうのみ）
    --start N        取得開始話数（デフォルト 1）
    --end N          取得終了話数（省略時は最終話まで）
    --encoding ENC   テキスト出力エンコーディング（デフォルト utf-8）
    --no-epub        ePub出力を省略してテキストのみ出力する
    --cover-bg COLOR 表紙背景色（#RRGGBB形式）
    --from-file FILE ローカルテキストファイルからePub3を生成（URLモード不要）
    --title TITLE    タイトルを上書き（--from-file 使用時）
    --author AUTHOR  著者名を上書き（--from-file 使用時）
    --font FILE      ePub本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）
"""

import sys
import time
import re
import os
import json
import uuid
import zipfile
import argparse
import unicodedata
from datetime import date
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse, urljoin
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
        "[警告] Pillow がインストールされていないため、PNG表紙画像を生成できません。\n"
        "       PNG表紙を有効にするには以下のコマンドでインストールしてください:\n"
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
_RE_EXCL_SPACE = re.compile(r"([！？])([^」』）】\s])")


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
    return (name[:60] if name else fallback)


def write_file(filename: str, header: str, sections: list, colophon: str,
               encoding: str = ENCODING):
    """ヘッダー + 各話（改ページ区切り）+ 奥付 を書き出す。"""
    with open(filename, "w", encoding=encoding) as f:
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

{font_face}/* ── 縦書き基本設定 ── */
html {{
  -epub-writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
  writing-mode: vertical-rl;
  line-height: 2.0;
  font-size: 1em;
}}

body {{
  -epub-writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
  writing-mode: vertical-rl;
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
"""

_XHTML_TMPL = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="ja" lang="ja"
      style="-epub-writing-mode:vertical-rl; -webkit-writing-mode:vertical-rl; writing-mode:vertical-rl;">
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


def _esc(s: str) -> str:
    """XML/HTML エスケープ。"""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


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
    9: その他（句読点・括弧類等）
    """
    cp = ord(ch)
    # 漢字（CJK統合漢字、互換漢字、拡張A/B/C/D/E/F）
    if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2CEAF
            or 0xF900 <= cp <= 0xFAFF):
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
    # その他（句読点・括弧・記号等）
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
    # パターン: (|ベース《よみ》) または (ベース《よみ》)
    # "|" から次の《まで / または《の直前テキストを後処理で分割
    pattern = re.compile(r"\|([^《|]+)《([^》]+)》|《([^》]+)》")
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
                # ベースが句読点・記号類（クラス9）のみの場合も地の文扱い
                if base and all(_char_class(ch) == 9 for ch in base):
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


def _body_lines_to_xhtml(text: str) -> str:
    """
    本文テキスト（改行区切り）をXHTML <p> タグ列に変換する。
    空行 → <p class="body-blank">、それ以外 → <p class="body-line">
    青空文庫ルビ記法「対象《読み》」→ <ruby> タグに変換。
    ルビ開始記号（|）省略時は直前の同一文字種ブロックを自動検出する。
    """
    lines = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line:
            lines.append('<p class="body-blank">&#160;</p>')
        else:
            converted = _apply_ruby_auto(line)
            lines.append(f'<p class="body-line">{converted}</p>')
    return "\n".join(lines)


def _make_cover_xhtml(title: str, author: str, synopsis: str,
                      source_url: str = "", site_name: str = "") -> str:
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
                               epub_type=' epub:type="frontmatter"')


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


def _make_cover_image_xhtml(title: str, fmt: str = "png") -> str:
    """
    ユーザー指定仕様に準拠した画像表紙XHTMLを生成する。
      - CSS: ../css/vertical_image.css
      - 画像: ../images/0000.png (PNG) または ../images/0000.svg (SVG)
      - body class="fit_h"、span.img > img 構造
    """
    ext = fmt  # "png" or "svg"
    img_src = f"../images/0000.{ext}"
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="ja" lang="ja">
<head>
  <meta charset="UTF-8"/>
  <link rel="stylesheet" type="text/css" href="../css/vertical_image.css"/>
  <title>{_esc(title)}</title>
</head>
<body epub:type="cover" class="fit_h">
<figure epub:type="cover-image" class="img">
  <img src="{img_src}" alt="{_esc(title)}"/>
</figure>
</body>
</html>
"""


def _make_episode_xhtml(ep_title: str, body_text: str) -> str:
    """1話分のXHTMLを生成する。"""
    body = (
        f'<h2 class="ep-title">{_esc(ep_title)}</h2>\n'
        + _body_lines_to_xhtml(body_text)
    )
    return _XHTML_TMPL.format(title=_esc(ep_title), body=body,
                               epub_type=' epub:type="chapter"')


def _make_colophon_xhtml(title: str, source_url: str, site_name: str) -> str:
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
                               epub_type=' epub:type="backmatter"')


def _make_nav_xhtml(title: str, ep_titles: list, cover_fmt: str = "") -> str:
    """ナビゲーションドキュメント（nav.xhtml）を生成する。"""
    # toc: 画像表紙ありなら image-cover を先頭リンクに
    toc_items = []
    if cover_fmt:
        toc_items.append('<li><a href="image-cover.xhtml">表紙</a></li>')
    toc_items.append('<li><a href="cover.xhtml">タイトルページ</a></li>')
    for i, t in enumerate(ep_titles):
        toc_items.append(f'<li><a href="ep{i+1:04d}.xhtml">{_esc(t)}</a></li>')
    toc_items.append('<li><a href="colophon.xhtml">奥付</a></li>')
    toc_str = "\n    ".join(toc_items)

    # landmarks: カバー・本文開始・目次をリーダーが認識するための必須ナビ
    cover_href = "image-cover.xhtml" if cover_fmt else "cover.xhtml"
    body_start = "ep0001.xhtml" if ep_titles else "cover.xhtml"
    landmarks = f"""\
<nav epub:type="landmarks" id="landmarks">
  <ol>
    <li><a epub:type="cover"       href="{cover_href}">表紙</a></li>
    <li><a epub:type="toc"         href="nav.xhtml">目次</a></li>
    <li><a epub:type="bodymatter"  href="{body_start}">本文</a></li>
  </ol>
</nav>"""

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="ja" lang="ja">
<head><meta charset="UTF-8"/><title>{_esc(title)}</title></head>
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
              cover_fmt: str = "", font_filename: str = "") -> str:
    """
    OPF（package.opf）を生成する。
    cover_fmt: "png" | "svg" | "" (表紙画像なし)
    font_filename: 埋め込みフォントのファイル名（例: "AyatiShowaSerif-Regular.otf"）
    """
    today = date.today().strftime("%Y-%m-%d")

    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
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

    if cover_fmt == "png":
        manifest_items += [
            '<item id="img0000" href="images/0000.png" media-type="image/png" properties="cover-image"/>',
            '<item id="css-cover" href="css/vertical_image.css" media-type="text/css"/>',
            '<item id="image-cover" href="image-cover.xhtml" media-type="application/xhtml+xml"/>',
        ]
    elif cover_fmt == "svg":
        manifest_items += [
            '<item id="img0000" href="images/0000.svg" media-type="image/svg+xml" properties="cover-image"/>',
            '<item id="css-cover" href="css/vertical_image.css" media-type="text/css"/>',
            '<item id="image-cover" href="image-cover.xhtml" media-type="application/xhtml+xml"/>',
        ]

    manifest_items.append(
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
    )

    spine_items = []
    if cover_fmt:
        spine_items.append('<itemref idref="image-cover" linear="yes"/>')
    spine_items.append('<itemref idref="cover"/>')

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

    manifest_str = "\n    ".join(manifest_items)
    spine_str    = "\n    ".join(spine_items)
    cover_meta   = ('\n    <meta name="cover" content="img0000"/>' if cover_fmt else "")

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         version="3.0"
         unique-identifier="book-id"
         xml:lang="ja">

  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{_esc(title)}</dc:title>
    <dc:creator>{_esc(author)}</dc:creator>
    <dc:language>ja</dc:language>
    <dc:date>{today}</dc:date>
    <meta property="dcterms:modified">{today}T00:00:00Z</meta>{cover_meta}
    <meta property="rendition:layout">reflowable</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">none</meta>
  </metadata>

  <manifest>
    {manifest_str}
  </manifest>

  <spine page-progression-direction="rtl">
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
    import os as _os
    _b = _os.path.basename(_FONT_BOLD_PATH)
    _m = _os.path.basename(_FONT_MEDIUM_PATH) if _FONT_MEDIUM_PATH else _b
    print(f"[情報] 日本語フォント検出: bold={_b}[{_FONT_BOLD_IDX}]  medium={_m}[{_FONT_MEDIUM_IDX}]")
else:
    print(
        "[警告] 日本語フォントが見つかりませんでした。PNG表紙はSVGで代替されます。\n"
        "       フォントをインストールすると PNG 表紙が生成されます:\n"
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
      fmt = "png"  Pillow利用可能時
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
            while title_sz > 28:
                font_t = load_font(_FONT_BOLD_PATH, _FONT_BOLD_IDX, title_sz)
                if font_t is None:
                    raise RuntimeError("Failed to load bold font")
                lines  = wrap_text(title, font_t, max_title_w)
                if len(lines) * (title_sz + 18) <= title_region_h:
                    break
                title_sz -= 4

            font_t = load_font(_FONT_BOLD_PATH, _FONT_BOLD_IDX, title_sz)
            lines  = wrap_text(title, font_t, max_title_w)
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
            font_a = load_font(_FONT_MEDIUM_PATH, _FONT_MEDIUM_IDX, AUTHOR_SZ)
            if font_a is None:
                font_a = font_t  # boldで代替
            try:
                ab = font_a.getbbox(author)   # (left, top, right, bottom)
                aw = ab[2] - ab[0]
                ah = ab[3] - ab[1]
            except Exception:
                aw = len(author) * AUTHOR_SZ
                ah = AUTHOR_SZ
            ax = (W - aw) / 2
            # 作者名エリアの視覚的中央（ascent オフセットを補正）
            area_h = AUTHOR_AREA_BOT - AUTHOR_AREA_TOP
            ay = AUTHOR_AREA_TOP + (area_h - ah) / 2 - (ab[1] if 'ab' in dir() else 0)
            draw.text((ax+2, ay+2), author, font=font_a, fill=(0, 0, 0, 100))
            draw.text((ax,   ay  ), author, font=font_a, fill=(220, 205, 170))

            buf = _io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), "png"

        except Exception as _png_err:
            import traceback as _tb
            print(
                "[警告] PillowでのPNG表紙生成中にエラーが発生しました。SVGで代替します。\n"
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
    font_path: str = "",
):
    """
    縦書きePub3ファイルを生成する。

    ePub3構造（画像表紙あり）:
      mimetype
      META-INF/container.xml
      OEBPS/package.opf
      OEBPS/nav.xhtml
      OEBPS/css/novel.css           ← 本文CSS
      OEBPS/css/vertical_image.css  ← 画像表紙専用CSS
      OEBPS/images/0000.png         ← 表紙画像
      OEBPS/image-cover.xhtml       ← 【spine先頭】画像表紙ページ
      OEBPS/cover.xhtml             ← テキスト表紙（タイトル・著者・あらすじ）
      OEBPS/ep0001.xhtml … ep{N}.xhtml
      OEBPS/colophon.xhtml
    """
    book_id   = str(uuid.uuid4())
    ep_titles = [ep["title"] for ep in episodes]

    # 表紙画像を生成（PNG優先、失敗時SVG）。常に (bytes, fmt) を返す
    cover_data, cover_fmt = make_cover_image(title, author, cover_bg)

    # 埋め込みフォントの準備
    font_filename = Path(font_path).name if font_path else ""
    font_name = Path(font_path).stem if font_path else ""

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
                              font_filename=font_filename))

        # nav.xhtml
        zf.writestr("OEBPS/nav.xhtml",
                    _make_nav_xhtml(title, ep_titles, cover_fmt))

        # 本文CSS（フォント指定あり時は @font-face を追加）
        zf.writestr("OEBPS/css/novel.css",
                    _make_epub_css(font_name, font_filename))

        # 埋め込みフォント
        if font_path:
            with open(font_path, "rb") as _ff:
                zf.writestr(f"OEBPS/fonts/{font_filename}", _ff.read())

        # 画像表紙 → spine 1ページ目（常に生成）
        zf.writestr("OEBPS/css/vertical_image.css", _VERTICAL_IMAGE_CSS)
        zf.writestr(f"OEBPS/images/0000.{cover_fmt}", cover_data)
        zf.writestr("OEBPS/image-cover.xhtml",
                    _make_cover_image_xhtml(title, cover_fmt))

        # テキスト表紙（タイトル・著者・あらすじ）→ spine 2ページ目
        zf.writestr("OEBPS/cover.xhtml",
                    _make_cover_xhtml(title, author, synopsis,
                                      source_url=source_url, site_name=site_name))

        # 各話
        for i, ep in enumerate(episodes):
            zf.writestr(f"OEBPS/ep{i+1:04d}.xhtml",
                        _make_episode_xhtml(ep["title"], ep["body"]))

        # 奥付
        zf.writestr("OEBPS/colophon.xhtml",
                    _make_colophon_xhtml(title, source_url, site_name))


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
        self.episodes    = []
        self._in_ep_link = False
        self._ep_path    = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and "href" in d:
            href = d["href"]
            if re.match(r"^/[a-z0-9]+/\d+/$", href):
                self._in_ep_link = True
                self._ep_path    = href

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_ep_link = False

    def handle_data(self, data):
        if self._in_ep_link and self._ep_path:
            s = data.strip()
            if s:
                self.episodes.append((self._ep_path, s))
                self._ep_path    = ""
                self._in_ep_link = False


def narou_get_all_episodes(base_url: str, ncode: str, index_wait: float = 1.0) -> tuple:
    """作品情報 + 目次全ページを取得して (title, author, synopsis, episodes) を返す。"""
    title, author, synopsis = narou_get_novel_info(ncode)
    time.sleep(index_wait)

    all_eps = []
    page    = 1

    while True:
        url  = f"{base_url}?p={page}" if page > 1 else base_url
        print(f"  目次 p.{page} 取得: {url}")
        html = narou_fetch(url)

        p = NarouEpisodeListParser()
        p.feed(html)

        if not p.episodes:
            # エピソードが0件 → 最終ページを超えた
            break

        all_eps.extend(p.episodes)
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
                        ruby = (f"{self._rb_buf}《{self._rt_buf}》"
                                if self._rt_buf else self._rb_buf)
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


def _ruby_inner_to_aozora(inner: str) -> str:
    """
    <ruby>...</ruby> の中身を青空文庫ルビ記法「ベース《よみ》」に変換する。
    <rb>ベース</rb><rt>よみ</rt> と ベース<rt>よみ</rt>（<rb>なし）の両形式に対応。
    """
    rt_m = re.search(r"<rt>(.*?)</rt>", inner, re.DOTALL)
    if not rt_m:
        return re.sub(r"<[^>]+>", "", inner)
    reading = re.sub(r"<[^>]+>", "", rt_m.group(1)).strip()
    # <rp>...</rp> と <rt>...</rt> ブロックを除去してベーステキストを取得
    base = re.sub(r"<rp>.*?</rp>", "", inner, flags=re.DOTALL)
    base = re.sub(r"<rt>.*?</rt>", "", base, flags=re.DOTALL)
    base = re.sub(r"<[^>]+>", "", base).strip()
    return f"{base}《{reading}》" if reading else base


def narou_extract_body_fallback(html: str) -> str:
    """EpisodeParserで本文が空だった場合の正規表現フォールバック。"""
    raw_ps = re.findall(
        r'<p[^>]+id=["\']?L\d+["\']?[^>]*>(.*?)</p>',
        html, re.DOTALL
    )
    lines = []
    for p_html in raw_ps:
        # <ruby>...</ruby> ブロック全体を青空文庫ルビ記法に変換
        p_html = re.sub(
            r"<ruby>(.*?)</ruby>",
            lambda m: _ruby_inner_to_aozora(m.group(1)),
            p_html, flags=re.DOTALL
        )
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

    base     = args.output or safe_filename(title, "narou_novel")
    txt_path = base + ".txt"
    epub_path= base + ".epub"
    header   = aozora_header(title, author, synopsis, source_url=base_url)
    colophon = aozora_colophon(title, base_url, "小説家になろう")

    # 範囲絞り込み
    start_idx = max(0, (args.start or 1) - 1)
    end_idx   = args.end if args.end else len(episodes)
    target    = episodes[start_idx:end_idx]
    total     = len(target)

    # 再開処理
    resume_from = args.resume or 1
    if resume_from > 1 and os.path.exists(txt_path):
        print(f"\n[Step 2] 第{resume_from}話から再開")
        with open(txt_path, "r", encoding=ENCODING) as f:
            content = f.read()
        body = content[len(header):] if content.startswith(header) else content
        sections = body.split(PAGE_BREAK)
        if sections and "底本：" in sections[-1]:
            sections.pop()
        # 再開時は本文テキストから (subtitle, body_text) を再構築してepub用に保持
        epub_episodes = []
        for sec in sections:
            lines = sec.strip().split("\n")
            # 見出し行（「は大見出し終わり」の次行が本文）
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

    for idx, (path, ep_title) in enumerate(target, start_idx + 1):
        if idx < resume_from:
            continue

        ep_url = f"https://ncode.syosetu.com{path}"
        print(f"  [{idx:5d}/{len(episodes)}] {ep_title[:50]}")

        try:
            html = narou_fetch(ep_url)
        except Exception as e:
            print(f"    !! 取得失敗（スキップ）: {e}")
            sections.append(aozora_chapter_title(ep_title) + "\n\n（取得失敗）\n")
            epub_episodes.append({"title": ep_title, "body": "（取得失敗）"})
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
        epub_episodes.append({"title": subtitle, "body": body})

        if idx % 50 == 0:
            write_file(txt_path, header, sections, colophon, args.encoding)
            print(f"    → 中間保存 ({idx}/{len(episodes)}話)")

        if idx < len(episodes):
            time.sleep(args.delay)

    write_file(txt_path, header, sections, colophon, args.encoding)

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
                   font_path=getattr(args, "font", "") or "")
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
                info["title"]       = work_obj.get("title", "")
                info["description"] = work_obj.get("introduction", "")
                author_ref = work_obj.get("author", {})
                if isinstance(author_ref, dict):
                    akey = author_ref.get("__ref", "")
                    if akey and akey in apollo:
                        info["author"] = apollo[akey].get("activityName", "")
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

        refs = []
        if work_obj:
            for ref in work_obj.get("episodeUnions", []):
                if isinstance(ref, dict) and "__ref" in ref:
                    refs.append(ref["__ref"])

        if refs:
            current_chapter = ""
            chapter_count   = 0
            for ref_key in refs:
                ep_obj = apollo.get(ref_key)
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
            print("  [警告] episodeUnions が見つかりません。Episode を直接列挙します。")
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
                    ruby.replace_with(f"{base}《{rt}》")
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

    print("[3/3] 各エピソードを取得中...")
    episodes_data = []

    for i, ep in enumerate(episode_list, 1):
        print(f"  [{i:4d}/{total}] {ep['title'][:50]}")
        try:
            ep_soup   = kky_fetch(session, ep["url"])
            ep_next   = kky_extract_next_data(ep_soup)
            ep_title_p, ep_chapter, body = kky_extract_episode_body(ep_soup, ep_next, ep["url"])
            fallback  = ep["title"].split(" - ")[0].split("　-　")[0].strip()
            final_ttl = ep_title_p or fallback
            episodes_data.append({"title": final_ttl, "chapter": ep_chapter, "body": body})
        except RuntimeError as e:
            print(f"  [エラー] スキップします: {e}")
            episodes_data.append({"title": ep["title"], "chapter": ep.get("chapter", ""),
                                  "body": "（取得失敗）"})
        if i < total:
            time.sleep(args.delay)

    # 青空文庫テキスト組み立て
    header   = aozora_header(info["title"], info["author"], info.get("description", ""),
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "カクヨム")

    sections     = []
    epub_episodes= []
    for ep in episodes_data:
        chapter = ep.get("chapter", "")
        heading = f"{chapter}　{ep['title']}" if chapter else ep["title"]
        sec_title = aozora_chapter_title(heading, level="中見出し")
        body = normalize_tate(ep["body"]) if ep["body"] and ep["body"] != "（取得失敗）" else ep["body"]
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": heading, "body": body})

    base      = args.output or safe_filename(info["title"], "kakuyomu_novel")
    txt_path  = base + ".txt"
    epub_path = base + ".epub"
    write_file(txt_path, header, sections, colophon, args.encoding)

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
                   font_path=getattr(args, "font", "") or "")
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

    print("[3/3] 各エピソードを取得中...")
    episodes_data = []

    for i, ep in enumerate(episode_list, 1):
        print(f"  [{i:4d}/{total}] {ep['title'][:50]}")
        try:
            ep_title, body = alp_extract_episode(session, ep["url"])
            episodes_data.append({"title": ep_title or ep["title"], "body": body})
        except RuntimeError as e:
            print(f"  [エラー] スキップします: {e}")
            episodes_data.append({"title": ep["title"], "body": "（取得失敗）"})
        if i < total:
            time.sleep(args.delay)

    header   = aozora_header(info["title"], info["author"], info.get("description", ""),
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "アルファポリス")

    sections      = []
    epub_episodes = []
    for ep in episodes_data:
        sec_title = aozora_chapter_title(ep["title"])
        body = (normalize_tate(ep["body"])
                if ep["body"] and ep["body"] != "（取得失敗）" else ep["body"])
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep["title"], "body": body})

    base      = args.output or safe_filename(info["title"], "alphapolis_novel")
    txt_path  = base + ".txt"
    epub_path = base + ".epub"
    write_file(txt_path, header, sections, colophon, args.encoding)

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
                   font_path=getattr(args, "font", "") or "")
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


def est_parse_viewer_page(nuxt_src: str) -> dict:
    """
    ビューアページの __NUXT__ から各エピソードの pageNo・body を抽出する。
    戻り値: {pageNo: body_str}
    """
    result = {}
    for m in re.finditer(
        r'novelPageId:"\d+",body:"((?:[^"\\]|\\.)*?)",bodyParsed', nuxt_src
    ):
        body = m.group(1).replace("\\n", "\n").replace("\\r", "")
        rest = nuxt_src[m.end():m.end() + 5000]
        title_m = re.search(r',title:"(\d+)"', rest)
        if title_m:
            result[int(title_m.group(1))] = body
    return result


def est_parse_chapter_starts(nuxt_src: str) -> dict:
    """
    ビューアページの __NUXT__ ナビセクション (body:e) から
    章タイトルの開始ページを抽出する。
    戻り値: {pageNo: chapterTitle}
    """
    chapter_starts = {}
    seen = set()
    for m in re.finditer(r'novelPageId:"(\d+)",body:e', nuxt_src):
        nid = m.group(1)
        if nid in seen:
            continue
        seen.add(nid)
        block = nuxt_src[m.start():m.start() + 2000]
        title_m   = re.search(r',title:"(\d+)"', block)
        chapter_m = re.search(r',chapterTitle:"([^"]+)"', block)
        if title_m and chapter_m:
            chapter_starts[int(title_m.group(1))] = chapter_m.group(1)
    return chapter_starts


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

    start_page   = max(1, args.start or 1)
    end_page     = min(total_pages, args.end or total_pages)
    target_pages = list(range(start_page, end_page + 1))
    print(f"[2/3] エピソードを取得中（{len(target_pages)} ページ / 全 {total_pages} ページ）...")

    all_bodies    = {}   # {pageNo: body_str}
    chapter_starts = {}  # {pageNo: chapterTitle}
    chapter_parsed = False

    batch_list = list(range(start_page, end_page + 1, 15))
    for batch_i, batch_page in enumerate(batch_list, 1):
        viewer_url = f"{_EST_BASE}/novels/{work_id}/viewer?page={batch_page}"
        print(f"  [{batch_i:3d}/{len(batch_list)}] page={batch_page}")
        try:
            _, viewer_html = est_fetch(session, viewer_url)
            nuxt_src = est_extract_nuxt(viewer_html)
            all_bodies.update(est_parse_viewer_page(nuxt_src))
            if not chapter_parsed:
                chapter_starts = est_parse_chapter_starts(nuxt_src)
                chapter_parsed = True
        except RuntimeError as e:
            print(f"    [エラー] バッチ取得失敗: {e}")
        if batch_i < len(batch_list):
            time.sleep(args.delay)

    # 青空文庫テキスト組み立て
    print("[3/3] テキスト・ePub を生成中...")
    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "エブリスタ")

    sections      = []
    epub_episodes = []
    current_chapter = ""

    for page_no in target_pages:
        body_raw = all_bodies.get(page_no, "（取得失敗）")
        body = (normalize_tate(body_raw)
                if body_raw != "（取得失敗）" else body_raw)

        chapter = chapter_starts.get(page_no, "")
        if chapter and chapter != current_chapter:
            current_chapter = chapter

        ep_title  = (f"{current_chapter}　第{page_no}話"
                     if current_chapter else f"第{page_no}話")
        sec_title = aozora_chapter_title(ep_title)
        sections.append(f"{sec_title}\n\n{body}\n")
        epub_episodes.append({"title": ep_title, "body": body})

    base      = args.output or safe_filename(info["title"], "estar_novel")
    txt_path  = base + ".txt"
    epub_path = base + ".epub"
    write_file(txt_path, header, sections, colophon, args.encoding)

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
                   font_path=getattr(args, "font", "") or "")
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
    """トップページからエピソード一覧を [(ep_num, href, title), ...] で返す。"""
    episodes = []
    table = soup.find("table")
    if not table:
        return episodes
    for row in table.find_all("tr"):
        span = row.find("span", id=True)
        a    = row.find("a", href=True)
        if span and a and span["id"].isdigit():
            episodes.append((int(span["id"]), a["href"], a.get_text(strip=True)))
    return episodes


def hameln_html_to_aozora(honbun_div, maegaki_div=None, atogaki_div=None) -> str:
    """本文div（<p>タグ）を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby><rb>底</rb><rt>そこ</rt></ruby> → 底《そこ》
    for ruby in honbun_div.find_all("ruby"):
        rb = ruby.find("rb")
        rt = ruby.find("rt")
        if rt:
            base_text = rb.get_text() if rb else ruby.get_text()
            ruby.replace_with(f"{base_text}《{rt.get_text()}》")
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
    print(f"[2/3] エピソードを取得中（{len(target)} 話）...")
    print(f"      ※ Cloudflare対策のため1話あたり約{_HAM_CF_WAIT}秒の待機が発生します")

    sections      = []
    epub_episodes = []
    got           = 0

    with _hameln_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        for ep_i, (ep_num, ep_href, ep_title_list) in enumerate(target, 1):
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
                    epub_episodes.append({"title": ep_title, "body": body})
                    got += 1
                else:
                    print(f"    [警告] 本文が見つかりません（CF未解決の可能性）")
                    sec_title = aozora_chapter_title(ep_title)
                    sections.append(f"{sec_title}\n\n（取得失敗）\n")
                    epub_episodes.append({"title": ep_title, "body": "（取得失敗）"})

            except Exception as e:
                print(f"    [エラー] {e}")
                sec_title = aozora_chapter_title(ep_title)
                sections.append(f"{sec_title}\n\n（取得失敗）\n")
                epub_episodes.append({"title": ep_title, "body": "（取得失敗）"})
                if ctx:
                    try:
                        ctx.close()
                    except Exception:
                        pass

            if ep_i < len(target):
                time.sleep(args.delay)

        browser.close()

    print("[3/3] テキスト・ePub を生成中...")
    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "ハーメルン")

    base      = args.output or safe_filename(info["title"], "hameln_novel")
    txt_path  = base + ".txt"
    epub_path = base + ".epub"
    write_file(txt_path, header, sections, colophon, args.encoding)

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
                   font_path=getattr(args, "font", "") or "")
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
    チャプター一覧を [(page_num, chapter_title), ...] で返す。
    bookChapterList の各 <a href="/book/nXXX/NUM"> から取得。
    """
    chapter_list = soup.find("div", class_="bookChapterList")
    if not chapter_list:
        return []
    chapters = []
    for a in chapter_list.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/book/[^/]+/(\d+)$", href)
        if m:
            chapters.append((int(m.group(1)), a.get_text(strip=True)))
    return chapters


def noichigo_html_to_aozora(body_div) -> str:
    """本文div（<br>区切りテキスト）を青空文庫書式テキストに変換する。"""
    # ルビ変換: <ruby>底<rt>そこ</rt></ruby> → 底《そこ》
    for ruby in body_div.find_all("ruby"):
        rt = ruby.find("rt")
        if rt:
            rt_text = rt.get_text()
            rt.decompose()
            for rp in ruby.find_all("rp"):
                rp.decompose()
            ruby.replace_with(f"{ruby.get_text()}《{rt_text}》")
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

    # チャプター範囲を構築 [(page_start, page_end, title), ...]
    chapter_ranges = []
    for i, (page_start, ch_title) in enumerate(chapters):
        if i + 1 < len(chapters):
            page_end = chapters[i + 1][0] - 1
        else:
            page_end = total_pages if total_pages else page_start
        chapter_ranges.append((page_start, page_end, ch_title))

    start_ch = max(1, args.start or 1)
    end_ch   = min(total_chapters, args.end or total_chapters)
    target_chapters = chapter_ranges[start_ch - 1:end_ch]
    total_targets   = sum(e - s + 1 for s, e, _ in target_chapters)
    print(f"[2/3] チャプターを取得中（{len(target_chapters)} チャプター / {total_targets} ページ）...")

    sections      = []
    epub_episodes = []
    got_chapters  = 0

    for ch_i, (page_start, page_end, ch_title) in enumerate(target_chapters, 1):
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
        epub_episodes.append({"title": ch_title, "body": body})
        got_chapters += 1
        if ch_i < len(target_chapters):
            time.sleep(args.delay)

    print("[3/3] テキスト・ePub を生成中...")
    header   = aozora_header(info["title"], info["author"], info["description"],
                             source_url=work_url)
    colophon = aozora_colophon(info["title"], work_url, "野いちご")

    base      = args.output or safe_filename(info["title"], "noichigo_novel")
    txt_path  = base + ".txt"
    epub_path = base + ".epub"
    write_file(txt_path, header, sections, colophon, args.encoding)

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
                   font_path=getattr(args, "font", "") or "")
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

    # PAGE_BREAK で章・話に分割
    raw_sections = body_content.split("［＃改ページ］")

    episodes = []
    for sec in raw_sections:
        sec = sec.strip()
        if not sec:
            continue

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

    base      = args.output or safe_filename(title, "novel")
    epub_path = base + ".epub"
    cover_bg  = args.cover_bg or "#16234b"

    print(f"📖 ePub生成中...")
    build_epub(epub_path, title, author, synopsis,
               "", "ローカルファイル", episodes, cover_bg=cover_bg,
               font_path=getattr(args, "font", "") or "")
    print(f"✅ ePub出力完了: {epub_path}")


# ══════════════════════════════════════════
#  エントリポイント
# ══════════════════════════════════════════

def detect_site(url: str) -> str:
    """URLからサイト種別を判定する。'narou' | 'kakuyomu' | 'alphapolis' | 'estar' | 'noichigo' | 'hameln' | 'unknown'"""
    parsed = urlparse(url)
    host   = parsed.netloc.lower()
    if "syosetu.com" in host:
        return "narou"
    if "kakuyomu.jp" in host:
        return "kakuyomu"
    if "alphapolis.co.jp" in host:
        return "alphapolis"
    if "estar.jp" in host:
        return "estar"
    if "no-ichigo.jp" in host:
        return "noichigo"
    if "syosetu.org" in host:
        return "hameln"
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

    return url


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
    parser.add_argument("--resume", type=int, default=1, metavar="N",
                        help="第N話から再開（なろうのみ、デフォルト: 1）")
    parser.add_argument("--start", type=int, default=1, metavar="N",
                        help="取得開始話数（デフォルト: 1）")
    parser.add_argument("--end", type=int, default=None, metavar="N",
                        help="取得終了話数（省略時は最終話まで）")
    parser.add_argument("--encoding", default="utf-8",
                        choices=["utf-8", "utf-8-sig", "shift_jis", "cp932"],
                        help="テキスト出力エンコーディング（デフォルト: utf-8）")
    parser.add_argument("--no-epub", dest="no_epub", action="store_true",
                        help="ePub出力を省略してテキストのみ出力する")
    parser.add_argument("--cover-bg", dest="cover_bg", default=None, metavar="COLOR",
                        help="表紙背景色（#RRGGBB形式。"
                             "省略時はなろう: #18b7cd, カクヨム: #4BAAE0, "
                             "ファイルモード: #16234b）")
    parser.add_argument("--from-file", dest="from_file", default=None, metavar="FILE",
                        help="ローカルテキストファイル（青空文庫書式）からePub3を生成する。"
                             "指定時はURLは不要")
    parser.add_argument("--title", dest="title_override", default=None, metavar="TITLE",
                        help="タイトルを上書き（--from-file 使用時）")
    parser.add_argument("--author", dest="author_override", default=None, metavar="AUTHOR",
                        help="著者名を上書き（--from-file 使用時）")
    parser.add_argument("--font", dest="font", default=None, metavar="FILE",
                        help="ePub本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）。"
                             "指定したフォントを body のデフォルトフォントとして CSS に設定する")

    args = parser.parse_args()

    if args.from_file:
        # ── ファイルモード ──────────────────────────────────────
        if args.cover_bg is None:
            args.cover_bg = "#16234b"
        run_from_file(args)
    else:
        # ── URLモード ───────────────────────────────────────────
        if not args.url:
            parser.error(
                "URLを指定するか、--from-file でローカルテキストファイルを指定してください。"
            )
        site = detect_site(args.url)
        args.url = normalize_url(args.url, site)
        if args.cover_bg is None:
            if site == "kakuyomu":
                args.cover_bg = "#4BAAE0"
            elif site == "alphapolis":
                args.cover_bg = "#e05c2c"
            elif site == "estar":
                args.cover_bg = "#00A0E9"
            elif site == "noichigo":
                args.cover_bg = "#FA8296"
            elif site == "hameln":
                args.cover_bg = "#6E654C"
            else:
                args.cover_bg = "#18b7cd"

        if site == "narou":
            print("サイト判別: 小説家になろう")
            run_narou(args)
        elif site == "kakuyomu":
            print("サイト判別: カクヨム")
            run_kakuyomu(args)
        elif site == "alphapolis":
            print("サイト判別: アルファポリス")
            run_alphapolis(args)
        elif site == "estar":
            print("サイト判別: エブリスタ")
            run_estar(args)
        elif site == "noichigo":
            print("サイト判別: 野いちご")
            run_noichigo(args)
        elif site == "hameln":
            print("サイト判別: ハーメルン")
            run_hameln(args)
        else:
            print("エラー: 対応しているURLを指定してください。")
            print("  小説家になろう: https://ncode.syosetu.com/nXXXXxx/")
            print("  カクヨム      : https://kakuyomu.jp/works/XXXXXXXXXX")
            print("  アルファポリス: https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX")
            print("  エブリスタ    : https://estar.jp/novels/XXXXXXXXX")
            print("  野いちご      : https://www.no-ichigo.jp/book/nXXXXXX")
            print("  ハーメルン    : https://syosetu.org/novel/XXXXXXX/")
            sys.exit(1)


if __name__ == "__main__":
    main()
