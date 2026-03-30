from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .kinds import ProviderKind

OutputMode = Literal["text", "event_stream"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "timeout", "cancelled"]
PromptSource = Literal["user", "default_hello", "default_continue"]


@dataclass(slots=True, frozen=True)
class UsageInfo:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    total_cost_usd: float | None = None


@dataclass(slots=True, frozen=True)
class RunError:
    code: str
    message: str
    retryable: bool = False


@dataclass(slots=True, frozen=True)
class ProviderBuildContext:
    provider_kind: ProviderKind
    session_id: str
    run_id: str
    workdir: str
    profile_name: str
    profile_dir: str
    provider_session_id: str | None
    prompt_used: str
    output_mode: OutputMode
    model: str | None
    additional_dirs: tuple[str, ...]
    merged_env: dict[str, str]


@dataclass(slots=True, frozen=True)
class ProviderInvocation:
    provider_kind: ProviderKind
    session_id: str
    run_id: str
    cwd: str
    command: tuple[str, ...]
    env: dict[str, str]
    config_home: str
    provider_session_id: str | None
    output_mode: OutputMode


@dataclass(slots=True, frozen=True)
class ProviderParseContext:
    provider_kind: ProviderKind
    run_id: str
    session_id: str
    output_mode: OutputMode
    stdout_text: str
    stderr_text: str


@dataclass(slots=True, frozen=True)
class ProviderParsedOutput:
    provider_session_id: str | None
    final_text: str | None
    usage: UsageInfo | None
    error: RunError | None
    raw_event_lines: tuple[str, ...] = field(default_factory=tuple)

