"""Access, rate limits and response headers for Kavach.

Three kinds of caller:
  * visitors     may watch, run attacks within a budget, and write and replay fixes (only in the sandbox);
  * operators    (KAVACH_ADMIN_KEY) also promote fixes to live agents, manage Shield keys and see everything;
  * Shield users (an agent's API key) call the runtime guard, and only for their own agent's sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, UploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings


def is_admin(key: str | None) -> bool:
    if not settings.admin_key:
        return not settings.production          # local development with no key: the operator desk is open
    return bool(key) and hmac.compare_digest(key.encode(), settings.admin_key.encode())


def require_admin(key: str | None) -> None:
    if not is_admin(key):
        raise HTTPException(401, "Operator key required.")


def sign(purpose: str, value: str) -> str:
    return hmac.new(settings.signing_key.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    """The real visitor. Hosting proxies add it; the last X-Forwarded-For hop is the one our proxy appended."""
    h = request.headers
    for name in ("fly-client-ip", "cf-connecting-ip"):
        if h.get(name):
            return h[name].strip()
    if settings.production and h.get("x-forwarded-for"):
        return h["x-forwarded-for"].split(",")[-1].strip()
    return request.client.host if request.client else "?"


class RateLimiter:
    """Sliding-window counters in memory (Kavach runs as one process)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(self.hits) > 50_000:
            for k in [k for k, v in self.hits.items() if not v or v[-1] < now - 3600][:25_000]:
                self.hits.pop(k, None)
        return True


limiter = RateLimiter()

# (path rule, method, limit, window seconds); first match wins; every /api request also counts toward "api"
RULES: list[tuple[str, str, int, float]] = [
    ("/api/runs/*/patch", "POST", 6, 600),
    ("/api/runs", "POST", 5, 600),                      # attacks and replays: each uses Gnani + Groq for a minute
    ("/api/live/*/turn", "POST", 30, 60),
    ("/api/live", "POST", 6, 600),
    ("/api/shield/try", "POST", 60, 60),               # the public Shield playground
]


def _match(rule: str, path: str) -> bool:
    if "*" not in rule:
        return path.startswith(rule)
    parts, got = rule.split("/"), path.split("/")
    return len(got) >= len(parts) and all(a == "*" or a == b for a, b in zip(parts, got))


MAX_BODY = 6 * 1024 * 1024
# Who may show the app inside a frame. Default: nobody. A Hugging Face Space page frames it, so a deployment
# there sets FRAME_ANCESTORS=https://huggingface.co (only that origin, never "*").
FRAME_ANCESTORS = " ".join(o for o in os.environ.get("FRAME_ANCESTORS", "").split()
                           if re.fullmatch(r"https://[a-z0-9.-]+", o)) or "'none'"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; media-src 'self' blob: data:; "
       "connect-src 'self'; frame-ancestors " + FRAME_ANCESTORS + "; base-uri 'self'; form-action 'self'; object-src 'none'")


def _slow_down(window: float) -> JSONResponse:
    return JSONResponse({"detail": "Too many requests. Please wait a moment and try again."}, status_code=429,
                        headers={"Retry-After": str(int(window))})


class Guard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path, method = request.url.path, request.method
        try:
            if int(request.headers.get("content-length") or 0) > MAX_BODY:
                return JSONResponse({"detail": "That upload is too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "bad request"}, status_code=400)
        if path.startswith("/api/") and not path.startswith("/api/shield/v1/"):   # Shield keys have their own limits
            ip = client_ip(request)
            if not is_admin(request.headers.get("x-admin-key")):
                for rule, methods, limit, window in RULES:
                    if method in methods and _match(rule, path):
                        if not limiter.allow(f"{rule}|{ip}", limit, window):
                            return _slow_down(window)
                        break
            if not limiter.allow(f"api|{ip}", 600, 60):
                return _slow_down(60)
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        if FRAME_ANCESTORS == "'none'":
            h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not path.startswith("/api/"):
            h.setdefault("Content-Security-Policy", CSP)
        if settings.production:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if path.startswith("/api/") and "cache-control" not in h:
            h["Cache-Control"] = "no-store"
        return response


async def read_wav(f: UploadFile, limit: int = MAX_BODY) -> bytes:
    data = bytearray()
    while chunk := await f.read(256 * 1024):
        data += chunk
        if len(data) > limit:
            raise HTTPException(413, "That recording is too long.")
    if bytes(data[:4]) != b"RIFF" or bytes(data[8:12]) != b"WAVE":
        raise HTTPException(400, "audio must be a 16-bit PCM WAV")
    return bytes(data)
