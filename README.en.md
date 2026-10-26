**English** | [简体中文](README.md)

# Super Memory -- Cross-harness long-term memory for AI agents

**Every new session, your AI agent forgets everything. Switch harnesses, and your memory resets to zero. And platform-built-in memory? You can't see it, edit it, or take it with you.**

super-memory gives AI agents **cross-session, cross-harness long-term memory**: the agent itself distills what's worth remembering (architecture decisions, project conventions, pitfalls and their fixes, environment facts, your preferences) into a local, plain-markdown **LLM wiki** (the memory organization pattern proposed by Karpathy), and any new session in any harness automatically recalls it. Two design choices, two benefits you can feel directly:

- **Memory follows you, not the harness** — a decision made in codex on Monday is live in opencode on Wednesday. No re-explaining context, no re-litigating decisions, no stepping into the same pit twice; switching or mixing harnesses is no longer a cost
- **What gets recalled is digested conclusions, not raw fragments** — knowledge is "compiled" into a wiki at write time (one fact per page, dedup and merge, cross-links), so the agent gets finished answers instead of a pile of raw session fragments it has to re-read on the spot. And the memory is just a directory of markdown: you can always see what the agent remembered, fix what it got wrong, and manage it with git

Currently supports [Codex](https://openai.com/codex/) and [opencode](https://opencode.ai); each harness adapter is self-contained (its own parser + skill template + digest worker). Adding a new harness is just another set of files — and all existing memory carries over.

Distillation happens inside the agent session as a side effect, so no extra LLM API key is needed; no vector database, no server process.


## Why super-memory

**Cross-harness memory — memory follows you, not the harness.**

```
Mon:  decisions made in codex       ─┐
Tue:  a gateway pitfall in opencode ─┼─► one single wiki
Wed:  open any harness              ─┘    ↑
       → Mon's plan and Tue's pitfall ────┘
       are already in context
```

- Sessions from different harnesses are distilled into **the same wiki**: what you work out in codex is directly usable in a new opencode session, and vice versa. Switching or mixing harnesses no longer means memory loss
- Memory is local plain markdown (`~/.super-memory/wiki/`), not locked into any harness's private format — when a new harness is supported (or you switch to a new agent), installing its skill instantly inherits your entire history
- Each harness digests independently yet converges into one: separate parsers and incremental cursors (codex by byte offset, opencode by session update timestamp), but the output follows one set of wiki principles (one fact one page, cross-linked pages, traceable sources), so knowledge never fragments by origin

**Not just cross-harness, but cross-machine — your memory is a portable, versionable personal asset.**

- `~/.super-memory/wiki/` is simply a directory of plain markdown: copy or sync it to another machine, install super-memory, and keep using it — no dependency on the original machine's harnesses or session data
- You can put the wiki in a Git repository, or even use a private GitHub repository to sync and back it up: every memory change can be diffed, reviewed, traced through history, or rolled back. Your memory is no longer locked to one machine or product

**The memory substrate is a Karpathy-style LLM wiki — "compiled" at write time, not assembled at retrieval time.**

Mainstream memory solutions fall into three camps; super-memory takes the third path:

| Approach | How it works | Weakness |
|---|---|---|
| Platform built-in memory (chat products' memory features) | Black-box hosted by the provider | Locked inside one product: invisible, uneditable, unportable — gone when you switch |
| RAG / vector-store memory (Mem0 etc.) | Raw text chunked into embeddings; every query retrieves and assembles fragments on the fly | Retrieval ≠ understanding: fragments are never digested into knowledge; contradictory facts pile up; plus a vector DB dependency |
| **LLM wiki (this project)** | The LLM **compiles** raw sessions into a structured wiki and maintains it over time | Requires an agent to do the distillation — but that reuses your harness subscription, at zero extra cost |

- The pattern comes from Karpathy's LLM Wiki (April 2026; see [an analysis of it as agent memory](https://aaif.io/blog/karpathys-llm-wiki-as-agent-memory)): raw sessions are the "source code", the wiki is the "compiled artifact". Knowledge is **digested once**; afterwards you use the finished product instead of making the LLM re-read the raw material every time
- **Dedup and merge happen at write time**: one fact lives on exactly one page, stale facts are fixed by `revise` — instead of pushing yet another contradicting chunk into a vector store
- `index.md` is sized to fit a context window, so the agent sees the whole memory table of contents at a glance; retrieval is just "turning to the right page" — understanding was already done at write time
- This is also the foundation of cross-harness memory: a wiki is a neutral plain-markdown format that belongs to no harness

**Distillation at zero extra cost.**

- "Judging what's worth remembering" is done by the agent inside its own session, riding on the harness subscription you already pay for — no extra LLM API key to apply for and guard
- Three automatic triggers (recall at session start, command-word trigger, scheduled launchd digestion) — just use codex / opencode normally, nothing manual

**Deterministic and controllable.**

- The LLM only "judges", never "stores": `pending`/`apply` are deterministic code; ops are schema-validated before hitting disk; the acknowledgment contract advances the cursor only for sessions the agent explicitly confirmed — batched digestion loses nothing and resumes after interruption
- Every fact carries a source tag `(session <id>, <date>)`, traceable back to the original session; memory can be diffed, git-managed, opened in Obsidian, edited by hand
- Zero dependencies (Python ≥ 3.11 standard library), no vector database, no Web UI — the whole system is a few scripts plus a directory of markdown; every link in the chain can be inspected and fixed directly

## How it works

```
   Three triggers (all automatic)
   ─ session start (AGENTS.md global instructions)
   ─ command words (super-memory skill)
   ─ scheduled digestion (launchd, every 6 hours)
                 │
                 ▼
   supermemory pending --json ──► agent reads condensed transcripts
                                  produces ops per wiki principles
                 │
                 ▼
   supermemory apply ──► ~/.super-memory/wiki/
   deterministic write + cursor    pages/ + index.md + log.md
                 │
                 ▼
   New task starts: supermemory inject "keywords"
   Relevant memory enters the agent's context
```

- **Distillation is done by the agent**: the LLM only "judges", never "stores"; `apply` writes to disk after validating the ops schema
- **Acknowledgment contract**: the cursor advances only for sessions the agent explicitly lists in its results — batched digestion loses nothing, interruption is resumable
- **Incremental and idempotent**: codex is read incrementally by byte offset, opencode by session update timestamp; reruns do zero duplicate work, appends auto-dedupe
- **Zero dependencies**: Python ≥ 3.11 standard library only, no third-party packages

## Installation

```bash
git clone https://github.com/chaocai2001/super-memory.git
cd super-memory
./install.sh                        # default: install for every harness detected on this machine
./install.sh --harness codex        # codex only
./install.sh --harness opencode     # opencode only (--harness is repeatable)
```

The install script performs, in order:

1. Create `.venv` and install the `supermemory` CLI
2. Install the skill per harness (codex → `~/.codex/skills/super-memory/`; opencode → `~/.config/opencode/skills/super-memory/`; trigger words: 记忆 / 消化积压 / 沉淀记忆 / remember / recall)
3. Append the memory protocol block to each AGENTS.md (codex `~/.codex/AGENTS.md`; opencode `~/.config/opencode/AGENTS.md`) — idempotent, marker-commented, safe to reinstall
4. **[codex only]** Merge `~/.super-memory` into `[sandbox_workspace_write].writable_roots` in `~/.codex/config.toml` (idempotent; lets the codex sandbox write the memory directory directly, so memory updates don't trigger approvals — works around auto_review approval-service 503s)
5. Register the launchd job `com.supermemory.digest` (digests every 6 hours; skip with `./install.sh --no-launchd`)

Requirements: macOS (for the launchd job); on Linux the skill and protocol work as usual — run `scripts/digest.sh` from cron for scheduled digestion.

## Usage

After installation, **just use codex / opencode normally** — nothing manual. You can also drive it actively:

| You say to the agent | The agent does |
|---|---|
| "之前我们讨论的 MCP 方案是什么" (what was the MCP approach we discussed) | `inject` recalls the relevant memory pages |
| "记住：这个项目统一用 pnpm" (remember: this project uses pnpm) | Writes it into the corresponding wiki page |
| "消化积压 / 沉淀记忆" (digest the backlog) | Runs a round of pending → apply |

Inspect memory directly from the terminal:

```bash
.venv/bin/supermemory status            # wiki page count, digestion progress
.venv/bin/supermemory search "MCP" "网关"      # keyword search; multiple rephrased queries supported (English tokenize+stem + Chinese bigram/unigram)
.venv/bin/supermemory inject "SaaS" "订阅制"   # the exact memory block the agent would receive
cat ~/.super-memory/wiki/index.md       # browse all memory pages (markdown; opens in Obsidian)
```

## CLI reference

```bash
supermemory [--wiki-dir DIR] [--state-dir DIR] <command>
```

| Command | Description |
|---|---|
| `pending [--json] [--limit N] [--source S]...` | List sessions pending digestion; `--json` emits a checkpoint for `apply`. `--source codex\|opencode` is repeatable, defaults to auto-detecting installed harnesses; `--sessions-dir` / `--storage-dir` / `--db-path` override default data locations (opencode prefers the sqlite db, falls back to the legacy JSON directory) |
| `apply --ops FILE --checkpoint FILE` | Validate and persist ops JSON, advance cursors per the acknowledgment contract |
| `inject <query>... [--max-chars N]` | Render the relevant-memory block for injection into a session (default 4000 chars); multiple query rephrasings (Chinese/English/synonyms) improve recall |
| `search <query>... [-n N]` | Keyword search (English tokenize+stem, Chinese bigram+unigram); multiple queries supported |
| `status` | Wiki size and digestion progress |
| `ingest [--dry-run] [--reprocess] [--source S]...` | Alternative: unattended batch distillation via an OpenAI-compatible API (LLM config: `SUPER_MEMORY_BASE_URL/API_KEY/MODEL` env vars first, falling back to codex `~/.codex/config.toml` or the provider config in opencode `~/.config/opencode/opencode.json[c]`) |

The ops schema the agent produces and the wiki principles are documented in each harness's skill template (`codex/SKILL.md` / `opencode/SKILL.md`).

## Managing scheduled digestion

```bash
scripts/digest.sh                                        # trigger once manually (auto-selects the harness worker)
launchctl kickstart gui/$(id -u)/com.supermemory.digest  # trigger immediately
launchctl print gui/$(id -u)/com.supermemory.digest      # check status
```

- `digest.sh` is the scheduler: it exits immediately when there is no backlog (zero token cost); with a backlog it prefers the codex worker (`codex exec --ephemeral`, which produces no new session logs), falling back to the opencode worker (`opencode run`; digestion sessions carry a fixed title prefix and are skipped during parsing)
- Interval: the plist's `StartInterval` (default 21600 seconds = 6 hours)
- Work per round: the plist's `SM_DIGEST_BATCHES` (default 3 batches × 5 sessions)
- Logs: `~/.super-memory/digest.log`
- codex CLI lookup order: `CODEX_BIN` env var → PATH → `/Applications/ChatGPT.app/Contents/Resources/codex`

## Data

```
~/.super-memory/
  wiki/pages/<slug>.md   # entity/topic pages: front-matter (title/summary/sources) + sectioned body + [[cross-links]]
  wiki/index.md          # global index, auto-rebuilt from front-matter
  wiki/log.md            # session timeline
  state.json             # incremental cursors (codex = byte offset, opencode = session update timestamp; delete to rescan everything)
  digest.log             # scheduled-job log
```

All memory is plain markdown — edit it directly, manage it with git, or open it in Obsidian. Wiki principles: one fact lives on exactly one page; pages cross-link; only long-term knowledge is recorded; every fact carries a source tag `(session <id>, <date>)` for traceability.

## Uninstall

```bash
./uninstall.sh                        # remove the launchd job, each harness's skill/protocol block, and the codex sandbox grant (memory data is kept)
./uninstall.sh --harness opencode     # remove only the opencode integration
./uninstall.sh --purge                # also delete the ~/.super-memory memory data and .venv
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Permission approval service keeps returning 503" when updating memory (codex) | Approvals went through `approvals_reviewer = "auto_review"` but the model gateway has no codex-auto-review channel. First re-run `./install.sh` (it merges `~/.super-memory` into `writable_roots`, after which memory writes no longer trigger approvals); if approvals still trigger, set `approvals_reviewer = "user"` at the top level of `~/.codex/config.toml` and fully restart codex. If auto_review is still forced after restart, an organization managed policy is overriding it — ask your admin |
| The agent doesn't recall automatically | Tell it "请按 super-memory skill 的协议工作" (work per the super-memory skill protocol); check that the corresponding AGENTS.md (codex `~/.codex/`, opencode `~/.config/opencode/`) contains the protocol block; re-run `./install.sh` to refresh a stale block |
| opencode sessions not being digested | Newer opencode stores sessions in `~/.local/share/opencode/opencode.db` (sqlite); only older versions use the `storage/` JSON directory. Old super-memory builds only read the JSON directory and miss new sessions — update this repo. Also: confirm the opencode harness was included at install time (`./install.sh --harness opencode`); inspect the backlog directly with `supermemory pending --source opencode` |
| The scheduled job didn't run | `launchctl print gui/$(id -u)/com.supermemory.digest` for the last exit code; check `~/.super-memory/digest.log` |
| The repo moved | Re-run `./install.sh` (idempotent; refreshes all absolute paths) |
| Want to rebuild all memory | Delete `~/.super-memory/state.json` (rescan history) or the whole `~/.super-memory/` (start over including the wiki) |

## Repository layout

```
src/super_memory/      # CLI implementation (standard library, zero dependencies)
  parser_codex.py      #   codex: jsonl → condensed transcript (byte-offset cursor)
  parser_opencode.py   #   opencode: opencode.db sqlite (legacy JSON directory fallback) → condensed transcript (update-timestamp cursor)
  state.py             #   incremental cursors
  wiki.py              #   page/index/log persistence
  search.py            #   keyword search and memory-block rendering
  distill.py           #   OpenAI-compatible API distillation (alternative ingest path; LLM config falls back env → codex/opencode config)
  cli.py               #   pending/apply/inject/search/status/ingest
codex/                 # codex harness templates
  SKILL.md             #   codex skill (absolute paths rendered at install time)
  AGENTS.snippet.md    #   codex AGENTS.md protocol-block template
opencode/              # opencode harness templates (independent from the codex side; they evolve separately)
  SKILL.md
  AGENTS.snippet.md
scripts/
  digest.sh            # scheduled-digestion dispatcher (launchd entry point)
  digest_codex.sh      # codex digestion worker
  digest_opencode.sh   # opencode digestion worker
  codex_config.py      # idempotent config.toml sandbox-grant merge (shared by install/uninstall)
  com.supermemory.digest.plist  # launchd template
install.sh / uninstall.sh   # --harness codex|opencode|all
```

## Design boundaries (deliberately not done)

- No vector database / embeddings — keyword search (with multiple rephrased queries per call, the LLM caller bridging semantics) is enough at page scale; `search.py` is the extension point
- Harness adapter isolation — each harness is its own `parser_<harness>.py` + `<harness>/` templates + `digest_<harness>.sh`, with no cross-references; add the same set of files for a new harness
- No Web UI — the wiki is markdown

## License

MIT
