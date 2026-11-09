"""WAV helpers and synthetic acoustic environments.

Real fraud calls are rarely clean: an "airport emergency" call comes with
announcements and crowd noise, a "police raid" call comes with sirens. Kavach
mixes those environments into the caller audio *before* Prisma hears it, so the
target is tested on the audio its ears would really get.

Everything is generated procedurally with numpy, so no sound assets are needed.
"""

from __future__ import annotations

import io
import wave

import numpy as np

SR = 16000

ENVIRONMENTS = {
    "none": "Clean line",
    "airport": "Airport terminal — crowd, PA chimes",
    "traffic": "Roadside — engine rumble, horns",
    "crowd": "Busy market — overlapping voices",
    "siren": "Emergency — sirens in the background",
}

INTENSITY_SNR_DB = {"light": 18.0, "medium": 10.0, "heavy": 4.0}


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        width = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"unsupported sample width {width}")
    pcm = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    return pcm, sr


def write_wav(pcm: np.ndarray, sr: int = SR) -> bytes:
    pcm = np.clip(pcm, -1.0, 1.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def duration_s(data: bytes) -> float:
    pcm, sr = read_wav(data)
    return round(len(pcm) / sr, 3)


def peaks(data: bytes, buckets: int = 96) -> list[float]:
    """Normalised amplitude envelope, used by the UI to draw static waveforms."""
    pcm, _ = read_wav(data)
    if len(pcm) == 0:
        return [0.0] * buckets
    chunks = np.array_split(np.abs(pcm), buckets)
    env = np.array([float(c.max()) if len(c) else 0.0 for c in chunks])
    top = env.max() or 1.0
    return [round(float(v / top), 3) for v in env]


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    f = np.arange(len(spec))
    f[0] = 1
    spec /= np.sqrt(f)
    return np.fft.irfft(spec, n)


def _babble(n: int, rng: np.random.Generator, voices: int = 6) -> np.ndarray:
    """Crowd chatter: band-limited noise with syllable-rate amplitude bursts."""
    out = np.zeros(n)
    t = np.arange(n) / SR
    for _ in range(voices):
        carrier = _pink(n, rng)
        spec = np.fft.rfft(carrier)
        freqs = np.fft.rfftfreq(n, 1 / SR)
        lo, hi = rng.uniform(180, 400), rng.uniform(1800, 3200)
        spec[(freqs < lo) | (freqs > hi)] = 0
        voice = np.fft.irfft(spec, n)
        rate = rng.uniform(3.0, 5.5)  # syllables per second
        env = np.clip(np.sin(2 * np.pi * rate * t + rng.uniform(0, 6)) , 0, None) ** 1.5
        slow = np.clip(np.sin(2 * np.pi * rng.uniform(0.1, 0.4) * t + rng.uniform(0, 6)), 0.2, 1)
        out += voice * env * slow
    return out


def _chime(n: int, start: float) -> np.ndarray:
    out = np.zeros(n)
    for k, (freq, offset) in enumerate([(659.3, 0.0), (523.3, 0.45), (392.0, 0.9)]):
        s = int((start + offset) * SR)
        length = int(1.4 * SR)
        if s >= n:
            break
        seg = np.arange(min(length, n - s)) / SR
        tone = np.sin(2 * np.pi * freq * seg) + 0.3 * np.sin(4 * np.pi * freq * seg)
        out[s:s + len(seg)] += tone * np.exp(-seg * 2.2)
    return out


def _horn(n: int, start: float) -> np.ndarray:
    out = np.zeros(n)
    s = int(start * SR)
    seg = np.arange(min(int(0.5 * SR), max(0, n - s))) / SR
    if len(seg):
        tone = np.sign(np.sin(2 * np.pi * 415 * seg)) * 0.5 + np.sign(np.sin(2 * np.pi * 495 * seg)) * 0.5
        out[s:s + len(seg)] = tone * np.minimum(1, seg * 30) * np.minimum(1, (seg[-1] - seg) * 30 + 0.01)
    return out


def _siren(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    f = 700 + 350 * np.sin(2 * np.pi * 0.35 * t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(phase) * 0.6


def environment(name: str, n: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if name == "airport":
        bed = _pink(n, rng) * 0.4 + _babble(n, rng, 8)
        if n > SR * 1.5:
            bed += _chime(n, rng.uniform(0.2, max(0.3, n / SR - 2.5))) * 2.5
        return bed
    if name == "traffic":
        rumble = np.cumsum(rng.standard_normal(n))
        rumble -= np.convolve(rumble, np.ones(800) / 800, mode="same")
        bed = rumble / (np.abs(rumble).max() or 1) + _pink(n, rng) * 0.3
        for _ in range(max(1, int(n / SR / 3))):
            bed += _horn(n, rng.uniform(0, max(0.1, n / SR - 0.6))) * 0.6
        return bed
    if name == "crowd":
        return _babble(n, rng, 12) + _pink(n, rng) * 0.15
    if name == "siren":
        return _siren(n) + _pink(n, rng) * 0.35 + _babble(n, rng, 3) * 0.5
    return np.zeros(n)


def mix_environment(wav: bytes, name: str, intensity: str = "medium", seed: int = 7) -> bytes:
    """Mix a background environment under speech at a target SNR."""
    if name == "none" or name not in ENVIRONMENTS:
        return wav
    speech, sr = read_wav(wav)
    if sr != SR:
        return wav
    # pad a little so the line sounds "open" before and after the caller speaks
    pad = int(0.35 * SR)
    speech = np.concatenate([np.zeros(pad), speech, np.zeros(pad)])
    noise = environment(name, len(speech), seed)
    p_speech = float(np.mean(speech[pad:-pad] ** 2)) or 1e-6
    p_noise = float(np.mean(noise ** 2)) or 1e-6
    snr = INTENSITY_SNR_DB.get(intensity, 10.0)
    noise *= np.sqrt(p_speech / (p_noise * 10 ** (snr / 10)))
    mixed = speech + noise
    mixed /= max(1.0, float(np.abs(mixed).max()) / 0.95)
    return write_wav(mixed.astype(np.float32), SR)


def concat(wavs: list[bytes], gap_s: float = 0.25) -> bytes:
    """Join clips end to end (resampled to the first clip's rate), with a short breath between them."""
    pcms, sr = [], None
    for w in wavs:
        pcm, rate = read_wav(w)
        if sr is None:
            sr = rate
        elif rate != sr:
            pcm = np.interp(np.linspace(0, len(pcm) - 1, int(len(pcm) * sr / rate)), np.arange(len(pcm)), pcm)
        pcms.append(pcm)
        pcms.append(np.zeros(int((sr or SR) * gap_s)))
    return write_wav(np.concatenate(pcms[:-1]) if pcms else np.zeros(1), sr or SR)


def truncate(wav: bytes, fraction: float) -> bytes:
    """Cut a clip short — used to model the caller barging in over the bot."""
    pcm, sr = read_wav(wav)
    cut = max(int(len(pcm) * fraction), int(0.4 * sr))
    pcm = pcm[:cut].copy()
    fade = min(len(pcm), int(0.04 * sr))
    pcm[-fade:] *= np.linspace(1, 0, fade)
    return write_wav(pcm, sr)


def split_for_asr(wav: bytes, max_s: float = 25.0) -> list[bytes]:
    """Split long audio into chunks under Prisma's 30 s limit, cutting at quiet points."""
    pcm, sr = read_wav(wav)
    limit = int(max_s * sr)
    if len(pcm) <= limit:
        return [wav]
    chunks, start = [], 0
    frame = int(0.02 * sr)
    while len(pcm) - start > limit:
        lo, hi = start + int(limit * 0.7), start + limit
        seg = pcm[lo:hi]
        energy = np.convolve(seg ** 2, np.ones(frame) / frame, mode="same")
        cut = lo + int(np.argmin(energy))
        chunks.append(write_wav(pcm[start:cut], sr))
        start = cut
    chunks.append(write_wav(pcm[start:], sr))
    return chunks
