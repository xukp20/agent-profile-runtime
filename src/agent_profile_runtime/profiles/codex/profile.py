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
class CodexProfile(BaseProfile):
    base_config_text: str = ""
    auth_payload: dict[str, object] = field(default_factory=dict)
    mcp_servers: list[McpServerSpec] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        profiles_root: Path,
        source_home: Path | None = None,
        config_toml_path: Path | None = None,
        base_config_text: str | None = None,
        auth_json_path: Path | None = None,
        auth_payload: dict[str, object] | None = None,
        mcp_servers: list[McpServerSpec] | None = None,
    ) -> "CodexProfile":
        root = profile_dir(profiles_root, ProviderKind.CODEX, name)

        resolved_base_config_text = resolve_codex_base_config_text(
            source_home=source_home,
            config_toml_path=config_toml_path,
            base_config_text=base_config_text,
        )
        resolved_auth_payload = resolve_json_payload(
            source_home=source_home,
            file_path=auth_json_path,
            filename="auth.json",
            payload=auth_payload,
        )
        return cls(
            kind=ProviderKind.CODEX,
            name=name,
            profile_dir=root,
            meta=ProfileMeta.create(kind=ProviderKind.CODEX, name=name),
            base_config_text=resolved_base_config_text,
            auth_payload=resolved_auth_payload,
            mcp_servers=list(mcp_servers or []),
        )

    def validate(self) -> None:
        if self.kind is not ProviderKind.CODEX:
            raise ValueError("CodexProfile must use ProviderKind.CODEX")
        if self.meta.kind is not ProviderKind.CODEX:
            raise ValueError("CodexProfile meta kind mismatch")
        if self.meta.name != self.name:
            raise ValueError("CodexProfile meta name mismatch")
        for server in self.mcp_servers:
            server.validate()

    def write(self) -> None:
        from .writer import write_codex_profile

        self.validate()
        write_codex_profile(self)

    @classmethod
    def from_dir(cls, profile_root: Path) -> "CodexProfile":
        from .loader import load_codex_profile

        return load_codex_profile(profile_root)

    @property
    def config_toml_text(self) -> str:
        from .blocks import build_codex_config, render_codex_mcp_servers

        return build_codex_config(
            base_config_text=self.base_config_text,
            mcp_servers_text=render_codex_mcp_servers(self.mcp_servers),
        )


def resolve_codex_base_config_text(
    *,
    source_home: Path | None,
    config_toml_path: Path | None,
    base_config_text: str | None,
) -> str:
    if base_config_text is not None:
        return base_config_text.strip() + ("\n" if base_config_text.strip() else "")
    if config_toml_path is not None:
        return config_toml_path.read_text(encoding="utf-8")
    if source_home is not None:
        candidate = source_home / "config.toml"
        return candidate.read_text(encoding="utf-8")
    return ""


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


def _read_json_payload(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data
