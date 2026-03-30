from __future__ import annotations

import json

import pytest

from agent_profile_runtime.mcp import McpServerSpec, McpTransport
from agent_profile_runtime.profiles.manager import ProfileManager
from agent_profile_runtime.providers import ProviderKind


def test_create_and_load_codex_profile(tmp_path):
    manager = ProfileManager(tmp_path / "profiles")
    profile = manager.create_profile(
        kind=ProviderKind.CODEX,
        name="default",
        base_config_text='model = "gpt-5.4"\napproval_policy = "never"\n',
        auth_payload={"access_token": "secret"},
        mcp_servers=[
            McpServerSpec(
                name="lean_steward",
                transport=McpTransport.HTTP,
                url="http://127.0.0.1:8000/mcp/default/",
            ),
            McpServerSpec(
                name="local_stdio",
                transport=McpTransport.STDIO,
                command="python",
                args=("-m", "server"),
                env={"ENV_A": "1"},
                env_passthrough=("HOME",),
            ),
        ],
    )

    config_text = (profile.profile_dir / "config.toml").read_text(encoding="utf-8")
    assert "# base-config:start" in config_text
    assert "# mcp-servers:start" in config_text

    loaded = manager.load_profile(kind=ProviderKind.CODEX, name="default")
    assert loaded.base_config_text.strip() == 'model = "gpt-5.4"\napproval_policy = "never"'
    assert loaded.auth_payload == {"access_token": "secret"}
    assert loaded.mcp_servers == profile.mcp_servers


def test_create_and_load_claude_code_profile(tmp_path):
    manager = ProfileManager(tmp_path / "profiles")
    manager.create_profile(
        kind=ProviderKind.CLAUDE_CODE,
        name="reviewer",
        settings_payload={"theme": "light", "model": "sonnet"},
        claude_state_payload={"projects": ["demo"]},
        mcp_servers=[
            McpServerSpec(
                name="lean_toolkit",
                transport=McpTransport.HTTP,
                url="http://127.0.0.1:18080/mcp/",
            )
        ],
    )

    loaded = manager.load_profile(kind=ProviderKind.CLAUDE_CODE, name="reviewer")
    assert loaded.settings_payload == {"theme": "light", "model": "sonnet"}
    assert loaded.claude_state_payload == {"projects": ["demo"]}
    assert loaded.mcp_servers == [
        McpServerSpec(
            name="lean_toolkit",
            transport=McpTransport.HTTP,
            url="http://127.0.0.1:18080/mcp/",
        )
    ]

    mcp_payload = json.loads((loaded.profile_dir / "mcp.json").read_text(encoding="utf-8"))
    assert mcp_payload["mcpServers"]["lean_toolkit"]["type"] == "http"


def test_profile_manager_list_copy_and_delete(tmp_path):
    manager = ProfileManager(tmp_path / "profiles")
    manager.create_profile(
        kind=ProviderKind.CODEX,
        name="default",
        base_config_text='model = "gpt-5.4"\n',
    )
    manager.create_profile(
        kind=ProviderKind.CLAUDE_CODE,
        name="planner",
        settings_payload={"model": "sonnet"},
    )

    listed = manager.list_profiles()
    assert [(item.kind.value, item.name) for item in listed] == [
        ("claude_code", "planner"),
        ("codex", "default"),
    ]

    copied = manager.copy_profile(
        src_kind=ProviderKind.CODEX,
        src_name="default",
        dst_name="semantic",
    )
    assert copied.name == "semantic"
    assert copied.meta.name == "semantic"
    assert manager.load_profile(kind=ProviderKind.CODEX, name="semantic").name == "semantic"

    manager.delete_profile(kind=ProviderKind.CLAUDE_CODE, name="planner")
    assert [(item.kind.value, item.name) for item in manager.list_profiles()] == [
        ("codex", "default"),
        ("codex", "semantic"),
    ]

    with pytest.raises(ValueError):
        manager.copy_profile(
            src_kind=ProviderKind.CODEX,
            src_name="default",
            dst_name="planner",
            dst_kind=ProviderKind.CLAUDE_CODE,
        )


def test_create_profile_from_source_home(tmp_path):
    manager = ProfileManager(tmp_path / "profiles")

    codex_source = tmp_path / "codex_source"
    codex_source.mkdir()
    (codex_source / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")
    (codex_source / "auth.json").write_text('{"token":"abc"}\n', encoding="utf-8")

    created_codex = manager.create_profile(
        kind=ProviderKind.CODEX,
        name="from_source",
        source_home=codex_source,
    )
    assert created_codex.auth_payload == {"token": "abc"}

    claude_source = tmp_path / "claude_source"
    claude_source.mkdir()
    (claude_source / "settings.json").write_text('{"model":"sonnet"}\n', encoding="utf-8")
    (claude_source / ".claude.json").write_text('{"projects":["x"]}\n', encoding="utf-8")

    created_claude = manager.create_profile(
        kind=ProviderKind.CLAUDE_CODE,
        name="from_source",
        source_home=claude_source,
    )
    assert created_claude.settings_payload == {"model": "sonnet"}
    assert created_claude.claude_state_payload == {"projects": ["x"]}
