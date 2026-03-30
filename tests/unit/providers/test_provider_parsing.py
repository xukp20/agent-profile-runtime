from __future__ import annotations

import json

from agent_profile_runtime.providers.claude_code import ClaudeCodeProviderAdapter
from agent_profile_runtime.providers.codex import CodexProviderAdapter
from agent_profile_runtime.providers.models import ProviderParseContext
from agent_profile_runtime.providers import ProviderKind


def test_codex_parse_output_ignores_reconnect_noise_after_turn_completed() -> None:
    adapter = CodexProviderAdapter()
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-test"}),
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "error", "message": "Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)"}),
            json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "semantic pass"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 3}}),
        ]
    )
    stderr = (
        "2026-03-29T16:25:22Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: IO error: tls handshake eof\n"
        "2026-03-29T16:25:30Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: IO error: tls handshake eof\n"
    )
    parsed = adapter.parse_output(
        ProviderParseContext(
            provider_kind=ProviderKind.CODEX,
            run_id="run-1",
            session_id="session-1",
            output_mode="text",
            stdout_text=stdout,
            stderr_text=stderr,
        )
    )
    assert parsed.provider_session_id == "thread-test"
    assert parsed.final_text == "semantic pass"
    assert parsed.error is None
    assert parsed.usage is not None
    assert parsed.usage.input_tokens == 2
    assert parsed.usage.output_tokens == 3


def test_codex_parse_output_preserves_non_ignorable_errors() -> None:
    adapter = CodexProviderAdapter()
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-test"}),
            json.dumps({"type": "error", "message": "fatal semantic worker corruption"}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}),
        ]
    )
    parsed = adapter.parse_output(
        ProviderParseContext(
            provider_kind=ProviderKind.CODEX,
            run_id="run-1",
            session_id="session-1",
            output_mode="text",
            stdout_text=stdout,
            stderr_text="",
        )
    )
    assert parsed.error is not None
    assert "fatal semantic worker corruption" in parsed.error.message


def test_claude_parse_stream_output_extracts_session_text_and_usage() -> None:
    adapter = ClaudeCodeProviderAdapter()
    stdout = "\n".join(
        [
            json.dumps({"type": "system", "session_id": "claude-session-1"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "thinking", "thinking": "planning"},
                            {"type": "text", "text": "hello world"},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "session_id": "claude-session-1",
                    "usage": {"input_tokens": 4, "output_tokens": 7},
                    "result": "hello world",
                    "is_error": False,
                }
            ),
        ]
    )
    parsed = adapter.parse_output(
        ProviderParseContext(
            provider_kind=ProviderKind.CLAUDE_CODE,
            run_id="run-1",
            session_id="session-1",
            output_mode="event_stream",
            stdout_text=stdout,
            stderr_text="",
        )
    )
    assert parsed.provider_session_id == "claude-session-1"
    assert parsed.final_text == "hello world"
    assert parsed.error is None
    assert parsed.usage is not None
    assert parsed.usage.input_tokens == 4
    assert parsed.usage.output_tokens == 7
