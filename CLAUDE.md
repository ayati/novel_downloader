# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

このファイルは、リポジトリ内のコードを扱う Claude Code (claude.ai/code) へのガイダンスです。

## 概要

単一ファイルの CLI ツール（`novel_downloader/novel_downloader.py`）。Python 3.10 以上が必要。小説家になろう・カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン・ノベマ！・ノベルアップ＋の作品をダウンロードし、以下を出力する：
- 青空文庫書式テキスト（`.txt`）
- 縦書き ePub3（`.epub`）

`--from-file` オプションで、ローカルの青空文庫書式テキストから ePub3 を生成することも可能。

> **注意:** `novel_downloader/` ディレクトリは独立した git リポジトリ（サブモジュール相当）。編集対象のファイルは `novel_downloader/novel_downloader.py`。

## 実行方法

```bash
# なろうからダウンロード（stdlib のみ、追加ライブラリ不要）
python novel_downloader/novel_downloader.py https://ncode.syosetu.com/nXXXXxx/

# カクヨムからダウンロード
python novel_downloader/novel_downloader.py https://kakuyomu.jp/works/XXXXXXXXXX

# アルファポリスからダウンロード
python novel_downloader/novel_downloader.py https://www.alphapolis.co.jp/novel/XXXXXXXXX/XXXXXXXXX

# エブリスタからダウンロード
python novel_downloader/novel_downloader.py https://estar.jp/novels/XXXXXXXXX

# 野いちごからダウンロード
python novel_downloader/novel_downloader.py https://www.no-ichigo.jp/book/nXXXXXX

# ハーメルンからダウンロード（playwright が必要）
python novel_downloader/novel_downloader.py https://syosetu.org/novel/XXXXXXX/

# ノベマ！からダウンロード
python novel_downloader/novel_downloader.py https://novema.jp/book/nXXXXXX

# ノベルアップ＋からダウンロード
python novel_downloader/novel_downloader.py https://novelup.plus/story/XXXXXXXXX

# ローカルテキストから ePub 生成
python novel_downloader/novel_downloader.py --from-file mynovel.txt
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
| `--no-epub` | — | ePub 出力を省略し、テキストのみ出力 |
| `--cover-bg COLOR` | サイト依存 | 表紙背景色（`#RRGGBB` 形式） |
| `--from-file FILE` | — | ローカルテキストから ePub3 を生成 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）。`body` のデフォルトフォントとして CSS に設定される |

## 依存ライブラリ

| ライブラリ | 用途 | インストール |
|---|---|---|
| `requests`, `beautifulsoup4` | カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン・ノベマ！・ノベルアップ＋ | `pip install requests beautifulsoup4` |
| `playwright` | ハーメルン（Cloudflare 回避） | `pip install playwright && python -m playwright install chromium` |
| `Pillow` | PNG 表紙生成 | `pip install Pillow` または `sudo apt install python3-pillow` |
| fonts-noto-cjk | PNG 表紙の日本語フォント | `sudo apt install fonts-noto-cjk` |

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

6. **エブリスタスクレイパー**：`requests` + `BeautifulSoup` を使用。ビューアページ（`/novels/{id}/viewer?page=N`）の `window.__NUXT__` に 15 件ずつ本文が `novelPageId:"NNN",body:"..."` 形式で埋め込まれる。page=1, 16, 31, … と 15 ページ刻みでバッチ取得。エントリポイント：`run_estar(args)`。

7. **野いちごスクレイパー**：`requests` + `BeautifulSoup` を使用。作品トップページの `div.bookChapterList` から章開始ページ番号と章タイトルを取得し、各ページ（`/book/{work_id}/{page_no}`）を個別フェッチ。`--start`/`--end` は章番号で指定。エントリポイント：`run_noichigo(args)`。

8. **ハーメルンスクレイパー**：`playwright` + `BeautifulSoup` を使用。トップページは `requests` で取得（CF保護なし）。エピソードページは Cloudflare Managed Challenge があるため、Playwright で各話ごとに新しい browser context を作成し 5 秒待機して取得。本文は `div#honbun`、前書きは `div#maegaki`、後書きは `div#atogaki`。エントリポイント：`run_hameln(args)`。

9. **ノベマ！スクレイパー**：`requests` + `BeautifulSoup` を使用。野いちごと同構造。`div.bookChapterList` の2階層 `<ul>` からエピソード一覧（章グループ内の個別エピソード、または単独エピソード）を取得し、各ページ（`/book/{work_id}/{page_num}`）を個別フェッチ。本文は `article.bookText > div`、`<br>` 区切り。`noichigo_html_to_aozora` を共用。エントリポイント：`run_novema(args)`。

10. **ノベルアップ＋スクレイパー**：`requests` + `BeautifulSoup` を使用。サーバーレンダリングで JS 不要。og:title から「タイトル（著者名）」形式で情報取得。`div.episodeList` 内の `a.episodeTitle` リンクからエピソード一覧取得。本文は `p#episode_content`（`\n` 区切り）、前書きは `div.novel_foreword`、後書きは `div.novel_afterword`。Ruby は `<rb>/<rt>` 形式。エントリポイント：`run_novelup(args)`。

11. **ローカルファイルモード**：`parse_aozora_text` で既存の青空文庫 `.txt` からタイトル・著者・あらすじを抽出し、`build_epub` に渡す。エントリポイント：`run_from_file(args)`。

12. **`main()`**：引数を解析し、`detect_site(url)` でサイトを判定 → 各 `run_*` 関数にディスパッチ。

## 主な規約

- ルビ記法：テキスト内の `漢字《かんじ》` → XHTML では `<ruby>漢字<rt>かんじ</rt></ruby>`
- 改ページ：テキスト内の `［＃改ページ］` → XHTML では `epub:type="pagebreak"`
- 表紙背景色のデフォルト：なろう `#18b7cd`、カクヨム `#4BAAE0`、アルファポリス `#e05c2c`、エブリスタ `#00A0E9`、野いちご `#FA8296`、ハーメルン `#6E654C`、ノベマ！ `#595757`、ノベルアップ＋ `#0CBF97`、ローカル `#16234b`
- リクエスト間隔デフォルト 1.5 秒、リトライ最大 3 回（間隔 5 秒）
