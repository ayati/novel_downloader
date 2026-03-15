# Windows セットアップガイド

novel_downloader を Windows で使うための環境設定手順です。
コマンドやプログラムを初めて扱う方でも順番通りに進めれば使えるようになります。

---

## 目次

1. [必要なもの](#1-必要なもの)
2. [Python のインストール](#2-python-のインストール)
3. [ファイルの配置](#3-ファイルの配置)
4. [ライブラリのインストール](#4-ライブラリのインストール)
5. [動作確認](#5-動作確認)
6. [実際に使ってみる](#6-実際に使ってみる)
7. [ハーメルンを使う場合の追加設定](#7-ハーメルンを使う場合の追加設定)
8. [よくあるエラーと対処法](#8-よくあるエラーと対処法)

---

## 1. 必要なもの

| 項目 | 内容 |
|---|---|
| OS | Windows 10 または Windows 11 |
| Python | 3.10 以上（無料） |
| インターネット接続 | インストール時・ダウンロード時に必要 |

---

## 2. Python のインストール

### 2-1. ダウンロード

1. ブラウザで [https://www.python.org/downloads/](https://www.python.org/downloads/) を開く
2. 「Download Python 3.x.x」ボタンをクリックしてインストーラーをダウンロード

### 2-2. インストール

1. ダウンロードした `python-3.x.x-amd64.exe` をダブルクリックして起動
2. **最初の画面で必ず以下にチェックを入れる**（これを忘れると後で動かない）

   ```
   ☑ Add Python 3.x to PATH       ← ★ここが最重要★
   ☑ Install launcher for all users (recommended)
   ```

3. 「Install Now」をクリックしてインストール完了まで待つ

### 2-3. インストール確認

インストールが終わったらコマンドプロンプトを開いて確認します。

**コマンドプロンプトの開き方：**
`Windowsキー` + `R` → `cmd` と入力 → `Enter`

表示されたウィンドウに以下を入力して `Enter` を押す：

```
python --version
```

`Python 3.12.x` のようにバージョン番号が表示されれば成功です。

> **「python は認識されていません」と出た場合**
> Python のインストール時に「Add Python to PATH」にチェックを入れ忘れた可能性があります。
> Python をアンインストールして 2-2 からやり直してください。

---

## 3. ファイルの配置

### 3-1. 作業フォルダを作る

わかりやすい場所に専用フォルダを作ります。例：

```
C:\Users\（ユーザー名）\Documents\novel_downloader\
```

エクスプローラーで「ドキュメント」を開き、右クリック → 「新しいフォルダー」→ `novel_downloader` と名前をつけます。

### 3-2. novel_downloader.py を配置

`novel_downloader.py` を上で作ったフォルダ（`novel_downloader`）に入れます。

### 3-3. フォントファイルを配置（任意）

同梱の `font` フォルダごとそのまま `novel_downloader` フォルダに入れると、
`--font font\AyatiShowaSerif-Regular.ttf` で ePub にフォントを埋め込めます。

---

## 4. ライブラリのインストール

Python 本体以外に、いくつかの追加ライブラリが必要です。
コマンドプロンプトで以下を順番に実行します。

### 4-1. コマンドプロンプトを作業フォルダで開く

エクスプローラーで `novel_downloader` フォルダを開き、
アドレスバー（上部のパスが表示されている欄）をクリックして `cmd` と入力 → `Enter`

フォルダのパスがすでに設定された状態でコマンドプロンプトが開きます。

### 4-2. ライブラリをインストール

以下のコマンドを1行ずつ実行します（コピー＆ペーストで OK）：

```
pip install requests beautifulsoup4
```

```
pip install Pillow
```

完了するまで少し待ちます。`Successfully installed ...` と表示されれば成功です。

> **pip コマンドとは？**
> Python のライブラリ（追加機能）をインターネットからダウンロードして
> インストールするための専用コマンドです。

### 4-3. インストール確認

```
pip list
```

と入力すると、インストール済みのライブラリ一覧が表示されます。
`requests`、`beautifulsoup4`、`Pillow` が含まれていれば OK です。

---

## 5. 動作確認

小説家になろう（追加ライブラリなしで動作）で動作確認します。

```
python novel_downloader.py https://ncode.syosetu.com/n0022gd/ --no-epub
```

> `--no-epub` をつけることで、テキストファイルのみを出力します（処理が速くなります）。

以下のように表示されれば成功です：

```
[1/○話] 取得中: 第一話タイトル ...
...
✅ テキスト出力完了: 作品タイトル.txt
```

`novel_downloader` フォルダの中に `作品タイトル.txt` が生成されていれば完了です。

---

## 6. 実際に使ってみる

### 基本的な使い方

```
python novel_downloader.py 作品のURL
```

**例：**

```
python novel_downloader.py https://ncode.syosetu.com/n0022gd/
python novel_downloader.py https://kakuyomu.jp/works/16817139555217983105
```

実行すると `作品タイトル.txt` と `作品タイトル.epub` の2ファイルが生成されます。

### よく使うオプション

| やりたいこと | コマンド例 |
|---|---|
| テキストだけ欲しい（ePub 不要） | `python novel_downloader.py URL --no-epub` |
| 出力ファイル名を指定したい | `python novel_downloader.py URL -o mynovel` |
| 途中から再開したい（なろう） | `python novel_downloader.py URL --resume 51` |
| 特定の話数だけ取得したい | `python novel_downloader.py URL --start 1 --end 10` |
| フォントを ePub に埋め込む | `python novel_downloader.py URL --font font\AyatiShowaSerif-Regular.ttf` |

### PNG 表紙について

Pillow がインストール済みであれば、表紙に日本語テキストが入った PNG 画像が自動生成されます。
Windows 10/11 には MS 明朝・BIZ UDP 明朝などの日本語フォントが標準搭載されているため、
追加でフォントをインストールしなくても PNG 表紙が生成されます。

---

## 7. ハーメルンを使う場合の追加設定

ハーメルン（syosetu.org）は Cloudflare による保護があるため、
ブラウザ自動操作ライブラリ「Playwright」が別途必要です。

### インストール手順

コマンドプロンプトで以下を順番に実行します：

```
pip install playwright
```

```
python -m playwright install chromium
```

Chromium（Chrome ベースのブラウザ）が自動でダウンロードされます（数分かかります）。

### 使い方

```
python novel_downloader.py https://syosetu.org/novel/XXXXXXX/
```

> Playwright インストール後はハーメルン以外のサイトには影響しません。

---

## 8. よくあるエラーと対処法

### `python は認識されていません`

**原因：** Python のインストール時に「Add Python to PATH」にチェックを入れなかった。
**対処：** Python をアンインストールして再インストール。2-2 の手順を確認する。

---

### `pip は認識されていません`

**原因：** Python のインストールが不完全。
**対処：** `python -m pip install ライブラリ名` の形式で代替できます。

---

### `ModuleNotFoundError: No module named 'requests'`

**原因：** requests ライブラリがインストールされていない。
**対処：** `pip install requests beautifulsoup4` を実行する。

---

### `[警告] Pillow がインストールされていないため…` と表示される

**内容：** エラーではなく警告です。ePub は生成されますが表紙が SVG 形式になります。
**対処：** PNG 表紙が必要な場合は `pip install Pillow` を実行する。

---

### 出力ファイルがどこにあるかわからない

コマンドを実行したフォルダ（作業フォルダ）に生成されます。
コマンドプロンプトのタイトルバーや先頭行に表示されているパスが作業フォルダです。
`C:\Users\（ユーザー名）\Documents\novel_downloader\` に作業フォルダを作った場合は
そこに `作品タイトル.txt` と `作品タイトル.epub` が保存されます。

---

### 文字化けする（コンソール表示がおかしい）

novel_downloader.py は起動時に自動で UTF-8 出力に切り替えるため、通常は発生しません。
それでも文字化けする場合は、コマンドプロンプトを開いてから以下を実行してみてください：

```
chcp 65001
```

その後、通常通り `python novel_downloader.py ...` を実行します。

---

以上で環境設定は完了です。問題が解決しない場合は GitHub の Issues ページにご報告ください。
