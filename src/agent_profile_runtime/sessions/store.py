from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import SessionRecord


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class SessionStore:
    runtime_dir: Path

    def __post_init__(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    @property
    def sessions_dir(self) -> Path:
        return self.runtime_dir / "sessions"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / f"s_{session_id}"

    def session_record_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.record.json"

    def create_session(self, record: SessionRecord) -> SessionRecord:
        session_dir = self.session_dir(record.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._write_session_record(record)
        return record

    def get_session(self, session_id: str) -> SessionRecord:
        path = self.session_record_path(session_id)
        if not path.exists():
            raise KeyError(f"session not found: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionRecord.from_dict(data)

    def update_session(self, record: SessionRecord) -> None:
        self._write_session_record(record)

    def update_provider_session_id(self, session_id: str, provider_session_id: str) -> SessionRecord:
        record = self.get_session(session_id)
        record.provider_session_id = provider_session_id
        record.updated_at = utc_now_iso()
        self.update_session(record)
        return record

    def mark_session_broken(self, session_id: str) -> SessionRecord:
        record = self.get_session(session_id)
        record.status = "broken"
        record.updated_at = utc_now_iso()
        self.update_session(record)
        return record

    def update_last_run_id(self, session_id: str, run_id: str) -> SessionRecord:
        record = self.get_session(session_id)
        record.last_run_id = run_id
        record.updated_at = utc_now_iso()
        self.update_session(record)
        return record

    def list_sessions(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        if not self.sessions_dir.exists():
            return records
        for directory in sorted(path for path in self.sessions_dir.iterdir() if path.is_dir()):
            path = directory / "session.record.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            records.append(SessionRecord.from_dict(data))
        return records

    def _write_session_record(self, record: SessionRecord) -> None:
        path = self.session_record_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

