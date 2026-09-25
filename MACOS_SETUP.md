# macOS セットアップガイド

novel_downloader を macOS で使うための手順です。前半（1〜6）は **自分の Mac で動かす**方法、
後半（7〜8）は **PyInstaller でアプリにして他の人に渡す**方法です。

> **確認状況**: macOS 26 Tahoe（Apple Silicon）の実機で、表紙フォント（ヒラギノ明朝の自動検出）・
> GUI・7 章の `.app` のビルドと、8 章の `xattr` による受け取り側の許可まで確認済み。

---

## 目次

1. [必要なもの](#1-必要なもの)
2. [Python のインストール](#2-python-のインストール)
3. [ファイルの配置とライブラリのインストール](#3-ファイルの配置とライブラリのインストール)
4. [CLI で使う](#4-cli-で使う)
5. [GUI で使う](#5-gui-で使う)
6. [ハーメルンを使う場合](#6-ハーメルンを使う場合)
7. [配布用アプリを作る（PyInstaller）](#7-配布用アプリを作るpyinstaller)
8. [アプリを受け取った人がすること](#8-アプリを受け取った人がすること)
9. [よくあるエラーと対処法](#9-よくあるエラーと対処法)

---

## 1. 必要なもの

| 項目 | 内容 |
|---|---|
| OS | macOS 11 Big Sur 以降（Apple Silicon / Intel） |
| Python | 3.10 以上。**python.org のインストーラ版を推奨**（理由は 2 章） |
| フォント | 追加不要。表紙には macOS 標準の**ヒラギノ明朝 ProN**を自動で使う |

---

## 2. Python のインストール

### どの Python を使うか

| 入手元 | GUI（tkinter） | pip | 配布アプリのビルド |
|---|---|---|---|
| **python.org のインストーラ**（推奨） | そのまま動く（Tcl/Tk 同梱） | そのまま使える | 古い macOS でも動くアプリになりやすい |
| Homebrew（`brew install python`） | `brew install python-tk@3.x` が別途必要 | 仮想環境（venv）が必要 | 作った Mac の OS より古い macOS では動かないことがある |
| macOS 付属の `/usr/bin/python3` | Tk が古く表示が崩れることがある | 使えるが非推奨 | 非推奨 |

Homebrew の Python しか入っていない状態で GUI を起動すると `No module named '_tkinter'` で
止まります。`brew install tcl-tk` / `python-tk` を入れれば動きますが、
これから入れるなら python.org 版が一番手間がかかりません。

### インストール

1. [https://www.python.org/downloads/macos/](https://www.python.org/downloads/macos/) から
   「macOS 64-bit universal2 installer」をダウンロードしてインストール
2. インストール後に開く Finder ウィンドウ（`/Applications/Python 3.x/`）で
   **`Install Certificates.command` をダブルクリック**する
   （これを忘れると、なろうの取得で `CERTIFICATE_VERIFY_FAILED` になる。9 章）
3. ターミナル（アプリケーション → ユーティリティ → ターミナル）で確認

   ```bash
   python3 --version        # Python 3.10 以上ならOK
   python3 -c "import tkinter; print(tkinter.TkVersion)"   # 8.6 以上ならOK
   ```

---

## 3. ファイルの配置とライブラリのインストール

作業フォルダに `novel_downloader.py`（GUI を使うなら `novel_downloader_gui.py` も）を置き、
そのフォルダで以下を実行します。

```bash
cd ~/novel_downloader
python3 -m pip install requests beautifulsoup4 Pillow   # CLI に必要
python3 -m pip install customtkinter                     # GUI に必要
```

> **Homebrew の Python の場合**は `error: externally-managed-environment` で止まるので、
> 先に仮想環境を作ってから入れる:
>
> ```bash
> python3 -m venv .venv && source .venv/bin/activate
> pip install requests beautifulsoup4 Pillow customtkinter
> ```
>
> 以降、使う前に毎回 `source .venv/bin/activate` を実行する。

---

## 4. CLI で使う

```bash
# 接続確認（ファイルは作らない）
python3 novel_downloader.py https://ncode.syosetu.com/n0022gd/ --dry-run
```

起動直後に次の行が出ていれば、表紙は JPEG（題簽デザイン）で作られます。

```
[情報] 日本語フォント検出: bold=ヒラギノ明朝 ProN.ttc[…]  medium=ヒラギノ明朝 ProN.ttc[…]
```

`[警告] 日本語フォントが見つかりませんでした` と出た場合は表紙が SVG になります。
フォントファイルを直接指定すれば回避できます:

```bash
python3 novel_downloader.py <URL> --cover-font "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
```

使い方・オプションは `README.md` と同じです。出力は実行したフォルダ（`--output-dir` で変更可）。

### 縦書き表紙の字形について（任意）

表紙の縦組みは、Pillow が raqm（＋FriBiDi）を使えるとフォント本来の縦書き字形で組み、
使えなければ Unicode の縦書き用の文字で代わりに組みます。どちらでも表紙は作られるので
通常は何もしなくてよいですが、Homebrew があれば `brew install fribidi` で前者になります。

---

## 5. GUI で使う

```bash
python3 novel_downloader_gui.py
```

- GUI は同じフォルダの `novel_downloader.py` を呼び出して動きます。**2 つは必ず同じフォルダに置く**
- 既定の保存先: `~/Downloads/小説`
- 設定ファイル: `~/.config/novel_downloader_gui/settings.json`

---

## 6. ハーメルンを使う場合

ハーメルンは Cloudflare を回避するためにブラウザ（playwright）が必要です。
**python3 で動かす場合のみ**対応します（7 章の配布アプリには含めません）。

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

---

## 7. 配布用アプリを作る（PyInstaller）

### 7-1. 配布できるか

**配布できます。受け取った人は Python・Homebrew・tcl-tk のどれも入れる必要がありません。**
PyInstaller が Python 本体・Tcl/Tk・ライブラリをまとめて 1 つにするためです
（`brew install tcl-tk` が必要なのは、ビルドする側が Homebrew の Python を使う場合だけ）。

ただし次の制約があります。

| 項目 | 内容 |
|---|---|
| CPU | **ビルドした Mac と同じ CPU でしか動かない**。Apple Silicon で作れば Apple Silicon 専用。Intel Mac 向けは Intel Mac（または Rosetta 上の x86_64 Python）で別にビルドする |
| macOS の版 | ビルドに使った Python が対応する最古の版まで。python.org 版なら古い macOS でも動きやすい。Homebrew 版はビルドした Mac の OS 以降になりがち |
| 署名・公証 | 無料の範囲では**公証（notarization）できない**ので、受け取った人が初回にターミナルで 1 行実行する必要がある（8 章）。公証には Apple Developer Program（年 99 米ドル）が要る |
| ハーメルン | 含めない（`--exclude-module playwright`）。Windows 版と同じ |

### 7-2. ビルド

python.org 版の Python で、作業フォルダに仮想環境を作ってビルドします。

```bash
cd ~/novel_downloader
python3 -m venv .venv-build && source .venv-build/bin/activate
pip install requests beautifulsoup4 Pillow customtkinter pyinstaller
```

#### 方法 A: `.app` にする（推奨・実機確認済み）

Dock やアプリケーションフォルダから起動できる普通のアプリにします。受け取る人の手間が一番少ない形です。macOS では `--windowed` と `--onefile` の
組み合わせは非推奨なので、GUI は onedir で作ります。

```bash
pyinstaller --onefile --exclude-module playwright novel_downloader.py
pyinstaller --windowed --collect-data customtkinter --exclude-module playwright \
            --name "小説ePubダウンローダー" novel_downloader_gui.py

# エンジンを .app の実行ファイルと同じ場所に入れる
cp dist/novel_downloader "dist/小説ePubダウンローダー.app/Contents/MacOS/"
# 中身を変えると PyInstaller の署名が壊れて「壊れているため開けません」になるので署名し直す
codesign --force --deep --sign - "dist/小説ePubダウンローダー.app"
```

`dist/小説ePubダウンローダー.app` を zip にして、**8 章の `xattr` の 1 行を添えて**渡します
（Finder の「圧縮」か `ditto -c -k --keepParent <app> <zip>`。普通の `zip` は署名を壊すことがある）。

#### 方法 B: 実行ファイル 2 つをフォルダで渡す

```bash
pyinstaller --onefile --exclude-module playwright novel_downloader.py
pyinstaller --onefile --collect-data customtkinter --exclude-module playwright \
            novel_downloader_gui.py
```

`dist/` にできる `novel_downloader` と `novel_downloader_gui` の **2 つを同じフォルダに入れて**渡します。
GUI は隣の `novel_downloader` を呼ぶので、片方だけでは動きません
（無いと、どの URL も「このサイトには対応していません」と表示される）。
ダブルクリックするとターミナルが開いてから GUI が表示されます。起動の手触りが普通のアプリと違うので、特に理由が無ければ方法 A を使ってください。

#### ビルドしたら確認すること

```bash
./dist/novel_downloader --detect-site https://ncode.syosetu.com/n0022gd/
# → {"schema": 1, "site": "narou", ...} が出ればエンジンは正常
./dist/novel_downloader https://ncode.syosetu.com/n0022gd/ --dry-run
# → 日本語フォント検出の行とタイトルが出れば、証明書・フォントとも正常
```

---

## 8. アプリを受け取った人がすること

インターネット（メール・クラウドストレージ・Web）経由で受け取ったアプリは、
公証されていないため初回起動時に止められます。**ターミナルで隔離属性を外してください。**
（アプリケーション → ユーティリティ → ターミナル を開き、`.app` を置いたフォルダで実行）

```bash
xattr -dr com.apple.quarantine 小説ePubダウンローダー.app
```

これ 1 行で、以後は普通にダブルクリックで起動できます。
方法 B（2 ファイル）で受け取った場合は、2 つを入れたフォルダに対して実行します
（`xattr -dr com.apple.quarantine <フォルダ>`）。

> **システム設定からの許可は使えません。** 通常の未公証アプリなら
> システム設定 → プライバシーとセキュリティ に「このまま開く」が出ますが、
> この `.app` は実機で試したところ**一覧に出てこなかった**ため、`xattr` が必須です。
> macOS 15 Sequoia 以降は右クリック →「開く」でも回避できません。

AirDrop や USB メモリで渡した場合も、受け取り方によっては同じように止められます。
そのときも上の 1 行で解除できます。

---

## 9. よくあるエラーと対処法

### `No module named '_tkinter'`（GUI が起動しない）

Homebrew の Python で Tk が入っていません。`brew install python-tk@3.x`（`3.x` は使っている版）を入れるか、
python.org 版の Python を使ってください。

### `No module named 'customtkinter'`

`python3 -m pip install customtkinter`。仮想環境を使っている場合は有効にしてから入れる。

### `CERTIFICATE_VERIFY_FAILED`

python.org 版の Python で `Install Certificates.command` を実行していません。
`/Applications/Python 3.x/Install Certificates.command` をダブルクリックしてください。

### 表紙が SVG になる（`日本語フォントが見つかりませんでした`）

4 章のとおり `--cover-font` でフォントを指定してください。GUI では
詳細設定 →「表紙の文字」からフォントファイルを選べます。

### 配布アプリで、どの URL も「このサイトには対応していません」になる

GUI がエンジン（`novel_downloader`）を起動できていません。
- GUI とエンジンが同じフォルダ（`.app` なら `Contents/MacOS/`）にあるか
- エンジンが古い版のままでないか（GUI と必ずセットで作り直す）
- エンジン単体で `./novel_downloader --detect-site <URL>` が JSON を返すか

### 「壊れているため開けません。ゴミ箱に入れる必要があります」

隔離属性か署名の問題です。8 章の `xattr -dr com.apple.quarantine` を試し、
それでも出る場合は `.app` の中身を変更した後の再署名（7-2 方法 A の `codesign`）が抜けていないか確認してください。
