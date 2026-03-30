from __future__ import annotations

import os
import stat
from pathlib import Path

from agent_profile_runtime.providers import ProviderKind
from agent_profile_runtime.runtime import ProviderRuntime, RuntimeConfig
from agent_profile_runtime.runs import RunConfig
from agent_profile_runtime.sessions import SessionInitConfig


def _seed_fake_home(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("model = 'test'\n", encoding="utf-8")
    (home / ".codex" / "auth.json").write_text('{"token":"x"}\n', encoding="utf-8")


def _install_fake_binary(tmp_path: Path, monkeypatch, *, name: str, script: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")


def test_stream_run_events_replays_and_follows_live_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_fake_home(monkeypatch, tmp_path)
    _install_fake_binary(
        tmp_path,
        monkeypatch,
        name="codex",
        script="""#!/usr/bin/env python3
import json, time
print(json.dumps({"type":"thread.started","thread_id":"thread-stream"}), flush=True)
time.sleep(0.2)
print(json.dumps({"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"hello events"}}), flush=True)
time.sleep(0.2)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}), flush=True)
""",
    )
    runtime = ProviderRuntime(RuntimeConfig(base_dir=str(tmp_path / ".apr"), base_workdir=str(tmp_path)))
    try:
        session_id = runtime.init_session(SessionInitConfig(provider_kind=ProviderKind.CODEX))
        run_id = runtime.submit_run(session_id, RunConfig(prompt="hello"))
        events = list(runtime.stream_run_events(run_id, from_seq=0, follow=True, idle_timeout_s=5.0))
        result = runtime.wait_run(run_id, timeout_s=5.0)

        event_types = [event.type for event in events]
        assert "run_queued" in event_types
        assert "run_started" in event_types
        assert "session_established" in event_types
        assert "message_final" in event_types
        assert "usage" in event_types
        assert "run_finished" in event_types
        assert result.final_text == "hello events"
    finally:
        runtime.close()


def test_stream_run_events_can_replay_after_completion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_fake_home(monkeypatch, tmp_path)
    _install_fake_binary(
        tmp_path,
        monkeypatch,
        name="codex",
        script="""#!/usr/bin/env python3
import json
print(json.dumps({"type":"thread.started","thread_id":"thread-replay"}), flush=True)
print(json.dumps({"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"done"}}), flush=True)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":4}}), flush=True)
""",
    )
    runtime = ProviderRuntime(RuntimeConfig(base_dir=str(tmp_path / ".apr"), base_workdir=str(tmp_path)))
    try:
        session_id = runtime.init_session(SessionInitConfig(provider_kind=ProviderKind.CODEX))
        run_id = runtime.submit_run(session_id, RunConfig(prompt="hello replay"))
        runtime.wait_run(run_id, timeout_s=5.0)

        replayed = list(runtime.stream_run_events(run_id, from_seq=0, follow=False))
        event_types = [event.type for event in replayed]
        assert event_types[0] == "run_queued"
        assert "message_final" in event_types
        assert event_types[-1] == "run_finished"
    finally:
        runtime.close()
