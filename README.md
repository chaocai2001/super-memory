# super-memory

给 [Codex](https://openai.com/codex/) 装上**跨会话的长期记忆**。

super-memory 读取 codex 的会话日志（`~/.codex/sessions/**/*.jsonl`），让 codex agent 自己把值得长期记住的知识（架构决策、项目约定、踩坑与解法、环境事实、你的偏好）蒸馏进一个纯 markdown 的 **LLM wiki**；开新任务时，相关记忆自动注入 agent 上下文。无需额外的 LLM API key——"判断什么值得记"由 codex 自己完成，CLI 只做确定性的解析、落盘与检索。

## 效果

```
周一:  你在 codex 里敲定了「MCP 必须 required=true，失败即终止」的方案
周三:  新会话里你问「帮我把这个 skill 接到网关上」
       → codex 自动召回周二的决策，直接按既定方案执行，不再重新讨论
```

## 工作原理

```
   三种触发（全部自动）                                  
   ─ 会话开始（AGENTS.md 全局指令）                      
   ─ 口令触发（super-memory skill）                      
   ─ 定时消化（launchd，每 6 小时）                      
                 │                                       
                 ▼                                       
   supermemory pending --json ──► codex 阅读浓缩转录     
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
- **增量幂等**：按字节偏移增量读取日志，重复运行零重复工作，append 自动去重
- **零依赖**：Python ≥ 3.11 标准库实现，无第三方包

## 安装

```bash
git clone https://github.com/chaocai2001/super-memory.git
cd super-memory
./install.sh
```

安装脚本会依次完成：

1. 创建 `.venv` 并安装 `supermemory` CLI
2. 安装 codex skill 到 `~/.codex/skills/super-memory/`（触发词：记忆 / 消化积压 / 沉淀记忆 / remember / recall）
3. 向 `~/.codex/AGENTS.md` 追加记忆协议块（幂等，带标记注释，可安全重装）
4. 注册 launchd 定时任务 `com.supermemory.digest`（每 6 小时消化一次；`./install.sh --no-launchd` 可跳过）

要求：macOS（launchd 定时任务）；Linux 下 skill 与协议照常工作，定时消化可自行用 cron 跑 `scripts/digest.sh`。

## 使用

安装后**正常使用 codex 即可**，无需手动操作。也可以主动驱动：

| 你在 codex 里说 | codex 做 |
|---|---|
| 「之前我们讨论的 MCP 方案是什么」 | `inject` 召回相关记忆页 |
| 「记住：这个项目统一用 pnpm」 | 写入 wiki 对应页面 |
| 「消化积压 / 沉淀记忆」 | 跑一轮 pending → apply |

终端直接查看记忆：

```bash
.venv/bin/supermemory status            # wiki 页数、消化进度
.venv/bin/supermemory search "MCP"      # 关键词检索（英文分词 + 中文 bigram）
.venv/bin/supermemory inject "SaaS"     # agent 实际会收到的记忆块
cat ~/.super-memory/wiki/index.md       # 浏览全部记忆页（markdown，可直接用 Obsidian 打开）
```

## CLI 参考

```bash
supermemory [--wiki-dir DIR] [--state-dir DIR] <command>
```

| 命令 | 说明 |
|---|---|
| `pending [--json] [--limit N]` | 列出有待消化字节的会话；`--json` 输出 checkpoint 供 `apply` 使用 |
| `apply --ops FILE --checkpoint FILE` | 校验并落盘 ops JSON，按确认契约推进游标 |
| `inject <query> [--max-chars N]` | 输出可注入会话的相关记忆块（默认 4000 字符） |
| `search <query> [-n N]` | 关键词检索 |
| `status` | wiki 规模与消化进度 |
| `ingest [--dry-run] [--reprocess]` | 备选：调 OpenAI 兼容 API 的无人值守批量蒸馏（需 `SUPER_MEMORY_BASE_URL/API_KEY/MODEL`） |

agent 产出的 ops schema 与 wiki 原则详见 `codex/SKILL.md`。

## 定时消化管理

```bash
scripts/digest.sh                                        # 手动触发一次
launchctl kickstart gui/$(id -u)/com.supermemory.digest  # 立即触发
launchctl print gui/$(id -u)/com.supermemory.digest      # 查看状态
```

- 间隔：plist 的 `StartInterval`（默认 21600 秒 = 6 小时）
- 每轮消化量：plist 的 `SM_DIGEST_BATCHES`（默认 3 批 × 5 会话）
- 无积压时不启动 codex 会话（零 token 消耗）；消化用 `codex exec --ephemeral`，不产生新会话日志
- 日志：`~/.super-memory/digest.log`
- codex CLI 定位顺序：`CODEX_BIN` 环境变量 → PATH → `/Applications/ChatGPT.app/Contents/Resources/codex`

## 数据

```
~/.super-memory/
  wiki/pages/<slug>.md   # 实体/主题页：front-matter(标题/摘要/来源) + 分节正文 + [[互链]]
  wiki/index.md          # 全局索引，由 front-matter 自动重建
  wiki/log.md            # 会话时间线
  state.json             # 日志字节偏移游标（删除后全量重扫）
  digest.log             # 定时任务日志
```

所有记忆都是纯 markdown——可以直接编辑、git 管理、或用 Obsidian 打开。wiki 原则：一个事实只住一个页面；页面互链；只记长期知识；每条事实带来源标签 `(session <id>, <date>)` 可回溯。

## 卸载

```bash
./uninstall.sh           # 移除 launchd 任务、skill、AGENTS.md 协议块（保留记忆数据）
./uninstall.sh --purge   # 连同 ~/.super-memory 记忆数据与 .venv 一起删除
```

## 故障排查

| 现象 | 处理 |
|---|---|
| codex 没有自动召回 | 对它说「请按 super-memory skill 的协议工作」；确认 `~/.codex/AGENTS.md` 含协议块 |
| 定时任务没跑 | `launchctl print gui/$(id -u)/com.supermemory.digest` 看 last exit code；查 `~/.super-memory/digest.log` |
| 仓库移动了位置 | 重跑 `./install.sh`（幂等，会刷新所有绝对路径） |
| 想重建全部记忆 | 删除 `~/.super-memory/state.json`（重扫历史）或整个 `~/.super-memory/`（连 wiki 一起重来） |

## 仓库结构

```
src/super_memory/      # CLI 实现（标准库，零依赖）
  parser.py            #   jsonl → 浓缩转录
  state.py             #   增量游标
  wiki.py              #   页面/index/log 落盘
  search.py            #   关键词检索与记忆块渲染
  distill.py           #   OpenAI 兼容 API 蒸馏（ingest 备选路径）
  cli.py               #   pending/apply/inject/search/status/ingest
codex/
  SKILL.md             # codex skill 模板（安装时渲染绝对路径）
  AGENTS.snippet.md    # AGENTS.md 协议块模板
scripts/
  digest.sh            # 定时消化入口
  com.supermemory.digest.plist  # launchd 模板
install.sh / uninstall.sh
```

## 设计边界（有意不做）

- 无向量数据库/embedding——关键词检索在页面量级内足够，`search.py` 留作扩展点
- 只适配 codex 日志格式——其它 agent 需在 `parser.py` 加适配器
- 无 Web UI——wiki 就是 markdown

## License

MIT
