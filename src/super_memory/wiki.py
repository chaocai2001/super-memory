"""Markdown wiki store: pages with front-matter, global index, event timeline."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path

from .state import DEFAULT_STATE_DIR

DEFAULT_WIKI_DIR = DEFAULT_STATE_DIR / "wiki"
RELATED_HEADING = "Related"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w一-鿿]+", "-", text)
    return text.strip("-") or "untitled"


@dataclass
class Page:
    slug: str
    title: str
    summary: str = ""
    updated: str = ""
    sources: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)  # heading -> body

    def render(self) -> str:
        lines = ["---"]
        lines.append(f"title: {self.title}")
        lines.append(f"summary: {self.summary}")
        lines.append(f"updated: {self.updated}")
        lines.append("sources:")
        for s in self.sources:
            lines.append(f"  - {s}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.title}")
        lines.append("")
        for heading, body in self.sections.items():
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(body.rstrip())
            lines.append("")
        return "\n".join(lines)


def parse_page(slug: str, text: str) -> Page:
    page = Page(slug=slug, title=slug)
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    body = text
    if fm_match:
        body = text[fm_match.end():]
        current_list = None
        for line in fm_match.group(1).splitlines():
            if line.startswith("  - ") and current_list == "sources":
                page.sources.append(line[4:].strip())
            elif ":" in line:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                current_list = key
                if key == "title":
                    page.title = val
                elif key == "summary":
                    page.summary = val
                elif key == "updated":
                    page.updated = val

    current_heading = None
    buf: list[str] = []
    def flush():
        if current_heading is not None:
            page.sections[current_heading] = "\n".join(buf).strip()

    for line in body.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            flush()
            current_heading = m.group(1).strip()
            buf = []
        elif current_heading is not None:
            buf.append(line)
        elif re.match(r"^# ", line):
            if not fm_match:
                page.title = line[2:].strip()
    flush()
    return page


class WikiStore:
    def __init__(self, root: Path):
        self.root = root
        self.pages_dir = root / "pages"
        self.index_path = root / "index.md"
        self.log_path = root / "log.md"

    def load_page(self, slug: str) -> Page | None:
        path = self.pages_dir / f"{slug}.md"
        if not path.is_file():
            return None
        return parse_page(slug, path.read_text())

    def save_page(self, page: Page) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        (self.pages_dir / f"{page.slug}.md").write_text(page.render())

    def list_pages(self) -> list[Page]:
        if not self.pages_dir.is_dir():
            return []
        pages = []
        for path in sorted(self.pages_dir.glob("*.md")):
            pages.append(parse_page(path.stem, path.read_text()))
        return pages

    def _merge_related(self, page: Page, links: list[str]) -> None:
        if not links:
            return
        existing = page.sections.get(RELATED_HEADING, "")
        bullets = [l for l in existing.splitlines() if l.strip()]
        known = set(bullets)
        for link in links:
            slug = slugify(link)
            if slug == page.slug:
                continue
            bullet = f"- [[{slug}]]"
            if bullet not in known:
                bullets.append(bullet)
                known.add(bullet)
        page.sections[RELATED_HEADING] = "\n".join(bullets)

    def _add_source(self, page: Page, source_tag: str) -> None:
        if source_tag and source_tag not in page.sources:
            page.sources.append(source_tag)

    def apply_ops(self, ops: list[dict], source_tag: str, today: str | None = None) -> list[str]:
        today = today or date_type.today().isoformat()
        applied = []
        for op in ops:
            slug = slugify(op.get("page", ""))
            action = op["action"]
            page = self.load_page(slug)
            if page is None:
                action = "create"
                page = Page(slug=slug, title=op.get("title") or slug)

            if action == "create":
                if op.get("title"):
                    page.title = op["title"]
                if op.get("summary"):
                    page.summary = op["summary"]
                section = op.get("section") or "Overview"
                page.sections[section] = op["content"].strip()
                applied.append(f"create {slug}")
            elif action == "append":
                section = op.get("section") or "Notes"
                existing = page.sections.get(section, "")
                seen = {l.strip() for l in existing.splitlines() if l.strip()}
                new_lines = []
                for l in op["content"].strip().splitlines():
                    if l.strip() and l.strip() not in seen:
                        new_lines.append(l)
                        seen.add(l.strip())
                if new_lines:
                    body = existing.rstrip()
                    page.sections[section] = (body + "\n" if body else "") + "\n".join(new_lines)
                applied.append(f"append {slug}#{section} (+{len(new_lines)} lines)")
            elif action == "revise":
                section = op.get("section") or "Overview"
                page.sections[section] = op["content"].strip()
                applied.append(f"revise {slug}#{section}")

            self._merge_related(page, [str(l) for l in op.get("links") or []])
            self._add_source(page, source_tag)
            page.updated = today
            self.save_page(page)

        if ops:
            self.rebuild_index()
        return applied

    def rebuild_index(self) -> None:
        pages = self.list_pages()
        lines = ["# Memory Wiki Index", ""]
        if not pages:
            lines.append("(empty)")
        for p in pages:
            summary = f" — {p.summary}" if p.summary else ""
            lines.append(f"- [[{p.slug}]]{summary} (updated {p.updated})")
        lines.append("")
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text("\n".join(lines))

    def index_summary(self) -> str:
        pages = self.list_pages()
        return "\n".join(
            f"- {p.slug}: {p.summary}" if p.summary else f"- {p.slug}" for p in pages
        )

    def append_log(self, date: str, cwd: str, entry: str, session_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        project = Path(cwd).name if cwd else "?"
        line = f"- {date} · `{project}` · {entry} (session {session_id[:8]})\n"
        if not self.log_path.is_file():
            self.log_path.write_text("# Session Log\n\n")
        with open(self.log_path, "a") as fh:
            fh.write(line)
