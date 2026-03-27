# novel_downloader

小説投稿サイトの作品を一括ダウンロードし、**青空文庫書式テキスト**（.txt）と**縦書き ePub3**（.epub）に変換するコマンドラインツールです。

ローカルの青空文庫書式テキストから ePub3 を生成する機能、およびローカル ePub3 ファイルを青空文庫書式テキストに逆変換する機能も備えています。

## 対応サイト

| サイト | URL例 | 追加ライブラリ |
|---|---|---|
| [小説家になろう](https://syosetu.com/) | `https://ncode.syosetu.com/nXXXXxx/` | 不要（stdlib のみ） |
| [カクヨム](https://kakuyomu.jp/) | `https://kakuyomu.jp/works/XXXXXXXXXX` | requests, beautifulsoup4 |
| [アルファポリス](https://www.alphapolis.co.jp/) | `https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX` | requests, beautifulsoup4 |
| [エブリスタ](https://estar.jp/) | `https://estar.jp/novels/XXXXXXXXX` | requests, beautifulsoup4 |
| [野いちご](https://www.no-ichigo.jp/) | `https://www.no-ichigo.jp/book/nXXXXXX` | requests, beautifulsoup4 |
| [ハーメルン](https://syosetu.org/) | `https://syosetu.org/novel/XXXXXXX/` | requests, beautifulsoup4, playwright |
| [ノベマ！](https://novema.jp/) | `https://novema.jp/book/nXXXXXX` | requests, beautifulsoup4 |
| [ノベルアップ＋](https://novelup.plus/) | `https://novelup.plus/story/XXXXXXXXX` | requests, beautifulsoup4 |
| [ステキブンゲイ](https://sutekibungei.com/) | `https://sutekibungei.com/novels/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX` | requests, beautifulsoup4 |
| [NOVEL DAYS](https://novel.daysneo.com/) | `https://novel.daysneo.com/works/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.html` | requests, beautifulsoup4 |
| [青空文庫](https://www.aozora.gr.jp/)（旧） | `https://www.aozora.gr.jp/cards/XXXXXX/cardXXXXXX.html` | 不要（stdlib のみ） |
| [青空文庫](https://www.aozora-renewal.cloud/)（新） | `https://www.aozora-renewal.cloud/cards/XXXXXX/cardXXXXXX.html` | 不要（stdlib のみ） |
| [プロジェクト杉田玄白](https://www.genpaku.org/) | `https://www.genpaku.org/XXXXXX/XXXXXXj.html` | requests, beautifulsoup4 |
| [結城浩翻訳の部屋](https://www.hyuki.com/trans/) | `https://www.hyuki.com/trans/XXXXXX` | requests, beautifulsoup4 |
| [ネオページ](https://www.neopage.com/) | `https://www.neopage.com/book/XXXXXXXXXXXXXXXXX` | requests, beautifulsoup4 |
| [ソリスピア](https://solispia.com/) | `https://solispia.com/title/XXXX` | requests, beautifulsoup4 |
| [berry's cafe](https://www.berrys-cafe.jp/) | `https://www.berrys-cafe.jp/book/nXXXXXXX` | requests, beautifulsoup4 |
| [monogatary.com](https://monogatary.com/) | `https://monogatary.com/story/XXXXXXX` | requests |

## 機能

- 短縮 URL を自動展開してから処理（share.google / search.app / bit.ly / t.co / lin.ee / amzn.to 等 30 種以上対応）
- 上記各サイトの全話を自動取得（URL から自動判別）
- 青空文庫書式テキスト（.txt）出力
  - ルビ記法（`漢字《かんじ》`）を保持
  - ヘッダーにあらすじ・底本 URL を記載
- 縦書き ePub3（.epub）出力
  - JPG 表紙画像を自動生成（Pillow + 日本語フォントが必要）
  - 表紙背景色をオプションで指定可能
  - Pillow・フォント未インストール時は SVG 表紙で代替
  - フォントファイルを ePub 内に埋め込み可能（`--font`）
  - 楽天 Kobo リーダー向け互換対応（縦書き・章目次・画像表紙）
  - `--kobo` オプションで Kobo Clara / Kobo Sage 等の専用端末向けに `.kepub.epub` 形式で出力（kepub タグによる縦書き・目次を端末側で正しく処理）
- ルビ自動判別：`《》` 内に漢字を含む場合は地の文として処理（ルビ誤変換を防止）
- ローカルテキストファイルから ePub3 を生成（`--from-file`）
- ローカル ePub3 ファイルを青空文庫書式テキストに逆変換（`--from-epub`）
  - 自ツール生成 ePub3・汎用 ePub3（カクヨム等）・ストリーミング ZIP 形式 ePub3 に対応
  - Kobo 形式ルビ（`<span>` 分割）を含む `<ruby>` タグを `漢字《かんじ》` 形式に変換
- 縦書き目次ページを spine に自動挿入（デフォルト: 表紙の直後・本文の前）
  - `--toc-at-end` で奥付の後（末尾）に変更可能
  - 表紙・タイトルページ・奥付はリンクのみ、エピソードは 1 から採番
- iPad / iOS の Kindle アプリで縦書き・ルビが正常表示（`primary-writing-mode` メタタグ対応）
- 途中再開機能（`--resume`、なろうのみ）
- 取得話数の範囲指定（`--start` / `--end`）
- テキスト出力の改行コード指定（`--newline`：`os`=OS標準 / `lf` / `crlf`）

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

### 推奨ライブラリ（JPG 表紙生成に必要）

**Ubuntu / Debian:**
```bash
sudo apt install python3-pillow
```

**その他:**
```bash
pip install Pillow
```

### 日本語フォント（JPG 表紙生成に必要）

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

# ノベマ！
python novel_downloader.py https://novema.jp/book/nXXXXXX

# ノベルアップ＋
python novel_downloader.py https://novelup.plus/story/XXXXXXXXX

# ステキブンゲイ
python novel_downloader.py https://sutekibungei.com/novels/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

# NOVEL DAYS
python novel_downloader.py https://novel.daysneo.com/works/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.html

# 青空文庫
python novel_downloader.py https://www.aozora.gr.jp/cards/XXXXXX/cardXXXXXX.html
python novel_downloader.py https://www.aozora-renewal.cloud/cards/XXXXXX/cardXXXXXX.html
```

話数ページの URL を指定した場合も、自動的に作品トップページへ正規化してから取得します。

出力ファイル（作品タイトルをベースに自動命名）:
```
作品タイトル.txt
作品タイトル.epub          # 通常
作品タイトル.kepub.epub    # --kobo 指定時
```

### ローカルテキストから ePub3 を生成

```bash
python novel_downloader.py --from-file 作品名.txt
```

青空文庫書式（このツールが出力する形式）のテキストファイルを ePub3 に変換します。タイトル・著者・あらすじはファイル先頭から自動抽出されます。

### ローカル ePub3 を青空文庫書式テキストに逆変換

```bash
python novel_downloader.py --from-epub 作品名.epub
```

ePub3 ファイルから本文テキストを抽出し、青空文庫書式テキスト（.txt）に変換します。自ツール生成 ePub3 のほか、カクヨム等からダウンロードした汎用 ePub3 にも対応します。

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
| `--newline MODE` | `os` | テキスト出力の改行コード（`os`=実行環境標準 / `lf`=LF / `crlf`=CRLF） |
| `--no-epub` | — | ePub 出力を省略し、テキストのみ出力 |
| `--cover-bg COLOR` | サイト依存 | 表紙背景色（`#RRGGBB` 形式） |
| `--from-file FILE` | — | ローカルテキストファイルから ePub3 を生成 |
| `--from-epub FILE` | — | ローカル ePub3 ファイルを青空文庫書式テキストに逆変換 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--cover-image FILE` | — | 表紙に使用するローカル画像ファイル（JPEG/PNG）。指定すると Pillow による自動生成表紙の代わりに使用される。ファイルが存在しない・非対応形式の場合は自動生成にフォールバック |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf / .ttf / .woff / .woff2）。ファイルが存在しない場合は警告を出して埋め込みなしで続行 |
| `--toc-at-end` | — | 目次ページを奥付の後（末尾）に配置する。デフォルトは表紙の直後・本文の前 |
| `--output-dir DIR` | カレントディレクトリ | 出力先ディレクトリを指定する。存在しない場合は自動作成。ファイル名は従来通りタイトルから自動生成（`-o` と併用可） |
| `--kobo` | — | 楽天 Kobo 専用端末（Kobo Clara / Kobo Sage 等）向けに ePub の拡張子を `.kepub.epub` にする。通常の `.epub` では端末側が kepub タグを解析せず縦書き・目次が正常に反映されないため、Kobo 端末へ転送する場合はこのオプションを使用する |

### 表紙背景色のデフォルト値

| サイト | デフォルト色 |
|---|---|
| 小説家になろう | `#18b7cd` |
| カクヨム | `#4BAAE0` |
| アルファポリス | `#e05c2c` |
| エブリスタ | `#00A0E9` |
| 野いちご | `#FA8296` |
| ハーメルン | `#6E654C` |
| ノベマ！ | `#595757` |
| ノベルアップ＋ | `#0CBF97` |
| ステキブンゲイ | `#E4097D` |
| NOVEL DAYS | `#CBA13F` |
| 青空文庫 | `#000066` |
| プロジェクト杉田玄白 | `#1D3461` |
| 結城浩翻訳の部屋 | `#2D6A4F` |
| ネオページ | `#E94F37` |
| ソリスピア | `#7C3AED` |
| berry's cafe | `#C8245A` |
| monogatary.com | `#231815` |
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

# Windows 向けに CRLF で出力
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --newline crlf

# ローカルテキストから ePub 生成
python novel_downloader.py --from-file mynovel.txt

# タイトル・著者を指定して ePub 生成
python novel_downloader.py --from-file mynovel.txt --title "作品タイトル" --author "著者名"

# フォントを埋め込んで ePub 生成
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --font MyFont.otf
python novel_downloader.py --from-file mynovel.txt --font MyFont.otf

# ローカル ePub3 を青空文庫テキストに変換
python novel_downloader.py --from-epub mynovel.epub

# 目次を末尾に配置して生成
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --toc-at-end

# 出力先フォルダを指定（フォルダが存在しない場合は自動作成）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --output-dir ~/novels

# -o と --output-dir の併用（ファイル名を指定しつつ別フォルダへ出力）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ -o mynovel --output-dir ~/novels

# Kobo Clara / Kobo Sage 等の楽天 Kobo 専用端末向けに .kepub.epub で出力
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --kobo

# Kobo 端末向け・出力フォルダ指定を組み合わせる
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --kobo --output-dir ~/kobo
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
OEBPS/fonts/                 ← 埋め込みフォント（--font 指定時のみ）
OEBPS/images/cover.jpg       ← 表紙画像（JPG または SVG）
OEBPS/image-cover.xhtml      ← 画像表紙ページ（epub:type="cover"）
OEBPS/cover.xhtml            ← タイトル・著者・あらすじページ
OEBPS/ep0001.xhtml           ← 各話（epub:type="chapter"）
OEBPS/ep0002.xhtml
...
OEBPS/colophon.xhtml         ← 奥付
```

- 縦書き（`-epub-writing-mode` / `-webkit-writing-mode` / `writing-mode: vertical-rl`）
- 游明朝 / ヒラギノ明朝 / Noto Serif CJK JP を優先したフォント指定
- ルビ（`<ruby>` タグ）対応
- 各 XHTML に `epub:type` を付与（`cover` / `frontmatter` / `chapter` / `backmatter`）
- OPF に `rendition:layout` / `rendition:orientation` / `rendition:spread` メタデータを付与
- OPF に `primary-writing-mode: horizontal-rl` メタタグを付与（iPad / iOS Kindle 縦書き対応）
- nav.xhtml を spine に明示挿入（縦書き目次ページとして表示）
- nav.xhtml の landmarks に `bodymatter`（本文開始位置）エントリを記載

## ライセンス

MIT License — Copyright (c) 2026 N.Aono
