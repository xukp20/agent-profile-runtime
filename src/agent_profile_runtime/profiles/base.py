from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from agent_profile_runtime.providers import ProviderKind

from .meta import ProfileMeta


@dataclass(slots=True)
class BaseProfile(ABC):
    kind: ProviderKind
    name: str
    profile_dir: Path
    meta: ProfileMeta

    def exists(self) -> bool:
        return self.profile_dir.is_dir()

    @abstractmethod
    def validate(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def write(self) -> None:
        raise NotImplementedError
