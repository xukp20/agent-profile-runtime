from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .base import BaseProviderAdapter
from .kinds import ProviderKind
from .models import (
    ProviderBuildContext,
    ProviderInvocation,
    ProviderParseContext,
    ProviderParsedOutput,
    RunError,
    UsageInfo,
)


@dataclass(slots=True)
class CodexProviderAdapter(BaseProviderAdapter):
    kind: ProviderKind = ProviderKind.CODEX

    def instructions_filename(self) -> str:
        return "AGENTS.md"

    def build_invocation(self, ctx: ProviderBuildContext) -> ProviderInvocation:
        env = dict(os.environ)
        env.update(ctx.merged_env)
        env["CODEX_HOME"] = ctx.profile_dir

        command: list[str] = ["codex"]
        for directory in ctx.additional_dirs:
            command.extend(["--add-dir", directory])

        if ctx.provider_session_id:
            command.extend(["exec", "resume", "--skip-git-repo-check", "--json"])
            if ctx.model:
                command.extend(["-m", ctx.model])
            command.extend([ctx.provider_session_id, ctx.prompt_used])
        else:
            command.extend(["exec", "--skip-git-repo-check", "--json"])
            if ctx.model:
                command.extend(["-m", ctx.model])
            command.append(ctx.prompt_used)

        return ProviderInvocation(
            provider_kind=self.kind,
            session_id=ctx.session_id,
            run_id=ctx.run_id,
            cwd=ctx.workdir,
            command=tuple(command),
            env=env,
            config_home=ctx.profile_dir,
            provider_session_id=ctx.provider_session_id,
            output_mode=ctx.output_mode,
        )

    def parse_output(self, ctx: ProviderParseContext) -> ProviderParsedOutput:
        provider_session_id: str | None = None
        final_text: str | None = None
        usage: dict[str, object] | None = None
        error: RunError | None = None
        saw_turn_completed = False
        event_errors: list[str] = []
        raw_lines: list[str] = []

        for line in ctx.stdout_text.splitlines():
            if not line.strip():
                continue
            raw_lines.append(line)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = obj.get("type")
            if event_type == "thread.started":
                provider_session_id = _as_optional_str(obj.get("thread_id"))
            elif event_type == "item.completed":
                item = obj.get("item") or {}
                if item.get("type") == "agent_message":
                    final_text = _as_optional_str(item.get("text")) or final_text
            elif event_type == "turn.completed":
                usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else None
                saw_turn_completed = True
            elif event_type in {"turn.failed", "error"}:
                message = _as_optional_str(obj.get("message"))
                nested = obj.get("error")
                if not message and isinstance(nested, dict):
                    message = _as_optional_str(nested.get("message"))
                if message:
                    event_errors.append(message)

        stderr_lines = [line.strip() for line in ctx.stderr_text.splitlines() if line.strip()]
        candidate_messages = list(event_errors)
        candidate_messages.extend(stderr_lines)
        if saw_turn_completed:
            candidate_messages = [
                msg for msg in candidate_messages if not _is_ignorable_codex_transport_message(msg)
            ]
        if candidate_messages:
            error = RunError(
                code="provider_error",
                message="\n".join(candidate_messages),
                retryable=False,
            )

        return ProviderParsedOutput(
            provider_session_id=provider_session_id,
            final_text=final_text,
            usage=_parse_usage(usage),
            error=error,
            raw_event_lines=tuple(raw_lines),
        )


def _parse_usage(raw: dict[str, object] | None) -> UsageInfo | None:
    if raw is None:
        return None
    return UsageInfo(
        input_tokens=_as_optional_int(raw.get("input_tokens")),
        output_tokens=_as_optional_int(raw.get("output_tokens")),
        cached_input_tokens=_as_optional_int(raw.get("cached_input_tokens")),
        cache_creation_input_tokens=_as_optional_int(raw.get("cache_creation_input_tokens")),
        total_cost_usd=_as_optional_float(raw.get("total_cost_usd")),
    )


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_ignorable_codex_transport_message(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    ignorable_fragments = (
        "reconnecting...",
        "stream disconnected before completion",
        "failed to connect to websocket",
        "tls handshake eof",
    )
    return any(fragment in text for fragment in ignorable_fragments)

