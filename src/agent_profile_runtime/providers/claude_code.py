from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

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
class ClaudeCodeProviderAdapter(BaseProviderAdapter):
    kind: ProviderKind = ProviderKind.CLAUDE_CODE

    def instructions_filename(self) -> str:
        return "CLAUDE.md"

    def build_invocation(self, ctx: ProviderBuildContext) -> ProviderInvocation:
        env = dict(os.environ)
        env.update(ctx.merged_env)
        env["CLAUDE_CONFIG_DIR"] = ctx.profile_dir

        command: list[str] = ["claude", "-p"]
        mcp_path = Path(ctx.profile_dir) / "mcp.json"
        if mcp_path.exists():
            command.extend(["--mcp-config", str(mcp_path), "--strict-mcp-config"])
        for directory in ctx.additional_dirs:
            command.extend(["--add-dir", directory])
        if ctx.provider_session_id:
            command.extend(["--resume", ctx.provider_session_id])
        else:
            command.extend(["--session-id", ctx.session_id])
        if ctx.model:
            command.extend(["--model", ctx.model])
        if ctx.output_mode == "event_stream":
            command.extend(["--verbose", "--output-format", "stream-json"])
        else:
            command.extend(["--output-format", "json"])
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
        if ctx.output_mode == "event_stream":
            return _parse_stream_output(ctx.stdout_text, ctx.stderr_text)
        return _parse_json_output(ctx.stdout_text, ctx.stderr_text)


def _parse_json_output(stdout: str, stderr: str) -> ProviderParsedOutput:
    payload = _extract_last_json(stdout)
    error = None
    if payload is None:
        error = RunError(
            code="provider_error",
            message=stderr.strip() or "no json payload found in claude output",
            retryable=False,
        )
        return ProviderParsedOutput(
            provider_session_id=None,
            final_text=None,
            usage=None,
            error=error,
            raw_event_lines=tuple(line for line in stdout.splitlines() if line.strip()),
        )

    if bool(payload.get("is_error")):
        error = RunError(
            code="provider_error",
            message=str(payload.get("result") or "claude reported error"),
            retryable=False,
        )

    return ProviderParsedOutput(
        provider_session_id=_as_optional_str(payload.get("session_id")),
        final_text=_as_optional_str(payload.get("result")),
        usage=_parse_usage(payload.get("usage")),
        error=error,
        raw_event_lines=tuple(line for line in stdout.splitlines() if line.strip()),
    )


def _parse_stream_output(stdout: str, stderr: str) -> ProviderParsedOutput:
    provider_session_id: str | None = None
    final_text: str | None = None
    usage: dict[str, object] | None = None
    error: RunError | None = None
    raw_lines: list[str] = []

    for line in stdout.splitlines():
        if not line.strip():
            continue
        raw_lines.append(line)
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        ptype = payload.get("type")
        if ptype == "system":
            provider_session_id = _as_optional_str(payload.get("session_id")) or provider_session_id
        elif ptype == "assistant":
            message = payload.get("message") or {}
            content = message.get("content") or []
            text_parts: list[str] = []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = _as_optional_str(block.get("text"))
                        if text:
                            text_parts.append(text)
            if text_parts:
                final_text = "\n".join(text_parts)
        elif ptype == "result":
            provider_session_id = _as_optional_str(payload.get("session_id")) or provider_session_id
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
            if payload.get("is_error"):
                error = RunError(
                    code="provider_error",
                    message=str(payload.get("result") or "claude reported error"),
                    retryable=False,
                )

    if error is None and stderr.strip():
        error = RunError(code="provider_error", message=stderr.strip(), retryable=False)

    return ProviderParsedOutput(
        provider_session_id=provider_session_id,
        final_text=final_text,
        usage=_parse_usage(usage),
        error=error,
        raw_event_lines=tuple(raw_lines),
    )


def _extract_last_json(content: str) -> dict[str, object] | None:
    for line in reversed([line for line in content.splitlines() if line.strip()]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _parse_usage(raw: object) -> UsageInfo | None:
    if not isinstance(raw, dict):
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

