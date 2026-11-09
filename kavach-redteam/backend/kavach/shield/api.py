"""Kavach Shield over HTTP.

Product API (what a voice-agent company calls on every turn), authenticated with an agent API key:
    POST   /api/shield/v1/sessions                     open a call (policy comes from the key)
    POST   /api/shield/v1/sessions/{id}/inbound        check what the caller said
    POST   /api/shield/v1/sessions/{id}/outbound       check what the agent is about to say
    POST   /api/shield/v1/sessions/{id}/action         may this tool run now?
    POST   /api/shield/v1/sessions/{id}/state          tell the Shield the caller passed verification
    GET    /api/shield/v1/sessions/{id}                the call's risk timeline
    DELETE /api/shield/v1/sessions/{id}                end the call (its summary is kept for the dashboard)

Operator API (KAVACH_ADMIN_KEY): agent keys, custom policies, full call timelines.
Playground (anyone, rate-limited): try the built-in policies on single lines.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import store
from ..config import settings
from ..security import is_admin, limiter, require_admin
from . import core
from .policies import BUILTIN, PolicyError, validate

router = APIRouter(prefix="/api/shield")
KEY_RATE = (1200, 60)                     # calls per key per minute: a busy agent makes ~3 per turn


def get_policy(pid: str) -> dict | None:
    if pid in BUILTIN:
        return BUILTIN[pid]
    return next((p for p in store.shield_policies() if p["id"] == pid), None)


# ---- agent API keys -----------------------------------------------------------------------------------------------------
def _hash(key: str) -> str:
    return hmac.new(settings.signing_key.encode(), f"shield-key:{key}".encode(), hashlib.sha256).hexdigest()


def new_key(policy: str, name: str) -> tuple[str, str]:
    kid = "key_" + secrets.token_hex(6)
    key = "kv_live_" + secrets.token_urlsafe(32)
    store.shield_key_add(kid, policy, name, key[:16], _hash(key))
    return kid, key


def authenticate(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Send your Kavach Shield key as 'Authorization: Bearer kv_live_...'.")
    key = authorization[7:].strip()
    want = _hash(key)
    row = next((r for r in store.shield_keys_by_prefix(key[:16]) if hmac.compare_digest(r["hash"], want)), None)
    if not row:
        raise HTTPException(401, "Unknown or revoked Shield key.")
    if not limiter.allow(f"shield-key|{row['id']}", *KEY_RATE):
        raise HTTPException(429, "Shield rate limit reached for this key.", headers={"Retry-After": "60"})
    return row


def _session(sid: str, owner: str) -> core.ShieldSession:
    s = core.SESSIONS.get(sid, owner)
    if not s:
        raise HTTPException(404, "No such Shield session (it ended or expired).")
    return s


_started: dict[str, str] = {}


def _finish(s: core.ShieldSession) -> dict:
    summary = s.summary()
    store.shield_call_save(summary, s.owner, _started.pop(s.id, store.now()))
    return summary


def _expired(s: core.ShieldSession) -> None:
    if s.owner == "playground":
        _started.pop(s.id, None)
        return
    _finish(s)


core.SESSIONS.on_end = _expired


# ---- product API --------------------------------------------------------------------------------------------------------
class OpenReq(BaseModel):
    mode: Literal["fast", "deep"] = "fast"
    language: Literal["en-IN", "hi-IN"] = "en-IN"
    secrets: dict[str, list[str] | str] = Field(default_factory=dict, max_length=30)


@router.post("/v1/sessions", status_code=201)
def v1_open(body: OpenReq, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    policy = get_policy(key["policy"])
    if not policy:
        raise HTTPException(409, "This key's policy no longer exists.")
    s = core.open_session(policy, key["id"], mode=body.mode, language=body.language, secrets=body.secrets)
    _started[s.id] = store.now()
    store.shield_key_used(key["id"])
    return {"session_id": s.id, "policy": policy["id"], "mode": s.mode}


class InboundReq(BaseModel):
    text: str = Field("", max_length=2000)
    asr_confidence: float | None = Field(None, ge=0, le=1)


@router.post("/v1/sessions/{sid}/inbound")
async def v1_inbound(sid: str, body: InboundReq, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    return await core.inbound(_session(sid, key["id"]), body.text, body.asr_confidence)


class OutboundReq(BaseModel):
    text: str = Field("", max_length=3000)


@router.post("/v1/sessions/{sid}/outbound")
def v1_outbound(sid: str, body: OutboundReq, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    return core.outbound(_session(sid, key["id"]), body.text)


class ActionReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@router.post("/v1/sessions/{sid}/action")
def v1_action(sid: str, body: ActionReq, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    return core.action(_session(sid, key["id"]), body.name)


class StateReq(BaseModel):
    verified: bool | None = None


@router.post("/v1/sessions/{sid}/state")
def v1_state(sid: str, body: StateReq, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    return core.set_state(_session(sid, key["id"]), body.verified)


@router.get("/v1/sessions/{sid}")
def v1_get(sid: str, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    return _session(sid, key["id"]).summary()


@router.delete("/v1/sessions/{sid}")
def v1_end(sid: str, authorization: str | None = Header(None)):
    key = authenticate(authorization)
    s = core.SESSIONS.pop(sid, key["id"])
    if not s:
        raise HTTPException(404, "No such Shield session (it ended or expired).")
    return _finish(s)


# ---- operator API -------------------------------------------------------------------------------------------------------
@router.get("/policies")
def policies(x_admin_key: str | None = Header(None)):
    builtin = list(BUILTIN.values())
    custom = store.shield_policies() if is_admin(x_admin_key) else []
    return {"policies": builtin + custom}


@router.post("/policies")
def save_policy(body: dict, x_admin_key: str | None = Header(None)):
    require_admin(x_admin_key)
    try:
        p = validate(body)
    except PolicyError as e:
        raise HTTPException(400, str(e))
    if p["id"] in BUILTIN:
        raise HTTPException(409, "That id belongs to a built-in policy.")
    store.shield_policy_save(p)
    return p


class KeyReq(BaseModel):
    policy: str = Field(..., max_length=60)
    name: str = Field(..., min_length=2, max_length=60)


@router.get("/keys")
def keys(x_admin_key: str | None = Header(None)):
    require_admin(x_admin_key)
    return store.shield_keys()


@router.post("/keys", status_code=201)
def create_key(body: KeyReq, x_admin_key: str | None = Header(None)):
    require_admin(x_admin_key)
    if not get_policy(body.policy):
        raise HTTPException(404, "No such policy.")
    kid, key = new_key(body.policy, body.name.strip())
    return {"id": kid, "key": key, "policy": body.policy,
            "note": "Shown once. Store it as a secret; Kavach keeps only a hash."}


@router.delete("/keys/{kid}")
def revoke_key(kid: str, x_admin_key: str | None = Header(None)):
    require_admin(x_admin_key)
    if not store.shield_key_revoke(kid):
        raise HTTPException(404, "No such key.")
    return {"ok": True}


@router.get("/calls")
def calls(x_admin_key: str | None = Header(None)):
    """Finished calls. Operators see every agent; visitors see only Kavach's own test calls and the playground."""
    rows = store.shield_calls(150)
    if not is_admin(x_admin_key):
        rows = [r for r in rows if r["owner"] in ("internal", "playground")]
    return rows[:100]


@router.get("/stats")
def stats():
    """Aggregates only (no call content), so anyone may see how the Shield is doing."""
    rows = store.shield_calls(5000)
    since = datetime.now(timezone.utc).timestamp() - 7 * 86400
    week = [r for r in rows if datetime.fromisoformat(r["started_at"]).timestamp() >= since]
    counts: dict[str, int] = {}
    for r in week:
        for k, v in (r.get("counts") or {}).items():
            counts[k] = counts.get(k, 0) + v
    return {"live_sessions": len(core.SESSIONS), "calls_7d": len(week),
            "escalated_7d": sum(1 for r in week if any(e.get("decision") == "escalate" for e in r.get("timeline", []))),
            "blocked_replies_7d": sum(v for k, v in counts.items() if k.startswith("out:")),
            "denied_actions_7d": counts.get("action:deny", 0), "signals_7d": counts}


# ---- playground ----------------------------------------------------------------------------------------------------------
class TryReq(BaseModel):
    policy: str = Field(..., max_length=60)
    direction: Literal["inbound", "outbound", "action"]
    text: str = Field("", max_length=1000)
    session_id: str | None = Field(None, max_length=40)
    verified: bool = False
    language: Literal["en-IN", "hi-IN"] = "en-IN"


# the playground's pretend call: Saakshi's worker also works for Bhatia ji, who pays 6,200 (a secret for this call)
PLAYGROUND_SECRETS = {"saakshi-employer-calls": {"another employer": ["Bhatia", "भाटिया"], "another employer's pay": ["6200"]}}


@router.post("/try")
async def try_it(body: TryReq):
    """Built-in policies only; a playground session keeps call-level risk across lines, like a real call."""
    if body.policy not in BUILTIN:
        raise HTTPException(404, "The playground runs the built-in policies.")
    s = core.SESSIONS.get(body.session_id, "playground") if body.session_id else None
    if not s or s.policy["id"] != body.policy:
        s = core.open_session(BUILTIN[body.policy], "playground", language=body.language,
                              secrets=PLAYGROUND_SECRETS.get(body.policy))
        _started[s.id] = store.now()
    s.verified = body.verified
    if body.direction == "inbound":
        out = await core.inbound(s, body.text)
    elif body.direction == "outbound":
        out = core.outbound(s, body.text)
    else:
        out = core.action(s, body.text.strip()[:60] or "unknown")
    return {**out, "session": s.summary()}
