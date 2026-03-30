from __future__ import annotations

import json

from ..layouts import codex_auth_path, codex_config_path
from .profile import CodexProfile


def write_codex_profile(profile: CodexProfile) -> None:
    profile.profile_dir.mkdir(parents=True, exist_ok=True)
    profile.meta.touch_updated()
    profile.meta.write(profile.profile_dir)
    codex_config_path(profile.profile_dir).write_text(profile.config_toml_text, encoding="utf-8")
    codex_auth_path(profile.profile_dir).write_text(
        json.dumps(profile.auth_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
