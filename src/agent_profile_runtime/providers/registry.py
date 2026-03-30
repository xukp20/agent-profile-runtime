from __future__ import annotations

from .base import BaseProviderAdapter
from .claude_code import ClaudeCodeProviderAdapter
from .codex import CodexProviderAdapter
from .kinds import ProviderKind

_REGISTRY: dict[ProviderKind, BaseProviderAdapter] = {
    ProviderKind.CODEX: CodexProviderAdapter(),
    ProviderKind.CLAUDE_CODE: ClaudeCodeProviderAdapter(),
}


def get_provider_adapter(kind: ProviderKind) -> BaseProviderAdapter:
    return _REGISTRY[kind]

