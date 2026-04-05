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
- 縦書き ePub3（.epub）出力（デフォルト）/ 横書き ePub3（`--horizontal`）出力
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
- 目次ページを spine に自動挿入（デフォルト: 表紙の直後・本文の前）
  - `--toc-at-end` で奥付の後（末尾）に変更可能
  - 表紙・タイトルページ・奥付はリンクのみ、エピソードは 1 から採番
  - なろう・カクヨムの「章」「部」単位を目次の区切り見出しとして自動反映（全エピソードは同一インデントレベルで表示）
- iPad / iOS の Kindle アプリで縦書き・ルビが正常表示（`primary-writing-mode` メタタグ対応）
- 途中再開機能（`--resume`、全サイト対応）
  - `--resume` のみで既存 `.txt` から話数を自動検出して再開
  - `--resume N` で第 N 話から強制開始
- 差分ダウンロード・追記機能（`--append`）：既存 `.txt` に続きを追記し ePub を再生成。新規エピソードがない場合はファイルを上書きしない
- ディレクトリ一括追記（`--append-dir`）：フォルダ内の全 `.txt` を走査し、新着のある作品だけ差分ダウンロード・追記・ePub 再生成。事前に対象一覧を表示して確認を求める（`--yes` でスキップ可）
- 更新確認機能（`--check-update`）：ダウンロード・上書きなしで新着話数・タイトルのみ表示
- ディレクトリ一括更新確認（`--check-update-dir`）：フォルダ内の全 `.txt` を走査し、各作品の新着有無をまとめて表示
- **お気に入り監視（`--watch`）**：URL リストファイルを定期チェックし、新着があれば通知・自動 DL する。cron と手動実行の両方に対応。Discord / Slack への Webhook 通知に対応
- サイト公式サムネイルを表紙として使用（`--use-site-cover`）
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
| `--resume [N]` | — | 続きからダウンロード。`N` 省略時は既存 `.txt` から話数を自動検出して再開。`N` 指定時は第 N 話から開始。全サイト対応 |
| `--append FILE` | — | 既存 `.txt` を指定して続きを追記・ePub 再生成。ヘッダーの `底本URL：` から URL を自動検出し差分ダウンロードを実行する。URL 指定不要。新規エピソードがない場合は既存ファイルを上書きしない |
| `--append-dir DIR` | — | ディレクトリ内の全 `.txt` を走査し、新着エピソードがある作品だけ差分ダウンロード・追記・ePub 再生成する。事前チェック → 確認プロンプト → ダウンロード → サマリー表示。`--yes` で確認スキップ |
| `--yes` | — | `--append-dir` の確認プロンプトをスキップする（自動化用） |
| `--check-update FILE` | — | 既存 `.txt` を渡してサイトの最新話数と比較し、新着話数・タイトルを表示して終了。ダウンロード・ファイル上書きは一切行わない。`--append` 前の確認に使う |
| `--check-update-dir DIR` | — | ディレクトリ内の全 `.txt` を走査し、各作品の新着エピソードを一括確認する。底本URL のないファイルは自動スキップ。ダウンロード・ファイル上書きは一切行わない |
| `--list-only` | — | ダウンロードせずエピソード一覧と話数のみ表示して終了する |
| `--start N` | `1` | 取得開始話数（野いちご・ノベマ！・berry's cafe は章番号） |
| `--end N` | 最終話 | 取得終了話数（野いちご・ノベマ！・berry's cafe は章番号） |
| `--encoding ENC` | `utf-8` | テキスト出力エンコーディング（`utf-8` / `utf-8-sig` / `shift_jis` / `cp932`） |
| `--newline MODE` | `os` | テキスト出力の改行コード（`os`=実行環境標準 / `lf`=LF / `crlf`=CRLF） |
| `--no-epub` | — | ePub 出力を省略し、テキストのみ出力 |
| `--cover-bg COLOR` | サイト依存 | 表紙背景色（`#RRGGBB` 形式） |
| `--from-file FILE` | — | ローカルテキストファイルから ePub3 を生成 |
| `--from-epub FILE` | — | ローカル ePub3 ファイルを青空文庫書式テキストに逆変換 |
| `--title TITLE` | — | タイトルを上書き（`--from-file` 使用時） |
| `--author AUTHOR` | — | 著者名を上書き（`--from-file` 使用時） |
| `--cover-image FILE` | — | 表紙に使用するローカル画像ファイル（JPEG/PNG）。指定すると Pillow による自動生成表紙の代わりに使用される。ファイルが存在しない・非対応形式の場合は自動生成にフォールバック |
| `--use-site-cover` | — | 作品ページの公式サムネイル画像（`og:image`）を表紙として使用する。`--cover-image` が指定されている場合は `--cover-image` が優先 |
| `--font FILE` | — | ePub 本文に埋め込むフォントファイル（.otf / .ttf / .woff / .woff2）。ファイルが存在しない場合は警告を出して埋め込みなしで続行 |
| `--toc-at-end` | — | 目次ページを奥付の後（末尾）に配置する。デフォルトは表紙の直後・本文の前 |
| `--output-dir DIR` | カレントディレクトリ | 出力先ディレクトリを指定する。存在しない場合は自動作成。ファイル名は従来通りタイトルから自動生成（`-o` と併用可） |
| `--kobo` | — | 楽天 Kobo 専用端末（Kobo Clara / Kobo Sage 等）向けに ePub の拡張子を `.kepub.epub` にする。通常の `.epub` では端末側が kepub タグを解析せず縦書き・目次が正常に反映されないため、Kobo 端末へ転送する場合はこのオプションを使用する |
| `--horizontal` | — | 横書き ePub3 を生成する。全ページを横組み（`html.hltr`）で出力し、縦中横（tcy）処理をスキップする。`page-progression-direction` は `ltr` に設定される |
| `--watch FILE` | — | ウォッチリストファイル（URL リスト）を指定して新着を監視する。新着があれば通知し、`auto=true` のエントリは自動 DL する。初回は全話数をキャッシュに登録するだけで通知しない |
| `--notify {stdout,webhook}` | `stdout` | 通知方法。`stdout`: 標準出力（新着なし・エラーなし時は無音）。`webhook`: `--webhook-url` 宛に POST |
| `--webhook-url URL` | — | Webhook 送信先（`--notify webhook` 時必須）。Discord / Slack の Incoming Webhook URL |
| `--webhook-format {discord,slack}` | `discord` | Webhook ペイロード形式。`discord`: `{"content":"..."}` / `slack`: `{"text":"..."}` |
| `--watch-cache FILE` | `.novel_watch_cache.json` | ウォッチキャッシュファイルのパス |
| `--watch-auto-default` | — | ウォッチリストで `auto=` 未指定のエントリにも自動 DL を適用する |

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

# 途中から再開（既存 .txt から話数を自動検出）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --resume

# 途中から再開（第 51 話を強制指定）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --resume 51

# 新着話数の確認（ダウンロード・上書きなし）
python novel_downloader.py --check-update 作品タイトル.txt

# 続きを追記して ePub を再生成（URL 指定不要）
python novel_downloader.py --append 作品タイトル.txt

# ディレクトリ内の全作品の新着を一括確認（ダウンロードなし）
python novel_downloader.py --check-update-dir ~/novels/

# ディレクトリ内の全作品を一括追記（新着のある作品だけダウンロード）
python novel_downloader.py --append-dir ~/novels/

# 一括追記を確認プロンプトなしで実行（自動化用）
python novel_downloader.py --append-dir ~/novels/ --yes

# サイト公式サムネイルを表紙に使用
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --use-site-cover

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

# 横書き ePub3 を生成する（縦中横スキップ・LTR ページ送り）
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --horizontal

# ローカルテキストから横書き ePub3 を生成
python novel_downloader.py --from-file mynovel.txt --horizontal

# お気に入りリストの新着を確認（標準出力、新着なし時は無音）
python novel_downloader.py --watch list.txt

# 新着があれば自動 DL（~/novels/ に出力）
python novel_downloader.py --watch list.txt --watch-auto-default --output-dir ~/novels/

# Discord に Webhook 通知
python novel_downloader.py --watch list.txt \
    --notify webhook \
    --webhook-url https://discord.com/api/webhooks/xxx/yyy

# Slack に Webhook 通知
python novel_downloader.py --watch list.txt \
    --notify webhook \
    --webhook-url https://hooks.slack.com/services/xxx/yyy/zzz \
    --webhook-format slack
```

## お気に入り監視（--watch）

複数作品の新着を定期チェックし、新着があれば通知・自動 DL します。cron に登録して使うほか、手動で随時実行することもできます。

### list.txt の書き方

```
# ハッシュでコメント（行頭・行末どちらもOK）
https://ncode.syosetu.com/n1234ab/ | title=水属性の魔法使い | auto=true
https://kakuyomu.jp/works/xxxxx    | auto=false
https://syosetu.org/novel/123/     # auto= 省略 → --watch-auto-default に従う
```

| フィールド | 説明 |
|---|---|
| URL（必須） | 作品トップページの URL。`\|` の前に記述する |
| `title=名前` | 通知・ログに表示する表示名。省略時はサイト取得タイトルを使用 |
| `auto=true\|false` | 新着時に自動 DL するか。省略時は `--watch-auto-default` の値に従う |

### キャッシュファイル（.novel_watch_cache.json）

チェック済みの話数・最終確認日時を保存します。デフォルトはカレントディレクトリの `.novel_watch_cache.json`（`--watch-cache` で変更可）。

```json
{
  "https://ncode.syosetu.com/n1234ab/": {
    "title": "水属性の魔法使い",
    "last_episode": 935,
    "last_title": "第935話 エピローグ",
    "last_checked": "2026-04-05T21:00:00",
    "output_file": "/home/user/novels/水属性の魔法使い.txt"
  }
}
```

`output_file` は `auto=true` で DL したファイルのフルパス。次回の差分追記に使います。

### 初回実行の挙動

初回チェック時はキャッシュが空のため、現在の総話数をキャッシュに登録するだけで通知・自動 DL は行いません。

```
[INIT] 水属性の魔法使い: 全935話をキャッシュに登録しました（次回チェックから新着を通知します）
```

2回目以降から新着が通知されます。

### 通知フォーマット（標準出力）

新着がある場合のみ出力します。新着なし・エラーなしの場合は何も出力しないため、cron でのメール送信を最小化できます。

```
[NEW] 水属性の魔法使い (+3話)
  + 第933話 新たな旅立ち
  + 第934話 決戦
  + 第935話 エピローグ
[ERROR] 別の作品
  ! 未対応サイト: example.com
```

### Discord / Slack Webhook 通知

```bash
# Discord（デフォルト形式）
python novel_downloader.py --watch list.txt \
    --notify webhook \
    --webhook-url https://discord.com/api/webhooks/チャンネルID/トークン

# Slack
python novel_downloader.py --watch list.txt \
    --notify webhook \
    --webhook-url https://hooks.slack.com/services/T.../B.../... \
    --webhook-format slack
```

Discord の Webhook メッセージ例：
```
【水属性の魔法使い】+3話
  第933話 新たな旅立ち
  第934話 決戦
  第935話 エピローグ
```

複数作品に新着があった場合は 1 回の POST にまとめて送信します。

### cron 設定例

```cron
# 6時間ごとにチェック、新着は Discord に通知（作業ディレクトリに list.txt と .novel_watch_cache.json が置かれている前提）
0 */6 * * * cd /home/user/novels && python novel_downloader.py --watch list.txt --notify webhook --webhook-url https://discord.com/api/webhooks/xxx/yyy

# 毎朝6時に新着があれば自動 DL も実行
0 6 * * * cd /home/user/novels && python novel_downloader.py --watch list.txt --watch-auto-default --output-dir /home/user/novels --notify webhook --webhook-url https://discord.com/api/webhooks/xxx/yyy
```

> **ヒント**: `--watch-cache` でキャッシュファイルのパスを指定すると、list.txt の場所とキャッシュの場所を分けて管理できます。

### 自動 DL の動作（`auto=true` / `--watch-auto-default`）

| 状況 | 動作 |
|---|---|
| キャッシュに `output_file` が記録されており、ファイルが存在する | `--append` 相当の差分ダウンロード・追記・ePub 再生成 |
| `output_file` が未記録、または `--output-dir` 内に URL 一致する `.txt` が見つかる | 発見したファイルに追記し、パスをキャッシュに保存 |
| 対応するファイルが見つからない | 全話を新規ダウンロード。完了後にファイルパスをキャッシュに保存 |

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
OEBPS/nav.xhtml              ← RS向け機械読み取り専用（spine に含めない）
OEBPS/toc.xhtml              ← 読者向け目次ページ（spine に含める）
OEBPS/css/novel.css
OEBPS/css/vertical_image.css
OEBPS/fonts/                 ← 埋め込みフォント（--font 指定時のみ）
OEBPS/images/cover.jpg       ← 表紙画像（JPG または SVG）
OEBPS/cover-image.xhtml      ← 画像表紙ページ（epub:type="cover"）
OEBPS/cover.xhtml            ← タイトル・著者・あらすじページ
OEBPS/ep0001.xhtml           ← 各話
OEBPS/ep0002.xhtml
...
OEBPS/colophon.xhtml         ← 奥付
```

spine 読み順（デフォルト）: cover-image → cover → toc → ep0001…epNNNN → colophon
`--toc-at-end` 指定時: cover-image → cover → ep0001…epNNNN → colophon → toc

### 縦書きモード（デフォルト）
- `writing-mode: vertical-rl`（DPFJガイド v1.1.4 準拠・`html.vrtl` クラス）
- OPF に `primary-writing-mode: horizontal-rl` メタタグを付与（iPad / iOS Kindle 縦書き対応）
- `page-progression-direction="rtl"`、表紙 spine に `page-spread-right` 付与
- 数字・半角英字（1〜3桁/文字）を縦中横（`.tcy`）で自動ラップ

### 横書きモード（`--horizontal`）
- `writing-mode: horizontal-tb`（`html.hltr` クラス）
- `page-progression-direction="ltr"`
- 縦中横（tcy）処理をスキップ
- 字下げ CSS は `padding-left` を使用（縦書き時の `padding-top` を `html.hltr` スコープで上書き）

### 共通
- 游明朝 / ヒラギノ明朝 / Noto Serif CJK JP を優先したフォント指定（RS 仮想フォント名 `serif-ja-v` / `serif-ja` も設定）
- ルビ（`<ruby>` タグ）対応
- `epub:type` は `cover` / `cover-image`（cover-image.xhtml）と nav の `toc` / `landmarks` のみ付与（DPFJガイド準拠）
- OPF に `rendition:layout` / `rendition:orientation` / `rendition:spread` メタデータを付与
- なろう・カクヨムの章・部区切りを目次に反映。章ヘッダーは非リンクの太字区切り行として全エピソードと同一インデントレベルに配置（章内エピソードのネスト段差なし）
- nav.xhtml の landmarks に `bodymatter`（本文開始位置）エントリを記載

## ライセンス

MIT License — Copyright (c) 2026 N.Aono
