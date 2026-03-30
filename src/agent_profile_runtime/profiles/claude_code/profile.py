from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_profile_runtime.mcp import McpServerSpec
from agent_profile_runtime.providers import ProviderKind

from ..base import BaseProfile
from ..layouts import profile_dir
from ..meta import ProfileMeta


@dataclass(slots=True)
class ClaudeCodeProfile(BaseProfile):
    settings_payload: dict[str, object] = field(default_factory=dict)
    claude_state_payload: dict[str, object] | None = None
    mcp_servers: list[McpServerSpec] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        profiles_root: Path,
        source_home: Path | None = None,
        settings_json_path: Path | None = None,
        settings_payload: dict[str, object] | None = None,
        claude_state_json_path: Path | None = None,
        claude_state_payload: dict[str, object] | None = None,
        mcp_servers: list[McpServerSpec] | None = None,
    ) -> "ClaudeCodeProfile":
        root = profile_dir(profiles_root, ProviderKind.CLAUDE_CODE, name)
        resolved_settings_payload = resolve_json_payload(
            source_home=source_home,
            file_path=settings_json_path,
            filename="settings.json",
            payload=settings_payload,
        )
        resolved_state_payload = resolve_optional_json_payload(
            source_home=source_home,
            file_path=claude_state_json_path,
            filename=".claude.json",
            payload=claude_state_payload,
        )
        return cls(
            kind=ProviderKind.CLAUDE_CODE,
            name=name,
            profile_dir=root,
            meta=ProfileMeta.create(kind=ProviderKind.CLAUDE_CODE, name=name),
            settings_payload=resolved_settings_payload,
            claude_state_payload=resolved_state_payload,
            mcp_servers=list(mcp_servers or []),
        )

    def validate(self) -> None:
        if self.kind is not ProviderKind.CLAUDE_CODE:
            raise ValueError("ClaudeCodeProfile must use ProviderKind.CLAUDE_CODE")
        if self.meta.kind is not ProviderKind.CLAUDE_CODE:
            raise ValueError("ClaudeCodeProfile meta kind mismatch")
        if self.meta.name != self.name:
            raise ValueError("ClaudeCodeProfile meta name mismatch")
        if not isinstance(self.settings_payload, dict):
            raise ValueError("ClaudeCodeProfile settings payload must be a JSON object")
        if self.claude_state_payload is not None and not isinstance(self.claude_state_payload, dict):
            raise ValueError("ClaudeCodeProfile state payload must be a JSON object or None")
        for server in self.mcp_servers:
            server.validate()

    def write(self) -> None:
        from .writer import write_claude_code_profile

        self.validate()
        write_claude_code_profile(self)

    @classmethod
    def from_dir(cls, profile_root: Path) -> "ClaudeCodeProfile":
        from .loader import load_claude_code_profile

        return load_claude_code_profile(profile_root)


def resolve_json_payload(
    *,
    source_home: Path | None,
    file_path: Path | None,
    filename: str,
    payload: dict[str, object] | None,
) -> dict[str, object]:
    if payload is not None:
        return dict(payload)
    if file_path is not None:
        return _read_json_payload(file_path)
    if source_home is not None:
        candidate = source_home / filename
        if candidate.exists():
            return _read_json_payload(candidate)
    return {}


def resolve_optional_json_payload(
    *,
    source_home: Path | None,
    file_path: Path | None,
    filename: str,
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    if payload is not None:
        return dict(payload)
    if file_path is not None:
        return _read_json_payload(file_path)
    if source_home is not None:
        candidate = source_home / filename
        if candidate.exists():
            return _read_json_payload(candidate)
    return None


def _read_json_payload(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data
