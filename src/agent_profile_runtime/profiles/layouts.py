from __future__ import annotations

from pathlib import Path

from agent_profile_runtime.providers import ProviderKind

from .meta import PROFILE_META_FILENAME

CODEX_CONFIG_FILENAME = "config.toml"
CODEX_AUTH_FILENAME = "auth.json"
CLAUDE_SETTINGS_FILENAME = "settings.json"
CLAUDE_STATE_FILENAME = ".claude.json"
CLAUDE_MCP_FILENAME = "mcp.json"


def provider_profiles_root(profiles_root: Path, kind: ProviderKind) -> Path:
    return profiles_root / kind.value


def profile_dir(profiles_root: Path, kind: ProviderKind, name: str) -> Path:
    return provider_profiles_root(profiles_root, kind) / name


def profile_meta_path(profile_root: Path) -> Path:
    return profile_root / PROFILE_META_FILENAME


def codex_config_path(profile_root: Path) -> Path:
    return profile_root / CODEX_CONFIG_FILENAME


def codex_auth_path(profile_root: Path) -> Path:
    return profile_root / CODEX_AUTH_FILENAME


def claude_settings_path(profile_root: Path) -> Path:
    return profile_root / CLAUDE_SETTINGS_FILENAME


def claude_state_path(profile_root: Path) -> Path:
    return profile_root / CLAUDE_STATE_FILENAME


def claude_mcp_path(profile_root: Path) -> Path:
    return profile_root / CLAUDE_MCP_FILENAME
