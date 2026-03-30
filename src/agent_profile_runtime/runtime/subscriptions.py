from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

from agent_profile_runtime.runs.models import ProviderEvent

from .event_bus import RunEventBus


def load_normalized_events(path: Path, *, from_seq: int = 0) -> list[ProviderEvent]:
    if not path.exists():
        return []
    events: list[ProviderEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        event = ProviderEvent.from_dict(payload)
        if event.seq >= from_seq:
            events.append(event)
    return events


def stream_run_events(
    *,
    event_bus: RunEventBus,
    normalized_events_path: Path,
    run_id: str,
    from_seq: int = 0,
    follow: bool = True,
    idle_timeout_s: float | None = None,
) -> Iterator[ProviderEvent]:
    yielded_max_seq = from_seq - 1
    for event in load_normalized_events(normalized_events_path, from_seq=from_seq):
        yielded_max_seq = max(yielded_max_seq, event.seq)
        yield event
    if not follow:
        return
    subscription = event_bus.subscribe(run_id)
    last_activity = time.monotonic()
    while True:
        timeout = 0.1
        if idle_timeout_s is not None:
            remaining = idle_timeout_s - (time.monotonic() - last_activity)
            if remaining <= 0:
                break
            timeout = min(timeout, remaining)
        try:
            event = subscription.get(timeout=timeout)
        except Exception:
            continue
        if event is None:
            break
        last_activity = time.monotonic()
        if event.seq <= yielded_max_seq:
            continue
        yielded_max_seq = event.seq
        yield event

