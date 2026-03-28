<# :
@echo off
setlocal EnableDelayedExpansion

rem =====================================================================
rem ★ ユーザー設定ここから ★
rem =====================================================================

rem フォントファイルのパス（不要な場合は空にする）
set "OPT_FONT="
set "OPT_FONT=C:/Users/ayati/OneDrive/fonts/AyatiShowaSerif-Regular.ttf"

rem 出力形式オプション（不要な場合は空にする）
rem 例: --kobo  --kindle  --epub など
set "OPT_FORMAT=--kobo"

rem その他追加オプション（不要な場合は空にする）
rem 例: --timeout 30  --encoding utf-8 など
set "OPT_EXTRA=--use-site-cover"

rem =====================================================================
rem ★ ユーザー設定ここまで ★
rem =====================================================================

rem オプション文字列を組み立てる
set "EXE_OPTS="
if not "!OPT_FONT!"==""   set "EXE_OPTS=!EXE_OPTS! --font !OPT_FONT!"
if not "!OPT_FORMAT!"=="" set "EXE_OPTS=!EXE_OPTS! !OPT_FORMAT!"
if not "!OPT_EXTRA!"==""  set "EXE_OPTS=!EXE_OPTS! !OPT_EXTRA!"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Expression (Get-Content '%~f0' -Raw)"`) do set "CLIP_URL=%%I"

if "!CLIP_URL!"=="" goto :EOF
if "!CLIP_URL!"=="ERROR" goto :EOF

echo =========================================
echo 対象URL: !CLIP_URL!
if not "!EXE_OPTS!"=="" echo オプション:!EXE_OPTS!
echo =========================================

novel_downloader.exe "!CLIP_URL!"!EXE_OPTS!

if !ERRORLEVEL! equ 0 (
    echo.
    echo 処理が正常に完了しました。保存先フォルダを開きます。
    explorer "%~dp0"
    timeout /t 10 /nobreak
) else (
    echo.
    echo エラーが発生しました（終了コード: !ERRORLEVEL!）。
    pause
)

goto :EOF
#>

# =====================================================================
# PowerShell スクリプト部
# =====================================================================
Add-Type -AssemblyName System.Windows.Forms

$clip = Get-Clipboard -Raw -ErrorAction SilentlyContinue

# 1. 空チェック
if ([string]::IsNullOrWhiteSpace($clip)) {
    [System.Windows.Forms.MessageBox]::Show(
        "クリップボードが空です。`nURLをコピーしてから起動してください。",
        "エラー",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
    Write-Output "ERROR"
    exit
}

# 2. 改行・前後空白を除去（複数行テキスト対策）
$clip = $clip.Trim() -replace "`r`n|`n|`r", ""

# 3. サニタイズ：バッチ特殊文字を含む危険文字を除去
$clip = $clip -replace '["%''<>|`\s!^&()%]', ''

# 4. URLスキームチェック
if ($clip -notmatch "^https?://") {
    [System.Windows.Forms.MessageBox]::Show(
        "クリップボードの内容がURLではありません。`nブラウザのアドレス欄のURLをコピーしてください。",
        "エラー",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
    Write-Output "ERROR"
    exit
}

# 5. .NET による厳密なURL検証
if (-not [System.Uri]::IsWellFormedUriString($clip, [System.UriKind]::Absolute)) {
    [System.Windows.Forms.MessageBox]::Show(
        "URLの形式が正しくありません。`n正しいURLをコピーし直してください。",
        "セキュリティ警告",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    Write-Output "ERROR"
    exit
}

Write-Output $clip
