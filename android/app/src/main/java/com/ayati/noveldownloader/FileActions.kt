package com.ayati.noveldownloader

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast

/**
 * 保存済みファイルを開く／共有する共通処理。
 * 完了カード（MainActivity）と履歴一覧（HistoryActivity）の両方から使う。
 *
 * uri は MediaStore（API 29+）または FileProvider（≤28）の content:// で、
 * どちらも再起動後に有効（設計書 android/design_history.md §2.2）。
 */
object FileActions {

    fun open(ctx: Context, file: DownloadState.SavedFile) {
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(Uri.parse(file.uri), file.mime)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            ctx.startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(ctx, ctx.getString(R.string.toast_no_epub_reader),
                Toast.LENGTH_LONG).show()
        }
    }

    /** 1件なら ACTION_SEND、複数なら ACTION_SEND_MULTIPLE。 */
    fun share(ctx: Context, files: List<DownloadState.SavedFile>, label: String) {
        if (files.isEmpty()) return
        val intent = if (files.size == 1) {
            Intent(Intent.ACTION_SEND)
                .setType(files[0].mime)
                .putExtra(Intent.EXTRA_STREAM, Uri.parse(files[0].uri))
        } else {
            Intent(Intent.ACTION_SEND_MULTIPLE)
                .setType("*/*")
                .putParcelableArrayListExtra(
                    Intent.EXTRA_STREAM,
                    ArrayList(files.map { Uri.parse(it.uri) }))
        }
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(
            Intent.createChooser(intent, label).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
