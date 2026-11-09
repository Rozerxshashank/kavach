"""Confirmation by link: the zero-cost way to reach an employer.

The worker forwards a link from her own WhatsApp (a free wa.me share, so no API
or per-message fee). The message comes from a number the employer already knows,
which defuses the "is this a scam?" problem a cold call has.

On the link page, Saakshi explains the request out loud (Timbre), and the employer:
  * confirms by SPEAKING ("haan, sahi hai" / "main pushti karta hoon"), heard by
    Prisma and kept as a recording, which is stronger evidence than a tap,
  * or taps confirm when they can't speak (counted, but marked weaker),
  * or corrects the amount / days, or says they don't know the worker,
  * and can pay the worker right there through their own UPI app; the UPI
    reference they give back is later matched against the worker's bank SMS.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote

from . import audio, gnani, langs, llm, store
from .calls import AGENT_VOICE, quick_yes_no
from .config import settings
from .lines import EXTRA, greet_name, honorific, money, period_words, tr

AFFIRM = re.compile(r"(पुष्टि|सही|हाँ|हां|ठीक|बिल्कुल|pushti|sahi|haan|han\b|theek|thik|bilkul|confirm|correct|yes|true|right)", re.I)
NEGATE = re.compile(r"(नहीं|नही|गलत|ग़लत|nahi|nahin|galat|wrong|\bno\b|not true|don'?t know)", re.I)


def message(worker: dict, employer: dict, url: str, lang: str | None = None) -> str:
    first = worker["name"].split()[0]
    lang = lang or worker["language"]
    who = greet_name(employer["name"], lang)
    if lang == "hi-IN":
        return (f"नमस्ते {who}, मैं {first} हूँ। मैंने साक्षी पर अपने काम का रिकॉर्ड बनाया है। "
                f"कृपया 20 सेकंड में इसकी पुष्टि कर दीजिए: {url}")
    return tr(lang, MESSAGE, who=who, first=first, url=url)


MESSAGE = "Hello {who}, this is {first}. I've recorded my work with you on Saakshi. Please confirm it (20 seconds): {url}"
INTRO = ("Hello {employer}. I'm Saakshi. {first} says they worked for you: {parts}. If that's right, just say: yes, "
         "that's correct. If it's wrong, tell me what's right. I never ask for money or OTPs.")
EXTRA += [MESSAGE, INTRO]


async def message_for(worker: dict, employer: dict, url: str) -> str:
    """The WhatsApp text in the employer's language (by default the worker's own)."""
    return message(worker, employer, url, employer.get("language") or worker["language"])


def whatsapp_url(employer_phone: str, text: str) -> str:
    return f"https://wa.me/{employer_phone.lstrip('+')}?text={quote(text, safe='')}"


def create(worker: dict, employer: dict, entry_ids: list[str], base_url: str) -> dict:
    link = store.create_link(worker["id"], employer["id"], entry_ids)
    url = f"{base_url.rstrip('/')}/c/{link['token']}"
    text = message(worker, employer, url)
    store.log("link.created", f"Confirmation link for {employer['name']} ({len(entry_ids)} record(s))",
              worker_id=worker["id"], employer_id=employer["id"])
    return {**link, "url": url, "message": text, "whatsapp": whatsapp_url(employer["phone"], text)}


def _entries(link: dict) -> list[dict]:
    return [e for e in (store.get_entry(x) for x in link["entry_ids"]) if e]


def view(token: str) -> dict:
    link = store.get_link(token)
    if not link:
        raise KeyError(token)
    w = store.get_worker(link["worker_id"]) or {}
    emp = store.get_employer(link["employer_id"]) or {}
    if not link["opened_at"]:
        store.update_link(token, opened_at=store.now(), status="opened" if link["status"] == "sent" else link["status"])
    rows = []
    for e in _entries(link):
        says = json.loads(e["employer_says"]) if e.get("employer_says") else None
        pay = json.loads(e["employer_payment"]) if e.get("employer_payment") else None
        rows.append({"id": e["id"], "period": {"start": e["period_start"], "end": e["period_end"], "label": e["period_label"]},
                     "amount": e["amount"], "days": e["days"], "status": e["status"], "employer_says": says,
                     "payment": pay, "payment_status": e.get("payment_status") or "none", "level": e.get("level") or 0})
    return {
        "token": token, "status": link["status"], "outcome": link["outcome"],
        "worker": {"name": w.get("name"), "role": w.get("role"), "upi_id": w.get("upi_id"), "language": w.get("language")},
        "employer": {"name": emp.get("name"), "opted_out": bool(emp.get("opted_out"))},
        "language": emp.get("language") or w.get("language") or "hi-IN",
        "entries": rows,
    }


async def intro_audio(token: str, lang: str | None = None) -> dict:
    """Saakshi explains the request out loud, in the employer's chosen language. Cached per link + language."""
    v = view(token)
    lang = lang or v["language"]
    path = settings.audio_dir / "links" / f"{token}_{lang}_v3.wav"
    if not path.exists():
        first = (v["worker"]["name"] or "").split()[0]
        parts = [f"{period_words(r['period'], lang)}, {money(r['amount'], lang)}" for r in v["entries"]]
        if lang == "hi-IN":
            text = (f"नमस्ते {greet_name(v['employer']['name'], lang)}। मैं साक्षी हूँ। {first} जी का कहना है कि उन्होंने आपके यहाँ काम किया: "
                    + "; ".join(parts) + "। अगर यह सही है, तो बस बोलिए: हाँ, सही है। ग़लत हो तो बताइए कि सही क्या है। मैं कभी पैसे या OTP नहीं माँगती।")
        else:
            text = tr(lang, INTRO, employer=honorific(v["employer"]["name"]), first=first, parts="; ".join(parts))
        res = await gnani.timbre_speak(text, voice=AGENT_VOICE, language=lang)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(res.audio)
    wav = path.read_bytes()
    return {"url": f"/audio/links/{path.name}", "duration": audio.duration_s(wav), "peaks": audio.peaks(wav, 64)}


def _finish(link: dict, outcome: str, via: str, clip: str | None = None, heard: str | None = None,
            fix: dict | None = None) -> dict:
    for e in _entries(link):
        if outcome == "verified":
            store.update_entry(e["id"], status="verified", attested_by="employer", attested_via=via,
                               employer_says={"amount": e["amount"], "days": e["days"]})
        elif outcome == "corrected":
            store.update_entry(e["id"], status="corrected", attested_by="employer", attested_via=via,
                               employer_says=(fix or {}).get(e["id"]) or {"amount": e["amount"]})
        elif outcome == "disputed":
            store.update_entry(e["id"], status="disputed", attested_by="employer", attested_via=via)
    store.update_link(link["token"], status="done", outcome=outcome, done_at=store.now(), voice_clip=clip, heard=heard)
    emp = store.get_employer(link["employer_id"]) or {}
    store.log("link.done", f"{emp.get('name')}: {outcome} via link", worker_id=link["worker_id"],
              employer_id=link["employer_id"])
    from .payments import reconcile
    from .trust import recompute
    reconcile(link["worker_id"])
    recompute()
    return view(link["token"])


async def confirm_by_voice(token: str, wav: bytes) -> dict:
    link = store.get_link(token)
    if not link:
        raise KeyError(token)
    lang = view(token)["language"]
    heard = (await gnani.prisma_transcribe(wav, language=lang)).text
    folder = settings.audio_dir / "links"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{token}_employer_{datetime.now().strftime('%H%M%S')}.wav"
    (folder / name).write_bytes(wav)
    clip = f"/audio/links/{name}"
    verdict = await _verdict(heard)
    if verdict == "yes":
        return {"heard": heard, "accepted": True, "view": _finish(link, "verified", "link_voice", clip, heard)}
    if verdict == "no":
        return {"heard": heard, "accepted": False, "reason": "negative"}
    return {"heard": heard, "accepted": False, "reason": "unclear"}


VERDICT = """An employer was asked, out loud, to confirm a worker's work record. Below is what they said (a speech
transcript; any Indian language, may be noisy). Did they clearly confirm it is correct ("yes"), clearly say it is wrong
or that they don't know the worker ("no"), or neither ("unclear", including questions and partial corrections)?
Reply ONLY with JSON: {"verdict": "yes|no|unclear"}"""


async def _verdict(heard: str) -> str:
    """Hindi/English yes/no by rule; anything else (other languages, mixed answers) by the model."""
    if quick_yes_no(heard) == "confirm" or (AFFIRM.search(heard) and not NEGATE.search(heard) and len(heard) < 60):
        return "yes"
    if NEGATE.search(heard) and not AFFIRM.search(heard) and len(heard) < 60:
        return "no"
    try:
        out = await llm.chat_json("openai/gpt-oss-20b", [{"role": "system", "content": VERDICT},
                                                        {"role": "user", "content": heard or "[silence]"}],
                                  temperature=0.0, max_tokens=300)
        v = str(out.get("verdict") or "unclear")
        return v if v in ("yes", "no", "unclear") else "unclear"
    except llm.LLMError:
        return "unclear"


def confirm_by_tap(token: str) -> dict:
    link = store.get_link(token)
    if not link:
        raise KeyError(token)
    return _finish(link, "verified", "link_tap")


def correct(token: str, fixes: dict[str, dict]) -> dict:
    link = store.get_link(token)
    if not link:
        raise KeyError(token)
    clean = {}
    for e in _entries(link):
        f = fixes.get(e["id"]) or {}
        amt = float(f.get("amount") or 0)
        days = float(f.get("days") or 0) or None
        if amt <= 0 or amt > 10 * max(1.0, e["amount"]):
            raise ValueError("Please enter the amount you actually paid.")
        clean[e["id"]] = {"amount": amt, "days": days or e["days"]}
    return _finish(link, "corrected", "link_form", fix=clean)


def deny(token: str) -> dict:
    link = store.get_link(token)
    if not link:
        raise KeyError(token)
    return _finish(link, "disputed", "link_form")
