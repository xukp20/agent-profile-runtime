from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal

from agent_profile_runtime.providers.models import (
    OutputMode,
    PromptSource,
    RunError,
    RunStatus,
    UsageInfo,
)
from agent_profile_runtime.providers import ProviderKind

ProviderEventType = Literal[
    "run_queued",
    "run_started",
    "session_established",
    "message_delta",
    "message_final",
    "thinking_delta",
    "tool_call_started",
    "tool_call_completed",
    "usage",
    "error",
    "run_finished",
    "raw_provider_event",
]
ProviderEventSource = Literal["runtime", "provider_stdout", "provider_stderr", "provider_parser"]


@dataclass(slots=True, frozen=True)
class RunConfig:
    prompt: str = ""
    output_mode: OutputMode = "text"
    timeout_s: int | None = None
    model: str | None = None
    additional_dirs: tuple[str, ...] | None = None
    env: tuple[tuple[str, str], ...] | None = None
    instructions_file_content: str | None = None


@dataclass(slots=True, frozen=True)
class RunEffectiveConfig:
    prompt_used: str
    prompt_source: PromptSource
    output_mode: OutputMode
    timeout_s: int | None
    model: str | None
    additional_dirs: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    instructions_override_applied: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "prompt_used": self.prompt_used,
            "prompt_source": self.prompt_source,
            "output_mode": self.output_mode,
            "timeout_s": self.timeout_s,
            "model": self.model,
            "additional_dirs": list(self.additional_dirs),
            "env_keys": sorted(key for key, _ in self.env),
            "instructions_override_applied": self.instructions_override_applied,
        }


@dataclass(slots=True, frozen=True)
class ProviderEvent:
    event_id: str
    run_id: str
    session_id: str
    provider_kind: ProviderKind
    seq: int
    created_at: str
    type: ProviderEventType
    source: ProviderEventSource
    payload: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["provider_kind"] = self.provider_kind.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProviderEvent":
        return cls(
            event_id=str(data["event_id"]),
            run_id=str(data["run_id"]),
            session_id=str(data["session_id"]),
            provider_kind=ProviderKind.from_value(str(data["provider_kind"])),
            seq=int(data["seq"]),
            created_at=str(data["created_at"]),
            type=str(data["type"]),  # type: ignore[arg-type]
            source=str(data["source"]),  # type: ignore[arg-type]
            payload=dict(data.get("payload") or {}),
        )

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"


@dataclass(slots=True)
class RunRecord:
    run_id: str
    session_id: str
    seq: int
    priority: int
    queue_seq: int
    status: RunStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    run_config: RunConfig
    effective: RunEffectiveConfig | None = None
    request_relpath: str | None = None
    effective_relpath: str | None = None
    command_relpath: str | None = None
    stdout_relpath: str | None = None
    stderr_relpath: str | None = None
    events_raw_relpath: str | None = None
    events_normalized_relpath: str | None = None
    result_relpath: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "seq": self.seq,
            "priority": self.priority,
            "queue_seq": self.queue_seq,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
            "run_config": {
                "prompt": self.run_config.prompt,
                "output_mode": self.run_config.output_mode,
                "timeout_s": self.run_config.timeout_s,
                "model": self.run_config.model,
                "additional_dirs": list(self.run_config.additional_dirs) if self.run_config.additional_dirs is not None else None,
                "env": [[k, v] for k, v in self.run_config.env] if self.run_config.env is not None else None,
                "instructions_file_content": self.run_config.instructions_file_content,
            },
            "effective": self.effective.to_dict() if self.effective else None,
            "request_relpath": self.request_relpath,
            "effective_relpath": self.effective_relpath,
            "command_relpath": self.command_relpath,
            "stdout_relpath": self.stdout_relpath,
            "stderr_relpath": self.stderr_relpath,
            "events_raw_relpath": self.events_raw_relpath,
            "events_normalized_relpath": self.events_normalized_relpath,
            "result_relpath": self.result_relpath,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RunRecord":
        run_config_data = dict(data["run_config"])
        effective_data = data.get("effective")
        effective = None
        if isinstance(effective_data, dict):
            effective = RunEffectiveConfig(
                prompt_used=str(effective_data["prompt_used"]),
                prompt_source=str(effective_data["prompt_source"]),  # type: ignore[arg-type]
                output_mode=str(effective_data["output_mode"]),  # type: ignore[arg-type]
                timeout_s=int(effective_data["timeout_s"]) if effective_data.get("timeout_s") is not None else None,
                model=str(effective_data["model"]) if effective_data.get("model") is not None else None,
                additional_dirs=tuple(str(item) for item in (effective_data.get("additional_dirs") or [])),
                env=tuple(),
                instructions_override_applied=bool(effective_data.get("instructions_override_applied", False)),
            )
        run_config = RunConfig(
            prompt=str(run_config_data.get("prompt") or ""),
            output_mode=str(run_config_data.get("output_mode") or "text"),  # type: ignore[arg-type]
            timeout_s=int(run_config_data["timeout_s"]) if run_config_data.get("timeout_s") is not None else None,
            model=str(run_config_data["model"]) if run_config_data.get("model") is not None else None,
            additional_dirs=tuple(str(item) for item in (run_config_data.get("additional_dirs") or []))
            if run_config_data.get("additional_dirs") is not None
            else None,
            env=tuple((str(k), str(v)) for k, v in (run_config_data.get("env") or []))
            if run_config_data.get("env") is not None
            else None,
            instructions_file_content=str(run_config_data["instructions_file_content"])
            if run_config_data.get("instructions_file_content") is not None
            else None,
        )
        return cls(
            run_id=str(data["run_id"]),
            session_id=str(data["session_id"]),
            seq=int(data["seq"]),
            priority=int(data["priority"]),
            queue_seq=int(data["queue_seq"]),
            status=str(data["status"]),  # type: ignore[arg-type]
            created_at=str(data["created_at"]),
            started_at=str(data["started_at"]) if data.get("started_at") else None,
            finished_at=str(data["finished_at"]) if data.get("finished_at") else None,
            error_message=str(data["error_message"]) if data.get("error_message") else None,
            run_config=run_config,
            effective=effective,
            request_relpath=str(data["request_relpath"]) if data.get("request_relpath") else None,
            effective_relpath=str(data["effective_relpath"]) if data.get("effective_relpath") else None,
            command_relpath=str(data["command_relpath"]) if data.get("command_relpath") else None,
            stdout_relpath=str(data["stdout_relpath"]) if data.get("stdout_relpath") else None,
            stderr_relpath=str(data["stderr_relpath"]) if data.get("stderr_relpath") else None,
            events_raw_relpath=str(data["events_raw_relpath"]) if data.get("events_raw_relpath") else None,
            events_normalized_relpath=str(data["events_normalized_relpath"]) if data.get("events_normalized_relpath") else None,
            result_relpath=str(data["result_relpath"]) if data.get("result_relpath") else None,
        )


@dataclass(slots=True, frozen=True)
class RunResult:
    ok: bool
    status: Literal["succeeded", "failed", "timeout", "cancelled"]
    run_id: str
    session_id: str
    provider_kind: ProviderKind
    provider_session_id: str
    prompt_used: str
    prompt_source: PromptSource
    output_mode: OutputMode
    started_at: str
    finished_at: str
    duration_ms: int
    final_text: str | None = None
    usage: UsageInfo | None = None
    error: RunError | None = None
    provider_exit_code: int | None = None
    artifacts: dict[str, str | None] = field(default_factory=dict)
    effective: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["provider_kind"] = self.provider_kind.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RunResult":
        usage_data = data.get("usage")
        error_data = data.get("error")
        return cls(
            ok=bool(data["ok"]),
            status=str(data["status"]),  # type: ignore[arg-type]
            run_id=str(data["run_id"]),
            session_id=str(data["session_id"]),
            provider_kind=ProviderKind.from_value(str(data["provider_kind"])),
            provider_session_id=str(data["provider_session_id"]),
            prompt_used=str(data["prompt_used"]),
            prompt_source=str(data["prompt_source"]),  # type: ignore[arg-type]
            output_mode=str(data["output_mode"]),  # type: ignore[arg-type]
            started_at=str(data["started_at"]),
            finished_at=str(data["finished_at"]),
            duration_ms=int(data["duration_ms"]),
            final_text=str(data["final_text"]) if data.get("final_text") is not None else None,
            usage=UsageInfo(**usage_data) if isinstance(usage_data, dict) else None,
            error=RunError(**error_data) if isinstance(error_data, dict) else None,
            provider_exit_code=int(data["provider_exit_code"]) if data.get("provider_exit_code") is not None else None,
            artifacts=dict(data.get("artifacts") or {}),
            effective=dict(data.get("effective") or {}),
        )

