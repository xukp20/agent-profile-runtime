from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_profile_runtime.providers import ProviderKind

from .base import BaseProfile
from .claude_code.profile import ClaudeCodeProfile
from .codex.profile import CodexProfile
from .layouts import profile_dir


def create_profile(
    *,
    kind: ProviderKind,
    name: str,
    profiles_root: Path,
    **kwargs: Any,
) -> BaseProfile:
    if kind is ProviderKind.CODEX:
        return CodexProfile.create(name=name, profiles_root=profiles_root, **kwargs)
    if kind is ProviderKind.CLAUDE_CODE:
        return ClaudeCodeProfile.create(name=name, profiles_root=profiles_root, **kwargs)
    raise ValueError(f"Unsupported provider kind: {kind!r}")


def load_profile(*, kind: ProviderKind, name: str, profiles_root: Path) -> BaseProfile:
    target_dir = profile_dir(profiles_root, kind, name)
    if kind is ProviderKind.CODEX:
        return CodexProfile.from_dir(target_dir)
    if kind is ProviderKind.CLAUDE_CODE:
        return ClaudeCodeProfile.from_dir(target_dir)
    raise ValueError(f"Unsupported provider kind: {kind!r}")
