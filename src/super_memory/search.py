"""Lightweight keyword search over wiki pages (no third-party deps)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .wiki import Page, WikiStore


def tokenize(text: str) -> list[str]:
    """ASCII words plus CJK bigrams, lowercased."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9_][a-z0-9_\-\.]*", text)
    cjk = re.findall(r"[一-鿿]+", text)
    for run in cjk:
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


@dataclass
class Hit:
    page: Page
    score: float
    snippet: str


def _snippet(page: Page, query_tokens: list[str], width: int = 200) -> str:
    for heading, body in page.sections.items():
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if any(tok in low for tok in query_tokens):
                return f"[{heading}] " + (line if len(line) <= width else line[:width] + "…")
    body = next(iter(page.sections.values()), "")
    return body[:width].replace("\n", " ")


def search(store: WikiStore, query: str, limit: int = 5) -> list[Hit]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    hits: list[Hit] = []
    for page in store.list_pages():
        score = 0.0
        slug_tokens = tokenize(page.slug)
        title_low = page.title.lower()
        summary_low = page.summary.lower()
        body_text = "\n".join(page.sections.values()).lower()
        for tok in q_tokens:
            if tok in slug_tokens or tok in title_low:
                score += 5.0
            if tok in summary_low:
                score += 3.0
            score += min(body_text.count(tok), 10) * 1.0
        if score > 0:
            hits.append(Hit(page=page, score=score, snippet=_snippet(page, q_tokens)))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def build_injection(store: WikiStore, query: str, max_chars: int = 4000, limit: int = 5) -> str:
    """Render top hits as a memory block suitable for pasting into a new session."""
    hits = search(store, query, limit=limit)
    if not hits:
        return ""
    parts = ["# Relevant memory (from super-memory wiki)", ""]
    used = len(parts[0])
    for hit in hits:
        page = hit.page
        block = [f"## {page.title} (wiki/pages/{page.slug}.md)"]
        if page.summary:
            block.append(page.summary)
        block.append("")
        for heading, body in page.sections.items():
            if heading == "Related":
                continue
            block.append(f"### {heading}")
            block.append(body.strip())
            block.append("")
        text = "\n".join(block)
        if used + len(text) > max_chars:
            remaining = max_chars - used
            if remaining > 300:
                parts.append(text[:remaining] + "\n…[truncated]")
            break
        parts.append(text)
        used += len(text)
    return "\n".join(parts)
