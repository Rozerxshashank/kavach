"""Gnani Vachana speech stack.

* Timbre (timbre-v2.5) — text-to-speech. Gives every caller persona and the bank
  bot a real, distinct Indian voice, with speaking speed driven by emotion.
* Prisma (prisma-v2.5) — speech-to-text. It is the *ears* of the system: the bank
  bot only ever sees what Prisma transcribed from the (possibly noisy) caller
  audio, and the attacker only hears what Prisma transcribed from the bot.

The API key allows one in-flight request, so every call goes through one lock
and 429s are retried with backoff.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from dataclasses import dataclass

import httpx

from .config import settings


class GnaniError(RuntimeError):
    pass


@dataclass
class SpeechResult:
    audio: bytes
    latency_ms: float
    model: str
    voice: str
    language: str


@dataclass
class TranscriptResult:
    text: str
    latency_ms: float
    model: str
    language: str


# ---- live usage, shown on the site (real numbers from this server, not marketing) ----------
from collections import deque  # noqa: E402

USAGE: dict[str, dict] = {
    "timbre": {"calls": 0, "seconds": 0.0, "lat": deque(maxlen=300), "langs": set()},
    "prisma": {"calls": 0, "seconds": 0.0, "lat": deque(maxlen=300), "langs": set()},
}


_USAGE_FILE = settings.data_dir / "gnani_usage.json"


def _load_usage() -> None:
    import json
    try:
        saved = json.loads(_USAGE_FILE.read_text())
    except (OSError, ValueError):
        return
    for k, v in saved.items():
        if k in USAGE:
            USAGE[k]["calls"] = int(v.get("calls", 0))
            USAGE[k]["seconds"] = float(v.get("seconds", 0))
            USAGE[k]["langs"] = set(v.get("langs", []))


def _record(model: str, latency_ms: float, seconds: float, language: str) -> None:
    import json
    u = USAGE[model]
    u["calls"] += 1
    u["seconds"] += seconds
    u["lat"].append(latency_ms)
    u["langs"].add(language)
    try:                                        # running totals survive restarts; latencies are "recent" only
        _USAGE_FILE.write_text(json.dumps({k: {"calls": v["calls"], "seconds": v["seconds"], "langs": sorted(v["langs"])}
                                           for k, v in USAGE.items()}))
    except OSError:
        pass


_load_usage()


def usage() -> dict:
    out = {}
    for k, u in USAGE.items():
        lat = sorted(u["lat"])
        out[k] = {"calls": u["calls"], "audio_seconds": round(u["seconds"], 1), "languages": sorted(u["langs"]),
                  "median_ms": round(lat[len(lat) // 2]) if lat else None,
                  "p90_ms": round(lat[int(len(lat) * 0.9)]) if lat else None}
    return out


# Voices on timbre-v2.5 that we use. The full catalogue has 70+.
BOT_VOICE = "Nalini"

# One client and one single-flight lock per event loop: objects bound to a loop
# can't be reused from another (tests, scripts, background workers).
_per_loop: dict[int, tuple[httpx.AsyncClient, asyncio.Lock]] = {}


def _state() -> tuple[httpx.AsyncClient, asyncio.Lock]:
    loop = asyncio.get_running_loop()
    st = _per_loop.get(id(loop))
    if st is None or st[0].is_closed:
        st = (httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0)), asyncio.Lock())
        _per_loop[id(loop)] = st
    return st


def _http() -> httpx.AsyncClient:
    return _state()[0]


def _headers() -> dict[str, str]:
    if not settings.gnani_api_key:
        raise GnaniError("GNANI_API_KEY is not set in .env")
    return {"X-API-Key-ID": settings.gnani_api_key}


# Background work (Kavach's attacks) yields the single speech slot to people: a low-priority request waits until no
# normal request is queued, so a worker or employer never waits behind a test call.
_low: "contextvars.ContextVar[bool]" = contextvars.ContextVar("gnani_low_priority", default=False)
_waiting_people = 0


@contextlib.contextmanager
def low_priority():
    tok = _low.set(True)
    try:
        yield
    finally:
        _low.reset(tok)


DEADLINE_S = 25.0          # a person is waiting: never spend longer than this on one speech call


async def _post_with_retry(make_request, what: str, deadline: float = DEADLINE_S) -> httpx.Response:
    """Single-flight within this process, jittered retries when the key's one slot is busy, hard time budget."""
    import random
    import time as _t
    last = ""
    start = _t.monotonic()

    def left() -> float:
        return deadline - (_t.monotonic() - start)

    global _waiting_people
    low = _low.get()
    if low:
        deadline = max(deadline, 90.0)                 # background work can wait its turn
        while (_waiting_people or _state()[1].locked()) and left() > 1:
            await asyncio.sleep(0.05)
    else:
        _waiting_people += 1
    try:
        await asyncio.wait_for(_state()[1].acquire(), timeout=max(0.1, left()))
    except asyncio.TimeoutError:
        raise GnaniError(f"{what} is busy right now (queue wait exceeded {deadline:.0f}s)")
    finally:
        if not low:
            _waiting_people -= 1
    try:
        attempt = 0
        while left() > 0.5:
            try:
                resp = await asyncio.wait_for(make_request(), timeout=min(15.0, left()))
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}: {resp.text[:200]}"
                elif resp.status_code >= 400:
                    raise GnaniError(f"{what} rejected: HTTP {resp.status_code}: {resp.text[:300]}")
                else:
                    return resp
            attempt += 1
            await asyncio.sleep(min(left(), min(3.0, 0.4 * 2 ** attempt) * random.uniform(0.7, 1.3)))
    finally:
        _state()[1].release()
    raise GnaniError(f"{what} unavailable after {deadline:.0f}s ({last})")


def clamp_speed(speed: float) -> float:
    # timbre-v2.5 accepts 0.85–1.15 only.
    return round(max(0.85, min(1.15, speed)), 2)


async def timbre_speak(text: str, *, voice: str, language: str = "en-IN",
                       speed: float = 1.0) -> SpeechResult:
    from .speech import for_speech        # names in the language's own script, so they're said right
    text = await for_speech(text, language)
    payload = {
        "text": text,
        "voice": voice,
        "model": settings.tts_model,
        "language": language,
        "speed": clamp_speed(speed),
        "audio_config": {
            "sample_rate": 16000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    t0 = time.perf_counter()
    resp = await _post_with_retry(
        lambda: _http().post(settings.tts_endpoint, json=payload, headers=_headers()),
        "Timbre TTS",
    )
    if not resp.content.startswith(b"RIFF"):
        raise GnaniError(f"Timbre returned non-WAV payload: {resp.content[:120]!r}")
    ms = (time.perf_counter() - t0) * 1000
    _record("timbre", ms, max(0, len(resp.content) - 44) / 32000, language)
    return SpeechResult(resp.content, ms, settings.tts_model, voice, language)


async def prisma_transcribe(wav: bytes, *, language: str = "en-IN") -> TranscriptResult:
    """Transcribe with Prisma; clips over its 30 s limit are split at pauses."""
    from .audio import split_for_asr
    parts = split_for_asr(wav)
    if len(parts) == 1:
        return await _prisma_once(wav, language)
    results = [await _prisma_once(p, language) for p in parts]
    return TranscriptResult(" ".join(r.text for r in results if r.text),
                            sum(r.latency_ms for r in results), results[0].model, language)


async def _prisma_once(wav: bytes, language: str) -> TranscriptResult:
    t0 = time.perf_counter()
    resp = await _post_with_retry(
        lambda: _http().post(
            settings.asr_endpoint,
            headers=_headers(),
            files={"audio_file": ("audio.wav", wav, "audio/wav")},
            data={"language_code": language},
        ),
        "Prisma STT",
    )
    body = resp.json()
    text = body.get("transcript") or (body.get("output") or {}).get("literal") or ""
    ms = (time.perf_counter() - t0) * 1000
    _record("prisma", ms, max(0, len(wav) - 44) / 32000, language)
    return TranscriptResult(str(text).strip(), ms, body.get("model", "prisma"), language)
