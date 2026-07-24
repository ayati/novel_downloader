#!/usr/bin/env bash
#
# novel_downloader 統合リリーススクリプト（Python 本体 + Android APK を一手に）
#
#   scripts/release.sh <X.Y.Z> [オプション]
#
# 何をするか（この順に）:
#   1. 前提チェック（main ブランチ / tracked な未コミット変更なし / gh 認証）
#   2. タグ vX.Y.Z を作成し main とタグを push
#   3. Android APK をビルド（versionName=X.Y.Z / versionCode=major*10000+minor*100+patch）
#   4. APK を android/noveldownloader_vX.Y.Z.apk にリネーム
#   5. 鮮度スタンプ android/.apk_built_from（novel_downloader.py の sha256）を更新
#   6. GitHub Release vX.Y.Z を作成（無ければ）し、APK をアセット添付
#
# オプション:
#   --notes-file FILE   リリースノート本文（省略時は --generate-notes で自動生成）
#   --title TITLE       リリースタイトル（省略時は "vX.Y.Z"）
#   --apk-only          タグ/Release 作成をスキップし、既存 Release vX.Y.Z に
#                       APK をビルド＆添付するだけ（「リリース済みだが APK を作り忘れた」時用）
#   --yes               確認プロンプトを省略
#   --no-release        APK のビルド/リネーム/スタンプまでで止め、push/Release はしない
#
set -euo pipefail

die()  { echo "❌ $*" >&2; exit 1; }
info() { echo "▶ $*" >&2; }

# ---- 引数 ----
[ $# -ge 1 ] || die "版数を指定してください（例: scripts/release.sh 2.3.0）"
RAW_VER="$1"; shift
VER="${RAW_VER#v}"
[[ "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "版数は X.Y.Z 形式で指定してください（受領: '$RAW_VER'）"
TAG="v$VER"

NOTES_FILE=""; TITLE="$TAG"; APK_ONLY=0; ASSUME_YES=0; NO_RELEASE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --notes-file) NOTES_FILE="${2:-}"; shift 2 ;;
    --title)      TITLE="${2:-}"; shift 2 ;;
    --apk-only)   APK_ONLY=1; shift ;;
    --yes|-y)     ASSUME_YES=1; shift ;;
    --no-release) NO_RELEASE=1; shift ;;
    *) die "不明なオプション: $1" ;;
  esac
done
[ -z "$NOTES_FILE" ] || [ -f "$NOTES_FILE" ] || die "notes ファイルが見つかりません: $NOTES_FILE"

# ---- リポジトリルート ----
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[ -f novel_downloader.py ] || die "リポジトリルートに novel_downloader.py がありません（$ROOT）"
[ -d android ] || die "android/ がありません"
APK_OUT="android/app/build/outputs/apk/debug/app-debug.apk"
APK_DIST="android/noveldownloader_${TAG}.apk"
STAMP="android/.apk_built_from"

# ---- 前提チェック ----
BR="$(git rev-parse --abbrev-ref HEAD)"
[ "$BR" = "main" ] || info "⚠ 現在のブランチは '$BR'（通常は main でリリース）"
if ! git diff --quiet || ! git diff --cached --quiet; then
  die "tracked な未コミット変更があります。コミットしてから実行してください（未追跡ファイルは無視されます）"
fi
command -v gh >/dev/null || die "gh（GitHub CLI）が必要です"

# ---- 実行内容の提示と確認 ----
echo "──────────────────────────────────────────" >&2
echo " リリース版数 : $TAG   (APK versionName=$VER)" >&2
if [ "$APK_ONLY" = 1 ]; then
  echo " モード       : --apk-only（既存 Release にAPKを添付するだけ）" >&2
elif [ "$NO_RELEASE" = 1 ]; then
  echo " モード       : --no-release（ローカルでAPKビルドのみ）" >&2
else
  echo " 操作         : タグ push → APKビルド → Release作成/添付" >&2
  echo " ノート       : ${NOTES_FILE:-（--generate-notes 自動生成）}" >&2
fi
echo "──────────────────────────────────────────" >&2
if [ "$ASSUME_YES" != 1 ]; then
  read -r -p "続行しますか? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || die "中止しました"
fi

# ---- 1) __version__ 更新コミット → タグ → push（--apk-only / --no-release ではスキップ）----
if [ "$APK_ONLY" != 1 ] && [ "$NO_RELEASE" != 1 ]; then
  # 版数の単一ソース novel_downloader.py の __version__ を $VER に設定（変化があればコミット）
  info "__version__ を $VER に設定"
  VER="$VER" python3 - <<'PY'
import os, re, sys
ver = os.environ["VER"]; p = "novel_downloader.py"
s = open(p, encoding="utf-8").read()
new, n = re.subn(r'(__version__\s*=\s*)["\'][^"\']*["\']',
                 lambda m: m.group(1) + '"' + ver + '"', s, count=1)
if n == 0:
    sys.exit("__version__ が novel_downloader.py に見つかりません")
if new != s:
    open(p, "w", encoding="utf-8").write(new)
PY
  if ! git diff --quiet novel_downloader.py; then
    git add novel_downloader.py
    git commit -m "release: $TAG"
    info "release コミットを作成（__version__=$VER）"
  else
    info "__version__ は既に $VER（コミット不要）"
  fi
  # タグ（__version__ 更新後のコミットを指す）
  if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    info "タグ $TAG は既に存在（作成をスキップ）"
  else
    git tag -a "$TAG" -m "$TITLE"
    info "タグ $TAG を作成"
  fi
  info "main とタグを push"
  git push origin "$BR"
  git push origin "$TAG"
fi

# ---- 2) APK ビルド ----
info "APK をビルド（-PappVersion=$VER）"
( cd android && ./gradlew assembleDebug -PappVersion="$VER" --console=plain )
[ -f "$APK_OUT" ] || die "APK が生成されませんでした: $APK_OUT"
cp -f "$APK_OUT" "$APK_DIST"
info "APK: $APK_DIST ($(du -h "$APK_DIST" | cut -f1))"

# ---- 3) 鮮度スタンプ（B: 陳腐化ガード用）----
sha256sum novel_downloader.py | awk '{print $1}' > "$STAMP"
info "鮮度スタンプを更新: $STAMP"

if [ "$NO_RELEASE" = 1 ]; then
  echo "✅ ローカルビルド完了（push/Release はスキップ）: $APK_DIST" >&2
  exit 0
fi

# ---- 4) GitHub Release 作成（無ければ）＋ APK 添付 ----
if gh release view "$TAG" >/dev/null 2>&1; then
  info "Release $TAG は既存（作成をスキップ）"
else
  [ "$APK_ONLY" != 1 ] || die "Release $TAG が存在しません（--apk-only は既存Release向け）"
  info "Release $TAG を作成"
  if [ -n "$NOTES_FILE" ]; then
    gh release create "$TAG" --title "$TITLE" --notes-file "$NOTES_FILE"
  else
    gh release create "$TAG" --title "$TITLE" --generate-notes
  fi
fi
info "APK を Release に添付"
gh release upload "$TAG" "$APK_DIST" --clobber

echo "✅ 完了: $TAG / $APK_DIST → $(gh release view "$TAG" --json url -q .url)" >&2
