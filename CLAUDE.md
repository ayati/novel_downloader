# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

このファイルは、リポジトリ内のコードを扱う Claude Code (claude.ai/code) へのガイダンスです。

## 概要

単一ファイルの CLI ツール（`novel_downloader.py`）。Python 3.10 以上が必要。小説家になろう・カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン・ノベマ！・ノベルアップ＋・ステキブンゲイ・NOVEL DAYS・青空文庫の作品をダウンロードし、以下を出力する：
- 青空文庫書式テキスト（`.txt`）
- 縦書き ePub3（`.epub`）

`--from-file` オプションで、ローカルの青空文庫書式テキストから ePub3 を生成することも可能。

## 実行方法

```bash
# なろうからダウンロード（stdlib のみ、追加ライブラリ不要）
python novel_downloader.py https://ncode.syosetu.com/nXXXXxx/

# カクヨムからダウンロード
python novel_downloader.py https://kakuyomu.jp/works/XXXXXXXXXX

# アルファポリスからダウンロード
python novel_downloader.py https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX

# エブリスタからダウンロード
python novel_downloader.py https://estar.jp/novels/XXXXXXXXX

# 野いちごからダウンロード
python novel_downloader.py https://www.no-ichigo.jp/book/nXXXXXX

# ハーメルンからダウンロード（playwright が必要）
python novel_downloader.py https://syosetu.org/novel/XXXXXXX/

# ノベマ！からダウンロード
python novel_downloader.py https://novema.jp/book/nXXXXXX

# ノベルアップ＋からダウンロード
python novel_downloader.py https://novelup.plus/story/XXXXXXXXX

# ステキブンゲイからダウンロード
python novel_downloader.py https://sutekibungei.com/novels/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

# NOVEL DAYSからダウンロード
python novel_downloader.py https://novel.daysneo.com/works/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.html

# 青空文庫からダウンロード（旧サイト / 新サイト共通）
python novel_downloader.py https://www.aozora.gr.jp/cards/XXXXXX/cardXXXXXX.html
python novel_downloader.py https://www.aozora-renewal.cloud/cards/XXXXXX/cardXXXXXX.html

# ローカルテキストから ePub 生成
python novel_downloader.py --from-file mynovel.txt
```

話数ページの URL を指定した場合も、自動的に作品トップページへ正規化してから取得する。

## オプション一覧

| オプション | デフォルト | 説明 |
|---|---|---|
| `url` | — | 作品 URL（`--from-file` 指定時は省略可） |
| `-o FILE` | タイトルから自動生成 | 出力ベース名（例: `-o mynovel` → `mynovel.txt` / `mynovel.epub`） |
| `--delay SEC` | `1.5` | リクエスト間隔（秒） |
| `--resume N` | `1` | 第 N 話から再開（なろうのみ） |
| `--start N` | `1` | 取得開始話数（野いちごは章番号） |
| `--end N` | 最終話 | 取得終了話数（野いちごは章番号） |
| `--encoding ENC` | `utf-8` | テキスト出力エンコーディング（`utf-8` / `utf-8-sig` / `shift_jis` / `cp932`） |
| `--newline MODE` | `os` | テキスト出力の改行コード（`os`=実行環境標準 / `lf`=LF / `crlf`=CRLF） |
| `--no-epub` | — | ePub 出力を省略し、テキストのみ出力 |
| `--cover-bg COLOR` | サイト依存 | 表紙背景色（`#RRGGBB` 形式） |
| `--from-file FILE` | — | ローカルテキストから ePub3 を生成 |
| `--from-epub FILE` | — | ローカル ePub3 から青空文庫書式テキストを生成 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）。`body` のデフォルトフォントとして CSS に設定される。ファイルが存在しない場合は警告を出して埋め込みなしで続行 |
| `--toc-at-end` | — | 目次ページを奥付の後（末尾）に配置する。デフォルトは表紙の直後・本文の前 |
| `--output-dir DIR` | カレントディレクトリ | 出力先ディレクトリを指定する。存在しない場合は自動作成。ファイル名は従来通りタイトルから自動生成（`-o` と併用可） |

## 依存ライブラリ

| ライブラリ | 用途 | インストール |
|---|---|---|
| `requests`, `beautifulsoup4` | カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン・ノベマ！・ノベルアップ＋ | `pip install requests beautifulsoup4` |
| `playwright` | ハーメルン（Cloudflare 回避） | `pip install playwright && python -m playwright install chromium` |
| `Pillow` | JPEG 表紙生成 | `pip install Pillow` または `sudo apt install python3-pillow` |
| fonts-noto-cjk | PNG 表紙の日本語フォント | `sudo apt install fonts-noto-cjk` |

すべてオプション扱いでフォールバックあり（なろうは stdlib のみで動作、Pillow 未インストール時は SVG 表紙で代替）。

## アーキテクチャ

すべて 1 ファイルに集約されており、`# ══════` で区切られたセクションで構成される：

1. **共通ユーティリティ**（行 ~115–238）：`normalize_tate`、`aozora_header/colophon/chapter_title`、`safe_filename`、`_apply_output_dir`（行 216）、`write_file` — 青空文庫書式テキストの共通処理。`_apply_output_dir` は `--output-dir` を全 `run_*` 関数に横断適用するヘルパー。ルビ関連ユーティリティ（`_char_class`、`_resolve_ruby_base`、`_ruby_needs_pipe`、`_bs4_prev_text`）もこのセクションに集約。

2. **ePub3 ビルダー**（行 ~239–1708）：stdlib の `zipfile` で ZIP を直接生成。主要関数：
   - `_char_class`（行 456）— 文字の種別（0=漢字・1=ひらがな等）を返す。`々仝〆〇ヶ` は青空文庫規定で漢字（0）扱い
   - `_apply_ruby_auto`（行 584）— 直前の漢字からルビ親文字を自動検出
   - `_jisage_to_int`（行 671）— 全角数字・漢数字の字下げ量を int に変換
   - `_body_lines_to_xhtml`（行 682）— 青空文庫本文を XHTML に変換。見出しタグ（大/中/小見出し）を `midashi-oo`/`midashi-naka`/`midashi-sho` クラスの `<p>` に変換。字下げタグ（`［＃N字下げ］`・`［＃ここからN字下げ］`・`［＃ここから改行天付き、折り返してN字下げ］`）をブロック/単行/ぶら下げインデントの CSS クラスに変換。図タグ（`の図`・`のキャプション付きの図`・`はキャプション`・`ここからキャプション`）を `<figure>/<img>/<figcaption>` に変換
   - `make_cover_image`（行 1460）— JPEG 表紙を生成（Pillow、quality=90）、なければ SVG にフォールバック
   - `build_epub`（行 1604）— XHTML / CSS / OPF を ZIP にまとめて ePub を組み立てる。`images: dict` パラメータで青空文庫 ZIP 内画像を `OEBPS/images/` に埋め込み可能

3. **なろうスクレイパー**（行 ~1709–2112）：stdlib `urllib` と独自 `HTMLParser` サブクラス（`NarouInfoParser`、`NarouEpisodeListParser`、`NarouEpisodeParser`）を使用。エントリポイント：`run_narou`（行 2113）。

4. **カクヨムスクレイパー**（行 ~2240–2517）：`requests` + `BeautifulSoup` を使用。ページに埋め込まれた `__NEXT_DATA__` JSON からエピソード情報を取得し、取得できない場合は HTML パースにフォールバック。エントリポイント：`run_kakuyomu`（行 2518 付近）。

5. **アルファポリススクレイパー**（行 ~2730–2936）：`requests` + `BeautifulSoup` を使用。エピソード一覧は `script[type="application/json"]` 内の `chapterEpisodes` JSON から取得（`{url, mainTitle, subTitle, isPublic}` 形式）。旧形式の `div.episodes > div.episode` はフォールバックとして残存。本文取得はセッション Cookie 有無でサーバーのレスポンスが変わる：Cookie あり → 本文が `div#novelBody` に直接埋め込み、Cookie なし → JS の `.load()` で `/novel/episode_body` に AJAX POST。エントリポイント：`run_alphapolis`（行 2825 付近）。

6. **エブリスタスクレイパー**（行 ~2937–3113）：`requests` + `BeautifulSoup` を使用。ビューアページ（`/novels/{id}/viewer?page=N`）の `window.__NUXT__` に 15 件ずつ本文が `novelPageId:"NNN",body:"..."` 形式で埋め込まれる。page=1, 16, 31, … と 15 ページ刻みでバッチ取得。エントリポイント：`run_estar`（行 3008）。

7. **ハーメルンスクレイパー**（行 ~3114–3359）：`playwright` + `BeautifulSoup` を使用。トップページは `requests` で取得（CF保護なし）。エピソードページは Cloudflare Managed Challenge があるため、Playwright で各話ごとに新しい browser context を作成し 5 秒待機して取得。本文は `div#honbun`、前書きは `div#maegaki`、後書きは `div#atogaki`。エントリポイント：`run_hameln`（行 3212）。

8. **野いちごスクレイパー**（行 ~3360–3595）：`requests` + `BeautifulSoup` を使用。作品トップページの `div.bookChapterList` から章開始ページ番号と章タイトルを取得し、各ページ（`/book/{work_id}/{page_no}`）を個別フェッチ。`--start`/`--end` は章番号で指定。エントリポイント：`run_noichigo`（行 3466）。

9. **ノベマ！スクレイパー**（行 ~3596–3796）：`requests` + `BeautifulSoup` を使用。野いちごと同構造。`div.bookChapterList` の2階層 `<ul>` からエピソード一覧（章グループ内の個別エピソード、または単独エピソード）を取得し、各ページ（`/book/{work_id}/{page_num}`）を個別フェッチ。本文は `article.bookText > div`、`<br>` 区切り。`noichigo_html_to_aozora` を共用。エントリポイント：`run_novema`（行 3698）。

10. **ノベルアップ＋スクレイパー**（行 ~3797–4016）：`requests` + `BeautifulSoup` を使用。サーバーレンダリングで JS 不要。og:title から「タイトル（著者名）」形式で情報取得。`div.episodeList` 内の `a.episodeTitle` リンクからエピソード一覧取得。本文は `p#episode_content`（`\n` 区切り）、前書きは `div.novel_foreword`、後書きは `div.novel_afterword`。Ruby は `<rb>/<rt>` 形式。エントリポイント：`run_novelup`（行 3929）。

11. **ステキブンゲイスクレイパー**（行 ~4017–4223）：`requests` + `BeautifulSoup` を使用。Nuxt.js SSR で JS 不要。タイトルは og:title（" - ステキブンゲイ" サフィックスを除去）、あらすじは og:description、著者は `/users/` へのリンクテキスト（フォールバック: `window.__NUXT__` の `"name":"..."` パターン）。エピソード一覧は `a[href^="/novels/{uuid}/{uuid}"]` リンク。本文は `div#episodeBody`（`\n` 区切り）。Ruby は `<rb>/<rt>` 形式。エントリポイント：`run_sutekibungei`（行 4139）。

12. **NOVEL DAYS スクレイパー**（行 ~4224–4451）：`requests` + `BeautifulSoup` を使用。SSR で JS 不要（講談社運営）。タイトルは `div.detail h2`、著者は `div.author a span.f18px`、あらすじは `p.readmore`（`<br>` → 改行）。エピソード一覧は `div.contents ol li a[href*="/works/episode/"]`。本文は `div.episode div.inner`（`<br>` → 改行）。Ruby は `<rb>/<rt>/<rp>` 形式。エピソードURLが指定された場合は作品トップページリンクを自動検出。エントリポイント：`run_days`（行 4354）。

13. **青空文庫スクレイパー**（行 ~4452–4760）：stdlib のみ（urllib + zipfile + re）で動作。旧サイト（`aozora.gr.jp`）・新サイト（`aozora-renewal.cloud`）の両方に対応。図書カードページからルビ付き ZIP（`_ruby_` 優先）の URL を抽出し、ZIP をダウンロード・展開。`aozora_download_extract`（行 4533）は画像ファイル（PNG/JPG/GIF等）も戻り値 `images` dict に含めて返す。テキストファイルはエンコーディングを自動判定（ShiftJIS → CP932 → UTF-8 → EUC-JP）して UTF-8 に変換して保存。ePub 生成時は `aozora_text_to_episodes()`（行 4625）でタイトル・著者を先頭2非空行から、本文を区切り線ブロック後・底本情報前から抽出し、`［＃改ページ］` と見出しタグ（`_split_aozora_by_headings`）で章分割。`.txt` のファイル名は ZIP 内のファイル名、`.epub` のファイル名は `safe_filename(title)` に変更（Kindle ライブラリでの表示に対応）。テキストページURL（`/files/{id}_{num}.html`）を指定した場合は図書カードページ URL へ正規化。エントリポイント：`run_aozora`（行 4702）。

14. **ローカルファイルモード**（行 ~4761–4920）：`parse_aozora_text`（行 4765）で既存の青空文庫 `.txt` からタイトル・著者・あらすじを抽出し、`_split_aozora_by_headings`（行 4589）で見出し分割を行って `build_epub` に渡す。`_strip_heading_block`（行 4564）は各チャプター本文の先頭から見出しマークアップ行を除去する（ep-title として別途レンダリングされるため）。エントリポイント：`run_from_file`（行 4857）。

15. **ローカルePub3 → テキスト変換**（行 ~4921–5443）：stdlib のみ（`zipfile` + `re` + `html` + `zlib`）で動作。
   - `_read_streaming_zip()`（行 5091）：中央ディレクトリなしのストリーミング ZIP（Kindle 配信 ePub 等）をローカルヘッダ走査で読み込む
   - `_ZipLike`：`zipfile.ZipFile` 互換ラッパー（`_read_streaming_zip` の戻り値をラップ）
   - `_ruby_to_aozora()`（行 4925）：標準形式・Kobo `<span>` 分割形式の両方に対応した `<ruby>` → `《》` 変換
   - `_epub_generic_to_text()`（行 5017）：汎用 XHTML の `<p>` タグを収集。`<br>` のみ改行扱い、それ以外のタグ内改行は HTML 的空白として正規化し日本語文字隣接スペースを除去
   - `parse_epub()`（行 5221）：自ツール生成 ePub（`OEBPS/ep*.xhtml`）優先、汎用 spine フォールバック。nav ドキュメントから `{zip_path → chapter_title}` マップを構築し genuine_nav_count ≥ 2 で nav-only モードに移行（前付け・後付け除外）。`BadZipFile` 時は `_read_streaming_zip` にフォールバック
   - エントリポイント：`run_from_epub()`（行 5392）

16. **`main()`**（行 ~5444–）：`_host_matches`（行 5448）でドメイン判定ヘルパー（スプーフィング対策）、`detect_site`（行 5455）でサイト判定、`normalize_url`（行 5484）で話数 URL → 作品トップ URL 正規化、`main()`（行 5631）で引数解析 → 各 `run_*` 関数にディスパッチ。

## ePub3 内部構造

```
mimetype
META-INF/container.xml
OEBPS/package.opf
OEBPS/nav.xhtml              ← 縦書き目次ページ（spine に明示挿入）
OEBPS/css/novel.css
OEBPS/fonts/                 ← 埋め込みフォント（--font 指定時のみ）
OEBPS/images/cover.jpg       ← 表紙画像（JPEG または SVG）
OEBPS/images/                ← 青空文庫 ZIP 内画像（aozora のみ）
OEBPS/cover-image.xhtml      ← 画像表紙ページ（epub:type="cover"、body に epub:type="cover"、img に epub:type="cover-image"）
OEBPS/cover.xhtml            ← タイトル・著者・あらすじページ
OEBPS/ep0001.xhtml           ← 各話（epub:type="chapter"）
OEBPS/ep0002.xhtml
...
OEBPS/colophon.xhtml         ← 奥付
```

spine 読み順（デフォルト）: cover-image → cover → **nav（目次）** → ep0001…epNNNN → colophon
`--toc-at-end` 指定時: cover-image → cover → ep0001…epNNNN → colophon → **nav（目次）**

縦書き（`writing-mode: vertical-rl`）。各 XHTML に `epub:type` を付与。楽天 Kobo・iPad/iOS Kindle リーダー向け互換対応済み。
OPF `<metadata>` に `<meta name="primary-writing-mode" content="horizontal-rl"/>` を付与（iPad/iOS Kindle 縦書き対応）。

## 主な規約

- ルビ記法：テキスト内の `漢字《かんじ》` → XHTML では `<ruby>漢字<rt>かんじ</rt></ruby>`
- 改ページ：テキスト内の `［＃改ページ］` → XHTML では `epub:type="pagebreak"`
- ルビ自動判別：`《》` 内に漢字を含む場合は地の文として処理（ルビ誤変換を防止）
- ルビ範囲確定：各スクレイパーは `|BASE《RUBY》` 形式（ASCII パイプ）で明示。`_ruby_needs_pipe(base, preceding)` で必要性を判定：(1) base が複数文字種を含む場合、(2) 直前テキストの末尾が base と同じ文字種の場合。`_bs4_prev_text(tag)` で BS4 タグの直前テキストを取得。なろう HTMLParser では `"".join(self._cur_para)` を preceding として渡す。青空文庫テキスト内の `｜`（全角）は `_apply_ruby_auto` が直接認識するため除去しない（`aozora_text_to_episodes`）
- 特殊記号の文字種：`々仝〆〇ヶ` は青空文庫規定により漢字（class 0）扱い。ルビ範囲判定（`_char_class`）に影響する
- 字下げタグ：`［＃N字下げ］`（単行）→ `text-indent: Nem`、`［＃ここからN字下げ］` → `div.aozora-indent-Nem`（縦書き `padding-top`）、`［＃ここから改行天付き、折り返してN字下げ］` → `div.aozora-hanging-Nem`（`padding-top` + 内側 `<p>` に `text-indent: -Nem`）
- 青空文庫図タグ：`「ファイル名」の図（ファイル名）入る` → `<figure><img></figure>`、キャプション付き → `<figcaption>` 付き。画像は `OEBPS/images/` に配置し、src は `images/filename`（`../images/` は誤り）
- 表紙背景色のデフォルト：なろう `#18b7cd`、カクヨム `#4BAAE0`、アルファポリス `#e05c2c`、エブリスタ `#00A0E9`、野いちご `#FA8296`、ハーメルン `#6E654C`、ノベマ！ `#595757`、ノベルアップ＋ `#0CBF97`、ステキブンゲイ `#E4097D`、NOVEL DAYS `#CBA13F`、青空文庫 `#000066`、ローカル `#16234b`
- リクエスト間隔デフォルト 1.5 秒、リトライ最大 3 回（間隔 5 秒）

## font/ ディレクトリ

`font/` に OFL ライセンスのフォントファイル（`AyatiShowaSerif-Regular.ttf`）を同梱。`--font font/AyatiShowaSerif-Regular.ttf` のように指定して ePub に埋め込める。

## 動作確認

テストスイートは存在しないため、手動で動作確認する：

```bash
# なろう（stdlib のみ、追加ライブラリ不要）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --no-epub

# ローカルテキストから ePub 生成（出力済みの .txt を使い回せる）
python novel_downloader.py --from-file <出力済み.txt>

# ローカル ePub3 から青空文庫テキスト生成（逆変換）
python novel_downloader.py --from-epub <出力済み.epub>

# ePub 構造確認（zipfile として展開可能）
python -c "import zipfile; zipfile.ZipFile('<出力.epub>').extractall('/tmp/epub_check')"
```

## 新スクレイパー追加手順

1. `detect_site(url)` にサイト判定条件を追加（`return "サイト名"` 形式）
2. `run_サイト名(args)` 関数を実装し、`aozora_header()` / `aozora_chapter_title()` / `aozora_colophon()` で青空文庫テキストを組み立てて `write_file()` + `build_epub()` を呼ぶ
3. `normalize_url()` にエピソード URL → 作品トップ URL の正規化ロジックを追加（必要な場合）
4. `main()` の if/elif チェーンに `elif site == "サイト名":` ブランチを追加し、カバー色デフォルト・ディスパッチ・エラーメッセージを追記
5. CLAUDE.md のアーキテクチャセクションと依存ライブラリ表を更新

## 青空文庫テキスト出力形式

```
作品タイトル
著者名

【あらすじ】
あらすじ本文

底本URL：https://...
-------------------------------------------------------
【テキスト中に現れる記号について】
《》：ルビ（例）漢字《かんじ》
...
-------------------------------------------------------

［＃「第一話タイトル」は大見出し］
第一話タイトル
［＃「第一話タイトル」は大見出し終わり］

本文...

［＃改ページ］
```
