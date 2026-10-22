#!/usr/bin/env bash
# super-memory 卸载：移除 launchd 任务、codex skill、AGENTS.md 协议块。
# 默认保留记忆数据（~/.super-memory）与仓库内 .venv；--purge 一并删除。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

step() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

if [[ "$(uname)" == "Darwin" ]]; then
    step "卸载 launchd 定时任务"
    launchctl bootout "gui/$(id -u)/com.supermemory.digest" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/com.supermemory.digest.plist"
fi

step "移除 codex skill"
rm -rf "$CODEX_HOME/skills/super-memory"

AGENTS="$CODEX_HOME/AGENTS.md"
if [[ -f "$AGENTS" ]] && grep -q '<!-- super-memory:start -->' "$AGENTS"; then
    step "移除 AGENTS.md 记忆协议块"
    awk '/<!-- super-memory:start -->/{skip=1} /<!-- super-memory:end -->/{skip=0; next} !skip' "$AGENTS" > "$AGENTS.tmp"
    mv "$AGENTS.tmp" "$AGENTS"
fi

PYBIN="$REPO_DIR/.venv/bin/python"
[[ -x "$PYBIN" ]] || PYBIN="${PYTHON:-python3}"
step "从 config.toml 移除 ~/.super-memory 沙箱放行"
"$PYBIN" "$REPO_DIR/scripts/codex_config.py" remove \
    --codex-home "$CODEX_HOME" --memory-dir "$HOME/.super-memory" 2>/dev/null \
    || echo "跳过 config.toml 清理（python 不可用或配置不存在）"

if [[ "$PURGE" -eq 1 ]]; then
    step "删除记忆数据 ~/.super-memory 与 .venv"
    rm -rf "$HOME/.super-memory" "$REPO_DIR/.venv"
else
    echo "保留记忆数据 ~/.super-memory 与 $REPO_DIR/.venv（--purge 可一并删除）"
fi

step "卸载完成"
