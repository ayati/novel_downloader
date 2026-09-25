package com.ayati.noveldownloader

import android.Manifest
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.NestedScrollView
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.concurrent.Executors
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    companion object {
        /** 外部から URL を受け取って入力欄に入れる（旧「もう一度ダウンロード」の経路）。 */
        const val EXTRA_PREFILL_URL = "prefill_url"
        /** 履歴の「新着を取得」「もう一度ダウンロード」: 更新する履歴の id（design_history.md §13.4）。 */
        const val EXTRA_UPDATE_ENTRY_ID = "update_entry_id"
        const val EXTRA_UPDATE_URL = "update_url"
        const val EXTRA_UPDATE_FORCE_FULL = "update_force_full"
    }

    private lateinit var urlInput: EditText
    private lateinit var btnPaste: Button
    private lateinit var btnClear: Button
    private lateinit var siteBadge: TextView
    private lateinit var btnMain: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var progressText: TextView
    private lateinit var statusLine: TextView
    private lateinit var doneCard: View
    private lateinit var doneHeading: TextView
    private lateinit var doneFile: TextView
    private lateinit var btnOpen: Button
    private lateinit var btnShare: Button
    private lateinit var logToggle: TextView
    private lateinit var logScroll: NestedScrollView
    private lateinit var logView: TextView

    private val detectExecutor = Executors.newSingleThreadExecutor()

    @Volatile
    private var pythonReady = false
    private var detectedUrl: String? = null   // detect 済みの正規化URL（DL開始に使う）
    private var detectedSiteName: String = ""  // 履歴に残すサイト表示名
    private var pendingStart = false          // 権限ダイアログ応答後に開始するか
    private var recent: DownloadHistory.Entry? = null  // IDLE 時に出す「最近のダウンロード」

    /** 履歴から頼まれた更新。権限フローを通したあと startDownload() が使う。 */
    private data class PendingUpdate(val entryId: String, val url: String, val forceFull: Boolean)
    private var pendingUpdate: PendingUpdate? = null

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()) {
        // 通知権限は拒否されてもダウンロードは続行する（設計 §6）
        if (pendingStart) { pendingStart = false; startDownload() }
    }

    private val writePermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            if (pendingStart) { pendingStart = false; maybeRequestNotifThenStart() }
        } else {
            pendingStart = false
            pendingUpdate = null
            Toast.makeText(this, getString(R.string.main_err_no_write_permission),
                Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        applyEdgeToEdgeInsets(
            root = findViewById(R.id.main_root),
            appBar = findViewById(R.id.app_bar),
            toolbar = findViewById(R.id.toolbar),
            content = findViewById(R.id.main_scroll),
        )

        urlInput = findViewById(R.id.url_input)
        btnPaste = findViewById(R.id.btn_paste)
        btnClear = findViewById(R.id.btn_clear)
        siteBadge = findViewById(R.id.site_badge)
        btnMain = findViewById(R.id.btn_main)
        progressBar = findViewById(R.id.progress_bar)
        progressText = findViewById(R.id.progress_text)
        statusLine = findViewById(R.id.status_line)
        doneCard = findViewById(R.id.done_card)
        doneHeading = findViewById(R.id.done_heading)
        doneFile = findViewById(R.id.done_file)
        btnOpen = findViewById(R.id.btn_open)
        btnShare = findViewById(R.id.btn_share)
        logToggle = findViewById(R.id.log_toggle)
        logScroll = findViewById(R.id.log_scroll)
        logView = findViewById(R.id.log_view)

        statusLine.text = getString(R.string.status_python_init)
        thread {
            PyBridge.ensureStarted(applicationContext)
            pythonReady = true
            runOnUiThread {
                if (!DownloadState.ui.value.isRunning) statusLine.text = ""
                onUrlChanged()
            }
        }

        urlInput.doAfterTextChanged { onUrlChanged() }

        btnPaste.setOnClickListener {
            val clip = getSystemService(ClipboardManager::class.java)
                .primaryClip?.getItemAt(0)?.coerceToText(this)?.toString() ?: ""
            val url = Regex("""https?://\S+""").find(clip)?.value
            if (url == null) {
                Toast.makeText(this, getString(R.string.main_toast_no_clipboard_url),
                    Toast.LENGTH_SHORT).show()
            } else {
                urlInput.setText(url)
            }
        }

        btnClear.setOnClickListener { urlInput.setText("") }

        btnMain.setOnClickListener {
            if (DownloadState.ui.value.isRunning) {
                startService(Intent(this, DownloadService::class.java)
                    .setAction(DownloadService.ACTION_CANCEL))
                btnMain.isEnabled = false  // 二度押し防止（CANCELLED 遷移で復帰）
            } else {
                pendingStart = true
                maybeRequestWriteThenStart()
            }
        }

        logToggle.setOnClickListener {
            val open = logScroll.visibility == View.VISIBLE
            logScroll.visibility = if (open) View.GONE else View.VISIBLE
            logToggle.text = getString(
                if (open) R.string.main_log_show else R.string.main_log_hide)
        }

        btnOpen.setOnClickListener { cardFiles().firstOrNull()?.let { FileActions.open(this, it) } }
        btnShare.setOnClickListener {
            val files = cardFiles()
            if (files.isNotEmpty()) FileActions.share(this, files, cardLabel())
        }
        doneHeading.setOnClickListener { openHistory() }

        lifecycleScope.launch {
            DownloadState.ui.collect { render(it) }
        }
        lifecycleScope.launch {
            DownloadState.logLines.collect { lines ->
                logView.text = lines.joinToString("\n")
                if (logScroll.visibility == View.VISIBLE) {
                    logScroll.post { logScroll.fullScroll(View.FOCUS_DOWN) }
                }
            }
        }

        handleIncomingIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        // 履歴画面での削除・取り込みを反映させるため毎回読み直す
        lifecycleScope.launch {
            recent = withContext(Dispatchers.IO) {
                DownloadHistory.load(this@MainActivity).firstOrNull()
            }
            render(DownloadState.ui.value)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    /**
     * 外部から渡された URL を入力欄へセットする。
     * 経路は2つ: 履歴の「もう一度ダウンロード」と、ブラウザ等の共有シート（ACTION_SEND）。
     */
    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return
        val entryId = intent.getStringExtra(EXTRA_UPDATE_ENTRY_ID)
        if (!entryId.isNullOrEmpty()) {
            val url = intent.getStringExtra(EXTRA_UPDATE_URL).orEmpty()
            val force = intent.getBooleanExtra(EXTRA_UPDATE_FORCE_FULL, false)
            // 画面回転で再実行されないよう消す
            intent.removeExtra(EXTRA_UPDATE_ENTRY_ID)
            if (DownloadState.ui.value.isRunning) {
                Toast.makeText(this, getString(R.string.main_toast_busy), Toast.LENGTH_SHORT).show()
                return
            }
            pendingUpdate = PendingUpdate(entryId, url, force)
            pendingStart = true
            maybeRequestWriteThenStart()
            return
        }
        val prefill = intent.getStringExtra(EXTRA_PREFILL_URL)
        if (!prefill.isNullOrEmpty()) {
            intent.removeExtra(EXTRA_PREFILL_URL)   // 画面回転で再適用されないよう消す
            urlInput.setText(prefill)
            return
        }
        if (intent.action != Intent.ACTION_SEND) return
        val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
        // ページタイトル等が混ざるため最初の URL だけを抽出する
        val url = Regex("""https?://\S+""").find(text)?.value ?: return
        urlInput.setText(url)
    }

    // ── 設定メニュー（⋮） ────────────────────────────────────────

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_history -> { openHistory(); true }
        R.id.action_settings -> { showSettingsDialog(); true }
        else -> super.onOptionsItemSelected(item)
    }

    private fun openHistory() {
        startActivity(Intent(this, HistoryActivity::class.java))
    }

    private fun showSettingsDialog() {
        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        // .txt は常に保存する（追記の材料。design_history.md §12 決定1）ので設定から外した
        val keys = arrayOf("horizontal", "kobo", "use_site_cover", "no_inline_images")
        val labels = arrayOf(
            getString(R.string.settings_horizontal),
            getString(R.string.settings_kobo),
            getString(R.string.settings_site_cover),
            getString(R.string.settings_no_inline_images),
        )
        val checked = BooleanArray(keys.size) { prefs.getBoolean(keys[it], false) }
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle(R.string.settings_title)
            .setMultiChoiceItems(labels, checked) { _, which, isChecked ->
                prefs.edit().putBoolean(keys[which], isChecked).apply()
            }
            .setPositiveButton(R.string.common_close, null)
            .show()
    }

    // ── 完了カード（開く／共有） ─────────────────────────────────

    /** 完了直後は今回の成果物、IDLE 時は履歴の最新エントリを対象にする。 */
    private fun cardFiles(): List<DownloadState.SavedFile> {
        val ui = DownloadState.ui.value
        return if (ui.phase == DownloadState.Phase.DONE && ui.savedFiles.isNotEmpty())
            ui.savedFiles
        else
            recent?.files.orEmpty()
    }

    private fun cardLabel(): String {
        val ui = DownloadState.ui.value
        return if (ui.phase == DownloadState.Phase.DONE && ui.savedFiles.isNotEmpty())
            ui.savedFiles.first().name
        else
            recent?.title.orEmpty()
    }

    // ── サイト判定バッジ ─────────────────────────────────────────

    private fun onUrlChanged() {
        val text = urlInput.text.toString().trim()
        detectedUrl = null
        detectedSiteName = ""
        if (!pythonReady || text.isEmpty()) {
            siteBadge.visibility = View.GONE
            updateMainButton()
            return
        }
        detectExecutor.submit {
            val json = try {
                JSONObject(PyBridge.module.callAttr("detect", text).toString())
            } catch (e: Exception) {
                null
            }
            runOnUiThread {
                if (text != urlInput.text.toString().trim()) return@runOnUiThread
                renderBadge(text, json)
                updateMainButton()
            }
        }
    }

    private fun renderBadge(input: String, json: JSONObject?) {
        siteBadge.visibility = View.VISIBLE
        when {
            json == null ->
                siteBadge.text = getString(R.string.main_badge_detect_error)
            json.optBoolean("needs_playwright") ->
                siteBadge.text = getString(R.string.main_badge_hameln)
            !json.isNull("site") -> {
                detectedUrl = json.optString("normalized_url", input).ifEmpty { input }
                detectedSiteName = json.optString("display_name")
                siteBadge.text = getString(R.string.main_badge_site, detectedSiteName)
            }
            Regex("""^https?://\S+$""").matches(input) &&
                    !input.contains("syosetu.org") -> {
                // 短縮URLの可能性: 本体が実行時に展開するので許可する
                detectedUrl = input
                siteBadge.text = getString(R.string.main_badge_unknown)
            }
            else ->
                siteBadge.text = getString(R.string.main_badge_unsupported)
        }
    }

    private fun updateMainButton() {
        val ui = DownloadState.ui.value
        btnMain.isEnabled = ui.isRunning || (pythonReady && detectedUrl != null)
    }

    // ── ダウンロード開始（権限フロー） ───────────────────────────

    private fun maybeRequestWriteThenStart() {
        if (Build.VERSION.SDK_INT < 29 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
            != PackageManager.PERMISSION_GRANTED) {
            writePermission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        } else {
            maybeRequestNotifThenStart()
        }
    }

    private fun maybeRequestNotifThenStart() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            pendingStart = false
            startDownload()
        }
    }

    private fun startDownload() {
        pendingUpdate?.let { u ->
            pendingUpdate = null
            ContextCompat.startForegroundService(this,
                Intent(this, DownloadService::class.java)
                    .putExtra(DownloadService.EXTRA_URL, u.url)
                    .putExtra(DownloadService.EXTRA_ENTRY_ID, u.entryId)
                    .putExtra(DownloadService.EXTRA_FORCE_FULL, u.forceFull))
            return
        }
        val url = detectedUrl ?: return
        val intent = Intent(this, DownloadService::class.java)
            .putExtra(DownloadService.EXTRA_URL, url)
            .putExtra(DownloadService.EXTRA_SITE_NAME, detectedSiteName)
        ContextCompat.startForegroundService(this, intent)
    }

    // ── 状態 → 画面反映 ──────────────────────────────────────────

    private var lastPhase: DownloadState.Phase? = null

    private fun render(ui: DownloadState.Ui) {
        updateMainButton()
        btnMain.text = getString(
            if (ui.isRunning) R.string.main_btn_cancel else R.string.main_btn_download)

        // 完了直後は「✅ 完了」、IDLE で履歴があれば「最近のダウンロード」を同じカードに出す
        val done = ui.phase == DownloadState.Phase.DONE && ui.savedFiles.isNotEmpty()
        val showRecent = !done && ui.phase == DownloadState.Phase.IDLE && recent != null
        doneCard.visibility = if (done || showRecent) View.VISIBLE else View.GONE
        // 横向き・大きな文字では完了カードが画面外に出る。完了に切り替わった 1 回だけ
        // 見える位置まで寄せる（見えていれば動かない。render は進捗ごとに呼ばれる）
        if (done && lastPhase != DownloadState.Phase.DONE) {
            doneCard.post {
                doneCard.requestRectangleOnScreen(Rect(0, 0, doneCard.width, doneCard.height))
            }
        }
        lastPhase = ui.phase
        doneHeading.visibility = if (showRecent) View.VISIBLE else View.GONE
        when {
            done -> doneFile.text = ui.savedFiles.joinToString("\n") { it.name }
            showRecent -> {
                doneHeading.text = getString(R.string.main_recent_heading)
                doneFile.text = recent!!.title
            }
        }

        when (ui.phase) {
            DownloadState.Phase.IDLE -> {
                progressBar.visibility = View.GONE
                progressText.visibility = View.GONE
            }
            DownloadState.Phase.PREPARING, DownloadState.Phase.SAVING -> {
                progressBar.visibility = View.VISIBLE
                progressBar.isIndeterminate = true
                progressText.visibility = View.GONE
                statusLine.text = statusText(ui.status, ui.statusArg)
            }
            DownloadState.Phase.DOWNLOADING -> {
                progressBar.visibility = View.VISIBLE
                progressBar.isIndeterminate = false
                progressBar.max = ui.total.coerceAtLeast(1)
                progressBar.progress = ui.n
                progressText.visibility = View.VISIBLE
                progressText.text = getString(R.string.progress_episodes, ui.n, ui.total)
                statusLine.text = statusText(ui.status, ui.statusArg)
            }
            DownloadState.Phase.DONE, DownloadState.Phase.CANCELLED -> {
                progressBar.visibility = View.GONE
                progressText.visibility = View.GONE
                statusLine.text = statusText(ui.status, ui.statusArg)
            }
            DownloadState.Phase.ERROR -> {
                progressBar.visibility = View.GONE
                progressText.visibility = View.GONE
                statusLine.text = statusText(ui.status, ui.statusArg)
                logScroll.visibility = View.VISIBLE   // エラー時はログを自動展開
                logToggle.text = getString(R.string.main_log_hide)
            }
        }
    }
}
