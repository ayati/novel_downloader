<# :
@echo off
setlocal EnableDelayedExpansion

rem =====================================================================
rem ★ ユーザー設定ここから ★
rem =====================================================================

rem ★★ OneDrive のユーザー名をここだけ変更 ★★
set "ONEDRIVE_USER=ayati"

rem OneDrive ルートパス（通常はここを変更する必要はありません）
set "OD=C:\Users\!ONEDRIVE_USER!\OneDrive"

rem 監視フォルダ
rem OneDrive直下に、新規にtrigerという名前のフォルダを作ってください。
rem エクスプローラー上で右クリックし、「このデバイス上で常に保持する」設定をしてください。
set "TARGET_FOLDER=!OD!\triger"

rem novel_downloader の実行ファイル（.exe）または python スクリプト
rem .exe の場合:
set "DOWNLOADER=!OD!\novel_downloader.exe"
rem .py の場合は上をコメントアウトして下を有効化:
rem set "DOWNLOADER_PY=!OD!\novel_downloader.py"

rem オプション定義（重複しないよう各項目1つだけ設定）
set "OPT_OUTPUT=--output-dir !OD!\epub"
set "OPT_FONT=--font !OD!\fonts\AyatiShowaSerif-Regular.ttf"
set "OPT_FORMAT=--kobo"
set "OPT_EXTRA="

rem =====================================================================
rem ★ ユーザー設定ここまで ★
rem =====================================================================

rem オプション文字列を組み立てる
set "EXE_OPTS="
if not "!OPT_OUTPUT!"=="" set "EXE_OPTS=!EXE_OPTS! !OPT_OUTPUT!"
if not "!OPT_FONT!"==""   set "EXE_OPTS=!EXE_OPTS! !OPT_FONT!"
if not "!OPT_FORMAT!"=="" set "EXE_OPTS=!EXE_OPTS! !OPT_FORMAT!"
if not "!OPT_EXTRA!"==""  set "EXE_OPTS=!EXE_OPTS! !OPT_EXTRA!"

rem 監視フォルダの存在確認
if not exist "!TARGET_FOLDER!" (
    echo [ERROR] 監視フォルダが見つかりません: !TARGET_FOLDER!
    pause
    goto :EOF
)

echo =========================================
echo フォルダ監視を開始します
echo 監視対象: !TARGET_FOLDER!
echo 停止するには Ctrl+C を押してください
echo =========================================
echo.

rem 処理済みファイルを記録する一時ファイル
:WATCH_LOOP
    for %%F in ("!TARGET_FOLDER!\*") do (
        set "TXT_FILE=%%~fF"

        if not exist "!TARGET_FOLDER!\done" mkdir "!TARGET_FOLDER!\done"
        if not exist "!TARGET_FOLDER!\done\%%~nxF" (
            echo [!TIME!] 新しいファイルを検知しました: %%~nxF
            timeout /t 1 /nobreak >nul

            rem 環境変数経由でファイルパスをPowerShell部に渡す
            set "WATCHER_TARGET_FILE=!TXT_FILE!"
            set "VALIDATED_URL="

            for /f "usebackq delims=" %%U in (`powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "Invoke-Expression (Get-Content '%~f0' -Raw)" 2^>nul`) do set "VALIDATED_URL=%%U"

            if "!VALIDATED_URL!"=="ERROR" (
                echo [!TIME!] URLの検証に失敗しました。スキップします: %%~nxF
            ) else if "!VALIDATED_URL!"=="" (
                echo [!TIME!] URLを取得できませんでした。スキップします: %%~nxF
            ) else (
                echo [!TIME!] ダウンローダーを起動します
                echo          URL    : !VALIDATED_URL!
                echo          オプション:!EXE_OPTS!
                echo.

                if defined DOWNLOADER (
                    "!DOWNLOADER!" "!VALIDATED_URL!"!EXE_OPTS!
                ) else (
                    python "!DOWNLOADER_PY!" "!VALIDATED_URL!"!EXE_OPTS!
                )

                if !ERRORLEVEL! equ 0 (
                    echo [!TIME!] 完了しました: %%~nxF
                ) else (
                    echo [!TIME!] エラーが発生しました（終了コード: !ERRORLEVEL!）: %%~nxF
                )
                echo.
            )

            move /y "!TXT_FILE!" "!TARGET_FOLDER!\done\" >nul
        )
    )
    set "VALIDATED_URL="
    set "WATCHER_TARGET_FILE="

timeout /t 2 /nobreak >nul
goto WATCH_LOOP

goto :EOF
#>

# =====================================================================
# PowerShell スクリプト部 ― 環境変数からファイルパスを受け取りURLを検証して返す
# =====================================================================
$WarningPreference  = "SilentlyContinue"
$InformationPreference = "SilentlyContinue"

# バッチ側がセットした環境変数からファイルパスを取得
$FilePath = $env:WATCHER_TARGET_FILE

if (-not $FilePath -or -not (Test-Path $FilePath)) {
    Write-Output "ERROR"
    exit 1
}

$content = Get-Content -Path $FilePath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
if ([string]::IsNullOrWhiteSpace($content)) {
    Write-Output "ERROR"
    exit 1
}

# 行中のどこにあっても最初の URL を抽出（行頭・文中・スペース後も対応）
$url = $null
foreach ($line in ($content -split "`n")) {
    if (($line.Trim() -replace "`r", "") -match "(https?://\S+)") {
        $url = $Matches[1]
        break
    }
}

if (-not $url) {
    Write-Output "ERROR"
    exit 1
}

# サニタイズ: バッチ経由で渡す危険文字を除去
$url = $url -replace '["%''<>|`\s!^&()%]', ''

# URL スキーマ確認（サニタイズ後の念のため）
if ($url -notmatch "^https?://") {
    Write-Output "ERROR"
    exit 1
}

# .NET による厳密なURL検証
if (-not [System.Uri]::IsWellFormedUriString($url, [System.UriKind]::Absolute)) {
    Write-Output "ERROR"
    exit 1
}

# URLのみを標準出力に1行出力
Write-Output $url
exit 0
