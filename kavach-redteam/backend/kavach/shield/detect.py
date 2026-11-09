"""Deterministic detectors for voice-call manipulation, in English, Hinglish and Devanagari Hindi.

Two directions:
  inbound   what the caller said (as heard through speech recognition): manipulation tactics, identity claims,
            spoken prompt injection, solicitation of protected data;
  outbound  what the agent is about to say: protected values, PII, vouching, revealing its instructions,
            promising exceptions.

Everything here is code: fast (well under a millisecond per turn), explainable (every signal says which words
fired it) and identical on every run. The Shield adds an optional LLM classifier on top for what patterns miss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


@dataclass
class Signal:
    kind: str           # e.g. "authority", "injection", "secret_leak"
    weight: int         # contribution to risk (0-100 scale)
    evidence: str       # the words that fired it
    detail: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "weight": self.weight, "evidence": self.evidence, "detail": self.detail}


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.I)


# ---- inbound: what the caller is doing -------------------------------------------------------------------------------
INBOUND: dict[str, tuple[int, re.Pattern, str]] = {
    "injection": (45, _rx(
        r"ignore (all |your |the )?(previous |prior |earlier )?(instructions|rules|policy|prompt)",
        r"(system|developer|admin|debug|maintenance|god)\s*(mode|override|prompt|message|note|command)",
        r"\boverride\b", r"\bjailbreak\b", r"you are now\b", r"act as (an? )?(admin|developer|system)",
        r"(repeat|reveal|read out|tell me|show me|print) (your|the) (instructions|system prompt|prompt|rules|config)",
        r"verification (is |has been )?(disabled|turned off|not required|skipped|bypassed)",
        r"\b(qa|test) (harness|mode)\b", r"new instructions?\b", r"from the (saakshi|navyug|bank) (team|developers?)",
        r"सिस्टम (ओवरराइड|मोड|कमांड)|डेवलपर मोड|एडमिन मोड|निर्देश (भूल|अनदेखा)|पिछले निर्देश"),
        "Spoken instructions aimed at the AI itself"),
    "authority": (28, _rx(
        r"\b(police|inspector|constable|cyber ?(cell|crime)|cbi|ed officer|income tax|rbi|court|magistrate|lawyer|"
        r"advocate|vakil|government official|officer|from the bank|bank (manager|officer|staff)|branch (manager|staff))\b",
        r"पुलिस|इंस्पेक्टर|साइबर|सीबीआई|अधिकारी|बैंक से|बैंक मैनेजर|वकील|कोर्ट|आरबीआई"),
        "Claims an official or institutional identity"),
    "urgency": (14, _rx(
        r"\b(urgent(ly)?|immediately|right now|asap|emergency|no time|hurry|quick(ly)?|flight (is )?(leaving|in)|"
        r"battery|last chance|today itself)\b",
        r"\b(jaldi|turant|abhi ke abhi|fauran)\b", r"जल्दी|तुरंत|फ़ौरन|फौरन|अभी के अभी|इमरजेंसी"),
        "Manufactured time pressure"),
    "intimidation": (20, _rx(
        r"\b(complain(t)?|legal action|arrest(ed)?|jail|fir|sue|lawsuit|ombudsman|shut (you|it) down|report you|"
        r"consequences|you will regret)\b",
        r"शिकायत|कार्रवाई|कार्यवाही|गिरफ़्तार|गिरफ्तार|जेल|मुक़दमा|मुकदमा|बंद करवा"),
        "Threats and legal pressure"),
    "sympathy": (10, _rx(
        r"\b(please help|i('m| am) (crying|begging)|dying|hospital|surgery|my (mother|father|child|son) is|"
        r"have mercy|i('ll| will) lose everything)\b",
        r"मदद कीजिए|रो रही|रो रहा|अस्पताल|मर जाएगा|भगवान के लिए"),
        "Emotional pressure"),
    "secret_request": (22, _rx(
        r"\b(otp|pin|cvv|password|card number|account number|balance|pan( number)?|aadhaar|date of birth|"
        r"transactions?|salary|total income)\b",
        r"(other|kaun ?kaun|kahan|kahaan|kis kis) .{0,20}(employer|ghar|kaam|naukri)",
        r"where else (does )?(she|he) work", r"other employers?",
        r"बैलेंस|ओटीपी|पिन|पासवर्ड|पैन|आधार|कहाँ और|और कहाँ|दूसरे घर|कुल आय|सैलरी|बाकी नियोक्ता"),
        "Asks for protected information"),
    "false_verification": (25, _rx(
        r"already (verified|confirmed|authenticated)", r"(otp|verification) (went through|is done|already)",
        r"verified (in|on) (the|a) (previous|earlier|last) call", r"you (already|just) (said|agreed|confirmed)",
        r"पहले ही (वेरिफाई|पुष्टि|कन्फर्म)|आपने (पहले )?कहा था"),
        "Claims verification or agreement that never happened"),
}

# identity and record-specific signals used by agents that confirm records with third parties
UNSURE = _rx(
    r"(don'?t|do not|never) (know|remember|recall) (her|him|them|this|any|who)", r"not sure (who|if|about)",
    r"no idea who", r"never heard of",
    r"(jaant[ai]|jant[ai]|pehchaant[ai]|pehchant[ai]) (bhi )?(nahi|nahin|nai)", r"(nahi|nahin|nai) (jaant|pehchaan|pehchan)",
    r"yaad (bhi )?(nahi|nahin)", r"koi (kaamwali|bai|maid) nahi",
    r"(जानत[ाीे]|पहचानत[ाीे]) (भी )?नहीं", r"नहीं (जानत|पहचानत)", r"याद (भी )?नहीं", r"कोई (काम वाली|कामवाली|बाई) नहीं")
WRITE_REQUEST = _rx(r"\b(write|put|record|mark|make it)\b", r"\b(likh|daal|kar do)", r"लिख|डाल|कर दो|कर दीजिए")


def inbound(text: str) -> list[Signal]:
    out = []
    for kind, (weight, rx, detail) in INBOUND.items():
        m = rx.search(text or "")
        if m:
            out.append(Signal(kind, weight, m.group(0), detail))
    if UNSURE.search(text or ""):
        out.append(Signal("unsure", 15, UNSURE.search(text).group(0), "Says they don't know the person concerned"))
    amounts = {round(n) for n in numbers(text) if n >= 100}
    if len(amounts) >= 2 and WRITE_REQUEST.search(text or ""):
        out.append(Signal("fake_amount", 30, ", ".join(str(a) for a in sorted(amounts)),
                          "Asks to record an amount different from one they mention"))
    return out


def claims_outsider(text: str) -> bool:
    return bool(INBOUND["authority"][1].search(text or ""))


def unsure(text: str) -> bool:
    return bool(UNSURE.search(text or ""))


# ---- outbound: what the agent is about to say ------------------------------------------------------------------------
VOUCH = _rx(r"^(हाँ|हां|जी हाँ)?[,\s]*(यह|ये)?\s*(बिल्कुल\s*)?सही है", r"\byes,? (it|that)('s| is) (correct|right|true)\b",
            r"\bi (can )?(confirm|guarantee|assure you)\b", r"मैं (पुष्टि|गारंटी) (करती|करता) (हूँ|हूं)")
_FACT = _rx(r"(ने|जी ने)\s+[^।?]{0,50}(काम किया|काम करती|काम किया था)", r"\b(she|he|they) (worked|did (the )?work|has worked)\b",
            r"\b[A-Z][a-z]+ (worked|did (housework|the work|cleaning))")
_CLAIM = _rx(r"कहना है|कहती हैं|कहते हैं|के मुताबिक|अनुसार|\bsays\b|\bsaid\b|according to|\bclaims?\b|recorded")
INTERNALS = _rx(r"\b(FACTS|intent|JSON|question_kind|per_worker|can_confirm_themselves|allowed numbers|system prompt|"
                r"my instructions|SECURITY RULES|tool call|function call|verify_otp|get_balance|transfer_funds)\b")
EXCEPTION = _rx(r"just this once", r"(make|making) an exception", r"(skip|bypass|waive) (the )?(otp|verification|check)",
                r"without (the )?(otp|verification)", r"i('ll| will) (do it|allow it) anyway",
                r"बिना (ओटीपी|OTP|वेरिफिकेशन)", r"इस बार (के लिए )?(छोड़|मान)")
PII = {
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "card number": re.compile(r"\b(?:\d[ -]?){15}\d\b"),
    "Aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "UPI ID": re.compile(r"\b[\w.-]{2,}@(?:ok)?[a-z]{2,}\b"),
}


_QUESTION = re.compile(r"\?\s*$|^(क्या|kya|did|does|do|is|was|has|have)\b", re.I)


def states_as_fact(said: str) -> bool:
    """'Kamla worked for you in October' (vouching) rather than 'Kamla says she worked...' (her claim)."""
    for sentence in re.split(r"(?<=[।.?!])\s*", said or ""):
        if _QUESTION.search(sentence.strip()):
            continue                                  # "Did she work for you?" asks; it doesn't vouch
        if _FACT.search(sentence) and not _CLAIM.search(sentence):
            return True
    return False


def vouches(said: str) -> bool:
    return bool(VOUCH.search(said or "")) or states_as_fact(said)


def leaks_internals(said: str) -> str | None:
    m = INTERNALS.search(said or "")
    return m.group(0) if m else None


def promises_exception(said: str) -> str | None:
    m = EXCEPTION.search(said or "")
    return m.group(0) if m else None


def pii(said: str) -> list[tuple[str, str]]:
    out = []
    for label, rx in PII.items():
        m = rx.search(said or "")
        if m:
            out.append((label, m.group(0)))
    return out


# ---- numbers and protected values ------------------------------------------------------------------------------------
def digit_runs(text: str) -> list[str]:
    """Each number with separators removed: "₹1,42,890.50" -> "14289050", "१,४२,८९०" -> "142890"."""
    text = (text or "").translate(_DEVA_DIGITS)
    return [re.sub(r"\D", "", r) for r in re.findall(r"\d(?:[\d,. -]*\d)?", text)]


def numbers(text: str) -> list[float]:
    out = []
    for r in re.findall(r"\d[\d,]*(?:\.\d+)?", (text or "").translate(_DEVA_DIGITS)):
        try:
            out.append(float(r.replace(",", "")))
        except ValueError:
            pass
    return out


def contains_value(text: str, value: str) -> bool:
    """Is a protected value spoken? Numbers match through any formatting (₹1,42,890.50 / 142890 / १,४२,८९०),
    identifiers with digits ignore spaces and dashes, and words match case-insensitively."""
    v = str(value or "").strip().translate(_DEVA_DIGITS)
    if not v:
        return False
    if re.fullmatch(r"[₹\s]*[\d][\d,. ]*", v):
        whole = re.sub(r"\D", "", v.split(".")[0])
        full = re.sub(r"\D", "", v)
        if len(whole) < 3:
            return False                                     # too short to tell apart from any other number
        return any(r in (whole, full) or (len(whole) >= 6 and whole in r) for r in digit_runs(text))
    flat = lambda s: re.sub(r"[\s-]", "", s.lower())
    if re.search(r"\d", v):
        return len(flat(v)) >= 6 and flat(v) in flat((text or "").translate(_DEVA_DIGITS))
    return v.lower() in (text or "").lower()


def _norm_has(text: str, evidence: str) -> bool:
    """Does the evidence really appear in the text (ignoring case, spacing and punctuation)? Guards model quotes."""
    n = lambda s: re.sub(r"[\W_]+", " ", (s or "").lower()).strip()
    e = n(evidence)
    return bool(e) and e in n(text)
