# CLAUDE.md

このファイルは、リポジトリ内のコードを扱う Claude Code (claude.ai/code) へのガイダンスです。

## 概要

単一ファイルの CLI ツール（`novel_downloader/novel_downloader.py`）。小説家になろう・カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルンの作品をダウンロードし、以下を出力する：
- 青空文庫書式テキスト（`.txt`）
- 縦書き ePub3（`.epub`）

`--from-file` オプションで、ローカルの青空文庫書式テキストから ePub3 を生成することも可能。

## 実行方法

```bash
# なろうからダウンロード
python novel_downloader/novel_downloader.py https://ncode.syosetu.com/nXXXXxx/

# カクヨムからダウンロード（requests + beautifulsoup4 が必要）
python novel_downloader/novel_downloader.py https://kakuyomu.jp/works/XXXXXXXXXX

# アルファポリスからダウンロード（requests + beautifulsoup4 が必要）
python novel_downloader/novel_downloader.py https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX

# エブリスタからダウンロード（requests + beautifulsoup4 が必要）
python novel_downloader/novel_downloader.py https://estar.jp/novels/XXXXXXXXX

# 野いちごからダウンロード（requests + beautifulsoup4 が必要）
python novel_downloader/novel_downloader.py https://www.no-ichigo.jp/book/nXXXXXX

# ハーメルンからダウンロード（playwright + beautifulsoup4 が必要）
python novel_downloader/novel_downloader.py https://syosetu.org/novel/XXXXXXX/

# ローカルテキストから ePub 生成
python novel_downloader/novel_downloader.py --from-file mynovel.txt
```

## 依存ライブラリ

- **カクヨム取得に必要：** `pip install requests beautifulsoup4`
- **PNG 表紙生成に必要：** `pip install Pillow`（または `sudo apt install python3-pillow`）
- **日本語フォント（PNG 表紙）：** `sudo apt install fonts-noto-cjk`

すべてオプション扱いでフォールバックあり（なろうは stdlib のみで動作、Pillow 未インストール時は SVG 表紙で代替）。

## アーキテクチャ

すべて 1 ファイルに集約されており、`# ══════` で区切られたセクションで構成される：

1. **共通ユーティリティ**（行 ~120–320）：`normalize_tate`、`aozora_header/colophon/chapter_title`、`safe_filename`、`write_file` — 青空文庫書式テキストの共通処理。

2. **ePub3 ビルダー**（行 ~320–1210）：stdlib の `zipfile` で ZIP を直接生成。主要関数：
   - `_body_lines_to_xhtml` — 青空文庫本文を XHTML（ruby タグ付き）に変換
   - `_apply_ruby_auto` — 直前の漢字からルビ親文字を自動検出
   - `make_cover_image` — PNG 表紙を生成（Pillow）、なければ SVG にフォールバック
   - `build_epub` — XHTML / CSS / OPF を ZIP にまとめて ePub を組み立てる

3. **なろうスクレイパー**（行 ~1213–1712）：stdlib `urllib` と独自 `HTMLParser` サブクラス（`NarouInfoParser`、`NarouEpisodeListParser`、`NarouEpisodeParser`）を使用。エントリポイント：`run_narou(args)`。

4. **カクヨムスクレイパー**（行 ~1713–2074）：`requests` + `BeautifulSoup` を使用。ページに埋め込まれた `__NEXT_DATA__` JSON からエピソード情報を取得し、取得できない場合は HTML パースにフォールバック。エントリポイント：`run_kakuyomu(args)`。

5. **アルファポリススクレイパー**（行 ~2072–）：`requests` + `BeautifulSoup` を使用。セッション Cookie 有無でサーバーのレスポンスが変わる：Cookie あり → 本文が `div#novelBody` に直接埋め込み、Cookie なし → JS の `.load()` で `/novel/episode_body` に AJAX POST。エントリポイント：`run_alphapolis(args)`。

6. **エブリスタスクレイパー**：`requests` + `BeautifulSoup` を使用。ビューアページ（`/novels/{id}/viewer?page=N`）の `window.__NUXT__` に 15 件ずつ本文が `novelPageId:"NNN",body:"..."` 形式で埋め込まれる。page=1, 16, 31, … と 15 ページ刻みでバッチ取得。章タイトルは最初のバッチのナビセクション（`body:e` エントリ）から抽出。エントリポイント：`run_estar(args)`。

7. **野いちごスクレイパー**：`requests` + `BeautifulSoup` を使用。作品トップページの `div.bookChapterList` から章開始ページ番号と章タイトルを取得し、各ページ（`/book/{work_id}/{page_no}`）を個別フェッチ。本文は `article.bookText` 内の `<div>`（`<aside>` を除いた後）の `<br>` 区切りテキスト。章ごとに全ページを結合してエピソードとして出力。`--start`/`--end` は章番号で指定。エントリポイント：`run_noichigo(args)`。

8. **ハーメルンスクレイパー**：`playwright` + `BeautifulSoup` を使用。トップページは `requests` で取得（CF保護なし）。エピソードページは Cloudflare Managed Challenge があるため、Playwright で各話ごとに新しい browser context を作成し 5 秒待機して取得。本文は `div#honbun` 内の `<p>` タグ、前書きは `div#maegaki`、後書きは `div#atogaki`。Ruby は `<ruby><rb>…</rb><rt>…</rt></ruby>` 形式。エントリポイント：`run_hameln(args)`。起動に `pip install playwright && python -m playwright install chromium` が必要。

9. **ローカルファイルモード**：`parse_aozora_text` で既存の青空文庫 `.txt` からタイトル・著者・あらすじを抽出し、`build_epub` に渡す。エントリポイント：`run_from_file(args)`。

10. **`main()`**：引数を解析し、`detect_site(url)` でサイトを判定 → `run_narou`・`run_kakuyomu`・`run_alphapolis`・`run_estar`・`run_noichigo`・`run_hameln`・`run_from_file` のいずれかにディスパッチ。

## 主な規約

- ルビ記法：テキスト内の `漢字《かんじ》` → XHTML では `<ruby>漢字<rt>かんじ</rt></ruby>`
- 改ページ：テキスト内の `［＃改ページ］` → XHTML では `epub:type="pagebreak"`
- 表紙背景色のデフォルト：なろう `#18b7cd`、カクヨム `#4BAAE0`、アルファポリス `#e05c2c`、エブリスタ `#00A0E9`、野いちご `#FA8296`、ハーメルン `#6E654C`、ローカル `#16234b`
- リクエスト間隔デフォルト 1.5 秒、リトライ最大 3 回（間隔 5 秒）
