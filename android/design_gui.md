# 小説ダウンローダー Android GUI 設計書

作成日: 2026-07-07 ／ 対象: `android/`（Chaquopy 17.0.0 + AGP 8.7.3 + Kotlin）

## 1. 目的と前提

- **想定ユーザー**: PC の CLI を使わない層。スマホのブラウザで見つけた Web 小説を、その場で ePub / テキストにして読みたい人
- **提供価値**: 「URL を渡す → 数分待つ → ダウンロードフォルダに ePub ができている」だけの体験。オプションの海は見せない
- **対象サイト**: CLI 版の対応 17 サイトのうち**ハーメルンを除く 16 サイト**（playwright 非搭載のため）
- **対象外機能**: `--watch` / `--append-dir` / `--check-update-dir` 等の運用系、`--from-file` / `--from-epub` の変換系（将来検討）
- **方針**: 本体には **GUI 連携用の最小 API**（§5.1）のみを実装し、それ以外は `bridge.py`（新設）側で吸収する。CLI 単体利用時の挙動は一切変えない。この API は Windows GUI・将来の組み込み利用とも共通

## 2. 全体アーキテクチャ

```
┌─────────────────────────────────────────────┐
│ MainActivity (Kotlin)                        │  UI・入力・進捗表示
│   └─ ViewModel（回転・再生成に耐える状態保持）│
├─────────────────────────────────────────────┤
│ DownloadService (Foreground Service)         │  DL実行・通知・完了後のファイル移動
│   └─ ワーカースレッド 1 本（直列・キューなし）│
├─────────────────────────────────────────────┤
│ Chaquopy (Python 3.10 in-process)            │
│   bridge.py（新設・アプリ専用）               │  main(argv)呼出 / stdout捕捉 / API接続
│   novel_downloader.py（本体・GUI連携API追加） │
└─────────────────────────────────────────────┘
```

- **同時実行は 1 件のみ**。実行中はダウンロードボタンを「中止」に切り替える（Windows GUI 版と同じ操作感）
- ダウンロードは **Foreground Service** で実行する。理由: 数百話の作品はリクエスト間隔 1.5 秒だけで 10 分超になり、Activity のライフサイクル（画面消灯・アプリ切替）では生存を保証できないため
- Service は通知（進捗バー付き）を常駐させ、完了・エラー・中止で更新する

## 3. 画面設計

### 3.1 メイン画面（単一画面構成）

```
┌──────────────────────────────┐
│  小説ダウンローダー        ⋮  │ ← トップバー（⋮=設定メニュー）
├──────────────────────────────┤
│ ┌──────────────────────────┐ │
│ │ 作品ページのURL           │ │ ← URL入力欄（1行・URL専用キーボード）
│ └──────────────────────────┘ │
│ [📋 貼り付け]        [✕ クリア] │
│                              │
│  ◉ カクヨム                  │ ← サイト判定バッジ（入力の都度更新）
│                              │
│ ┌──────────────────────────┐ │
│ │      ⬇ ダウンロード       │ │ ← 大ボタン（実行中は「⏸ 中止」に変化）
│ └──────────────────────────┘ │
│                              │
│ ████████████░░░░░░  123/345  │ ← 進捗バー＋話数（準備中は不定モード）
│ 第123話 ○○○○を取得中…       │ ← ステータス行（最新ログ1行）
│                              │
│ ▸ 詳細ログ                    │ ← 折りたたみ式（stdout/stderr全行）
│                              │
│ ┌──────────────────────────┐ │
│ │ ✅ 完了: 作品タイトル.epub │ │ ← 完了カード（完了時のみ表示）
│ │   [📖 開く]  [📤 共有]     │ │
│ └──────────────────────────┘ │
└──────────────────────────────┘
```

### 3.2 UI 要素定義

| 要素 | 仕様 |
|---|---|
| URL入力欄 | `EditText`（inputType=textUri）。変更のたびに `bridge.detect(url)` で即時サイト判定（オフライン・数ms） |
| 貼り付けボタン | クリップボード先頭項目からURLを抽出して入力欄へ。**自動読み取りはしない**（Android 10+ はバックグラウンド読取不可＋読取トーストが出て不信感を与えるため、明示ボタン方式とする） |
| サイト判定バッジ | 対応サイト名（例「カクヨム」）／未対応なら「⚠ 未対応のURLです」／ハーメルンは「⚠ ハーメルンはアプリ版では非対応です」を専用表示 |
| 大ボタン | IDLE時「ダウンロード」（URL未判定時は無効化）／実行中「中止」。誤タップ対策として中止は確認ダイアログなしだが、中止後も入力URLは保持する |
| 進捗バー | 準備中（作品情報・話数一覧取得）= 不定モード、本文DL中 = `n/N` 確定モード。stdout の `[ n/ N]` 行を正規表現で解析 |
| 詳細ログ | 折りたたみ式のスクロールTextView。stdout/stderr 全行を追記（上限5,000行でローテート） |
| 完了カード | 保存ファイル名を表示。「開く」= `ACTION_VIEW`（ePubリーダーに渡す）、「共有」= `ACTION_SEND` |
| 設定メニュー（⋮） | §8 のオプション。MVP では「横書きにする」「Kobo用拡張子」「サイトの表紙画像を使う」の3項目のみ |

### 3.3 状態遷移

```
IDLE ──[DL押下]──▶ PREPARING（作品情報・エピソード一覧取得、不定進捗）
PREPARING ──▶ DOWNLOADING（n/N 確定進捗）
DOWNLOADING ──▶ SAVING（txt書出・ePub構築・Downloadsへ移動）
SAVING ──▶ DONE（完了カード表示・通知更新）
任意の実行状態 ──[中止押下]──▶ CANCELLING ──▶ CANCELLED
任意の実行状態 ──[例外/exit≠0]──▶ ERROR（ログ自動展開・通知更新）
DONE / CANCELLED / ERROR ──[URL変更 or DL押下]──▶ IDLE へ復帰
```

- 状態は ViewModel が保持し、Service からは `LiveData`/`StateFlow` 経由で配信（画面回転・一時破棄に耐える）
- CANCELLED 時は部分ファイルを残さない（本体は最後に一括書き出しする構造なので、staging を破棄すれば足りる）

## 4. 入力経路

1. **手入力／貼り付けボタン**（MVP）
2. **共有インテント**（M2）: ブラウザの共有メニューから受け取る
   - `ACTION_SEND` + `text/plain` を Manifest の intent-filter に登録
   - 共有テキストから最初の `https?://` をURLとして抽出（ページタイトル等が混ざるため）
   - 起動後、URL欄に自動セット＋サイト判定まで行い、**DL開始はユーザーのボタン押下を待つ**（誤爆防止）
3. **短縮URL**: 本体の `expand_short_url()` がDL実行時に展開する。ただし入力時の即時判定（`--detect-site` 相当）は短縮URL展開をしないため、バッジは「🔗 短縮URL（実行時に展開します）」と表示して実行は許可する

## 5. Python 連携

### 5.1 本体に追加する GUI 連携 API（novel_downloader.py 改修）

モンキーパッチではなく、本体に最小限の連携 API を実装する。**未使用時はすべて不活性**で、CLI 単体の挙動・出力は変わらない。

| # | 追加機能 | 内容 |
|---|---|---|
| 1 | `main(argv=None)` | `parser.parse_args(argv)` に変更。プロセス内から `sys.argv` を汚さずに呼び出せる |
| 2 | 中止フラグ | `ABORT_EVENT = threading.Event()`（公開）と `AbortRequested` 例外を新設。内部ヘルパー `_sleep(sec)` を追加し、既存の `time.sleep` 呼び出し（45箇所）を機械置換する。`_sleep` は `ABORT_EVENT.wait(sec)` で待機し、フラグが立っていれば `AbortRequested` を送出。共通HTTPフェッチの入口でもフラグをチェックする |
| 3 | 中止時の後始末 | `main()` が `AbortRequested` / `KeyboardInterrupt` を捕捉して「中止しました。」を表示し、終了コード **130** で終了する。**CLI の Ctrl+C も traceback を出さなくなる**（副次的改善） |
| 4 | 進捗フック | `PROGRESS_CALLBACK`（公開・既定 `None`）。話数進捗の print 箇所（3箇所）の直後に `PROGRESS_CALLBACK(i, total, title)` を呼ぶ。print 出力自体は現状維持（Windows GUI の stdout 解析との互換を保つ） |
| 5 | 表紙フォント指定 | 環境変数 `NOVEL_DL_COVER_FONT` を `_find_cjk_fonts()` の最優先候補に追加（存在するパスなら即採用）。Android は同梱 TTF（`font/AyatiShowaSerif-Regular.ttf`）を指す。fc-list 等の探索が走らなくなるため import も速くなる |

- リクエスト間には必ず `_sleep(delay=1.5)` が挟まるため、中止は**最悪でも「実行中のHTTPリクエスト1本＋1.5秒」以内**に効く（HTTPにはタイムアウト設定済み）
- Windows GUI は当面 subprocess + `terminate()` 方式のままでよいが、終了コード 130 を「中止」と解釈するよう合わせておくと判定を共通化できる
- 実装時は `CLAUDE.md` にこの API 群を追記する

### 5.2 bridge.py（アプリ専用の薄い層）

本体 API への接続だけを担う。

| 関数 | 説明 |
|---|---|
| `detect(url) -> str(JSON)` | `detect_site()` / `normalize_url()` / `_SITE_DISPATCH` を直接呼び、`--detect-site` と同一スキーマの JSON を返す。オフライン・即時 |
| `run(url, options_json, listener) -> int` | argv リストを組み立てて `main(argv)` を呼び、`SystemExit` / `AbortRequested` を捕捉して終了コードを返す。実行前に `ABORT_EVENT.clear()`・`PROGRESS_CALLBACK` 登録・stdout/stderr 差し替えを行い、`finally` ですべて復元する |
| `cancel()` | `novel_downloader.ABORT_EVENT.set()` を呼ぶだけ |

### 5.3 進捗コールバック（Kotlin側インターフェース）

```kotlin
interface DownloadListener {
    fun onLine(text: String)          // stdout/stderr 1行（詳細ログ用）
    fun onProgress(n: Int, total: Int) // PROGRESS_CALLBACK 経由
    fun onPhase(phase: String)        // PREPARING / DOWNLOADING / SAVING
}
```

- **主経路**: 本体の `PROGRESS_CALLBACK` に bridge が関数を登録し、`onProgress()` へ中継する（print 書式変更に影響されない）
- **ログ経路**: `sys.stdout` / `sys.stderr` を行バッファ付きの自作 TextIO に差し替え、1行ごとに `listener.onLine()` を呼ぶ。`[ n/ N]` の正規表現解析は予備経路として残す
- フェーズ判定: 最初の `onProgress` 受信で DOWNLOADING、進捗が `total` に達した後は SAVING とみなす

### 5.4 novel_downloader.py の同梱方法

- `app/build.gradle.kts` に **Gradle コピータスク**を追加: `../novel_downloader.py` と `../font/AyatiShowaSerif-Regular.ttf` を `app/src/main/python/`（および assets）へビルド時コピー
- コピー先は `.gitignore` に追加（原本はリポジトリ直下のまま一元管理）
- これにより本体のサイト対応追加・バグ修正が `./gradlew assembleDebug` だけで APK に反映される

## 6. ダウンロード実行基盤（DownloadService）

- `startForeground()` + 進捗通知（`setProgress(N, n, false)`）。Android 13+ は `POST_NOTIFICATIONS` の実行時許可を初回DL時に要求（拒否されても DL 自体は継続）
- foregroundServiceType: `dataSync`
- ワーカースレッド 1 本で `bridge.run()` を同期実行。中止は `bridge.cancel()` を別スレッドから呼ぶ
- Service 生存中は部分 WakeLock は**取らない**（Foreground Service + ネットワークI/Oで実用上足りる。Doze で問題が出たら再検討）
- アプリ強制終了・端末再起動での再開はサポートしない（再実行してもらう。将来 `--resume` 対応で緩和可能）

## 7. ファイル出力

### 7.1 二段階方式

1. **Python 側**: `--output-dir` に**アプリ専用領域** `filesDir/staging/` を指定して通常実行（.txt と .epub が生成される）
2. **Kotlin 側**: 完了後に MediaStore 経由で公開領域へコピーし、staging を削除

### 7.2 保存先

- **API 29+**: `MediaStore.Downloads` + `RELATIVE_PATH = "Download/小説ダウンローダー"`。権限不要
- **API 24–28**: `Environment.getExternalStoragePublicDirectory(DIRECTORY_DOWNLOADS)/小説ダウンローダー/` へ直書き（`WRITE_EXTERNAL_STORAGE` を Manifest 宣言し実行時要求、`maxSdkVersion="28"`）
- 同名ファイルの衝突は MediaStore の自動リネーム（`タイトル (1).epub`）に任せる
- 保存対象はデフォルト **.epub のみ**。設定「テキスト(.txt)も保存する」ON で .txt もコピー（CLI に「txt を出さない」オプションは無いため、staging からのコピー選別で実現し本体無改造を守る）

## 8. GUI 設定 → CLI 引数マッピング

| GUI設定（⋮メニュー） | 既定値 | CLI引数 | 実装時期 |
|---|---|---|---|
| （固定）リクエスト間隔 | 1.5秒 | `--delay 1.5`（UI非公開） | — |
| 横書きにする | OFF | `--horizontal` | MVP |
| Kobo用拡張子 (.kepub.epub) | OFF | `--kobo` | MVP |
| サイトの表紙画像を使う | OFF | `--use-site-cover` | MVP |
| テキスト(.txt)も保存する | OFF | （コピー選別で実現） | MVP |
| 話数範囲（開始/終了） | 全話 | `--start N` / `--end N` | M3 |
| 埋め込みフォント | なし | `--font`（同梱TTF） | M3 |
| 続きから再開 | — | `--resume` / `--append` | 将来 |

- 設定は `SharedPreferences` に永続化
- `-o` は使わず、本体のタイトル自動命名に任せる

## 9. エラー処理

| 事象 | 挙動 |
|---|---|
| 未対応URL | DL開始前にバッジで警告、ボタン無効化 |
| 接続エラー・HTTPエラー | 本体のリトライ（3回）後に失敗 → ERROR 状態。ログ自動展開＋通知「❌ 失敗: 作品名」 |
| 中止 | CANCELLED 状態。「中止しました」表示。staging 破棄 |
| Python例外（想定外） | traceback をログに全文表示。ERROR 状態 |
| 機内モード等の事前検出 | DL開始時に `ConnectivityManager` で接続確認し、オフラインなら即エラー表示（1.5秒×リトライを待たせない） |

終了コード規約: `0`=成功 / `130`=中止 / その他=エラー（bridge が Kotlin へ返す）。

## 10. マイルストーン

| M | 内容 | 完了基準 |
|---|---|---|
| **M1 (MVP)** | 本体GUI連携API実装（§5.1、CLIで回帰確認）・本体同梱・bridge（run/cancel/detect）・メイン画面・Foreground Service・進捗表示・中止・Downloads保存 | なろう／カクヨムの実作品URLを貼り付け→実機のDownloadsに .epub が保存され、ePubリーダーで開ける。中止が2秒以内に効く |
| **M2** | 共有インテント受け取り・完了カード（開く/共有）・完了/エラー通知・サイト判定バッジ精緻化 | ブラウザの共有→アプリ起動→ワンタップDLが通る |
| **M3** | 設定メニュー（縦横/Kobo/サイト表紙/txt保存/話数範囲）・アプリアイコン・表紙フォント同梱 | 全16サイトをヘルスチェックURLで実機確認 |
| 将来 | `--resume`/`--append`（同名txt検出時「続きから」提案）、`--from-file`、履歴画面 | — |

## 11. リスク・検討事項

| リスク | 影響 | 対策 |
|---|---|---|
| Chaquopy pip に Pillow の Python 3.10 用 wheel が無い | JPEG表紙が作れない | 本体が SVG 表紙へ自動フォールバックするため機能は維持。wheel の有無は M1 実装初日に確認 |
| requests / beautifulsoup4 の wheel | これが無いと対応サイトが激減 | 両方とも pure Python 主体で Chaquopy 実績あり。lxml は使っていない（bs4 は html.parser）ため問題なし見込み |
| 長時間DL（1000話 ≈ 25分超）中の省電力キル | DL失敗 | Foreground Service で大幅に軽減。メーカー独自の電池最適化（Xiaomi等）は既知の限界としてREADMEに記載 |
| `_find_cjk_fonts()` が import 時に実行され数秒かかる可能性 | 初回起動が遅い | `NOVEL_DL_COVER_FONT`（§5.1-5）を bridge が import 前に環境変数設定するため探索自体が走らない |
| 本体 API 改修による CLI デグレード | 既存ユーザーに影響 | 未使用時不活性の設計＋ M1 で `--dry-run`・なろう実DLの回帰確認。`time.sleep`→`_sleep` は機械置換で差分レビュー容易 |
| Python 3.10 固定（Chaquopy 17 デフォルト） | 本体が将来 3.11+ 構文を使うと壊れる | 本体は 3.10+ 要件で現状一致。`version = "3.13"` への引き上げを M3 で検証 |
| 「開く」で ePub を開けるリーダーが端末に無い | 完了後に行き止まり | `ACTION_VIEW` 失敗時は「ePubリーダーアプリをインストールしてください」トースト |

## 12. 決定事項サマリー

- 本体に GUI 連携 API を実装（`main(argv)`・`ABORT_EVENT`/`AbortRequested`・終了コード130・`PROGRESS_CALLBACK`・`NOVEL_DL_COVER_FONT`）。未使用時不活性で CLI 挙動不変。Windows GUI とも共通利用
- bridge.py は「API への接続」だけを担う薄い層（argv 組立・stdout 捕捉・コールバック中継）
- Foreground Service で直列 1 件実行、キューなし
- クリップボードは明示ボタン方式（自動読み取りしない）
- 保存先は Download/小説ダウンローダー/、既定は .epub のみ
- オプションは最小限（⋮メニュー内 3〜5 項目）、`-o`・`--delay` 等は非公開
