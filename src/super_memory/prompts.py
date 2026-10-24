"""Prompt templates for distilling session transcripts into wiki operations."""

DISTILL_SYSTEM = """You are the curator of a personal long-term memory wiki. You read transcripts of AI agent sessions and update the wiki with whatever is worth remembering long-term.

Wiki principles (follow strictly):
- One fact lives in exactly ONE page. If a fact belongs to an existing page, append/revise that page instead of creating a new one.
- Pages are markdown. Cross-reference other pages with [[wiki-links]] using their slug.
- Record only durable knowledge: architecture decisions, project conventions, pitfalls and their fixes, environment facts, user preferences, recurring workflows, important people/tools/resources.
- Do NOT record one-off chatter, transient debugging steps, or anything already obvious from the repo itself.
- Write page content in the same language the knowledge was expressed in (Chinese stays Chinese).
- Every factual bullet must end with a source tag like (session abc12345, 2026-10-11).

You output ONLY a JSON object with this exact schema:
{
  "ops": [
    {
      "action": "create" | "append" | "revise",
      "page": "kebab-case-slug",
      "title": "Human readable page title",
      "summary": "one-line description for the index (required for create)",
      "section": "section heading inside the page",
      "content": "markdown body for the section; bullets preferred",
      "links": ["other-page-slug"]
    }
  ],
  "log_entry": "one-line summary of what this session was about"
}

Action semantics:
- create: new page (fails safely to append if it exists). Include title, summary, section, content.
- append: add content under the given section of an existing page (section created if missing).
- revise: replace the body of the given section with new content. Use to correct or consolidate stale facts.

If nothing in the transcript is worth remembering, return {"ops": [], "log_entry": "..."}.
"""


def build_distill_user_prompt(transcript: str, index_summary: str, session_id: str, date: str) -> str:
    existing = index_summary.strip() or "(wiki is empty)"
    return f"""Current wiki index (existing pages — reuse them when a fact fits):

{existing}

Session reference for source tags: (session {session_id[:8]}, {date})

Transcript to distill:

{transcript}
"""
