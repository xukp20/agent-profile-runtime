from __future__ import annotations

import json

from ..layouts import claude_mcp_path, claude_settings_path, claude_state_path
from .profile import ClaudeCodeProfile


def write_claude_code_profile(profile: ClaudeCodeProfile) -> None:
    profile.profile_dir.mkdir(parents=True, exist_ok=True)
    profile.meta.touch_updated()
    profile.meta.write(profile.profile_dir)
    claude_settings_path(profile.profile_dir).write_text(
        json.dumps(profile.settings_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    state_path = claude_state_path(profile.profile_dir)
    if profile.claude_state_payload is None:
        if state_path.exists():
            state_path.unlink()
    else:
        state_path.write_text(
            json.dumps(profile.claude_state_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    claude_mcp_path(profile.profile_dir).write_text(
        json.dumps(
            {
                "mcpServers": {
                    server.name: server.to_claude_dict()
                    for server in profile.mcp_servers
                }
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
