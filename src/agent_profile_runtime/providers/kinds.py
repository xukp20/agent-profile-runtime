from __future__ import annotations

from enum import StrEnum


class ProviderKind(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"

    @classmethod
    def from_value(cls, value: str) -> "ProviderKind":
        normalized = str(value or "").strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unsupported provider kind: {value!r}")
