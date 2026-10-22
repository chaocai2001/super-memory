"""Incremental ingest cursor, persisted as JSON."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".super-memory"


class State:
    def __init__(self, path: Path):
        self.path = path
        self.files: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text())
                self.files = data.get("files", {})
            except (json.JSONDecodeError, OSError):
                self.files = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"files": self.files}, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    def offset_for(self, file_path: str) -> int:
        return int(self.files.get(file_path, {}).get("offset", 0))

    def mark_distilled(self, file_path: str, offset: int, session_id: str) -> None:
        self.files[file_path] = {
            "offset": offset,
            "session_id": session_id,
            "distilled": True,
        }

    def reset(self, file_path: str) -> None:
        self.files.pop(file_path, None)
