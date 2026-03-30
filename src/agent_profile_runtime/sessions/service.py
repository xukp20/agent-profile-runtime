from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agent_profile_runtime.profiles.manager import ProfileManager
from agent_profile_runtime.providers.registry import get_provider_adapter

from .models import SessionEffectiveConfig, SessionInitConfig, SessionRecord
from .store import SessionStore, utc_now_iso


@dataclass(slots=True)
class SessionService:
    session_store: SessionStore
    profile_manager: ProfileManager
    base_workdir: str | None = None

    def init_session(self, init_config: SessionInitConfig) -> SessionRecord:
        profile = self.profile_manager.load_profile(
            kind=init_config.provider_kind,
            name=init_config.profile_name,
        )
        adapter = get_provider_adapter(init_config.provider_kind)
        workdir = init_config.workdir or self.base_workdir
        if workdir is None:
            workdir = str(self.session_store.runtime_dir.parent.resolve())
        Path(workdir).mkdir(parents=True, exist_ok=True)

        effective = SessionEffectiveConfig(
            provider_kind=init_config.provider_kind,
            profile_name=init_config.profile_name,
            profile_dir=str(profile.profile_dir.resolve()),
            workdir=str(Path(workdir).resolve()),
            model=init_config.model,
            additional_dirs=init_config.additional_dirs,
            env=init_config.env,
            instructions_filename=adapter.instructions_filename(),
        )

        if init_config.instructions_file_content is not None:
            self.write_session_instructions(
                workdir=effective.workdir,
                filename=effective.instructions_filename,
                content=init_config.instructions_file_content,
            )

        now = utc_now_iso()
        session_id = str(uuid4())
        record = SessionRecord(
            session_id=session_id,
            provider_kind=effective.provider_kind,
            profile_name=effective.profile_name,
            profile_dir=effective.profile_dir,
            provider_session_id=None,
            workdir=effective.workdir,
            model=effective.model,
            additional_dirs=effective.additional_dirs,
            env=effective.env,
            status="ready",
            created_at=now,
            updated_at=now,
        )
        return self.session_store.create_session(record)

    def get_session(self, session_id: str) -> SessionRecord:
        return self.session_store.get_session(session_id)

    def list_sessions(self) -> list[SessionRecord]:
        return self.session_store.list_sessions()

    @staticmethod
    def write_session_instructions(*, workdir: str, filename: str, content: str) -> str:
        path = Path(workdir) / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

