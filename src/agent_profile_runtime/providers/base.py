from __future__ import annotations

from abc import ABC, abstractmethod

from .kinds import ProviderKind
from .models import ProviderBuildContext, ProviderInvocation, ProviderParseContext, ProviderParsedOutput


class BaseProviderAdapter(ABC):
    kind: ProviderKind

    @abstractmethod
    def build_invocation(self, ctx: ProviderBuildContext) -> ProviderInvocation:
        raise NotImplementedError

    @abstractmethod
    def parse_output(self, ctx: ProviderParseContext) -> ProviderParsedOutput:
        raise NotImplementedError

    @abstractmethod
    def instructions_filename(self) -> str:
        raise NotImplementedError

