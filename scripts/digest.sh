#!/bin/bash
# super-memory 定期消化入口（launchd 或手动调用）——调度器。
# 无积压时直接退出，不起 worker 会话；有积压时按 codex → opencode → Kimi Code → Claude Code 顺序选择 worker。
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
elif command -v kimi >/dev/null 2>&1 \
        || [[ -x "${KIMI_CODE_HOME:-$HOME/.kimi-code}/bin/kimi" ]]; then
    exec "$REPO_DIR/scripts/digest_kimi.sh"
elif [[ -n "${CLAUDE_BIN:-}" ]] || command -v claude >/dev/null 2>&1 \
        || [[ -x "$HOME/.local/bin/claude" ]]; then
    exec "$REPO_DIR/scripts/digest_claude.sh"
else
    echo "$(date '+%F %T') no codex, opencode, kimi, or claude CLI found; set CODEX_BIN, KIMI_BIN, or CLAUDE_BIN" >&2
    exit 1
fi
