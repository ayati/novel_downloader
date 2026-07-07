package com.ayati.noveldownloader

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.ContentValues
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.MediaScannerConnection
import android.os.Build
import android.os.Environment
import android.os.IBinder
import android.provider.MediaStore
import androidx.core.app.NotificationCompat
import org.json.JSONObject
import java.io.File
import kotlin.concurrent.thread

/**
 * ダウンロード実行用 Foreground Service。
 * 同時実行は 1 件のみ（実行中の開始要求は無視）。
 * 完了後、staging の .epub を Download/小説ダウンローダー/ へコピーする。
 */
class DownloadService : Service() {

    companion object {
        const val EXTRA_URL = "url"
        const val ACTION_CANCEL = "com.ayati.noveldownloader.action.CANCEL"
        private const val CHANNEL_ID = "download"
        private const val NOTIF_ID_PROGRESS = 1
        private const val NOTIF_ID_RESULT = 2
        private const val SUBDIR = "小説ダウンローダー"
    }

    @Volatile
    private var running = false
    private var lastNotified = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(
            CHANNEL_ID, "ダウンロード", NotificationManager.IMPORTANCE_LOW)
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
                val notif = buildProgressNotification("準備中…", 0, 0)
                if (Build.VERSION.SDK_INT >= 29) {
                    startForeground(NOTIF_ID_PROGRESS, notif,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
                } else {
                    startForeground(NOTIF_ID_PROGRESS, notif)
                }
                val url = intent.getStringExtra(EXTRA_URL)!!
                thread { work(url) }
            }
        }
        return START_NOT_STICKY
    }

    // ── ダウンロード本体（ワーカースレッド） ──────────────────────

    private fun work(url: String) {
        DownloadState.reset()
        DownloadState.ui.value = DownloadState.Ui(phase = DownloadState.Phase.PREPARING)

        val staging = File(filesDir, "staging")
        staging.deleteRecursively()
        staging.mkdirs()

        val listener = Listener()
        val code = try {
            PyBridge.ensureStarted(applicationContext)
            val opts = JSONObject().put("output_dir", staging.path)
            PyBridge.module.callAttr("run", url, opts.toString(), listener).toInt()
        } catch (e: Exception) {
            DownloadState.appendLog("[アプリ内エラー] $e")
            1
        }

        when (code) {
            0 -> {
                val saved = staging.listFiles { f -> f.name.endsWith(".epub") }
                    .orEmpty().mapNotNull { saveToDownloads(it) }
                if (saved.isEmpty()) {
                    DownloadState.appendLog("[アプリ内エラー] 保存対象の .epub がありません")
                    finish(DownloadState.Phase.ERROR, "❌ 失敗（詳細ログ参照）")
                } else {
                    DownloadState.ui.value = DownloadState.ui.value.copy(savedFiles = saved)
                    finish(DownloadState.Phase.DONE,
                        "✅ 完了: ${saved.joinToString()}（ダウンロードフォルダ）")
                }
            }
            130 -> finish(DownloadState.Phase.CANCELLED, "中止しました")
            else -> finish(DownloadState.Phase.ERROR, "❌ 失敗（詳細ログ参照）")
        }

        staging.deleteRecursively()
        running = false
        stopSelf()
    }

    private fun finish(phase: DownloadState.Phase, message: String) {
        DownloadState.ui.value = DownloadState.ui.value.copy(phase = phase, statusLine = message)
        stopForeground(STOP_FOREGROUND_REMOVE)
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(message)
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(NOTIF_ID_RESULT, notif)
    }

    // ── Python からのコールバック受け口 ──────────────────────────

    inner class Listener {
        fun onLine(text: String) {
            DownloadState.appendLog(text)
            if (text.isNotBlank()) {
                DownloadState.ui.value =
                    DownloadState.ui.value.copy(statusLine = text.trim())
            }
        }

        fun onProgress(n: Int, total: Int) {
            DownloadState.ui.value = DownloadState.ui.value.copy(
                phase = DownloadState.Phase.DOWNLOADING, n = n, total = total)
            val now = System.currentTimeMillis()
            if (now - lastNotified > 900) {
                lastNotified = now
                getSystemService(NotificationManager::class.java).notify(
                    NOTIF_ID_PROGRESS, buildProgressNotification("$n / $total 話", n, total))
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
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setProgress(if (total > 0) total else 0, n, total <= 0)
            .build()

    /** staging のファイルを公開 Downloads へコピーし、保存名を返す。 */
    private fun saveToDownloads(file: File): String? {
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
                file.name
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
                dst.name
            }
        } catch (e: Exception) {
            DownloadState.appendLog("[アプリ内エラー] 保存失敗: ${file.name}: $e")
            null
        }
    }
}
