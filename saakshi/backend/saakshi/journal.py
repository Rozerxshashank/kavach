"""The worker's side: a voice journal that turns how people actually talk into records.

One voice note can hold several employers ("Mehta ji teen hazaar, kothi 12 wali
madam dhai hazaar, Sharma ji ke yahan paise abhi baaki"). The agent:

  1. asks the LLM to propose structured entries (it is good at language),
  2. re-derives every amount and date deterministically (numbers.py),
  3. asks only for what is still missing (an employer's phone number, an amount…),
  4. reads everything back in the worker's language and saves only on "haan".

Corrections ("nahi, Mehta ji saade teen hazaar") update the draft and trigger a
fresh read-back. Saved entries queue confirmation calls to each employer, unless
the worker said not to contact them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from . import langs, lines, llm, store
from .config import settings
from .numbers import parse_amount, parse_period

SYSTEM = """You turn what an Indian informal worker says (Hindi, English, Hinglish, Tamil, Telugu, Kannada, Malayalam,
Marathi, Bengali or Gujarati, transcribed from possibly noisy audio) into work records for their personal work history.
Today is {today}. The worker's language is {lang}.

You receive the CURRENT DRAFT (records not yet saved), the worker's KNOWN EMPLOYERS, and what Saakshi last asked.
Return the FULL updated draft after applying what the worker just said.

Intents:
- "log_work": they describe work/payments (possibly several employers in one go)
- "add_info": they answer Saakshi's question (e.g. give a phone number, an amount, a month)
- "confirm_yes": they agree the read-back is correct ("haan", "sahi hai", "yes")
- "correct": they say something is wrong and/or give the corrected value
- "cancel": they want to drop the draft
- "read_record": they ask to hear their record ("mera record sunao")
- "smalltalk": anything else

Per record fields (keep verbatim words where asked, they are parsed by code):
- employer_name: how the worker refers to them ("Mehta ji", "kothi 12 wali madam", "Bablu thekedar")
- employer_phone_text: the phone number exactly as said, or "" if not given
- known_employer_id: id from KNOWN EMPLOYERS if this clearly is one of them, else ""
- role: domestic | cook | nanny | driver | construction | painter | plumber | electrician | tailor | security | delivery | other
- pay_type: monthly | daily | piece | lumpsum | in_kind
- amount_text: the worker's exact words for the TOTAL earned for this record ("teen hazaar", "4500", "dhai sau")
- amount: your numeric reading of amount_text (rupees), 0 if unknown
- days_text / days: number of days worked if mentioned
- rate_text: per-day or per-piece rate words if mentioned
- period_text: the worker's exact words for when ("october", "pichle hafte", "is mahine", "kal")
- period_start / period_end: your ISO-date reading of period_text, "" if unknown
- paid: "yes" | "no" | "partial" | "unknown"; paid_amount_text for partial
- paid_mode: cash | upi | in_kind | unknown
- do_not_contact: true if the worker says not to call/contact this employer
- notes: anything else important (in-kind pay like food, advances, deductions)
If pay is daily and only rate + days are given, set amount = rate*days and amount_text to "".
If the worker is NOT speaking Hindi/English/Hinglish, copy employer_phone_text exactly as transcribed (words and all;
code converts it) and still fill the numeric fields (amount, days, period_start/period_end) carefully; keep the *_text fields as their words.
"reply" (only for smalltalk) must be in {lang}: answer briefly and naturally, then invite them to tell their work.

Reply ONLY with JSON: {{"intent": "...", "drafts": [ ...records... ], "reply": "<short reply in the worker's language, only for smalltalk>"}}"""


@dataclass
class Draft:
    employer_name: str = ""
    employer_phone: str | None = None
    employer_id: str | None = None
    phone_said: bool = False
    role: str | None = None
    pay_type: str = "monthly"
    amount: float | None = None
    amount_source: str = ""        # "parsed" | "model" | "computed"
    days: float | None = None
    rate: float | None = None
    period: dict | None = None
    paid: str = "unknown"
    paid_amount: float | None = None
    paid_mode: str = "unknown"
    do_not_contact: bool = False
    notes: str = ""
    # the worker's own words, carried across turns so nothing said earlier is lost
    phone_text: str = ""
    amount_text: str = ""
    period_text: str = ""
    days_text: str = ""
    rate_text: str = ""

    def missing(self) -> str | None:
        if not self.employer_name:
            return "employer_name"
        if not self.employer_id and not self.do_not_contact:
            if not self.employer_phone:
                return "employer_phone_invalid" if self.phone_said else "employer_phone"
        if not self.amount:
            return "amount"
        if not self.period:
            return "period"
        return None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class JournalSession:
    worker: dict
    drafts: list[Draft] = field(default_factory=list)
    state: str = "listening"            # listening | asking | confirming
    asked: str = ""
    audio: list[str] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)

    @property
    def lang(self) -> str:
        return self.worker["language"]


SESSIONS: dict[str, JournalSession] = {}


def session_for(worker: dict) -> JournalSession:
    s = SESSIONS.get(worker["id"])
    if not s:
        s = SESSIONS[worker["id"]] = JournalSession(worker)
    return s


def _known_employers(worker_id: str) -> list[dict]:
    return [{"id": e["id"], "name": e["name"], "phone_last4": e["phone"][-4:]}
            for e in store.worker_employers(worker_id)]


_CARRY = {"employer_phone_text": "phone_text", "amount_text": "amount_text", "period_text": "period_text",
          "days_text": "days_text", "rate_text": "rate_text"}


def _as_model_view(d: Draft) -> dict:
    """The draft in the same shape the model returns, so it can copy fields forward."""
    return {"employer_name": d.employer_name, "employer_phone_text": d.phone_text or (d.employer_phone or ""),
            "known_employer_id": d.employer_id or "", "role": d.role, "pay_type": d.pay_type,
            "amount_text": d.amount_text, "amount": d.amount or 0, "days_text": d.days_text, "rate_text": d.rate_text,
            "period_text": d.period_text, "period_start": (d.period or {}).get("start", ""),
            "period_end": (d.period or {}).get("end", ""), "paid": d.paid, "paid_mode": d.paid_mode,
            "do_not_contact": d.do_not_contact, "notes": d.notes}


def _merge(raw: dict, prev: Draft | None) -> dict:
    """If the model left a field empty that the worker already gave, keep the earlier words."""
    if not prev:
        return raw
    merged = dict(raw)
    old = _as_model_view(prev)
    for k in ("employer_phone_text", "amount_text", "period_text", "days_text", "rate_text", "known_employer_id",
              "period_start", "period_end", "role"):
        if not str(merged.get(k) or "").strip() and str(old.get(k) or "").strip():
            merged[k] = old[k]
    if not merged.get("amount") and old.get("amount"):
        merged["amount"] = old["amount"]
    return merged


def _match_prev(raw: dict, prev: list[Draft], i: int) -> Draft | None:
    name = str(raw.get("employer_name") or "").strip().lower()
    for d in prev:
        if name and d.employer_name.strip().lower() == name:
            return d
    return prev[i] if i < len(prev) and not name else None


def _to_draft(raw: dict, worker_id: str, today: date) -> Draft:
    d = Draft()
    for src, dst in _CARRY.items():
        setattr(d, dst, str(raw.get(src) or "").strip())
    d.employer_name = str(raw.get("employer_name") or "").strip()
    d.role = raw.get("role") or None
    d.pay_type = raw.get("pay_type") if raw.get("pay_type") in ("monthly", "daily", "piece", "lumpsum", "in_kind") else "monthly"
    d.do_not_contact = bool(raw.get("do_not_contact"))
    d.notes = str(raw.get("notes") or "")
    d.paid = raw.get("paid") if raw.get("paid") in ("yes", "no", "partial", "unknown") else "unknown"
    d.paid_mode = raw.get("paid_mode") if raw.get("paid_mode") in ("cash", "upi", "in_kind", "unknown") else "unknown"

    # employer: a known employer by id, else by phone
    known = {e["id"]: e for e in store.worker_employers(worker_id)}
    if raw.get("known_employer_id") in known:
        e = known[raw["known_employer_id"]]
        d.employer_id, d.employer_phone = e["id"], e["phone"]
        d.employer_name = d.employer_name or e["name"]
    phone_text = str(raw.get("employer_phone_text") or "")
    if phone_text.strip():
        d.phone_said = True
        p = store.normalize_phone(phone_text)
        if p:
            d.employer_phone = p
            existing = store.employer_by_phone(p)
            d.employer_id = existing["id"] if existing else None

    # amounts: our parser wins over the model whenever it can read the words
    parsed = parse_amount(str(raw.get("amount_text") or ""))
    model_amt = float(raw.get("amount") or 0) or None
    d.amount, d.amount_source = (parsed, "parsed") if parsed else (model_amt, "model" if model_amt else "")
    days = parse_amount(str(raw.get("days_text") or "")) or (float(raw.get("days") or 0) or None)
    d.days = days if days and days <= 31 * 12 else None
    d.rate = parse_amount(str(raw.get("rate_text") or "")) or None
    if d.pay_type == "daily" and d.rate and d.days and not parsed:
        d.amount, d.amount_source = d.rate * d.days, "computed"
    if d.paid == "partial":
        d.paid_amount = parse_amount(str(raw.get("paid_amount_text") or "")) or None

    # period: deterministic reading first, the model's ISO dates as fallback
    per = parse_period(str(raw.get("period_text") or ""), today)
    if per:
        d.period = per.to_dict()
    elif raw.get("period_start"):
        try:
            s = date.fromisoformat(raw["period_start"])
            e = date.fromisoformat(raw.get("period_end") or raw["period_start"])
            if s <= today and (today - s).days < 800:
                d.period = {"start": s.isoformat(), "end": min(e, today).isoformat(), "label": raw.get("period_text") or "", "exact": False}
        except ValueError:
            pass
    return d


async def handle(worker: dict, text: str, audio_url: str | None = None) -> dict:
    """One worker utterance in, Saakshi's spoken reply (and state) out."""
    s = session_for(worker)
    today = date.today()
    if audio_url:
        s.audio.append(audio_url)
    s.transcript.append(text)

    payload = {
        "current_draft": [_as_model_view(d) for d in s.drafts],
        "known_employers": _known_employers(worker["id"]),
        "saakshi_last_asked": s.asked or "(nothing yet)",
        "saakshi_state": s.state,
        "worker_said": text,
    }
    out = await llm.chat_json(settings.agent_model, [
        {"role": "system", "content": SYSTEM.format(today=today.isoformat(), lang=langs.name(s.lang))},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ], temperature=0.1, max_tokens=2200)
    intent = out.get("intent") or "smalltalk"

    if intent == "read_record":
        from .passport import spoken_summary
        return _reply(s, spoken_summary(worker, s.lang), intent)

    if intent == "cancel":
        s.drafts, s.state, s.asked = [], "listening", ""
        return _reply(s, lines.CANCELLED[s.lang], intent)

    if intent == "confirm_yes" and s.state == "confirming" and s.drafts and not any(d.missing() for d in s.drafts):
        return _save(s)

    if intent in ("log_work", "add_info", "correct", "confirm_yes"):
        raw = [r for r in (out.get("drafts") or []) if isinstance(r, dict)]
        # a number said in Tamil/Kannada/… words: converted by a dedicated, self-checking step, and read back
        for r in raw:
            pt = str(r.get("employer_phone_text") or "")
            if pt.strip() and not store.normalize_phone(pt) and s.lang not in langs.HAND_WRITTEN:
                digits = await langs.spoken_phone(pt, s.lang)
                if digits:
                    r["employer_phone_text"] = digits
        if raw:
            prev = s.drafts
            s.drafts = [_to_draft(_merge(r, _match_prev(r, prev, i)), worker["id"], today) for i, r in enumerate(raw)]
            # a bare answer to "what's Verma ji's number?" belongs to the record we asked about
            if s.asked in ("employer_phone", "employer_phone_invalid") and intent == "add_info":
                target = next((d for d in s.drafts if d.missing() in ("employer_phone", "employer_phone_invalid")), None)
                p = store.normalize_phone(text)
                if not p and s.lang not in langs.HAND_WRITTEN:
                    d = await langs.spoken_phone(text, s.lang)
                    p = store.normalize_phone(d) if d else None
                if target and p:
                    target.employer_phone, target.phone_text, target.phone_said = p, text, True
                    ex = store.employer_by_phone(p)
                    target.employer_id = ex["id"] if ex else None
    elif intent == "smalltalk" and not s.drafts:
        return _reply(s, str(out.get("reply") or lines.NOT_UNDERSTOOD[s.lang]), intent)

    if not s.drafts:
        return _reply(s, lines.NOT_UNDERSTOOD[s.lang], intent)

    for d in s.drafts:
        need = d.missing()
        if need:
            s.state, s.asked = "asking", need
            who = d.employer_name or ("उनके" if s.lang == "hi-IN" else lines.tr(s.lang, "them"))
            return _reply(s, lines.ASK[need][s.lang].format(who=who), intent)

    s.state, s.asked = "confirming", "readback"
    return _reply(s, lines.readback([d.to_dict() for d in s.drafts], s.lang), intent)


def _save(s: JournalSession) -> dict:
    worker = s.worker
    saved, call_targets = [], {}
    clip = s.audio[-2] if len(s.audio) >= 2 else (s.audio[-1] if s.audio else None)
    for d in s.drafts:
        if d.employer_id:
            emp = store.get_employer(d.employer_id)
        elif d.employer_phone:
            # employers named by a demo worker are demo data too, so a demo reset cleans them up
            emp = store.upsert_employer(d.employer_phone, d.employer_name or "Employer", sim_group=worker.get("sim_group"),
                                        language=worker["language"])      # they're asked in the worker's language first
        else:  # do-not-contact employer without a number: keep a private placeholder
            emp = store.upsert_employer(_placeholder_phone(worker["id"], d.employer_name), d.employer_name, kind="private")
        assert emp is not None
        entry = store.add_entry(
            worker["id"], emp["id"], role=d.role or worker["role"], pay_type=d.pay_type, period=d.period or {},
            days=d.days, rate=d.rate, amount=float(d.amount or 0), paid=d.paid_amount if d.paid == "partial" else
            (float(d.amount or 0) if d.paid == "yes" else (0.0 if d.paid == "no" else None)),
            paid_mode=d.paid_mode, do_not_contact=d.do_not_contact or emp.get("opted_out") == 1,
            source_audio=clip, transcript=" / ".join(s.transcript[-4:]))
        saved.append(entry)
        store.log("entry.saved", f"{worker['name']} logged {entry['period_label'] or ''} at {emp['name']}: ₹{entry['amount']:,.0f}",
                  worker_id=worker["id"], employer_id=emp["id"])
        if not entry["do_not_contact"]:
            call_targets.setdefault(emp["id"], {"emp": emp, "entries": []})["entries"].append(entry["id"])

    from .calls import queue_call
    from .config import settings
    links = []
    for t in call_targets.values():
        # every employer gets a free confirmation link the worker sends from her own WhatsApp;
        # a phone call is added when a real line is configured (or for simulated demo employers)
        links.append(store.create_link(worker["id"], t["emp"]["id"], t["entries"]))
        if settings.telephony or t["emp"].get("persona"):
            queue_call(t["emp"]["id"], t["entries"])

    names = ", ".join(t["emp"]["name"] for t in call_targets.values())
    n = len(saved)
    forms = {"n": n, "names": names, "hua": "हो गया" if n == 1 else "हो गए", "records": "record" if n == 1 else "records"}
    msg = (lines.SAVED_LINK[s.lang].format(**forms) if call_targets else lines.SAVED_NO_CALL[s.lang].format(**forms))
    s.drafts, s.state, s.asked, s.transcript = [], "listening", "", []
    from .trust import recompute
    recompute()
    return _reply(s, msg, "saved", saved=saved)


def _placeholder_phone(worker_id: str, name: str) -> str:
    # never dialled: a stable fake number in an unallocated-looking range keyed by worker + name
    import hashlib
    h = int(hashlib.sha1(f"{worker_id}:{name}".encode()).hexdigest(), 16) % 10**9
    return f"6{h:09d}"


def _reply(s: JournalSession, say: str, intent: str, saved: list[dict] | None = None) -> dict:
    return {
        "say": say,
        "language": s.lang,
        "intent": intent,
        "state": s.state,
        "asked": s.asked,
        "drafts": [d.to_dict() for d in s.drafts],
        "saved": saved or [],
    }


def welcome(worker: dict) -> str:
    return lines.WELCOME[worker["language"]].format(name=worker["name"].split()[0])
