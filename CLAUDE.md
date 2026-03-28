# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

このファイルは、リポジトリ内のコードを扱う Claude Code (claude.ai/code) へのガイダンスです。

## 概要

単一ファイルの CLI ツール（`novel_downloader.py`）。Python 3.10 以上が必要。小説家になろう・カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン・ノベマ！・ノベルアップ＋・ステキブンゲイ・NOVEL DAYS・青空文庫・プロジェクト杉田玄白・結城浩翻訳の部屋・ネオページ・ソリスピア・berry's cafe・monogatary.com の作品をダウンロードし、以下を出力する：
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

# プロジェクト杉田玄白からダウンロード
python novel_downloader.py https://www.genpaku.org/XXXXXX/XXXXXXj.html

# 結城浩翻訳の部屋からダウンロード
python novel_downloader.py https://www.hyuki.com/trans/XXXXXX

# ネオページからダウンロード
python novel_downloader.py https://www.neopage.com/book/XXXXXXXXXXXXXXXXX

# ソリスピアからダウンロード
python novel_downloader.py https://solispia.com/title/XXXX

# berry's cafeからダウンロード
python novel_downloader.py https://www.berrys-cafe.jp/book/nXXXXXXX

# monogatary.comからダウンロード（story URL または episode URL どちらでも可）
python novel_downloader.py https://monogatary.com/story/XXXXXXX
python novel_downloader.py https://monogatary.com/episode/XXXXXXX

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
| `--resume [N]` | — | 続きからダウンロード。`N` 省略時は既存 `.txt` から話数を自動検出して再開。`N` 指定時は第 N 話から開始。全サイト対応 |
| `--start N` | `1` | 取得開始話数（野いちご・ノベマ！・berry's cafe は章番号） |
| `--end N` | 最終話 | 取得終了話数（野いちご・ノベマ！・berry's cafe は章番号） |
| `--encoding ENC` | `utf-8` | テキスト出力エンコーディング（`utf-8` / `utf-8-sig` / `shift_jis` / `cp932`） |
| `--newline MODE` | `os` | テキスト出力の改行コード（`os`=実行環境標準 / `lf`=LF / `crlf`=CRLF） |
| `--no-epub` | — | ePub 出力を省略し、テキストのみ出力 |
| `--cover-bg COLOR` | サイト依存 | 表紙背景色（`#RRGGBB` 形式） |
| `--from-file FILE` | — | ローカルテキストから ePub3 を生成 |
| `--from-epub FILE` | — | ローカル ePub3 から青空文庫書式テキストを生成 |
| `--append FILE` | — | 既存 `.txt` を指定して続きを追記・ePub 再生成。`底本URL：` から URL を自動検出し `--resume 0` と同等の差分ダウンロードを実行する。URL 指定不要。新規エピソードがない場合は既存ファイルを上書きしない |
| `--list-only` | — | ダウンロードせずエピソード一覧と話数のみ表示して終了する |
| `--check-update FILE` | — | 既存 `.txt` を渡してサイトの最新話数と比較し、新着話数・タイトルを表示して終了。ダウンロード・ファイル上書きは一切行わない。`--append` の前の確認に使う |
| `--dry-run` | — | 作品情報（タイトル・著者・総話数）を取得して表示したあと終了する。ダウンロード・ファイル出力は一切行わない。`--list-only` より軽量な接続確認用 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--cover-image FILE` | — | 表紙に使用するローカル画像ファイル（JPEG/PNG）。指定するとPillowによる自動生成表紙の代わりに使用される。ファイルが存在しない・非対応形式の場合は自動生成にフォールバック |
| `--use-site-cover` | — | 作品ページの公式サムネイル画像（`og:image`）を表紙として使用する。一時ファイルに保存して `build_epub` に渡し、終了後に自動削除。`--cover-image` が指定されている場合は `--cover-image` が優先 |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）。`body` のデフォルトフォントとして CSS に設定される。ファイルが存在しない場合は警告を出して埋め込みなしで続行 |
| `--toc-at-end` | — | 目次ページを奥付の後（末尾）に配置する。デフォルトは表紙の直後・本文の前 |
| `--output-dir DIR` | カレントディレクトリ | 出力先ディレクトリを指定する。存在しない場合は自動作成。ファイル名は従来通りタイトルから自動生成（`-o` と併用可） |
| `--kobo` | — | 楽天 Kobo 専用端末（Kobo Clara / Kobo Sage 等）向けに ePub の拡張子を `.kepub.epub` にする。内部的には `_epub_ext(args)` ヘルパーが拡張子を切り替える |

## 依存ライブラリ

| ライブラリ | 用途 | インストール |
|---|---|---|
| `requests`, `beautifulsoup4` | カクヨム・アルファポリス・エブリスタ・野いちご・ハーメルン・ノベマ！・ノベルアップ＋・ステキブンゲイ・NOVEL DAYS・プロジェクト杉田玄白・結城浩翻訳の部屋・ネオページ・ソリスピア・berry's cafe | `pip install requests beautifulsoup4` |
| `requests` （のみ） | monogatary.com（REST API、BS4 不要） | `pip install requests` |
| `playwright` | ハーメルン（Cloudflare 回避） | `pip install playwright && python -m playwright install chromium` |
| `Pillow` | JPEG 表紙生成 | `pip install Pillow` または `sudo apt install python3-pillow` |
| fonts-noto-cjk | JPG 表紙の日本語フォント | `sudo apt install fonts-noto-cjk` |

すべてオプション扱いでフォールバックあり（なろうは stdlib のみで動作、Pillow 未インストール時は SVG 表紙で代替）。

## アーキテクチャ

すべて 1 ファイルに集約されており、`# ══════` で区切られたセクションで構成される：

1. **共通ユーティリティ**（行 ~148–）：`normalize_tate`、`aozora_header/colophon/chapter_title`、`safe_filename`、`_apply_output_dir`、`write_file` — 青空文庫書式テキストの共通処理。`_apply_output_dir` は `--output-dir` を全 `run_*` 関数に横断適用するヘルパー。`_show_episode_list` は `--list-only` / `--check-update` 用（`_CHECK_UPDATE_MODE` フラグが立っているときは `_CheckUpdateDone` 例外を送出してエピソードリストを呼び出し元に返す）。`_dry_run_exit(args)` は `--dry-run` 指定時にメッセージを表示して `sys.exit(0)` する（全 `run_*` 関数の `list_only` チェック直後に配置）。`_load_existing_txt(txt_path)` は既存 `.txt` から sections と epub_episodes を復元し `_apply_resume(args, txt_path, target_eps)` が resume ロジックをカプセル化（全 run_* 関数から呼ばれる）。`_extract_url_from_txt(txt_path)` はヘッダーの「底本URL：」行または奥付 URL から元 URL を取得し `--append` / `--check-update` モードで使用する。`_fetch_ogp_cover(page_url)` は `og:image` を一時ファイルにダウンロードして返す（`--use-site-cover` 用、`main()` のディスパッチ直前に呼ばれ finally で削除）。ルビ関連ユーティリティ（`_resolve_ruby_base`、`_ruby_needs_pipe`、`_bs4_prev_text`）もこのセクションに集約。

2. **ePub3 ビルダー**（行 ~436–1981）：stdlib の `zipfile` で ZIP を直接生成。DPFJガイド v1.1.4 準拠で `<html class="vrtl">` / `<html class="hltr">` による組み方向制御を採用（縦組み: ep*.xhtml・cover.xhtml・nav.xhtml、横組み: cover-image.xhtml・colophon.xhtml）。主要関数：
   - `_char_class`（行 659）— 文字の種別（0=漢字・1=ひらがな等）を返す。`々仝〆〇ヶ` は青空文庫規定で漢字（0）扱い
   - `_apply_ruby_auto`（行 798）— 直前の漢字からルビ親文字を自動検出
   - `_jisage_to_int`（行 886）— 全角数字・漢数字の字下げ量を int に変換
   - `_body_lines_to_xhtml`（行 897）— 青空文庫本文を XHTML に変換。見出しタグ（大/中/小見出し）を `midashi-oo`/`midashi-naka`/`midashi-sho` クラスの `<p>` に変換。字下げタグ（`［＃N字下げ］`・`［＃ここからN字下げ］`・`［＃ここから改行天付き、折り返してN字下げ］`）をブロック/単行/ぶら下げインデントの CSS クラスに変換。図タグ（`の図`・`のキャプション付きの図`・`はキャプション`・`ここからキャプション`）を `<figure>/<img>/<figcaption>` に変換
   - `make_cover_image`（行 1700）— JPEG 表紙を生成（Pillow、quality=90）、なければ SVG にフォールバック
   - `_make_nav_xhtml`（行 1207）— ナビゲーションドキュメントを生成。`episodes` は `list[str]` または `list[dict{"title", "body", "group"?}]` を受け付ける。`group` が設定されたエピソードが新しいグループに切り替わる直前に `<li class="toc-chapter"><a href="ep{n:04d}.xhtml">グループ名</a></li>` を挿入する（フラット構造：ネスト `<ol>` は使わず全エピソードを同一インデントレベルに配置。**注意**: ePub3 nav の `<li>` は `<a>` か `<span>+<ol>` のみ許可。`<span>` 単独は epubcheck RSC-005 エラーになり Send to Kindle も失敗するため、章ヘッダーはその章の先頭エピソードへの `<a>` リンクとする）
   - `_make_opf`（行 ~1300）— `package.opf` を生成。`synopsis` パラメータを受け取り `<dc:description>` に設定（非空時のみ出力）。`<dc:creator id="creator">` に `<meta refines="#creator" property="role" scheme="marc:relators">aut</meta>` を付与（著者ロール明示）。`dcterms:modified` は `datetime.now(timezone.utc)` で実時刻の ISO 8601 形式（以前は `T00:00:00Z` 固定）
   - `build_epub`（行 ~1868）— XHTML / CSS / OPF を ZIP にまとめて ePub を組み立てる。`images: dict` パラメータで青空文庫 ZIP 内画像を `OEBPS/images/` に埋め込み可能。`synopsis` は `_make_opf` に渡され `dc:description` へ

3. **なろうスクレイパー**（行 ~1982–2560）：stdlib `urllib` と独自 `HTMLParser` サブクラス（`NarouInfoParser`、`NarouEpisodeListParser`、`NarouEpisodeParser`）を使用。`NarouEpisodeListParser` は `div.p-eplist__chapter-title` を検知して `_current_chapter` を更新し、各エピソードに章名を付与する（`[(path, title, chapter), ...]`）。`narou_get_all_episodes` は複数ページ取得時に前ページ末尾の `_current_chapter` を次ページのパーサーに引き継ぐ（ページ境界での章情報欠落を防止）。エントリポイント：`run_narou`（行 2404）。

4. **カクヨムスクレイパー**（行 ~2561–2993）：`requests` + `BeautifulSoup` を使用。`__NEXT_DATA__` の `__APOLLO_STATE__` から `work.tableOfContents` → `TableOfContentsChapter:` → `chapter.__ref` → `Chapter:` → `title` のパスで章名を取得し、各エピソードに `"chapter"` フィールドとして付与する（旧形式 `work.episodeUnions` はフォールバック）。エピソードページの HTML から章名が取得できない場合は `kky_get_episode_urls` で取得した章名をフォールバックとして使用。エントリポイント：`run_kakuyomu`（行 2878）。

5. **アルファポリススクレイパー**（行 ~2994–3315）：`requests` + `BeautifulSoup` を使用。エピソード一覧は `script[type="application/json"]` 内の `chapterEpisodes` JSON から取得（`{url, mainTitle, subTitle, isPublic}` 形式）。旧形式の `div.episodes > div.episode` はフォールバックとして残存。本文取得はセッション Cookie 有無でサーバーのレスポンスが変わる：Cookie あり → 本文が `div#novelBody` に直接埋め込み、Cookie なし → JS の `.load()` で `/novel/episode_body` に AJAX POST。エントリポイント：`run_alphapolis`（行 3228）。

6. **エブリスタスクレイパー**（行 ~3316–3589）：`requests` + `BeautifulSoup` を使用。ビューアページ（`/novels/{id}/viewer?page=N`）の `window.__NUXT__` に 15 件ずつ本文が `novelPageId:"NNN",body:"..."` 形式で埋め込まれる。page=1, 16, 31, … と 15 ページ刻みでバッチ取得。`_est_parse_nuxt_vars()` で IIFE 引数リストを解析して変数名→整数のマッピング（例: `g=1`）を構築し、`pageNo:g` のような変数参照を解決する。エピソード開始ページは `title:"..."` フィールドが存在し、`est_parse_episode_titles()` で抽出。連続ページは `タイトル（2）` 形式で採番。エントリポイント：`run_estar`（行 3462）。

7. **ハーメルンスクレイパー**（行 ~3590–3843）：`playwright` + `BeautifulSoup` を使用。トップページは `requests` で取得（CF保護なし）。エピソードページは Cloudflare Managed Challenge があるため、Playwright で各話ごとに新しい browser context を作成し 5 秒待機して取得。本文は `div#honbun`、前書きは `div#maegaki`、後書きは `div#atogaki`。エントリポイント：`run_hameln`（行 3689）。

8. **ネオページスクレイパー**（行 ~3844–4154）：`requests` + `BeautifulSoup` を使用（playwright 不要）。作品ページ（`/book/{id}`）は Next.js RSC 形式（`self.__next_f.push([1,"KEY:JSON\n"])`）。`_neopage_parse_next_f()`（行 3877）でペイロードを展開し `_neopage_find_book_obj()`（行 3906）で `book_id` 一致オブジェクトを再帰探索。キー: `name`（タイトル）、`author.author_name`（著者）、`intro`（あらすじ）、`first_chapter_id`（初章）、`total_chapter`（総話数）。章本文は `/v1/book/content/{chapter_id}` REST API から直接取得（`data.content` に `<p>` タグ形式HTML、`data.next.chapter_id` でチェーン辿り）。`neopage_content_to_aozora()` で `<p>` タグを青空文庫書式に変換。有料章は `content: null` → "（有料章または非公開）" と出力。チェーン探索中は 0.3 秒間隔（本文取得は `--delay` に従う）。**巻構成**：`neopage_fetch_chapter` の戻り値 `volume_name` キーで取得（各巻の先頭話にのみ設定される）。`run_neopage` の chain ループで `current_volume` 変数に引き継ぎ、各エピソードの `"group"` として ePub 目次に反映。エントリポイント：`run_neopage`（行 4029）。

9. **ソリスピアスクレイパー**（行 ~4155–4394）：`requests` + `BeautifulSoup` を使用。作品トップページ（`/title/{id}`）から `h1.text-title`（タイトル）、`a.main-user-underline`（著者）、`div.summary`（あらすじ）を取得。エピソード一覧は `div.chapters > details.chapter-group` を走査して章グループ名（`summary.chapter-summary > span.chapter-title`）とエピソード（`div.chapter-episodes > div.row-list > dt > a.row-link`）を抽出し `(url, title, chapter_name)` 3-tuple で返す。章グループなし作品はフォールバック（flat、`chapter_name=""`）。本文は `div#novelContent` 内の最深ネスト div に直接 text node + `<br>` タグが交互に配置される構造（`<p>` タグなし）。`_solispia_deepest_text_div()` で最深 div を探索し、`<br>` 2 連続以上を段落区切りとして青空文庫書式に変換。`/novel/{id}` 形式の URL は内部で `/title/{id}` へ正規化（エピソードページのリンクを辿る）。エントリポイント：`run_solispia`（行 4285）。

10. **野いちごスクレイパー**（行 ~4395–4637）：`requests` + `BeautifulSoup` を使用。`noichigo_get_chapter_list()` が `div.bookChapterList` の2階層 `<ul>` を走査して `(page_num, title, group_name)` 3-tuple リストを返す（外側 `<li>` が章グループ、内側 `<li>` が個別ページ）。章グループ名は `run_noichigo` の `chapter_ranges`（4-tuple: `page_start, page_end, title, group_name`）に引き継がれ、各エピソードの `"group"` として ePub 目次に反映。`--start`/`--end` は章番号で指定。エントリポイント：`run_noichigo`（行 4501）。

11. **berry's cafe スクレイパー**（行 ~4638–4833）：野いちごと同会社のサービス。`requests` + `BeautifulSoup` を使用。作品トップページ（`/book/{id}`）から `div.title-wrap div.title h2`（タイトル）、`div.subDetails-02 div.name a`（著者）、`div.bookSummary-01`（あらすじ）、`div.bookInfo dd` 内の `\d+ページ`（総ページ数）を取得。エピソード一覧は `div.bookChapterList`（野いちごと同構造）から `noichigo_get_chapter_list()` を共用し `group_name` も取得。各チャプターは複数ページをまとめた範囲で構成される（`/book/{id}/{page_num}` 形式）。本文は `div.bookContent div.bookBody`（`<br>` 区切り）で `noichigo_html_to_aozora()` を共用。総ページ数が取得できない場合は 1 ページ目の `og:title` の `(1/N)` 形式から取得。エントリポイント：`run_berrys`（行 4702）。

12. **monogatary.com スクレイパー**（行 ~4834–5039）：`requests` のみ使用（Playwright 不要、BeautifulSoup 不要）。公開 REST API を使用。`/api/episode/{id}` → `episodeContents.storyId`・`storyTitle`・`userName`・`episode`（本文テキスト）、`/api/story/{id}` → `episodes[]`（`{episodeId, episodeTitle}` 配列）。`/episode/{id}` または `/story/{id}` どちらの URL でも動作する（`/episode/` 形式の場合は API で storyId を解決）。あらすじはストーリーページ HTML の `og:description` を regex で抽出（React SPA のため BeautifulSoup 不要）。本文は `\n` 区切りのプレーンテキストを `monogatary_text_to_aozora()` で青空文庫書式に変換。エントリポイント：`run_monogatary`（行 4894）。

13. **ノベマ！スクレイパー**（行 ~5040–5246）：`requests` + `BeautifulSoup` を使用。野いちごと同構造。`novema_get_episode_list()` が `div.bookChapterList` の2階層 `<ul>` を走査して `(page_num, title, chapter_name)` 3-tuple リストを返す。外側 `<li>` の直下 `<a>` タグから章名を取得（`<p>` タグではなく `<a>` タグに章名が入る仕様）。章グループなし作品は `chapter_name=""` で返す。各エピソードの `"group"` フィールドに章名を設定して ePub 目次に反映。各ページ（`/book/{work_id}/{page_num}`）を個別フェッチ。本文は `article.bookText > div`、`<br>` 区切り。`noichigo_html_to_aozora` を共用。エントリポイント：`run_novema`（行 5142）。

14. **ノベルアップ＋スクレイパー**（行 ~5247–5472）：`requests` + `BeautifulSoup` を使用。サーバーレンダリングで JS 不要。og:title から「タイトル（著者名）」形式で情報取得。`div.episodeList` 内の `a.episodeTitle` リンクからエピソード一覧取得。本文は `p#episode_content`（`\n` 区切り）、前書きは `div.novel_foreword`、後書きは `div.novel_afterword`。Ruby は `<rb>/<rt>` 形式。エントリポイント：`run_novelup`（行 5379）。

15. **ステキブンゲイスクレイパー**（行 ~5473–5686）：`requests` + `BeautifulSoup` を使用。Nuxt.js SSR で JS 不要。タイトルは og:title（" - ステキブンゲイ" サフィックスを除去）、あらすじは og:description、著者は `/users/` へのリンクテキスト（フォールバック: `window.__NUXT__` の `"name":"..."` パターン）。エピソード一覧は `a[href^="/novels/{uuid}/{uuid}"]` リンク。本文は `div#episodeBody`（`\n` 区切り）。Ruby は `<rb>/<rt>` 形式。エントリポイント：`run_sutekibungei`（行 5596）。

16. **NOVEL DAYS スクレイパー**（行 ~5687–5921）：`requests` + `BeautifulSoup` を使用。SSR で JS 不要（講談社運営）。タイトルは `div.detail h2`、著者は `div.author a span.f18px`、あらすじは `p.readmore`（`<br>` → 改行）。エピソード一覧は `div.contents ol li a[href*="/works/episode/"]`。本文は `div.episode div.inner`（`<br>` → 改行）。Ruby は `<rb>/<rt>/<rp>` 形式。エピソードURLが指定された場合は作品トップページリンクを自動検出。エントリポイント：`run_days`（行 5818）。

17. **プロジェクト杉田玄白スクレイパー**（行 ~5922–6191）：`requests` + `BeautifulSoup` を使用。単一 XHTML ファイルに全章が収録されるシンプルな構造。`<h1>` からタイトル、直後の `<div>` から原著者（"XXX 著" パターン）と訳者（`cruel.org` へのリンク or "翻訳:" テキスト）、原題（英語タイトル）を取得。`<h2>` を章区切りとして使用し、`<a name="toc">/<a id="toc">` を持つ `<h2>` は目次と判定してスキップ。フラグメントリンクのみの短い段落（「目次に戻る」等）もスキップ。`\ruby{base}{ruby}` テキスト記法を `|base《ruby》`（青空文庫ルビ記法）に変換。エントリポイント：`run_genpaku`（行 6118）。

18. **結城浩翻訳の部屋スクレイパー**（行 ~6192–6523）：`requests` + `BeautifulSoup` を使用。2種類のHTML設計に対応。**Bootstrap設計**（leaf・magi等、`div.jumbotron` あり）: `<h1>` からタイトル、jumbotron内 `<p>` から著者（"原作：XXX　翻訳：XXX" 形式）、`og:description` からあらすじを取得、`div.col-md-12` 内の `<p>` を 1 エピソードとして抽出（`div.panel` が現れたら終了）。**XHTML設計**（bedtime等、`div.titles` あり）: `<h1 class="title">` からタイトル、`<p class="author">` から著者（"XXX\\n結城浩訳" 形式）を取得、`<h2 class="section">` を章区切りとして使用、対訳テーブル（`<blockquote><table>`）は最初の `<td>`（日本語側）のみ抽出。`<a name/id="toc">` を持つ `<h2>` は目次と判定してスキップ。エントリポイント：`run_hyuki`（行 6448）。

19. **青空文庫スクレイパー**（行 ~6524–6839）：stdlib のみ（urllib + zipfile + re）で動作。旧サイト（`aozora.gr.jp`）・新サイト（`aozora-renewal.cloud`）の両方に対応。図書カードページからルビ付き ZIP（`_ruby_` 優先）の URL を抽出し、ZIP をダウンロード・展開。`aozora_download_extract`（行 6605）は画像ファイル（PNG/JPG/GIF等）も戻り値 `images` dict に含めて返す。テキストファイルはエンコーディングを自動判定（ShiftJIS → CP932 → UTF-8 → EUC-JP）して UTF-8 に変換して保存。ePub 生成時は `aozora_text_to_episodes()`（行 6697）でタイトル・著者を先頭2非空行から、本文を区切り線ブロック後・底本情報前から抽出し、`［＃改ページ］` と見出しタグ（`_split_aozora_by_headings`、行 6661）で章分割。`.txt` のファイル名は ZIP 内のファイル名、`.epub` のファイル名は `safe_filename(title)` に変更（Kindle ライブラリでの表示に対応）。テキストページURL（`/files/{id}_{num}.html`）を指定した場合は図書カードページ URL へ正規化。エントリポイント：`run_aozora`（行 6774）。

20. **ローカルファイルモード**（行 ~6840–7000）：`parse_aozora_text`（行 6844）で既存の青空文庫 `.txt` からタイトル・著者・あらすじを抽出し、`_split_aozora_by_headings` で見出し分割を行って `build_epub` に渡す。`_strip_heading_block`（行 6636）は各チャプター本文の先頭から見出しマークアップ行を除去する（ep-title として別途レンダリングされるため）。エントリポイント：`run_from_file`（行 6936）。

21. **ローカルePub3 → テキスト変換**（行 ~7001–7523）：stdlib のみ（`zipfile` + `re` + `html` + `zlib`）で動作。
   - `_ruby_to_aozora()`（行 7005）：標準形式・Kobo `<span>` 分割形式の両方に対応した `<ruby>` → `《》` 変換
   - `_epub_generic_to_text()`（行 7097）：汎用 XHTML の `<p>` タグを収集。`<br>` のみ改行扱い、それ以外のタグ内改行は HTML 的空白として正規化し日本語文字隣接スペースを除去
   - `_read_streaming_zip()`（行 7171）：中央ディレクトリなしのストリーミング ZIP（Kindle 配信 ePub 等）をローカルヘッダ走査で読み込む
   - `_ZipLike`（行 7282）：`zipfile.ZipFile` 互換ラッパー（`_read_streaming_zip` の戻り値をラップ）
   - `parse_epub()`（行 7301）：自ツール生成 ePub（`OEBPS/ep*.xhtml`）優先、汎用 spine フォールバック。nav ドキュメントから `{zip_path → chapter_title}` マップを構築し genuine_nav_count ≥ 2 で nav-only モードに移行（前付け・後付け除外）。`BadZipFile` 時は `_read_streaming_zip` にフォールバック
   - エントリポイント：`run_from_epub()`（行 7472）

22. **短縮URL展開**（行 ~7524–）：`_SHORT_URL_HOSTS`（30種以上）で短縮サービスを判定。`expand_short_url()` が最大5ホップのリダイレクト追跡を行う。各ホップで `_follow_one_redirect()`（HEAD→GETフォールバック、ブラウザ互換ヘッダー）→ `_unwrap_query_url()`（クエリパラメータへの実URL埋め込み展開）→ `_extract_url_from_html()`（meta refresh / window.location パース）の順で展開を試みる。`main()` 内で `detect_site()` の前に呼び出される。

23. **短縮URL展開・og:image取得**（行 ~7524–）：`_fetch_ogp_cover(page_url)` が `og:image` を一時ファイルにダウンロード（requests → urllib フォールバック）。`expand_short_url()` が短縮URL展開。

24. **`main()`**（行 ~8006–）：`_host_matches` でドメイン判定ヘルパー（スプーフィング対策）、`detect_site` でサイト判定、`normalize_url` で話数 URL → 作品トップ URL 正規化。引数解析後の処理順：`--append` → `--check-update` → `--use-site-cover`（og:image 取得）→ ディスパッチ（`try/except _CheckUpdateDone/finally`）。`--check-update` は `_CHECK_UPDATE_MODE = True` でディスパッチに乗せ、`_show_episode_list` が `_CheckUpdateDone` を送出したところでキャッチして差分を表示。`--use-site-cover` の一時ファイルは `finally` で削除。

## ePub3 内部構造

```
mimetype
META-INF/container.xml
OEBPS/package.opf
OEBPS/nav.xhtml              ← RS向け機械読み取り専用（spine に含めない、properties="nav"）
OEBPS/toc.xhtml              ← 読者向け縦組み目次ページ（spine に含める）
OEBPS/css/novel.css
OEBPS/css/vertical_image.css ← 画像表紙専用 CSS
OEBPS/fonts/                 ← 埋め込みフォント（--font 指定時のみ）
OEBPS/images/cover.jpg       ← 表紙画像（Pillow あり: JPEG、なし: SVG）
OEBPS/images/                ← 青空文庫 ZIP 内画像（aozora のみ）
OEBPS/cover-image.xhtml      ← 画像表紙ページ（epub:type="cover"、body に epub:type="cover"、img に epub:type="cover-image"）
OEBPS/cover.xhtml            ← タイトル・著者・あらすじページ
OEBPS/ep0001.xhtml           ← 各話（epub:type="chapter"）
OEBPS/ep0002.xhtml
...
OEBPS/colophon.xhtml         ← 奥付
```

spine 読み順（デフォルト）: cover-image → cover → **toc（目次）** → ep0001…epNNNN → colophon
`--toc-at-end` 指定時: cover-image → cover → ep0001…epNNNN → colophon → **toc（目次）**
nav.xhtml は spine に含めない（`properties="nav"` のみで RS が認識、DPFJガイド準拠）

DPFJガイド v1.1.4 準拠の組み方向制御：`<html class="vrtl/hltr">` で切り替え。

| ファイル | class | 組み方向 |
|---|---|---|
| cover-image.xhtml | `hltr` | 横組み（表紙画像ページ） |
| cover.xhtml | `vrtl` | 縦組み（タイトルページ） |
| nav.xhtml | `vrtl` | 縦組み（目次） |
| ep*.xhtml | `vrtl` | 縦組み（本文） |
| colophon.xhtml | `hltr` | 横組み（奥付） |

CSS は2層構造：(1) `html, body { writing-mode: vertical-rl }` — class 非対応環境（Amazon Kindle 等）向けフォールバック、(2) `html.vrtl / html.vrtl body` / `html.hltr / html.hltr body` — class 対応 RS 向け上書き。`_XHTML_TMPL` は `{html_class}` パラメータで class を切り替える（inline style は除去済み）。`body` の `font-family` も `html.vrtl body` / `html.hltr body` セレクタで分岐し、先頭に RS 仮想フォント名 `serif-ja-v`（縦組み）/ `serif-ja`（横組み）を付与（DPFJガイド準拠）。フォールバック `body { font-family: ... }` で class 非対応環境もカバー。`epub:type` は `epub:type="cover"` / `epub:type="cover-image"`（cover-image.xhtml）と nav の `epub:type="toc"` / `epub:type="landmarks"` のみ付与。本文 body・cover.xhtml・colophon.xhtml の `epub:type` は除去（DPFJガイド準拠）。

縦中横（`.tcy`）対応：
- 明示タグ `［＃縦中横］TEXT［＃縦中横終わり］` → `<span class="tcy">TEXT</span>`（センチネル2フェーズ変換で `_apply_ruby_auto` と干渉しない）
- 自動検出：`_auto_tcy_xhtml()` がテキストノード内の**1〜3桁の孤立数字**（前後に数字が隣接しない）を自動でラップ。4桁以上（年号等）は対象外。HTMLエンティティ（`&#160;` 等）は保護する（split パターンに `&#\d+;|&[a-zA-Z]+;` を含め `&` 始まりトークンは素通し）
- `page-spread-right` を cover-page の spine itemref に付与（日本語 RTL 書籍の表紙は右ページ）

各 XHTML に `epub:type` を付与。楽天 Kobo・iPad/iOS Kindle リーダー向け互換対応済み。

OPF `<metadata>` の主要フィールド：
- `<dc:creator id="creator">` + `<meta refines="#creator" property="role" scheme="marc:relators">aut</meta>`（著者ロール）
- `<dc:description>` — あらすじ（synopsis 非空時のみ出力）
- `<meta property="dcterms:modified">` — `datetime.now(timezone.utc)` による実時刻 ISO 8601（例: `2026-03-28T03:34:39Z`）
- `<meta name="primary-writing-mode" content="horizontal-rl"/>` — iPad/iOS Kindle 縦書き対応

目次は2ファイル構成：
- `toc.xhtml`（`_make_toc_xhtml()`）: 読者が読む縦組み目次ページ。spine に含まれ `_XHTML_TMPL` で生成（`class="vrtl"`）。`epub:type` なし。
- `nav.xhtml`（`_make_nav_xhtml()`）: RS向け機械読み取り専用（`properties="nav"`）。spine に含めない。landmarks の `epub:type="toc"` href は `toc.xhtml` を指す。

両ファイルとも `epub_episodes` の `"group"` フィールドが切り替わるたびに `<li class="toc-chapter"><a href="ep{n:04d}.xhtml">グループ名</a></li>` を挿入（フラット構造、ネスト `<ol>` なし）。

## 主な規約

- ルビ記法：テキスト内の `漢字《かんじ》` → XHTML では `<ruby>漢字<rt>かんじ</rt></ruby>`
- 改ページ：テキスト内の `［＃改ページ］` → XHTML では `epub:type="pagebreak"`
- ルビ自動判別：`《》` 内に漢字を含む**かつパイプなし**の場合は地の文として処理（ルビ誤変換を防止）。`|BASE《漢字》` 形式（明示パイプあり）は漢字ルビでも必ず `<ruby>` タグに変換する
- ルビ範囲確定：各スクレイパーは `|BASE《RUBY》` 形式（ASCII パイプ）で明示。`_ruby_needs_pipe(base, preceding, yomi)` で必要性を判定：(1) **yomi（ルビテキスト）に漢字が含まれる場合**（`《転生先》` 等の漢字ルビを確実にルビタグ化するため）、(2) base が複数文字種を含む場合、(3) 直前テキストの末尾が base と同じ文字種の場合、(4) **base の末尾文字がクラス9（記号・句読点）の場合**（`＆《アンド》` 等のシンボルルビ、`_apply_ruby_auto` の自動検出では地の文扱いになる恐れがあるためパイプで明示）。`_bs4_prev_text(tag)` で BS4 タグの直前テキストを取得。なろう HTMLParser では `"".join(self._cur_para)` を preceding、`self._rt_buf` を yomi として渡す。青空文庫テキスト内の `｜`（全角）は `_apply_ruby_auto` が直接認識するため除去しない（`aozora_text_to_episodes`）
- シンボルルビベース：`_apply_ruby_auto` の自動検出パス（パイプなし）では `_PUNCT_NO_RUBY_BASE` 定数（`。、！？…‥・「」『』（）【】〈〉《》：；―—–` 等）に含まれる文字のみをルビベース不可とする。`＆` `♪` `★` 等のシンボル文字はクラス9であっても有効なルビベースとして扱う
- 特殊記号の文字種：`々仝〆〇ヶ` は青空文庫規定により漢字（class 0）扱い。ルビ範囲判定（`_char_class`）に影響する
- 字下げタグ：`［＃N字下げ］`（単行）→ `text-indent: Nem`、`［＃ここからN字下げ］` → `div.aozora-indent-Nem`（縦書き `padding-top`）、`［＃ここから改行天付き、折り返してN字下げ］` → `div.aozora-hanging-Nem`（`padding-top` + 内側 `<p>` に `text-indent: -Nem`）
- 青空文庫図タグ：`「ファイル名」の図（ファイル名）入る` → `<figure><img></figure>`、キャプション付き → `<figcaption>` 付き。画像は `OEBPS/images/` に配置し、src は `images/filename`（`../images/` は誤り）
- 表紙背景色のデフォルト：なろう `#18b7cd`、カクヨム `#4BAAE0`、アルファポリス `#e05c2c`、エブリスタ `#00A0E9`、野いちご `#FA8296`、ハーメルン `#6E654C`、ノベマ！ `#595757`、ノベルアップ＋ `#0CBF97`、ステキブンゲイ `#E4097D`、NOVEL DAYS `#CBA13F`、青空文庫 `#000066`、プロジェクト杉田玄白 `#1D3461`、結城浩翻訳の部屋 `#2D6A4F`、ネオページ `#E94F37`、ソリスピア `#7C3AED`、berry's cafe `#C8245A`、monogatary.com `#231815`、ローカル `#16234b`
- リクエスト間隔デフォルト 1.5 秒、リトライ最大 3 回（間隔 5 秒）

## font/ ディレクトリ

`font/` に OFL ライセンスのフォントファイル（`AyatiShowaSerif-Regular.ttf`）を同梱。`--font font/AyatiShowaSerif-Regular.ttf` のように指定して ePub に埋め込める。

## forwindows/ ディレクトリ

Windows 向け補助スクリプト一式。Shift-JIS エンコード（PowerShell ブロックは ASCII のみ）。

| ファイル | 用途 |
|---|---|
| `clipnoveldwn.bat` | クリップボードの URL を即ダウンロード |
| `watcher.bat` | OneDrive 監視・自動ダウンロード（処理済みを `done\` フォルダへ移動） |
| `watcherG.bat` | Google Drive 監視・自動ダウンロード（同上） |
| `novel_downloader.exe` | 本体 exe（git 管理外） |

両 watcher は**バッチ＋PowerShell のポリグロットスクリプト**。バッチ部でファイル検知・ダウンロード実行、PowerShell 部でファイル内容から URL を抽出して返す。URL はファイル中どこにあっても（タイトル行・スペース後・文中など）最初に見つかった URL を採用。短縮 URL（`expand_short_url`）は `novel_downloader.py` 側で自動展開される。

## 動作確認

テストスイートは存在しないため、手動で動作確認する：

```bash
# 構文チェック（編集後は必ず実行）
python -m py_compile novel_downloader.py

# 接続・タイトル確認のみ（ファイル出力なし）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --dry-run

# なろう（stdlib のみ、追加ライブラリ不要）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --no-epub

# ローカルテキストから ePub 生成（出力済みの .txt を使い回せる）
python novel_downloader.py --from-file <出力済み.txt>

# ローカル ePub3 から青空文庫テキスト生成（逆変換）
python novel_downloader.py --from-epub <出力済み.epub>

# ePub 構造確認（zipfile として展開可能）
python -c "import zipfile; zipfile.ZipFile('<出力.epub>').extractall('/tmp/epub_check')"
```

> **注意**: `.gitignore` に `*.txt` と `*.epub` が含まれるため、ダウンロード結果の出力ファイルは git 管理対象外。Windows 向けセットアップ手順は `WINDOWS_SETUP.md` を参照。

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
