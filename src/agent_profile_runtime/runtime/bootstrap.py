from __future__ import annotations

from pathlib import Path

from agent_profile_runtime.mcp import McpServerSpec, McpTransport
from agent_profile_runtime.profiles.manager import ProfileManager
from agent_profile_runtime.providers import ProviderKind

from .config import RuntimeConfig


def bootstrap_runtime(config: RuntimeConfig) -> None:
    Path(config.base_dir).mkdir(parents=True, exist_ok=True)
    Path(config.runtime_dir).mkdir(parents=True, exist_ok=True)
    Path(config.profiles_root).mkdir(parents=True, exist_ok=True)


def bootstrap_profile(
    *,
    config: RuntimeConfig,
    profile_manager: ProfileManager,
    provider_kind: ProviderKind,
    profile_name: str,
    overwrite: bool = False,
) -> None:
    source_home = _resolve_source_home(config, provider_kind)
    kwargs = {"source_home": source_home, "mcp_servers": _managed_mcp_servers(config, profile_name)}
    if provider_kind is ProviderKind.CODEX:
        profile_manager.create_profile(
            kind=provider_kind,
            name=profile_name,
            overwrite=overwrite,
            **kwargs,
        )
    else:
        profile_manager.create_profile(
            kind=provider_kind,
            name=profile_name,
            overwrite=overwrite,
            **kwargs,
        )


def ensure_profile_exists(
    *,
    config: RuntimeConfig,
    profile_manager: ProfileManager,
    provider_kind: ProviderKind,
    profile_name: str,
) -> None:
    try:
        profile_manager.load_profile(kind=provider_kind, name=profile_name)
    except Exception:
        bootstrap_profile(
            config=config,
            profile_manager=profile_manager,
            provider_kind=provider_kind,
            profile_name=profile_name,
        )


def _resolve_source_home(config: RuntimeConfig, provider_kind: ProviderKind) -> Path:
    if provider_kind is ProviderKind.CODEX:
        return Path(config.codex_source_home or Path.home() / ".codex").expanduser().resolve()
    return Path(config.claude_code_source_home or Path.home() / ".claude").expanduser().resolve()


def _managed_mcp_servers(config: RuntimeConfig, profile_name: str) -> list[McpServerSpec]:
    servers: list[McpServerSpec] = []
    if config.mcp_server_base_url:
        endpoint = _profile_to_endpoint_path(profile_name)
        servers.append(
            McpServerSpec(
                name="lean_steward",
                transport=McpTransport.HTTP,
                url=f"{config.mcp_server_base_url}{endpoint}",
            )
        )
    if config.toolkit_mcp_base_url:
        servers.append(
            McpServerSpec(
                name="lean_toolkit",
                transport=McpTransport.HTTP,
                url=f"{config.toolkit_mcp_base_url}/mcp/",
            )
        )
    return servers


def _profile_to_endpoint_path(profile_name: str) -> str:
    if profile_name == "semantic":
        return "/mcp/semantic/"
    return "/mcp/default/"

