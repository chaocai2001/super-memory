#!/bin/bash
# super-memory opencode 消化 worker：无积压时直接退出，有积压时让 opencode 跑蒸馏协议二。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM="$REPO_DIR/.venv/bin/supermemory"
BATCHES="${SM_DIGEST_BATCHES:-10}"
MAX_SESSIONS="${SM_DIGEST_MAX_SESSIONS:-$((BATCHES * 5))}"

if ! command -v opencode >/dev/null 2>&1; then
    echo "$(date '+%F %T') opencode CLI not found" >&2
    exit 1
fi

if ! "$SM" pending --json --limit 1 | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin)['sessions'] else 1)"; then
    echo "$(date '+%F %T') no pending sessions, skip"
    exit 0
fi

echo "$(date '+%F %T') pending backlog found, starting opencode digest (${MAX_SESSIONS} sessions max)"
opencode run --title "super-memory digest" --dangerously-skip-permissions --dir "$REPO_DIR" \
    "你是 super-memory 记忆系统的无人值守消化 worker。严格按照 ~/.config/opencode/skills/super-memory/SKILL.md 的协议二执行：每批用 $SM pending --json --limit N 取积压，N 为 5 与本轮剩余配额的较小者；按 skill 的 wiki 原则为每条会话产出 ops 文件，然后 apply。如此重复，本轮最多处理 ${MAX_SESSIONS} 个会话，达到上限或没有积压时停止。读完没有价值的会话也要列入 sessions（ops 为空）以确认消化。不要向用户提问，不要做任何与记忆消化无关的事。完成后用一行总结处理了几条会话、创建/更新了哪些页面。"
echo "$(date '+%F %T') digest finished"
