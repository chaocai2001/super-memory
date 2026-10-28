"""Parse Claude Code project JSONL logs into condensed session transcripts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_TOOL_CHARS = 500
MAX_MSG_CHARS = 2000
MAX_TRANSCRIPT_CHARS = 12000

DIGEST_PROMPT_PREFIX = "super-memory digest"


def default_claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def default_projects_dir() -> Path:
    return default_claude_home() / "projects"


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
    if not isinstance(content, list):
        return ""
    return "\n".join(
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
    )


def _is_digest_session(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(65536)
    except OSError:
        return False
    for raw in chunk.decode("utf-8", errors="ignore").splitlines():
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("type") == "queue-operation":
            content = rec.get("content") or ""
            if isinstance(content, str) and content.strip():
                return content.startswith(DIGEST_PROMPT_PREFIX)
        if rec.get("type") != "user" or rec.get("isSidechain"):
            continue
        text = _content_text((rec.get("message") or {}).get("content"))
        if text.strip():
            return text.startswith(DIGEST_PROMPT_PREFIX)
    return False


def find_log_files(claude_home: Path) -> list[Path]:
    projects_dir = claude_home / "projects"
    if not projects_dir.is_dir():
        return []
    return [
        path
        for path in sorted(projects_dir.glob("*/*.jsonl"))
        if not _is_digest_session(path)
    ]


def _append_assistant(turns: list[Turn], content, ts: str) -> None:
    text = _content_text(content)
    if text.strip():
        turns.append(Turn(role="assistant", text=_clip(text, MAX_MSG_CHARS), ts=ts))
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_use":
            continue
        name = item.get("name", "?")
        args = json.dumps(item.get("input") or {}, ensure_ascii=False)
        turns.append(Turn(role="tool", text=f"{name}: {_clip(args, MAX_TOOL_CHARS)}", ts=ts))


def _append_user(turns: list[Turn], rec: dict, content, ts: str) -> None:
    text = _content_text(content)
    origin_kind = (rec.get("origin") or {}).get("kind")
    if text.strip() and not rec.get("isMeta") and origin_kind in (None, "human"):
        turns.append(Turn(role="user", text=_clip(text, MAX_MSG_CHARS), ts=ts))
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_result":
            continue
        output = _content_text(item.get("content"))
        if not output and item.get("content") is not None:
            output = str(item.get("content"))
        if output.strip():
            turns.append(Turn(role="tool_output", text=_clip(output, MAX_TOOL_CHARS), ts=ts))


def parse_file(path: Path, offset: int = 0) -> tuple[Transcript | None, int]:
    """Parse complete new JSONL records, retaining an incomplete trailing line."""
    size = path.stat().st_size
    if offset >= size:
        return None, offset

    with open(path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    if not chunk.endswith(b"\n"):
        last_newline = chunk.rfind(b"\n")
        if last_newline < 0:
            return None, offset
        chunk = chunk[:last_newline + 1]
    end_offset = offset + len(chunk)

    session_id = path.stem
    cwd = ""
    started_at = ""
    turns: list[Turn] = []

    for raw in chunk.decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("isSidechain"):
            continue
        session_id = rec.get("sessionId") or rec.get("session_id") or session_id
        cwd = rec.get("cwd") or cwd
        ts = rec.get("timestamp", "")[:19]
        if not started_at and ts:
            started_at = ts
        rtype = rec.get("type")
        if rtype not in ("user", "assistant"):
            continue
        message = rec.get("message") or {}
        if message.get("role") != rtype:
            continue
        if rtype == "assistant":
            _append_assistant(turns, message.get("content"), ts)
        else:
            _append_user(turns, rec, message.get("content"), ts)

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
