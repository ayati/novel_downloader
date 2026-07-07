package com.ayati.noveldownloader

import android.content.Context
import android.system.Os
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

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
}
