from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import ProviderEvent


@dataclass(slots=True, frozen=True)
class RunArtifactLayout:
    run_dir: Path
    request_relpath: str
    effective_relpath: str
    command_relpath: str
    stdout_relpath: str
    stderr_relpath: str
    events_raw_relpath: str
    events_normalized_relpath: str
    result_relpath: str
    record_relpath: str


def build_run_artifact_layout(*, runtime_dir: Path, session_id: str, seq: int, run_id: str) -> RunArtifactLayout:
    rel_run_dir = f"sessions/s_{session_id}/runs/r_{seq:06d}_{run_id}"
    run_dir = runtime_dir / rel_run_dir
    return RunArtifactLayout(
        run_dir=run_dir,
        request_relpath=f"{rel_run_dir}/run.request.json",
        effective_relpath=f"{rel_run_dir}/run.effective.json",
        command_relpath=f"{rel_run_dir}/provider.command.json",
        stdout_relpath=f"{rel_run_dir}/stdout.log",
        stderr_relpath=f"{rel_run_dir}/stderr.log",
        events_raw_relpath=f"{rel_run_dir}/events.raw.jsonl",
        events_normalized_relpath=f"{rel_run_dir}/events.normalized.jsonl",
        result_relpath=f"{rel_run_dir}/result.json",
        record_relpath=f"{rel_run_dir}/run.record.json",
    )


class ArtifactStore:
    _TAIL_READ_CHUNK_BYTES = 8192

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def abspath(self, relpath: str) -> Path:
        return self.runtime_dir / relpath

    def write_json_file(self, relpath: str, payload: dict[str, object]) -> None:
        path = self.abspath(relpath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def read_json_file(self, relpath: str) -> dict[str, object]:
        return json.loads(self.abspath(relpath).read_text(encoding="utf-8"))

    def write_text_file(self, relpath: str, content: str) -> None:
        path = self.abspath(relpath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def append_text_file(self, relpath: str, content: str) -> None:
        path = self.abspath(relpath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)

    def append_event(self, relpath: str, event: ProviderEvent) -> None:
        self.append_text_file(relpath, event.to_json_line())

    def tail_text_file(self, relpath: str, *, lines: int) -> str:
        if lines <= 0:
            return ""
        path = self.abspath(relpath)
        if not path.exists() or not path.is_file():
            return ""
        with path.open("rb") as handle:
            handle.seek(0, 2)
            file_size = handle.tell()
            chunks: list[bytes] = []
            remaining = file_size
            newline_count = 0
            while remaining > 0 and newline_count <= lines:
                chunk_size = min(self._TAIL_READ_CHUNK_BYTES, remaining)
                remaining -= chunk_size
                handle.seek(remaining)
                chunk = handle.read(chunk_size)
                chunks.append(chunk)
                newline_count += chunk.count(b"\n")
            text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
        parts = text.splitlines(keepends=True)
        tail = parts[-lines:]
        return "".join(tail)

    def read_text_file_from_offset(self, relpath: str, *, offset: int, max_bytes: int) -> tuple[str, int]:
        if max_bytes <= 0:
            return "", offset
        path = self.abspath(relpath)
        if not path.exists():
            return "", offset
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(max_bytes)
            return data.decode("utf-8", errors="replace"), offset + len(data)

    def read_text_file_lines_from_offset(self, relpath: str, *, offset: int, max_bytes: int) -> tuple[str, int]:
        chunk, next_offset = self.read_text_file_from_offset(relpath, offset=offset, max_bytes=max_bytes)
        if not chunk:
            return "", offset
        if chunk.endswith("\n"):
            return chunk, next_offset
        last_newline = chunk.rfind("\n")
        if last_newline < 0:
            return "", offset
        safe_chunk = chunk[: last_newline + 1]
        safe_offset = offset + len(safe_chunk.encode("utf-8"))
        return safe_chunk, safe_offset

