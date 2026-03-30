from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

from agent_profile_runtime.providers import ProviderKind
from agent_profile_runtime.runs import RunConfig
from agent_profile_runtime.runs.artifacts import ArtifactStore
from agent_profile_runtime.runs.executor import execute_run
from agent_profile_runtime.runtime import ProviderRuntime, RuntimeConfig
from agent_profile_runtime.sessions import SessionInitConfig


def _seed_fake_home(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("model = 'test'\n", encoding="utf-8")
    (home / ".codex" / "auth.json").write_text('{"token":"x"}\n', encoding="utf-8")


def _install_fake_binary(tmp_path: Path, monkeypatch, *, name: str, script: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return path


def test_artifact_store_tail_and_offset_readers(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "runtime")
    relpath = "sessions/s_test/runs/r_000001_test/stdout.log"
    store.write_text_file(relpath, "line1\nline2\nline3\n")
    assert store.tail_text_file(relpath, lines=2) == "line2\nline3\n"
    chunk1, offset1 = store.read_text_file_from_offset(relpath, offset=0, max_bytes=6)
    assert chunk1 == "line1\n"
    chunk2, offset2 = store.read_text_file_lines_from_offset(relpath, offset=offset1, max_bytes=1024)
    assert chunk2 == "line2\nline3\n"
    assert offset2 == len("line1\nline2\nline3\n".encode("utf-8"))


def test_runtime_executes_codex_run_and_writes_incremental_artifacts(
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
print(json.dumps({"type":"thread.started","thread_id":"thread-test"}), flush=True)
time.sleep(0.3)
print(json.dumps({"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"hello world"}}), flush=True)
time.sleep(0.3)
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":5}}), flush=True)
""",
    )
    runtime = ProviderRuntime(
        RuntimeConfig(
            base_dir=str(tmp_path / ".apr"),
            base_workdir=str(tmp_path),
        )
    )
    try:
        session_id = runtime.init_session(SessionInitConfig(provider_kind=ProviderKind.CODEX))
        run_id = runtime.submit_run(session_id, RunConfig(prompt="stream me"))
        record = runtime.list_runs(session_id=session_id)[0]
        stdout_path = Path(runtime.config.runtime_dir) / f"sessions/s_{session_id}/runs/r_{record.seq:06d}_{run_id}/stdout.log"
        normalized_path = Path(runtime.config.runtime_dir) / f"sessions/s_{session_id}/runs/r_{record.seq:06d}_{run_id}/events.normalized.jsonl"

        deadline = time.time() + 3.0
        saw_partial = False
        while time.time() < deadline:
            if stdout_path.exists():
                text = stdout_path.read_text(encoding="utf-8")
                if "thread.started" in text and "turn.completed" not in text:
                    saw_partial = True
                    break
            time.sleep(0.05)

        result = runtime.wait_run(run_id, timeout_s=5.0)
        assert saw_partial is True
        assert result.ok is True
        assert result.status == "succeeded"
        assert result.provider_session_id == "thread-test"
        assert result.final_text == "hello world"
        assert result.usage is not None
        assert result.usage.input_tokens == 3
        assert result.usage.output_tokens == 5
        assert "message_final" in normalized_path.read_text(encoding="utf-8")
    finally:
        runtime.close()


def test_execute_run_timeout_keeps_partial_output(
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
print(json.dumps({"type":"thread.started","thread_id":"thread-timeout"}), flush=True)
time.sleep(2.5)
""",
    )
    runtime = ProviderRuntime(
        RuntimeConfig(
            base_dir=str(tmp_path / ".apr"),
            base_workdir=str(tmp_path),
        )
    )
    try:
        session_id = runtime.init_session(SessionInitConfig(provider_kind=ProviderKind.CODEX))
        run_id = runtime.submit_run(session_id, RunConfig(prompt="timeout", timeout_s=1))
        record = runtime.list_runs(session_id=session_id)[0]
        stdout_path = Path(runtime.config.runtime_dir) / f"sessions/s_{session_id}/runs/r_{record.seq:06d}_{run_id}/stdout.log"
        result = runtime.wait_run(run_id, timeout_s=5.0)
        assert result.ok is False
        assert result.status == "timeout"
        assert result.error is not None
        assert result.error.code == "timeout"
        assert "thread.started" in stdout_path.read_text(encoding="utf-8")
    finally:
        runtime.close()
