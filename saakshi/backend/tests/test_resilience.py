"""When Gnani is busy (one request per key) nobody may be left waiting forever."""

import asyncio
import time

import httpx
import pytest
from starlette.testclient import TestClient

from saakshi import accounts, gnani, store


def test_busy_speech_service_gives_up_within_budget():
    async def always_busy():
        return httpx.Response(429, json={"detail": "Only 1 active request is allowed at a time"})

    async def run():
        t = time.monotonic()
        with pytest.raises(gnani.GnaniError):
            await gnani._post_with_retry(always_busy, "Timbre TTS", deadline=2.0)
        return time.monotonic() - t

    assert asyncio.run(run()) < 3.0


def test_hanging_request_is_cut_off():
    async def hangs():
        await asyncio.sleep(60)

    async def run():
        t = time.monotonic()
        with pytest.raises(gnani.GnaniError):
            await gnani._post_with_retry(hangs, "Prisma STT", deadline=1.5)
        return time.monotonic() - t

    assert asyncio.run(run()) < 2.5


def test_app_still_answers_in_text_when_voice_is_down(monkeypatch):
    from saakshi.server import app

    async def down(*a, **k):
        raise gnani.GnaniError("busy")

    monkeypatch.setattr(gnani, "timbre_speak", down)
    w = store.create_worker("Resilient User", "9123488001", "hi-IN", "cook", "Pune", "MH",
                            pin_hash=accounts.hash_pin("4826"))
    c = TestClient(app)
    t = time.monotonic()
    r = c.post(f"/api/workers/{w['id']}/welcome", headers={"X-Worker-Token": accounts.token_for(w["id"])})
    assert r.status_code == 200 and r.json()["say"] and r.json()["audio"] is None
    assert time.monotonic() - t < 3
