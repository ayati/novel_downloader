# novel_downloader

小説投稿サイトの作品を一括ダウンロードし、**青空文庫書式テキスト**（.txt）と**縦書き ePub3**（.epub）に変換するコマンドラインツールです。

ローカルの青空文庫書式テキストから ePub3 を生成する機能も備えています。

## 対応サイト

| サイト | URL例 | 追加ライブラリ |
|---|---|---|
| [小説家になろう](https://syosetu.com/) | `https://ncode.syosetu.com/nXXXXxx/` | 不要（stdlib のみ） |
| [カクヨム](https://kakuyomu.jp/) | `https://kakuyomu.jp/works/XXXXXXXXXX` | requests, beautifulsoup4 |
| [アルファポリス](https://www.alphapolis.co.jp/) | `https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX` | requests, beautifulsoup4 |
| [エブリスタ](https://estar.jp/) | `https://estar.jp/novels/XXXXXXXXX` | requests, beautifulsoup4 |
| [野いちご](https://www.no-ichigo.jp/) | `https://www.no-ichigo.jp/book/nXXXXXX` | requests, beautifulsoup4 |
| [ハーメルン](https://syosetu.org/) | `https://syosetu.org/novel/XXXXXXX/` | requests, beautifulsoup4, playwright |

## 機能

- 上記 6 サイトの全話を自動取得（URL から自動判別）
- 青空文庫書式テキスト（.txt）出力
  - ルビ記法（`漢字《かんじ》`）を保持
  - ヘッダーにあらすじ・底本 URL を記載
- 縦書き ePub3（.epub）出力
  - PNG 表紙画像を自動生成（Pillow + 日本語フォントが必要）
  - 表紙背景色をオプションで指定可能
  - Pillow・フォント未インストール時は SVG 表紙で代替
  - フォントファイルを ePub 内に埋め込み可能（`--font`）
- ローカルテキストファイルから ePub3 を生成（`--from-file`）
- 途中再開機能（`--resume`、なろうのみ）
- 取得話数の範囲指定（`--start` / `--end`）

## 動作環境

- Python 3.10 以上
- OS: Linux / macOS / Windows

## インストール

### 必須ライブラリ（なろう以外の取得に必要）

```bash
pip install requests beautifulsoup4
```

### ハーメルン取得に必要な追加ライブラリ

ハーメルンのエピソードページは Cloudflare の保護対象のため、ブラウザ自動化ライブラリが必要です。

```bash
pip install playwright
python -m playwright install chromium
```

### 推奨ライブラリ（PNG 表紙生成に必要）

**Ubuntu / Debian:**
```bash
sudo apt install python3-pillow
```

**その他:**
```bash
pip install Pillow
```

### 日本語フォント（PNG 表紙生成に必要）

**Ubuntu / Debian:**
```bash
sudo apt install fonts-noto-cjk
# または
sudo apt install fonts-ipafont
```

**Windows:**
以下のフォントが `C:\Windows\Fonts` に存在すれば自動検出されます。

| フォント | 入手方法 |
|---|---|
| BIZ UDP明朝 | Windows 11 標準搭載 |
| MS 明朝 | Windows 標準搭載 |
| 游明朝 | Microsoft Office 付属 |
| HGS明朝E | Microsoft Office 付属 |

## 使い方

### URL を指定してダウンロード

```bash
# 小説家になろう
python novel_downloader.py https://ncode.syosetu.com/nXXXXxx/

# カクヨム
python novel_downloader.py https://kakuyomu.jp/works/XXXXXXXXXX

# アルファポリス
python novel_downloader.py https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX

# エブリスタ
python novel_downloader.py https://estar.jp/novels/XXXXXXXXX

# 野いちご
python novel_downloader.py https://www.no-ichigo.jp/book/nXXXXXX

# ハーメルン
python novel_downloader.py https://syosetu.org/novel/XXXXXXX/
```

話数ページの URL を指定した場合も、自動的に作品トップページへ正規化してから取得します。

出力ファイル（作品タイトルをベースに自動命名）:
```
作品タイトル.txt
作品タイトル.epub
```

### ローカルテキストから ePub3 を生成

```bash
python novel_downloader.py --from-file 作品名.txt
```

青空文庫書式（このツールが出力する形式）のテキストファイルを ePub3 に変換します。タイトル・著者・あらすじはファイル先頭から自動抽出されます。

## オプション一覧

| オプション | デフォルト | 説明 |
|---|---|---|
| `url` | — | 作品の URL（`--from-file` 指定時は省略可） |
| `-o FILE` | タイトルから自動生成 | 出力ファイルのベース名（例: `-o mynovel` → `mynovel.txt` / `mynovel.epub`） |
| `--delay SEC` | `1.5` | リクエスト間隔（秒） |
| `--resume N` | `1` | 第 N 話から再開（なろうのみ） |
| `--start N` | `1` | 取得開始話数（野いちごは章番号） |
| `--end N` | 最終話 | 取得終了話数（野いちごは章番号） |
| `--encoding ENC` | `utf-8` | テキスト出力エンコーディング（`utf-8` / `utf-8-sig` / `shift_jis` / `cp932`） |
| `--no-epub` | — | ePub 出力を省略し、テキストのみ出力 |
| `--cover-bg COLOR` | サイト依存 | 表紙背景色（`#RRGGBB` 形式） |
| `--from-file FILE` | — | ローカルテキストファイルから ePub3 を生成 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf / .ttf / .woff / .woff2） |

### 表紙背景色のデフォルト値

| サイト | デフォルト色 |
|---|---|
| 小説家になろう | `#18b7cd` |
| カクヨム | `#4BAAE0` |
| アルファポリス | `#e05c2c` |
| エブリスタ | `#00A0E9` |
| 野いちご | `#FA8296` |
| ハーメルン | `#6E654C` |
| ローカルファイル | `#16234b` |

## 使用例

```bash
# なろう作品をダウンロード（テキスト + ePub）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/

# 出力ファイル名を指定
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ -o mynovel

# テキストのみ出力（ePub なし）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --no-epub

# 途中から再開（第 51 話〜）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --resume 51

# 第 1〜10 話だけ取得
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --start 1 --end 10

# 表紙背景色を指定
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --cover-bg "#2d4073"

# カクヨム（Shift_JIS で出力）
python novel_downloader.py https://kakuyomu.jp/works/XXXXXXXXXX --encoding shift_jis

# ローカルテキストから ePub 生成
python novel_downloader.py --from-file mynovel.txt

# タイトル・著者を指定して ePub 生成
python novel_downloader.py --from-file mynovel.txt --title "作品タイトル" --author "著者名"

# フォントを埋め込んで ePub 生成
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --font MyFont.otf
python novel_downloader.py --from-file mynovel.txt --font MyFont.otf
```

## 出力テキスト形式

青空文庫書式に準拠したテキストを出力します。

```
作品タイトル
著者名

【あらすじ】
あらすじ本文

底本URL：https://ncode.syosetu.com/nXXXX/
-------------------------------------------------------
【テキスト中に現れる記号について】

《》：ルビ
（例）漢字《かんじ》
...
-------------------------------------------------------

［＃「第一話タイトル」は大見出し］
第一話タイトル
［＃「第一話タイトル」は大見出し終わり］

本文...

［＃改ページ］

...（以下、各話）
```

## ePub3 構造

```
mimetype
META-INF/container.xml
OEBPS/package.opf
OEBPS/nav.xhtml
OEBPS/css/novel.css
OEBPS/css/vertical_image.css
OEBPS/images/0000.png        ← 表紙画像（PNG または SVG）
OEBPS/image-cover.xhtml      ← 画像表紙ページ
OEBPS/cover.xhtml            ← タイトル・著者・あらすじページ
OEBPS/ep0001.xhtml           ← 各話
OEBPS/ep0002.xhtml
...
OEBPS/colophon.xhtml         ← 奥付
```

- 縦書き（`writing-mode: vertical-rl`）
- 游明朝 / ヒラギノ明朝 / Noto Serif CJK JP を優先したフォント指定
- ルビ（`<ruby>` タグ）対応

## ライセンス

MIT License — Copyright (c) 2026 N.Aono
