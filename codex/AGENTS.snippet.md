<!-- super-memory:start -->
## Memory protocol (super-memory)

You have a persistent cross-session memory wiki at `~/.super-memory/wiki/`, maintained via the `super-memory` skill (`~/.codex/skills/super-memory/SKILL.md`).

At the start of every non-trivial task, before doing the work:

1. Recall — run `@SUPERMEMORY_CLI@ inject "<task keywords>"` and treat its output as established context (user preferences, past decisions, project conventions). Do not re-ask the user for things already in memory.
2. Digest — if time permits, process one batch of the memory backlog (`pending --json --limit 5` → write ops → `apply`), following the skill's wiki principles.

Keep memory maintenance in the background: never let it block or dominate the user's actual task, and skip it entirely for trivial one-line requests.
<!-- super-memory:end -->
