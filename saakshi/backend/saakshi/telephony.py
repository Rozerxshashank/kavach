"""Real phone lines via Twilio Programmable Voice.

Saakshi's call engine is turn-based (Saakshi speaks → the other person answers),
which maps cleanly onto plain TwiML, so no media-streaming server is needed:

    Saakshi line ──<Play> Timbre audio
    their answer ──<Record> → recording (8 kHz phone audio) → Prisma → call engine
    next line    ──<Play> … until the engine says the call is done → <Hangup/>

Two directions:
  * outbound: Saakshi rings an employer's real number to confirm a record
  * inbound:  a worker calls Saakshi's number from any phone (feature phones too)
              and logs work by voice — no app, no internet, no literacy needed

Webhooks are authenticated with Twilio's X-Twilio-Signature (HMAC-SHA1 over the
URL + sorted form params, keyed with the auth token).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from xml.sax.saxutils import escape

import httpx

from .config import settings

API = "https://api.twilio.com/2010-04-01"


class TelephonyError(RuntimeError):
    pass


def public(url: str | None) -> str | None:
    """Our /audio/... paths as absolute URLs Twilio can fetch."""
    if not url:
        return None
    return url if url.startswith("http") else f"{settings.public_base_url}{url}"


# ---- webhook security ----------------------------------------------------------------------
def signature(url: str, params: dict[str, str], token: str) -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def valid_request(url: str, params: dict[str, str], header: str | None) -> bool:
    if not settings.twilio_token:
        return False
    return hmac.compare_digest(signature(url, params, settings.twilio_token), header or "")


# ---- TwiML ------------------------------------------------------------------------------------
def twiml(*verbs: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(verbs) + "</Response>"


def play(url: str | None) -> str:
    u = public(url)
    return f"<Play>{escape(u)}</Play>" if u else ""


def record(action: str, max_len: int = 15) -> str:
    # silence ends the turn quickly; no beep so it feels like a conversation, not voicemail
    return (f'<Record action="{escape(settings.public_base_url + action)}" method="POST" maxLength="{max_len}" '
            f'timeout="3" playBeep="false" trim="trim-silence" />'
            f'<Redirect method="POST">{escape(settings.public_base_url + action + ("&" if "?" in action else "?") + "silent=1")}</Redirect>')


def hangup() -> str:
    return "<Hangup/>"


# ---- REST ---------------------------------------------------------------------------------------
def _auth() -> tuple[str, str]:
    if not settings.telephony:
        raise TelephonyError("Telephony is not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                             "TWILIO_FROM_NUMBER, SAAKSHI_PUBLIC_URL).")
    return settings.twilio_sid, settings.twilio_token


async def place_call(to: str, call_id: str) -> str:
    """Dial an employer. Answering-machine detection lets us treat voicemail as 'no answer'."""
    sid, token = _auth()
    base = settings.public_base_url
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{API}/Accounts/{sid}/Calls.json", auth=(sid, token), data={
            "To": to, "From": settings.twilio_from,
            "Url": f"{base}/tel/call/{call_id}/answer",
            "StatusCallback": f"{base}/tel/call/{call_id}/status",
            "StatusCallbackEvent": "completed",
            "MachineDetection": "Enable",
            "Timeout": "30",
        })
    if r.status_code >= 400:
        raise TelephonyError(f"Twilio refused the call: {r.text[:300]}")
    return r.json()["sid"]


async def fetch_recording(recording_url: str) -> bytes:
    """Download a caller's recorded answer as WAV (Twilio serves 8 kHz phone audio)."""
    url = recording_url if recording_url.endswith(".wav") else recording_url + ".wav"
    auth = (settings.twilio_sid, settings.twilio_token) if url.startswith("https://api.twilio.com") else None
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        for _ in range(4):                       # recordings can take a moment to become available
            r = await c.get(url, auth=auth)
            if r.status_code == 200 and r.content[:4] == b"RIFF":
                return r.content
            import asyncio
            await asyncio.sleep(0.6)
    raise TelephonyError(f"could not fetch recording ({r.status_code})")
