package com.ayati.noveldownloader

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ContentValues
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.IBinder
import android.provider.MediaStore
import androidx.core.app.NotificationCompat
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import kotlin.concurrent.thread

/**
 * ダウンロード実行用 Foreground Service。
 * 同時実行は 1 件のみ（実行中の開始要求は無視）。
 * 完了後、staging の .epub と .txt を Download/小説ダウンローダー/ へコピーする。
 *
 * EXTRA_ENTRY_ID があれば**更新モード**（design_history.md §13.4）: 履歴の .txt を
 * staging へコピーして --append で新着だけを追記し、結果を**その行の URI へ上書き**する。
 * .txt が使えなければ（または EXTRA_FORCE_FULL）まるごと取り直して同じく上書きする。
 */
class DownloadService : Service() {

    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_SITE_NAME = "site_name"
        /** 更新モード: 対象の履歴 id。 */
        const val EXTRA_ENTRY_ID = "entry_id"
        /** 更新モードで追記せず、まるごと取り直す（行メニューの「もう一度ダウンロード」）。 */
        const val EXTRA_FORCE_FULL = "force_full"
        const val ACTION_CANCEL = "com.ayati.noveldownloader.action.CANCEL"
        private const val CHANNEL_ID = "download"
        private const val NOTIF_ID_PROGRESS = 1
        private const val NOTIF_ID_RESULT = 2
        private const val SUBDIR = "小説ダウンローダー"
    }

    @Volatile
    private var running = false
    /** bridge.py が短縮URL展開後に判定したサイト名（detect 時点では未判定のことがある）。 */
    @Volatile
    private var resolvedSiteName = ""
    private var lastNotified = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(
            CHANNEL_ID, getString(R.string.notif_channel_name), NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when {
            intent?.action == ACTION_CANCEL -> {
                // GIL 待ちで ANR にならないようワーカーから呼ぶ
                thread { PyBridge.module.callAttr("cancel") }
            }
            intent?.getStringExtra(EXTRA_URL) != null && !running -> {
                running = true
                val notif = buildProgressNotification(getString(R.string.status_preparing), 0, 0)
                if (Build.VERSION.SDK_INT >= 29) {
                    startForeground(NOTIF_ID_PROGRESS, notif,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
                } else {
                    startForeground(NOTIF_ID_PROGRESS, notif)
                }
                val url = intent.getStringExtra(EXTRA_URL)!!
                val siteName = intent.getStringExtra(EXTRA_SITE_NAME).orEmpty()
                val entryId = intent.getStringExtra(EXTRA_ENTRY_ID)
                val forceFull = intent.getBooleanExtra(EXTRA_FORCE_FULL, false)
                thread { work(url, siteName, entryId, forceFull) }
            }
        }
        return START_NOT_STICKY
    }

    // ── ダウンロード本体（ワーカースレッド） ──────────────────────

    private fun work(url: String, siteName: String, entryId: String?, forceFull: Boolean) {
        DownloadState.reset()
        resolvedSiteName = ""
        DownloadState.ui.value = DownloadState.Ui(
            phase = DownloadState.Phase.PREPARING, status = DownloadState.Status.PREPARING)

        val staging = File(filesDir, "staging")
        // 新着チェックが終わるのを待つ（§13.2）。チェックは長くても十数秒
        PyBridge.engine.lock()
        try {
            staging.deleteRecursively()
            staging.mkdirs()
            val entry = entryId?.let { DownloadHistory.get(this, it) }
            doWork(url, siteName, entry, forceFull, staging)
        } finally {
            PyBridge.engine.unlock()
            staging.deleteRecursively()
            running = false
            stopSelf()
        }
    }

    private fun doWork(
        url: String, siteName: String, entry: DownloadHistory.Entry?,
        forceFull: Boolean, staging: File,
    ) {
        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        val opts = JSONObject()
            .put("output_dir", staging.path)
            .put("horizontal", prefs.getBoolean("horizontal", false))
            .put("kobo", prefs.getBoolean("kobo", false))
            .put("use_site_cover", prefs.getBoolean("use_site_cover", false))
            .put("no_inline_images", prefs.getBoolean("no_inline_images", false))

        // 更新モード: 手元の .txt を staging へ。読めなければまるごと取り直しへ落とす（§13.4）
        val appendTxt: File? = if (entry != null && !forceFull) {
            entry.txt?.let { copyIn(Uri.parse(it.uri), File(staging, it.name.replace('/', '_'))) }
        } else null
        if (entry != null && !forceFull && appendTxt == null) {
            DownloadState.appendLog(getString(R.string.log_append_fallback))
        }

        val listener = Listener()
        var added = -1
        val code = try {
            PyBridge.ensureStarted(applicationContext)
            if (appendTxt != null) {
                val r = JSONObject(PyBridge.module.callAttr(
                    "append", appendTxt.path, opts.toString(), listener).toString())
                added = r.optInt("added")
                r.optInt("code", 1)
            } else {
                PyBridge.module.callAttr("run", url, opts.toString(), listener).toInt()
            }
        } catch (e: Exception) {
            DownloadState.appendLog("[アプリ内エラー] $e")
            1
        }

        when (code) {
            0 -> {
                // 追記したが新着が無かった: 本体はファイルを書き換えていないので何もしない
                if (entry != null && appendTxt != null && added == 0) {
                    DownloadState.ui.value = DownloadState.ui.value.copy(savedFiles = entry.files)
                    finish(DownloadState.Phase.DONE, DownloadState.Status.NO_NEW)
                    return
                }
                val outputs = staging.listFiles { f ->
                    f.name.endsWith(".epub") || f.name.endsWith(".txt")
                }.orEmpty().sortedBy { !it.name.endsWith(".epub") }  // 完了カードの先頭は epub
                if (outputs.none { it.name.endsWith(".epub") }) {
                    DownloadState.appendLog("[アプリ内エラー] 保存対象の .epub がありません")
                    finish(DownloadState.Phase.ERROR, DownloadState.Status.FAILED)
                    return
                }
                // 話数は .txt の節数から取る。進捗の total はサイトによって章・ページ・0（§11.2）
                val episodes = outputs.firstOrNull { it.name.endsWith(".txt") }?.let {
                    try { PyBridge.module.callAttr("count", it.path).toInt() } catch (e: Exception) { 0 }
                } ?: 0
                val saved = outputs.mapNotNull { f ->
                    val target = entry?.let { if (f.name.endsWith(".txt")) it.txt else it.epub }
                    if (target != null && overwrite(f, Uri.parse(target.uri))) target
                    else saveToDownloads(f)
                }
                if (saved.none { it.name.endsWith(".epub") }) {
                    finish(DownloadState.Phase.ERROR, DownloadState.Status.FAILED)
                    return
                }
                DownloadState.ui.value = DownloadState.ui.value.copy(savedFiles = saved)
                val site = siteName.ifEmpty { resolvedSiteName }
                if (entry != null) {
                    DownloadHistory.update(this, entry.copy(
                        savedAt = System.currentTimeMillis(),
                        sourceUrl = entry.sourceUrl.ifEmpty { url },
                        siteName = entry.siteName.ifEmpty { site },
                        episodeCount = episodes,
                        files = saved,
                        lastCheck = null,
                    ))
                } else {
                    DownloadHistory.add(this, DownloadHistory.Entry(
                        id = DownloadHistory.newId(),
                        savedAt = System.currentTimeMillis(),
                        title = DownloadHistory.titleOf(saved.first().name),
                        sourceUrl = url,
                        siteName = site,
                        episodeCount = episodes,
                        files = saved,
                    ))
                }
                if (appendTxt != null) {
                    finish(DownloadState.Phase.DONE, DownloadState.Status.UPDATED, added.toString())
                } else {
                    finish(DownloadState.Phase.DONE, DownloadState.Status.DONE,
                        saved.joinToString { it.name })
                }
            }
            130 -> finish(DownloadState.Phase.CANCELLED, DownloadState.Status.CANCELLED)
            else -> finish(DownloadState.Phase.ERROR, DownloadState.Status.FAILED)
        }
    }

    /** 公開フォルダのファイルを staging へコピーする。読めなければ null。 */
    private fun copyIn(uri: Uri, dst: File): File? = try {
        contentResolver.openInputStream(uri)?.use { input ->
            dst.outputStream().use { input.copyTo(it) }
            dst
        }
    } catch (e: Exception) {
        null
    }

    /**
     * staging のファイルを既存の URI へ上書きする。開けなければ false（呼び出し側が新規作成へ回す）。
     * **モードは必ず "wt"**。"w" は実装によって切り詰めず、新しい ePub の方が短いと
     * 末尾に古いバイトが残って ZIP が壊れる（§11.5）。
     */
    private fun overwrite(file: File, uri: Uri): Boolean = try {
        contentResolver.openOutputStream(uri, "wt")?.use { out ->
            file.inputStream().use { it.copyTo(out) }
            true
        } ?: false
    } catch (e: Exception) {
        false
    }

    private fun finish(phase: DownloadState.Phase, status: DownloadState.Status, arg: String = "") {
        DownloadState.ui.value =
            DownloadState.ui.value.copy(phase = phase, status = status, statusArg = arg)
        stopForeground(STOP_FOREGROUND_REMOVE)
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(statusText(status, arg))
            .setContentIntent(openAppIntent())
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(NOTIF_ID_RESULT, notif)
    }

    /** 通知タップでメイン画面を開く PendingIntent。 */
    private fun openAppIntent(): PendingIntent =
        PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

    // ── Python からのコールバック受け口 ──────────────────────────

    inner class Listener {
        fun onLine(text: String) {
            DownloadState.appendLog(text)
            if (text.isNotBlank()) {
                DownloadState.ui.value = DownloadState.ui.value.copy(
                    status = DownloadState.Status.RAW, statusArg = text.trim())
            }
        }

        fun onProgress(n: Int, total: Int) {
            DownloadState.ui.value = DownloadState.ui.value.copy(
                phase = DownloadState.Phase.DOWNLOADING, n = n, total = total)
            val now = System.currentTimeMillis()
            if (now - lastNotified > 900) {
                lastNotified = now
                getSystemService(NotificationManager::class.java).notify(
                    NOTIF_ID_PROGRESS, buildProgressNotification(
                        getString(R.string.progress_episodes, n, total), n, total))
            }
        }

        /**
         * bridge.py が短縮URLを展開して判定したサイト名を受け取る。
         * detect() はオフライン即時判定なので短縮URLではサイトが分からず、
         * そのままだと履歴の配信元が空になる。
         */
        fun onMeta(json: String) {
            try {
                val name = JSONObject(json).optString("display_name")
                if (name.isNotEmpty()) resolvedSiteName = name
            } catch (e: Exception) {
                // サイト名は補助情報。取れなくてもダウンロードには影響しない
            }
        }

        fun onPhase(phase: String) {
            val p = when (phase) {
                "PREPARING" -> DownloadState.Phase.PREPARING
                "DOWNLOADING" -> DownloadState.Phase.DOWNLOADING
                "SAVING" -> DownloadState.Phase.SAVING
                else -> return
            }
            DownloadState.ui.value = DownloadState.ui.value.copy(phase = p)
        }
    }

    // ── 通知・保存ユーティリティ ─────────────────────────────────

    private fun buildProgressNotification(text: String, n: Int, total: Int) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setContentIntent(openAppIntent())
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setProgress(if (total > 0) total else 0, n, total <= 0)
            .build()

    /**
     * MediaStore が実際に付けた表示名を返す。
     * 同名ファイルが既にある場合 MediaStore は「作品名 (1).epub」へ自動リネームするため、
     * staging 側の名前をそのまま記録すると履歴に誤った名前が残る（設計書 §2.5）。
     */
    private fun actualDisplayName(uri: android.net.Uri, fallback: String): String = try {
        contentResolver.query(
            uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: fallback
    } catch (e: Exception) {
        fallback
    }

    /** staging のファイルを公開 Downloads へコピーし、開く/共有に使える SavedFile を返す。 */
    private fun saveToDownloads(file: File): DownloadState.SavedFile? {
        val mime = when {
            file.name.endsWith(".epub") -> "application/epub+zip"
            file.name.endsWith(".txt") -> "text/plain"
            else -> "application/octet-stream"
        }
        return try {
            if (Build.VERSION.SDK_INT >= 29) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
                    put(MediaStore.MediaColumns.MIME_TYPE, mime)
                    put(MediaStore.MediaColumns.RELATIVE_PATH,
                        Environment.DIRECTORY_DOWNLOADS + "/" + SUBDIR)
                }
                val uri = contentResolver.insert(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
                contentResolver.openOutputStream(uri)?.use { out ->
                    file.inputStream().use { it.copyTo(out) }
                } ?: return null
                DownloadState.SavedFile(actualDisplayName(uri, file.name), uri.toString(), mime)
            } else {
                val dir = File(Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS), SUBDIR)
                dir.mkdirs()
                var dst = File(dir, file.name)
                var i = 1
                while (dst.exists()) {
                    dst = File(dir, "${file.nameWithoutExtension} ($i).${file.extension}")
                    i++
                }
                file.copyTo(dst)
                MediaScannerConnection.scanFile(this, arrayOf(dst.path), null, null)
                val uri = FileProvider.getUriForFile(
                    this, "$packageName.fileprovider", dst)
                DownloadState.SavedFile(dst.name, uri.toString(), mime)
            }
        } catch (e: Exception) {
            DownloadState.appendLog("[アプリ内エラー] 保存失敗: ${file.name}: $e")
            null
        }
    }
}
