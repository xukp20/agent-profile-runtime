from __future__ import annotations

import json
from pathlib import Path

from ..layouts import codex_auth_path, codex_config_path
from ..meta import ProfileMeta
from .blocks import parse_codex_mcp_servers, split_codex_config
from .profile import CodexProfile


def load_codex_profile(profile_root: Path) -> CodexProfile:
    meta = ProfileMeta.load(profile_root)
    config_text = codex_config_path(profile_root).read_text(encoding="utf-8")
    blocks = split_codex_config(config_text)

    auth_path = codex_auth_path(profile_root)
    auth_payload: dict[str, object] = {}
    if auth_path.exists():
        data = json.loads(auth_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object in {auth_path}")
        auth_payload = data

    profile = CodexProfile(
        kind=meta.kind,
        name=meta.name,
        profile_dir=profile_root,
        meta=meta,
        base_config_text=blocks.base_config_text,
        auth_payload=auth_payload,
        mcp_servers=parse_codex_mcp_servers(blocks.mcp_servers_text),
    )
    profile.validate()
    return profile
