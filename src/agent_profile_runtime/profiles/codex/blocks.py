from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass

from agent_profile_runtime.mcp import McpServerSpec, McpTransport

BASE_CONFIG_BLOCK = "base-config"
MCP_SERVERS_BLOCK = "mcp-servers"


@dataclass(slots=True, frozen=True)
class CodexConfigBlocks:
    base_config_text: str
    mcp_servers_text: str


def split_codex_config(text: str) -> CodexConfigBlocks:
    return CodexConfigBlocks(
        base_config_text=extract_block(text, BASE_CONFIG_BLOCK),
        mcp_servers_text=extract_block(text, MCP_SERVERS_BLOCK, default=""),
    )


def build_codex_config(*, base_config_text: str, mcp_servers_text: str) -> str:
    parts = [
        _format_block(BASE_CONFIG_BLOCK, base_config_text),
        _format_block(MCP_SERVERS_BLOCK, mcp_servers_text),
    ]
    return "\n\n".join(parts).rstrip() + "\n"


def extract_block(text: str, block_name: str, default: str | None = None) -> str:
    pattern = re.compile(
        rf"^\s*#\s*{re.escape(block_name)}:start\s*$\n(?P<body>.*?)^\s*#\s*{re.escape(block_name)}:end\s*$",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        return _normalize_body(match.group("body"))
    if default is not None:
        return default
    raise ValueError(f"Missing managed block {block_name!r}")


def parse_codex_mcp_servers(block_text: str) -> list[McpServerSpec]:
    block_text = block_text.strip()
    if not block_text:
        return []
    data = tomllib.loads(block_text)
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ValueError("Codex MCP block must define [mcp_servers.*] tables")

    parsed: list[McpServerSpec] = []
    for name in sorted(servers):
        payload = servers[name]
        if not isinstance(payload, dict):
            raise ValueError(f"Codex MCP server {name!r} must be a table")
        if "url" in payload:
            transport = McpTransport.HTTP
        else:
            transport = McpTransport.STDIO
        parsed.append(
            McpServerSpec(
                name=name,
                transport=transport,
                url=_as_optional_str(payload.get("url")),
                command=_as_optional_str(payload.get("command")),
                args=tuple(_as_str_list(payload.get("args"))),
                env=_as_str_dict(payload.get("env")),
                env_passthrough=tuple(_as_str_list(payload.get("env_vars"))),
                startup_timeout_sec=_as_optional_int(payload.get("startup_timeout_sec")),
                tool_timeout_sec=_as_optional_int(payload.get("tool_timeout_sec")),
                enabled=bool(payload.get("enabled", True)),
            )
        )
    return parsed


def render_codex_mcp_servers(servers: list[McpServerSpec]) -> str:
    lines: list[str] = []
    for index, server in enumerate(servers):
        server.validate()
        if index:
            lines.append("")
        lines.append(f"[mcp_servers.{server.name}]")
        if server.transport is McpTransport.HTTP and server.url:
            lines.append(f"url = {_toml_value(server.url)}")
        if server.transport is McpTransport.STDIO and server.command:
            lines.append(f"command = {_toml_value(server.command)}")
        if server.args:
            lines.append(f"args = {_toml_value(list(server.args))}")
        if server.env_passthrough:
            lines.append(f"env_vars = {_toml_value(list(server.env_passthrough))}")
        if server.startup_timeout_sec is not None:
            lines.append(f"startup_timeout_sec = {server.startup_timeout_sec}")
        if server.tool_timeout_sec is not None:
            lines.append(f"tool_timeout_sec = {server.tool_timeout_sec}")
        if not server.enabled:
            lines.append("enabled = false")
        if server.env:
            lines.append("")
            lines.append(f"[mcp_servers.{server.name}.env]")
            for key, value in sorted(server.env.items()):
                lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines).strip()


def _format_block(block_name: str, body: str) -> str:
    normalized = _normalize_body(body)
    if normalized:
        return f"# {block_name}:start\n{normalized}\n# {block_name}:end"
    return f"# {block_name}:start\n# {block_name}:end"


def _normalize_body(body: str) -> str:
    return body.strip("\n").strip()


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Expected list value, got {type(value).__name__}")
    return [str(item) for item in value]


def _as_str_dict(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected dict value, got {type(value).__name__}")
    return {str(k): str(v) for k, v in value.items()}
