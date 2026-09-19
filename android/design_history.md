# Android 設計書: ダウンロード履歴

対象: `android/`（Kotlin 側のみ）
関連: `android/design_gui.md`（既存の GUI 設計）
**Python 本体（`novel_downloader.py` / `bridge.py`）の変更は不要**（根拠は §2.3）。

---

## 1. 目的と背景

### 1.1 解決したい問題

話数の多い作品はダウンロードに時間がかかる。ユーザーが他アプリへ切り替えている間に完了し、
その後アプリのプロセスが OS に終了させられると、**完了カード（開く／共有）が失われる**。
再起動後の画面には何も残っておらず、ファイラーアプリで保存先を探す羽目になる。

ダウンロード自体は成功しており、ファイルも `Download/小説ダウンローダー/` に残っている。
**失われているのは「どこに何を保存したか」という情報だけ**である。

### 1.2 ゴール

1. 過去のダウンロードを遡って一覧できる
2. 一覧から **開く** / **共有** が完了カードと同じワンタップでできる
3. アプリを再起動した直後でも、直近の成果物にすぐ手が届く

---

## 2. 調査結果（設計の根拠）

### 2.1 根本原因

`DownloadState` は `object`（インメモリのシングルトン）であり、`savedFiles` もそこにしかない。

```kotlin
object DownloadState {
    val ui = MutableStateFlow(Ui())   // savedFiles: List<SavedFile>
}
```

プロセスが死ねば消える。**永続化層が存在しないことが唯一の原因**で、保存処理やファイル自体に問題はない。

### 2.2 保存済み URI は再起動後も有効

`saveToDownloads()` が返す `uri` は再利用できる。

| API | 生成方法 | 永続性 |
|---|---|---|
| 29+ | `contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, …)` | **有効**。挿入したアプリが所有者なので、再起動後も権限なしで読める |
| ≤28 | `FileProvider.getUriForFile(…)` | **有効**。パスから決定的に生成され、`res/xml/file_paths.xml` の `Download/` が対象範囲。付与は `FLAG_GRANT_READ_URI_PERMISSION` で都度行う |

したがって**履歴に URI 文字列を保存しておけば、そのまま `ACTION_VIEW` / `ACTION_SEND` に渡せる**。
無効化する条件はただ一つ、**ユーザーが外部でファイルを消したとき**（→ §4.6 で扱う）。

### 2.3 Python 側の変更が不要な理由

履歴に必要な項目は、すべて Kotlin 側で既に得られる。

| 項目 | 入手元 | 追加実装 |
|---|---|---|
| ファイル名・URI・MIME | `saveToDownloads()` の戻り値 | なし |
| 話数 | `DownloadState.ui.value.total` | なし |
| 保存日時 | `System.currentTimeMillis()` | なし |
| 元 URL | `Intent` の `EXTRA_URL` | なし |
| サイト表示名 | `MainActivity` が `detect()` で取得済み | **Intent extra を1つ追加**するだけ |
| 作品タイトル | `.epub` のファイル名から拡張子を除去 | なし |

作品タイトルは本体の `safe_filename(title)` がファイル名の元なので、**ファイル名＝タイトル（60字で切り詰め・
記号を `_` 置換）**である。表示用途としてはこれで十分。

> **代替案（不採用）**: `bridge.run()` に `onMeta(json)` を足して正式なタイトルを受け取る方法もある。
> 正確さは上がるが Python 側の改修が必要になり、「Android だけの追加」という前提を崩す。
> 60字超の長題や記号を含む題を正確に出したくなった時点で再検討する。
> **本文ログから `タイトル ： …` を拾う方法は採らない** — Windows GUI で解消しようとしている
> stdout パースと同じ罠（`design_i18n.md` §2.2）を新規に作ることになる。

### 2.4 既存 UI を再利用できる

`activity_main.xml` の `done_card` は既に「ファイル名 ＋ 📖開く ＋ 📤共有」を持つ `MaterialCardView` で、
`MainActivity` の `openFile()` / `shareFile()` は `SavedFile` を受け取る形になっている。
**履歴から開く／共有は、この2メソッドをそのまま呼べる。**

### 2.5 【要修正】保存名が実ファイル名と食い違う場合がある

`saveToDownloads()` は `DownloadState.SavedFile(file.name, …)` と **staging 側のファイル名**を記録している。
しかし API 29+ の `MediaStore` は、同名ファイルが既にある場合 **`title (1).epub` のように自動でリネームする**。

現状は完了直後に表示するだけなので実害が小さいが、**履歴に残ると恒久的に誤った名前が残る**。
同じ作品を2回ダウンロードすれば必ず踏む。

→ 挿入後に `DISPLAY_NAME` を問い合わせて、実際の名前を記録する（§5.2）。

### 2.6 既存ファイルの取り込みが可能

Scoped Storage 下でも**自アプリが作成した MediaStore エントリは自分で列挙できる**。
`RELATIVE_PATH = Download/小説ダウンローダー/` で絞れば、**履歴機能の導入以前にダウンロードしたファイルも
一覧に取り込める**（API ≤28 はディレクトリを直接読む）。

ユーザーは既に「履歴に残っていないファイル」を複数抱えている状態なので、この取り込みは初回の体験を大きく変える。

---

## 3. 全体方針

| 論点 | 採用 | 理由 |
|---|---|---|
| 永続化 | **`filesDir/history.json`（一時ファイル＋`rename` の原子的書き込み）** | 依存追加ゼロ。本体 Python の `_save_watch_cache`（`tempfile` + `os.replace`）と同じ作法で揃う |
| Room / DataStore | 不採用 | 659 行のアプリに対し過剰。スキーマ管理・KSP 追加のコストが利得を上回る |
| SharedPreferences | 不採用 | 設定用であり、増え続けるレコードの置き場所としては不適 |
| 画面 | **`HistoryActivity`（`RecyclerView`）＋ メイン画面の「最近のダウンロード」** | 一覧は専用画面へ。メイン画面のミニマルさは維持しつつ、再起動直後の導線も確保 |
| 記録対象 | **成功して保存できたものだけ** | 失敗・中止は履歴ではなくログの領分 |
| 上限 | **200 件**（超過分は古い順に破棄） | ファイルサイズと描画コストの上限を固定する |

---

## 4. 仕様

### 4.1 保存スキーマ（`filesDir/history.json`）

```json
{
  "schema": 1,
  "entries": [
    {
      "id": "1758240000000-3f2a",
      "savedAt": 1758240000000,
      "title": "作品タイトル",
      "sourceUrl": "https://ncode.syosetu.com/nXXXXxx/",
      "siteName": "小説家になろう",
      "episodeCount": 123,
      "files": [
        {"name": "作品タイトル.epub", "uri": "content://media/…", "mime": "application/epub+zip"},
        {"name": "作品タイトル.txt",  "uri": "content://media/…", "mime": "text/plain"}
      ]
    }
  ]
}
```

- `entries` は**新しい順**で保持する（先頭が最新）
- `schema` は本プロジェクトの既存規約（`--detect-site` / `--list-sites` / watch キャッシュ）に合わせる。
  読み込み時に `schema != 1` なら**空として扱い、ファイルは上書きしない**（将来のダウングレード耐性）
- `id` は `savedAt` ＋ 乱数4桁。削除・重複判定に使う
- `files` の先頭は必ず `.epub`（既存の `sortedBy { !it.name.endsWith(".epub") }` を踏襲）

### 4.2 画面1: メイン画面の「最近のダウンロード」

**再起動直後に成果物へ手が届かない**という主訴に直接応える。

- `phase == IDLE` かつ履歴が1件以上あるとき、既存の `done_card` を**「最近のダウンロード」として表示**する
- カード見出しに `最近のダウンロード` を出し、直近1件のタイトル・ファイル名を表示。📖開く / 📤共有 はそのまま機能する
- ダウンロード開始時に隠し、完了時は従来どおり「✅ 完了」カードへ戻る
- カードのタップ（または「すべて見る」）で `HistoryActivity` へ

> 新規レイアウトは `done_card` の上に見出し `TextView` を1つ足すだけでよい。

### 4.3 画面2: 履歴一覧（`HistoryActivity`）

導線: メイン画面の ⋮ メニューに **「履歴」** を追加（既存は「設定」のみ）。

```
┌──────────────────────────────┐
│ ← ダウンロード履歴          ⋮ │   ⋮ = すべて削除 / 保存フォルダを取り込む
├──────────────────────────────┤
│ 作品タイトル                  │
│ 小説家になろう ・ 123話 ・ 3月21日 │   ← タップで開く
│ 作品タイトル.epub          📤 ⋮ │
├──────────────────────────────┤
│ 別の作品                      │
│ カクヨム ・ 48話 ・ 3月19日      │
│ 別の作品.epub              📤 ⋮ │
└──────────────────────────────┘
```

- 行タップ = **開く**（`files` の先頭＝`.epub`）
- 📤 = **共有**（`files` が2件以上なら `ACTION_SEND_MULTIPLE`）
- ⋮（行メニュー）= `共有` / `もう一度ダウンロード` / `履歴から削除`
  - **もう一度ダウンロード**: `sourceUrl` をメイン画面の入力欄へ渡して戻る（`Intent` の `EXTRA_TEXT` で既存の
    `handleShareIntent()` 相当の経路に載せる）。更新された作品を取り直す用途に効く
  - **履歴から削除**: 履歴の行を消すだけで、**ファイルは削除しない**。確認ダイアログを出し、その旨を明記する
- 空状態: `まだダウンロード履歴がありません`

### 4.4 日時の表示

`savedAt` を、今日なら `HH:mm`、今年なら `M月d日`、それ以前は `yyyy年M月d日` で出す。

### 4.5 重複（同じ作品の再ダウンロード）

**まとめず、別エントリとして時系列に並べる。** MediaStore が `作品名 (1).epub` として別ファイルを作るため、
実体が2つある以上は履歴も2件あるのが正しい。`sourceUrl` が同じ行は視覚的に同じタイトルで並ぶが、
日時とファイル名で区別できる。

### 4.6 ファイルが消えている場合

ユーザーが外部でファイルを消した場合、URI は無効になる。

- **一覧表示時に一括検証する。** API 29+ は `MediaStore` を `_id` で 1 クエリ、≤28 は `File.exists()`
- 無効な行は**グレーアウトし「ファイルが見つかりません」**と表示。タップでは開かず、
  「この履歴を削除しますか？」を出す
- **自動では消さない。** 外部ストレージの一時的な不可視（SD カード未マウント等）で履歴が消えるのを避ける

### 4.7 既存ファイルの取り込み（§2.6）

⋮ メニューの **「保存フォルダを取り込む」** で、`Download/小説ダウンローダー/` を走査して
履歴に無いファイルをエントリ化する。

- `savedAt` はファイルの更新日時（`DATE_MODIFIED`）
- `title` はファイル名から拡張子を除いたもの
- `sourceUrl` / `siteName` / `episodeCount` は**不明**として空にし、一覧では省略表示
  （`もう一度ダウンロード` はこの行では無効）
- 同名・同 URI が既にあればスキップ
- **初回起動時に自動実行はしない。** 勝手に履歴が生える挙動は分かりにくいので、明示操作に限る

---

## 5. 実装設計

### 5.1 追加・変更するファイル

| ファイル | 種別 | 内容 |
|---|---|---|
| `DownloadHistory.kt` | 新規 | 永続化層。`load` / `add` / `remove` / `clear` / `importFolder` / `validate` |
| `HistoryActivity.kt` | 新規 | 一覧画面。`RecyclerView` ＋ アダプタ（同ファイル内 inner class） |
| `FileActions.kt` | 新規 | 開く／共有の共通処理。完了カードと履歴一覧の両方から使う（実装時に追加） |
| `res/layout/activity_history.xml` | 新規 | Toolbar ＋ RecyclerView ＋ 空状態 TextView |
| `res/layout/item_history.xml` | 新規 | 1行分のレイアウト |
| `res/menu/history_menu.xml` | 新規 | すべて削除 / 保存フォルダを取り込む |
| `res/menu/main_menu.xml` | 変更 | 「履歴」を追加 |
| `activity_main.xml` | 変更 | `done_card` に見出し `TextView`（`done_heading`）を追加 |
| `MainActivity.kt` | 変更 | ⋮ に履歴を追加／IDLE 時に最近の1件を表示／`EXTRA_SITE_NAME` を渡す |
| `DownloadService.kt` | 変更 | 完了時に履歴へ追加／`DISPLAY_NAME` の問い合わせ（§2.5） |
| `AndroidManifest.xml` | 変更 | `HistoryActivity` の登録 |
| `app/build.gradle.kts` | 変更 | `androidx.recyclerview:recyclerview` を明示依存に追加 |

`SavedFile` は `DownloadState.SavedFile` をそのまま再利用する（`name` / `uri` / `mime` で過不足なし）。

> **実装時の追加 (1)**: 開く／共有は `MainActivity` の private メソッドだったため、そのままでは履歴画面から呼べない。
> `FileActions` オブジェクトへ切り出し、両画面が同じ実装を使う形にした（§2.4 の「再利用できる」を実際に成立させるための整理）。
> 複数ファイルの共有は `ACTION_SEND_MULTIPLE` に対応させている。
>
> **実装時の追加 (2)**: `DownloadHistory.titleOf()` を追加。`--kobo` 指定時のファイル名は `作品名.kepub.epub` で、
> `substringBeforeLast('.')` だと `作品名.kepub` が残るため、既知の拡張子を順に剥がす。
> 履歴の表示名と取り込み時のグループ化の両方で使う。

### 5.2 `DownloadService` の変更点

```kotlin
// 1) MediaStore 挿入後に実名を取り戻す（§2.5）
private fun actualDisplayName(uri: Uri, fallback: String): String =
    contentResolver.query(uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME),
                          null, null, null)?.use { c ->
        if (c.moveToFirst()) c.getString(0) else null
    } ?: fallback

// 2) 保存成功時に履歴へ1件追加する（work() の code==0 分岐内）
DownloadHistory.add(this, DownloadHistory.Entry(
    savedAt      = System.currentTimeMillis(),
    title        = saved.first().name.substringBeforeLast('.'),
    sourceUrl    = url,
    siteName     = intent.getStringExtra(EXTRA_SITE_NAME).orEmpty(),
    episodeCount = DownloadState.ui.value.total,
    files        = saved,
))
```

履歴書き込みは**ワーカースレッド上**（`work()` 内）で行うため、メインスレッドを塞がない。

### 5.3 `DownloadHistory` の骨格

```kotlin
object DownloadHistory {
    private const val FILE = "history.json"
    private const val SCHEMA = 1
    private const val MAX = 200

    data class Entry(
        val id: String = "${System.currentTimeMillis()}-${(0..0xFFFF).random().toString(16)}",
        val savedAt: Long,
        val title: String,
        val sourceUrl: String,
        val siteName: String,
        val episodeCount: Int,
        val files: List<DownloadState.SavedFile>,
    )

    @Synchronized fun load(ctx: Context): List<Entry>
    @Synchronized fun add(ctx: Context, e: Entry)      // 先頭へ挿入し MAX で切り詰め
    @Synchronized fun remove(ctx: Context, id: String)
    @Synchronized fun clear(ctx: Context)
    fun importFolder(ctx: Context): Int                // §4.7・戻り値は取り込み件数
    fun validate(ctx: Context, entries: List<Entry>): Set<String>  // 無効な id の集合
}
```

- 書き込みは `history.json.tmp` へ出してから `renameTo`。途中でプロセスが死んでも既存ファイルは壊れない
- 読み込み失敗・`schema` 不一致は**空リストを返し、ファイルには触らない**
- すべて `@Synchronized`。`Service` のワーカーと `Activity` から同時に触られうる

---

## 6. 動作確認

```
1. 通常の完了 → 履歴に1件増える。タイトル・サイト名・話数・日時が正しい
2. アプリを強制終了 → 再起動 → メイン画面に「最近のダウンロード」が出て、開く／共有が動く
3. 履歴画面 → 行タップで ePub リーダーが開く。📤 で共有シートが出る
4. 同じ作品を2回DL → 2件並ぶ。2件目のファイル名が実ファイル（`… (1).epub`）と一致する（§2.5 の検証）
5. ファイラーでファイルを削除 → 履歴画面でグレーアウト＋「ファイルが見つかりません」
6. 「保存フォルダを取り込む」→ 履歴に無い既存ファイルが取り込まれ、二重に増えない
7. 「履歴から削除」→ 行が消え、Download フォルダのファイルは残っている
8. 「もう一度ダウンロード」→ メイン画面に URL が入り、サイトバッジが出る
9. 201件目を追加 → 最古の1件が落ちる
10. 端末回転・API 24 実機 / API 35 実機の双方
```

### 確認結果（2026-09-19 / Android 16・Android 13 実機）

| # | 項目 | 結果 |
|---|---|---|
| 1 | 完了で履歴が1件増える | ✅ |
| 2 | 強制終了→再起動で「最近のダウンロード」が出る | ✅ |
| 3 | 履歴から開く／共有 | ✅ |
| 4 | 2回目の `… (1).epub` がファイル名と一致（§2.5 の検証） | ✅ |
| 5 | ファイル削除でグレーアウト | ✅ |
| 6 | 保存フォルダの取り込み | ✅ |
| 7 | 「履歴から削除」でファイルは残る | ✅ |
| 8 | 「もう一度ダウンロード」 | ✅ |
| 9 | 201件目で最古が落ちる | 未確認（手動検証は非現実的） |
| 10 | API 24 実機 | **未確認** |

**残る未確認は API 24 系の経路。** 検証した2機種はいずれも API 29 以上のため、`DownloadHistory.scanMediaStore()`
は通ったが `scanLegacy()`（`FileProvider` ＋ `WRITE_EXTERNAL_STORAGE` の旧経路）は一度も実行されていない。
`minSdk = 24` を維持するならいずれ実機かエミュレータでの確認が要る。

---

## 7. 決定事項サマリー

| # | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 1 | メイン画面に「最近のダウンロード」を出すか | **出す**（§4.2） | 主訴が「再起動したら何も残っていない」であり、履歴画面へ1タップ必要な状態では解決しきらない。既存 `done_card` の再利用で新規 UI はほぼ不要 |
| 2 | 同一作品の再ダウンロードをまとめるか | **まとめない。最新を上にした時系列で並べる**（§4.5） | 履歴であり、ファイル実体も別々に存在する。まとめると「どちらのファイルを開くのか」が曖昧になる |
| 3 | 「履歴から削除」でファイル実体も消すか | **消さない。履歴の行のみ削除**（§4.3 / §4.6） | 破壊的操作を履歴画面に置かない。確認ダイアログに「ファイルは削除されません」と明記する |

（2026-09-19 確定。以降の実装はこの3点を前提とする。）

---

## 8. スコープ外（将来の検討）

- **同一作品のグループ化と更新差分（`--append` 相当）** — 本体の `--append` を Android から使う話になり、
  履歴とは独立した機能。履歴に `sourceUrl` を持たせておくのはその布石でもある
- **失敗したダウンロードの履歴** — 現状はログで足りている
- **履歴のエクスポート／端末間同期**
- **正式なタイトルの取得**（§2.3 の代替案）

---

## 9. リスク

| リスク | 対策 |
|---|---|
| `history.json` の破損 | 一時ファイル＋`rename`。読み込み失敗時は空扱いで既存を温存 |
| URI が無効化して開けない | §4.6 の検証とグレーアウト。自動削除はしない |
| 保存名の食い違い（§2.5） | `DISPLAY_NAME` を問い合わせて実名を記録。確認項目4で検証 |
| 履歴が肥大して描画が重い | 上限 200 件。`RecyclerView` で再利用 |
| 「履歴から削除」をファイル削除と誤解される | 確認ダイアログに「ファイルは削除されません」と明記 |
| `importFolder` の重複登録 | URI 一致でスキップ |
