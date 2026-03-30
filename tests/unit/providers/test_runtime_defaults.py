from __future__ import annotations

import json
from pathlib import Path

from agent_profile_runtime.providers import ProviderBuildContext, ProviderKind, get_provider_adapter
from agent_profile_runtime.runtime import ProviderRuntime, RuntimeConfig
from agent_profile_runtime.runs import RunConfig
from agent_profile_runtime.sessions import SessionInitConfig


def _seed_fake_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("model = 'test'\n", encoding="utf-8")
    (home / ".codex" / "auth.json").write_text('{"token": "x"}\n', encoding="utf-8")
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"theme":"light"}\n', encoding="utf-8")
    (home / ".claude" / ".claude.json").write_text('{"projects":["demo"]}\n', encoding="utf-8")
    return home


def test_runtime_init_session_bootstraps_profiles_and_injects_managed_mcp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_fake_home(monkeypatch, tmp_path)
    runtime = ProviderRuntime(
        RuntimeConfig(
            base_dir=str(tmp_path / ".apr"),
            base_workdir=str(tmp_path),
            mcp_server_base_url="http://127.0.0.1:8000",
            toolkit_mcp_base_url="http://127.0.0.1:18080",
        )
    )
    try:
        session_default = runtime.init_session(
            SessionInitConfig(provider_kind=ProviderKind.CODEX, profile_name="default")
        )
        session_semantic = runtime.init_session(
            SessionInitConfig(provider_kind=ProviderKind.CODEX, profile_name="semantic")
        )
        session_claude = runtime.init_session(
            SessionInitConfig(provider_kind=ProviderKind.CLAUDE_CODE, profile_name="default")
        )

        codex_default = runtime.get_session(session_default)
        codex_semantic = runtime.get_session(session_semantic)
        claude_default = runtime.get_session(session_claude)

        assert codex_default.profile_dir.endswith("/profiles/codex/default")
        assert codex_semantic.profile_dir.endswith("/profiles/codex/semantic")
        assert claude_default.profile_dir.endswith("/profiles/claude_code/default")

        codex_default_cfg = (Path(codex_default.profile_dir) / "config.toml").read_text(encoding="utf-8")
        codex_semantic_cfg = (Path(codex_semantic.profile_dir) / "config.toml").read_text(encoding="utf-8")
        claude_default_mcp = json.loads(
            (Path(claude_default.profile_dir) / "mcp.json").read_text(encoding="utf-8")
        )

        assert "# base-config:start" in codex_default_cfg
        assert "# mcp-servers:start" in codex_default_cfg
        assert "http://127.0.0.1:8000/mcp/default/" in codex_default_cfg
        assert "http://127.0.0.1:8000/mcp/semantic/" in codex_semantic_cfg
        assert "http://127.0.0.1:18080/mcp/" in codex_default_cfg
        assert claude_default_mcp["mcpServers"]["lean_steward"]["url"] == "http://127.0.0.1:8000/mcp/default/"
        assert claude_default_mcp["mcpServers"]["lean_toolkit"]["url"] == "http://127.0.0.1:18080/mcp/"
    finally:
        runtime.close()


def test_claude_adapter_build_invocation_uses_strict_mcp_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_fake_home(monkeypatch, tmp_path)
    runtime = ProviderRuntime(
        RuntimeConfig(
            base_dir=str(tmp_path / ".apr"),
            base_workdir=str(tmp_path),
            mcp_server_base_url="http://127.0.0.1:8000",
        )
    )
    try:
        session_id = runtime.init_session(
            SessionInitConfig(provider_kind=ProviderKind.CLAUDE_CODE, profile_name="default")
        )
        session = runtime.get_session(session_id)
        adapter = get_provider_adapter(ProviderKind.CLAUDE_CODE)
        invocation = adapter.build_invocation(
            ProviderBuildContext(
                provider_kind=session.provider_kind,
                session_id=session.session_id,
                run_id="run-1",
                workdir=session.workdir,
                profile_name=session.profile_name,
                profile_dir=session.profile_dir,
                provider_session_id=session.provider_session_id,
                prompt_used="hello",
                output_mode="text",
                model=None,
                additional_dirs=(),
                merged_env={},
            )
        )

        assert "--strict-mcp-config" in invocation.command
        assert "--mcp-config" in invocation.command
        assert invocation.env["CLAUDE_CONFIG_DIR"] == session.profile_dir
        assert str(Path(session.profile_dir) / "mcp.json") in invocation.command
    finally:
        runtime.close()
