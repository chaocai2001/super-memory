#!/bin/bash
# super-memory 定期消化入口（launchd 或手动调用）。
# 无积压时直接退出，不起 codex 会话；有积压时让 codex 自己跑蒸馏协议。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SM="$REPO_DIR/.venv/bin/supermemory"
BATCHES="${SM_DIGEST_BATCHES:-3}"

# 定位 codex CLI：环境变量 > PATH > ChatGPT.app 内置
if [[ -n "${CODEX_BIN:-}" ]]; then
    CODEX="$CODEX_BIN"
elif command -v codex >/dev/null 2>&1; then
    CODEX="$(command -v codex)"
elif [[ -x /Applications/ChatGPT.app/Contents/Resources/codex ]]; then
    CODEX=/Applications/ChatGPT.app/Contents/Resources/codex
else
    echo "$(date '+%F %T') codex CLI not found; set CODEX_BIN" >&2
    exit 1
fi

if ! "$SM" pending --json --limit 1 | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin)['sessions'] else 1)"; then
    echo "$(date '+%F %T') no pending sessions, skip"
    exit 0
fi

echo "$(date '+%F %T') pending backlog found, starting codex digest (${BATCHES} batches max)"
"$CODEX" exec --ephemeral --skip-git-repo-check \
    -s danger-full-access -c approval_policy="never" \
    -C "$REPO_DIR" \
    "你是 super-memory 记忆系统的无人值守消化 worker。严格按照 ~/.codex/skills/super-memory/SKILL.md 的协议二执行：用 $SM pending --json --limit 5 取积压，按 skill 的 wiki 原则为每条会话产出 ops 文件，然后 apply。如此重复，最多处理 ${BATCHES} 批。读完没有价值的会话也要列入 sessions（ops 为空）以确认消化。不要向用户提问，不要做任何与记忆消化无关的事。完成后用一行总结处理了几条会话、创建/更新了哪些页面。"
echo "$(date '+%F %T') digest finished"
