"""Kavach and Saakshi in one process on one port, for a single free web service.

    /saakshi/...  ->  Saakshi (its UI is built with base "/saakshi/"; the prefix is stripped before it sees the path)
    everything else  ->  Kavach

Each app keeps its own settings, data folder, middleware and startup tasks; this only routes requests and runs both
apps' startup and shutdown. They reach each other over loopback (KAVACH_SAAKSHI_URL / KAVACH_SHIELD_URL)."""

from __future__ import annotations

import asyncio

from kavach.server import app as kavach
from saakshi.server import app as saakshi

PREFIX = "/saakshi"


_states: dict[int, dict] = {}


async def _startup() -> None:
    for a in (kavach, saakshi):
        st = _states.setdefault(id(a), {})
        inbox: asyncio.Queue = asyncio.Queue()
        outbox: asyncio.Queue = asyncio.Queue()
        st.update(inbox=inbox, outbox=outbox)
        st["task"] = asyncio.create_task(a({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}, inbox.get, outbox.put))
        await inbox.put({"type": "lifespan.startup"})
        msg = await outbox.get()
        if msg["type"] != "lifespan.startup.complete":
            raise RuntimeError(f"startup failed: {msg.get('message', '')}")


async def _shutdown() -> None:
    for a in (saakshi, kavach):
        st = _states.get(id(a))
        if not st:
            continue
        await st["inbox"].put({"type": "lifespan.shutdown"})
        try:
            await asyncio.wait_for(st["outbox"].get(), timeout=10)
        except asyncio.TimeoutError:
            pass


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                try:
                    await _startup()
                except Exception as e:  # noqa: BLE001
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await _shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return
    path = scope.get("path", "")
    if path == PREFIX or path.startswith(PREFIX + "/"):
        rest = path[len(PREFIX):] or "/"
        raw = scope.get("raw_path") or path.encode()
        raw = raw[len(PREFIX):] if raw.startswith(PREFIX.encode()) else rest.encode()
        scope = dict(scope, path=rest, raw_path=raw or b"/")
        return await saakshi(scope, receive, send)
    return await kavach(scope, receive, send)
