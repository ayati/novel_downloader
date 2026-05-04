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
| `--append FILE` | — | 既存 `.txt` を指定して続きを追記・ePub 再生成。`底本URL：` から URL を自動検出し `--resume 0` と同等の差分ダウンロードを実行する。URL 指定不要。新規エピソードがない場合は既存ファイルを上書きしない。`--notify webhook` 対応 |
| `--append-dir DIR` | — | ディレクトリ内の全 `.txt` を走査し、新着エピソードがある作品だけ差分ダウンロード・追記・ePub 再生成する。Phase 1 で事前チェック → 確認プロンプト → Phase 2 でダウンロード → サマリー表示。`--yes` で確認スキップ。`--notify webhook` 対応 |
| `--yes` | — | `--append-dir` の確認プロンプトをスキップする（自動化用） |
| `--list-only` | — | ダウンロードせずエピソード一覧と話数のみ表示して終了する |
| `--check-update FILE` | — | 既存 `.txt` を渡してサイトの最新話数と比較し、新着話数・タイトルを表示して終了。ダウンロード・ファイル上書きは一切行わない。`--append` の前の確認に使う。`--notify webhook` 対応 |
| `--check-update-dir DIR` | — | ディレクトリ内の全 `.txt` を走査し、各作品の新着エピソードを一括確認する。底本URL のないファイルは自動スキップ。ダウンロード・ファイル上書きは一切行わない。`--notify webhook` 対応 |
| `--dry-run` | — | 作品情報（タイトル・著者・総話数）を取得して表示したあと終了する。ダウンロード・ファイル出力は一切行わない。`--list-only` より軽量な接続確認用 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--cover-image FILE` | — | 表紙に使用するローカル画像ファイル（JPEG/PNG）。指定するとPillowによる自動生成表紙の代わりに使用される。ファイルが存在しない・非対応形式の場合は自動生成にフォールバック |
| `--use-site-cover` | — | 作品ページの公式サムネイル画像（`og:image`）を表紙として使用する。一時ファイルに保存して `build_epub` に渡し、終了後に自動削除。`--cover-image` が指定されている場合は `--cover-image` が優先 |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf/.ttf/.woff/.woff2）。`body` のデフォルトフォントとして CSS に設定される。ファイルが存在しない場合は警告を出して埋め込みなしで続行 |
| `--toc-at-end` | — | 目次ページを奥付の後（末尾）に配置する。デフォルトは表紙の直後・本文の前 |
| `--output-dir DIR` | カレントディレクトリ | 出力先ディレクトリを指定する。存在しない場合は自動作成。ファイル名は従来通りタイトルから自動生成（`-o` と併用可） |
| `--kobo` | — | 楽天 Kobo 専用端末（Kobo Clara / Kobo Sage 等）向けに ePub の拡張子を `.kepub.epub` にする。内部的には `_epub_ext(args)` ヘルパーが拡張子を切り替える |
| `--horizontal` | — | 横書き ePub3 を生成する。全ページを `html.hltr`（横組み）で出力。縦中横（tcy）処理をスキップ、`page-progression-direction="ltr"`、`primary-writing-mode` 省略、cover の `page-spread-right` 除去。字下げ CSS は `html.hltr` スコープで `padding-left` を使用（縦書き時の `padding-top` を上書き） |
| `--watch FILE` | — | ウォッチリストファイル（URLリスト）を読んで新着を一括チェックする。新着があれば通知し、`auto=true` のエントリは自動 DL する。初回は全話数をキャッシュに登録するだけで通知しない |
| `--notify {stdout,webhook}` | `stdout` | 通知方法。`stdout`: 標準出力（cron フレンドリー、新着なし・エラーなし時は無音）。`webhook`: `--webhook-url` 宛に POST。**通常 URL ダウンロード**（完了時に「全N話ダウンロード完了」通知）・`--watch` / `--append` / `--append-dir` / `--check-update` / `--check-update-dir` で有効。エラー時も通知 |
| `--webhook-url URL` | — | Webhook 送信先（`--notify webhook` 時必須）。Discord / Slack の Incoming Webhook URL |
| `--webhook-format {discord,slack}` | `discord` | Webhook ペイロード形式。`discord`: `{"content":"..."}` / `slack`: `{"text":"..."}` |
| `--watch-cache FILE` | `.novel_watch_cache.json` | ウォッチキャッシュファイルのパス（アトミック書き込み・エントリ単位で即時更新） |
| `--watch-auto-default` | — | ウォッチリストで `auto=` 未指定のエントリに自動 DL を適用する |

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

すべて `novel_downloader.py` 1 ファイルに集約されており、`# ══════` で区切られたセクションで構成される：

1. **共通ユーティリティ** — 青空文庫書式テキストの共通処理（`normalize_tate`、`aozora_header/colophon/chapter_title`、`safe_filename`）。`_apply_output_dir` は `--output-dir` を全 `run_*` 関数に横断適用するヘルパー。`_show_episode_list` は `--list-only` / `--check-update` 用（`_CHECK_UPDATE_MODE` フラグが立っているときは `_CheckUpdateDone` 例外を送出してエピソードリストを呼び出し元に返す）。`_dry_run_exit(args)` は `--dry-run` 指定時にメッセージを表示して `sys.exit(0)` する。`_load_existing_txt` / `_apply_resume` が resume ロジックをカプセル化。`_extract_url_from_txt` はヘッダーの「底本URL：」行から元 URL を取得し `--append` / `--check-update` モードで使用する。ルビ関連ユーティリティ（`_resolve_ruby_base`、`_ruby_needs_pipe`、`_bs4_prev_text`）もこのセクションに集約。

2. **ePub3 ビルダー** — stdlib の `zipfile` で ZIP を直接生成。DPFJガイド v1.1.4 準拠で `<html class="vrtl">` / `<html class="hltr">` による組み方向制御を採用。主要関数：
   - `_char_class` — 文字の種別（0=漢字・1=ひらがな等）を返す。`々仝〆〇ヶ` は青空文庫規定で漢字（0）扱い
   - `_apply_ruby_auto` — 直前の漢字からルビ親文字を自動検出
   - `_body_lines_to_xhtml` — 青空文庫本文を XHTML に変換。見出しタグ・字下げタグ・図タグを処理。冒頭で `_apply_tcy_pre` を呼び青空文庫縦中横タグをセンチネルに変換、末尾で `_auto_tcy_xhtml(_apply_tcy_post(r))` で数字・英字の自動縦中横ラップ
   - `make_cover_image` — JPEG 表紙を生成（Pillow、quality=90）、なければ SVG にフォールバック
   - `_make_toc_xhtml` — 読者向け縦組み目次ページ（toc.xhtml）を生成。`class="vrtl"`・`epub:type` なし
   - `_make_nav_xhtml` — RS向け機械読み取り専用ナビゲーションドキュメント（nav.xhtml）を生成。spine に含めない。`<li>` は必ず `<a>` を含む（`<span>` 単独は ePub3 nav 仕様違反・epubcheck RSC-005 エラー）
   - `_make_opf` — `package.opf` を生成。`<dc:creator>` に marc:relators `aut` ロール付与。cover-page spine itemref に `page-spread-right` 付与（日本語 RTL 書籍の表紙は右ページ）
   - `build_epub` — XHTML / CSS / OPF を ZIP にまとめて ePub を組み立てる。`images: dict` パラメータで青空文庫 ZIP 内画像を `OEBPS/images/` に埋め込み可能

3. **スクレイパー群**（なろう・カクヨム・アルファポリス・エブリスタ・ハーメルン・ネオページ・ソリスピア・野いちご・berry's cafe・monogatary.com・ノベマ！・ノベルアップ＋・ステキブンゲイ・NOVEL DAYS・プロジェクト杉田玄白・結城浩翻訳の部屋・青空文庫）— 各サイトの `run_サイト名(args)` 関数がエントリポイント。**共通パターン**：`aozora_header()` でヘッダー組み立て → エピソードごとに `aozora_chapter_title()` + 本文取得 → `aozora_colophon()` で奥付 → `write_file()` でテキスト保存 → `build_epub()` で ePub 生成。`_apply_resume` / `_apply_output_dir` / `_dry_run_exit` / `_show_episode_list` を最初に呼ぶ（全スクレイパー共通）。各エピソードは `{"title": str, "body": str, "group": str}` 形式で `epub_episodes` リストに追加する。

4. **ローカルファイルモード** — `run_from_file`（`--from-file`）は `parse_aozora_text` で既存テキストからタイトル・著者・あらすじを抽出。`run_from_epub`（`--from-epub`）は ePub3 → 青空文庫テキスト逆変換（`parse_epub`）。

5. **短縮URL展開・og:image取得** — `_SHORT_URL_HOSTS`（30種以上）で短縮サービスを判定。`expand_short_url()` が最大5ホップのリダイレクト追跡。`main()` 内で `detect_site()` の前に呼び出される。

6. **青空文庫外字注記の Unicode 変換** — `aozora_resolve_gaiji(text)` が ZIP デコード直後のテキストに対して `※［＃「説明」、識別子］` 形式の外字注記を解決する。対応識別子は `U+XXXX`（Unicode 直接指定）、`第3水準1-X-Y` / `第4水準2-X-Y`（JIS X 0213 プレフィックス付き）、素の `P-R-C`（プレフィックス省略形、P=1 or 2）の4形式。JIS X 0213 系は `data/aozora_gaiji_jis0213.tsv`（11,233 エントリ、x0213.org 由来、`tools/build_gaiji_table.py` で再生成可）を遅延ロード。`_extract_gaiji_identifier` は注記内部を `、` で分割して走査し、最初に解決可能な識別子にマッチする要素を採用するため、複合説明（説明部に `、` を含む山月記の `※［＃「口＋皐」の「白」に代えて「自」、第4水準2-4-33］`）や併記形（放浪記の `※［＃「さんずい＋垂」、U+6DB6、235-7］`）にも対応する。Unicode 解決不能な注記（Unicode 未収録字形・UCV・78字形・ページ-行のみ等）は `_extract_gaiji_description()` で説明部のみ抽出して `※（説明）` 形式へフォールバック（ドグラ・マグラの `※［＃感嘆符三つ、626-10］` → `※（感嘆符三つ）`）。フォールバック件数は ℹ・原文保持件数は ⚠ で stderr へ集約レポート。

7. **サイトディスパッチテーブル `_SITE_DISPATCH`** — `{サイトID: (表示名, デフォルト表紙色, run_関数)}` の辞書。`main()` のサイト判定・表紙色設定・ディスパッチで参照。`_check_update_one()` でも使用。

8. **`_check_update_one(txt_path, delay)`** — 1ファイルの更新チェックを実行し結果辞書を返す。`--check-update-dir` / `--append-dir` の Phase 1 で使用。`_extract_url_from_txt` → `expand_short_url` → `detect_site` → `normalize_url` → `_SITE_DISPATCH` 参照でディスパッチ。`_CHECK_UPDATE_MODE = True` で `_CheckUpdateDone` 例外をキャッチして新着話数を算出。

9. **`_append_one(txt_path, base_args)`** — 1ファイルの追記処理を実行し結果辞書を返す。`--append-dir` の Phase 2 で使用。`--append` と同等の args を内部で組み立て、`_SITE_DISPATCH` で `run_*` を呼び出す。追記前後の話数差分で追加話数を算出。

10. **ウォッチモード** — `--watch` で `run_watch()` に early dispatch。関連関数：
   - `_parse_watch_list` — `list.txt` を `[{url, title, auto}]` にパース（`#` コメント・`|` 区切り対応）
   - `_load_watch_cache` / `_save_watch_cache` — `.novel_watch_cache.json` の読み書き（`_save_watch_cache` は `tempfile.mkstemp` + `os.replace` でアトミック書き込み）
   - `_check_update_url` — URL 直接指定でエピソード数をチェック（`_check_update_one` の .txt ファイルなし版。ランナーの stdout を `contextlib.redirect_stdout` で抑制）。`n_cached=0` 時は `status="init"` を返す
   - `_find_txt_by_url` — `output_dir` 内の `.txt` から `底本URL：` で URL 照合し、自動 DL 先のファイルパスを特定する
   - `_notify_stdout` — 新着・エラーのみ出力（新着なし・エラーなしなら無音）
   - `_notify_webhook` — 新着エントリをまとめて 1 回 POST。`fmt="discord"` → `{"content":"..."}` / `fmt="slack"` → `{"text":"..."}`
   - `run_watch` — list.txt を走査 → `_check_update_url` → 通知収集 → `auto=true` 時に `_append_one`（既存 .txt あり）または `run_*` 新規 DL → キャッシュ保存 → `_notify_stdout` / `_notify_webhook`

11. **`main()`** — `_host_matches` でドメイン判定（スプーフィング対策）、`detect_site` でサイト判定、`normalize_url` で話数 URL → 作品トップ URL 正規化。引数解析後の処理順：`--watch`（ウォッチモード）→ `--check-update-dir`（一括チェック）→ `--append-dir`（一括追記: Phase 1 事前チェック → 確認プロンプト → Phase 2 ダウンロード → サマリー）→ `--from-epub` / `--from-file` → `--append` → `--check-update` → `--use-site-cover`（og:image 取得）→ `_SITE_DISPATCH` によるディスパッチ（`try/except _CheckUpdateDone/finally`）。

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
OEBPS/cover-image.xhtml      ← 画像表紙ページ（epub:type="cover"）
OEBPS/cover.xhtml            ← タイトル・著者・あらすじページ
OEBPS/ep0001.xhtml           ← 各話
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
| toc.xhtml | `vrtl` | 縦組み（読者向け目次） |
| colophon.xhtml | `vrtl` | 縦組み（奥付） |

CSS は2層構造：(1) `html, body { writing-mode: vertical-rl }` — class 非対応環境（Amazon Kindle 等）向けフォールバック、(2) `html.vrtl / html.vrtl body` / `html.hltr / html.hltr body` — class 対応 RS 向け上書き。`body` の `font-family` も `html.vrtl body` / `html.hltr body` セレクタで分岐し、先頭に RS 仮想フォント名 `serif-ja-v`（縦組み）/ `serif-ja`（横組み）を付与（DPFJガイド準拠）。

目次は2ファイル構成：
- `toc.xhtml`（`_make_toc_xhtml()`）: 読者が読む縦組み目次ページ。spine に含まれる。`epub:type` なし。
- `nav.xhtml`（`_make_nav_xhtml()`）: RS向け機械読み取り専用（`properties="nav"`）。spine に含めない。landmarks の `epub:type="toc"` href は `toc.xhtml` を指す。

両ファイルとも `epub_episodes` の `"group"` フィールドが切り替わるたびに `<li class="toc-chapter">` を挿入（フラット構造、ネスト `<ol>` なし）。

縦中横（`.tcy`）対応：
- 明示タグ `［＃縦中横］TEXT［＃縦中横終わり］` → `<span class="tcy">TEXT</span>`（センチネル2フェーズ変換で `_apply_ruby_auto` と干渉しない）
- 自動検出：`_auto_tcy_xhtml()` がテキストノード内の**1〜3桁の孤立数字**および**1〜3文字の孤立半角英字**を自動でラップ。4桁以上・4文字以上は対象外。

`epub:type` は `epub:type="cover"` / `epub:type="cover-image"`（cover-image.xhtml）と nav の `epub:type="toc"` / `epub:type="landmarks"` のみ付与。本文 body・cover.xhtml・colophon.xhtml の `epub:type` は除去（DPFJガイド準拠）。

## 主な規約

- **ルビ記法**：テキスト内の `漢字《かんじ》` → XHTML では `<ruby>漢字<rt>かんじ</rt></ruby>`
- **改ページ**：テキスト内の `［＃改ページ］` → XHTML では `epub:type="pagebreak"`
- **ルビ自動判別**：`《》` 内に漢字を含む**かつパイプなし**の場合は地の文として処理（ルビ誤変換を防止）。`|BASE《漢字》` 形式（明示パイプあり）は漢字ルビでも必ず `<ruby>` タグに変換する
- **ルビ範囲確定**：各スクレイパーは `|BASE《RUBY》` 形式（ASCII パイプ）で明示。`_ruby_needs_pipe` で必要性を判定：(1) yomi に漢字が含まれる場合、(2) base が複数文字種を含む場合、(3) 直前テキスト末尾が base と同じ文字種の場合、(4) base 末尾文字がクラス9（記号・句読点）の場合。青空文庫テキスト内の `｜`（全角）は `_apply_ruby_auto` が直接認識するため除去しない
- **特殊記号の文字種**：`々仝〆〇ヶ` は青空文庫規定により漢字（class 0）扱い。ルビ範囲判定（`_char_class`）に影響する
- **字下げタグ**：`［＃N字下げ］`（単行）→ `text-indent: Nem`、`［＃ここからN字下げ］` → `div.aozora-indent-Nem`（縦書き `padding-top`）、`［＃ここから改行天付き、折り返してN字下げ］` → `div.aozora-hanging-Nem`
- **青空文庫図タグ**：`「ファイル名」の図（ファイル名）入る` → `<figure><img></figure>`。画像は `OEBPS/images/` に配置し、src は `images/filename`（`../images/` は誤り）
- **青空文庫外字注記**：`※［＃「説明」、識別子］` を `aozora_resolve_gaiji()` で Unicode 文字に置換。識別子は `U+XXXX` / `第3水準1-X-Y` / `第4水準2-X-Y` / 素の `P-R-C`（プレフィックス省略形、P=1 or 2）の4形式（JIS X 0213）。マッピング表は `data/aozora_gaiji_jis0213.tsv`（11,233 エントリ、`tools/build_gaiji_table.py` で再生成）。`U+XXXX、ページ-行` のような併記形にも対応するため、`、` で区切られた要素を順に走査し最初の解決可能な識別子を採用。複合説明（説明部に `、` を含む）にも対応。**Unicode 解決不能ケース**（Unicode 未収録字形・UCV・78字形・ページ-行のみ等）は `_extract_gaiji_description()` で説明部だけ抜き取り `※（説明）` 形式へフォールバック（例: `※［＃感嘆符三つ、626-10］` → `※（感嘆符三つ）`）。フォールバック適用件数は ℹ で stderr 集約レポート、説明も取得できないレアケースのみ ⚠ で原文保持
- **表紙背景色のデフォルト**：なろう `#18b7cd`、カクヨム `#4BAAE0`、アルファポリス `#e05c2c`、エブリスタ `#00A0E9`、野いちご `#FA8296`、ハーメルン `#6E654C`、ノベマ！ `#595757`、ノベルアップ＋ `#0CBF97`、ステキブンゲイ `#E4097D`、NOVEL DAYS `#CBA13F`、青空文庫 `#000066`、プロジェクト杉田玄白 `#1D3461`、結城浩翻訳の部屋 `#2D6A4F`、ネオページ `#E94F37`、ソリスピア `#7C3AED`、berry's cafe `#C8245A`、monogatary.com `#231815`、ローカル `#16234b`
- **リクエスト間隔**：デフォルト 1.5 秒、リトライ最大 3 回（間隔 5 秒）

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

## ウォッチモード（--watch）

URLリストを定期チェックし、新着があれば通知・自動 DL する機能。cron と単発実行の両方に対応。

```bash
# 単発チェック（cron に登録して定期実行）
python novel_downloader.py --watch list.txt

# 自動 DL 有効・出力先指定
python novel_downloader.py --watch list.txt --watch-auto-default --output-dir ~/novels/

# Discord 通知
python novel_downloader.py --watch list.txt \
    --notify webhook --webhook-url https://discord.com/api/webhooks/xxx

# Slack 通知
python novel_downloader.py --watch list.txt \
    --notify webhook --webhook-url https://hooks.slack.com/services/xxx \
    --webhook-format slack

# cron 例（6時間ごと）
# 0 */6 * * * cd /home/user/novels && python novel_downloader.py --watch list.txt \
#     --notify webhook --webhook-url https://discord.com/api/webhooks/xxx
```

**list.txt フォーマット:**
```
# コメント（行頭・行末どちらもOK）
https://ncode.syosetu.com/n1234ab/ | title=作品A | auto=true
https://kakuyomu.jp/works/xxxxx    | auto=false
https://syosetu.org/novel/123/     # auto= 未指定 → --watch-auto-default に従う
```

**`.novel_watch_cache.json` フォーマット:**
```json
{
  "https://ncode.syosetu.com/n1234ab/": {
    "title": "作品A",
    "last_episode": 123,
    "last_title": "第123話 タイトル",
    "last_checked": "2026-04-05T12:00:00",
    "output_file": "/home/user/novels/作品A.txt"
  }
}
```

- 初回実行時は全話数をキャッシュに登録するだけで通知・自動 DL しない（`[INIT]` 表示）
- 新着なし・エラーなしの場合は何も出力しない（cron メール不要）
- キャッシュはエントリ単位でアトミック書き込み（途中クラッシュ時の損失最小化）
- 終了コード: `0`=全正常、`1`=1件以上エラー

## ヘルスチェックツール（novel_health_check.py）

各サイトのスクレイピングが正常動作するか定期確認するツール。`--dry-run` をサブプロセスで実行し、タイトル・話数が取得できるかを検証する。テスト用 URL は `novel_health_check_urls.json` で管理。ログは `health_check_logs/` に保存される（git 管理外）。

```bash
python novel_health_check.py                           # 全サイトをチェック
python novel_health_check.py --site narou              # 特定サイトのみ
python novel_health_check.py --site narou estar        # 複数サイト指定
python novel_health_check.py --list-sites              # 設定済みサイト一覧
python novel_health_check.py --update-url narou <URL>  # テストURLを更新
python novel_health_check.py --timeout 120             # タイムアウト変更（デフォルト: 90秒）
python novel_health_check.py --delay 5                 # サイト間待機変更（デフォルト: 3秒）
python novel_health_check.py --log-dir /path/to/logs  # ログ出力先変更（デフォルト: health_check_logs/）
python novel_health_check.py --no-color                # カラー出力を無効化
```

終了コード: `0`=全成功、`1`=1件以上失敗、`2`=設定エラー。

`novel_health_check_urls.json` の形式（`url` が空文字列のサイトはスキップ）：
```json
{
  "サイトID": {
    "name": "表示名",
    "url": "テスト用作品URL",
    "note": "選定理由・代替URL等のメモ"
  }
}
```

新スクレイパーを追加したら `novel_health_check_urls.json` にもエントリを追加する。

## 新スクレイパー追加手順

1. `detect_site(url)` にサイト判定条件を追加（`return "サイト名"` 形式）
2. `run_サイト名(args)` 関数を実装し、`aozora_header()` / `aozora_chapter_title()` / `aozora_colophon()` で青空文庫テキストを組み立てて `write_file()` + `build_epub()` を呼ぶ
   - 関数の先頭で `_apply_output_dir` / `_dry_run_exit` / `_show_episode_list` / `_apply_resume` を呼ぶ（共通パターン）
   - エピソードは `{"title": str, "body": str, "group": str}` 形式で `epub_episodes` に追加する
3. `normalize_url()` にエピソード URL → 作品トップ URL の正規化ロジックを追加（必要な場合）
4. `_SITE_DISPATCH` 辞書に `"サイト名": ("表示名", "#デフォルト表紙色", run_サイト名)` を追加する（`main()` のディスパッチ・表紙色設定・エラーメッセージ出力はすべて `_SITE_DISPATCH` を参照するため、if/elif への追記は不要）
5. CLAUDE.md のアーキテクチャセクションと依存ライブラリ表を更新

## font/ ディレクトリ

`font/` に OFL ライセンスのフォントファイルを同梱：
- `AyatiShowaSerif-Regular.ttf` — 昭和書体風明朝
- `AyatiRoundedSerif.ttf` — 丸みのある明朝

`--font font/AyatiShowaSerif-Regular.ttf` のように指定して ePub に埋め込める。

## forwindows/ ディレクトリ

Windows 向け補助スクリプト一式。Shift-JIS エンコード（PowerShell ブロックは ASCII のみ）。

| ファイル | 用途 |
|---|---|
| `clipnoveldwn.bat` | クリップボードの URL を即ダウンロード |
| `watcher.bat` | OneDrive 監視・自動ダウンロード（処理済みを `done\` フォルダへ移動） |
| `watcherG.bat` | Google Drive 監視・自動ダウンロード（同上） |
| `novel_downloader.exe` | 本体 exe（git 管理外） |

両 watcher は**バッチ＋PowerShell のポリグロットスクリプト**。バッチ部でファイル検知・ダウンロード実行、PowerShell 部でファイル内容から URL を抽出して返す。短縮 URL は `novel_downloader.py` 側で自動展開される。

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
