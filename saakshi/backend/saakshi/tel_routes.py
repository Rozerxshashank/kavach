"""Twilio webhooks: the same call engine and voice journal, on real phone lines."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from . import audio, calls, gnani, journal, store
from . import telephony as tel
from .bus import bus
from .config import settings

router = APIRouter(prefix="/tel")

NOT_REGISTERED = {
    "hi-IN": "नमस्ते! मैं साक्षी हूँ, आपके काम का रिकॉर्ड रखने वाली सेवा। आपका यह नंबर अभी जुड़ा नहीं है। बीप के बिना, बस अपना पूरा नाम बोलिए।",
}
GOODBYE = {
    "hi-IN": "धन्यवाद! जब भी काम का रिकॉर्ड जोड़ना हो, इसी नंबर पर फ़ोन कीजिए।",
    "en-IN": "Thank you! Call this number any time you want to add a work record.",
}
DIDNT_HEAR = {
    "hi-IN": "माफ़ कीजिए, आवाज़ नहीं आई। फिर से बोलिए।",
    "en-IN": "Sorry, I didn't hear anything. Please say that again.",
}


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


async def _form(request: Request) -> dict[str, str]:
    """Read the webhook form and reject anything not signed by Twilio."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    url = settings.public_base_url + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    if not tel.valid_request(url, form, request.headers.get("X-Twilio-Signature")):
        raise HTTPException(403, "invalid Twilio signature")
    return form


async def _say_clip(text: str, lang: str, folder: str) -> dict:
    res = await gnani.timbre_speak(text, voice=calls.AGENT_VOICE, language=lang)
    name = f"tel_{datetime.now().strftime('%H%M%S%f')}.wav"
    d = settings.audio_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(res.audio)
    return {"url": f"/audio/{folder}/{name}"}


def _turn_twiml(turn: dict, next_action: str | None) -> str:
    verbs = [tel.play((turn.get("audio") or {}).get("url")), tel.play(turn.get("worker_clip")),
             tel.play((turn.get("follow_audio") or {}).get("url"))]
    verbs.append(tel.hangup() if turn.get("done") or not next_action else tel.record(next_action))
    return tel.twiml(*verbs)


async def _caller_audio(form: dict[str, str]) -> bytes | None:
    if not form.get("RecordingUrl"):
        return None
    raw = await tel.fetch_recording(form["RecordingUrl"])
    return audio.to_16k(raw)                      # 8 kHz / μ-law phone audio → 16 kHz for Prisma


# ---- outbound: confirming with an employer ---------------------------------------------------
@router.post("/call/{call_id}/answer")
async def call_answer(call_id: str, request: Request):
    form = await _form(request)
    if form.get("AnsweredBy", "").startswith("machine") or form.get("AnsweredBy") == "fax":
        await calls.no_answer(call_id)            # voicemail: never leave a record-confirmation on a machine
        return _xml(tel.twiml(tel.hangup()))
    turn = await calls.answer(call_id)
    return _xml(_turn_twiml(turn, f"/tel/call/{call_id}/heard"))


@router.post("/call/{call_id}/heard")
async def call_heard(call_id: str, request: Request):
    form = await _form(request)
    wav = await _caller_audio(form)
    if wav:
        text, clip = await calls.transcribe_employer(call_id, wav)
    else:
        text, clip = "", None                     # silence: the engine re-prompts, then gives up politely
    turn = await calls.employer_said(call_id, text, clip)
    return _xml(_turn_twiml(turn, f"/tel/call/{call_id}/heard"))


@router.post("/call/{call_id}/status")
async def call_status(call_id: str, request: Request):
    form = await _form(request)
    status = form.get("CallStatus", "")
    c = store.get_call(call_id)
    if c and status in ("no-answer", "busy", "failed", "canceled"):
        await calls.no_answer(call_id)
    elif c and status == "completed" and c["status"] in ("ringing", "in_call"):
        # they hung up mid-call: keep the records pending and try again later
        calls.LIVE.pop(call_id, None)
        await calls.no_answer(call_id)
    return _xml(tel.twiml())


# ---- inbound: a worker calls Saakshi from any phone --------------------------------------------
@router.post("/inbound")
async def inbound(request: Request):
    form = await _form(request)
    caller = store.normalize_phone(form.get("From", ""))
    w = next((x for x in store.list_workers() if x["phone"] == caller), None) if caller else None
    if not w:
        if not caller:
            return _xml(tel.twiml(tel.hangup()))
        clip = await _say_clip(NOT_REGISTERED["hi-IN"], "hi-IN", "tel_inbound")
        return _xml(tel.twiml(tel.play(clip["url"]), tel.record(f"/tel/register?from={caller[1:]}", 8)))
    text = journal.welcome(w)
    clip = await _say_clip(text, w["language"], f"j_{w['id']}")
    store.log("hotline.call", f"{w['name']} called the Saakshi line", worker_id=w["id"])
    await bus.emit("hotline.call", worker_id=w["id"])
    return _xml(tel.twiml(tel.play(clip["url"]), tel.record(f"/tel/worker/{w['id']}/heard")))


@router.post("/register")
async def register(request: Request):
    form = await _form(request)
    phone = "+" + request.query_params.get("from", "").lstrip("+")
    wav = await _caller_audio(form)
    if not wav:
        clip = await _say_clip(DIDNT_HEAR["hi-IN"], "hi-IN", "tel_inbound")
        return _xml(tel.twiml(tel.play(clip["url"]), tel.record(f"/tel/register?from={phone[1:]}", 8)))
    heard = (await gnani.prisma_transcribe(wav, language="hi-IN")).text.strip(" .।")
    name = " ".join(heard.replace("मेरा नाम", "").replace("है", "").split()[:3]).strip() or "Saakshi user"
    w = store.create_worker(name, phone, "hi-IN", "other", "—", "—")
    store.log("hotline.registered", f"{name} registered by phone", worker_id=w["id"])
    await bus.emit("world.changed")
    clip = await _say_clip(journal.welcome(w), "hi-IN", f"j_{w['id']}")
    return _xml(tel.twiml(tel.play(clip["url"]), tel.record(f"/tel/worker/{w['id']}/heard")))


@router.post("/worker/{worker_id}/heard")
async def worker_heard(worker_id: str, request: Request):
    form = await _form(request)
    w = store.get_worker(worker_id)
    if not w:
        return _xml(tel.twiml(tel.hangup()))
    wav = await _caller_audio(form)
    if not wav:
        if request.query_params.get("silent") and journal.session_for(w).state == "listening":
            clip = await _say_clip(GOODBYE[w["language"]], w["language"], f"j_{worker_id}")
            return _xml(tel.twiml(tel.play(clip["url"]), tel.hangup()))
        clip = await _say_clip(DIDNT_HEAR[w["language"]], w["language"], f"j_{worker_id}")
        return _xml(tel.twiml(tel.play(clip["url"]), tel.record(f"/tel/worker/{worker_id}/heard")))

    d = settings.audio_dir / f"j_{worker_id}"
    d.mkdir(parents=True, exist_ok=True)
    name = f"phone_{datetime.now().strftime('%H%M%S%f')}.wav"
    (d / name).write_bytes(wav)
    heard = (await gnani.prisma_transcribe(wav, language=w["language"])).text
    out = await journal.handle(w, heard, f"/audio/j_{worker_id}/{name}")
    clip = await _say_clip(out["say"], w["language"], f"j_{worker_id}")
    await bus.emit("journal.turn", worker_id=worker_id, state=out["state"], saved=len(out["saved"]))
    if out["saved"]:
        await bus.emit("world.changed")
        bye = await _say_clip(GOODBYE[w["language"]], w["language"], f"j_{worker_id}")
        return _xml(tel.twiml(tel.play(clip["url"]), tel.play(bye["url"]), tel.hangup()))
    return _xml(tel.twiml(tel.play(clip["url"]), tel.record(f"/tel/worker/{worker_id}/heard")))
