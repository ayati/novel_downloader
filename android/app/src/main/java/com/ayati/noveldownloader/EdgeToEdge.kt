package com.ayati.noveldownloader

import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import com.google.android.material.appbar.MaterialToolbar

/**
 * 画面の端まで描く（edge-to-edge）前提で、システムバーとキーボードの分だけ余白を付ける。
 *
 * Android 15（targetSdk 35）以降は edge-to-edge が強制され、Android 16（targetSdk 36）では
 * 解除用の windowOptOutEdgeToEdgeEnforcement も効かなくなる。以前はその属性で逃げていたが、
 * テーマを NoActionBar にしてレイアウト内の Toolbar を ActionBar として使い、インセットを
 * 自前で配る形に作り直した。
 *
 * - [appBar]（Toolbar を包む AppBarLayout）: 上・左右にステータスバーと切り欠きの分。
 *   背景色がステータスバーの裏まで伸びるので、バーの色を別に塗らなくてよい
 * - [content]: 左右と下にナビゲーションバーの分。キーボードが出ていればその高さを優先する
 *   （edge-to-edge では adjustResize が画面を縮めてくれないため）。
 *   レイアウトに書いた元の padding は保ったまま足す
 *
 * 呼ぶ前に Activity 側で enableEdgeToEdge() と setContentView() を済ませておくこと。
 */
internal fun AppCompatActivity.applyEdgeToEdgeInsets(
    root: View,
    appBar: View,
    toolbar: MaterialToolbar,
    content: View,
) {
    setSupportActionBar(toolbar)
    val baseLeft = content.paddingLeft
    val baseRight = content.paddingRight
    val baseBottom = content.paddingBottom
    ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
        val bars = insets.getInsets(
            WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
        )
        val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
        appBar.updatePadding(left = bars.left, top = bars.top, right = bars.right)
        content.updatePadding(
            left = baseLeft + bars.left,
            right = baseRight + bars.right,
            bottom = baseBottom + maxOf(bars.bottom, ime.bottom),
        )
        WindowInsetsCompat.CONSUMED
    }
}
