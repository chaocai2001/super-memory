"""Parse opencode session storage into condensed transcripts.

Self-contained opencode harness adapter: intentionally shares no code with
parser_codex.py so the two harnesses can evolve independently.

Storage layout (two generations; the sqlite store is preferred when present):

  SQLite (current): ~/.local/share/opencode/opencode.db
    session(id, project_id, directory, title, time_created, time_updated)
    message(id, session_id, time_created, data JSON: role, time.created)
    part(id, message_id, session_id, time_created, data JSON: type text|tool|...)

  Legacy JSON: ~/.local/share/opencode/storage/ (or $XDG_DATA_HOME/opencode/storage/)
    session/<projectID>/<sessionID>.json   metadata: directory, title, time.{created,updated}
    message/<sessionID>/<messageID>.json   role, time.created
    part/<messageID>/<partID>.json         type: text | tool | reasoning | step-* | patch | file
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MAX_TOOL_CHARS = 500
MAX_MSG_CHARS = 2000
MAX_TRANSCRIPT_CHARS = 12000

DIGEST_TITLE_PREFIX = "super-memory digest"


def default_storage_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "opencode" / "storage"


def default_db_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "opencode" / "opencode.db"


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


def _iso(ms: int | float | None) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def find_sessions(storage_dir: Path) -> list[Path]:
    """Session json paths sorted by creation time, digest worker sessions excluded."""
    sessions_dir = storage_dir / "session"
    if not sessions_dir.is_dir():
        return []
    metas = []
    for path in sessions_dir.glob("*/*.json"):
        data = _load_json(path)
        if data is None:
            continue
        title = data.get("title") or ""
        if title.startswith(DIGEST_TITLE_PREFIX):
            continue
        metas.append((data.get("time", {}).get("created", 0), path))
    return [p for _, p in sorted(metas)]


def _message_parts(storage_dir: Path, message_id: str) -> list[dict]:
    parts_dir = storage_dir / "part" / message_id
    if not parts_dir.is_dir():
        return []
    parts = []
    for path in sorted(parts_dir.glob("*.json")):  # part ids are time-ordered
        data = _load_json(path)
        if data is not None:
            parts.append(data)
    return parts


def _append_part_turns(turns: list[Turn], role: str, ts: str, part: dict) -> None:
    ptype = part.get("type")
    if ptype == "text":
        text = part.get("text") or ""
        if text.strip():
            turns.append(Turn(role=role, text=_clip(text, MAX_MSG_CHARS), ts=ts))
    elif ptype == "tool":
        state = part.get("state") or {}
        name = part.get("tool", "?")
        args = json.dumps(state.get("input") or {}, ensure_ascii=False)
        turns.append(Turn(role="tool", text=f"{name}: {_clip(args, MAX_TOOL_CHARS)}", ts=ts))
        out = state.get("output") or ""
        turns.append(Turn(role="tool_output", text=_clip(str(out), MAX_TOOL_CHARS), ts=ts))


def parse_session(session_path: Path, cursor_ms: int = 0) -> tuple[Transcript | None, int]:
    """Parse one opencode session into a transcript.

    Returns (transcript, end_cursor). transcript is None when the session has
    not been updated past cursor_ms. The cursor is the session's time.updated
    in milliseconds; the whole session is re-rendered on each change (wiki
    append dedupe makes re-distillation idempotent).
    """
    meta = _load_json(session_path)
    if meta is None:
        return None, cursor_ms
    updated = int(meta.get("time", {}).get("updated", 0) or 0)
    if updated <= cursor_ms:
        return None, cursor_ms

    storage_dir = session_path.parent.parent.parent
    session_id = meta.get("id") or session_path.stem
    cwd = meta.get("directory") or ""
    started_at = _iso(meta.get("time", {}).get("created"))

    turns: list[Turn] = []
    messages_dir = storage_dir / "message" / session_id
    if messages_dir.is_dir():
        messages = []
        for path in messages_dir.glob("*.json"):
            data = _load_json(path)
            if data is not None:
                messages.append(data)
        messages.sort(key=lambda m: m.get("time", {}).get("created", 0))

        for msg in messages:
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue
            ts = _iso(msg.get("time", {}).get("created"))
            for part in _message_parts(storage_dir, msg.get("id", "")):
                _append_part_turns(turns, role, ts, part)

    if not turns and not cwd:
        return None, updated
    return (
        Transcript(
            session_id=session_id,
            cwd=cwd,
            started_at=started_at,
            source_file=str(session_path),
            turns=turns,
        ),
        updated,
    )


DB_KEY_PREFIX = "sqlite://"


def db_key(db_path: Path, session_id: str) -> str:
    return f"{DB_KEY_PREFIX}{db_path}#{session_id}"


def split_db_key(key: str) -> tuple[Path, str]:
    db_str, _, session_id = key[len(DB_KEY_PREFIX):].rpartition("#")
    return Path(db_str), session_id


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def find_db_sessions(db_path: Path) -> list[str]:
    """Unit keys for sessions in the sqlite store, digest worker sessions excluded."""
    if not db_path.is_file():
        return []
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT id, title FROM session ORDER BY time_created").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        db_key(db_path, session_id)
        for session_id, title in rows
        if not (title or "").startswith(DIGEST_TITLE_PREFIX)
    ]


def parse_db_session(db_path: Path, session_id: str, cursor_ms: int = 0) -> tuple[Transcript | None, int]:
    """Parse one session from the sqlite store; same cursor semantics as parse_session."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT directory, time_created, time_updated FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None, cursor_ms
        cwd, created, updated = row
        updated = int(updated or 0)
        if updated <= cursor_ms:
            return None, cursor_ms

        turns: list[Turn] = []
        messages = conn.execute(
            "SELECT id, time_created, data FROM message WHERE session_id = ? ORDER BY time_created",
            (session_id,),
        ).fetchall()
        for message_id, m_created, data in messages:
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue
            ts = _iso(msg.get("time", {}).get("created") or m_created)
            parts = conn.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created",
                (message_id,),
            ).fetchall()
            for (part_data,) in parts:
                try:
                    part = json.loads(part_data)
                except json.JSONDecodeError:
                    continue
                _append_part_turns(turns, role, ts, part)
    except sqlite3.Error:
        return None, cursor_ms
    finally:
        conn.close()

    if not turns and not cwd:
        return None, updated
    return (
        Transcript(
            session_id=session_id,
            cwd=cwd or "",
            started_at=_iso(created),
            source_file=db_key(db_path, session_id),
            turns=turns,
        ),
        updated,
    )


def parse_unit(key: str, cursor_ms: int = 0) -> tuple[Transcript | None, int]:
    """Parse a unit key: a sqlite:// key for the db store, otherwise a legacy JSON path."""
    if key.startswith(DB_KEY_PREFIX):
        db_path, session_id = split_db_key(key)
        return parse_db_session(db_path, session_id, cursor_ms)
    return parse_session(Path(key), cursor_ms)


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
