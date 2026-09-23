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
| `workinfo` | `title`, `author`, `total`（任意）, `unit`, `url` | `_dry_run_exit()` |
| `checkresult` | `file`, `path`, `title`, `author`, `existing`, `total`, `new`, `status`, `error` | `_emit_checkresult()` |
| `episodes` | `title`, `author`, `total`, `titles`（配列） | `_show_episode_list()` |

```json
{"schema":1,"event":"stage","n":1,"total":3,"label":"作品情報を取得中: https://…"}
{"schema":1,"event":"progress","n":5,"total":123,"title":"第5話 …"}
{"schema":1,"event":"output","kind":"epub","path":"/…/作品.epub"}
```

### 3.1 `workinfo`（v2.12.0+ / design_gui_v2.md §10）

作品情報（題名・著者・総数）を 1 回だけ通知する。`--dry-run` と併用すると
**ダウンロードせずに作品情報だけ**取れるので、GUI の受信箱（design_gui_v2 §8.1）が
「出先で投げた URL が何の作品なのか」を取得前に表示するのに使う。

```json
{"schema":1,"event":"workinfo","title":"水属性の魔法使い","author":"久宝　忠","total":935,"unit":"episode"}
```

- 発火点は `_dry_run_exit()`。**全スクレイパーが「作品情報を取得し終えた直後」に
  必ず通る唯一の地点**なので、ここに置けば 17 サイト分が 1 箇所で賄える
  （`--dry-run` 指定の有無にかかわらず発火する。ヘルパー名と役割がずれているが、
  17 箇所を改名する churn に見合わないため据え置き）
- `unit` は `total` の単位。サイトによって数える単位が違うため明示する:
  `"episode"` 話数 / `"page"` ページ数（エブリスタ・野いちご・ノベマ！・berry's）
  / `"chapter"` 章数（ネオページ・杉田玄白・結城浩）
- 青空文庫は ZIP 1 本でこの時点では話数が確定しないので **`total` を送らない**
  （受け手は `total` が無い場合を必ず扱うこと）
- `url` は**短縮URLを展開し作品トップへ正規化したあと**の URL（v2.14.0+）。
  `share.google/…` を投げた呼び出し側は**これでしか作品の正体を知れない**。
  GUI の受信箱はこれで本棚との重複判定をやり直す（design_gui_v2.md §8.8）

**これがある理由**: 無いと GUI は `--dry-run` の人間向け表示を正規表現で読むことになり、
§1 で戒めた「表示文言をプロセス間の契約にする」の再発になる。

**発火点が 3 つで済むのは Step 0 で集約したから。** 集約前は進捗 13 箇所・出力完了 36 箇所・
段階見出し 48 箇所を個別に触る必要があった。

**イベントは翻訳しない。** `event` / `kind` は安定識別子（`design_i18n.md` §3 Step 1 確定事項 7）。

### 3.2 `checkresult`（v2.14.0+ / design_gui_v2.md §8.1a）

更新チェック **1 作品分の結果**を通知する。本棚（design_gui_v2 §8.4）の
「🆕 +N」表示と「N / 全M 件」の進捗に使う。

```json
{"schema":1,"event":"checkresult","file":"作品A.txt","path":"/…/作品A.txt",
 "title":"水属性の魔法使い","author":"久宝　忠",
 "existing":3,"total":935,"new":932,"status":"updated","error":""}
```

- 発火点は `_check_update_one()` のラッパ 1 箇所（`_emit_checkresult()`）。
  この関数は**同じ内容の結果辞書を既に返していた**ので、送出点を足すだけで
  `--check-update-dir` と `--append-dir` Phase 1 の両方が賄える。
  early return が複数あるため `_check_update_one_impl()` に実処理を移し、
  ラッパで送出点を 1 箇所に集約している
- 単発 `--check-update FILE` は `_check_update_one()` を通らず `_main()` の
  `except _CheckUpdateDone` で処理されるので、そこにも同じ形で置いた
- `status` は `updated` / `uptodate` / `error`
- `existing` は手元の話数、`total` はサイト側の全話数、`new` はその差（下限 0）
- **`new_titles` は載せない。** 935 話の作品では 932 件が 1 行の JSON に載る一方、
  GUI は件数しか使わない。題名が要るときは人間向けログ（stderr）にある
- **`底本URL：` の無い `.txt` には発火しない。** ディレクトリモードは
  `_check_update_one()` を呼ぶ前にそれらを弾く（`[スキップ] … 底本URL なし`）。
  受け手が「N / 全M 件」を出すときの M は、**`--shelf-scan` の `url` が空でない
  行数**であって `.txt` の総数ではない

### 3.3 ディレクトリモードでは `stage` / `progress` が作品ごとに繰り返す

`--check-update-dir` / `--append-dir` は作品ごとにランナーを呼ぶため、
`stage` は **作品数 × 3 回**、`progress` は作品ごとに 1 からやり直す形で流れる。
1 本のダウンロードの段階だと思って進捗バーに繋ぐと、作品が変わるたびに
3/3 → 1/3 へ巻き戻って見える。

**ディレクトリモードの受け手は `stage` / `progress` を全体進捗に使わず、
`checkresult` の到着数で数えること。**

### 3.4 `episodes`（v2.15.0+ / design_gui_v2.md §8.15）

`--list-only` の結果（話の題名の配列）を 1 回で通知する。

```json
{"schema":1,"event":"episodes","title":"作品A","author":"著者名","total":3,
 "titles":["第1話","第2話","第3話"]}
```

- 発火点は `_show_episode_list()` の 1 箇所。**全 17 サイトがここを通る**ので
  ここだけで賄える（`workinfo` / `checkresult` と同じ考え方）
- **`--from-file FILE --list-only` でも出る。** 手元の `.txt` の話一覧を
  **通信せずに**取れるので、GUI の本棚はこちらを使う
- `checkresult` では題名の配列を載せなかったが、こちらは載せる。あちらは
  ディレクトリ内の作品ごとにループで発火し受け手は件数しか使わないのに対し、
  こちらは**利用者の明示操作で 1 回だけ**で、題名そのものが目的だから。
  935 話で 1 行あたり 60KB 程度になるが、`for line in stream` で読む分には支障ない
- `_CHECK_UPDATE_MODE` のときは従来どおり `_CheckUpdateDone` を送出して
  イベントは出さない（`--check-update` 系の内部利用と混ざらない）

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
