package com.ayati.noveldownloader

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * ダウンロード履歴の永続化層（設計書 android/design_history.md §5.3）。
 *
 * DownloadState はインメモリのシングルトンなのでプロセス終了で消える。
 * 「どこに何を保存したか」だけを filesDir/history.json に残し、
 * 再起動後も開く／共有ができるようにする。
 *
 * 書き込みは一時ファイル + rename の原子的操作。途中でプロセスが死んでも
 * 既存ファイルは壊れない（本体 Python の _save_watch_cache と同じ作法）。
 */
object DownloadHistory {

    private const val FILE = "history.json"
    private const val TMP = "history.json.tmp"
    private const val SCHEMA = 1
    private const val MAX = 200
    private const val SUBDIR = "小説ダウンローダー"

    /** 履歴1件。files の先頭は必ず .epub（DownloadService の並びを踏襲）。 */
    data class Entry(
        val id: String,
        val savedAt: Long,
        val title: String,
        val sourceUrl: String,
        val siteName: String,
        val episodeCount: Int,
        val files: List<DownloadState.SavedFile>,
        /** 直近の新着チェックの結果（design_history.md §13.7）。未確認なら null。 */
        val lastCheck: Check? = null,
    ) {
        /** 追記の材料になる .txt（無ければ null）。 */
        val txt: DownloadState.SavedFile? get() = files.firstOrNull { it.name.endsWith(".txt") }
        /** 開く対象の .epub（無ければ null）。 */
        val epub: DownloadState.SavedFile? get() = files.firstOrNull { it.name.endsWith(".epub") }
    }

    /**
     * 新着チェックの結果。status は updated / uptodate / nolocal / error。
     * nolocal = 手元に .txt が無く、サイト側の総数（total）だけ分かった。
     */
    data class Check(
        val at: Long,
        val status: String,
        val existing: Int = 0,
        val total: Int = 0,
        val newTitles: List<String> = emptyList(),
        val error: String = "",
    ) {
        val newCount: Int get() = if (status == "updated") (total - existing).coerceAtLeast(0) else 0
    }

    /** 保存する新着の題名の上限（§13.7。935 話の作品で履歴が肥大しないように）。 */
    private const val MAX_NEW_TITLES = 20

    fun newId(): String =
        "${System.currentTimeMillis()}-${(0..0xFFFF).random().toString(16)}"

    /**
     * ファイル名から表示用のタイトルを作る。
     * --kobo の «作品名.kepub.epub» を考慮して既知の拡張子を順に剥がす
     * （substringBeforeLast('.') だけだと «作品名.kepub» が残る）。
     */
    fun titleOf(name: String): String =
        name.removeSuffix(".epub").removeSuffix(".kepub").removeSuffix(".txt")

    // ── 読み書き ────────────────────────────────────────────────

    /** 新しい順の履歴を返す。読めない・スキーマ不一致なら空（ファイルには触らない）。 */
    @Synchronized
    fun load(ctx: Context): List<Entry> {
        val f = File(ctx.filesDir, FILE)
        if (!f.exists()) return emptyList()
        return try {
            val root = JSONObject(f.readText())
            if (root.optInt("schema") != SCHEMA) return emptyList()
            val arr = root.optJSONArray("entries") ?: return emptyList()
            (0 until arr.length()).mapNotNull { arr.optJSONObject(it)?.toEntry() }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /** 先頭（＝最新）へ追加し、MAX を超えた分は古い順に捨てる。 */
    @Synchronized
    fun add(ctx: Context, entry: Entry) {
        save(ctx, (listOf(entry) + load(ctx)).take(MAX))
    }

    @Synchronized
    fun get(ctx: Context, id: String): Entry? = load(ctx).firstOrNull { it.id == id }

    /**
     * 同じ id の行を差し替えて先頭へ移す（追記・取り直しの後。§12 決定5）。
     * 行が消えていたら（履歴画面で削除された等）先頭へ追加する。
     */
    @Synchronized
    fun update(ctx: Context, entry: Entry) {
        save(ctx, (listOf(entry) + load(ctx).filterNot { it.id == entry.id }).take(MAX))
    }

    /** 新着チェックの結果（と、分かればサイト名）を書き込む。並び順は変えない。 */
    @Synchronized
    fun setCheck(ctx: Context, id: String, check: Check, siteName: String = ""): Entry? {
        val c = check.copy(newTitles = check.newTitles.take(MAX_NEW_TITLES))
        var hit: Entry? = null
        save(ctx, load(ctx).map {
            if (it.id != id) it
            else it.copy(lastCheck = c, siteName = it.siteName.ifEmpty { siteName }).also { e -> hit = e }
        })
        return hit
    }

    @Synchronized
    fun remove(ctx: Context, id: String) {
        save(ctx, load(ctx).filterNot { it.id == id })
    }

    @Synchronized
    fun clear(ctx: Context) {
        save(ctx, emptyList())
    }

    @Synchronized
    private fun save(ctx: Context, entries: List<Entry>) {
        val root = JSONObject()
            .put("schema", SCHEMA)
            .put("entries", JSONArray().apply { entries.forEach { put(it.toJson()) } })
        val tmp = File(ctx.filesDir, TMP)
        val dst = File(ctx.filesDir, FILE)
        try {
            tmp.writeText(root.toString())
            if (!tmp.renameTo(dst)) {      // 環境によっては既存ファイルがあると失敗する
                dst.delete()
                tmp.renameTo(dst)
            }
        } catch (e: Exception) {
            tmp.delete()
        }
    }

    // ── JSON 変換 ───────────────────────────────────────────────

    private fun Entry.toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("savedAt", savedAt)
        .put("title", title)
        .put("sourceUrl", sourceUrl)
        .put("siteName", siteName)
        .put("episodeCount", episodeCount)
        .put("files", JSONArray().apply {
            files.forEach {
                put(JSONObject()
                    .put("name", it.name)
                    .put("uri", it.uri)
                    .put("mime", it.mime))
            }
        })
        .apply { lastCheck?.let { put("lastCheck", it.toJson()) } }

    private fun Check.toJson(): JSONObject = JSONObject()
        .put("at", at)
        .put("status", status)
        .put("existing", existing)
        .put("total", total)
        .put("newTitles", JSONArray(newTitles))
        .put("error", error)

    private fun JSONObject.toCheck(): Check? {
        val status = optString("status")
        if (status.isEmpty()) return null
        val titles = optJSONArray("newTitles")
        return Check(
            at = optLong("at"),
            status = status,
            existing = optInt("existing"),
            total = optInt("total"),
            newTitles = if (titles == null) emptyList()
                        else (0 until titles.length()).map { titles.optString(it) },
            error = optString("error"),
        )
    }

    private fun JSONObject.toEntry(): Entry? {
        val arr = optJSONArray("files") ?: return null
        val files = (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            val uri = o.optString("uri")
            if (uri.isEmpty()) null
            else DownloadState.SavedFile(o.optString("name"), uri, o.optString("mime"))
        }
        if (files.isEmpty()) return null
        val id = optString("id").ifEmpty { newId() }
        return Entry(
            id = id,
            savedAt = optLong("savedAt"),
            title = optString("title").ifEmpty { titleOf(files[0].name) },
            sourceUrl = optString("sourceUrl"),
            siteName = optString("siteName"),
            episodeCount = optInt("episodeCount"),
            files = files,
            lastCheck = optJSONObject("lastCheck")?.toCheck(),
        )
    }

    // ── 実体の存在確認（設計書 §4.6） ───────────────────────────

    /**
     * ファイルが消えている履歴の id を返す。
     * 自動削除はしない（SD 未マウント等の一時的な不可視で履歴を失わないため）。
     * バックグラウンドスレッドから呼ぶこと。
     */
    fun validate(ctx: Context, entries: List<Entry>): Set<String> =
        entries.filterNot { e -> exists(ctx, e.files.first().uri) }
            .map { it.id }
            .toSet()

    fun exists(ctx: Context, uri: String): Boolean = try {
        ctx.contentResolver.openInputStream(Uri.parse(uri))?.use { true } ?: false
    } catch (e: Exception) {
        false
    }

    // ── 保存フォルダの取り込み（設計書 §4.7） ───────────────────

    /**
     * Download/小説ダウンローダー/ を走査し、履歴に無いファイルをエントリ化する。
     * 戻り値は取り込んだ件数。バックグラウンドスレッドから呼ぶこと。
     *
     * Scoped Storage 下でも自アプリが作成した MediaStore エントリは列挙できるため、
     * 履歴機能の導入以前にダウンロードしたファイルも取り込める。
     */
    @Synchronized
    fun importFolder(ctx: Context): Int {
        val current = load(ctx)
        val known = current.flatMap { e -> e.files.map { it.uri } }.toSet()
        val found = if (Build.VERSION.SDK_INT >= 29) scanMediaStore(ctx) else scanLegacy(ctx)

        // 同じベース名の .epub / .txt は 1 エントリにまとめる（.epub が先頭）
        val added = found
            .filterNot { it.first.uri in known }
            .groupBy { titleOf(it.first.name) }
            .map { (base, items) ->
                val sorted = items.sortedBy { !it.first.name.endsWith(".epub") }
                val txt = sorted.firstOrNull { it.first.name.endsWith(".txt") }?.first
                Entry(
                    id = newId(),
                    savedAt = sorted.maxOf { it.second },
                    title = base,
                    // .txt があれば「底本URL：」から拾う（§13.6）。無ければ不明のまま
                    sourceUrl = txt?.let { readSourceUrl(ctx, it.uri) }.orEmpty(),
                    siteName = "",
                    episodeCount = 0,
                    files = sorted.map { it.first },
                )
            }
        // 以前の取り込みで sourceUrl が空のまま残っている行も補う
        var patched = 0
        val fixed = current.map { e ->
            val t = e.txt
            if (e.sourceUrl.isNotEmpty() || t == null) return@map e
            val url = readSourceUrl(ctx, t.uri) ?: return@map e
            patched++
            e.copy(sourceUrl = url)
        }
        if (added.isEmpty() && patched == 0) return 0
        save(ctx, (fixed + added).sortedByDescending { it.savedAt }.take(MAX))
        return added.size + patched
    }

    /** http / https の URL か（ブラウザや本体へ渡してよい形か）。 */
    fun isWebUrl(url: String): Boolean {
        val u = try { Uri.parse(url) } catch (e: Exception) { return false }
        return (u.scheme == "http" || u.scheme == "https") && !u.host.isNullOrEmpty()
    }

    /**
     * .txt の先頭から「底本URL：」行を読む（本体の _extract_url_from_txt と同じ規則）。
     * ヘッダーは【あらすじ】より前に置かれるので先頭 8KB で足りる（§13.6）。
     */
    fun readSourceUrl(ctx: Context, uri: String): String? = try {
        ctx.contentResolver.openInputStream(Uri.parse(uri))?.use { input ->
            val buf = ByteArray(8192)
            val n = input.read(buf).coerceAtLeast(0)
            String(buf, 0, n, Charsets.UTF_8).lineSequence()
                .map { it.trim().removePrefix("\uFEFF") }
                .firstOrNull { it.startsWith("底本URL：") }
                ?.removePrefix("底本URL：")?.trim()
                ?.takeIf { isWebUrl(it) }
        }
    } catch (e: Exception) {
        null
    }

    /** (SavedFile, 更新日時ミリ秒) の一覧。 */
    private fun scanMediaStore(ctx: Context): List<Pair<DownloadState.SavedFile, Long>> {
        val out = mutableListOf<Pair<DownloadState.SavedFile, Long>>()
        val projection = arrayOf(
            MediaStore.MediaColumns._ID,
            MediaStore.MediaColumns.DISPLAY_NAME,
            MediaStore.MediaColumns.MIME_TYPE,
            MediaStore.MediaColumns.DATE_MODIFIED,
        )
        val relPath = Environment.DIRECTORY_DOWNLOADS + "/" + SUBDIR + "/"
        try {
            ctx.contentResolver.query(
                MediaStore.Downloads.EXTERNAL_CONTENT_URI, projection,
                "${MediaStore.MediaColumns.RELATIVE_PATH}=?", arrayOf(relPath), null
            )?.use { c ->
                val iId = c.getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
                val iName = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
                val iMime = c.getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE)
                val iDate = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED)
                while (c.moveToNext()) {
                    val name = c.getString(iName) ?: continue
                    if (!isTarget(name)) continue
                    val uri = ContentUris.withAppendedId(
                        MediaStore.Downloads.EXTERNAL_CONTENT_URI, c.getLong(iId))
                    out += DownloadState.SavedFile(
                        name, uri.toString(), c.getString(iMime) ?: mimeOf(name)
                    ) to c.getLong(iDate) * 1000L
                }
            }
        } catch (e: Exception) {
            // 列挙できない環境では取り込み 0 件として扱う
        }
        return out
    }

    private fun scanLegacy(ctx: Context): List<Pair<DownloadState.SavedFile, Long>> {
        val dir = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), SUBDIR)
        val files = dir.listFiles()?.filter { it.isFile && isTarget(it.name) }.orEmpty()
        return files.mapNotNull { f ->
            try {
                val uri = FileProvider.getUriForFile(
                    ctx, "${ctx.packageName}.fileprovider", f)
                DownloadState.SavedFile(f.name, uri.toString(), mimeOf(f.name)) to f.lastModified()
            } catch (e: Exception) {
                null
            }
        }
    }

    private fun isTarget(name: String) = name.endsWith(".epub") || name.endsWith(".txt")

    private fun mimeOf(name: String) =
        if (name.endsWith(".txt")) "text/plain" else "application/epub+zip"
}
