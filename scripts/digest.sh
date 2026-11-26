#!/bin/bash
# super-memory 定期消化入口（launchd 或手动调用）——调度器。
# 无积压时直接退出，不起 worker 会话；有积压时按 codex → opencode → Kimi Code → Claude Code 顺序选择 worker。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM="$REPO_DIR/.venv/bin/supermemory"
IDLE_SECONDS="${SM_DIGEST_IDLE_SECONDS:-0}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-sessions)
            if [[ $# -lt 2 ]]; then
                echo "--max-sessions requires a positive integer" >&2
                exit 2
            fi
            MAX_SESSIONS="$2"
            shift 2
            ;;
        --max-sessions=*)
            MAX_SESSIONS="${1#--max-sessions=}"
            shift
            ;;
        --idle-seconds)
            if [[ $# -lt 2 ]]; then
                echo "--idle-seconds requires a non-negative integer" >&2
                exit 2
            fi
            IDLE_SECONDS="$2"
            shift 2
            ;;
        --idle-seconds=*)
            IDLE_SECONDS="${1#--idle-seconds=}"
            shift
            ;;
        -h|--help)
            echo "usage: ./scripts/digest.sh [--max-sessions N] [--idle-seconds N]"
            echo "  --max-sessions N  limit sessions per run; overrides SM_DIGEST_MAX_SESSIONS"
            echo "  --idle-seconds N  only digest sessions idle for N seconds (default: 0)"
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            exit 2
            ;;
    esac
done

if [[ ${MAX_SESSIONS+x} ]]; then
    if ! [[ "$MAX_SESSIONS" =~ ^[1-9][0-9]*$ ]]; then
        echo "--max-sessions requires a positive integer" >&2
        exit 2
    fi
    export SM_DIGEST_MAX_SESSIONS="$MAX_SESSIONS"
fi

if ! [[ "$IDLE_SECONDS" =~ ^[0-9]+$ ]]; then
    echo "--idle-seconds/SM_DIGEST_IDLE_SECONDS requires a non-negative integer" >&2
    exit 2
fi
export SM_DIGEST_IDLE_SECONDS="$IDLE_SECONDS"

LOCK_FILE="${SM_DIGEST_LOCK_FILE:-$HOME/.super-memory/digest.lock}"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! python3 -c 'import fcntl, sys
try:
    fcntl.flock(int(sys.argv[1]), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(1)' 9; then
    echo "$(date '+%F %T') another digest is running, skip"
    exit 0
fi

PENDING="$("$SM" pending --json --idle-seconds "$IDLE_SECONDS" --limit 1)"
PENDING_STATUS=0
PENDING_SUMMARY="$(python3 -c 'import json,sys
data = json.load(sys.stdin)
deferred = data.get("deferred_sessions", 0)
print(f"{deferred} active session(s) deferred" if deferred else "")
sys.exit(0 if data["sessions"] else 2)' <<<"$PENDING")" || PENDING_STATUS=$?
if [[ $PENDING_STATUS -eq 2 ]]; then
    echo "$(date '+%F %T') no ready pending sessions${PENDING_SUMMARY:+, $PENDING_SUMMARY}, skip"
    exit 0
elif [[ $PENDING_STATUS -ne 0 ]]; then
    exit "$PENDING_STATUS"
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
