# forwindows — Windows 向け補助スクリプト

`novel_downloader.exe` を Windows で手軽に使うための2つのバッチスクリプトです。
どちらも **バッチ＋PowerShell のポリグロットスクリプト**のため、ダブルクリックで動作します。

---

## ファイル一覧

| ファイル | 用途 |
|---|---|
| `clipnoveldwn.bat` | クリップボードの URL を即ダウンロード |
| `watcher.bat` | OneDrive フォルダを監視し、txt ファイルが置かれたら自動ダウンロード |
| `watcherG.bat` | Google Drive フォルダを監視し、ファイルが置かれたら自動ダウンロード |
| `novel_downloader.exe` | 本体の実行ファイル |

---

## clipnoveldwn.bat

### 概要

ブラウザでダウンロードしたい作品ページを開き、URL をコピーしてからこのスクリプトを実行するだけでダウンロードできます。

### 使い方

1. ブラウザで対応サイトの作品ページを開き、アドレスバーの URL をコピー（Ctrl+C）
2. `clipnoveldwn.bat` をダブルクリック
3. ダウンロード完了後、自動的に保存先フォルダ（スクリプトと同じフォルダ）が開く

### カスタマイズ（スクリプト冒頭の「ユーザー設定」欄）

```bat
rem フォントファイルのパス（不要な場合は空にする）
set "OPT_FONT=C:/Users/ayati/OneDrive/fonts/AyatiShowaSerif-Regular.ttf"

rem 出力形式オプション（--kobo / 空欄など）
set "OPT_FORMAT=--kobo"

rem その他追加オプション（--encoding utf-8 など）
set "OPT_EXTRA="
```

| 変数 | 説明 | 例 |
|---|---|---|
| `OPT_FONT` | ePub に埋め込むフォントのパス。不要なら空にする | `C:/Users/yourname/fonts/MyFont.ttf` |
| `OPT_FORMAT` | 出力形式オプション。Kobo 端末向けなら `--kobo`、不要なら空 | `--kobo` |
| `OPT_EXTRA` | その他のオプション。通常は空でよい | `--encoding utf-8` |

> **ユーザー名の変更**: `OPT_FONT` のパス内の `ayati` を自分のユーザー名に書き換えてください。

### エラー時の動作

| 状況 | 動作 |
|---|---|
| クリップボードが空 | メッセージボックスで警告し終了 |
| URL 形式でない | メッセージボックスで警告し終了 |
| ダウンロード失敗 | 終了コードを表示し、キー入力待ち（`pause`）で停止 |

---

## watcher.bat

### 概要

OneDrive 上の「トリガーフォルダ」を常時監視し、そこに URL を書いた `.txt` ファイルを置くと自動でダウンロードを実行します。
スマートフォンや別の PC から OneDrive 経由でダウンロードを指示したいときに便利です。

### 初期セットアップ

#### 1. ファイルの配置

`novel_downloader.exe` を OneDrive 直下にコピーします。

```
C:\Users\{ユーザー名}\OneDrive\
├── novel_downloader.exe   ← ここに配置
├── fonts\
│   └── AyatiShowaSerif-Regular.ttf   ← フォントもここに（任意）
├── epub\                  ← ダウンロード結果の保存先（自動作成）
└── triger\                ← 監視フォルダ（手動で作成）
```

#### 2. 監視フォルダの作成と同期設定

1. OneDrive 直下に `triger` フォルダを作成
2. エクスプローラーで `triger` フォルダを右クリック →「このデバイス上で常に保持する」を選択
   （OneDrive のオンデマンド同期で検知漏れを防ぐため）

#### 3. スクリプトのカスタマイズ

```bat
rem ★★ OneDrive のユーザー名をここだけ変更 ★★
set "ONEDRIVE_USER=ayati"
```

`ayati` を自分の Windows ユーザー名に変更します。その他の設定は自動的に決まります。

必要に応じて以下も変更できます：

| 変数 | デフォルト | 説明 |
|---|---|---|
| `ONEDRIVE_USER` | `ayati` | Windows ユーザー名（**要変更**） |
| `TARGET_FOLDER` | `OneDrive\triger` | 監視フォルダのパス |
| `DOWNLOADER` | `OneDrive\novel_downloader.exe` | 実行ファイルのパス |
| `OPT_OUTPUT` | `OneDrive\epub` | ePub の保存先 |
| `OPT_FONT` | `OneDrive\fonts\AyatiShowaSerif-Regular.ttf` | 埋め込みフォントのパス |
| `OPT_FORMAT` | `--kobo` | 出力形式（`--kobo` / 空欄など） |
| `OPT_EXTRA` | 空 | その他のオプション |

> **python スクリプトを使う場合**: `DOWNLOADER` 行をコメントアウトし、`DOWNLOADER_PY` 行のコメントを外してください。

### 使い方

#### 監視の開始

`watcher.bat` をダブルクリックするとコマンドプロンプトが開き、フォルダ監視が始まります。

```
=========================================
フォルダ監視を開始します
監視対象: C:\Users\ayati\OneDrive\triger
停止するには Ctrl+C を押してください
=========================================
```

停止するには **Ctrl+C** を押します。

#### ダウンロードの指示方法

`triger` フォルダに URL を含む `.txt` ファイルを作成します。

```
https://kakuyomu.jp/works/XXXXXXXXXX
```

URL はファイルの先頭でなくても構いません。タイトルや説明文が先にあっても、最初に見つかった URL を自動抽出します。

```
カクヨム おすすめ作品
https://kakuyomu.jp/works/XXXXXXXXXX
```

share.google / bit.ly / t.co / lin.ee 等の短縮 URL もそのまま使えます（自動展開）。

- ファイル名は何でも構いません（例: `dl.txt`）
- OneDrive で同期されると watcher が自動検知し、ダウンロードを開始します
- スマートフォンの OneDrive アプリからファイルを作成しても動作します

#### 動作ログの例

```
[12:34:56.78] 新しいファイルを検知しました: dl.txt
[12:34:57.89] ダウンローダーを起動します
              URL    : https://kakuyomu.jp/works/XXXXXXXXXX
              オプション: --output-dir C:\...\epub --kobo
[12:35:10.12] 完了しました: dl.txt
```

#### 処理済みファイルの扱い

処理済みファイルは `triger\done\` サブフォルダに移動されます。再起動後も重複処理されません。
同じ URL を再ダウンロードしたい場合は、`done\` フォルダから取り出すか、新しいファイル名で `.txt` を作成してください。

### 注意事項

- `watcher.bat` は開いている間だけ動作します。PC 起動時に自動実行したい場合は、スタートアップフォルダ（`shell:startup`）にショートカットを配置してください。
- 監視間隔は 2 秒です。OneDrive の同期完了後に検知されます。

---

## watcherG.bat

### 概要

Google Drive 上の「トリガーフォルダ」を常時監視し、そこにファイルを置くと自動でダウンロードを実行します。
`watcher.bat`（OneDrive版）と同様の仕組みですが、**Google ドライブ for デスクトップ**でマウントした `G:\マイドライブ` を使用します。
スマートフォンや別の PC から Google Drive 経由でダウンロードを指示したいときに便利です。

### `watcher.bat`（OneDrive版）との違い

| 項目 | `watcher.bat` | `watcherG.bat` |
|---|---|---|
| ストレージ | OneDrive（`C:\Users\{user}\OneDrive`） | Google Drive（`G:\マイドライブ`） |
| 設定方法 | `ONEDRIVE_USER` 変数を書き換えるだけ | パスを直接編集 |
| 処理済みの管理 | `done\` サブフォルダに移動（永続） | `done\` サブフォルダに移動（永続） |

### 初期セットアップ

#### 1. Google ドライブ for デスクトップのインストールと設定

1. [Google ドライブ for デスクトップ](https://www.google.com/intl/ja_jp/drive/download/)をインストール
2. サインイン後、エクスプローラーで `G:\マイドライブ` が表示されることを確認
3. `G:\マイドライブ\triger` フォルダをエクスプローラーで右クリック →「オフラインアクセス - オフラインで使用可能にする」を設定
   （同期完了前に検知されるのを防ぐため）

#### 2. ファイルの配置

`novel_downloader.exe` を Google ドライブ直下にコピーします。

```
G:\マイドライブ\
├── novel_downloader.exe   ← ここに配置
├── fonts\
│   └── AyatiShowaSerif-Regular.ttf   ← フォントもここに（任意）
├── epub\                  ← ダウンロード結果の保存先（自動作成）
└── triger\                ← 監視フォルダ（手動で作成）
```

#### 3. スクリプトのカスタマイズ

スクリプト冒頭の「ユーザー設定」欄のパスを直接編集します（`watcher.bat` と異なり、ユーザー名変数はありません）：

```bat
rem 監視フォルダ
set "TARGET_FOLDER=G:\マイドライブ\triger"

rem novel_downloader の実行ファイルパス
set "DOWNLOADER=G:\マイドライブ\novel_downloader.exe"

rem オプション定義
set "OPT_OUTPUT=--output-dir "G:\マイドライブ\epub""
set "OPT_FONT=--font "G:\マイドライブ\fonts\AyatiShowaSerif-Regular.ttf""
set "OPT_FORMAT=--kobo"
set "OPT_EXTRA="
```

| 変数 | 説明 |
|---|---|
| `TARGET_FOLDER` | 監視するフォルダのパス |
| `DOWNLOADER` | `novel_downloader.exe` のパス |
| `OPT_OUTPUT` | ePub の保存先（`--output-dir`） |
| `OPT_FONT` | 埋め込みフォントのパス。不要なら空にする |
| `OPT_FORMAT` | 出力形式オプション。Kobo 端末向けなら `--kobo`、不要なら空 |
| `OPT_EXTRA` | その他のオプション。通常は空でよい |

### 使い方

#### 監視の開始

`watcherG.bat` をダブルクリックするとコマンドプロンプトが開き、フォルダ監視が始まります。

停止するには **Ctrl+C** を押します。

#### ダウンロードの指示方法

`triger` フォルダに URL を含むファイルを作成します（拡張子不問）。

```
https://kakuyomu.jp/works/XXXXXXXXXX
```

URL はファイルの先頭でなくても構いません。タイトルや説明文が先にあっても、最初に見つかった URL を自動抽出します。

```
カクヨム おすすめ作品
https://kakuyomu.jp/works/XXXXXXXXXX
```

share.google / bit.ly / t.co / lin.ee 等の短縮 URL もそのまま使えます（自動展開）。

- ファイル名・拡張子は何でも構いません
- Google Drive で同期されると watcherG が自動検知し、ダウンロードを開始します
- スマートフォンの Google Drive アプリからファイルを作成しても動作します

#### 処理済みファイルの扱い

処理済みファイルは `triger\done\` サブフォルダに移動されます。再起動後も重複処理されません。
同じ URL を再ダウンロードしたい場合は、`done\` フォルダから元のファイルを取り出すか、新しいファイル名で作成してください。

### 注意事項

- `watcherG.bat` は開いている間だけ動作します。PC 起動時に自動実行したい場合は、スタートアップフォルダ（`shell:startup`）にショートカットを配置してください。
- 監視間隔は 2 秒です。Google Drive の同期完了後に検知されます。
- Google ドライブ for デスクトップが起動していないと `G:\` ドライブが存在せずエラーになります。
