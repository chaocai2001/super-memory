#!/bin/bash
# super-memory 定期消化入口（launchd 或手动调用）——调度器。
# 无积压时直接退出，不起 worker 会话；有积压时优先 codex worker，无 codex 时回落 opencode worker。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM="$REPO_DIR/.venv/bin/supermemory"

if ! "$SM" pending --json --limit 1 | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin)['sessions'] else 1)"; then
    echo "$(date '+%F %T') no pending sessions, skip"
    exit 0
fi

if [[ -n "${CODEX_BIN:-}" ]] || command -v codex >/dev/null 2>&1 \
        || [[ -x /Applications/ChatGPT.app/Contents/Resources/codex ]]; then
    exec "$REPO_DIR/scripts/digest_codex.sh"
elif command -v opencode >/dev/null 2>&1; then
    exec "$REPO_DIR/scripts/digest_opencode.sh"
else
    echo "$(date '+%F %T') neither codex nor opencode CLI found; set CODEX_BIN" >&2
    exit 1
fi
