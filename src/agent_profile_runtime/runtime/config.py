from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RuntimeConfig:
    base_dir: str
    base_workdir: str | None = None
    max_concurrency: int = 1
    default_profile_name: str = "default"
    codex_source_home: str | None = None
    claude_code_source_home: str | None = None
    mcp_server_base_url: str | None = None
    toolkit_mcp_base_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_dir", str(Path(self.base_dir).expanduser().resolve()))
        if self.base_workdir is not None:
            object.__setattr__(self, "base_workdir", str(Path(self.base_workdir).expanduser().resolve()))
        if self.codex_source_home is not None:
            object.__setattr__(self, "codex_source_home", str(Path(self.codex_source_home).expanduser().resolve()))
        if self.claude_code_source_home is not None:
            object.__setattr__(self, "claude_code_source_home", str(Path(self.claude_code_source_home).expanduser().resolve()))
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        if self.mcp_server_base_url is not None:
            object.__setattr__(self, "mcp_server_base_url", self.mcp_server_base_url.rstrip("/"))
        if self.toolkit_mcp_base_url is not None:
            object.__setattr__(self, "toolkit_mcp_base_url", self.toolkit_mcp_base_url.rstrip("/"))

    @property
    def runtime_dir(self) -> str:
        return str((Path(self.base_dir) / "runtime").resolve())

    @property
    def profiles_root(self) -> str:
        return str((Path(self.base_dir) / "profiles").resolve())

