from __future__ import annotations

import json
from pathlib import Path

from agent_profile_runtime.mcp import McpServerSpec

from ..layouts import claude_mcp_path, claude_settings_path, claude_state_path
from ..meta import ProfileMeta
from .profile import ClaudeCodeProfile


def load_claude_code_profile(profile_root: Path) -> ClaudeCodeProfile:
    meta = ProfileMeta.load(profile_root)
    settings_payload = _load_required_json(claude_settings_path(profile_root))
    state_path = claude_state_path(profile_root)
    state_payload = _load_optional_json(state_path)
    mcp_payload = _load_optional_json(claude_mcp_path(profile_root)) or {}
    mcp_servers = _parse_claude_mcp_servers(mcp_payload)

    profile = ClaudeCodeProfile(
        kind=meta.kind,
        name=meta.name,
        profile_dir=profile_root,
        meta=meta,
        settings_payload=settings_payload,
        claude_state_payload=state_payload,
        mcp_servers=mcp_servers,
    )
    profile.validate()
    return profile


def _parse_claude_mcp_servers(payload: dict[str, object]) -> list[McpServerSpec]:
    servers_payload = payload.get("mcpServers", {})
    if not isinstance(servers_payload, dict):
        raise ValueError("Claude MCP payload must define mcpServers object")
    servers: list[McpServerSpec] = []
    for name in sorted(servers_payload):
        server_payload = servers_payload[name]
        if not isinstance(server_payload, dict):
            raise ValueError(f"Claude MCP server {name!r} must be a JSON object")
        servers.append(McpServerSpec.from_claude_dict(name, server_payload))
    return servers


def _load_required_json(path: Path) -> dict[str, object]:
    return _load_json(path, required=True)


def _load_optional_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return _load_json(path, required=False)


def _load_json(path: Path, *, required: bool) -> dict[str, object]:
    if required and not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data
