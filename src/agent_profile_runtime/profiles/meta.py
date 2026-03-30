from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_profile_runtime.providers import ProviderKind

PROFILE_META_FILENAME = "profile.meta.json"
PROFILE_SCHEMA_VERSION = "profile.v1"


@dataclass(slots=True)
class ProfileMeta:
    kind: ProviderKind
    name: str
    created_at: str
    updated_at: str
    schema_version: str = PROFILE_SCHEMA_VERSION

    @classmethod
    def create(cls, *, kind: ProviderKind, name: str) -> "ProfileMeta":
        now = _utc_now()
        return cls(kind=kind, name=name, created_at=now, updated_at=now)

    @classmethod
    def load(cls, profile_dir: Path) -> "ProfileMeta":
        path = profile_dir / PROFILE_META_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=str(data.get("schema_version") or PROFILE_SCHEMA_VERSION),
            kind=ProviderKind.from_value(str(data["kind"])),
            name=str(data["name"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )

    def write(self, profile_dir: Path) -> None:
        path = profile_dir / PROFILE_META_FILENAME
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def touch_updated(self) -> None:
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
