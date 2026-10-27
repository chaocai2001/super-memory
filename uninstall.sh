#!/usr/bin/env bash
# super-memory 卸载：移除 launchd 任务、各 harness 的 skill 与 AGENTS.md 协议块。
# 默认保留记忆数据（~/.super-memory）与仓库内 .venv；--purge 一并删除。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
OPENCODE_CONFIG_HOME="${OPENCODE_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/opencode}"
KIMI_CODE_HOME="${KIMI_CODE_HOME:-$HOME/.kimi-code}"
PURGE=0
HARNESSES=()

for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        --harness=*) HARNESSES+=("${arg#--harness=}") ;;
        -h|--help)
            echo "usage: ./uninstall.sh [--purge] [--harness codex|opencode|kimi|all]"
            exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

want_codex=0
want_opencode=0
want_kimi=0
if [[ ${#HARNESSES[@]} -eq 0 || " ${HARNESSES[*]} " == *" all "* ]]; then
    want_codex=1
    want_opencode=1
    want_kimi=1
else
    for h in "${HARNESSES[@]}"; do
        case "$h" in
            codex) want_codex=1 ;;
            opencode) want_opencode=1 ;;
            kimi) want_kimi=1 ;;
            *) echo "unknown harness: $h（可选 codex|opencode|kimi|all）" >&2; exit 2 ;;
        esac
    done
fi

step() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

remove_agents_block() {
    local agents="$1"
    if [[ -f "$agents" ]] && grep -q '<!-- super-memory:start -->' "$agents"; then
        awk '/<!-- super-memory:start -->/{skip=1} /<!-- super-memory:end -->/{skip=0; next} !skip' "$agents" > "$agents.tmp"
        mv "$agents.tmp" "$agents"
    fi
}

# launchd 定时任务服务所有 harness，只在整体卸载（缺省 all）时移除
if [[ $want_codex -eq 1 && $want_opencode -eq 1 && $want_kimi -eq 1 && "$(uname)" == "Darwin" ]]; then
    step "卸载 launchd 定时任务"
    launchctl bootout "gui/$(id -u)/com.supermemory.digest" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/com.supermemory.digest.plist"
fi

if [[ $want_codex -eq 1 ]]; then
    step "移除 codex skill 与 AGENTS.md 协议块"
    rm -rf "$CODEX_HOME/skills/super-memory"
    remove_agents_block "$CODEX_HOME/AGENTS.md"

    PYBIN="$REPO_DIR/.venv/bin/python"
    [[ -x "$PYBIN" ]] || PYBIN="${PYTHON:-python3}"
    step "从 config.toml 移除 ~/.super-memory 沙箱放行"
    "$PYBIN" "$REPO_DIR/scripts/codex_config.py" remove \
        --codex-home "$CODEX_HOME" --memory-dir "$HOME/.super-memory" 2>/dev/null \
        || echo "跳过 config.toml 清理（python 不可用或配置不存在）"
fi

if [[ $want_opencode -eq 1 ]]; then
    step "移除 opencode skill 与 AGENTS.md 协议块"
    rm -rf "$OPENCODE_CONFIG_HOME/skills/super-memory"
    remove_agents_block "$OPENCODE_CONFIG_HOME/AGENTS.md"
fi

if [[ $want_kimi -eq 1 ]]; then
    step "移除 Kimi Code skill 与 AGENTS.md 协议块"
    rm -rf "$KIMI_CODE_HOME/skills/super-memory"
    remove_agents_block "$KIMI_CODE_HOME/AGENTS.md"
fi

if [[ "$PURGE" -eq 1 ]]; then
    step "删除记忆数据 ~/.super-memory 与 .venv"
    rm -rf "$HOME/.super-memory" "$REPO_DIR/.venv"
else
    echo "保留记忆数据 ~/.super-memory 与 $REPO_DIR/.venv（--purge 可一并删除）"
fi

step "卸载完成"
