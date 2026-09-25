# Android 設計書: ダウンロード履歴

対象: `android/`（Kotlin 側のみ）
関連: `android/design_gui.md`（既存の GUI 設計）
**Python 本体（`novel_downloader.py` / `bridge.py`）の変更は不要**（根拠は §2.3）。

> **第2部（§10〜）を 2026-09-25 に追補**: 履歴からの「作品ページを開く」「新着チェック」「新着をダウンロード」。
> 第2部は `bridge.py` に関数を足す（本体 `novel_downloader.py` は無改修のまま）。

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

- ~~**同一作品のグループ化と更新差分（`--append` 相当）**~~ → **第2部（§10〜）で設計**
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

---
---

# 第2部: 履歴からの新着チェック・追記（2026-09-25 追補）

## 10. 目的と背景

### 10.1 解決したい問題

Windows / macOS の GUI には**本棚**（手元の `.txt` を一覧し、新着を確かめ、あれば差分だけ追記する）があるが、
Android の履歴でできるのは「開く／共有／もう一度ダウンロード（URL を入力欄に戻す）／削除」だけで、
**連載を追いかける使い方ができない**。更新を知るにはブラウザで作品ページを見に行き、
あればまるごと取り直すしかない（話数の多い作品ではそれ自体が §1.1 の問題を再発させる）。

### 10.2 ゴール

履歴の各行から次の3つができること。

1. **作品ページを開く** — 元サイトをブラウザで開く
2. **新着チェック** — サイト側の話数と手元を比べ、新着の有無と件数を出す
3. **新着をダウンロード** — 新着があれば**差分だけ**取得し、**同じ `.txt` / `.epub` を上書き**する

あわせて、設定に **「挿絵を取り込まない」**（`--no-inline-images`）を足す（§14）。

### 10.3 やらないこと（第2部のスコープ外）

- **履歴全体の一括チェック・定期チェック・新着通知**（WorkManager を使う別機能。1件ずつが動いてから）
- 表紙フォント・本文フォント・表紙画像の指定（次の版で別途設計）
- `--start` による途中からの取得

---

## 11. 調査結果（設計の根拠）

### 11.1 追記には `.txt` が要るが、既定では保存していない

本体の `--append FILE` は `.txt` の「底本URL：」行と節の数（＝取得済みの話数）を読んで続きから取る。
ところが `DownloadService` は設定 `save_txt`（既定 **false**）が立っていないと `.txt` を公開フォルダへコピーせず、
staging は完了時に消している。**既定の使い方では追記の材料が端末に残っていない。**

→ **`.txt` を常に保存する**（§12 決定1）。

### 11.2 履歴の `episodeCount` は話数ではない

`episodeCount` は `DownloadState.ui.value.total`、つまり `PROGRESS_CALLBACK` の `total` である。
これはサイトによって**何を数えているかが違う**（`run_*` の `_progress()` 呼び出しを確認）。

| サイト | `total` が数えるもの |
|---|---|
| なろう・カクヨム・アルファポリス・ハーメルン・ソリスピア・monogatary・ノベマ！・ノベルアップ＋・ステキブンゲイ・NOVEL DAYS | 取得対象の**話**数 |
| エブリスタ | **ページのまとまり**（`batch_list`） |
| 野いちご・berry's cafe | **章**数 |
| ネオページ・青空文庫・杉田玄白・結城浩 | `_progress()` を呼ばない → **0** |

したがって **`episodeCount` とサイト側の話数を引き算して新着を出してはいけない**
（エブリスタでは新着が無いのに「新着あり」になる）。

→ 新着の判定は**手元の `.txt` を正**とし、本体の `_check_update_one(txt)` に任せる。
これは PC の `--check-update` / 本棚と同じ判定で、`.txt` の節数と一覧の件数を同じ尺度で比べる。

> **エブリスタだけは要確認。** `.txt` の節は**ページ**ごと（2ページ目以降は `話題（2）` の節になる）で、
> `--append` の再開位置もページで数えるので追記は揃っている。一方、新着チェックの一覧は
> **`title` を持つページだけ**を並べる。1話が複数ページに分かれる作品では一覧の件数が節数より少なくなり、
> **新着があっても「新着なし」になる**おそれがある。
> 実測（2026-09-25・健康診断用の 26384598）では全ページに `title` があり、20ページ取得 → `--check-update` で
> 「既存 20 / サイト 148」と正しく出た。複数ページの話を持つ作品で確かめ、ずれるなら
> **本体側で直す**（チェック時の一覧をページ単位にする。PC の本棚にも効く修正で、Android 固有の問題ではない）。
あわせて、**履歴に出す話数も `.txt` の節数から取り直す**（§13.5）。

### 11.3 本体に必要な関数はすべて揃っている

| 用途 | 本体の入口 | 備考 |
|---|---|---|
| 新着チェック（`.txt` あり） | `_check_update_one(txt_path, delay)` | 戻り値 `{status, existing, total, new, new_titles, title, error}`。**ファイルに書き込まない** |
| 総話数だけ知る（`.txt` なし） | `_check_update_url(url, 0, delay)` | `status="init"` と `total` を返す（`--watch` の初回と同じ） |
| 追記 | `main(["--append", txt, …])` | CLI の `--append` と同じ経路。**新着が無ければファイルを書き換えない**。出力名は `.txt` の stem、出力先は `.txt` と同じディレクトリ |
| 節数 | `_load_existing_txt(txt_path)` | 追記前後の差＝追加話数 |

`--append` は `_append_one()` ではなく **`main()` の `--append` 経路**を使う。`_append_one()` は
`_make_runner_args()` に渡す項目を列挙しており **`no_inline_images` を引き継がない**ため、
§14 の設定が追記時に効かなくなる。`main()` 経由なら CLI オプションがそのまま効く。

→ **本体 `novel_downloader.py` は無改修**。`bridge.py` に薄い関数を足すだけで済む（§13.3）。

### 11.4 公開フォルダの `.txt` は読み書きできる

§2.2 のとおり、API 29+ で自アプリが `MediaStore` に挿入したファイルは**権限なしで読み書きできる**
（`openInputStream` / `openOutputStream`）。≤28 は `WRITE_EXTERNAL_STORAGE` の範囲内の実ファイル。
追記は「URI から staging へコピー → `--append` → 同じ URI へ書き戻す」で実現できる。

ただし次の場合は**読めない／中身が当てにならない**。

| 状況 | 起きること |
|---|---|
| 利用者がファイラーで削除・移動した | URI が無効 |
| **アプリを入れ直した**（アンインストール → 再インストール、データ消去） | ファイルは残るが所有者でなくなり、API 29+ では読めない。そもそも `history.json` も消えている |
| 利用者が `.txt` を編集した | 節数がずれる・「底本URL：」が消える可能性 |
| 第1部の時期に `save_txt=false` で取った作品 | `.txt` が存在しない |

→ **いずれの場合も「まるごと取り直す」へ落とす**（§13.4）。新着をダウンロードする機能自体は常に使える。

### 11.5 `openOutputStream(uri, "w")` は切り詰めない場合がある

Android 10 以降の一部の実装で、モード `"w"` が**既存の内容を切り詰めずに先頭から上書きする**
（新しい中身の方が短いと末尾に古いバイトが残り、ePub の ZIP が壊れる）。追記では `.epub` が
作り直されるので、サイズが縮むこともある（表紙画像が変わった場合など）。

→ 書き戻しは**必ずモード `"wt"`**（write + truncate）で開く。

### 11.6 Python エンジンは同時に2つ動かせない

bridge は `sys.stdout` / `sys.stderr` の差し替え、`PROGRESS_CALLBACK`、`ABORT_EVENT`、本体の
`_CHECK_UPDATE_MODE` といった**プロセス全体のグローバル**を触る。特に `_CHECK_UPDATE_MODE` は、
立っている間に走った `run_*` の `_show_episode_list()` が `_CheckUpdateDone` を投げる作りなので、
**ダウンロード中に新着チェックを走らせるとダウンロードが途中で壊れる**。

→ エンジン呼び出しを**プロセス内で1つに直列化**する（§13.2）。

---

## 12. 決定事項

| # | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 1 | `.txt` を保存するか | **常に `.txt` と `.epub` の両方を保存する。設定の「テキスト（.txt）も保存」は撤去** | 追記の材料を常に残すため（§11.1）。PC 版と同じ出力になり、スマホで取った `.txt` を PC の `--append-dir` / `--from-file` にそのまま使える。`.txt` の置き場所を1つに絞れるので、アプリ専用領域に隠しコピーを持つ案より内容のずれが起きない |
| 2 | 新着の判定に何を使うか | **手元の `.txt`**（`_check_update_one`）。履歴の `episodeCount` は使わない | §11.2。`episodeCount` はサイトによって話・章・ページ・0 のどれかで、比べられない |
| 3 | 新着の取り込み方 | **`--append` で差分だけ取り、既存の URI へ上書き** | 取り直しは話数の多い作品で時間がかかり、サイトにも負担。上書きしないと `作品名 (1).epub` が増える（§4.5 の挙動） |
| 4 | `.txt` が使えないとき | **確認ダイアログを出して、まるごと取り直す。結果は既存の URI へ上書き**（`.txt` が無ければ新規作成） | §11.4。ボタンを押せない状態を作らない |
| 5 | 同じ作品の履歴を追記後どう並べるか | **その行を更新して先頭へ移す**（新しい行は作らない） | 追記はファイル実体を増やさない。第1部 §4.5（別エントリで並べる）は「実体が2つある」ことが前提だった |
| 6 | 追記・取り直しの実行場所 | **既存の `DownloadService`（前景サービス）で行い、メイン画面で進捗を見せる** | 話数が多いと長時間かかる。プロセスが落ちても前景サービスなら続く。進捗表示・中止・通知の既存 UI をそのまま使える |
| 7 | 新着チェックの実行場所 | **履歴画面のコルーチン（IO スレッド）で行う**。前景サービスは使わない | 1件あたり数秒〜十数秒（目次ページ数 × 1.5 秒）。画面を離れても結果は `history.json` に残るので、途中で死んでも次回チェックし直せば済む |

---

## 13. 仕様

### 13.1 履歴の行 UI

```
┌──────────────────────────────────┐
│ 作品タイトル                         │
│ 小説家になろう ・ 123話 ・ 9月25日       │
│ 🆕 新着 3話（9月25日 20:14 確認）       │   ← 確認結果の行（確認したことがある場合だけ）
│ 作品タイトル.epub        🌐  🔄  📤  ⋮ │
│                       [⬇ 新着を取得]   │   ← 新着があるときだけ出る
└──────────────────────────────────┘
```

| 部品 | 動作 | 出す条件 |
|---|---|---|
| 🌐 作品ページ | `ACTION_VIEW` で `sourceUrl` をブラウザで開く | `sourceUrl` が空でない |
| 🔄 新着チェック | §13.3 のチェックを実行。実行中は行にスピナー、ボタンは押せない | `sourceUrl` が空でない |
| ⬇ 新着を取得 | §13.4 の追記を開始し、メイン画面へ移って進捗を見せる | 直近のチェック結果が `new > 0` |
| 確認結果の行 | `🆕 新着 N話` / `新着なし` / `確認できませんでした` ＋確認日時 | 一度でも確認した |

- ⋮ メニューは従来どおり（共有 / もう一度ダウンロード / 履歴から削除）。**「もう一度ダウンロード」の中身は
  §13.4 の「まるごと取り直す」に変える**（入力欄に戻す旧動作は、別の設定で取り直したいときに使えたが、
  `(1)` 付きのファイルが増える原因でもあった）
- 🔄 と ⬇ は、**エンジンが使用中**（ダウンロード中、または別の行をチェック中）なら押せない（§13.2）
- ファイルが見つからない行（§4.6）でも 🌐 と 🔄 は使える。⬇ はまるごと取り直しになる

### 13.2 エンジンの直列化

`PyBridge` に**プロセス全体で1つのロック**を置き、bridge の関数はすべてこれを通して呼ぶ。

```kotlin
object PyBridge {
    /** エンジンは同時に1つしか動かせない（§11.6）。 */
    val engine = java.util.concurrent.locks.ReentrantLock()

    /** 取れなければ null（UI 側は「ダウンロード中です」を出す）。 */
    fun <T> tryWithEngine(block: () -> T): T? =
        if (engine.tryLock()) try { block() } finally { engine.unlock() } else null
}
```

- **新着チェック**は `tryWithEngine`。取れなければトースト「ダウンロード中はチェックできません」
- **ダウンロード／追記**（`DownloadService`）は `engine.lock()` で**待つ**。チェックは長くても十数秒なので、
  チェック中に開始されても少し遅れて始まるだけで済む。待っている間の状態は「準備中」のまま
- `detect()`（オフライン・即時）はロック対象外。ただし**グローバルを触らないわけではない**:
  話数 URL の正規化で出る `[情報]…` を捨てるため `contextlib.redirect_stdout` を使い、プロセス全体の
  `sys.stdout` を一瞬差し替える。ダウンロード中に URL 欄を打ち換えると、その間のログ行が数行欠けることがある
  （第1部からの既存の挙動・実害はログの欠けだけ。2026-09-26 レビューで判明し、ロックには入れず受け入れた。
  入力のたびにダウンロードの終了を待たせると、サイトバッジが出なくなるため）

### 13.3 新着チェックの流れ

```
[🔄]
 ├─ files に .txt がある？
 │   ├─ ある → .txt を staging_check/ へコピー（読めなければ「ない」へ）
 │   │         → bridge.check(txt) → _check_update_one
 │   │         → {status, existing, total, new, new_titles}
 │   └─ ない → bridge.check_url(url) → _check_update_url(url, 0)
 │             → {status:"init", total}  ＝「サイトは N話・追記には取り直しが必要」
 └─ 結果を history.json の該当行へ保存（lastCheck）→ 行を再描画
```

- `.txt` はコピーしてから渡す（Python に `content://` は開けない。チェックは読むだけだが、
  追記と同じ経路にしておくと失敗の扱いが揃う）
- `delay` は本体既定の 1.5 秒
- 失敗（`status="error"`）でも `lastCheck` に保存し、「確認できませんでした」と出す。**理由は ⋮ → 詳細で見られる**
  （`error` 文字列。本体の文言は日本語固定のものがある — `design_i18n.md` の P0 範囲外）
- `bridge.check*` は `sys.stdout` を捨てる（本体が一覧を print するため）

### 13.4 新着を取得（追記）／まるごと取り直す

`DownloadService` に**更新モード**を足す。Intent に `EXTRA_ENTRY_ID` があれば更新モード。

```
[⬇ 新着を取得] → MainActivity へ移動し DownloadService(EXTRA_URL, EXTRA_ENTRY_ID) を開始

DownloadService.work()（更新モード）
 1. engine.lock()
 2. 履歴から entry を読む
 3. entry の .txt URI を staging/<.txt の表示名> へコピー
      ├─ 成功 → 4a（追記）
      └─ 失敗 → 4b（まるごと）※ 押す前の確認ダイアログは §13.4.1
 4a. bridge.append(staging/xxx.txt, opts, listener)
       = main(["--append", txt, <設定の CLI 引数>]) ＋ 追記前後の節数の差を返す
       追加 0 話 → 「新着はありませんでした」で終了（書き戻さない）
 4b. bridge.run(url, opts, listener)（通常ダウンロードと同じ）
 5. staging の .epub / .txt を書き戻す
       entry にその種類の URI があり、開ける → そこへ "wt" で上書き（§11.5）
       無い／開けない                      → saveToDownloads() で新規作成
 6. 節数を数え直し（bridge.count(txt)）、entry を更新して先頭へ移す（§12 決定5）
       savedAt=今、episodeCount=節数、files=書き戻した URI、lastCheck=クリア
```

- **出力名**: `--append` は `.txt` の stem を出力名にするので、`作品名 (1).txt` なら `作品名 (1).epub` ができる。
  書き戻し先は URI で決めるので名前は問題にならない
- **`--kobo` を途中で切り替えた場合**: staging にできる `.kepub.epub` を既存の `.epub` の URI へ書く。
  中身は同じ ePub なので読めるが、**拡張子は元のまま**。拡張子まで変えたいなら「履歴から削除」→ 新規ダウンロード
- **追記は現在の設定で ePub 全体を作り直す**（横書き・Kobo・サイト表紙・挿絵）。PC の `--append` と同じ
- 中止（終了コード 130）・失敗のときは**書き戻さない**。元のファイルは無傷で残る
- 完了カードは通常のダウンロードと同じ。見出しは「✅ 3話追加しました」、追加 0 なら「新着はありませんでした」

#### 13.4.1 まるごと取り直すときの確認

`.txt` が使えないと分かっている場合（行に `.txt` が無い・直近の検証で開けなかった）、⬇ を押した時点で確認する。

> **まるごと取り直します**
> 手元のテキストが見つからないため、差分だけの追記ができません。
> 最初からダウンロードし直して、今のファイルを置き換えます。（N話・数分かかることがあります）
> ［取り直す］［やめる］

実行中に初めて分かった場合（コピーに失敗）は、ダイアログを出せないので**そのまま取り直し**、ログに理由を書く。

### 13.5 `.txt` の常時保存と話数の取り直し

- `DownloadService` の `saveTxt` 分岐を削除し、`.epub` と `.txt` を常に保存する
- 設定ダイアログから「テキスト（.txt）も保存」を削除。**`save_txt` の値は読まない**（残っていても無害）
- 保存後、`bridge.count(staging/xxx.txt)` で**節数を数えて `episodeCount` に入れる**（§11.2）。
  `run()` の進捗 `total` は使わない

### 13.6 取り込み（§4.7）で底本 URL を拾う

「保存フォルダを取り込む」で `.txt` を含むエントリを作るとき、**`.txt` の先頭部分から `底本URL：` 行を読んで
`sourceUrl` に入れる**。これで取り込んだ作品にも 🌐 / 🔄 / ⬇ が効く。

- Kotlin で先頭 8KB だけ読み、行頭 `底本URL：` を探す（本体の `_extract_url_from_txt` と同じ規則。
  ヘッダーは `【あらすじ】` の前に置かれるので 8KB で足りる）
- `siteName` は空のまま（最初のチェックで `_check_update_one` は返さないので、`bridge.detect(url)` で埋める）
- **既に取り込み済みで `sourceUrl` が空の行も、次回の取り込みで補う**（URI が一致する行の `sourceUrl` だけ更新）

### 13.7 保存スキーマの追加項目

`schema` は **1 のまま**。追加項目はすべて任意で、無ければ既定値として読む（旧版アプリが読み書きしても落ちない。
旧版で書き戻すと追加項目は消えるが、次のチェックで復元できる情報しか持たない）。

```json
{
  "id": "…", "savedAt": 0, "title": "…", "sourceUrl": "…", "siteName": "…",
  "episodeCount": 123,
  "files": [ … ],
  "lastCheck": {
    "at": 1758799000000,
    "status": "updated",          // updated / uptodate / nolocal / error
    "existing": 120,
    "total": 123,
    "newTitles": ["第121話 …", "第122話 …", "第123話 …"],
    "error": ""
  }
}
```

- `nolocal` = `.txt` が無く `check_url` で総数だけ取れた
- `newTitles` は最大 20 件に切り詰めて保存（行の ⋮ → 詳細で一覧を見せる）

---

## 14. 設定: 挿絵を取り込まない

- 設定ダイアログに **「挿絵を取り込まない」**（key `no_inline_images`・既定 false）を追加し、
  `bridge.run` / `bridge.append` で `--no-inline-images` を付ける
- 説明文: 「サイトの変更で挿絵の取得に失敗し続けるときに使います。表紙には影響しません」
- 本体側の挙動は CLAUDE.md の `--no-inline-images` の項のとおり（なろう・アルファポリス・ノベルアップ＋・
  エブリスタ・NOVEL DAYS の挿絵を一括で無効化）

---

## 15. 実装設計

### 15.1 変更するファイル

| ファイル | 内容 |
|---|---|
| `python/bridge.py` | `check(txt)` / `check_url(url)` / `append(txt, opts, listener)` / `count(txt)` を追加。`run()` と `append()` の CLI 引数組み立てを共通化し `no_inline_images` を追加 |
| `PyBridge.kt` | `engine` ロックと `tryWithEngine`（§13.2） |
| `DownloadService.kt` | 更新モード（§13.4）、`.txt` 常時保存と節数（§13.5）、`"wt"` での書き戻し（§11.5）、`engine.lock()` |
| `DownloadHistory.kt` | `lastCheck` の読み書き、`update(entry)`（行の差し替え＋先頭へ）、取り込み時の `底本URL：` 読み取り（§13.6） |
| `HistoryActivity.kt` | 🌐 / 🔄 / ⬇、確認結果の行、チェック中のスピナー、まるごと取り直しの確認、⋮ の「もう一度ダウンロード」の中身差し替え |
| `res/layout/item_history.xml` | ボタン3つと確認結果の行 |
| `MainActivity.kt` | 設定から `save_txt` を撤去し `no_inline_images` を追加。更新モードの完了カードの見出し |
| `res/values*/strings.xml` | 追加文言（日英。`design_i18n.md` に従う） |

**`novel_downloader.py` は無改修**（§11.3）。

### 15.2 `bridge.py` の追加

```python
def _cli_opts(opts: dict) -> list:
    """設定 → CLI 引数（run / append で共通）。"""
    argv = []
    for key, flag in (("horizontal", "--horizontal"), ("kobo", "--kobo"),
                      ("use_site_cover", "--use-site-cover"),
                      ("no_inline_images", "--no-inline-images")):
        if opts.get(key):
            argv.append(flag)
    return argv

def check(txt_path: str) -> str:
    """_check_update_one の結果を JSON で返す。ファイルは書き換えない。"""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        r = nd._check_update_one(txt_path, 1.5)
    return json.dumps(r, ensure_ascii=False)

def check_url(url: str) -> str:
    """.txt が無いとき用。_check_update_url(url, 0) → total だけ使う。"""

def count(txt_path: str) -> int:
    """.txt の節数（＝取得済みの話数）。"""
    return len(nd._load_existing_txt(txt_path)[0])

def append(txt_path: str, options_json: str, listener) -> str:
    """--append を実行し {"code": int, "added": int} を JSON で返す。

    run() と同じ listener・stdout 差し替え・ABORT_EVENT の扱いにする
    （共通部分は _run_main(argv, listener) に切り出す）。
    """
```

- `check` は `_check_update_one`（`checkresult` イベントを出す薄いラッパ）を呼ぶ。イベントの出力先は
  `--progress-json` 時だけ有効なので、Android では不活性
- `_check_update_one` は内部で `_CHECK_UPDATE_MODE` を立てて戻すので、**§13.2 のロックの内側で呼ぶこと**

### 15.3 書き戻し

```kotlin
/** staging のファイルを既存の URI へ上書きする。開けなければ false（呼び出し側が新規作成へ回す）。 */
private fun overwrite(file: File, uri: Uri): Boolean = try {
    contentResolver.openOutputStream(uri, "wt")?.use { out ->
        file.inputStream().use { it.copyTo(out) }
    } != null
} catch (e: Exception) { false }
```

≤28 の `FileProvider` URI は書き込み不可なので、`files` に記録している名前から実ファイルを引いて
`File.writeBytes` する（`scanLegacy` と同じディレクトリ）。

---

## 16. 動作確認

```
[新着チェック]
1. なろうの連載を取得 → 🔄 → 「新着なし」。確認日時が出る
2. .txt の末尾の話を1つ手で消す（または古い .txt を用意）→ 🔄 → 「新着 1話」と ⬇ が出る
3. エブリスタ・野いちご・berry's cafe で 1 と同じ → 「新着なし」になる（§11.2 の誤判定が起きない）
4. ダウンロード中に 🔄 → 「ダウンロード中はチェックできません」。ダウンロードは壊れない
5. 機内モードで 🔄 → 「確認できませんでした」。⋮ → 詳細に理由

[新着を取得]
6. 2 の状態で ⬇ → メイン画面で進捗 → 「1話追加しました」。Download フォルダに (1) 付きのファイルが増えていない
7. 追記後の .epub がリーダーで開け、最終話が入っている（"wt" で壊れていない）
8. 追記後の履歴行が先頭に移り、話数・日時が更新され、確認結果の行が消えている
9. 新着が無い状態で ⬇（チェック後に作者が話を消した等）→ 「新着はありませんでした」。ファイルの更新日時が変わらない
10. 追記中に中止 → 元のファイルが開ける（書き戻していない）

[まるごと取り直し]
11. ファイラーで .txt だけ削除 → ⬇ → 確認ダイアログ → 取り直し → 既存の .epub の URI に上書き、.txt は新規
12. 第1部の時期に取った（.txt の無い）行 → 🔄 で「サイトは N話」→ ⬇ で取り直し
13. ⋮ → もう一度ダウンロード → (1) 付きのファイルが増えない

[その他]
14. 🌐 でブラウザが作品ページを開く。sourceUrl の無い行では 🌐 / 🔄 が出ない
15. 保存フォルダを取り込む → .txt のある作品に sourceUrl が入り、🌐 / 🔄 が出る
16. 設定に「テキスト（.txt）も保存」が無く、新規ダウンロードで .txt と .epub の両方が保存される
17. 挿絵を取り込まない → なろうの挿絵入り作品で ePub に画像が入らない。追記でも同様
18. Kobo 形式で取った作品を追記 → .kepub.epub のまま開ける
```

**要確認（実装時に確かめる）**: 3 のエブリスタは §11.2 の注記のとおり、1話が複数ページの作品で確かめる。
野いちご・berry's cafe は、`.txt` の節と `_show_episode_list` の件数が
どちらも「章」で揃っている前提。PC の `--check-update` で実作品を1つずつ当てて、新着 0 になることを先に確かめる。

---

## 17. リスク

| リスク | 対策 |
|---|---|
| チェックとダウンロードの同時実行で本体のグローバルが混ざる | §13.2 のロック。チェックは `tryLock`、ダウンロードは待つ |
| 書き戻しで ePub が壊れる（切り詰め漏れ） | `"wt"`（§11.5）。確認項目 7 |
| 書き戻し途中でプロセスが死ぬ | 前景サービス内で行うので起きにくい。起きても `.txt` が残っていれば次の追記で `.epub` は作り直される。`.txt` が壊れた場合は §13.4 の取り直しへ落ちる |
| 利用者が `.txt` を編集して節数がずれる | 追記は「既存節数の次から」取るので重複・欠落が起きうる。PC の `--append` と同じ制約として受け入れ、取り直しで回復できることを案内する |
| Download フォルダのファイルが倍になる | PC 版と同じ出力として受け入れる（§12 決定1） |
| `episodeCount` の過去データが話数でない | 表示にしか使わない。追記・取り直しのたびに節数で置き換わる |

---

## 18. 実装メモ（2026-09-25）

設計（§10〜§17）からの差分と、実装時に決めた細部。

- **確認結果の保存は IO 側で行う**（`HistoryActivity.runCheck`）。画面を閉じるとコルーチンは取り消されるが、
  Chaquopy の呼び出しは止まらない。結果を受け取ってから保存する形だと、エンジンは最後まで走るのに結果だけ捨てられる
- **「新着を取得」は `MainActivity` を経由する**（`EXTRA_UPDATE_ENTRY_ID` / `EXTRA_UPDATE_URL` / `EXTRA_UPDATE_FORCE_FULL`）。
  API ≤28 の書き込み権限・API 33+ の通知権限の確認を、通常のダウンロードと同じ経路で通すため。
  `FLAG_ACTIVITY_CLEAR_TOP | SINGLE_TOP` で既存のメイン画面の `onNewIntent` に届く
- 行の ⋮ に「新着チェックの結果」を足した（確認結果の行のタップでも開く）。新着の題名（最大 20 件）か、失敗の理由を出す
- `DownloadState.Status` に `UPDATED`（arg=追加話数）/ `NO_NEW` を追加。新着 0 のときは完了カードに既存のファイルを出す
- 追記の `.txt` は staging に**元の表示名のまま**置く（`--append` は stem を出力名にするので、`作品名 (1).txt` でも `.epub` の名前が揃う）

### PC での bridge.py の確認（2026-09-25）

実サイト（カクヨム・218話の作品）で `bridge.py` の新関数を直接呼んで確認した。

| 手順 | 結果 |
|---|---|
| `run()` で全話を取得 → `count()` | 218 |
| 末尾2話を消して `check()` | `updated` / 手元 216・サイト 218・新着 2（題名2件） |
| `append()` | `{"code": 0, "added": 2}`、.txt は 218 節、.epub を再生成（2秒） |
| もう一度 `append()`（`no_inline_images` 付き） | `{"code": 0, "added": 0}`、**.epub を作らない**（本体は書き換えない） |
| `check()` | `uptodate` / 218・218 |

なろう（935話）でも `check()` が手元 250・サイト 935・新着 685 を正しく返すことを確認（17秒）。

### セキュリティレビューでの修正（2026-09-26）

| # | 内容 | 修正 |
|---|---|---|
| 1 | `MainActivity` は共有シートを受けるため `exported="true"`。§18 で足した `EXTRA_UPDATE_ENTRY_ID` / `EXTRA_UPDATE_URL` は**他のアプリからも送れ**、利用者の操作なしに前景サービスでダウンロードを始められた。さらに URL が `bridge.run()` の argv の先頭に置かれていたため、`--from-file=<アプリ専用領域のファイル>` のような値がオプションとして解釈され、そのファイルを ePub にして公開 Download フォルダへ出せた（PC で再現） | `EXTRA_UPDATE_URL` を廃止し、**履歴に実在する行の `sourceUrl`（http/https のみ）だけを使う**。`bridge.run()` は URL を `"--"` の後ろに置く（どこから来た値でもオプションにならない） |
| 2 | 「作品ページを開く」の URL が `startsWith("http")` だけの検査だった（取り込んだ `.txt` 由来の値もある） | `DownloadHistory.isWebUrl()`（scheme が http/https かつホストあり）で開く前と取り込み時に検査 |
| 3 | 回転対策に Intent の extra を消していたが、プロセス終了後の再生成では元の Intent が戻り、更新がもう一度始まった | `onCreate` では `savedInstanceState == null` のときだけ Intent を処理する |

1〜3 の修正後の APK（本番と同じリリース鍵）で、2026-09-26 に実機の動作確認済み。v2.17.0 でリリース。

**実機での確認（§16）: 2026-09-25 に確認済み**（本番と同じリリース鍵で署名した APK を既存アプリの上に入れて検証）。
