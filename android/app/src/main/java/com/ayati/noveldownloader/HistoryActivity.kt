package com.ayati.noveldownloader

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.PopupMenu
import android.widget.TextView
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * ダウンロード履歴の一覧画面（設計書 android/design_history.md §4.3）。
 *
 * 行タップ = 開く / 📤 = 共有 / ⋮ = 共有・もう一度ダウンロード・履歴から削除。
 * 「履歴から削除」はファイル実体を消さない（§7 決定事項3）。
 */
class HistoryActivity : AppCompatActivity() {

    private lateinit var list: RecyclerView
    private lateinit var emptyView: TextView
    private val adapter = Adapter()

    private var entries: List<DownloadHistory.Entry> = emptyList()
    private var invalid: Set<String> = emptySet()

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_history)
        applyEdgeToEdgeInsets(
            root = findViewById(R.id.history_root),
            appBar = findViewById(R.id.app_bar),
            toolbar = findViewById(R.id.toolbar),
            content = findViewById(R.id.history_list),
        )
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        title = getString(R.string.history_title)

        list = findViewById(R.id.history_list)
        emptyView = findViewById(R.id.history_empty)
        list.layoutManager = LinearLayoutManager(this)
        list.adapter = adapter

        reload()
    }

    /** 履歴を読み直し、実体の存在確認まで済ませて描画する。 */
    private fun reload() {
        lifecycleScope.launch {
            val loaded = withContext(Dispatchers.IO) { DownloadHistory.load(this@HistoryActivity) }
            entries = loaded
            adapter.notifyDataSetChanged()
            render()
            // 存在確認は件数に比例するので描画の後で行う
            val bad = withContext(Dispatchers.IO) {
                DownloadHistory.validate(this@HistoryActivity, loaded)
            }
            if (bad != invalid) {
                invalid = bad
                adapter.notifyDataSetChanged()
            }
        }
    }

    private fun render() {
        val empty = entries.isEmpty()
        emptyView.visibility = if (empty) View.VISIBLE else View.GONE
        list.visibility = if (empty) View.GONE else View.VISIBLE
    }

    // ── メニュー ─────────────────────────────────────────────────

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.history_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        android.R.id.home -> { finish(); true }
        R.id.action_import -> { importFolder(); true }
        R.id.action_clear -> { confirmClear(); true }
        else -> super.onOptionsItemSelected(item)
    }

    private fun importFolder() {
        lifecycleScope.launch {
            val n = withContext(Dispatchers.IO) {
                DownloadHistory.importFolder(this@HistoryActivity)
            }
            Toast.makeText(
                this@HistoryActivity,
                if (n > 0) resources.getQuantityString(R.plurals.imported_count, n, n)
                else getString(R.string.history_toast_nothing_imported),
                Toast.LENGTH_SHORT).show()
            if (n > 0) reload()
        }
    }

    private fun confirmClear() {
        if (entries.isEmpty()) return
        AlertDialog.Builder(this)
            .setTitle(R.string.history_menu_clear)
            .setMessage(R.string.history_clear_message)
            .setPositiveButton(R.string.common_delete) { _, _ ->
                lifecycleScope.launch {
                    withContext(Dispatchers.IO) { DownloadHistory.clear(this@HistoryActivity) }
                    reload()
                }
            }
            .setNegativeButton(R.string.common_cancel, null)
            .show()
    }

    // ── 行の操作 ─────────────────────────────────────────────────

    private fun onRowClick(e: DownloadHistory.Entry) {
        if (e.id in invalid) {
            confirmRemoveMissing(e)
        } else {
            FileActions.open(this, e.files.first())
        }
    }

    private fun confirmRemoveMissing(e: DownloadHistory.Entry) {
        AlertDialog.Builder(this)
            .setTitle(R.string.history_missing_title)
            .setMessage(getString(R.string.history_missing_message, e.title))
            .setPositiveButton(R.string.history_missing_remove) { _, _ -> removeEntry(e) }
            .setNegativeButton(R.string.history_missing_keep, null)
            .show()
    }

    private fun confirmRemove(e: DownloadHistory.Entry) {
        AlertDialog.Builder(this)
            .setTitle(R.string.history_row_remove)
            .setMessage(R.string.history_remove_message)
            .setPositiveButton(R.string.common_delete) { _, _ -> removeEntry(e) }
            .setNegativeButton(R.string.common_cancel, null)
            .show()
    }

    private fun removeEntry(e: DownloadHistory.Entry) {
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { DownloadHistory.remove(this@HistoryActivity, e.id) }
            reload()
        }
    }

    /** URL をメイン画面の入力欄へ渡して戻る。 */
    private fun redownload(e: DownloadHistory.Entry) {
        if (e.sourceUrl.isEmpty()) {
            Toast.makeText(this, getString(R.string.history_toast_no_url),
                Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(this, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_PREFILL_URL, e.sourceUrl))
        finish()
    }

    private fun showRowMenu(anchor: View, e: DownloadHistory.Entry) {
        PopupMenu(this, anchor).apply {
            menu.add(0, 1, 0, getString(R.string.common_share))
            menu.add(0, 2, 1, getString(R.string.history_row_redownload))
            menu.add(0, 3, 2, getString(R.string.history_row_remove))
            setOnMenuItemClickListener { item ->
                when (item.itemId) {
                    1 -> FileActions.share(this@HistoryActivity, e.files, e.title)
                    2 -> redownload(e)
                    3 -> confirmRemove(e)
                }
                true
            }
            show()
        }
    }

    // ── 一覧アダプタ ─────────────────────────────────────────────

    private inner class Holder(v: View) : RecyclerView.ViewHolder(v) {
        val title: TextView = v.findViewById(R.id.item_title)
        val meta: TextView = v.findViewById(R.id.item_meta)
        val file: TextView = v.findViewById(R.id.item_file)
        val share: ImageButton = v.findViewById(R.id.item_share)
        val more: ImageButton = v.findViewById(R.id.item_more)
    }

    private inner class Adapter : RecyclerView.Adapter<Holder>() {

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
            Holder(LayoutInflater.from(parent.context)
                .inflate(R.layout.item_history, parent, false))

        override fun getItemCount() = entries.size

        override fun onBindViewHolder(h: Holder, position: Int) {
            val e = entries[position]
            val missing = e.id in invalid

            h.title.text = e.title
            h.meta.text = metaLine(e)
            h.file.text = if (missing) getString(R.string.history_file_missing)
                          else e.files.joinToString(" / ") { it.name }

            val alpha = if (missing) 0.45f else 1f
            h.title.alpha = alpha
            h.meta.alpha = alpha
            h.share.isEnabled = !missing
            h.share.alpha = alpha

            h.itemView.setOnClickListener { onRowClick(e) }
            h.share.setOnClickListener { FileActions.share(this@HistoryActivity, e.files, e.title) }
            h.more.setOnClickListener { showRowMenu(it, e) }
        }
    }

    /** 「小説家になろう ・ 123話 ・ 3月21日」。取り込み分は不明な要素を省く。 */
    private fun metaLine(e: DownloadHistory.Entry): String = listOf(
        e.siteName,
        if (e.episodeCount > 0)
            resources.getQuantityString(R.plurals.episode_count, e.episodeCount, e.episodeCount)
        else "",
        formatDate(e.savedAt),
    ).filter { it.isNotEmpty() }.joinToString(getString(R.string.history_meta_separator))

    private fun formatDate(ms: Long): String {
        if (ms <= 0L) return ""
        val now = Calendar.getInstance()
        val then = Calendar.getInstance().apply { timeInMillis = ms }
        val sameYear = now.get(Calendar.YEAR) == then.get(Calendar.YEAR)
        val pattern = when {
            sameYear && now.get(Calendar.DAY_OF_YEAR) == then.get(Calendar.DAY_OF_YEAR) ->
                R.string.history_date_time
            sameYear -> R.string.history_date_md
            else -> R.string.history_date_ymd
        }
        // 書式自体もロケール依存なのでリソースから取り、Locale も端末に合わせる（design_i18n.md §7.1）
        return SimpleDateFormat(getString(pattern), Locale.getDefault()).format(Date(ms))
    }
}
