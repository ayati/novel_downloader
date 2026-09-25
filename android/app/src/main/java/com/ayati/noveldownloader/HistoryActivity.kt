package com.ayati.noveldownloader

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageButton
import android.widget.PopupMenu
import android.widget.ProgressBar
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
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * ダウンロード履歴の一覧画面（設計書 android/design_history.md §4.3）。
 *
 * 行タップ = 開く / 📤 = 共有 / ⋮ = 共有・もう一度ダウンロード・履歴から削除。
 * 「履歴から削除」はファイル実体を消さない（§7 決定事項3）。
 *
 * 第2部（§13.1）: 🌐 作品ページ / 🔄 新着チェック / ⬇ 新着を取得。
 * 新着チェックはこの画面の IO スレッドで行い（前景サービスは使わない・§12 決定7）、
 * 取得はメイン画面へ渡して DownloadService の更新モードで行う（§12 決定6）。
 */
class HistoryActivity : AppCompatActivity() {

    private lateinit var list: RecyclerView
    private lateinit var emptyView: TextView
    private val adapter = Adapter()

    private var entries: List<DownloadHistory.Entry> = emptyList()
    private var invalid: Set<String> = emptySet()
    /** 新着チェック中の行 id。 */
    private val checking = mutableSetOf<String>()

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

    // ── 作品ページ・新着チェック・新着を取得（§13） ─────────────

    private fun openWeb(e: DownloadHistory.Entry) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(e.sourceUrl)))
        } catch (ex: ActivityNotFoundException) {
            Toast.makeText(this, getString(R.string.history_toast_no_browser),
                Toast.LENGTH_SHORT).show()
        }
    }

    private fun toastBusy() {
        Toast.makeText(this, getString(R.string.history_toast_busy), Toast.LENGTH_SHORT).show()
    }

    private fun runCheck(e: DownloadHistory.Entry) {
        if (DownloadState.ui.value.isRunning) { toastBusy(); return }
        if (!checking.add(e.id)) return
        adapter.notifyDataSetChanged()
        lifecycleScope.launch {
            // 保存まで IO 側で済ませる。画面を閉じるとこのコルーチンは取り消されるが、
            // エンジンの呼び出しは止まらないので、結果だけは history.json に残す（§12 決定7）
            val appCtx = applicationContext
            val result = withContext(Dispatchers.IO) {
                doCheck(e)?.let { (check, site) ->
                    DownloadHistory.setCheck(appCtx, e.id, check, site) ?: e
                }
            }
            checking.remove(e.id)
            if (result == null) {
                toastBusy()        // 直前にダウンロードが始まってロックが取れなかった
            } else {
                entries = entries.map { if (it.id == e.id) result else it }
            }
            adapter.notifyDataSetChanged()
        }
    }

    /**
     * エンジンで新着を調べる。ロックが取れなければ null（§13.2）。
     * 手元の .txt があれば _check_update_one（PC の本棚と同じ判定・§11.2）、
     * 無ければ（または読めなければ）サイトの総数だけを調べる。
     */
    private fun doCheck(e: DownloadHistory.Entry): Pair<DownloadHistory.Check, String>? {
        PyBridge.ensureStarted(applicationContext)
        return PyBridge.tryWithEngine {
            val dir = File(cacheDir, "check").apply { deleteRecursively(); mkdirs() }
            val local = e.txt?.let { t ->
                try {
                    contentResolver.openInputStream(Uri.parse(t.uri))?.use { input ->
                        File(dir, "check.txt").also { f -> f.outputStream().use { input.copyTo(it) } }
                    }
                } catch (ex: Exception) {
                    null
                }
            }
            val json = try {
                JSONObject(
                    if (local != null) PyBridge.module.callAttr("check", local.path).toString()
                    else PyBridge.module.callAttr("check_url", e.sourceUrl).toString())
            } catch (ex: Exception) {
                JSONObject().put("status", "error").put("error", ex.toString())
            } finally {
                dir.deleteRecursively()
            }
            val raw = json.optString("status")
            val titles = json.optJSONArray("new_titles")
            val check = DownloadHistory.Check(
                at = System.currentTimeMillis(),
                status = when (raw) {
                    "updated", "uptodate" -> raw
                    "init" -> "nolocal"
                    else -> "error"
                },
                existing = json.optInt("existing"),
                total = json.optInt("total"),
                newTitles = if (titles == null) emptyList()
                            else (0 until titles.length()).map { titles.optString(it) },
                error = json.optString("error"),
            )
            // 取り込んだ行はサイト名が空。オフラインの detect() で埋める（§13.6）
            val site = if (e.siteName.isNotEmpty()) "" else try {
                JSONObject(PyBridge.module.callAttr("detect", e.sourceUrl).toString())
                    .optString("display_name")
            } catch (ex: Exception) {
                ""
            }
            check to site
        }
    }

    /**
     * 新着を取得する（forceFull=false）／まるごと取り直す（true）。
     * .txt が無い・開けないときは追記できないので、確認してから取り直す（§13.4.1）。
     */
    private fun startUpdate(e: DownloadHistory.Entry, forceFull: Boolean) {
        if (e.sourceUrl.isEmpty()) {
            Toast.makeText(this, getString(R.string.history_toast_no_url),
                Toast.LENGTH_SHORT).show()
            return
        }
        if (DownloadState.ui.value.isRunning) { toastBusy(); return }
        lifecycleScope.launch {
            val canAppend = !forceFull && withContext(Dispatchers.IO) {
                e.txt?.let { DownloadHistory.exists(this@HistoryActivity, it.uri) } ?: false
            }
            if (canAppend) {
                launchUpdate(e, forceFull = false)
                return@launch
            }
            AlertDialog.Builder(this@HistoryActivity)
                .setTitle(R.string.history_full_title)
                .setMessage(if (forceFull) R.string.history_full_message_redo
                            else R.string.history_full_message_notxt)
                .setPositiveButton(R.string.history_full_ok) { _, _ -> launchUpdate(e, true) }
                .setNegativeButton(R.string.common_cancel, null)
                .show()
        }
    }

    /** メイン画面へ渡して、権限の確認とサービスの起動・進捗表示を任せる。 */
    private fun launchUpdate(e: DownloadHistory.Entry, forceFull: Boolean) {
        startActivity(Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra(MainActivity.EXTRA_UPDATE_ENTRY_ID, e.id)
            .putExtra(MainActivity.EXTRA_UPDATE_URL, e.sourceUrl)
            .putExtra(MainActivity.EXTRA_UPDATE_FORCE_FULL, forceFull))
        finish()
    }

    private fun showCheckDetail(e: DownloadHistory.Entry) {
        val c = e.lastCheck ?: return
        val msg = when (c.status) {
            "updated" -> c.newTitles.joinToString("\n").ifEmpty { checkLine(c) }
            "error" -> c.error.ifEmpty { checkLine(c) }
            else -> checkLine(c)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.history_check_detail_title)
            .setMessage(msg)
            .setPositiveButton(R.string.common_close, null)
            .show()
    }

    private fun showRowMenu(anchor: View, e: DownloadHistory.Entry) {
        PopupMenu(this, anchor).apply {
            menu.add(0, 1, 0, getString(R.string.common_share))
            if (e.lastCheck != null)
                menu.add(0, 4, 1, getString(R.string.history_check_detail_title))
            menu.add(0, 2, 2, getString(R.string.history_row_redownload))
            menu.add(0, 3, 3, getString(R.string.history_row_remove))
            setOnMenuItemClickListener { item ->
                when (item.itemId) {
                    1 -> FileActions.share(this@HistoryActivity, e.files, e.title)
                    2 -> startUpdate(e, forceFull = true)
                    3 -> confirmRemove(e)
                    4 -> showCheckDetail(e)
                }
                true
            }
            show()
        }
    }

    /** テーマ属性の色（新着ありは強調色、それ以外は補助の文字色）。 */
    private fun themeColor(attr: Int): Int {
        val ta = obtainStyledAttributes(intArrayOf(attr))
        return try { ta.getColor(0, 0) } finally { ta.recycle() }
    }

    /** 「🆕 新着 3話（9月25日 確認）」など。 */
    private fun checkLine(c: DownloadHistory.Check): String {
        val at = formatDate(c.at)
        return when (c.status) {
            "updated" -> resources.getQuantityString(R.plurals.history_check_new, c.newCount, c.newCount, at)
            "uptodate" -> getString(R.string.history_check_uptodate, at)
            "nolocal" -> resources.getQuantityString(R.plurals.history_check_nolocal, c.total, c.total, at)
            else -> getString(R.string.history_check_error, at)
        }
    }

    // ── 一覧アダプタ ─────────────────────────────────────────────

    private inner class Holder(v: View) : RecyclerView.ViewHolder(v) {
        val title: TextView = v.findViewById(R.id.item_title)
        val meta: TextView = v.findViewById(R.id.item_meta)
        val file: TextView = v.findViewById(R.id.item_file)
        val share: ImageButton = v.findViewById(R.id.item_share)
        val more: ImageButton = v.findViewById(R.id.item_more)
        val check: TextView = v.findViewById(R.id.item_check)
        val actions: View = v.findViewById(R.id.item_actions)
        val web: Button = v.findViewById(R.id.item_web)
        val checkBtn: Button = v.findViewById(R.id.item_check_btn)
        val checkingBar: ProgressBar = v.findViewById(R.id.item_checking)
        val update: Button = v.findViewById(R.id.item_update)
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

            // 🌐 / 🔄 / ⬇ は元 URL が分かっている行だけ（取り込み分で .txt も無い行は出さない）
            val hasUrl = e.sourceUrl.isNotEmpty()
            h.actions.visibility = if (hasUrl) View.VISIBLE else View.GONE
            val isChecking = e.id in checking
            h.checkBtn.isEnabled = !isChecking && checking.isEmpty()
            h.checkingBar.visibility = if (isChecking) View.VISIBLE else View.GONE
            val c = e.lastCheck
            h.check.visibility = if (c != null && !isChecking) View.VISIBLE else View.GONE
            if (c != null) {
                h.check.text = checkLine(c)
                h.check.setTextColor(themeColor(
                    if (c.status == "updated") androidx.appcompat.R.attr.colorPrimary
                    else android.R.attr.textColorSecondary))
            }
            // 新着あり → 追記。手元に .txt が無い → 取り直し（§13.1）
            val offer = c != null && (c.status == "updated" || c.status == "nolocal") && !isChecking
            h.update.visibility = if (offer) View.VISIBLE else View.GONE
            h.update.text = getString(
                if (c?.status == "nolocal") R.string.history_btn_redo else R.string.history_btn_update)

            h.web.setOnClickListener { openWeb(e) }
            h.checkBtn.setOnClickListener { runCheck(e) }
            h.update.setOnClickListener { startUpdate(e, forceFull = c?.status == "nolocal") }
            h.check.setOnClickListener { showCheckDetail(e) }
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
