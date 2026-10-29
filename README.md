[English](README.en.md) | **简体中文**

# Super Memory -- AI agent 的跨 harness 长期记忆

**每次开新会话，你的 AI agent 就失忆一次；换个 harness，记忆直接归零；而平台内置的记忆，你又看不见、改不了、带不走。**

super-memory 给 AI agent 装上**跨会话、跨 harness 的长期记忆**：agent 自己把值得长期记住的知识（架构决策、项目约定、踩坑与解法、环境事实、你的偏好）蒸馏进一个本地纯 markdown 的 **LLM wiki**（Karpathy 提出的记忆组织模式），之后任何 harness 的新会话都自动召回。两个设计，对应两笔你能直接感受到的价值：

- **记忆跟着人走，不跟着 harness 走**——周一在 codex 敲定的方案，周三在 opencode 直接生效。背景不用重复交代，决策不重新讨论，坑不踩第二次；换 harness、混用 harness 都不再是代价
- **召回的是消化过的结论，不是原始碎片**——知识在写入时就被"编译"成 wiki（一个事实一个页面、去重合并、互链），agent 每次拿到的是成品，而不是一堆需要现场重读的原始会话碎片。而且记忆是一目录纯 markdown：agent 记住了什么、记错了什么，你随时看得见、随手改得动、用 git 管得住

目前支持 [Codex](https://openai.com/codex/)、[opencode](https://opencode.ai)、[Kimi Code](https://www.kimi.com/code/) 和 [Claude Code](https://code.claude.com/)；每个 harness 的适配相互独立（解析器 + skill 模板 + 消化 worker 各一套），接入新 harness 只需照此加一组文件，记忆天然继承。

蒸馏由 agent 在会话中顺带完成，不需要额外的 LLM API key；没有向量数据库，没有服务进程。


## 优势

**跨 harness 的记忆打通——记忆跟着人走，不跟着 harness 走。**

```
周一:  codex    里敲定架构方案      ─┐
周二:  opencode 里踩了一个网关的坑  ─┼─► 同一个 wiki
周三:  随便开哪个 harness           ─┘    ↑
       → 周一的方案、周二的坑都在上下文里 ──┘
```

- 不同harness的会话被蒸馏进**同一个 wiki**：在 codex 里沉淀的决策，在 opencode 的新会话里直接可用，反之亦然。换 harness、混用 harness 都不再意味着记忆清零
- 记忆是本地纯 markdown（`~/.super-memory/wiki/`），不绑定任何 harness 的私有格式——未来接入新 harness（或你自己换用新 agent），只要装上对应 skill 就能立刻继承全部历史记忆
- 各 harness 的消化互不干扰又汇入一体：各自独立的解析器和增量游标（codex 按字节偏移、opencode 按 session 更新时间戳、Kimi Code 按 wire.jsonl 字节偏移、Claude Code 按项目 JSONL 字节偏移），产出遵循同一套 wiki 原则（一个事实一个页面、页面互链、来源可回溯），不会因为来源不同而割裂

**不只跨 harness，也跨机器——记忆是可迁移、可版本管理的个人资产。**

- `~/.super-memory/wiki/` 就是一目录纯 markdown，可以复制或同步到另一台机器；装好 super-memory 后即可继续使用，不依赖原机器上的 harness 或会话数据
- 可以把 wiki 放进 Git 仓库，甚至用 GitHub 私有仓库同步和备份：每次记忆变更都能 diff、review、回溯历史或回滚，记忆不再锁死在某台机器、某个产品里

**记忆的载体是 Karpathy 式的 LLM wiki——写入时"编译"，而非检索时拼凑。**

主流记忆方案大体三类，super-memory 选了第三条路：

| 方案 | 做法 | 短板 |
|---|---|---|
| 平台内置记忆（各 chat 产品的 memory 功能） | provider 黑盒托管 | 锁死在单个产品里：不可看、不可改、带不走，换产品即清零 |
| RAG / 向量库记忆（Mem0 等） | 原始文本切成碎片存 embedding，每次查询临时检索、现场拼凑 | 检索 ≠ 理解：碎片从未被消化成知识；矛盾事实越积越多；还多一个向量库依赖 |
| **LLM wiki（本项目）** | LLM 把原始会话**编译**成结构化 wiki 并持续维护 | 需要 agent 参与蒸馏——但这恰好复用 harness 订阅，零额外成本 |

- 模式出自 Karpathy 2026 年 4 月提出的 LLM Wiki（[作为 agent 记忆的分析](https://aaif.io/blog/karpathys-llm-wiki-as-agent-memory)）：原始会话是"源代码"，wiki 是"编译产物"。知识**只消化一次**，之后每次用的是成品，而不是让 LLM 每次重读原料
- **去重与合并发生在写入时**：一个事实只住一个页面，过时的事实由 `revise` 修正——而不是往向量库里再塞一条和旧切片互相矛盾的新切片
- `index.md` 按上下文窗口大小设计，agent 一眼看到全部记忆目录；检索只是"翻到对应页面"，理解早在写入时就已完成
- 这也是跨 harness 打通的地基：wiki 是纯 markdown 的中立格式，天然不属于任何一家 harness

**蒸馏零额外成本。**

- 「判断什么值得记」由 agent 自己在会话中完成，沿用你已付费的 harness 订阅，不需要额外申请和保管 LLM API key
- 三种自动触发（会话开始召回、口令触发、launchd 定时消化），正常使用 codex / opencode / Kimi Code / Claude Code 即可，无需任何手动操作

**确定性与可控性。**

- LLM 只做"判断"，不碰"存储"：`pending`/`apply` 是确定性代码，ops 经 schema 校验后才落盘；确认契约保证只有 agent 明确确认的 session 才推进游标，分批消化不丢数据、中断可续
- 每条事实带来源标签 `(session <id>, <date)`，可回溯到原始会话；记忆可 diff、可 git 管理、可用 Obsidian 打开、可手动编辑
- 零依赖（Python ≥ 3.11 标准库）、无向量数据库、无 Web UI——整个系统就是几个脚本加一目录 markdown，出问题时每一环都可以直接检查和修复

## 工作原理

```
   三种触发（全部自动）                                  
   ─ 会话开始（AGENTS.md / CLAUDE.md 全局指令）
   ─ 口令触发（super-memory skill）                      
   ─ 定时消化（launchd，每 6 小时）                      
                 │                                       
                 ▼                                       
   supermemory pending --json ──► agent 阅读浓缩转录     
                                 按 wiki 原则产出 ops    
                 │                                       
                 ▼                                       
   supermemory apply ──► ~/.super-memory/wiki/           
   确定性落盘 + 推进游标      pages/ + index.md + log.md 
                 │                                       
                 ▼                                       
   新任务开始: supermemory inject "关键词"               
   相关记忆进入 agent 上下文                               
```

- **蒸馏由 agent 完成**：LLM 只做"判断"，不碰"存储"；`apply` 校验 ops schema 后落盘
- **确认契约**：只有被 agent 明确列入结果的 session 才推进游标，分批消化不丢数据、中断可续
- **增量幂等**：codex 按字节偏移增量读取，opencode 按 session 更新时间戳、Kimi Code 按 wire.jsonl 字节偏移、Claude Code 按项目 JSONL 字节偏移增量读取；重复运行零重复工作，append 自动去重
- **零依赖**：Python ≥ 3.11 标准库实现，无第三方包

## 安装

```bash
git clone https://github.com/chaocai2001/super-memory.git
cd super-memory
./install.sh                        # 缺省对本机检测到的 harness 全部安装
./install.sh --harness codex        # 只装 codex
./install.sh --harness opencode     # 只装 opencode（可重复传 --harness）
./install.sh --harness=kimi         # 只装 Kimi Code
./install.sh --harness=claude       # 只装 Claude Code
```

### 交给你的agent安装

也可以把下面的提示词直接发给支持 shell 的 personal agent，由它完成安装，并引导首次记忆蒸馏和定时任务设置：

```text
请安装 super-memory：https://github.com/chaocai2001/super-memory

1. 阅读 README.md 和 install.sh，检查 Python >= 3.11，将仓库克隆到合适位置；如果目录已存在，不要删除或覆盖，先询问我。
2. 识别当前使用的 harness，只安装当前 harness（codex / opencode / kimi / claude）。修改全局配置或注册定时任务前，说明变更范围并征得我同意。
3. 运行对应的 ./install.sh --harness=<harness>，不要加 --no-launchd。macOS 上确认 com.supermemory.digest 已注册并每 6 小时运行；Linux 上与我确认后用 cron 设置定时执行 scripts/digest.sh。
4. 安装后运行 .venv/bin/supermemory status 验证 CLI；macOS 上再运行 launchctl print gui/$(id -u)/com.supermemory.digest 验证定时任务。
5. 询问我是否立即进行首次记忆蒸馏；经我确认后运行 scripts/digest.sh --max-sessions 500，并检查 ~/.super-memory/digest.log。历史会话较少时可以调低上限。
6. 最后汇报安装位置、首次蒸馏结果、定时任务状态、使用方法和卸载方法。不要执行 uninstall.sh --purge。
```

安装脚本会依次完成：

1. 创建 `.venv` 并安装 `supermemory` CLI
2. 按 harness 安装 skill（codex → `~/.codex/skills/super-memory/`；opencode → `~/.config/opencode/skills/super-memory/`；Kimi Code → `${KIMI_CODE_HOME:-~/.kimi-code}/skills/super-memory/`；Claude Code → `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/super-memory/`；触发词：记忆 / 消化积压 / 沉淀记忆 / remember / recall）
3. 向对应全局指令文件追加记忆协议块（codex `~/.codex/AGENTS.md`；opencode `~/.config/opencode/AGENTS.md`；Kimi Code `${KIMI_CODE_HOME:-~/.kimi-code}/AGENTS.md`；Claude Code `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md`；幂等，带标记注释，可安全重装）
4. 【仅 codex】把 `~/.super-memory` 合并进 `~/.codex/config.toml` 的 `[sandbox_workspace_write].writable_roots`（幂等；让 codex 沙箱直接可写记忆目录，记忆更新不触发审批，规避 auto_review 审批服务 503）
5. 注册 launchd 定时任务 `com.supermemory.digest`（每 6 小时消化一次；`./install.sh --no-launchd` 可跳过）

要求：macOS（launchd 定时任务）；Linux 下 skill 与协议照常工作，定时消化可自行用 cron 跑 `scripts/digest.sh`。

## 使用

安装后**正常使用 codex / opencode / Kimi Code / Claude Code 即可**，无需手动操作。也可以主动驱动：

| 你在 agent 里说 | agent 做 |
|---|---|
| 「之前我们讨论的 MCP 方案是什么」 | `inject` 召回相关记忆页 |
| 「记住：这个项目统一用 pnpm」 | 写入 wiki 对应页面 |
| 「消化积压 / 沉淀记忆」 | 跑一轮 pending → apply |

终端直接查看记忆：

```bash
.venv/bin/supermemory status            # wiki 页数、消化进度
.venv/bin/supermemory search "MCP" "网关"      # 关键词检索，可传多个改写查询（英文分词+词干 + 中文 bigram/unigram）
.venv/bin/supermemory inject "SaaS" "订阅制"   # agent 实际会收到的记忆块
cat ~/.super-memory/wiki/index.md       # 浏览全部记忆页（markdown，可直接用 Obsidian 打开）
```

## CLI 参考

```bash
supermemory [--wiki-dir DIR] [--state-dir DIR] <command>
```

| 命令 | 说明 |
|---|---|
| `pending [--json] [--limit N] [--source S]...` | 列出有待消化的会话；`--json` 输出 checkpoint 供 `apply` 使用。`--source codex\|opencode\|kimi\|claude` 可重复，缺省自动探测本机已有的 harness；`--sessions-dir` / `--storage-dir` / `--db-path` / `--kimi-home` / `--claude-home` 可覆盖默认数据位置（opencode 优先读 sqlite db，无 db 时回落旧版 JSON 目录；Kimi Code 默认读 `${KIMI_CODE_HOME:-~/.kimi-code}`；Claude Code 默认读 `${CLAUDE_CONFIG_DIR:-~/.claude}`） |
| `apply --ops FILE --checkpoint FILE` | 校验并落盘 ops JSON，按确认契约推进游标 |
| `inject <query>... [--max-chars N]` | 输出可注入会话的相关记忆块（默认 4000 字符）；query 可传多个改写（中英/同义词）提高召回 |
| `search <query>... [-n N]` | 关键词检索（英文分词+词干、中文 bigram+unigram）；query 可传多个 |
| `status` | wiki 规模与消化进度 |
| `ingest [--dry-run] [--reprocess] [--source S]...` | 备选：调 OpenAI 兼容 API 的无人值守批量蒸馏（LLM 配置：`SUPER_MEMORY_BASE_URL/API_KEY/MODEL` 环境变量优先，缺省回落到 codex、opencode 或 Kimi Code 的 provider 配置）。Kimi Code 回落只读取带 API key 的 provider；OAuth 登录请使用 Skill 或 `kimi -p` 主路径，无需额外 API key。Claude Code 的 Anthropic 兼容配置不作为此 API 路径的回落来源 |

agent 产出的 ops schema 与 wiki 原则详见各 harness 的 skill 模板（`codex/SKILL.md` / `opencode/SKILL.md` / `kimi/SKILL.md` / `claude/SKILL.md`）。

## 定时消化管理

```bash
scripts/digest.sh                                        # 手动触发一次（自动选择 harness worker）
scripts/digest.sh --max-sessions 200                     # 本次最多消化 200 个会话
launchctl kickstart gui/$(id -u)/com.supermemory.digest  # 立即触发
launchctl print gui/$(id -u)/com.supermemory.digest      # 查看状态
```

- `digest.sh` 是调度器：无积压直接退出（零 token 消耗）；有积压时按 codex（`codex exec --ephemeral`，不产生新会话日志）→ opencode（`opencode run`，按固定标题前缀跳过消化会话）→ Kimi Code（`kimi -p`，按固定 prompt 前缀跳过消化会话）→ Claude Code（`claude -p --no-session-persistence`，不保存 worker 会话）的顺序选择 worker
- 间隔：plist 的 `StartInterval`（默认 21600 秒 = 6 小时）
- 每轮消化量：默认最多 50 个会话；手动执行时 `--max-sessions N` 仅对本次运行生效（覆盖本次的 `SM_DIGEST_MAX_SESSIONS`，不修改持久配置）；未传该命令行参数时，也可用 `SM_DIGEST_MAX_SESSIONS` 或 plist 的 `SM_DIGEST_BATCHES`（默认 10 批 × 5 会话）调整
- 日志：`~/.super-memory/digest.log`
- codex CLI 定位顺序：`CODEX_BIN` 环境变量 → PATH → `/Applications/ChatGPT.app/Contents/Resources/codex`；Kimi CLI 定位顺序：`KIMI_BIN` 环境变量 → PATH → `${KIMI_CODE_HOME:-~/.kimi-code}/bin/kimi`；Claude CLI 定位顺序：`CLAUDE_BIN` 环境变量 → PATH → `~/.local/bin/claude`

## 数据

```
~/.super-memory/
  wiki/pages/<slug>.md   # 实体/主题页：front-matter(标题/摘要/来源) + 分节正文 + [[互链]]
  wiki/index.md          # 全局索引，由 front-matter 自动重建
  wiki/log.md            # 会话时间线
  state.json             # 增量游标（codex/Kimi Code/Claude Code=字节偏移，opencode=session 更新时间戳；删除后全量重扫）
  digest.log             # 定时任务日志
```

所有记忆都是纯 markdown——可以直接编辑、git 管理、或用 Obsidian 打开。wiki 原则：一个事实只住一个页面；页面互链；只记长期知识；每条事实带来源标签 `(session <id>, <date>)` 可回溯。

## 卸载

```bash
./uninstall.sh                        # 移除 launchd 任务、各 harness 的 skill/协议块与 codex 沙箱放行（保留记忆数据）
./uninstall.sh --harness opencode     # 只移除 opencode 集成
./uninstall.sh --harness=kimi         # 只移除 Kimi Code 集成
./uninstall.sh --harness=claude       # 只移除 Claude Code 集成
./uninstall.sh --purge                # 连同 ~/.super-memory 记忆数据与 .venv 一起删除
```

## 故障排查

| 现象 | 处理 |
|---|---|
| 更新记忆时报「权限审批服务持续返回 503」（codex） | 审批走了 `approvals_reviewer = "auto_review"` 但模型网关没有 codex-auto-review 通道。先重跑 `./install.sh`（自动把 `~/.super-memory` 并入 `writable_roots`，记忆写入即不再触发审批）；仍触发审批时在 `~/.codex/config.toml` 顶层设 `approvals_reviewer = "user"` 并完全重启 codex。重启后仍被强制 auto_review 说明被组织托管策略覆盖，需管理员调整 |
| agent 没有自动召回 | 对它说「请按 super-memory skill 的协议工作」；确认对应全局指令文件（codex `~/.codex/AGENTS.md`、opencode `~/.config/opencode/AGENTS.md`、Kimi Code `${KIMI_CODE_HOME:-~/.kimi-code}/AGENTS.md`、Claude Code `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md`）含协议块；协议块陈旧时重跑 `./install.sh` 刷新 |
| opencode 会话没被消化 | 新版 opencode 的会话存在 `~/.local/share/opencode/opencode.db`（sqlite），旧版才是 `storage/` JSON 目录；老版本 super-memory 只读 JSON 目录会扫不到新会话，更新本仓库代码即可。其他排查：确认安装时包含了 opencode harness（`./install.sh --harness opencode`）；用 `supermemory pending --source opencode` 直接看积压 |
| Kimi Code 会话没被消化 | 确认安装时包含了 Kimi Code（`./install.sh --harness=kimi`）；用 `supermemory pending --source kimi` 查看积压。自定义数据目录时设置 `KIMI_CODE_HOME` 或传 `--kimi-home`；只解析主 Agent 的 `agents/main/wire.jsonl`，子 Agent 和消化 worker 会话会有意跳过 |
| Claude Code 会话没被消化 | 确认安装时包含了 Claude Code（`./install.sh --harness=claude`）；用 `supermemory pending --source claude` 查看积压。自定义数据目录时设置 `CLAUDE_CONFIG_DIR` 或传 `--claude-home`；只解析 `projects/*/*.jsonl` 中的主 Agent 内容，sidechain 与消化 worker 会话会有意跳过 |
| Claude Code 更新记忆时报 401「API Key invalid or expired」 | 通常是误调用了 `supermemory ingest`：它使用独立的 OpenAI 兼容 API 凭证，不复用 Claude Code 的 OAuth 或 `apiKeyHelper`。交互会话应只走 Skill 协议二的 `pending → ops → apply`，不要调用 `ingest`，无需额外 API key；若确需使用 `ingest`，则更新 `SUPER_MEMORY_BASE_URL/API_KEY/MODEL` |
| 定时任务没跑 | `launchctl print gui/$(id -u)/com.supermemory.digest` 看 last exit code；查 `~/.super-memory/digest.log` |
| 仓库移动了位置 | 重跑 `./install.sh`（幂等，会刷新所有绝对路径） |
| 想重建全部记忆 | 删除 `~/.super-memory/state.json`（重扫历史）或整个 `~/.super-memory/`（连 wiki 一起重来） |

## 仓库结构

```
src/super_memory/      # CLI 实现（标准库，零依赖）
  parser_codex.py      #   codex：jsonl → 浓缩转录（字节偏移游标）
  parser_opencode.py   #   opencode：opencode.db sqlite（旧版 JSON 目录回落）→ 浓缩转录（更新时间戳游标）
  parser_kimi.py       #   Kimi Code：主 Agent wire.jsonl → 浓缩转录（字节偏移游标）
  parser_claude.py     #   Claude Code：项目 jsonl → 浓缩转录（字节偏移游标）
  state.py             #   增量游标
  wiki.py              #   页面/index/log 落盘
  search.py            #   关键词检索与记忆块渲染
  distill.py           #   OpenAI 兼容 API 蒸馏（ingest 备选路径；LLM 配置 env → codex/opencode/Kimi Code 配置回落）
  cli.py               #   pending/apply/inject/search/status/ingest
codex/                 # codex harness 模板
  SKILL.md             #   codex skill（安装时渲染绝对路径）
  AGENTS.snippet.md    #   codex AGENTS.md 协议块模板
opencode/              # opencode harness 模板（与 codex 侧相互独立，各自演化）
  SKILL.md
  AGENTS.snippet.md
kimi/                  # Kimi Code harness 模板
  SKILL.md
  AGENTS.snippet.md
claude/                # Claude Code harness 模板
  SKILL.md
  CLAUDE.snippet.md
scripts/
  digest.sh            # 定时消化调度器（launchd 入口）
  digest_codex.sh      # codex 消化 worker
  digest_opencode.sh   # opencode 消化 worker
  digest_kimi.sh       # Kimi Code 消化 worker
  digest_claude.sh     # Claude Code 消化 worker
  codex_config.py      # config.toml 沙箱放行幂等合并（install/uninstall 共用）
  com.supermemory.digest.plist  # launchd 模板
install.sh / uninstall.sh   # --harness codex|opencode|kimi|claude|all
```

## 设计边界（有意不做）

- 无向量数据库/embedding——关键词检索（支持一次传多个改写查询，由 LLM 调用方做语义桥接）在页面量级内足够，`search.py` 留作扩展点
- harness 适配隔离——每个 harness 独立成 `parser_<harness>.py` + `<harness>/` 模板 + `digest_<harness>.sh`，互不引用；新增 harness 照此加文件即可
- 无 Web UI——wiki 就是 markdown

## License

MIT
