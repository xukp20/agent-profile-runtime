from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from agent_profile_runtime.profiles.manager import ProfileManager
from agent_profile_runtime.providers.registry import get_provider_adapter
from agent_profile_runtime.runs.artifacts import ArtifactStore, build_run_artifact_layout
from agent_profile_runtime.runs.executor import execute_run
from agent_profile_runtime.runs.models import ProviderEvent, RunConfig, RunRecord, RunResult
from agent_profile_runtime.sessions.models import SessionInitConfig, SessionRecord
from agent_profile_runtime.sessions.service import SessionService
from agent_profile_runtime.sessions.store import SessionStore, utc_now_iso

from .bootstrap import bootstrap_runtime, ensure_profile_exists
from .config import RuntimeConfig
from .event_bus import RunEventBus
from .subscriptions import stream_run_events


@dataclass(slots=True)
class _RunState:
    run_id: str
    session_id: str
    priority: int
    queue_seq: int
    created_at: str
    run_config: RunConfig
    seq: int
    status: str = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    result: RunResult | None = None
    done_event: threading.Event = field(default_factory=threading.Event)


class ProviderRuntime:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        bootstrap_runtime(config)
        self.profile_manager = ProfileManager(Path(config.profiles_root))
        self.artifact_store = ArtifactStore(Path(config.runtime_dir))
        self.session_store = SessionStore(Path(config.runtime_dir))
        self.session_service = SessionService(
            session_store=self.session_store,
            profile_manager=self.profile_manager,
            base_workdir=config.base_workdir,
        )
        self.event_bus = RunEventBus()
        self._lock = threading.RLock()
        self._run_states: dict[str, _RunState] = {}
        self._run_seq = 0
        self._queue_seq = 0
        self._queue: "queue.PriorityQueue[tuple[int, int, str]]" = queue.PriorityQueue()
        self._accepting = True
        self._workers: list[threading.Thread] = []
        for idx in range(config.max_concurrency):
            worker = threading.Thread(target=self._worker_loop, name=f"provider-runtime-{idx}", daemon=True)
            worker.start()
            self._workers.append(worker)

    def close(self) -> None:
        with self._lock:
            self._accepting = False
            for _ in self._workers:
                self._queue.put((10**9, 10**9, "__shutdown__"))
        for worker in self._workers:
            worker.join(timeout=2.0)

    def init_session(self, init_config: SessionInitConfig) -> str:
        ensure_profile_exists(
            config=self.config,
            profile_manager=self.profile_manager,
            provider_kind=init_config.provider_kind,
            profile_name=init_config.profile_name,
        )
        record = self.session_service.init_session(init_config)
        return record.session_id

    def get_session(self, session_id: str) -> SessionRecord:
        return self.session_store.get_session(session_id)

    def list_sessions(self) -> list[SessionRecord]:
        return self.session_store.list_sessions()

    def submit_run(self, session_id: str, run_config: RunConfig | None = None, *, priority: int = 0) -> str:
        with self._lock:
            if not self._accepting:
                raise RuntimeError("runtime is closed")
            run_id = str(uuid4())
            self._run_seq += 1
            self._queue_seq += 1
            state = _RunState(
                run_id=run_id,
                session_id=session_id,
                priority=priority,
                queue_seq=self._queue_seq,
                created_at=utc_now_iso(),
                run_config=run_config or RunConfig(),
                seq=self._run_seq,
            )
            self._run_states[run_id] = state
            layout = build_run_artifact_layout(
                runtime_dir=Path(self.config.runtime_dir),
                session_id=session_id,
                seq=state.seq,
                run_id=run_id,
            )
            layout.run_dir.mkdir(parents=True, exist_ok=True)
            self.artifact_store.write_text_file(layout.events_raw_relpath, "")
            self.artifact_store.write_text_file(layout.events_normalized_relpath, "")
            self._write_run_record(state)
            queued_event = ProviderEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                session_id=session_id,
                provider_kind=self.get_session(session_id).provider_kind,
                seq=0,
                created_at=utc_now_iso(),
                type="run_queued",
                source="runtime",
                payload={},
            )
            self.artifact_store.append_event(layout.events_normalized_relpath, queued_event)
            self.event_bus.publish(queued_event)
            self._queue.put((-priority, self._queue_seq, run_id))
            return run_id

    def run_blocking(self, session_id: str, run_config: RunConfig | None = None) -> RunResult:
        run_id = self.submit_run(session_id, run_config=run_config)
        return self.wait_run(run_id)

    def wait_run(self, run_id: str, timeout_s: float | None = None) -> RunResult:
        state = self._get_run_state(run_id)
        if not state.done_event.wait(timeout=timeout_s):
            raise TimeoutError(f"wait_run timeout: {run_id}")
        if state.result is None:
            raise RuntimeError(f"run finished without result: {run_id}")
        return state.result

    def get_run_result(self, run_id: str) -> RunResult | None:
        state = self._get_run_state(run_id)
        return state.result

    def list_runs(self, *, session_id: str | None = None, status: str | None = None) -> list[RunRecord]:
        records = [self._load_run_record(state.run_id) for state in self._run_states.values()]
        if session_id is not None:
            records = [record for record in records if record.session_id == session_id]
        if status is not None:
            records = [record for record in records if record.status == status]
        return sorted(records, key=lambda item: item.seq)

    def subscribe_run_events(self, run_id: str):
        return self.event_bus.subscribe(run_id)

    def stream_run_events(self, run_id: str, *, from_seq: int = 0, follow: bool = True, idle_timeout_s: float | None = None):
        state = self._get_run_state(run_id)
        record = self._load_run_record(run_id)
        if record.events_normalized_relpath is None:
            raise RuntimeError(f"run has no normalized events artifact: {run_id}")
        return stream_run_events(
            event_bus=self.event_bus,
            normalized_events_path=self.artifact_store.abspath(record.events_normalized_relpath),
            run_id=run_id,
            from_seq=from_seq,
            follow=follow,
            idle_timeout_s=idle_timeout_s,
        )

    def _worker_loop(self) -> None:
        while True:
            _, _, run_id = self._queue.get()
            try:
                if run_id == "__shutdown__":
                    return
                with self._lock:
                    state = self._run_states.get(run_id)
                    if state is None or state.status != "queued":
                        continue
                    state.status = "running"
                    state.started_at = utc_now_iso()
                    self._write_run_record(state)
                self._execute_state(state)
            finally:
                self._queue.task_done()

    def _execute_state(self, state: _RunState) -> None:
        session = self.get_session(state.session_id)
        adapter = get_provider_adapter(session.provider_kind)
        execution = execute_run(
            artifact_store=self.artifact_store,
            session=session,
            run_id=state.run_id,
            run_config=state.run_config,
            run_seq=state.seq,
            provider_adapter=adapter,
            publish_event=self.event_bus.publish,
            write_session_instructions=self.session_service.write_session_instructions,
        )
        with self._lock:
            state.result = execution.run_result
            state.status = execution.run_result.status
            state.finished_at = execution.run_result.finished_at
            state.error_message = execution.run_result.error.message if execution.run_result.error else None
            self._write_run_record(state, execution.run_result)
            self.session_store.update_last_run_id(session.session_id, state.run_id)
            if execution.provider_session_id:
                self.session_store.update_provider_session_id(session.session_id, execution.provider_session_id)
            state.done_event.set()
            self.event_bus.close_run(state.run_id)

    def _get_run_state(self, run_id: str) -> _RunState:
        with self._lock:
            state = self._run_states.get(run_id)
            if state is None:
                raise KeyError(f"run not found: {run_id}")
            return state

    def _run_record_path(self, run_id: str) -> Path:
        state = self._get_run_state(run_id)
        rel = f"sessions/s_{state.session_id}/runs/r_{state.seq:06d}_{run_id}/run.record.json"
        return self.artifact_store.abspath(rel)

    def _write_run_record(self, state: _RunState, result: RunResult | None = None) -> None:
        rel_run_dir = f"sessions/s_{state.session_id}/runs/r_{state.seq:06d}_{state.run_id}"
        existing_record = None
        path = self.artifact_store.abspath(f"{rel_run_dir}/run.record.json")
        if path.exists():
            try:
                existing_record = RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                existing_record = None
        record = RunRecord(
            run_id=state.run_id,
            session_id=state.session_id,
            seq=state.seq,
            priority=state.priority,
            queue_seq=state.queue_seq,
            status=state.status,  # type: ignore[arg-type]
            created_at=state.created_at,
            started_at=state.started_at,
            finished_at=state.finished_at,
            error_message=state.error_message,
            run_config=state.run_config,
            effective=existing_record.effective if existing_record else None,
            request_relpath=existing_record.request_relpath if existing_record else f"{rel_run_dir}/run.request.json",
            effective_relpath=existing_record.effective_relpath if existing_record else f"{rel_run_dir}/run.effective.json",
            command_relpath=existing_record.command_relpath if existing_record else f"{rel_run_dir}/provider.command.json",
            stdout_relpath=existing_record.stdout_relpath if existing_record else f"{rel_run_dir}/stdout.log",
            stderr_relpath=existing_record.stderr_relpath if existing_record else f"{rel_run_dir}/stderr.log",
            events_raw_relpath=existing_record.events_raw_relpath if existing_record else f"{rel_run_dir}/events.raw.jsonl",
            events_normalized_relpath=existing_record.events_normalized_relpath if existing_record else f"{rel_run_dir}/events.normalized.jsonl",
            result_relpath=existing_record.result_relpath if existing_record else f"{rel_run_dir}/result.json",
        )
        if result is not None:
            record.effective = None
        self.artifact_store.write_json_file(f"{rel_run_dir}/run.record.json", record.to_dict())

    def _load_run_record(self, run_id: str) -> RunRecord:
        path = self._run_record_path(run_id)
        return RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
