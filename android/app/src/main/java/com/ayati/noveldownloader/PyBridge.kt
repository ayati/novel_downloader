package com.ayati.noveldownloader

import android.content.Context
import android.system.Os
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.locks.ReentrantLock

/**
 * Chaquopy の起動と bridge モジュールへのアクセスを集約する。
 *
 * novel_downloader は import 時に表紙フォント探索を行うため、
 * Python.start() より前に NOVEL_DL_COVER_FONT を設定する必要がある。
 */
object PyBridge {

    private const val FONT_ASSET = "fonts/AyatiShowaSerif-Regular.ttf"

    @Synchronized
    fun ensureStarted(context: Context) {
        if (Python.isStarted()) return
        val fontFile = File(context.filesDir, FONT_ASSET)
        if (!fontFile.exists()) {
            fontFile.parentFile?.mkdirs()
            context.assets.open(FONT_ASSET).use { input ->
                fontFile.outputStream().use { input.copyTo(it) }
            }
        }
        Os.setenv("NOVEL_DL_COVER_FONT", fontFile.absolutePath, true)
        Python.start(AndroidPlatform(context))
    }

    val module: PyObject
        get() = Python.getInstance().getModule("bridge")

    /**
     * エンジンは同時に1つしか動かせない（design_history.md §11.6 / §13.2）。
     *
     * bridge は sys.stdout・PROGRESS_CALLBACK・本体の _CHECK_UPDATE_MODE といった
     * プロセス全体のグローバルを触る。特に新着チェック中に走ったダウンロードは
     * 話の一覧を取った時点で _CheckUpdateDone に化けて壊れる。
     * detect() はロックしない（入力のたびにダウンロードの終了を待たせない）。ただし
     * redirect_stdout で sys.stdout を一瞬差し替えるので、ダウンロード中に打ち換えると
     * ログ行が数行欠けることがある（design_history.md §13.2・受け入れ済み）。
     */
    val engine = ReentrantLock()

    /** ロックが取れなければ実行せず null を返す（新着チェック用。ダウンロード中は諦める）。 */
    fun <T> tryWithEngine(block: () -> T): T? {
        if (!engine.tryLock()) return null
        return try { block() } finally { engine.unlock() }
    }
}
