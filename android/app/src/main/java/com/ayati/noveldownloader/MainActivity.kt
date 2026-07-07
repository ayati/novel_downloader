package com.ayati.noveldownloader

import android.Manifest
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.concurrent.Executors
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var urlInput: EditText
    private lateinit var btnPaste: Button
    private lateinit var btnClear: Button
    private lateinit var siteBadge: TextView
    private lateinit var btnMain: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var progressText: TextView
    private lateinit var statusLine: TextView
    private lateinit var doneCard: View
    private lateinit var doneFile: TextView
    private lateinit var btnOpen: Button
    private lateinit var btnShare: Button
    private lateinit var logToggle: TextView
    private lateinit var logScroll: ScrollView
    private lateinit var logView: TextView

    private val detectExecutor = Executors.newSingleThreadExecutor()

    @Volatile
    private var pythonReady = false
    private var detectedUrl: String? = null   // detect 済みの正規化URL（DL開始に使う）
    private var pendingStart = false          // 権限ダイアログ応答後に開始するか

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
            Toast.makeText(this, "保存権限がないためダウンロードできません",
                Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        urlInput = findViewById(R.id.url_input)
        btnPaste = findViewById(R.id.btn_paste)
        btnClear = findViewById(R.id.btn_clear)
        siteBadge = findViewById(R.id.site_badge)
        btnMain = findViewById(R.id.btn_main)
        progressBar = findViewById(R.id.progress_bar)
        progressText = findViewById(R.id.progress_text)
        statusLine = findViewById(R.id.status_line)
        doneCard = findViewById(R.id.done_card)
        doneFile = findViewById(R.id.done_file)
        btnOpen = findViewById(R.id.btn_open)
        btnShare = findViewById(R.id.btn_share)
        logToggle = findViewById(R.id.log_toggle)
        logScroll = findViewById(R.id.log_scroll)
        logView = findViewById(R.id.log_view)

        statusLine.text = "Python 初期化中…"
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
                Toast.makeText(this, "クリップボードにURLがありません", Toast.LENGTH_SHORT).show()
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
            logToggle.text = if (open) "▸ 詳細ログ" else "▾ 詳細ログ"
        }

        btnOpen.setOnClickListener { firstSavedFile()?.let { openFile(it) } }
        btnShare.setOnClickListener { firstSavedFile()?.let { shareFile(it) } }

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

        handleShareIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShareIntent(intent)
    }

    /** 共有シート（ACTION_SEND）から受け取ったテキストの先頭URLを入力欄へセットする。 */
    private fun handleShareIntent(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
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

    override fun onOptionsItemSelected(item: MenuItem): Boolean =
        if (item.itemId == R.id.action_settings) {
            showSettingsDialog()
            true
        } else {
            super.onOptionsItemSelected(item)
        }

    private fun showSettingsDialog() {
        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        val keys = arrayOf("horizontal", "kobo", "use_site_cover", "save_txt")
        val labels = arrayOf(
            "横書きにする",
            "Kobo用拡張子 (.kepub.epub)",
            "サイトの表紙画像を使う",
            "テキスト (.txt) も保存する",
        )
        val checked = BooleanArray(keys.size) { prefs.getBoolean(keys[it], false) }
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("設定（次のダウンロードから適用）")
            .setMultiChoiceItems(labels, checked) { _, which, isChecked ->
                prefs.edit().putBoolean(keys[which], isChecked).apply()
            }
            .setPositiveButton("閉じる", null)
            .show()
    }

    // ── 完了カード（開く／共有） ─────────────────────────────────

    private fun firstSavedFile(): DownloadState.SavedFile? =
        DownloadState.ui.value.savedFiles.firstOrNull()

    private fun openFile(file: DownloadState.SavedFile) {
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(android.net.Uri.parse(file.uri), file.mime)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        try {
            startActivity(intent)
        } catch (e: android.content.ActivityNotFoundException) {
            Toast.makeText(this, "ePubリーダーアプリをインストールしてください",
                Toast.LENGTH_LONG).show()
        }
    }

    private fun shareFile(file: DownloadState.SavedFile) {
        val intent = Intent(Intent.ACTION_SEND)
            .setType(file.mime)
            .putExtra(Intent.EXTRA_STREAM, android.net.Uri.parse(file.uri))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        startActivity(Intent.createChooser(intent, file.name))
    }

    // ── サイト判定バッジ ─────────────────────────────────────────

    private fun onUrlChanged() {
        val text = urlInput.text.toString().trim()
        detectedUrl = null
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
                siteBadge.text = "⚠ 判定エラー"
            json.optBoolean("needs_playwright") ->
                siteBadge.text = "⚠ ハーメルンはアプリ版では非対応です"
            !json.isNull("site") -> {
                detectedUrl = json.optString("normalized_url", input).ifEmpty { input }
                siteBadge.text = "◉ ${json.optString("display_name")}"
            }
            Regex("""^https?://\S+$""").matches(input) &&
                    !input.contains("syosetu.org") -> {
                // 短縮URLの可能性: 本体が実行時に展開するので許可する
                detectedUrl = input
                siteBadge.text = "🔗 サイト未判定（短縮URLなら実行時に展開されます）"
            }
            else ->
                siteBadge.text = "⚠ 未対応のURLです"
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
        val url = detectedUrl ?: return
        val intent = Intent(this, DownloadService::class.java)
            .putExtra(DownloadService.EXTRA_URL, url)
        ContextCompat.startForegroundService(this, intent)
    }

    // ── 状態 → 画面反映 ──────────────────────────────────────────

    private fun render(ui: DownloadState.Ui) {
        updateMainButton()
        btnMain.text = if (ui.isRunning) "⏸ 中止" else "⬇ ダウンロード"

        val done = ui.phase == DownloadState.Phase.DONE && ui.savedFiles.isNotEmpty()
        doneCard.visibility = if (done) View.VISIBLE else View.GONE
        if (done) {
            doneFile.text = ui.savedFiles.joinToString("\n") { it.name }
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
                statusLine.text = ui.statusLine
            }
            DownloadState.Phase.DOWNLOADING -> {
                progressBar.visibility = View.VISIBLE
                progressBar.isIndeterminate = false
                progressBar.max = ui.total.coerceAtLeast(1)
                progressBar.progress = ui.n
                progressText.visibility = View.VISIBLE
                progressText.text = "${ui.n} / ${ui.total} 話"
                statusLine.text = ui.statusLine
            }
            DownloadState.Phase.DONE, DownloadState.Phase.CANCELLED -> {
                progressBar.visibility = View.GONE
                progressText.visibility = View.GONE
                statusLine.text = ui.statusLine
            }
            DownloadState.Phase.ERROR -> {
                progressBar.visibility = View.GONE
                progressText.visibility = View.GONE
                statusLine.text = ui.statusLine
                logScroll.visibility = View.VISIBLE   // エラー時はログを自動展開
                logToggle.text = "▾ 詳細ログ"
            }
        }
    }
}
