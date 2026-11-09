"""Who may see what, how often anyone may ask, and the headers every response carries.

Two kinds of data live in one database:
  * demo data (seeded "Sunita", red-team runs): `sim_group` is set. Anyone may watch and drive it, so judges
    and visitors can try the whole product without an account.
  * real people: only the worker herself (her login) or an operator (SAAKSHI_ADMIN_KEY) may see it.
"""

from __future__ import annotations

import hmac
import os
import re
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, UploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import store
from .config import settings


# ---- operator key -----------------------------------------------------------------------------------------------
def is_admin(key: str | None) -> bool:
    if not settings.admin_key:
        return not settings.production          # local development with no key: the desk is open
    return bool(key) and hmac.compare_digest(key.encode(), settings.admin_key.encode())


# ---- demo vs real -----------------------------------------------------------------------------------------------
def demo_worker(wid: str | None) -> bool:
    w = store.get_worker(wid) if wid else None
    return bool(w and w.get("sim_group"))


def demo_employer(eid: str | None) -> bool:
    e = store.get_employer(eid) if eid else None
    return bool(e and e.get("sim_group"))


def call_scope(cid: str | None) -> tuple[bool, set[str]]:
    """(is this a demo call, which workers it is about)."""
    c = store.get_call(cid) if cid else None
    if not c:
        return False, set()
    wids = {e["worker_id"] for e in (store.get_entry(x) for x in c["entry_ids"]) if e}
    return demo_employer(c["employer_id"]), wids


def sandboxed(entity_id: str | None) -> bool:
    """Kavach's sandbox worlds live in the attack lab only, not on the desk, the demo or the graph."""
    if not entity_id:
        return False
    row = store.get_worker(entity_id) if entity_id.startswith("w_") else store.get_employer(entity_id)
    return bool(row and row.get("sim_group") == "kavach")


def sandboxed_call(c: dict) -> bool:
    return sandboxed(c.get("employer_id"))


def sandboxed_event(e: dict) -> bool:
    if e.get("call_id"):
        c = store.get_call(e["call_id"])
        if c and sandboxed_call(c):
            return True
    return sandboxed(e.get("worker_id")) or sandboxed(e.get("employer_id"))


class Viewer:
    """Who is looking: an operator, a logged-in worker, or anyone."""

    def __init__(self, admin: bool = False, wid: str | None = None):
        self.admin, self.wid = admin, wid

    def sees_worker(self, wid: str | None) -> bool:
        return self.admin or (wid is not None and wid == self.wid) or demo_worker(wid)

    def sees_employer(self, eid: str | None) -> bool:
        return self.admin or demo_employer(eid)

    def sees_call(self, cid: str | None) -> bool:
        if self.admin:
            return True
        demo, wids = call_scope(cid)
        return demo or (self.wid is not None and self.wid in wids)

    def sees_event(self, ev: dict) -> bool:
        """A live or logged event: shown if everything it names is visible; events that name nobody are public."""
        if self.admin:
            return True
        wids = [w for w in [ev.get("worker_id"), *(ev.get("worker_ids") or [])] if w]
        named = bool(wids or ev.get("employer_id") or ev.get("call_id"))
        if not named:
            return True
        if ev.get("call_id") and not self.sees_call(ev["call_id"]):
            return False
        if ev.get("employer_id") and not self.sees_employer(ev["employer_id"]) and not ev.get("call_id"):
            return False
        return all(self.sees_worker(w) for w in wids)


# ---- client address & rate limits -------------------------------------------------------------------------------
def client_ip(request: Request) -> str:
    """The real visitor. Hosting proxies put it in a header; the last X-Forwarded-For hop is the one the
    proxy itself added (earlier hops are whatever the client claimed)."""
    h = request.headers
    for name in ("fly-client-ip", "cf-connecting-ip"):
        if h.get(name):
            return h[name].strip()
    if settings.production and h.get("x-forwarded-for"):
        return h["x-forwarded-for"].split(",")[-1].strip()
    return request.client.host if request.client else "?"


class RateLimiter:
    """Sliding-window counters in memory (Saakshi runs as one process)."""

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
        if len(self.hits) > 50_000:                       # forget idle visitors
            for k in [k for k, v in self.hits.items() if not v or v[-1] < now - 3600][:25_000]:
                self.hits.pop(k, None)
        return True


limiter = RateLimiter()

# (path prefix or exact, methods, limit, window seconds). The first match decides; all /api also hits "api".
RULES: list[tuple[str, str, int, float]] = [
    ("/api/auth/", "POST", 10, 60),                  # login / join
    ("/api/workers/*/delete", "POST", 5, 600),
    ("/api/workers/*/journal", "POST", 30, 60),      # speech + model per turn
    ("/api/workers/*/welcome", "POST", 10, 60),
    ("/api/c/*/voice", "POST", 10, 60),
    ("/api/c/*/intro", "POST", 10, 60),
    ("/api/c/", "POST", 30, 60),
    ("/api/calls/*/reply", "POST", 30, 60),
    ("/api/calls/*/answer", "POST", 20, 60),
    ("/api/demo/voice", "POST", 40, 600),
    ("/api/demo/seed", "POST", 3, 600),
    ("/api/redteam/run", "POST", 2, 600),
    ("/api/showcase/", "GET", 30, 60),
    ("/api/harness/sessions", "POST", 120, 60),        # Kavach (key-protected); generous, it drives whole calls
]
GLOBAL_COOLDOWN = {"/api/demo/seed": 60.0, "/api/redteam/run": 300.0}   # shared by everyone: these reset demo data
_last_global: dict[str, float] = {}


def _match(rule: str, path: str) -> bool:
    if "*" not in rule:
        return path.startswith(rule)
    parts, got = rule.split("/"), path.split("/")
    return len(got) >= len(parts) and all(a == "*" or a == b for a, b in zip(parts, got))


MAX_BODY = 6 * 1024 * 1024        # a minute of 16 kHz speech is ~2 MB


class Guard(BaseHTTPMiddleware):
    """Body size cap, rate limits and security headers for every request."""

    async def dispatch(self, request: Request, call_next):
        path, method = request.url.path, request.method
        try:
            if int(request.headers.get("content-length") or 0) > MAX_BODY:
                return JSONResponse({"detail": "That upload is too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "bad request"}, status_code=400)
        if path.startswith("/api/") or path.startswith("/tel/"):
            ip = client_ip(request)
            if not is_admin(request.headers.get("x-admin-key")):
                for rule, methods, limit, window in RULES:
                    if method in methods and _match(rule, path):
                        if not limiter.allow(f"{rule}|{ip}", limit, window):
                            return _slow_down(window)
                        break
                cool = GLOBAL_COOLDOWN.get(path)
                if cool and method == "POST":
                    if time.monotonic() - _last_global.get(path, -1e9) < cool:
                        return _slow_down(cool)
                    _last_global[path] = time.monotonic()
            if not limiter.allow(f"api|{ip}", 600, 60):
                return _slow_down(60)
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        if FRAME_ANCESTORS == "'none'":
            h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")          # confirmation and share links carry their token
        h.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not path.startswith("/api/"):
            h.setdefault("Content-Security-Policy", CSP)
        if settings.production:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if path.startswith("/api/") and "cache-control" not in h:
            h["Cache-Control"] = "no-store"
        return response


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


# ---- uploads ----------------------------------------------------------------------------------------------------
async def read_wav(f: UploadFile, limit: int = MAX_BODY) -> bytes:
    """Read an uploaded recording without trusting its declared size, and insist on WAV."""
    data = bytearray()
    while chunk := await f.read(256 * 1024):
        data += chunk
        if len(data) > limit:
            raise HTTPException(413, "That recording is too long.")
    if not bytes(data[:4]) == b"RIFF" or bytes(data[8:12]) != b"WAVE":
        raise HTTPException(400, "audio must be WAV")
    return bytes(data)


# ---- live-stream tickets ------------------------------------------------------------------------------------------
def _ticket_sig(body: str) -> str:
    return hmac.new(settings.signing_key.encode(), f"stream:{body}".encode(), "sha256").hexdigest()[:32]


def ticket(admin: bool, wid: str | None, hours: int = 24) -> str:
    body = f"{int(admin)}:{wid or ''}:{int(time.time()) + hours * 3600}"
    return f"{body}:{_ticket_sig(body)}"


def from_ticket(t: str | None) -> Viewer:
    """Visitors (no or bad ticket) see the demo; a valid ticket adds a worker's own events, or everything."""
    try:
        a, wid, exp, sig = (t or "").split(":")
        body = f"{a}:{wid}:{exp}"
        if hmac.compare_digest(_ticket_sig(body), sig) and int(exp) > time.time():
            return Viewer(admin=a == "1", wid=wid or None)
    except ValueError:
        pass
    return Viewer()
