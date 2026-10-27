#!/bin/bash
# super-memory Kimi Code 消化 worker：无积压时直接退出，有积压时让 kimi 跑蒸馏协议二。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM="$REPO_DIR/.venv/bin/supermemory"
BATCHES="${SM_DIGEST_BATCHES:-3}"
KIMI_HOME="${KIMI_CODE_HOME:-$HOME/.kimi-code}"

if [[ -n "${KIMI_BIN:-}" ]]; then
    KIMI="$KIMI_BIN"
elif command -v kimi >/dev/null 2>&1; then
    KIMI="$(command -v kimi)"
elif [[ -x "$KIMI_HOME/bin/kimi" ]]; then
    KIMI="$KIMI_HOME/bin/kimi"
else
    echo "$(date '+%F %T') kimi CLI not found; set KIMI_BIN" >&2
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

echo "$(date '+%F %T') pending backlog found, starting Kimi Code digest (${BATCHES} batches max)"
cd "$REPO_DIR"
"$KIMI" -p "super-memory digest 你是 super-memory 记忆系统的无人值守消化 worker。严格按照 $KIMI_HOME/skills/super-memory/SKILL.md 的协议二执行：用 $SM pending --json --limit 5 取积压，按 skill 的 wiki 原则为每条会话产出 ops 文件，然后 apply。如此重复，最多处理 ${BATCHES} 批。读完没有价值的会话也要列入 sessions（ops 为空）以确认消化。不要向用户提问，不要做任何与记忆消化无关的事。完成后用一行总结处理了几条会话、创建/更新了哪些页面。"
echo "$(date '+%F %T') digest finished"
