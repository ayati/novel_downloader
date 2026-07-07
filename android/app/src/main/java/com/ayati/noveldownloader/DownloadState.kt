package com.ayati.noveldownloader

import kotlinx.coroutines.flow.MutableStateFlow

/**
 * ダウンロードの進行状態をプロセス全体で共有するシングルトン。
 * Service が更新し、Activity が StateFlow 経由で購読する
 * （画面回転・Activity 再生成に耐える）。
 */
object DownloadState {

    enum class Phase { IDLE, PREPARING, DOWNLOADING, SAVING, DONE, CANCELLED, ERROR }

    /** 保存済みファイル。uri は ACTION_VIEW / ACTION_SEND にそのまま渡せる content:// 形式。 */
    data class SavedFile(val name: String, val uri: String, val mime: String)

    data class Ui(
        val phase: Phase = Phase.IDLE,
        val n: Int = 0,
        val total: Int = 0,
        val statusLine: String = "",
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
