from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

from agent_profile_runtime.runs.models import ProviderEvent

_END = object()


@dataclass
class RunEventSubscription:
    run_id: str
    _queue: "queue.Queue[ProviderEvent | object]" = field(default_factory=queue.Queue)
    _closed: bool = False

    def get(self, timeout: float | None = None) -> ProviderEvent | None:
        item = self._queue.get(timeout=timeout)
        if item is _END:
            self._closed = True
            return None
        return item  # type: ignore[return-value]

    def push(self, event: ProviderEvent) -> None:
        if not self._closed:
            self._queue.put(event)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._queue.put(_END)


class RunEventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[RunEventSubscription]] = {}
        self._closed_runs: set[str] = set()

    def subscribe(self, run_id: str) -> RunEventSubscription:
        subscription = RunEventSubscription(run_id=run_id)
        with self._lock:
            if run_id in self._closed_runs:
                subscription.close()
                return subscription
            self._subscribers.setdefault(run_id, []).append(subscription)
        return subscription

    def publish(self, event: ProviderEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(event.run_id, []))
        for subscription in subscribers:
            subscription.push(event)

    def close_run(self, run_id: str) -> None:
        with self._lock:
            self._closed_runs.add(run_id)
            subscribers = self._subscribers.pop(run_id, [])
        for subscription in subscribers:
            subscription.close()

