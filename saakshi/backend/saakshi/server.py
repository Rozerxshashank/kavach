"""HTTP API, live event stream (SSE) and static hosting for the Saakshi web app."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import accounts, agent, audio, harness, security, calls, gnani, journal, langs, lines, links, passport, showcase, payments, simulate, store, telephony, trust
from .tel_routes import router as tel_router
from . import llm
from .bus import bus
from .config import settings

app = FastAPI(title="Saakshi", version="1.0.0",
              docs_url=None if settings.production else "/docs", redoc_url=None,
              openapi_url=None if settings.production else "/openapi.json")
if not settings.production:      # the dev servers on other ports; in production the UI is served from this origin
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(security.Guard)
app.include_router(tel_router)


@app.on_event("startup")
def recover_interrupted_calls() -> None:
    """A restart drops in-flight calls; put them back in the queue instead of leaving them 'on call' forever."""
    for c in store.list_calls(1000):
        if c["status"] in ("ringing", "in_call"):
            store.update_call(c["id"], status="queued")
            for xid in c["entry_ids"]:
                e = store.get_entry(xid)
                if e and e["status"] == "calling":
                    store.update_entry(xid, status="pending")
            store.log("call.recovered", "A call interrupted by a server restart was put back in the queue",
                      employer_id=c["employer_id"], call_id=c["id"])

@app.on_event("startup")
def harness_startup() -> None:
    agent.ensure_versions()
    harness.cleanup_orphans()                         # no sandbox call survives a restart


@app.on_event("startup")
async def daily_backup() -> None:
    """A copy of the database every day, the last seven kept (data/backups)."""
    async def loop():
        while True:
            try:
                await asyncio.to_thread(store.backup)
            except Exception as exc:  # a failed backup must never take the server down
                store.log("backup.failed", f"Database backup failed: {exc}")
            await asyncio.sleep(6 * 3600)
    asyncio.get_running_loop().create_task(loop())


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    ok = store.healthy()
    if not ok:
        raise HTTPException(503, "database unavailable")
    return {"ok": True, "gnani": bool(settings.gnani_api_key), "llm": bool(settings.groq_api_key)}


@app.on_event("startup")
async def warm_showcase() -> None:
    """Voice the public showcase in the background (cached on disk after the first run)."""
    import asyncio as _a
    _a.get_running_loop().create_task(showcase.warm())


BUSY_SPEECH = "The speech service is busy. Please try again in a moment, or type instead."
BUSY_BRAIN = "Saakshi is busy right now. Please try again in a moment."
lines.EXTRA += [BUSY_SPEECH, BUSY_BRAIN]

WORKER_VOICE = {"hi-IN": "Urmila", "en-IN": "Gauri"}          # other languages: Urmila


def _clip(folder: str, name: str, wav: bytes) -> dict:
    d = settings.audio_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(wav)
    return {"url": f"/audio/{folder}/{name}", "duration": audio.duration_s(wav), "peaks": audio.peaks(wav, 64)}


async def _say(text: str, lang: str, folder: str, name: str) -> dict | None:
    """Saakshi's voice is best-effort: if Timbre is busy the person still gets the text and can carry on."""
    try:
        res = await gnani.timbre_speak(text, voice=calls.AGENT_VOICE, language=lang)
    except gnani.GnaniError:
        return None
    return _clip(folder, name, res.audio)


def _stamp() -> str:
    return datetime.now().strftime("%H%M%S%f")[:-3]


# ---- meta ------------------------------------------------------------------------------
def _lan_ip() -> str | None:
    """This machine's address on the local network, so a phone on the same WiFi can open the app."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))          # no packet is sent; this just picks the outgoing interface
            ip = sk.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


@app.get("/api/meta")
def meta():
    return {
        "ready": {"gnani": bool(settings.gnani_api_key), "llm": bool(settings.groq_api_key),
                  "telephony": settings.telephony},
        "hotline": settings.twilio_from if settings.telephony else None,
        "lan_ip": None if settings.production else _lan_ip(),
        "languages": [{"code": k, **v} for k, v in langs.LANGS.items()],
        "models": {"tts": settings.tts_model, "asr": "prisma-v2.5", "agent": settings.agent_model,
                   "fast": settings.fast_model, "agent_voice": calls.AGENT_VOICE},
        "counts": {"workers": len(store.list_workers()), "employers": len(store.list_employers()),
                   "entries": len(store.all_entries()), "calls": len(store.list_calls(1000))},
    }


@app.get("/api/stats")
def stats():
    """Live numbers for the site, computed from the records (not marketing)."""
    ws = store.list_workers()
    entries = [e for e in store.all_entries() if e["status"] != "withdrawn"]
    ps = [passport.build(w["id"])["stats"] for w in ws]
    verified = [e for e in entries if e["status"] in ("verified", "corrected")]
    return {
        "workers": len(ws), "records": len(entries), "verified": len(verified),
        "employers_confirmed": len({e["employer_id"] for e in verified}),
        "verified_income_monthly": sum(p["avg_monthly_verified"] for p in ps if not p["fraud_flags"]),
        "levels": {k: sum(p["levels"].get(k, 0) for p in ps) for k in range(4)},
        "flagged_workers": sum(1 for p in ps if p["fraud_flags"]),
        "calls": len(store.list_calls(5000)),
        "languages": len(langs.LANGS),
        "gnani": gnani.usage(),
    }


@app.get("/api/showcase/story")
async def showcase_story(lang: str = "hi-IN"):
    try:
        return await showcase.story(lang)
    except gnani.GnaniError:
        raise HTTPException(503, "The voice service is busy; try again in a moment.")


@app.get("/api/showcase/hello/{lang}")
async def showcase_hello(lang: str):
    try:
        return await showcase.hello(lang)
    except gnani.GnaniError:
        raise HTTPException(503, "The voice service is busy; try again in a moment.")


class DemoVoice(BaseModel):
    text: str
    voice: str = "Urmila"
    language: langs.LangCode = "hi-IN"


@app.post("/api/demo/voice")
async def demo_voice(body: DemoVoice, x_admin_key: str | None = Header(None)):
    """The demo autopilot's actors: Timbre speaks a worker's or employer's line, which the page then plays
    and sends back as audio, so it goes through Prisma exactly like a real voice."""
    if body.voice not in ("Urmila", "Vikrant", "Gauri", "Omkar", "Farhan", "Jatin", "Shweta", "Kartik"):
        raise HTTPException(400, "unknown voice")
    import hashlib
    text = body.text.strip()[:300]
    name = "actor_" + hashlib.sha256(f"{body.voice}|{body.language}|{text}".encode()).hexdigest()[:20] + ".wav"
    cached = settings.audio_dir / "demo" / name
    if cached.exists():                                   # the autopilot says the same lines every run
        wav = cached.read_bytes()
        return {"url": f"/audio/demo/{name}", "duration": audio.duration_s(wav), "peaks": audio.peaks(wav, 64)}
    try:
        sp = await gnani.timbre_speak(text, voice=body.voice, language=body.language)
    except gnani.GnaniError:
        raise HTTPException(503, "voice unavailable right now")
    return _clip("demo", name, sp.audio)


@app.post("/api/demo/seed")
async def seed():
    """Resets the demo data only (sim_group). Open to visitors; the guard lets it run once a minute."""
    return await simulate.seed_demo(with_voice=bool(settings.gnani_api_key))


# ---- access ------------------------------------------------------------------------------
is_admin = security.is_admin


def viewer(admin: str | None, token: str | None = None) -> security.Viewer:
    return security.Viewer(is_admin(admin), accounts.worker_from_token(token))


def require_worker(wid: str, token: str | None, admin: str | None) -> dict:
    w = store.get_worker(wid)
    if not w:
        raise HTTPException(404, "worker not found")
    if accounts.worker_from_token(token) == wid or is_admin(admin):
        return w
    raise HTTPException(401, "Please log in with your phone number and PIN.")


def require_admin(admin: str | None) -> None:
    if not is_admin(admin):
        raise HTTPException(401, "Operator key required.")


def _base_url(request: Request) -> str:
    """The address people actually use: configured public URL, else what the browser/proxy says it visited."""
    from urllib.parse import urlsplit
    if settings.public_base_url:
        return settings.public_base_url
    h = request.headers
    if h.get("x-forwarded-host"):
        return f"{h.get('x-forwarded-proto', 'https')}://{h['x-forwarded-host']}"
    for src in (h.get("origin"), h.get("referer")):
        if src:
            u = urlsplit(src)
            if u.scheme and u.netloc:
                return f"{u.scheme}://{u.netloc}"
    return str(request.base_url).rstrip("/")


class Join(BaseModel):
    name: str
    phone: str
    pin: str
    language: langs.LangCode = "hi-IN"
    role: str = "domestic"
    city: str = ""
    state: str = ""
    upi_id: str = ""


@app.post("/api/auth/join")
def join(body: Join):
    if len(body.name.strip()) < 2:
        raise HTTPException(400, "Please enter your name.")
    if not store.normalize_phone(body.phone):
        raise HTTPException(400, "Please enter a 10-digit Indian mobile number.")
    if not accounts.valid_pin(body.pin):
        raise HTTPException(400, "Choose a 4–6 digit PIN that isn't all the same digit.")
    if body.upi_id and not accounts.valid_upi(body.upi_id.strip()):
        raise HTTPException(400, "That UPI ID doesn't look right. It looks like name@bank.")
    if len(body.name) > 80 or len(body.city) > 80 or len(body.state) > 80:
        raise HTTPException(400, "That's too long.")
    if store.worker_by_phone(body.phone):
        raise HTTPException(409, "This number already has a Saakshi record. Log in instead.")
    w = store.create_worker(body.name.strip(), body.phone, body.language, body.role, body.city.strip() or "—",
                            body.state.strip() or "—", upi_id=body.upi_id.strip() or None,
                            pin_hash=accounts.hash_pin(body.pin))
    return {"worker": _public_worker(w), "token": accounts.token_for(w["id"])}


class Login(BaseModel):
    phone: str
    pin: str


@app.post("/api/auth/login")
def login(body: Login):
    key = store.normalize_phone(body.phone) or body.phone[:20]
    wait = accounts.locked_for(key)
    if wait:
        raise HTTPException(429, f"Too many wrong PINs. Try again in {wait // 60 + 1} minutes, or ask a helper to reset it.")
    w = store.worker_by_phone(body.phone)
    ok = bool(w and accounts.check_pin(body.pin, w.get("pin_hash")))
    accounts.record_attempt(key, ok)
    if not ok:
        raise HTTPException(401, "Phone number or PIN is wrong.")
    return {"worker": _public_worker(w), "token": accounts.token_for(w["id"])}


def _public_worker(w: dict) -> dict:
    return {k: v for k, v in w.items() if k not in ("pin_hash", "device", "sim_group")}


class Profile(BaseModel):
    upi_id: str | None = None
    language: langs.LangCode | None = None


@app.post("/api/workers/{wid}/profile")
def profile(wid: str, body: Profile, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    require_worker(wid, x_worker_token, x_admin_key)
    if body.upi_id is not None:
        if body.upi_id and not accounts.valid_upi(body.upi_id.strip()):
            raise HTTPException(400, "That UPI ID doesn't look right. It looks like name@bank.")
        store.update_worker(wid, upi_id=body.upi_id.strip() or None)
    if body.language:
        store.update_worker(wid, language=body.language)
        if wid in journal.SESSIONS:                      # the ongoing conversation switches language too
            journal.SESSIONS[wid].worker = store.get_worker(wid)
    return _public_worker(store.get_worker(wid))  # type: ignore[arg-type]


@app.post("/api/workers/{wid}/entries/{xid}/withdraw")
async def withdraw(wid: str, xid: str, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    """The worker takes back a record she got wrong. It stays in the tamper-evident chain, marked withdrawn."""
    require_worker(wid, x_worker_token, x_admin_key)
    e = store.get_entry(xid)
    if not e or e["worker_id"] != wid:
        raise HTTPException(404, "record not found")
    store.update_entry(xid, status="withdrawn")
    for l in store.worker_links(wid):
        if xid in l["entry_ids"] and l["status"] != "done":
            remaining = [x for x in l["entry_ids"] if (store.get_entry(x) or {}).get("status") != "withdrawn"]
            if not remaining:
                store.update_link(l["token"], status="done", outcome="withdrawn", done_at=store.now())
    for c in store.list_calls(1000):
        if xid in c["entry_ids"] and c["status"] in ("queued", "callback"):
            if all((store.get_entry(x) or {}).get("status") == "withdrawn" for x in c["entry_ids"]):
                store.update_call(c["id"], status="done", outcome="withdrawn")
    store.log("entry.withdrawn", "A record was withdrawn by the worker", worker_id=wid)
    trust.recompute()
    await bus.emit("world.changed")
    return {"ok": True}


class DeleteAccount(BaseModel):
    pin: str


@app.post("/api/workers/{wid}/delete")
async def delete_account(wid: str, body: DeleteAccount, x_worker_token: str | None = Header(None),
                         x_admin_key: str | None = Header(None)):
    """Erase everything about this worker (her right under India's DPDP Act). Needs her PIN again."""
    w = require_worker(wid, x_worker_token, x_admin_key)
    key = w["phone"]
    if accounts.locked_for(key):
        raise HTTPException(429, "Too many wrong PINs. Try again later.")
    if w.get("pin_hash"):
        ok = accounts.check_pin(body.pin, w["pin_hash"])
        accounts.record_attempt(key, ok)
        if not ok:
            raise HTTPException(401, "PIN is wrong.")
    import shutil
    for folder in store.delete_worker_everything(wid):
        shutil.rmtree(settings.audio_dir / folder, ignore_errors=True)
    journal.SESSIONS.pop(wid, None)
    await bus.emit("world.changed")
    return {"ok": True}


class PinReset(BaseModel):
    pin: str


@app.post("/api/admin/workers/{wid}/pin")
def admin_reset_pin(wid: str, body: PinReset, x_admin_key: str | None = Header(None)):
    """A helper (union / NGO desk) resets a forgotten PIN after checking the person in front of them."""
    require_admin(x_admin_key)
    if not store.get_worker(wid):
        raise HTTPException(404, "worker not found")
    if not accounts.valid_pin(body.pin):
        raise HTTPException(400, "Choose a 4–6 digit PIN that isn't all the same digit.")
    store.update_worker(wid, pin_hash=accounts.hash_pin(body.pin))      # new salt: old logins stop working
    store.clear_login_fails(store.get_worker(wid)["phone"])
    store.log("worker.pin_reset", "PIN reset by an operator", worker_id=wid)
    return {"ok": True}


@app.post("/api/demo/token/{wid}")
def demo_token(wid: str, x_admin_key: str | None = Header(None)):
    """Operators can open any worker's app; visitors can open the demo workers' (seeded, not real people)."""
    if not store.get_worker(wid):
        raise HTTPException(404, "worker not found")
    if not (is_admin(x_admin_key) or security.demo_worker(wid)):
        raise HTTPException(401, "Operator key required.")
    return {"token": accounts.token_for(wid, days=1)}


# ---- workers ----------------------------------------------------------------------------
class NewWorker(BaseModel):
    name: str
    phone: str
    language: langs.LangCode = "hi-IN"
    role: str = "domestic"
    city: str = ""
    state: str = ""


@app.get("/api/workers")
def workers(x_admin_key: str | None = Header(None)):
    """Operators see everyone; visitors see the demo workers."""
    admin = is_admin(x_admin_key)
    out = []
    for w in store.list_workers():
        if (not admin and not w.get("sim_group")) or w.get("sim_group") == "kavach":
            continue
        w = _public_worker(w)
        p = passport.build(w["id"])
        out.append({**w, "stats": p["stats"]})
    return out


@app.post("/api/workers")
def new_worker(body: NewWorker, x_admin_key: str | None = Header(None)):
    """An operator adds a worker without a PIN (people sign themselves up through /api/auth/join)."""
    require_admin(x_admin_key)
    try:
        return store.create_worker(body.name, body.phone, body.language, body.role, body.city or "—", body.state or "—")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/workers/{wid}")
async def worker(wid: str, request: Request, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    w = _public_worker(require_worker(wid, x_worker_token, x_admin_key))
    entries = store.worker_entries(wid)
    for e in entries:
        e["reasons"] = json.loads(e["reasons"] or "[]")
        if w["language"] != "en-IN":                    # the reasons, in the worker's own language
            for r in e["reasons"]:
                r["text"] = lines.tr_any(w["language"], r.get("tpl") or r["text"], **(r.get("vars") or {}))
        e["claimed"] = json.loads(e["claimed"] or "{}")
        e["employer_says"] = json.loads(e["employer_says"]) if e.get("employer_says") else None
    ids = {e["id"] for e in entries}
    wcalls = [c for c in store.list_calls(500) if set(c["entry_ids"]) & ids]
    s = journal.SESSIONS.get(wid)
    base = _base_url(request)
    wlinks = []
    for l in store.worker_links(wid):
        emp = store.get_employer(l["employer_id"]) or {}
        url = f"{base}/c/{l['token']}"
        text = await links.message_for(w, emp, url)
        wlinks.append({**l, "url": url, "message": text, "whatsapp": links.whatsapp_url(emp.get("phone", ""), text),
                       "employer_name": emp.get("name")})
    return {
        "worker": w, "entries": entries, "links": wlinks, "passport": passport.build(wid), "calls": wcalls,
        "evidence": store.worker_evidence(wid), "shares": store.worker_shares(wid),
        "events": store.events(40, wid),
        "journal": {"state": s.state, "drafts": [d.to_dict() for d in s.drafts]} if s else None,
    }


@app.post("/api/workers/{wid}/welcome")
async def welcome(wid: str, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    w = require_worker(wid, x_worker_token, x_admin_key)
    text = await langs.localize(journal.welcome(w), w["language"])
    # the greeting never changes for a worker: synthesise once, reuse forever
    import hashlib
    name = f"welcome_{hashlib.sha1(text.encode()).hexdigest()[:10]}.wav"
    cached = settings.audio_dir / f"j_{wid}" / name
    if cached.exists():
        wav = cached.read_bytes()
        return {"say": text, "audio": {"url": f"/audio/j_{wid}/{name}", "duration": audio.duration_s(wav),
                                       "peaks": audio.peaks(wav, 64)}}
    return {"say": text, "audio": await _say(text, w["language"], f"j_{wid}", name)}


@app.post("/api/workers/{wid}/journal")
async def journal_turn(wid: str, audio_file: UploadFile | None = File(None), text: str | None = Form(None),
                       x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    w = require_worker(wid, x_worker_token, x_admin_key)
    clip = None
    heard = (text or "").strip()
    if audio_file is not None:
        wav = await security.read_wav(audio_file)
        clip = _clip(f"j_{wid}", f"worker_{_stamp()}.wav", wav)
        try:
            res = await gnani.prisma_transcribe(wav, language=w["language"])
        except gnani.GnaniError:
            raise HTTPException(503, "आवाज़ सेवा अभी व्यस्त है। थोड़ी देर में फिर बोलिए, या लिखकर भेजिए।"
                                if w["language"] == "hi-IN" else lines.tr(w["language"], BUSY_SPEECH))
        heard = res.text
    elif heard:
        # typed lines are voiced by Timbre so the employer can still hear "the worker" (best-effort)
        try:
            res = await gnani.timbre_speak(heard, voice=w.get("voice") or WORKER_VOICE.get(w["language"], "Urmila"), language=w["language"])
            clip = _clip(f"j_{wid}", f"worker_{_stamp()}.wav", res.audio)
        except gnani.GnaniError:
            clip = None
    if not heard:
        raise HTTPException(400, "nothing was heard")
    heard = heard[:600]
    from . import llm
    try:
        out = await journal.handle(w, heard, clip["url"] if clip else None)
    except llm.LLMError:
        raise HTTPException(503, "साक्षी अभी व्यस्त है। थोड़ी देर में फिर कोशिश कीजिए।"
                            if w["language"] == "hi-IN" else lines.tr(w["language"], BUSY_BRAIN))
    out["say"] = await langs.localize(out["say"], w["language"])
    out["heard"] = heard
    out["worker_audio"] = clip
    out["audio"] = await _say(out["say"], w["language"], f"j_{wid}", f"saakshi_{_stamp()}.wav")
    await bus.emit("journal.turn", worker_id=wid, state=out["state"], saved=len(out["saved"]))
    if out["saved"]:
        await bus.emit("world.changed")
    return out


class Evidence(BaseModel):
    text: str


@app.post("/api/workers/{wid}/evidence")
async def add_evidence(wid: str, body: Evidence, x_worker_token: str | None = Header(None),
                       x_admin_key: str | None = Header(None)):
    require_worker(wid, x_worker_token, x_admin_key)
    if len(body.text) > 1000:
        raise HTTPException(400, "That message is too long.")
    parsed = passport.parse_upi_sms(body.text)
    if not parsed:
        raise HTTPException(400, "That doesn't look like a payment-received SMS")
    match = passport.match_evidence(wid, parsed)
    ev = store.add_evidence(wid, "upi_sms", body.text, parsed, match)
    payments.reconcile(wid)
    trust.recompute()
    await bus.emit("world.changed")
    return {"evidence": ev, "matched_entry": match}


class ShareReq(BaseModel):
    scope: Literal["full", "income_band", "bocw"] = "full"
    audience: str = ""
    days: int = 30


@app.post("/api/workers/{wid}/shares")
def share(wid: str, body: ShareReq, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    require_worker(wid, x_worker_token, x_admin_key)
    if not 1 <= body.days <= 365 or len(body.audience) > 80:
        raise HTTPException(400, "A link lasts 1 to 365 days.")
    exp = (datetime.now(timezone.utc) + timedelta(days=body.days)).isoformat(timespec="seconds")
    s = store.create_share(wid, body.scope, body.audience or None, exp)
    store.log("share.created", f"Shared {body.scope.replace('_', ' ')} view with {body.audience or 'someone'}", worker_id=wid)
    return s


@app.delete("/api/workers/{wid}/shares/{token}")
def revoke(wid: str, token: str, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    require_worker(wid, x_worker_token, x_admin_key)
    s = store.get_share(token)
    if not s or s["worker_id"] != wid:
        raise HTTPException(404, "not found")
    store.update_share(token, revoked=1)
    store.log("share.revoked", "Share link revoked", worker_id=s["worker_id"])
    return {"ok": True}


@app.get("/api/p/{token}")
def public_passport(token: str):
    s = store.get_share(token)
    if not s:
        raise HTTPException(404, "This link does not exist.")
    if s["revoked"]:
        raise HTTPException(410, "The worker has revoked this link.")
    if s["expires_at"] and s["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(410, "This link has expired.")
    store.update_share(token, views=s["views"] + 1)
    full = passport.build(s["worker_id"])
    return {**passport.scoped(full, s["scope"]), "audience": s["audience"], "expires_at": s["expires_at"]}


# ---- employer confirmation links (public: anyone holding the link) -------------------------
@app.get("/api/c/{token}")
def link_view(token: str):
    try:
        return links.view(token)
    except KeyError:
        raise HTTPException(404, "This confirmation link doesn't exist.")


@app.post("/api/c/{token}/intro")
async def link_intro(token: str, lang: langs.LangCode | None = None):
    try:
        return await links.intro_audio(token, lang)
    except KeyError:
        raise HTTPException(404, "not found")
    except gnani.GnaniError:
        raise HTTPException(503, "voice unavailable right now")


def _open_link(token: str) -> dict:
    l = store.get_link(token)
    if not l:
        raise HTTPException(404, "This confirmation link doesn't exist.")
    if l["status"] == "done":
        raise HTTPException(409, "This record has already been answered. Thank you!")
    return l


@app.post("/api/c/{token}/voice")
async def link_voice(token: str, audio_file: UploadFile = File(...)):
    l = _open_link(token)
    wav = await security.read_wav(audio_file)
    try:
        out = await links.confirm_by_voice(token, wav)
    except gnani.GnaniError:
        raise HTTPException(503, "Speech service is busy. Please try again, or confirm with a tap.")
    if out.get("accepted"):
        await bus.emit("call.ended", call_id=None, outcome="verified", worker_ids=[l["worker_id"]])
        await bus.emit("world.changed")
    return out


@app.post("/api/c/{token}/tap")
async def link_tap(token: str):
    l = _open_link(token)
    v = links.confirm_by_tap(token)
    await bus.emit("call.ended", call_id=None, outcome="verified", worker_ids=[l["worker_id"]])
    return v


class LinkCorrection(BaseModel):
    fixes: dict[str, dict]


@app.post("/api/c/{token}/correct")
async def link_correct(token: str, body: LinkCorrection):
    l = _open_link(token)
    try:
        v = links.correct(token, body.fixes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await bus.emit("call.ended", call_id=None, outcome="corrected", worker_ids=[l["worker_id"]])
    return v


@app.post("/api/c/{token}/deny")
async def link_deny(token: str):
    l = _open_link(token)
    v = links.deny(token)
    await bus.emit("call.ended", call_id=None, outcome="disputed", worker_ids=[l["worker_id"]])
    return v


class PaymentReport(BaseModel):
    entry_id: str
    utr: str
    amount: float


@app.post("/api/c/{token}/paid")
async def link_paid(token: str, body: PaymentReport):
    l = store.get_link(token)
    if not l or body.entry_id not in l["entry_ids"]:
        raise HTTPException(404, "not found")
    try:
        payments.employer_reports_payment(body.entry_id, body.utr, body.amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    trust.recompute()
    await bus.emit("world.changed")
    return links.view(token)


# ---- employers & calls --------------------------------------------------------------------
@app.get("/api/employers")
def employers(x_admin_key: str | None = Header(None)):
    v = viewer(x_admin_key)
    out = []
    for e in store.list_employers():
        if e["kind"] == "private" or not v.sees_employer(e["id"]) or e.get("sim_group") == "kavach":
            continue
        e = {k: x for k, x in e.items() if k != "device"}
        e["pending"] = len(store.pending_calls_for(e["id"]))
        out.append(e)
    return out


@app.get("/api/calls")
def list_calls(x_admin_key: str | None = Header(None)):
    v = viewer(x_admin_key)
    out = []
    for c in store.list_calls(200):
        if not v.sees_call(c["id"]) or security.sandboxed_call(c):
            continue
        emp = store.get_employer(c["employer_id"]) or {}
        names = []
        for x in c["entry_ids"]:
            e = store.get_entry(x)
            if e:
                n = (store.get_worker(e["worker_id"]) or {}).get("name")
                if n and n not in names:
                    names.append(n)
        out.append({**c, "employer": {"id": emp.get("id"), "name": emp.get("name"), "persona": emp.get("persona"),
                                      "kind": emp.get("kind")}, "workers": names})
    return out


@app.get("/api/calls/{cid}")
def get_call(cid: str, x_admin_key: str | None = Header(None)):
    return _visible_call(cid, x_admin_key)


def _visible_call(cid: str, admin: str | None) -> dict:
    """Demo calls are open to visitors (they play the employer); real calls only to operators."""
    c = store.get_call(cid)
    if not c or not viewer(admin).sees_call(cid):
        raise HTTPException(404, "call not found")
    return c


@app.post("/api/calls/{cid}/ring")
async def ring(cid: str, mode: Literal["auto", "human", "phone"] = "human", x_admin_key: str | None = Header(None)):
    c = _visible_call(cid, x_admin_key)
    if mode == "phone":
        require_admin(x_admin_key)                       # a real phone call costs money and reaches a real person
    if c["status"] not in ("queued", "callback"):
        raise HTTPException(409, f"call is {c['status']}")
    if mode == "phone":
        emp = store.get_employer(c["employer_id"]) or {}
        if emp.get("opted_out"):
            raise HTTPException(409, "This employer asked not to be called.")
        try:
            sid = await telephony.place_call(emp["phone"], cid)
        except telephony.TelephonyError as e:
            raise HTTPException(503, str(e))
        store.update_call(cid, status="ringing", mode="phone")
        store.log("call.dialled", f"Dialling {emp.get('name')} on {emp['phone'][:6]}•••• (Twilio {sid[-6:]})",
                  employer_id=emp.get("id"), call_id=cid)
        await bus.emit("call.ringing", call_id=cid, employer_id=c["employer_id"], phone=True)
        return {"ok": True, "sid": sid}
    store.update_call(cid, status="ringing", mode=mode)
    if mode == "auto":
        asyncio.create_task(_auto(cid))
    else:
        await bus.emit("call.ringing", call_id=cid, employer_id=c["employer_id"])
    return {"ok": True}


async def _auto(cid: str):
    try:
        await calls.run_auto(cid, with_voice=True)
    except Exception as exc:  # surface failures instead of a silent stuck call
        store.update_call(cid, status="queued", outcome=f"error: {exc}")
        await bus.emit("call.error", call_id=cid, message=str(exc))


@app.post("/api/calls/{cid}/answer")
async def answer(cid: str, x_admin_key: str | None = Header(None)):
    c = _visible_call(cid, x_admin_key)
    if c["status"] != "ringing":
        raise HTTPException(409, "This call is no longer ringing.")
    return await calls.answer(cid)


@app.post("/api/calls/{cid}/decline")
async def decline(cid: str, x_admin_key: str | None = Header(None)):
    _visible_call(cid, x_admin_key)
    await calls.no_answer(cid)
    return {"ok": True}


@app.post("/api/calls/{cid}/reply")
async def reply(cid: str, audio_file: UploadFile | None = File(None), text: str | None = Form(None),
                x_admin_key: str | None = Header(None)):
    c = _visible_call(cid, x_admin_key)
    if c["status"] != "in_call":
        # e.g. the server restarted mid-call: the call was put back in the queue and will be retried
        raise HTTPException(409, "The call dropped. Saakshi will call again.")
    clip = None
    said = (text or "").strip()[:600]
    if audio_file is not None:
        wav = await security.read_wav(audio_file)
        said, clip = await calls.transcribe_employer(cid, wav)
    return await calls.employer_said(cid, said, clip)


# ---- trust, red team, log -------------------------------------------------------------------
@app.get("/api/trust/graph")
def trust_graph(x_admin_key: str | None = Header(None)):
    g = trust.graph()
    if is_admin(x_admin_key):
        hide = {n["id"] for n in g["nodes"] if security.sandboxed(n["id"])}
        return {"nodes": [n for n in g["nodes"] if n["id"] not in hide],
                "edges": [e for e in g["edges"] if e["source"] not in hide and e["target"] not in hide], "rings": g["rings"]}
    v = viewer(None)
    keep = {n["id"] for n in g["nodes"] if (v.sees_worker(n["id"]) if n["type"] == "worker" else v.sees_employer(n["id"]))
            and not security.sandboxed(n["id"])}
    return {"nodes": [n for n in g["nodes"] if n["id"] in keep],
            "edges": [e for e in g["edges"] if e["source"] in keep and e["target"] in keep],
            "rings": [r for r in g["rings"] if all(x in keep for x in r)]}


@app.post("/api/redteam/run")
async def redteam_run():
    """Synthetic workers and fraud rings only (sim_group). Open to visitors, once every five minutes."""
    if simulate.RUN.get("status") == "running":
        raise HTTPException(409, "already running")
    asyncio.create_task(simulate.red_team())
    return {"ok": True}


@app.get("/api/redteam")
def redteam_status():
    return simulate.RUN


@app.get("/api/events")
def events(x_admin_key: str | None = Header(None)):
    v = viewer(x_admin_key)
    return [e for e in store.events(400) if v.sees_event(e) and not security.sandboxed_event(e)][:120]


class StreamTicket(BaseModel):
    worker_id: str | None = None


@app.post("/api/stream/ticket")
def stream_ticket(body: StreamTicket, x_worker_token: str | None = Header(None), x_admin_key: str | None = Header(None)):
    """EventSource can't send headers, so a signed, day-long ticket in the URL says who is listening."""
    admin = is_admin(x_admin_key) and bool(security.settings.admin_key)
    wid = accounts.worker_from_token(x_worker_token)
    if body.worker_id and wid != body.worker_id:
        wid = None
    return {"ticket": security.ticket(admin, wid)}


@app.get("/api/stream")
async def stream(after: int | None = None, t: str | None = None):
    """Live events. A client that reconnects passes the last seq it saw, and gets what it missed.
    Visitors get the demo's events; a ticket (see /api/stream/ticket) adds a worker's own or everything."""
    v = security.from_ticket(t)
    if not security.settings.admin_key and not security.settings.production:
        v.admin = True                                   # local development with no operator key
    restarted = after is not None and after > bus.seq          # the server restarted since then
    start = bus.seq if after is None or restarted else after

    async def gen():
        yield f"data: {json.dumps({'type': 'hello', 'seq': bus.seq, 'restarted': restarted})}\n\n"
        async for ev in bus.stream(start):
            if not v.sees_event(ev):
                continue
            if ev.get("type", "").startswith(("call.", "journal.")) and security.sandboxed_event(ev):
                continue                                  # Kavach's sandbox calls only show in the attack lab
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- test harness for Kavach (an external red-team service) ---------------------------------------------------
def require_harness(key: str | None) -> None:
    want = settings.harness_key
    if not want:
        raise HTTPException(404, "Not Found")             # harness off: don't even admit it exists
    import hmac
    if not key or not hmac.compare_digest(key.encode(), want.encode()):
        raise HTTPException(401, "harness key required")


def _harness_call(fn):
    try:
        return fn()
    except harness.HarnessError as e:
        raise HTTPException(e.status, str(e))


class HarnessOpen(BaseModel):
    language: Literal["hi-IN", "en-IN"] = "hi-IN"
    hardening: Literal["live", "original"] | int | dict = "live"
    world: dict | None = None
    voice: bool = True
    shield: bool = False


@app.get("/api/harness/info")
def harness_info(x_harness_key: str | None = Header(None)):
    require_harness(x_harness_key)
    return harness.info()


@app.post("/api/harness/sessions")
async def harness_open(body: HarnessOpen, x_harness_key: str | None = Header(None)):
    require_harness(x_harness_key)
    try:
        return await harness.open_session(body.language, body.hardening, body.world, body.voice, body.shield)
    except harness.HarnessError as e:
        raise HTTPException(e.status, str(e))


class HarnessTurn(BaseModel):
    heard: str = Field("", max_length=2000)
    voice: bool = True


@app.post("/api/harness/sessions/{sid}/turn")
async def harness_turn(sid: str, body: HarnessTurn, x_harness_key: str | None = Header(None)):
    require_harness(x_harness_key)
    from . import llm
    try:
        return await harness.turn(sid, body.heard, body.voice)
    except harness.HarnessError as e:
        raise HTTPException(e.status, str(e))
    except llm.LLMError:
        raise HTTPException(503, "Saakshi's call brain is unavailable right now")


@app.get("/api/harness/sessions/{sid}/outcome")
def harness_outcome(sid: str, x_harness_key: str | None = Header(None)):
    require_harness(x_harness_key)
    return _harness_call(lambda: harness.outcome(sid))


@app.delete("/api/harness/sessions/{sid}")
async def harness_close(sid: str, x_harness_key: str | None = Header(None)):
    require_harness(x_harness_key)
    return await harness.close(sid)


class HarnessPromote(BaseModel):
    title: str = Field(..., min_length=2, max_length=80)
    rules: list[str] = Field(default_factory=list, max_length=8)
    gates: dict[str, bool] = Field(default_factory=dict)
    source: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=300)


@app.post("/api/harness/versions")
def harness_promote(body: HarnessPromote, x_harness_key: str | None = Header(None)):
    """Kavach promotes a fix it proved by replay; every real call uses the new version from then on."""
    require_harness(x_harness_key)
    v = agent.promote(body.title, agent.clean_rules(body.rules), body.gates, body.source, body.note)
    return {"version": v, "live": agent.live()}


@app.post("/api/harness/versions/{version}/activate")
def harness_activate(version: int, x_harness_key: str | None = Header(None)):
    require_harness(x_harness_key)
    if not store.activate_agent_version(version):
        raise HTTPException(404, "no such version")
    store.log("agent.activated", f"Call agent v{version} is live")
    return {"live": agent.live()}


# ---- static ---------------------------------------------------------------------------------
app.mount("/audio", StaticFiles(directory=settings.audio_dir), name="audio")
if settings.web_dist.exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def spa(path: str):
        f = settings.web_dist / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(settings.web_dist / "index.html")
