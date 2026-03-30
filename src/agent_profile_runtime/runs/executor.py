from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent_profile_runtime.providers.base import BaseProviderAdapter
from agent_profile_runtime.providers.models import ProviderBuildContext, ProviderInvocation, ProviderParseContext
from agent_profile_runtime.sessions.models import SessionRecord
from agent_profile_runtime.sessions.store import utc_now_iso

from .artifacts import ArtifactStore, RunArtifactLayout
from .event_normalizer import normalize_provider_stderr_line, normalize_provider_stdout_line, normalize_runtime_event
from .models import ProviderEvent, RunConfig, RunEffectiveConfig, RunResult
from .parser import build_run_result


def resolve_prompt(raw_prompt: str, *, has_provider_session: bool) -> tuple[str, str]:
    prompt = (raw_prompt or "").strip()
    if prompt:
        return prompt, "user"
    if not has_provider_session:
        return "hello", "default_hello"
    return "continue", "default_continue"


@dataclass(slots=True)
class RunExecutionResult:
    run_result: RunResult
    provider_session_id: str | None
    invocation: ProviderInvocation
    effective_config: RunEffectiveConfig
    normalized_events: list[ProviderEvent]


def execute_run(
    *,
    artifact_store: ArtifactStore,
    session: SessionRecord,
    run_id: str,
    run_config: RunConfig,
    run_seq: int,
    provider_adapter: BaseProviderAdapter,
    publish_event: Callable[[ProviderEvent], None] | None = None,
    write_session_instructions: Callable[[str, str, str], str] | None = None,
) -> RunExecutionResult:
    prompt_used, prompt_source = resolve_prompt(
        run_config.prompt,
        has_provider_session=bool(session.provider_session_id),
    )
    effective_model = run_config.model or session.model
    effective_additional_dirs = (
        tuple(run_config.additional_dirs)
        if run_config.additional_dirs is not None
        else tuple(session.additional_dirs)
    )
    base_env = dict(session.env)
    if run_config.env:
        base_env.update(dict(run_config.env))
    effective_env = tuple(sorted(base_env.items()))
    effective = RunEffectiveConfig(
        prompt_used=prompt_used,
        prompt_source=prompt_source,  # type: ignore[arg-type]
        output_mode=run_config.output_mode,
        timeout_s=run_config.timeout_s,
        model=effective_model,
        additional_dirs=effective_additional_dirs,
        env=effective_env,
        instructions_override_applied=run_config.instructions_file_content is not None,
    )

    if run_config.instructions_file_content is not None and write_session_instructions is not None:
        write_session_instructions(
            session.workdir,
            provider_adapter.instructions_filename(),
            run_config.instructions_file_content,
        )

    build_ctx = ProviderBuildContext(
        provider_kind=session.provider_kind,
        session_id=session.session_id,
        run_id=run_id,
        workdir=session.workdir,
        profile_name=session.profile_name,
        profile_dir=session.profile_dir,
        provider_session_id=session.provider_session_id,
        prompt_used=prompt_used,
        output_mode=run_config.output_mode,
        model=effective_model,
        additional_dirs=effective_additional_dirs,
        merged_env=base_env,
    )
    invocation = provider_adapter.build_invocation(build_ctx)

    layout = RunArtifactLayout(
        **build_run_artifact_layout_kwargs(
            artifact_store=artifact_store,
            session_id=session.session_id,
            run_seq=run_seq,
            run_id=run_id,
        )
    )
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    artifact_store.write_json_file(
        layout.request_relpath,
        {
            "prompt": run_config.prompt,
            "output_mode": run_config.output_mode,
            "timeout_s": run_config.timeout_s,
            "model": run_config.model,
            "additional_dirs": list(run_config.additional_dirs) if run_config.additional_dirs is not None else None,
            "env_keys": sorted(dict(run_config.env).keys()) if run_config.env else None,
            "instructions_override_supplied": run_config.instructions_file_content is not None,
        },
    )
    artifact_store.write_json_file(
        layout.effective_relpath,
        {
            "provider_kind": session.provider_kind.value,
            "workdir": session.workdir,
            "profile_name": session.profile_name,
            "profile_dir": session.profile_dir,
            **effective.to_dict(),
        },
    )
    artifact_store.write_json_file(
        layout.command_relpath,
        {
            "command": list(invocation.command),
            "cwd": invocation.cwd,
            "env_keys": sorted(invocation.env.keys()),
        },
    )
    artifact_store.write_text_file(layout.stdout_relpath, "")
    artifact_store.write_text_file(layout.stderr_relpath, "")
    artifact_store.write_text_file(layout.events_raw_relpath, "")
    if not artifact_store.abspath(layout.events_normalized_relpath).exists():
        artifact_store.write_text_file(layout.events_normalized_relpath, "")

    normalized_events: list[ProviderEvent] = []
    next_seq = 1
    seq_lock = threading.RLock()

    def _emit(event: ProviderEvent) -> None:
        nonlocal next_seq
        with seq_lock:
            artifact_store.append_event(layout.events_normalized_relpath, event)
            normalized_events.append(event)
            next_seq = max(next_seq, event.seq + 1)
        if publish_event is not None:
            publish_event(event)

    queued_event = normalize_runtime_event(
        run_id=run_id,
        session_id=session.session_id,
        provider_kind=session.provider_kind,
        seq=next_seq,
        event_type="run_started",
        payload={},
    )
    _emit(queued_event)

    started_at = utc_now_iso()
    start_dt = datetime.now(timezone.utc)
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    def _consume_stdout(stream) -> None:
        for line in iter(stream.readline, ""):
            if not line:
                break
            stdout_parts.append(line)
            artifact_store.append_text_file(layout.stdout_relpath, line)
            artifact_store.append_text_file(layout.events_raw_relpath, line)
            if line.strip():
                with seq_lock:
                    seq_start = next_seq
                for event in normalize_provider_stdout_line(
                    run_id=run_id,
                    session_id=session.session_id,
                    provider_kind=session.provider_kind,
                    seq_start=seq_start,
                    line=line.strip(),
                ):
                    _emit(event)
        stream.close()

    def _consume_stderr(stream) -> None:
        for line in iter(stream.readline, ""):
            if not line:
                break
            stderr_parts.append(line)
            artifact_store.append_text_file(layout.stderr_relpath, line)
            if line.strip():
                with seq_lock:
                    seq_start = next_seq
                for event in normalize_provider_stderr_line(
                    run_id=run_id,
                    session_id=session.session_id,
                    provider_kind=session.provider_kind,
                    seq_start=seq_start,
                    line=line,
                ):
                    _emit(event)
        stream.close()

    process = subprocess.Popen(
        list(invocation.command),
        cwd=invocation.cwd,
        env=invocation.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(target=_consume_stdout, args=(process.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=_consume_stderr, args=(process.stderr,), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    try:
        provider_exit_code = process.wait(timeout=run_config.timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        process.kill()
        provider_exit_code = None
        timed_out = True
    stdout_thread.join()
    stderr_thread.join()

    parse_ctx = ProviderParseContext(
        provider_kind=session.provider_kind,
        run_id=run_id,
        session_id=session.session_id,
        output_mode=run_config.output_mode,
        stdout_text="".join(stdout_parts),
        stderr_text="".join(stderr_parts),
    )
    parsed = provider_adapter.parse_output(parse_ctx)
    finished_at = utc_now_iso()
    duration_ms = int((datetime.now(timezone.utc) - start_dt).total_seconds() * 1000)

    result = build_run_result(
        run_id=run_id,
        session_id=session.session_id,
        provider_kind=session.provider_kind,
        provider_invocation=invocation,
        effective_config=effective,
        parsed_output=parsed,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        provider_exit_code=provider_exit_code,
        artifacts={
            "request_relpath": layout.request_relpath,
            "effective_relpath": layout.effective_relpath,
            "command_relpath": layout.command_relpath,
            "stdout_relpath": layout.stdout_relpath,
            "stderr_relpath": layout.stderr_relpath,
            "events_raw_relpath": layout.events_raw_relpath,
            "events_normalized_relpath": layout.events_normalized_relpath,
            "result_relpath": layout.result_relpath,
        },
    )
    if timed_out:
        from agent_profile_runtime.providers.models import RunError

        result = RunResult(
            ok=False,
            status="timeout",
            run_id=result.run_id,
            session_id=result.session_id,
            provider_kind=result.provider_kind,
            provider_session_id=result.provider_session_id,
            prompt_used=result.prompt_used,
            prompt_source=result.prompt_source,
            output_mode=result.output_mode,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_ms=result.duration_ms,
            final_text=result.final_text,
            usage=result.usage,
            error=RunError(code="timeout", message="provider run timed out", retryable=True),
            provider_exit_code=result.provider_exit_code,
            artifacts=result.artifacts,
            effective=result.effective,
        )

    final_event = normalize_runtime_event(
        run_id=run_id,
        session_id=session.session_id,
        provider_kind=session.provider_kind,
        seq=next_seq,
        event_type="run_finished",
        payload={"status": result.status, "ok": result.ok},
    )
    _emit(final_event)
    artifact_store.write_json_file(layout.result_relpath, result.to_dict())
    return RunExecutionResult(
        run_result=result,
        provider_session_id=parsed.provider_session_id,
        invocation=invocation,
        effective_config=effective,
        normalized_events=normalized_events,
    )


def build_run_artifact_layout_kwargs(*, artifact_store: ArtifactStore, session_id: str, run_seq: int, run_id: str) -> dict[str, object]:
    rel_run_dir = f"sessions/s_{session_id}/runs/r_{run_seq:06d}_{run_id}"
    run_dir = artifact_store.runtime_dir / rel_run_dir
    return {
        "run_dir": run_dir,
        "request_relpath": f"{rel_run_dir}/run.request.json",
        "effective_relpath": f"{rel_run_dir}/run.effective.json",
        "command_relpath": f"{rel_run_dir}/provider.command.json",
        "stdout_relpath": f"{rel_run_dir}/stdout.log",
        "stderr_relpath": f"{rel_run_dir}/stderr.log",
        "events_raw_relpath": f"{rel_run_dir}/events.raw.jsonl",
        "events_normalized_relpath": f"{rel_run_dir}/events.normalized.jsonl",
        "result_relpath": f"{rel_run_dir}/result.json",
        "record_relpath": f"{rel_run_dir}/run.record.json",
    }
