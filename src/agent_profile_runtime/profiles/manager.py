from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_profile_runtime.providers import ProviderKind

from .base import BaseProfile
from .factory import create_profile, load_profile
from .layouts import profile_dir, provider_profiles_root
from .meta import PROFILE_META_FILENAME, ProfileMeta


@dataclass(slots=True)
class ProfileManager:
    profiles_root: Path

    def profile_dir(self, kind: ProviderKind, name: str) -> Path:
        return profile_dir(self.profiles_root, kind, name)

    def create_profile(
        self,
        *,
        kind: ProviderKind,
        name: str,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> BaseProfile:
        target_dir = self.profile_dir(kind, name)
        if target_dir.exists():
            if not overwrite:
                raise FileExistsError(target_dir)
            shutil.rmtree(target_dir)
        profile = create_profile(kind=kind, name=name, profiles_root=self.profiles_root, **kwargs)
        profile.write()
        return profile

    def load_profile(self, *, kind: ProviderKind, name: str) -> BaseProfile:
        return load_profile(kind=kind, name=name, profiles_root=self.profiles_root)

    def list_profiles(self, *, kind: ProviderKind | None = None) -> list[ProfileMeta]:
        kinds = [kind] if kind is not None else [ProviderKind.CODEX, ProviderKind.CLAUDE_CODE]
        metas: list[ProfileMeta] = []
        for current_kind in kinds:
            root = provider_profiles_root(self.profiles_root, current_kind)
            if not root.exists():
                continue
            for child in sorted(path for path in root.iterdir() if path.is_dir()):
                meta_path = child / PROFILE_META_FILENAME
                if not meta_path.exists():
                    continue
                metas.append(ProfileMeta.load(child))
        metas.sort(key=lambda item: (item.kind.value, item.name))
        return metas

    def delete_profile(self, *, kind: ProviderKind, name: str, missing_ok: bool = False) -> None:
        target_dir = self.profile_dir(kind, name)
        if not target_dir.exists():
            if missing_ok:
                return
            raise FileNotFoundError(target_dir)
        shutil.rmtree(target_dir)

    def copy_profile(
        self,
        *,
        src_kind: ProviderKind,
        src_name: str,
        dst_name: str,
        dst_kind: ProviderKind | None = None,
        overwrite: bool = False,
    ) -> BaseProfile:
        final_kind = dst_kind or src_kind
        if final_kind is not src_kind:
            raise ValueError("Cross-provider profile copy is not supported")
        source_dir = self.profile_dir(src_kind, src_name)
        target_dir = self.profile_dir(final_kind, dst_name)
        if target_dir.exists():
            if not overwrite:
                raise FileExistsError(target_dir)
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        copied = self.load_profile(kind=final_kind, name=dst_name)
        copied.name = dst_name
        copied.profile_dir = target_dir
        copied.meta.name = dst_name
        copied.write()
        return copied
