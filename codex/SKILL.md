---
name: super-memory
description: Persistent long-term memory for the agent, stored as an LLM-curated markdown wiki built from codex session logs. Use at the START of every non-trivial task to recall relevant memory (supermemory inject), and to digest past sessions into the wiki (pending → apply). Triggers on "记忆", "remember", "recall", "之前我们", "上次", "memory", "消化积压", "沉淀记忆", or whenever prior context from earlier sessions would help.
---

# Super-Memory：持久记忆协议

你拥有一个跨会话的持久记忆 wiki，位于 `~/.super-memory/wiki/`。它由历史会话日志蒸馏而来，靠你（agent）持续维护。所有确定性操作（解析日志、落盘 wiki、检索）都由 CLI 完成，你只做两件事：**召回** 和 **蒸馏**。

CLI 绝对路径（不要依赖 PATH）：

```
SM=@SUPERMEMORY_CLI@
```

## 协议一：任务开始时召回记忆（必做）

每个非平凡任务开始时，先用任务关键词召回相关记忆：

```bash
$SM inject "<任务关键词>" --max-chars 4000
```

- 输出是一段可直接使用的 markdown 记忆块，把它当作已知背景，不要向用户重复询问记忆里已有的偏好、决策和约定。
- 输出 "no relevant memory found" 属正常，继续任务即可，不要反复重试。
- 也可以用 `$SM search "<关键词>" -n 5` 浏览命中页面路径后，直接 Read 对应 `~/.super-memory/wiki/pages/*.md` 深读。

## 协议二：蒸馏历史会话（后台消化，必做）

在任务开始召回之后、或会话空闲时，检查并消化积压的历史会话，每批 5 条：

```bash
$SM pending --json --limit 5 > /tmp/sm-pending.json
```

- 若输出中 `sessions` 为空，说明没有积压，跳过本协议。
- 否则：阅读每条 session 的 `transcript`，按下方的 wiki 原则判断哪些知识值得长期记住，结合 JSON 里的 `index`（既有页面清单，事实要优先归入既有页面），写出 ops 文件 `/tmp/sm-ops.json`：

```json
{
  "sessions": [
    {
      "session_id": "<来自 pending 的完整 session_id>",
      "log_entry": "一句话总结这个会话做了什么",
      "ops": [
        {
          "action": "create | append | revise",
          "page": "kebab-case-slug",
          "title": "页面标题",
          "summary": "一句话索引摘要（create 必填）",
          "section": "页内小节标题",
          "content": "markdown 内容，bullet 优先，每条事实结尾带来源标签 (session <id前8位>, <日期>)",
          "links": ["其它页面slug"]
        }
      ]
    }
  ]
}
```

然后落盘并确认消化：

```bash
$SM apply --ops /tmp/sm-ops.json --checkpoint /tmp/sm-pending.json
```

**确认契约**：只有出现在 ops 文件 `sessions` 列表里的 session 才会被标记为已消化。某条会话没有值得记的内容时，也要列进去（`ops: []` + `log_entry`），否则它会一直留在积压里。没处理完的留到下一批，不要硬塞进一个批次。

## Wiki 原则（蒸馏时严格遵守）

- 一个事实只住一个页面；能 append/revise 既有页面就不新建。
- 只记长期有价值的知识：架构决策、项目约定、踩坑与解法、环境事实、用户偏好、反复出现的工作流、重要工具与资源。
- 不记一次性闲聊、临时调试过程、从仓库代码就能看出的东西。
- 内容用知识原本的语言书写（中文事实保持中文）。
- 页面间用 `[[wiki-link]]` 互链（填进 links 字段即可，CLI 负责落盘）。
- revise 用于纠正或合并过时事实，会替换整个小节。

## 其他

- 当前会话的日志会在下次会话时自动进入 pending 积压 —— 不需要在会话进行中蒸馏自己，协议二会自然覆盖。
- `$SM status` 查看 wiki 页面数与消化进度。
- 若配置了 `SUPER_MEMORY_BASE_URL/API_KEY/MODEL`，也可用 `$SM ingest` 走 API 批量蒸馏（等价于协议二的无人值守版）。
