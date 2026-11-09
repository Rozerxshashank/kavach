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


# Voices on timbre-v2.5 that we use. The full catalogue has 70+.
BOT_VOICE = "Nalini"

_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0))
    return _client


def _headers() -> dict[str, str]:
    if not settings.gnani_api_key:
        raise GnaniError("GNANI_API_KEY is not set in .env")
    return {"X-API-Key-ID": settings.gnani_api_key}


async def _post_with_retry(make_request, what: str) -> httpx.Response:
    last = ""
    async with _lock:
        for attempt in range(5):
            try:
                resp = await make_request()
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise GnaniError(f"{what} rejected: HTTP {resp.status_code}: {resp.text[:300]}")
            return resp
    raise GnaniError(f"{what} failed after retries ({last})")


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
    return SpeechResult(resp.content, (time.perf_counter() - t0) * 1000,
                        settings.tts_model, voice, language)


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
    return TranscriptResult(str(text).strip(), (time.perf_counter() - t0) * 1000,
                            body.get("model", "prisma"), language)
