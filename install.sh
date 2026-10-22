#!/usr/bin/env bash
# super-memory 一键安装：venv + CLI + codex skill + AGENTS.md 协议 + launchd 定时消化
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
WITH_LAUNCHD=1
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

for arg in "$@"; do
    case "$arg" in
        --no-launchd) WITH_LAUNCHD=0 ;;
        -h|--help)
            echo "usage: ./install.sh [--no-launchd]"
            echo "  --no-launchd  只安装 CLI 与 codex skill/指令，不注册 6 小时定时消化任务"
            exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# 1. venv + CLI
step "安装 Python 包到 $REPO_DIR/.venv"
if [[ ! -x "$REPO_DIR/.venv/bin/supermemory" ]]; then
    "$PYTHON" -m venv "$REPO_DIR/.venv"
    "$REPO_DIR/.venv/bin/pip" install -q -e "$REPO_DIR"
else
    "$REPO_DIR/.venv/bin/pip" install -q -e "$REPO_DIR"
fi
SM="$REPO_DIR/.venv/bin/supermemory"
"$SM" --help >/dev/null

# 2. codex skill（渲染绝对路径）
step "安装 codex skill 到 $CODEX_HOME/skills/super-memory/"
mkdir -p "$CODEX_HOME/skills/super-memory"
sed "s|@SUPERMEMORY_CLI@|$SM|g" "$REPO_DIR/codex/SKILL.md" > "$CODEX_HOME/skills/super-memory/SKILL.md"

# 3. AGENTS.md 全局指令（幂等：先移除旧块再追加）
step "写入 $CODEX_HOME/AGENTS.md 记忆协议块"
SNIPPET="$(sed "s|@SUPERMEMORY_CLI@|$SM|g" "$REPO_DIR/codex/AGENTS.snippet.md")"
AGENTS="$CODEX_HOME/AGENTS.md"
touch "$AGENTS"
if grep -q '<!-- super-memory:start -->' "$AGENTS"; then
    awk '/<!-- super-memory:start -->/{skip=1} /<!-- super-memory:end -->/{skip=0; next} !skip' "$AGENTS" > "$AGENTS.tmp"
    mv "$AGENTS.tmp" "$AGENTS"
fi
printf '\n%s\n' "$SNIPPET" >> "$AGENTS"

# 4. codex 沙箱放行记忆目录（幂等；避免记忆写入触发 auto_review 审批 503。失败不阻断安装）
step "配置 $CODEX_HOME/config.toml：沙箱直接可写 $HOME/.super-memory"
if ! "$REPO_DIR/.venv/bin/python" "$REPO_DIR/scripts/codex_config.py" install \
        --codex-home "$CODEX_HOME" --memory-dir "$HOME/.super-memory"; then
    echo "警告: config.toml 自动配置失败，请按上面提示手动加入 writable_roots" >&2
fi

# 5. launchd 定时消化（仅 macOS）
if [[ "$WITH_LAUNCHD" -eq 1 ]]; then
    if [[ "$(uname)" != "Darwin" ]]; then
        step "非 macOS，跳过 launchd（可用 cron 代替：每 6 小时执行 $REPO_DIR/scripts/digest.sh）"
    else
        step "注册 launchd 定时消化（每 6 小时）"
        PLIST="$HOME/Library/LaunchAgents/com.supermemory.digest.plist"
        mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.super-memory"
        sed -e "s|@REPO_DIR@|$REPO_DIR|g" -e "s|@HOME@|$HOME|g" \
            "$REPO_DIR/scripts/com.supermemory.digest.plist" > "$PLIST"
        chmod +x "$REPO_DIR/scripts/digest.sh"
        launchctl bootout "gui/$(id -u)/com.supermemory.digest" 2>/dev/null || true
        launchctl bootstrap "gui/$(id -u)" "$PLIST"
    fi
fi

step "安装完成"
"$SM" status || true
cat <<EOF

接下来：
  - 正常使用 codex 即可：新会话开始非平凡任务时会自动召回记忆并消化积压
  - 手动触发一次消化: $REPO_DIR/scripts/digest.sh
  - 口令触发: 在 codex 里说「消化积压」「沉淀记忆」「记住: ...」
  - 卸载: $REPO_DIR/uninstall.sh
EOF
