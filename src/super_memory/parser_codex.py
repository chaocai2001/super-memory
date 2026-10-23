"""Parse codex rollout jsonl logs into condensed session transcripts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

MAX_TOOL_CHARS = 500
MAX_MSG_CHARS = 2000
MAX_TRANSCRIPT_CHARS = 12000


@dataclass
class Turn:
    role: str  # user | assistant | tool | tool_output
    text: str
    ts: str = ""


@dataclass
class Transcript:
    session_id: str
    cwd: str
    started_at: str
    source_file: str
    turns: list[Turn] = field(default_factory=list)

    def has_content(self) -> bool:
        return any(t.role in ("user", "assistant") for t in self.turns)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"…[+{len(text) - limit} chars]"


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for c in content or []:
        if isinstance(c, dict) and c.get("type") in ("input_text", "output_text"):
            parts.append(c.get("text", ""))
    return "\n".join(p for p in parts if p)


def _is_wrapper_user_message(text: str) -> bool:
    head = text.lstrip()[:120]
    return head.startswith("<environment_context") or head.startswith("<app-context")


def find_log_files(sessions_dir: Path) -> list[Path]:
    if not sessions_dir.is_dir():
        return []
    return sorted(sessions_dir.rglob("*.jsonl"))


def parse_file(path: Path, offset: int = 0) -> tuple[Transcript | None, int]:
    """Parse new bytes of a rollout file starting at byte offset.

    Returns (transcript, end_offset). transcript is None when the file
    yielded no parseable new records.
    """
    size = path.stat().st_size
    if offset >= size:
        return None, offset

    session_id = path.stem.rsplit("-", 5)[-1] if "-" in path.stem else path.stem
    cwd = ""
    started_at = ""
    turns: list[Turn] = []

    with open(path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    end_offset = offset + len(chunk)

    for raw in chunk.decode("utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue

        rtype = rec.get("type")
        payload = rec.get("payload") or {}
        ptype = payload.get("type") if isinstance(payload, dict) else None
        ts = rec.get("timestamp", "")[:19]

        if rtype == "session_meta":
            session_id = payload.get("session_id") or payload.get("id") or session_id
            cwd = payload.get("cwd") or cwd
            started_at = (payload.get("timestamp") or ts)[:19]
            continue

        if rtype != "response_item" or not isinstance(payload, dict):
            continue

        if ptype == "message":
            role = payload.get("role", "")
            if role not in ("user", "assistant"):
                continue
            text = _content_text(payload.get("content"))
            if not text or _is_wrapper_user_message(text):
                continue
            turns.append(Turn(role=role, text=_clip(text, MAX_MSG_CHARS), ts=ts))
        elif ptype in ("custom_tool_call", "function_call"):
            name = payload.get("name", "?")
            args = payload.get("input") or payload.get("arguments") or ""
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            turns.append(Turn(role="tool", text=f"{name}: {_clip(args, MAX_TOOL_CHARS)}", ts=ts))
        elif ptype in ("custom_tool_call_output", "function_call_output"):
            out = _content_text(payload.get("output")) or str(payload.get("output") or "")
            turns.append(Turn(role="tool_output", text=_clip(out, MAX_TOOL_CHARS), ts=ts))

    if not turns and not cwd:
        return None, end_offset
    return (
        Transcript(
            session_id=session_id,
            cwd=cwd,
            started_at=started_at,
            source_file=str(path),
            turns=turns,
        ),
        end_offset,
    )


def render_transcript(t: Transcript) -> str:
    """Render a condensed, token-bounded transcript for the distill prompt."""
    lines = [
        f"# Session {t.session_id}",
        f"# cwd: {t.cwd}",
        f"# started: {t.started_at}",
        "",
    ]
    role_label = {"user": "USER", "assistant": "ASSISTANT", "tool": "TOOL CALL", "tool_output": "TOOL OUT"}
    for turn in t.turns:
        label = role_label.get(turn.role, turn.role.upper())
        prefix = f"[{turn.ts}] " if turn.ts else ""
        lines.append(f"{prefix}{label}: {turn.text}")
        lines.append("")

    body = "\n".join(lines)
    if len(body) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        body = (
            body[:half]
            + f"\n\n…[middle {len(body) - MAX_TRANSCRIPT_CHARS} chars omitted]…\n\n"
            + body[-half:]
        )
    return body
