"""Parse Kimi Code wire.jsonl logs into condensed session transcripts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MAX_TOOL_CHARS = 500
MAX_MSG_CHARS = 2000
MAX_TRANSCRIPT_CHARS = 12000

DIGEST_PROMPT_PREFIX = "super-memory digest"


def default_kimi_home() -> Path:
    return Path(os.environ.get("KIMI_CODE_HOME") or Path.home() / ".kimi-code")


def default_sessions_dir() -> Path:
    return default_kimi_home() / "sessions"


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


def _iso(value: int | float | str | None) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat(timespec="seconds")
    return datetime.fromtimestamp(value / 1000).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _session_dir(wire_path: Path) -> Path:
    return wire_path.parent.parent.parent


def _is_digest_session(wire_path: Path) -> bool:
    state = _load_json(_session_dir(wire_path) / "state.json")
    return any(
        str(state.get(key) or "").startswith(DIGEST_PROMPT_PREFIX)
        for key in ("title", "lastPrompt")
    )


def find_log_files(kimi_home: Path) -> list[Path]:
    sessions_dir = kimi_home / "sessions"
    if not sessions_dir.is_dir():
        return []
    return [
        path
        for path in sorted(sessions_dir.glob("*/*/agents/main/wire.jsonl"))
        if not _is_digest_session(path)
    ]


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "\n".join(part for part in parts if part)


def _append_message(turns: list[Turn], event: dict, ts: str) -> None:
    envelope = event.get("message") or {}
    message = envelope.get("message") or {}
    meta = envelope.get("meta") or {}
    role = message.get("role", "")
    if role not in ("user", "assistant", "tool"):
        return
    if role == "user" and (meta.get("origin") or {}).get("kind", "user") != "user":
        return

    text = _content_text(message.get("content"))
    if text.strip():
        turns.append(Turn(
            role="tool_output" if role == "tool" else role,
            text=_clip(text, MAX_TOOL_CHARS if role == "tool" else MAX_MSG_CHARS),
            ts=ts,
        ))
    if role != "assistant":
        return

    for call in message.get("toolCalls") or []:
        if not isinstance(call, dict):
            continue
        name = call.get("name", "?")
        args = call.get("arguments") or ""
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        turns.append(Turn(role="tool", text=f"{name}: {_clip(args, MAX_TOOL_CHARS)}", ts=ts))


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

    session_dir = _session_dir(path)
    state = _load_json(session_dir / "state.json")
    session_id = state.get("id") or session_dir.name
    cwd = state.get("cwd") or ""
    started_at = _iso(state.get("createdAt"))
    turns: list[Turn] = []

    for raw in chunk.decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("type") != "agent.message.appended":
            continue
        _append_message(turns, rec, _iso(rec.get("time")))

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
