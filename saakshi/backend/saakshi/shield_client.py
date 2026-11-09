"""Kavach Shield inside Saakshi: the runtime guard on every employer call.

Saakshi sends Shield what the employer said (inbound), asks before it confirms a record or records an amount
(actions), and lets Shield check the brain's free-text answers before they're spoken (outbound). The worker's other
employers and their pay are registered as this call's secrets, so they can never be spoken.

Fail-safe: every request has a 2 second budget. If Shield is slow or down the call carries on under Saakshi's own
local protections (the agent version's gates), and the miss is logged. A call never waits on the guard.
"""

from __future__ import annotations

import httpx

from . import store
from .config import settings

TIMEOUT = httpx.Timeout(2.0, connect=1.0)
_client: httpx.AsyncClient | None = None


def configured() -> bool:
    return bool(settings.shield_url and settings.shield_key)


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=f"{settings.shield_url}/api/shield/v1", timeout=TIMEOUT,
                                    headers={"Authorization": f"Bearer {settings.shield_key}"})
    return _client


async def _call(method: str, path: str, body: dict | None, call_id: str) -> dict | None:
    try:
        r = await _http().request(method, path, json=body)
        if r.status_code < 400:
            return r.json()
        why = f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        why = type(e).__name__
    store.log("call.shield", f"Kavach Shield unavailable ({why}); local protections only", call_id=call_id)
    return None


async def open_session(call_id: str, language: str, secrets: dict[str, list[str]]) -> str | None:
    out = await _call("POST", "/sessions", {"language": language if language in ("hi-IN", "en-IN") else "en-IN",
                                             "secrets": secrets, "mode": "fast"}, call_id)
    return out["session_id"] if out else None


async def inbound(sid: str, text: str, call_id: str) -> dict | None:
    return await _call("POST", f"/sessions/{sid}/inbound", {"text": text[:2000]}, call_id)


async def outbound(sid: str, text: str, call_id: str) -> dict | None:
    return await _call("POST", f"/sessions/{sid}/outbound", {"text": text[:3000]}, call_id)


async def action(sid: str, name: str, call_id: str) -> dict | None:
    return await _call("POST", f"/sessions/{sid}/action", {"name": name}, call_id)


async def close(sid: str, call_id: str) -> None:
    await _call("DELETE", f"/sessions/{sid}", None, call_id)


def secrets_for(worker_ids: list[str], employer_id: str) -> dict[str, list[str]]:
    """Everything about the worker this employer must not hear: her other employers and what they pay (from her
    structured records; names never come from parsing speech, which could catch this employer's own name)."""
    names, pay = [], []
    for wid in worker_ids:
        for e in store.worker_entries(wid):
            if e["employer_id"] == employer_id or e["status"] == "withdrawn":
                continue
            emp = store.get_employer(e["employer_id"]) or {}
            if emp.get("name") and emp["name"] not in names:
                names.append(emp["name"])
            amt = str(int(round(e["amount"])))
            if amt not in pay:
                pay.append(amt)
    return {k: v[:10] for k, v in (("another employer", names), ("another employer's pay", pay)) if v}
