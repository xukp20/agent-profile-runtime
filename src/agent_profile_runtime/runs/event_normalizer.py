from __future__ import annotations

import json
from uuid import uuid4

from agent_profile_runtime.providers import ProviderKind
from agent_profile_runtime.sessions.store import utc_now_iso

from .models import ProviderEvent


def normalize_runtime_event(
    *,
    run_id: str,
    session_id: str,
    provider_kind: ProviderKind,
    seq: int,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        event_id=str(uuid4()),
        run_id=run_id,
        session_id=session_id,
        provider_kind=provider_kind,
        seq=seq,
        created_at=utc_now_iso(),
        type=event_type,  # type: ignore[arg-type]
        source="runtime",
        payload=dict(payload or {}),
    )


def normalize_provider_stdout_line(
    *,
    run_id: str,
    session_id: str,
    provider_kind: ProviderKind,
    seq_start: int,
    line: str,
) -> list[ProviderEvent]:
    if provider_kind is ProviderKind.CODEX:
        return _normalize_codex_stdout_line(run_id, session_id, seq_start, line)
    return _normalize_claude_stdout_line(run_id, session_id, seq_start, line)


def normalize_provider_stderr_line(
    *,
    run_id: str,
    session_id: str,
    provider_kind: ProviderKind,
    seq_start: int,
    line: str,
) -> list[ProviderEvent]:
    payload = {"text": line.rstrip("\n")}
    return [
        ProviderEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            session_id=session_id,
            provider_kind=provider_kind,
            seq=seq_start,
            created_at=utc_now_iso(),
            type="error",
            source="provider_stderr",
            payload=payload,
        )
    ]


def _normalize_codex_stdout_line(run_id: str, session_id: str, seq_start: int, line: str) -> list[ProviderEvent]:
    events: list[ProviderEvent] = [
        ProviderEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            session_id=session_id,
            provider_kind=ProviderKind.CODEX,
            seq=seq_start,
            created_at=utc_now_iso(),
            type="raw_provider_event",
            source="provider_stdout",
            payload={"line": line},
        )
    ]
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return events

    event_type = payload.get("type")
    next_seq = seq_start + 1
    if event_type == "thread.started":
        thread_id = payload.get("thread_id")
        if thread_id:
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CODEX,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="session_established",
                    source="provider_parser",
                    payload={"provider_session_id": str(thread_id)},
                )
            )
            next_seq += 1
    elif event_type == "item.completed":
        item = payload.get("item") or {}
        if item.get("type") == "agent_message" and item.get("text") is not None:
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CODEX,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="message_final",
                    source="provider_parser",
                    payload={"text": str(item.get("text"))},
                )
            )
            next_seq += 1
        elif item.get("type") == "command_execution":
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CODEX,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="tool_call_completed",
                    source="provider_parser",
                    payload={
                        "tool_name": "command_execution",
                        "command": item.get("command"),
                        "exit_code": item.get("exit_code"),
                    },
                )
            )
            next_seq += 1
        elif item.get("type") == "mcp_tool_call":
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CODEX,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="tool_call_completed",
                    source="provider_parser",
                    payload={
                        "tool_name": str(item.get("tool") or ""),
                        "server": item.get("server"),
                        "arguments": item.get("arguments"),
                    },
                )
            )
            next_seq += 1
    elif event_type == "turn.completed":
        events.append(
            ProviderEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                session_id=session_id,
                provider_kind=ProviderKind.CODEX,
                seq=next_seq,
                created_at=utc_now_iso(),
                type="usage",
                source="provider_parser",
                payload=dict(payload.get("usage") or {}),
            )
        )
        next_seq += 1
    elif event_type in {"error", "turn.failed"}:
        message = payload.get("message")
        if not message and isinstance(payload.get("error"), dict):
            message = payload["error"].get("message")
        events.append(
            ProviderEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                session_id=session_id,
                provider_kind=ProviderKind.CODEX,
                seq=next_seq,
                created_at=utc_now_iso(),
                type="error",
                source="provider_parser",
                payload={"message": str(message or "provider error")},
            )
        )
    return events


def _normalize_claude_stdout_line(run_id: str, session_id: str, seq_start: int, line: str) -> list[ProviderEvent]:
    events: list[ProviderEvent] = [
        ProviderEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            session_id=session_id,
            provider_kind=ProviderKind.CLAUDE_CODE,
            seq=seq_start,
            created_at=utc_now_iso(),
            type="raw_provider_event",
            source="provider_stdout",
            payload={"line": line},
        )
    ]
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return events

    event_type = payload.get("type")
    next_seq = seq_start + 1
    if event_type == "system":
        session_value = payload.get("session_id")
        if session_value:
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CLAUDE_CODE,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="session_established",
                    source="provider_parser",
                    payload={"provider_session_id": str(session_value)},
                )
            )
    elif event_type == "assistant":
        message = payload.get("message") or {}
        content = message.get("content") or []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    events.append(
                        ProviderEvent(
                            event_id=str(uuid4()),
                            run_id=run_id,
                            session_id=session_id,
                            provider_kind=ProviderKind.CLAUDE_CODE,
                            seq=next_seq,
                            created_at=utc_now_iso(),
                            type="message_delta",
                            source="provider_parser",
                            payload={"text": str(block.get("text") or "")},
                        )
                    )
                    next_seq += 1
                elif block.get("type") == "thinking":
                    events.append(
                        ProviderEvent(
                            event_id=str(uuid4()),
                            run_id=run_id,
                            session_id=session_id,
                            provider_kind=ProviderKind.CLAUDE_CODE,
                            seq=next_seq,
                            created_at=utc_now_iso(),
                            type="thinking_delta",
                            source="provider_parser",
                            payload={"text": str(block.get("thinking") or "")},
                        )
                    )
                    next_seq += 1
                elif block.get("type") == "tool_use":
                    events.append(
                        ProviderEvent(
                            event_id=str(uuid4()),
                            run_id=run_id,
                            session_id=session_id,
                            provider_kind=ProviderKind.CLAUDE_CODE,
                            seq=next_seq,
                            created_at=utc_now_iso(),
                            type="tool_call_started",
                            source="provider_parser",
                            payload={
                                "tool_name": str(block.get("name") or ""),
                                "input": block.get("input"),
                            },
                        )
                    )
                    next_seq += 1
    elif event_type == "result":
        usage = payload.get("usage")
        if isinstance(usage, dict):
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CLAUDE_CODE,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="usage",
                    source="provider_parser",
                    payload=dict(usage),
                )
            )
            next_seq += 1
        if payload.get("result") is not None:
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CLAUDE_CODE,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="message_final",
                    source="provider_parser",
                    payload={"text": str(payload.get("result"))},
                )
            )
            next_seq += 1
        if payload.get("is_error"):
            events.append(
                ProviderEvent(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    session_id=session_id,
                    provider_kind=ProviderKind.CLAUDE_CODE,
                    seq=next_seq,
                    created_at=utc_now_iso(),
                    type="error",
                    source="provider_parser",
                    payload={"message": str(payload.get("result") or "provider error")},
                )
            )
    return events

