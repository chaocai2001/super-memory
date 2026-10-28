#!/bin/bash
# super-memory Claude Code 消化 worker：无积压时直接退出，有积压时让 claude 跑蒸馏协议二。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM="$REPO_DIR/.venv/bin/supermemory"
BATCHES="${SM_DIGEST_BATCHES:-10}"
MAX_SESSIONS="${SM_DIGEST_MAX_SESSIONS:-$((BATCHES * 5))}"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

if [[ -n "${CLAUDE_BIN:-}" ]]; then
    CLAUDE="$CLAUDE_BIN"
elif command -v claude >/dev/null 2>&1; then
    CLAUDE="$(command -v claude)"
elif [[ -x "$HOME/.local/bin/claude" ]]; then
    CLAUDE="$HOME/.local/bin/claude"
else
    echo "$(date '+%F %T') claude CLI not found; set CLAUDE_BIN" >&2
    exit 1
fi

PENDING="$("$SM" pending --json --limit 1)"
PENDING_STATUS=0
python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin)['sessions'] else 2)" <<<"$PENDING" || PENDING_STATUS=$?
if [[ $PENDING_STATUS -eq 2 ]]; then
    echo "$(date '+%F %T') no pending sessions, skip"
    exit 0
elif [[ $PENDING_STATUS -ne 0 ]]; then
    exit "$PENDING_STATUS"
fi

echo "$(date '+%F %T') pending backlog found, starting Claude Code digest (${MAX_SESSIONS} sessions max)"
cd "$REPO_DIR"
"$CLAUDE" -p --no-session-persistence --permission-mode bypassPermissions \
    --verbose --output-format stream-json --include-partial-messages \
    "super-memory digest 你是 super-memory 记忆系统的无人值守消化 worker。严格按照 $CLAUDE_HOME/skills/super-memory/SKILL.md 的协议二执行：每批用 $SM pending --json --limit N 取积压，N 为 5 与本轮剩余配额的较小者；按 skill 的 wiki 原则为每条会话产出 ops 文件，然后 apply。如此重复，本轮最多处理 ${MAX_SESSIONS} 个会话，达到上限或没有积压时停止。读完没有价值的会话也要列入 sessions（ops 为空）以确认消化。不要向用户提问，不要做任何与记忆消化无关的事。完成后用一行总结处理了几条会话、创建/更新了哪些页面。" |
python3 -u -c '
import json
import sys

for line in sys.stdin:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue

    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        model = event.get("model", "unknown")
        print(f"worker started (model: {model})", flush=True)
    elif kind == "system" and event.get("subtype") == "status":
        status = event.get("status", "unknown")
        print(f"worker status: {status}", flush=True)
    elif kind == "stream_event":
        inner = event.get("event", {})
        if inner.get("type") == "content_block_start":
            block = inner.get("content_block", {})
            if block.get("type") == "thinking":
                print("worker thinking...", flush=True)
        elif inner.get("type") == "content_block_delta":
            delta = inner.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta.get("text", ""), end="", flush=True)
    elif kind == "assistant":
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                inputs = block.get("input", {})
                detail = inputs.get("command") or inputs.get("file_path") or ""
                detail = detail.splitlines()[0][:160] if detail else ""
                suffix = f": {detail}" if detail else ""
                name = block.get("name", "unknown")
                print(f"\n[tool] {name}{suffix}", flush=True)
    elif kind == "result":
        print(flush=True)
        if event.get("is_error"):
            print(event.get("result", "Claude Code digest failed"), file=sys.stderr, flush=True)
'
echo "$(date '+%F %T') digest finished"
