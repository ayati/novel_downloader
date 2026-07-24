#!/usr/bin/env bash
# git フックを .git/hooks にインストールする（陳腐化ガード pre-push）。
# フック本体は scripts/hooks/ にありバージョン管理される。ここでシンボリックリンクを張る。
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$ROOT/scripts/hooks/pre-push"
HOOK_DST="$ROOT/.git/hooks/pre-push"
[ -f "$HOOK_SRC" ] || { echo "❌ $HOOK_SRC がありません" >&2; exit 1; }
chmod +x "$HOOK_SRC"
ln -sf ../../scripts/hooks/pre-push "$HOOK_DST"
echo "✅ pre-push フックをインストールしました: $HOOK_DST -> scripts/hooks/pre-push"
