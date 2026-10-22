"""Lightweight keyword search over wiki pages (no third-party deps)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .wiki import Page, WikiStore


def tokenize(text: str) -> list[str]:
    """ASCII words plus CJK bigrams, lowercased (lone CJK chars kept)."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9_][a-z0-9_\-\.]*", text)
    cjk = re.findall(r"[一-鿿]+", text)
    for run in cjk:
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def weak_tokenize(text: str) -> list[str]:
    """Low-confidence tokens: CJK unigrams from multi-char runs, crude English stems."""
    text = text.lower()
    weak: list[str] = []
    for run in re.findall(r"[一-鿿]+", text):
        if len(run) > 1:
            weak.extend(run)
    for tok in re.findall(r"[a-z]+", text):
        if len(tok) > 4:
            for suf in ("ing", "ed", "es", "s"):
                if tok.endswith(suf) and len(tok) - len(suf) >= 3:
                    weak.append(tok[:-len(suf)])
                    break
    return [t for t in dict.fromkeys(weak) if t not in tokenize(text)]


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


def _score_page(page: Page, q_tokens: list[str], q_weak: list[str]) -> float:
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
    for tok in q_weak:
        score += min(body_text.count(tok), 10) * 0.5
    return score


def search(store: WikiStore, query: str | list[str], limit: int = 5) -> list[Hit]:
    queries = [query] if isinstance(query, str) else list(query)
    pages = store.list_pages()
    best: dict[str, tuple[Page, float, list[str]]] = {}
    for q in queries:
        q_tokens = tokenize(q)
        if not q_tokens:
            continue
        q_weak = weak_tokenize(q)
        for page in pages:
            score = _score_page(page, q_tokens, q_weak)
            if score > 0:
                prev = best.get(page.slug)
                if prev is None or score > prev[1]:
                    best[page.slug] = (page, score, q_tokens)
    hits = [Hit(page=p, score=s, snippet=_snippet(p, toks)) for p, s, toks in best.values()]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def build_injection(store: WikiStore, query: str | list[str], max_chars: int = 4000, limit: int = 5) -> str:
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
