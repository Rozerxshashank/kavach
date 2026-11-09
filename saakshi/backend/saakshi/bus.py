"""In-process event bus: every screen (worker app, employer phone, console) listens here over SSE."""

from __future__ import annotations

import asyncio
import time


class Bus:
    def __init__(self, keep: int = 600):
        self.events: list[dict] = []
        self.keep = keep
        self.seq = 0
        self.cond = asyncio.Condition()

    async def emit(self, kind: str, **data) -> None:
        async with self.cond:
            self.seq += 1
            self.events.append({"seq": self.seq, "type": kind, "t": time.time(), **data})
            self.events = self.events[-self.keep:]
            self.cond.notify_all()

    async def stream(self, after: int):
        last = after
        while True:
            async with self.cond:
                await self.cond.wait_for(lambda: self.seq > last)     # replays buffered events newer than `after`
                batch = [e for e in self.events if e["seq"] > last]
            for e in batch:
                yield e
            if batch:
                last = batch[-1]["seq"]


bus = Bus()
