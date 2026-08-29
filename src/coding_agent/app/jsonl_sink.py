"""JsonlLogSink: append every event to .wavecode/logs/<timestamp>.jsonl.

Full, untruncated session record (docs/04 §2 layer 1). Never contains the
API key: events simply do not carry credentials.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import IO

from coding_agent.domain.events import AgentEvent


class JsonlLogSink:
    def __init__(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = log_dir / f"{stamp}.jsonl"
        self._fh: IO[str] = self.path.open("a", encoding="utf-8")

    def on_event(self, event: AgentEvent) -> None:
        record = {"event": type(event).__name__, **dataclasses.asdict(event)}
        self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
