package com.ayati.noveldownloader

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * ダウンロードの進行状態をプロセス全体で共有するシングルトン。
 * Service が更新し、Activity が StateFlow 経由で購読する
 * （画面回転・Activity 再生成に耐える）。
 */
object DownloadState {

    enum class Phase { IDLE, PREPARING, DOWNLOADING, SAVING, DONE, CANCELLED, ERROR }

    /**
     * 状態表示の種別。**組み立て済みの文字列ではなくコードを持つ。**
     *
     * 以前は Service が getString() で組み立てた文字列をそのまま保持していたが、
     * このシングルトンはプロセスが生きている限り残るため、途中で端末やアプリの言語を
     * 切り替えると Activity だけが新しいロケールで作り直され、
     * **状態行だけ旧언語のまま残る**（実機で再現: 日本語UIに英語の「Done: …」）。
     * 表示時に Activity / Service がその時点のロケールで組み立てる。
     */
    enum class Status { NONE, PREPARING, DONE, CANCELLED, FAILED, RAW }

    /** 保存済みファイル。uri は ACTION_VIEW / ACTION_SEND にそのまま渡せる content:// 形式。 */
    data class SavedFile(val name: String, val uri: String, val mime: String)

    data class Ui(
        val phase: Phase = Phase.IDLE,
        val n: Int = 0,
        val total: Int = 0,
        val status: Status = Status.NONE,
        /** DONE のファイル名連結 / RAW の生ログ行。ロケールに依存しない値だけを入れる。 */
        val statusArg: String = "",
        val savedFiles: List<SavedFile> = emptyList(),
    ) {
        val isRunning: Boolean
            get() = phase == Phase.PREPARING || phase == Phase.DOWNLOADING || phase == Phase.SAVING
    }

    private const val LOG_LIMIT = 5000

    val ui = MutableStateFlow(Ui())
    val logLines = MutableStateFlow<List<String>>(emptyList())

    fun reset() {
        ui.value = Ui()
        logLines.value = emptyList()
    }

    fun appendLog(line: String) {
        val cur = logLines.value
        logLines.value = if (cur.size >= LOG_LIMIT) cur.drop(1) + line else cur + line
    }
}

/**
 * 状態コードを現在のロケールの文言に組み立てる。
 * Activity（画面）と Service（通知）の両方から使う。
 * RAW は Python 本体の生ログ行なので翻訳しない（design_i18n.md §3 C層）。
 */
fun Context.statusText(status: DownloadState.Status, arg: String): String = when (status) {
    DownloadState.Status.NONE -> ""
    DownloadState.Status.PREPARING -> getString(R.string.status_preparing)
    DownloadState.Status.DONE -> getString(R.string.status_done, arg)
    DownloadState.Status.CANCELLED -> getString(R.string.status_cancelled)
    DownloadState.Status.FAILED -> getString(R.string.status_failed)
    DownloadState.Status.RAW -> arg
}
