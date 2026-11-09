"""Everything Saakshi says out loud.

Hindi and English are hand-written. The other seven languages use the English *templates*, translated
once ahead of time (scripts/build_i18n.py -> i18n_lines.json) with their {placeholders} intact. Names,
numbers and dates are filled in by code after translation, never by a model, so what the worker and
employer hear is exactly what gets recorded, and speaking never waits on a translation service.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .numbers import MONTH_NAMES_EN, MONTH_NAMES_HI, inr, spoken_amount_hi

AGENT_NAME = "Saakshi"
HAND_WRITTEN = ("hi-IN", "en-IN")

def _load_i18n() -> dict[str, dict[str, str]]:
    """Machine translations (checked by scripts/build_i18n.py), then hand-reviewed overrides on top."""
    out: dict[str, dict[str, str]] = {}
    for name in ("i18n_lines.json", "i18n_overrides.json"):
        try:
            for lang, rows in json.loads(Path(__file__).with_name(name).read_text()).items():
                out.setdefault(lang, {}).update(rows)
        except (OSError, ValueError):
            pass
    return out


_I18N = _load_i18n()


def tr(lang: str, template: str, **kw) -> str:
    """An English template in `lang` (pre-translated), with the placeholders then filled in by code."""
    t = template if lang in HAND_WRITTEN else _I18N.get(lang, {}).get(template, template)
    return t.format(**kw) if kw else t


def tr_any(lang: str, template: str, **kw) -> str:
    """Like tr, but Hindi uses the pre-translated template too (for text that has no hand-written Hindi)."""
    t = template if lang == "en-IN" else _I18N.get(lang, {}).get(template, template)
    try:
        return t.format(**kw) if kw else t
    except (KeyError, IndexError):
        return template.format(**kw) if kw else template


def missing_translations() -> dict[str, int]:
    """How many known templates have no translation, per language (for tests and the build script)."""
    from .langs import LANGS
    allt = all_templates()
    return {l: sum(1 for t in allt if t not in _I18N.get(l, {})) for l in LANGS if l not in HAND_WRITTEN}


def period_words(period: dict, lang: str, natural: bool = True) -> str:
    """'अक्टूबर' (this year), 'अक्टूबर 2025', '26 से 31 अक्टूबर', '5 नवंबर'. People don't say the current year."""
    s, e = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    this_year = s.year == date.today().year and natural
    full_month = s.day == 1 and (s.year, s.month) == (e.year, e.month) and (
        e.day >= 28 or (e + timedelta(days=1)).day == 1 or e >= date.today())
    if lang == "hi-IN":
        if full_month:
            return MONTH_NAMES_HI[s.month] if this_year else f"{MONTH_NAMES_HI[s.month]} {s.year}"
        if s == e:
            return f"{s.day} {MONTH_NAMES_HI[s.month]}"
        if s.month == e.month:
            return f"{s.day} से {e.day} {MONTH_NAMES_HI[e.month]}"
        return f"{s.day} {MONTH_NAMES_HI[s.month]} से {e.day} {MONTH_NAMES_HI[e.month]}"
    ms, me = tr(lang, MONTH_NAMES_EN[s.month]), tr(lang, MONTH_NAMES_EN[e.month])
    if full_month:
        return ms if this_year else f"{ms} {s.year}"
    if s == e:
        return f"{s.day} {ms}"
    if s.month == e.month:
        return f"{s.day}–{e.day} {me}"
    return tr(lang, "{a} to {b}", a=f"{s.day} {ms}", b=f"{e.day} {me}")


WORK = {
    "domestic": ("घर की साफ़-सफ़ाई का", "housework"), "cook": ("खाना बनाने का", "cooking"),
    "nanny": ("बच्चों की देखभाल का", "childcare"), "driver": ("गाड़ी चलाने का", "driving"),
    "construction": ("निर्माण का", "construction work"), "painter": ("पेंटिंग का", "painting"),
    "plumber": ("प्लंबिंग का", "plumbing"), "electrician": ("बिजली का", "electrical work"),
    "tailor": ("सिलाई का", "tailoring"), "security": ("सुरक्षा गार्ड का", "security guard work"),
    "delivery": ("डिलीवरी का", "delivery work"),
}


def work_words(role: str | None, lang: str) -> str:
    hi, en = WORK.get(role or "", ("", "work"))
    return (f"{hi} काम" if hi else "काम") if lang == "hi-IN" else tr(lang, en)


def money(amount: float, lang: str) -> str:
    return spoken_amount_hi(amount) if lang == "hi-IN" else tr(lang, "{n} rupees", n=inr(amount).replace("₹", ""))


def entry_phrase(d: dict, lang: str) -> str:
    """One line of a read-back: who, when, how much, paid or not."""
    who = d.get("employer_name") or ("नियोक्ता" if lang == "hi-IN" else tr(lang, "employer"))
    when = period_words(d["period"], lang) if d.get("period") else ""
    amt = money(d["amount"], lang) if d.get("amount") else ""
    days = d.get("days")
    unpaid = d.get("paid") in ("no", "partial")
    # a new employer's number is read back in full, so a mis-heard digit gets caught before anyone is contacted
    ph = (d.get("employer_phone") or "")[-10:] if d.get("employer_phone") and not d.get("employer_id") else ""
    phone = f"{ph[:5]} {ph[5:]}" if ph else ""
    if lang == "hi-IN":
        bits = [f"{who} के यहाँ", f"नंबर {phone}" if phone else "", f"{when} में" if when and not when[0].isdigit() else when]
        if days:
            bits.append(f"{int(days) if float(days).is_integer() else days} दिन")
        bits.append(amt)
        if d.get("paid") == "no":
            bits.append("पैसे अभी बाकी हैं")
        elif d.get("paid") == "partial":
            bits.append(f"{money(d['paid_amount'], lang)} मिले" if d.get("paid_amount") else "कुछ पैसे बाकी")
        if d.get("do_not_contact"):
            bits.append("इन्हें फ़ोन नहीं करेंगे")
        return ", ".join(b for b in bits if b)
    bits = [f"{who}", tr(lang, "number {phone}", phone=phone) if phone else "", when]
    if days:
        bits.append(tr(lang, "{d} days", d=f"{days:g}"))
    bits.append(amt)
    if unpaid:
        bits.append(tr(lang, "not fully paid yet"))
    if d.get("do_not_contact"):
        bits.append(tr(lang, "we won't call them"))
    return ", ".join(b for b in bits if b)


def readback(drafts: list[dict], lang: str) -> str:
    items = [entry_phrase(d, lang) for d in drafts]
    if lang == "hi-IN":
        joined = "; ".join(f"{i}. {t}" for i, t in enumerate(items, 1)) if len(items) > 1 else items[0]
        return f"मैंने लिखा: {joined}। क्या यह सही है? हाँ या ना बोलिए।"
    joined = "; ".join(f"{i}. {t}" for i, t in enumerate(items, 1)) if len(items) > 1 else items[0]
    return tr(lang, "I have noted: {items}. Is that right? Please say yes or no.", items=joined)


ASK = {
    "employer_phone": {
        "hi-IN": "{who} का मोबाइल नंबर बताइए, ताकि मैं उनसे पुष्टि कर सकूँ। अगर आप नहीं चाहतीं कि मैं उन्हें फ़ोन करूँ, तो बोलिए 'फ़ोन मत करना'।",
        "en-IN": "What is {who}'s mobile number, so I can confirm with them? Please say it one digit at a time, or type it. If you don't want me to contact them, just say 'don't call'.",
    },
    "employer_phone_invalid": {
        "hi-IN": "यह नंबर पूरा नहीं लगा। {who} का दस अंकों का मोबाइल नंबर दोबारा बताइए।",
        "en-IN": "That number didn't sound complete. Please say {who}'s 10-digit mobile number again, one digit at a time, or type it.",
    },
    "amount": {
        "hi-IN": "{who} के यहाँ कितने पैसे बने?",
        "en-IN": "How much did you earn at {who}'s?",
    },
    "period": {
        "hi-IN": "{who} के यहाँ यह काम कब का है? जैसे 'अक्टूबर' या 'पिछले हफ़्ते'।",
        "en-IN": "When was this work at {who}'s? For example 'October' or 'last week'.",
    },
    "employer_name": {
        "hi-IN": "यह काम किसके यहाँ किया?",
        "en-IN": "Whose place was this work at?",
    },
}

SAVED = {
    "hi-IN": "हो गया! {n} रिकॉर्ड सेव {hua}। मैं {names} से पुष्टि करूँगी और आपको बताऊँगी।",
    "en-IN": "Done! {n} {records} saved. I'll confirm with {names} and let you know.",
}
SAVED_LINK = {
    "hi-IN": "हो गया! {n} रिकॉर्ड सेव {hua}। अब नीचे के बटन से {names} को व्हाट्सऐप पर पुष्टि का लिंक भेजिए।",
    "en-IN": "Done! {n} {records} saved. Now send {names} the confirmation link on WhatsApp using the button below.",
}
SAVED_NO_CALL = {
    "hi-IN": "हो गया! {n} रिकॉर्ड सेव {hua}।",
    "en-IN": "Done! {n} {records} saved.",
}
NOT_UNDERSTOOD = {
    "hi-IN": "माफ़ कीजिए, मैं समझ नहीं पाई। बताइए आज किसके यहाँ कितना काम किया?",
    "en-IN": "Sorry, I didn't catch that. Tell me whose place you worked at and how much you earned.",
}
CANCELLED = {
    "hi-IN": "ठीक है, मैंने यह रिकॉर्ड हटा दिया। फिर से बताइए।",
    "en-IN": "Okay, I've dropped that. Please tell me again.",
}
WELCOME = {
    "hi-IN": "नमस्ते {name} जी! मैं साक्षी हूँ। बताइए, किसके यहाँ काम किया और कितने पैसे बने?",
    "en-IN": "Hello {name}! I'm Saakshi. Tell me where you worked and how much you earned.",
}


# ---- employer calls ----------------------------------------------------------------------
def honorific(name: str) -> str:
    """'Verma ji' -> 'Verma' so we can say 'Verma जी' without doubling it."""
    import re as _re
    return _re.sub(r"\s*(ji|jee|जी)\s*$", "", name.strip(), flags=_re.I)


def greet_name(name: str, lang: str) -> str:
    """'Kapoor madam (Kothi 12)' -> 'Kapoor madam'; 'Verma ji' -> 'Verma जी'; 'Dr. Iyer' -> 'Dr. Iyer जी'."""
    import re as _re
    n = _re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    if _re.search(r"\b(madam|ma'am|sir|sahab|saab|sahib|didi|bhaiya|aunty|uncle)$", n, _re.I) or n.endswith("जी"):
        return n
    base = honorific(n)
    return f"{base} जी" if lang == "hi-IN" else base


def call_opening(employer_name: str, worker_names: list[str], lang: str) -> str:
    employer_name = greet_name(employer_name, lang)
    who = " और ".join(worker_names) if lang == "hi-IN" else " and ".join(worker_names)
    if lang == "hi-IN":
        return (f"नमस्ते {employer_name}, मैं साक्षी बोल रही हूँ, कामगारों का मुफ़्त काम-रिकॉर्ड रखती हूँ। "
                f"{who} जी ने आपके यहाँ के काम की पुष्टि माँगी है। बस आधा मिनट लगेगा, और यह कॉल रिकॉर्ड हो रही है। "
                f"क्या मैं बताऊँ?")
    return tr(lang, "Hello {employer}, this is Saakshi. We keep free work records for workers. {who} has recorded the work "
                    "they did for you and needs your confirmation. It takes twenty seconds, and this call is recorded. "
                    "Shall I go ahead?", employer=employer_name, who=who)


def _month_runs(entries: list[dict], lang: str) -> list[str]:
    """Group consecutive months with the same pay: 'मई से अक्टूबर तक हर महीने 3 हज़ार रुपये'."""
    rows = sorted(entries, key=lambda e: e["period"]["start"])
    out, i = [], 0
    while i < len(rows):
        j = i
        monthly = rows[i]["period"]["start"].endswith("-01")
        while (monthly and j + 1 < len(rows) and rows[j + 1]["amount"] == rows[i]["amount"]
               and rows[j + 1]["period"]["start"].endswith("-01") and not rows[j + 1].get("days")):
            j += 1
        a, b = rows[i], rows[j]
        amt = money(a["amount"], lang)
        if j > i:
            if lang == "hi-IN":
                out.append(f"{period_words(a['period'], lang)} से {period_words(b['period'], lang)} तक हर महीने {amt}")
            else:
                out.append(tr(lang, "from {a} to {b}, {amt} a month", a=period_words(a["period"], lang),
                              b=period_words(b["period"], lang), amt=amt))
        else:
            d = a.get("days")
            when = period_words(a["period"], lang)
            if lang == "hi-IN":
                out.append(f"{when} तक {d:g} दिन के {amt}" if d else f"{when} में {amt}")
            else:
                out.append(tr(lang, "{amt} for {d} days ({when})", amt=amt, d=f"{d:g}", when=when) if d
                           else tr(lang, "{amt} in {when}", amt=amt, when=when))
        i = j + 1
    return out


def call_claim(worker_name: str, entries: list[dict], lang: str, role: str | None = None) -> str:
    runs = _month_runs(entries, lang)
    work = work_words(role, lang)
    if lang == "hi-IN":
        joined = "; और ".join(runs)
        return (f"{worker_name} जी का कहना है कि उन्होंने आपके यहाँ {work} किया, और आपने उन्हें {joined} दिए। "
                f"क्या यह सही है?")
    return tr(lang, "{worker} says they did {work} for you, and you paid them {runs}. Is that right?",
              worker=worker_name, work=work, runs="; ".join(runs))


REASK = {
    # always self-contained: the employer may have just heard an answer about something else
    "hi-IN": ["तो क्या {worker} जी का यह रिकॉर्ड सही है?", "क्या आप {worker} जी के इस रिकॉर्ड की पुष्टि करेंगे?",
              "तो {worker} जी के काम और पैसों के बारे में जो मैंने बताया, क्या वह सही है?"],
    "en-IN": ["So, is {worker}'s record right?", "Would you confirm {worker}'s record?",
              "So, is what I told you about {worker}'s work and pay correct?"],
}

# Said instead of repeating the same refusal word for word.
OFF_TOPIC_AGAIN = {
    "hi-IN": "जैसा मैंने कहा, उसके बारे में मैं कुछ नहीं बता सकती। {worker} जी के रिकॉर्ड पर आपको कुछ कहना हो, तो ज़रूर बताइए।",
    "en-IN": "As I said, I can't tell you about that. If you'd like to say anything about {worker}'s record, please do.",
}

# The caller kept asking about things outside this record: end politely instead of looping.
OFF_TOPIC_END = {
    "hi-IN": "माफ़ कीजिए, मैं सिर्फ़ {worker} जी के काम-रिकॉर्ड के बारे में ही बात कर सकती हूँ। शायद अभी सही समय नहीं है, "
             "मैं बाद में फिर कोशिश करूँगी। धन्यवाद!",
    "en-IN": "Sorry, I can only talk about {worker}'s work record. Perhaps this isn't a good time; I'll try again later. Thank you!",
}


def call_bulk_claim(site: str, rows: list[tuple[str, dict]], lang: str) -> str:
    if lang == "hi-IN":
        parts = [f"{name}, {period_words(e['period'], lang)}, {int(e['days'] or 0)} दिन, {money(e['amount'], lang)}"
                 for name, e in rows]
        return f"{site} के लिए ये रिकॉर्ड हैं: " + "; ".join(parts) + "। क्या सब सही है? किसी का अलग हो तो नाम लेकर बताइए।"
    parts = [f"{name}, {period_words(e['period'], lang)}, {tr(lang, '{d} days', d=int(e['days'] or 0))}, {money(e['amount'], lang)}"
             for name, e in rows]
    return tr(lang, "For {site}, the records are: {parts}. Is everything correct? If anyone is different, tell me their name.",
              site=site, parts="; ".join(parts))


TRUST = {
    "hi-IN": "मैं समझती हूँ। मैं कभी पैसे, OTP या बैंक की जानकारी नहीं माँगती। {worker} जी की अपनी आवाज़ सुनिए:",
    "en-IN": "I understand. I never ask for money, OTPs or bank details. Here is {worker} in their own voice:",
}
TRUST_VERIFY = {
    "hi-IN": "आपका सावधान रहना बिल्कुल ठीक है। आप चाहें तो इस कॉल का कोड {code} Saakshi ऐप पर जाँच सकते हैं, या {worker} जी से ख़ुद पूछ लीजिए। मैं कुछ नहीं माँग रही, बस यह बताइए: क्या उन्होंने आपके यहाँ यह काम किया था?",
    "en-IN": "You're right to be careful. You can check this call's code {code} on the Saakshi app, or ask {worker} yourself. I'm not asking for anything; just tell me: did they do this work for you?",
}
TRUST_GIVE_UP = {
    "hi-IN": "कोई बात नहीं, मैं आपको परेशान नहीं करूँगी। आप {worker} जी से बात करके कभी भी पुष्टि कर सकते हैं। धन्यवाद!",
    "en-IN": "No problem, I won't bother you. You can confirm any time after speaking to them. Thank you!",
}
AFTER_CLIP = {
    "hi-IN": "अब बताइए, क्या यह जानकारी सही है?",
    "en-IN": "So, is that information correct?",
}
CORRECTION_READBACK = {
    "hi-IN": "समझ गई। तो आपके हिसाब से: {what}। सही है?",
    "en-IN": "Got it. So according to you: {what}. Is that right?",
}
THANKS_VERIFIED = {
    "hi-IN": "बहुत धन्यवाद! {worker} जी का रिकॉर्ड पक्का हो गया। आपका दिन शुभ हो।",
    "en-IN": "Thank you so much! {worker}'s record is confirmed. Have a good day.",
}
THANKS_CORRECTED = {
    "hi-IN": "धन्यवाद! मैंने आपकी बताई जानकारी दर्ज कर ली है।",
    "en-IN": "Thank you! I've recorded the details as you gave them.",
}
DENY_CHECK = {
    "hi-IN": "ठीक है। क्या आप {worker} जी को जानते ही नहीं, या जानकारी गलत है?",
    "en-IN": "Okay. Do you not know {worker} at all, or are the details wrong?",
}
THANKS_DISPUTED = {
    "hi-IN": "धन्यवाद, मैंने नोट कर लिया कि आप इसकी पुष्टि नहीं करते।",
    "en-IN": "Thank you, I've noted that you don't confirm this.",
}
CALLBACK_OK = {
    "hi-IN": "ज़रूर, मैं {when} फिर से फ़ोन करूँगी। धन्यवाद!",
    "en-IN": "Sure, I'll call again {when}. Thank you!",
}
OPT_OUT = {
    "hi-IN": "माफ़ कीजिए परेशानी के लिए। आपको दोबारा फ़ोन नहीं आएगा।",
    "en-IN": "Sorry for the trouble. You won't be called again.",
}
ASK_FOR_EMPLOYER = {
    "hi-IN": "क्या आप {employer} से बात करवा सकते हैं? या आप ही इस काम की पुष्टि कर सकते हैं?",
    "en-IN": "Could I speak to {employer}? Or can you confirm this work yourself?",
}
REPROMPT = {
    "hi-IN": "माफ़ कीजिए, ठीक से सुनाई नहीं दिया। क्या {worker} जी की बात सही है? हाँ या ना बोलिए।",
    "en-IN": "Sorry, I didn't catch that. Is what {worker} said correct? Please say yes or no.",
}
REPROMPT_2 = {
    "hi-IN": "आवाज़ अब भी साफ़ नहीं है। बस 'हाँ' या 'ना' बोल दीजिए।",
    "en-IN": "Still couldn't hear clearly. Just 'yes' or 'no' is enough.",
}
REPROMPT_OPENING = {
    "hi-IN": "माफ़ कीजिए, आवाज़ साफ़ नहीं आई। क्या आप अभी एक मिनट बात कर सकते हैं?",
    "en-IN": "Sorry, I couldn't hear that clearly. Do you have a minute to talk?",
}
GIVE_UP = {
    "hi-IN": "कोई बात नहीं, मैं बाद में फिर कोशिश करूँगी। धन्यवाद!",
    "en-IN": "No problem, I'll try again later. Thank you!",
}


def faq_answer(question_kind: str, worker: str, claim: str, lang: str, role: str | None = None) -> str:
    """Scripted, always-correct answers used when the model's answer can't be trusted.
    Only a question about the money repeats the claim; everything else is answered on its own."""
    work = work_words(role, lang)
    if lang == "hi-IN":
        return {
            "who": f"मैं साक्षी हूँ, एक मुफ़्त सेवा जो घरों और साइटों पर काम करने वालों का काम-रिकॉर्ड बनाती है, "
                   f"ताकि उन्हें कर्ज़, किराये का घर और सरकारी योजनाएँ मिल सकें। {worker} जी ने ख़ुद यह रिकॉर्ड बनाया है।",
            "money": f"इसका मतलब है कि {worker} जी के हिसाब से आपने उन्हें उनके काम के लिए इतने पैसे दिए। {claim}",
            "why": f"{worker} जी के पास अपनी कमाई का कोई सबूत नहीं है। आपकी पुष्टि से उनका रिकॉर्ड पक्का होता है। आपसे कुछ नहीं माँगा जाएगा।",
            "work": f"{worker} जी के हिसाब से वे आपके यहाँ {work} करती हैं।",
            "privacy": "आपका नंबर किसी को नहीं दिखाया जाता। यह कॉल सिर्फ़ आपके जवाब के सबूत के लिए रिकॉर्ड होती है।",
            "remark": "जी, यह तो आप मुझसे बेहतर जानते हैं।",
        }.get(question_kind, f"माफ़ कीजिए, मैं सिर्फ़ {worker} जी के इस रिकॉर्ड के बारे में ही बात कर सकती हूँ।")
    return tr(lang, FAQ_EN.get(question_kind, FAQ_EN["other"]), worker=worker, claim=claim, work=work)


FAQ_EN = {
    "who": "I'm Saakshi, a free service that keeps work records for household and site workers, so they can get loans, "
           "housing and government schemes. {worker} created this record themselves.",
    "money": "It means that, according to {worker}, this is what you paid them for their work. {claim}",
    "why": "{worker} has no other proof of their income. Your confirmation makes their record trustworthy. Nothing is asked of you.",
    "work": "According to {worker}, they do {work} for you.",
    "privacy": "Your number is not shown to anyone. The call is recorded only as proof of your answer.",
    "remark": "You'd know that better than me.",
    "other": "Sorry, I can only talk about this record of {worker}'s.",
}


# ---- every other language: the English template, pre-translated ---------------------------------
class _ByLang(dict):
    def __missing__(self, key):
        en = self["en-IN"]
        return [tr(key, x) for x in en] if isinstance(en, list) else tr(key, en)


def _wrap_all() -> None:
    g = globals()
    for k, v in list(g.items()):
        if isinstance(v, dict) and not isinstance(v, _ByLang):
            if set(v) == {"hi-IN", "en-IN"}:
                g[k] = _ByLang(v)
            elif v and all(isinstance(x, dict) and set(x) == {"hi-IN", "en-IN"} for x in v.values()):
                g[k] = {kk: _ByLang(x) for kk, x in v.items()}


_wrap_all()


# Small pieces composed in code (not in a table above); listed so the build script translates them.
PIECES = [
    "{a} to {b}", "{n} rupees", "employer", "number {phone}", "{d} days", "not fully paid yet", "we won't call them",
    "I have noted: {items}. Is that right? Please say yes or no.",
    "Hello {employer}, this is Saakshi. We keep free work records for workers. {who} has recorded the work they did for "
    "you and needs your confirmation. It takes twenty seconds, and this call is recorded. Shall I go ahead?",
    "from {a} to {b}, {amt} a month", "{amt} for {d} days ({when})", "{amt} in {when}",
    "{worker} says they did {work} for you, and you paid them {runs}. Is that right?",
    "For {site}, the records are: {parts}. Is everything correct? If anyone is different, tell me their name.",
    "your site", "them", "and", "Sure, I'll wait.", "Okay, so what was the correct amount?",
    "tomorrow morning", "tomorrow evening", "this evening", "a little later", "in {h} hour(s)",
]
EXTRA: list[str] = []          # other modules register their templates here (passport, links)


def all_templates() -> list[str]:
    out: list[str] = []
    for v in list(globals().values()):
        if isinstance(v, _ByLang):
            en = v["en-IN"]
            out.extend(en if isinstance(en, list) else [en])
        elif isinstance(v, dict) and v and all(isinstance(x, _ByLang) for x in v.values()):
            out.extend(x["en-IN"] for x in v.values())
    out += [m for m in MONTH_NAMES_EN if m] + [en for _, en in WORK.values()] + ["work"]
    out += list(FAQ_EN.values()) + PIECES + EXTRA
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]
