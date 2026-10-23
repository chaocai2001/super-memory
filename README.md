# Super Memory -- 基于LLM wiki的记忆系统

给 [Codex](https://openai.com/codex/) 和 [opencode](https://opencode.ai) 装上**跨会话的长期记忆**。

super-memory 读取 agent 的会话日志（codex 的 `~/.codex/sessions/**/*.jsonl`、opencode 的 `~/.local/share/opencode/opencode.db` sqlite 库，旧版 JSON 目录 `storage/` 作为回落），让 agent 自己把值得长期记住的知识（架构决策、项目约定、踩坑与解法、环境事实、你的偏好）蒸馏进一个纯 markdown 的 **LLM wiki**；开新任务时，相关记忆自动注入 agent 上下文。无需额外的 LLM API key——"判断什么值得记"由 agent 自己完成，CLI 只做确定性的解析、落盘与检索。

## 效果

```
周一:  你在 codex 里敲定了「MCP 必须 required=true，失败即终止」的方案
周三:  新会话里你问「帮我把这个 skill 接到网关上」
       → agent 自动召回周二的决策，直接按既定方案执行，不再重新讨论
```

## 优势

**跨 harness 的记忆打通——记忆跟着人走，不跟着工具走。**

```
周一:  codex    里敲定架构方案      ─┐
周二:  opencode 里踩了一个网关的坑  ─┼─► 同一个 wiki
周三:  随便开哪个 harness           ─┘    ↑
       → 周一的方案、周二的坑都在上下文里 ──┘
```

- codex 和 opencode 的会话被蒸馏进**同一个 wiki**：在 codex 里沉淀的决策，在 opencode 的新会话里直接可用，反之亦然。换工具、混用工具都不再意味着记忆清零
- 记忆是本地纯 markdown（`~/.super-memory/wiki/`），不绑定任何 harness 的私有格式——即使未来换第三个 agent，只要装上对应 skill 就能立刻继承全部历史记忆
- 两个 harness 的消化互不干扰又汇入一体：各自独立的解析器和增量游标（codex 按字节偏移、opencode 按 session 更新时间戳），产出遵循同一套 wiki 原则（一个事实一个页面、页面互链、来源可回溯），不会因为来源不同而割裂

**蒸馏零额外成本。**

- 「判断什么值得记」由 agent 自己在会话中完成，沿用你已付费的 harness 订阅，不需要额外申请和保管 LLM API key
- 三种自动触发（会话开始召回、口令触发、launchd 定时消化），正常使用 codex / opencode 即可，无需任何手动操作

**确定性与可控性。**

- LLM 只做"判断"，不碰"存储"：`pending`/`apply` 是确定性代码，ops 经 schema 校验后才落盘；确认契约保证只有 agent 明确确认的 session 才推进游标，分批消化不丢数据、中断可续
- 每条事实带来源标签 `(session <id>, <date)`，可回溯到原始会话；记忆可 diff、可 git 管理、可用 Obsidian 打开、可手动编辑
- 零依赖（Python ≥ 3.11 标准库）、无向量数据库、无 Web UI——整个系统就是几个脚本加一目录 markdown，出问题时每一环都可以直接检查和修复

## 工作原理

```
   三种触发（全部自动）                                  
   ─ 会话开始（AGENTS.md 全局指令）                      
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
- **增量幂等**：codex 按字节偏移增量读取，opencode 按 session 更新时间戳增量读取；重复运行零重复工作，append 自动去重
- **零依赖**：Python ≥ 3.11 标准库实现，无第三方包

## 安装

```bash
git clone https://github.com/chaocai2001/super-memory.git
cd super-memory
./install.sh                        # 缺省对本机检测到的 harness 全部安装
./install.sh --harness codex        # 只装 codex
./install.sh --harness opencode     # 只装 opencode（可重复传 --harness）
```

安装脚本会依次完成：

1. 创建 `.venv` 并安装 `supermemory` CLI
2. 按 harness 安装 skill（codex → `~/.codex/skills/super-memory/`；opencode → `~/.config/opencode/skills/super-memory/`；触发词：记忆 / 消化积压 / 沉淀记忆 / remember / recall）
3. 向对应 AGENTS.md（codex `~/.codex/AGENTS.md`；opencode `~/.config/opencode/AGENTS.md`）追加记忆协议块（幂等，带标记注释，可安全重装）
4. 【仅 codex】把 `~/.super-memory` 合并进 `~/.codex/config.toml` 的 `[sandbox_workspace_write].writable_roots`（幂等；让 codex 沙箱直接可写记忆目录，记忆更新不触发审批，规避 auto_review 审批服务 503）
5. 注册 launchd 定时任务 `com.supermemory.digest`（每 6 小时消化一次；`./install.sh --no-launchd` 可跳过）

要求：macOS（launchd 定时任务）；Linux 下 skill 与协议照常工作，定时消化可自行用 cron 跑 `scripts/digest.sh`。

## 使用

安装后**正常使用 codex / opencode 即可**，无需手动操作。也可以主动驱动：

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
| `pending [--json] [--limit N] [--source S]...` | 列出有待消化的会话；`--json` 输出 checkpoint 供 `apply` 使用。`--source codex|opencode` 可重复，缺省自动探测本机已有的 harness；`--sessions-dir` / `--storage-dir` / `--db-path` 可覆盖默认数据位置（opencode 优先读 sqlite db，无 db 时回落旧版 JSON 目录） |
| `apply --ops FILE --checkpoint FILE` | 校验并落盘 ops JSON，按确认契约推进游标 |
| `inject <query>... [--max-chars N]` | 输出可注入会话的相关记忆块（默认 4000 字符）；query 可传多个改写（中英/同义词）提高召回 |
| `search <query>... [-n N]` | 关键词检索（英文分词+词干、中文 bigram+unigram）；query 可传多个 |
| `status` | wiki 规模与消化进度 |
| `ingest [--dry-run] [--reprocess] [--source S]...` | 备选：调 OpenAI 兼容 API 的无人值守批量蒸馏（LLM 配置：`SUPER_MEMORY_BASE_URL/API_KEY/MODEL` 环境变量优先，缺省回落到 codex `~/.codex/config.toml` 或 opencode `~/.config/opencode/opencode.json[c]` 的 provider 配置） |

agent 产出的 ops schema 与 wiki 原则详见各 harness 的 skill 模板（`codex/SKILL.md` / `opencode/SKILL.md`）。

## 定时消化管理

```bash
scripts/digest.sh                                        # 手动触发一次（自动选择 harness worker）
launchctl kickstart gui/$(id -u)/com.supermemory.digest  # 立即触发
launchctl print gui/$(id -u)/com.supermemory.digest      # 查看状态
```

- `digest.sh` 是调度器：无积压直接退出（零 token 消耗）；有积压时优先用 codex worker（`codex exec --ephemeral`，不产生新会话日志），找不到 codex 时回落 opencode worker（`opencode run`，消化会话带固定标题前缀，解析时自动跳过）
- 间隔：plist 的 `StartInterval`（默认 21600 秒 = 6 小时）
- 每轮消化量：plist 的 `SM_DIGEST_BATCHES`（默认 3 批 × 5 会话）
- 日志：`~/.super-memory/digest.log`
- codex CLI 定位顺序：`CODEX_BIN` 环境变量 → PATH → `/Applications/ChatGPT.app/Contents/Resources/codex`

## 数据

```
~/.super-memory/
  wiki/pages/<slug>.md   # 实体/主题页：front-matter(标题/摘要/来源) + 分节正文 + [[互链]]
  wiki/index.md          # 全局索引，由 front-matter 自动重建
  wiki/log.md            # 会话时间线
  state.json             # 增量游标（codex=字节偏移，opencode=session 更新时间戳；删除后全量重扫）
  digest.log             # 定时任务日志
```

所有记忆都是纯 markdown——可以直接编辑、git 管理、或用 Obsidian 打开。wiki 原则：一个事实只住一个页面；页面互链；只记长期知识；每条事实带来源标签 `(session <id>, <date>)` 可回溯。

## 卸载

```bash
./uninstall.sh                        # 移除 launchd 任务、各 harness 的 skill/协议块与 codex 沙箱放行（保留记忆数据）
./uninstall.sh --harness opencode     # 只移除 opencode 集成
./uninstall.sh --purge                # 连同 ~/.super-memory 记忆数据与 .venv 一起删除
```

## 故障排查

| 现象 | 处理 |
|---|---|
| 更新记忆时报「权限审批服务持续返回 503」（codex） | 审批走了 `approvals_reviewer = "auto_review"` 但模型网关没有 codex-auto-review 通道。先重跑 `./install.sh`（自动把 `~/.super-memory` 并入 `writable_roots`，记忆写入即不再触发审批）；仍触发审批时在 `~/.codex/config.toml` 顶层设 `approvals_reviewer = "user"` 并完全重启 codex。重启后仍被强制 auto_review 说明被组织托管策略覆盖，需管理员调整 |
| agent 没有自动召回 | 对它说「请按 super-memory skill 的协议工作」；确认对应 AGENTS.md（codex `~/.codex/`、opencode `~/.config/opencode/`）含协议块；协议块陈旧时重跑 `./install.sh` 刷新 |
| opencode 会话没被消化 | 新版 opencode 的会话存在 `~/.local/share/opencode/opencode.db`（sqlite），旧版才是 `storage/` JSON 目录；老版本 super-memory 只读 JSON 目录会扫不到新会话，更新本仓库代码即可。其他排查：确认安装时包含了 opencode harness（`./install.sh --harness opencode`）；用 `supermemory pending --source opencode` 直接看积压 |
| 定时任务没跑 | `launchctl print gui/$(id -u)/com.supermemory.digest` 看 last exit code；查 `~/.super-memory/digest.log` |
| 仓库移动了位置 | 重跑 `./install.sh`（幂等，会刷新所有绝对路径） |
| 想重建全部记忆 | 删除 `~/.super-memory/state.json`（重扫历史）或整个 `~/.super-memory/`（连 wiki 一起重来） |

## 仓库结构

```
src/super_memory/      # CLI 实现（标准库，零依赖）
  parser_codex.py      #   codex：jsonl → 浓缩转录（字节偏移游标）
  parser_opencode.py   #   opencode：opencode.db sqlite（旧版 JSON 目录回落）→ 浓缩转录（更新时间戳游标）
  state.py             #   增量游标
  wiki.py              #   页面/index/log 落盘
  search.py            #   关键词检索与记忆块渲染
  distill.py           #   OpenAI 兼容 API 蒸馏（ingest 备选路径；LLM 配置 env → codex/opencode 配置回落）
  cli.py               #   pending/apply/inject/search/status/ingest
codex/                 # codex harness 模板
  SKILL.md             #   codex skill（安装时渲染绝对路径）
  AGENTS.snippet.md    #   codex AGENTS.md 协议块模板
opencode/              # opencode harness 模板（与 codex 侧相互独立，各自演化）
  SKILL.md
  AGENTS.snippet.md
scripts/
  digest.sh            # 定时消化调度器（launchd 入口）
  digest_codex.sh      # codex 消化 worker
  digest_opencode.sh   # opencode 消化 worker
  codex_config.py      # config.toml 沙箱放行幂等合并（install/uninstall 共用）
  com.supermemory.digest.plist  # launchd 模板
install.sh / uninstall.sh   # --harness codex|opencode|all
```

## 设计边界（有意不做）

- 无向量数据库/embedding——关键词检索（支持一次传多个改写查询，由 LLM 调用方做语义桥接）在页面量级内足够，`search.py` 留作扩展点
- harness 适配隔离——每个 harness 独立成 `parser_<harness>.py` + `<harness>/` 模板 + `digest_<harness>.sh`，互不引用；新增 harness 照此加文件即可
- 无 Web UI——wiki 就是 markdown

## License

MIT
