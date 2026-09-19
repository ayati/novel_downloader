# 設計書: `--progress-json`（GUI 連携プロトコル）

対象: `novel_downloader.py` / `novel_downloader_gui.py`
前提: `design_i18n.md` §2.2「GUI が CLI の標準出力をパースしている」/ §3 Step P
状態: v2.11.0 で実装

---

## 1. 目的

Windows GUI は現在、エンジンの**人間向け標準出力を正規表現で読んで**進捗と完了を検出している。

```python
_RE_PROGRESS  = re.compile(r"^\s+\[\s*(\d+)\s*/\s*(\d+)\s*\]")
_RE_EPUB_DONE = re.compile(r"✅\s*ePub出力完了:\s*(.+)$")
```

**`✅ ePub出力完了:` は表示文言ではなくプロセス間の契約**になってしまっており、
文言を少しでも変えると GUI が完了を検出できず「終わったのに完了しない」という無言の故障になる。
i18n で進捗表示を訳せないのも、Step 0 で出力完了の書式を変えられなかったのも、この結合が理由。

**構造化したイベントストリームに置き換え、表示文言を自由にする。**

## 2. 方針

| 論点 | 採用 | 理由 |
|---|---|---|
| プロセスモデル | **サブプロセスのまま** | `gui_v1_design.md` §3 ①A の4理由のうち「クラッシュ非波及」「exe 資産の分離」「中断の確実性」は現在も有効。失効したのは「本体無改修」のみ |
| 通信路 | **stdout を JSON Lines 専用にし、人間向け出力は stderr へ回す** | 既存の `--detect-site` / `--list-sites` と同じ「stdout には機械可読出力だけ」規律（`engine_gui_modes_design.md` §2.3） |
| 有効化 | **`--progress-json` を指定したときだけ** | 既定の挙動は一切変えない。CLI 単体利用者に影響しない |
| スキーマ | `{"schema":1,"event":…}` | 既存2モードと同じ規約 |

### 2.1 人間向け出力の切り替え方

`--progress-json` 指定時は `_main()` の冒頭で **`sys.stdout` を `sys.stderr` に差し替える**。
これにより**既存の 400 箇所以上の `print()` を 1 つも書き換えずに** stderr へ回せる。
イベントは差し替え前に退避した本物の stdout へ書く。

## 3. イベント仕様

1 行 1 JSON（JSON Lines）。未知の `event` は無視してよい。

| event | フィールド | 発火点 |
|---|---|---|
| `stage` | `n`, `total`, `label` | `_print_stage()` |
| `progress` | `n`, `total`, `title` | `_progress()` |
| `output` | `kind`（`txt` / `epub`）, `path` | `_print_text_done()` / `_print_epub_done()` |

```json
{"schema":1,"event":"stage","n":1,"total":3,"label":"作品情報を取得中: https://…"}
{"schema":1,"event":"progress","n":5,"total":123,"title":"第5話 …"}
{"schema":1,"event":"output","kind":"epub","path":"/…/作品.epub"}
```

**発火点が 3 つで済むのは Step 0 で集約したから。** 集約前は進捗 13 箇所・出力完了 36 箇所・
段階見出し 48 箇所を個別に触る必要があった。

**イベントは翻訳しない。** `event` / `kind` は安定識別子（`design_i18n.md` §3 Step 1 確定事項 7）。

## 4. GUI 側

- `_build_cli_args()` に `--progress-json` を追加
- `Popen` の `stderr` を `STDOUT` に統合せず**別パイプにする**。stdout を読む
  スレッドと stderr を読むスレッドの 2 本にする
- stdout: 1 行ずつ `json.loads`。`event` で分岐して従来と同じキュー
  （`progress` / `epub`）へ流す
- stderr: そのまま生ログへ。**旧正規表現も残す**（後述）

### 4.1 版ずれへの備え

GUI とエンジンは別ビルドにできる（`gui_v1_design.md` §12）。エンジンが古いと
`--progress-json` を知らずに `argparse` エラーで即終了する。

- **旧正規表現 `_RE_PROGRESS` / `_RE_EPUB_DONE` は stderr 側に残す。**
  新エンジンでも人間向け出力は stderr に来るので、イベントと二重に拾っても
  結果は同じ（同じ進捗・同じパス）で害がない
- エンジンが `--progress-json` を受け付けずに終了コード 2 で即死した場合は、
  フラグ無しで 1 度だけ再実行する

## 5. 確認

```
1. GUI からダウンロード → 進捗バーが動き、完了カードにファイル名が出る
2. 詳細ログに従来どおり人間向けの行が流れる（stderr 由来）
3. 中止ボタンが効く
4. CLI 単体（--progress-json なし）の出力が従来と 1 バイトも変わらない
5. --progress-json 単体実行: stdout が JSON Lines のみ・人間向けは stderr
6. 旧エンジン exe と新 GUI の組み合わせで再実行フォールバックが働く
```

**4 が最重要。** 既定の挙動を変えないことがこの変更の前提。
