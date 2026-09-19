# 設計書: CLI メッセージの英語対応（i18n）

対象: `novel_downloader.py`
方針の前提: `CLAUDE.md`「国際化（i18n）方針」— **ヘルプとエラーのみ英語対応**、青空文庫書式と縦組み組版は日本語固定。
目的: 日本語コンテンツを扱いたい**日本語学習者・非日本語環境のユーザー**が、失敗したときにメッセージを読めて検索できる状態にする。

> **本書は v2.9.0（PR #1 マージ後）のコードに対して実測し直したもの。**
> 数値・行番号・関数名はすべて現状のコードで確認済み。再現は `tools/extract_messages.py`。

---

## 1. 現状

### 1.1 完了している部分（PR #1 / v2.9.0）

| 項目 | 状態 |
|---|---|
| 言語解決（旧 Step 3） | **完了**。`_resolve_ui_lang()` が `--lang` / `-L` > `NOVEL_DOWNLOADER_LANG` > `ja`。`LANG` / `LC_ALL` は見ない |
| CLI ヘルプ（旧 Step 2b） | **完了**。`--lang en --help` の日本語行は 0。日本語ヘルプは `--lang` の行が増えた以外は無変更 |
| `README.en.md` | **完了** |

### 1.2 残っている部分（実測値）

| 指標 | 件数 |
|---|---:|
| 日本語を出力する呼び出し箇所 | **471** |
| うちユニークな文言 | **229** |
| 1回しか出現しない文言 | 165 |

PR #1 は `_build_arg_parser()` と GUI しか触っていないため、**`print` 側の数値はマージ前と変わっていない**。

| 層 | ユニーク | 箇所 | 内容 |
|---|---:|---:|---|
| **P0 エラー・警告** | **95** | **129** | `エラー:` `[エラー]` `[警告]` `⚠` `〜できません` `〜が必要です` |
| P2 進捗・情報 | 42 | 147 | `✅` `📖` `[n/3]` `[情報]` |
| P3 データ出力・その他 | 92 | 195 | 作品情報表示、エピソード一覧、集計表示 |

**実装対象は P0 の 95 文言・129 箇所のみ**（P2 / P3 は方針上の対象外・§4）。

> `tools/extract_messages.py` の「CLI ヘルプ」カウントは現在 40 と出るが、これは
> `H(en, ja)` の日本語側を数えているだけで未訳ではない。指標としては役目を終えている。

---

## 2. 現状コードの調査結果

### 2.1 呼び出し箇所の 49% は定型ブロックの複製

21 個の `run_*` が同じ意味の出力を各自で書いており、**表記ゆれも生んでいる**。

| 定型ブロック | 箇所 | 出現関数数 | ユニーク文言 |
|---|---:|---:|---:|
| 3段階進捗 `[1/3]〜[3/3]` | 48 | 16 | 14 |
| 作品情報ヘッダ（タイトル・著者） | 43 | 21 | 12 |
| 件数表示（エピソード数・総文字数等） | 39 | 19 | 11 |
| 出力完了（`✅ テキスト/ePub出力完了`） | 36 | 19 | 3 |
| URL 正規化の3行 | 36 | 1 | 6 |
| `📖 ePub生成中...` | 17 | 17 | 1 |
| `[resume]` / `[Step N]` | 11 | 4 | 11 |
| サイト判別・作品トップ | 5 | 5 | 3 |
| **小計** | **235 (49%)** | | |

例（タイトル行だけで5種）: `タイトル    :` / `タイトル  :` / `タイトル :` / `タイトル:` / `タイトル  :`

### 2.2 【重大】GUI が CLI の標準出力をパースしている

`novel_downloader_gui.py`:

```python
_RE_PROGRESS  = re.compile(r"^\s+\[\s*(\d+)\s*/\s*(\d+)\s*\]")   # 13 箇所が該当
_RE_EPUB_DONE = re.compile(r"✅\s*ePub出力完了:\s*(.+)$")          # 18 箇所が該当
```

**`✅ ePub出力完了:` は表示文言ではなくプロセス間の契約。** 翻訳すると Windows GUI が完了を検出できず、
「終わったのに完了しない」という無言の故障になる。（Android は `PROGRESS_CALLBACK` のインプロセス連携なので無関係。）

### 2.3 イベント発火の単一挿入点は既に存在する

`_progress(n, total, title)` は **print をしていない**。`PROGRESS_CALLBACK` を呼ぶだけで、
**13 箇所すべてで進捗 print と隣接**している（`CLAUDE.md` の新スクレイパー追加手順で規約化済み）。

```python
print(f"  [{ep_i:3d}/{len(target)}] {ep_title[:40]}")
_progress(ep_i, len(target), f"{ep_title[:40]}")
```

進捗イベントの発火点は `_progress()` ひとつで足り、出力完了イベントの発火点は Step 0 が作る
`_print_outputs()` ひとつになる。**Step 0 は Step P のリスクではなく前提条件。**

### 2.4 【新】言語解決は存在するが、そのままでは `T()` から使えない

PR #1 が入れた仕組みは**ヘルプ専用の配線**になっている。

```python
def _resolve_ui_lang(argv=None) -> str: ...       # 11115
def _build_arg_parser(lang: str = "ja") -> ...:   # 11135
    en = (lang == "en")
    def H(en_text, ja_text): return en_text if en else ja_text   # 11143（内側の関数）
...
parser = _build_arg_parser(_resolve_ui_lang(argv))                # 11356
```

- **解決結果はどこにも保持されない。** `_build_arg_parser()` の引数として渡されて終わり
- **`H()` は `_build_arg_parser()` 内のクロージャ**で、`en` を捕捉している。外からは呼べない
- `_make_runner_args()` は `_build_arg_parser()`（既定 `ja`）を**既定値の取得のためだけに**呼ぶ（10548）。
  ここは言語と無関係なので触らない

→ `T()` 用に**モジュール変数 `_UI_LANG` を追加**し、`_resolve_ui_lang()` を唯一の判定元として共有する（§3 Step 1）。

### 2.5 【新】3 件はインポート時に出力される（argv 解析より前）

モジュール直下で日本語を出す `print` が 3 箇所ある。

| 行 | 内容 | 層 | 出力先 |
|---:|---|---|---|
| 147 | `[警告] Pillow がインストールされていないため…` | P0 | **stdout** |
| 2547 | `[情報] 日本語フォント検出: …` | P2 | stderr |
| 2550 | `[警告] 日本語フォントが見つかりませんでした…` | P0 | stderr |

`_main()` が argv を解析する前に実行されるため、**`_main()` の中で `_UI_LANG` を設定する方式では
この 2 件の P0 警告を英語化できない**。`_resolve_ui_lang()` は `argv=None` で `sys.argv` を読むので、
**モジュール直下で `_UI_LANG = _resolve_ui_lang()` を評価すれば CLI では解決できる**。

**インプロセス利用（Android / GUI が `main(argv)` を呼ぶ形）では解決できない。** `sys.argv` はホストアプリのものであり、
インポート時点で呼び出し側の希望言語は分からない。これは仕様として受け入れる（該当は上記 2 件のみ、
Android は `NOVEL_DL_COVER_FONT` を設定するので 2550 には到達しない）。

### 2.6 【新・i18n とは別件の不具合】Pillow 警告が stdout に出て GUI 用 JSON を壊す

`engine_gui_modes_design.md` §4.5 でフォント診断を stderr へ移したが、**行 147 の Pillow 警告が漏れている**。
これは stdout に出るため、`--detect-site` / `--list-sites` の「stdout には JSON だけ」という規律（同§2.3）を破る。

実測（`PIL` の import を失敗させて再現）:

```
$ python3 novel_downloader.py --list-sites          # Pillow なし
1  [{"site": "narou", "display_name": "小説家になろう"}, …    ← JSON
2  [警告] Pillow がインストールされていないため、JPEG表紙画像を…
…  （警告は計 6 行）
```

GUI は **最終非空行**を JSON として読む（`novel_downloader_gui.py` の `detect_site()` / `list_sites()` が
`[ln for ln in out.splitlines() if ln.strip()][-1]`）ため、警告の最終行を `json.loads` して失敗する。

**結果: Pillow 未導入の Windows 環境では、`detect_site()` が常に `None` を返し、サイトバッジが
「⚠ 判定エラー」のままダウンロードボタンが有効にならない＝ GUI が使えない。**

修正は `print(...)` に `file=sys.stderr` を足すだけ。**i18n とは独立した不具合なので、先に単独で直す。**

---

## 3. 実装案

### 3.0 順序

```
Step B  Pillow 警告を stderr へ（§2.6・i18n とは独立。単独で先に）
  └─ Step 0  定型ブロックの共通ヘルパー化（挙動非変更）
       └─ Step P  --progress-json（GUI 連携プロトコル）※正式な設計書は別途
            └─ Step 1  _UI_LANG と T() カタログの骨組み
                 └─ Step 2a P0 エラー・警告 95 文言
```

Step 2b（ヘルプ）と Step 3（言語解決）は PR #1 で完了済み。

### Step B: Pillow 警告を stderr へ（先行・単独）

行 147 の `print(...)` に `file=sys.stderr` を足す。**1 行の修正**。
確認は §5 の「Pillow なし再現」。他の変更と混ぜず単独のコミットにする（緊急度が違うため）。

### Step 0: 定型ブロックの共通ヘルパー化（挙動非変更）

```python
def _print_work_info(title, author, *, original=None, episodes=None,
                     chapters=None, pages=None, chars=None): ...
def _print_stage(n, total, label): ...               # [1/3] 作品情報を取得中: …
def _print_episode(i, total, title, suffix=""): ...  # ␣␣[   5/123] 第5話 …
def _print_outputs(txt_path=None, epub_path=None): ...
def _print_normalized(before, after, kind="episode"): ...
```

**確定事項:**

1. **表記ゆれは正準形へ統一する。** ラベルは全角4字分で `:` を置き、値まで半角スペース1つ
2. **GUI 契約の 2 書式は互換性を壊さない**（§2.2）。許容される変更は書式ごとに異なる
   - `  [N/M] {title}` — 13 箇所。**桁揃えの差（`:3d` / `:4d` / `:5d`）は統一してよい**。
     GUI 側は `^\s+\[\s*(\d+)\s*/` で `[` 直後の空白を `\s*` が吸収するため右詰め幅に依存しない。正準形は `:4d`
   - `✅ ePub出力完了: {path}` — 18 箇所。**接頭辞・記号・コロン・空白すべて現状維持**。出力バイト列を不変にする
3. **ステージ見出し `[1/3]`〜`[3/3]` は自由に整形してよい。** GUI の正規表現は先頭空白を必須にして
   ステージ見出しを意図的に弾いている（`gui_v1_design.md` §9.2）。48 箇所・14 種の表記ゆれをここで解消する
4. **`_progress()` には触らない。** Step P の発火点として現状のまま残す
5. **P2 / P3 の文言も対象。** Step 0 は i18n ではなく重複排除

**検証**: 挙動非変更が要件。各サイト 1 作品を Step 0 前後で実行し、**stdout を diff して差分ゼロ**を確認する
（正準形へ統一した箇所のみ意図的差分として許容し、一覧をコミットに残す）。

### Step P: `--progress-json`（GUI 連携プロトコル）

**正式な設計書は別途作成する。** 方向のみ:

- stdout を JSON Lines のイベントストリームにし、人間向けログは stderr へ回す
- スキーマは `--detect-site` / `--list-sites` の既存規約（`{"schema":1,…}`）を踏襲
- 発火点は `_progress()`（進捗）と `_print_outputs()`（出力完了）。Step 0 完了後は各 1 行で足りる
- **サブプロセス方式は維持する。** `gui_v1_design.md` §3 ①A の4理由のうち「クラッシュ非波及」
  「`.exe` 資産の分離」「中断の確実性」は現在も有効。失効したのは「本体無改修」のみ

### Step 1: `_UI_LANG` と `T()` カタログ

**採用案: 日本語原文をキーにする（gettext の msgid モデル）**

```python
# モジュール直下（§2.5 のインポート時出力より前に評価する）
_UI_LANG = _resolve_ui_lang()

def T(ja: str) -> str:
    """UI 言語に応じてメッセージを返す。未登録なら日本語をそのまま返す。"""
    return _MESSAGES_EN.get(ja, ja) if _UI_LANG == "en" else ja

_MESSAGES_EN = {
    "エラー: エピソード一覧を取得できませんでした。":
        "Error: could not retrieve the episode list.",
    "[警告] フォントファイルが見つかりません: {path}":
        "[warn] Font file not found: {path}",
}

print(T("エラー: エピソード一覧を取得できませんでした。"), file=sys.stderr)
print(T("[警告] フォントファイルが見つかりません: {path}").format(path=p), file=sys.stderr)
```

**確定事項:**

1. **判定元は `_resolve_ui_lang()` ひとつに保つ。** PR #1 が入れた関数をそのまま使い、判定ロジックを二重化しない
2. **`_UI_LANG` はモジュール直下で評価する**（§2.5）。`_main(argv)` の冒頭で
   `argv is not None` のときだけ `_UI_LANG = _resolve_ui_lang(argv)` として再解決する
   （インプロセス利用で呼び出し側が明示した言語に従うため）
3. **`H()` には手を出さない。** `_build_arg_parser()` 内のクロージャのままでよい。
   ヘルプは 1 関数に密集した対、エラーは 471 箇所に散在、と性質が違うので併存は許容する
4. **プレースホルダは名前付き `{path}`。** 位置指定 `{}` は英語で語順が変わったとき差し替え順を固定してしまう。
   `f"..."` は `T("...{x}").format(x=x)` へ書き換える
5. **カタログは `novel_downloader.py` に埋め込む。** 単一ファイル配布（Windows exe・Android APK 同梱）が前提で、
   外部ファイル化すると同梱漏れで英語だけ消える。95 エントリ ≒ 200 行
6. **`T()` を通すのは P0 のみ**（§1.2）
7. **イベント（Step P）は翻訳しない。** `event` / `code` / `kind` は安定識別子とし、`message` のみ `T()` を通す
8. **エラーコードは 95 件すべてには振らない。** GUI が分岐に使う 3 種
   （`unsupported_site` / `needs_playwright` / `download_failed`、`gui_v1_design.md` §8 の①②③）に限る

**日本語フォールバックがあるため、カタログが空でも動作は現状と完全に同一。** これが段階導入とリスク低減の要。

### Step 2a: P0 エラー・警告 95 文言

129 箇所を `T()` 化し、`_MESSAGES_EN` を埋める。**部分的に進めてよい**（未登録は日本語のまま出る）。

---

## 4. 翻訳してはいけないもの（保護対象）

| 対象 | 理由 |
|---|---|
| `✅ ePub出力完了: {path}` | **GUI がパースする契約**（§2.2） |
| 進捗行 `  [N/M]` の書式 | 同上 |
| `--list-sites` / `--detect-site` の JSON | GUI 用の機械可読出力。`display_name` はサイト固有名詞 |
| `--list-only` のエピソード一覧 | 中身は作品タイトルそのもの |
| `.txt` 内の全ラベル（`底本URL：` 等） | パースキー。`CLAUDE.md`「対応しない層1」 |
| ePub 内の文言（奥付・目次・`第N話`） | 出力物の一部 |
| サイト表示名（小説家になろう 等） | 固有名詞。`_SITE_COLOR_BY_LABEL` の照合キーでもある |

**P2 進捗を対象外にした理由は方針だけでなくこれ。** 進捗表示には GUI 契約が混ざっており、一括で `T()` を通すと壊れる。
**Step P 完了後は上位 2 件が保護対象から外れ**、将来 P2 を訳す選択肢が開く。

---

## 5. 検証

### 5.1 Step B（Pillow 警告）

```bash
mkdir -p /tmp/noPIL && echo 'raise ImportError' > /tmp/noPIL/PIL.py
PYTHONPATH=/tmp/noPIL python3 novel_downloader.py --list-sites 2>/dev/null | wc -l   # 1 であること
PYTHONPATH=/tmp/noPIL python3 novel_downloader.py --detect-site https://ncode.syosetu.com/n0022gd/ \
  2>/dev/null | python3 -c 'import json,sys; json.loads(sys.stdin.read()); print("OK")'
```

### 5.2 Step 0

各サイト 1 作品を前後で実行し stdout を diff。差分は正準形統一分のみ。

### 5.3 Step 1 / 2a

`tools/check_i18n.py` を追加する（`tools/extract_messages.py` と同じ位置づけ）。

1. AST で `T()` の第1引数リテラルを収集し、`_MESSAGES_EN` のキーと突き合わせて**未翻訳**と**孤児**を報告
2. `{name}` プレースホルダが日英で一致するか検査（英訳での取りこぼしは実行時 `KeyError` になる）
3. **保護対象（§4）の文字列が `T()` に渡されていないか**検査

```bash
python3 -m py_compile novel_downloader.py
python3 novel_downloader.py --lang en --help | grep -P '[\p{Hiragana}\p{Katakana}]'   # 0 行
LANG=en_US.UTF-8 python3 novel_downloader.py --help | head -3                          # 日本語のまま
python3 novel_downloader.py --lang en <URL> --dry-run                                  # エラー系を英語で確認
python3 novel_downloader_gui.py                                                        # 完了検出が効くこと
```

---

## 6. リスク

| リスク | 対策 |
|---|---|
| GUI の完了検出が壊れる | §4 の保護対象を `check_i18n.py` で機械検査。GUI 実行を確認手順に含める |
| Step 0 のリファクタで出力が変わる | 挙動非変更として単独実施。stdout の diff で差分ゼロを確認 |
| 英訳漏れで日英混在 | 日本語フォールバックで壊れはしない。P0 は段階導入可 |
| 原文変更でカタログが浮く | `check_i18n.py` の孤児検査 |
| インポート時出力が英語化されない（インプロセス時） | 仕様として受け入れる（§2.5・該当 2 件） |
| 単一ファイルが肥大 | カタログ ≒ 200 行 |

---

## 7. 作業量

| Step | 内容 | 規模 |
|---|---|---|
| B | Pillow 警告を stderr へ | **1 行** |
| 0 | 定型ブロック 8 種を共通ヘルパー化 | 21 関数・235 箇所 → 約 8 箇所 |
| P | `--progress-json` とイベント発火 | `_progress()` / `_print_outputs()` に各 1 行＋エミッタ約 60 行。GUI 側の読み取りループ改修。**正式設計書は別途** |
| 1 | `_UI_LANG` / `T()` / `_MESSAGES_EN` の骨組み | 新規 約 30 行 |
| 2a | P0 エラー・警告 95 文言の `T()` 化と英訳 | 129 箇所 |
| 検証 | `tools/check_i18n.py` | 新規 約 120 行 |
