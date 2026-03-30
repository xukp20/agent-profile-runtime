from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agent_profile_runtime.providers import ProviderKind

SessionStatus = Literal["ready", "broken", "closed"]


def _normalize_abs_path(path: str | None, *, name: str) -> str | None:
    if path is None:
        return None
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = resolved.resolve()
    return str(resolved)


@dataclass(slots=True, frozen=True)
class SessionInitConfig:
    provider_kind: ProviderKind
    profile_name: str = "default"
    workdir: str | None = None
    model: str | None = None
    additional_dirs: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    instructions_file_content: str | None = None

    def __post_init__(self) -> None:
        if not self.profile_name.strip():
            raise ValueError("profile_name must be non-empty")
        if self.workdir is not None:
            object.__setattr__(self, "workdir", _normalize_abs_path(self.workdir, name="workdir"))
        normalized_dirs = tuple(
            _normalize_abs_path(directory, name="additional_dirs[]") or ""
            for directory in self.additional_dirs
        )
        object.__setattr__(self, "additional_dirs", normalized_dirs)


@dataclass(slots=True, frozen=True)
class SessionEffectiveConfig:
    provider_kind: ProviderKind
    profile_name: str
    profile_dir: str
    workdir: str
    model: str | None
    additional_dirs: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    instructions_filename: str


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    provider_kind: ProviderKind
    profile_name: str
    profile_dir: str
    provider_session_id: str | None
    workdir: str
    model: str | None
    additional_dirs: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    status: SessionStatus
    created_at: str
    updated_at: str
    last_run_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "provider_kind": self.provider_kind.value,
            "profile_name": self.profile_name,
            "profile_dir": self.profile_dir,
            "provider_session_id": self.provider_session_id,
            "workdir": self.workdir,
            "model": self.model,
            "additional_dirs": list(self.additional_dirs),
            "env": [[k, v] for k, v in self.env],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_id": self.last_run_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SessionRecord":
        env_pairs = tuple((str(k), str(v)) for k, v in (data.get("env") or []))
        return cls(
            session_id=str(data["session_id"]),
            provider_kind=ProviderKind.from_value(str(data["provider_kind"])),
            profile_name=str(data["profile_name"]),
            profile_dir=str(data["profile_dir"]),
            provider_session_id=str(data["provider_session_id"]) if data.get("provider_session_id") else None,
            workdir=str(data["workdir"]),
            model=str(data["model"]) if data.get("model") is not None else None,
            additional_dirs=tuple(str(item) for item in (data.get("additional_dirs") or [])),
            env=env_pairs,
            status=str(data["status"]),  # type: ignore[arg-type]
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            last_run_id=str(data["last_run_id"]) if data.get("last_run_id") else None,
        )

