from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class McpTransport(StrEnum):
    HTTP = "http"
    STDIO = "stdio"


@dataclass(slots=True, frozen=True)
class McpServerSpec:
    name: str
    transport: McpTransport
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: tuple[str, ...] = ()
    startup_timeout_sec: int | None = None
    tool_timeout_sec: int | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env_passthrough", tuple(self.env_passthrough))
        self.validate()

    def validate(self) -> None:
        if not self.name:
            raise ValueError("MCP server name must not be empty")
        if self.transport is McpTransport.HTTP:
            if not self.url:
                raise ValueError(f"HTTP MCP server {self.name!r} requires url")
            if self.command:
                raise ValueError(f"HTTP MCP server {self.name!r} must not set command")
        elif self.transport is McpTransport.STDIO:
            if not self.command:
                raise ValueError(f"STDIO MCP server {self.name!r} requires command")
            if self.url:
                raise ValueError(f"STDIO MCP server {self.name!r} must not set url")

    def to_claude_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.transport.value,
            "enabled": self.enabled,
        }
        if self.transport is McpTransport.HTTP and self.url:
            payload["url"] = self.url
        if self.transport is McpTransport.STDIO and self.command:
            payload["command"] = self.command
        if self.args:
            payload["args"] = list(self.args)
        if self.env:
            payload["env"] = dict(self.env)
        if self.env_passthrough:
            payload["env_passthrough"] = list(self.env_passthrough)
        if self.startup_timeout_sec is not None:
            payload["startup_timeout_sec"] = self.startup_timeout_sec
        if self.tool_timeout_sec is not None:
            payload["tool_timeout_sec"] = self.tool_timeout_sec
        return payload

    @classmethod
    def from_claude_dict(cls, name: str, payload: dict[str, object]) -> "McpServerSpec":
        transport = McpTransport(str(payload.get("type") or "http"))
        return cls(
            name=name,
            transport=transport,
            url=_as_optional_str(payload.get("url")),
            command=_as_optional_str(payload.get("command")),
            args=tuple(_as_str_list(payload.get("args"))),
            env=_as_str_dict(payload.get("env")),
            env_passthrough=tuple(_as_str_list(payload.get("env_passthrough"))),
            startup_timeout_sec=_as_optional_int(payload.get("startup_timeout_sec")),
            tool_timeout_sec=_as_optional_int(payload.get("tool_timeout_sec")),
            enabled=bool(payload.get("enabled", True)),
        )


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
