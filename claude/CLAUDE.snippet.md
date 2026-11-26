<!-- super-memory:start -->
## Memory protocol (super-memory)

You have a persistent cross-session memory wiki at `~/.super-memory/wiki/`, maintained via the `super-memory` skill (`@CLAUDE_CONFIG_DIR@/skills/super-memory/SKILL.md`).

At the start of every non-trivial task, before doing the work:

Recall — run `@SUPERMEMORY_CLI@ inject "<task keywords>" "<synonym/English variant>"` (search is keyword-based: pass 2–3 paraphrases, e.g. Chinese + English + synonyms, to bridge wording gaps) and treat its output as established context (user preferences, past decisions, project conventions). Do not re-ask the user for things already in memory.

Digestion is owned by the background scheduler after sessions become idle. Do not run `pending`/`apply` at task start or during conversational idle time; run it only when the user explicitly asks to digest the backlog. Explicit requests to remember or correct a fact should update the wiki immediately.

Keep recall lightweight: never let it block or dominate the user's actual task, and skip it entirely for trivial one-line requests.
<!-- super-memory:end -->
