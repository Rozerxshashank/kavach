"""The languages Saakshi speaks and hears.

Every language here was checked end to end: Timbre speaks it and Prisma hears it
back word for word. Hindi and English lines are hand-written (lines.py). For the
other languages the same English line is translated once by the LLM and cached;
the translation is rejected if a single number in it changes, so what a person
hears always matches what is recorded.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from . import llm
from .config import settings

LangCode = Literal["hi-IN", "en-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN"]

LANGS: dict[str, dict] = {
    "hi-IN": {"native": "हिन्दी", "english": "Hindi"},
    "en-IN": {"native": "English", "english": "English"},
    "ta-IN": {"native": "தமிழ்", "english": "Tamil"},
    "te-IN": {"native": "తెలుగు", "english": "Telugu"},
    "kn-IN": {"native": "ಕನ್ನಡ", "english": "Kannada"},
    "ml-IN": {"native": "മലയാളം", "english": "Malayalam"},
    "mr-IN": {"native": "मराठी", "english": "Marathi"},
    "bn-IN": {"native": "বাংলা", "english": "Bengali"},
    "gu-IN": {"native": "ગુજરાતી", "english": "Gujarati"},
}

HAND_WRITTEN = ("hi-IN", "en-IN")


def valid(lang: str | None) -> bool:
    return lang in LANGS


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_HINDI_ROMAN = re.compile(r"\b(hai|hain|haan|han|nahi|nahin|kya|kyun|aap|aapka|aapke|ji|mein|mera|meri|hum|ke|ka|ki|ko|se|"
                         r"karo|kariye|kijiye|bolo|boliye|bataiye|batao|theek|thik|accha|acha|matlab|abhi|kaun|kahan|"
                         r"kitna|kitne|wala|wali|liye|toh|bhi|sab|sabhi|chahiye|dijiye|rupaye|paise)\b", re.I)


def sounds_hindi(text: str) -> bool:
    """Is the caller actually speaking Hindi/Hinglish? Devanagari, or a few everyday Hindi words in Roman letters."""
    t = text or ""
    if _DEVANAGARI.search(t):
        return True
    return len(_HINDI_ROMAN.findall(t)) >= 2


def base(lang: str) -> str:
    """The hand-written language a line is composed in before translation."""
    return lang if lang in HAND_WRITTEN else "en-IN"


def name(lang: str) -> str:
    return LANGS.get(lang, LANGS["en-IN"])["english"]


# ---- numbers must survive translation ---------------------------------------------------
_DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯૦૧૨૩૪૫૬૭૮૯௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯೦೧೨೩೪೫೬೭೮೯൦൧൨൩൪൫൬൭൮൯",
                        "0123456789" * 7)


def numbers_in(text: str) -> list[int]:
    t = (text or "").translate(_DIGITS)
    return sorted(int(re.sub(r"\D", "", m)) for m in re.findall(r"\d[\d,]*", t) if re.sub(r"\D", "", m))


# ---- translation cache ----------------------------------------------------------------------
_CACHE_PATH = settings.data_dir / "translations.json"
_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CACHE_PATH.read_text())
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _key(text: str, lang: str) -> str:
    return lang + ":" + hashlib.sha1(text.encode()).hexdigest()[:16]


TRANSLATE = """You are a professional translator for Saakshi, a voice app (a free work-record service for informal workers
in India). The user message contains ONE line that Saakshi, a polite woman, will SPEAK to a worker or an employer,
inside <line> tags. Translate that line into natural, simple, spoken {lang}, as an ordinary person in India would say
it on the phone. You only translate: never answer the line, never refuse, never add or drop sentences.
- Keep every number exactly as written, in Western digits (3,500 stays 3,500).
- Keep people's names and "Saakshi" (you may write them in {lang} script).
- Translate quoted phrases too. Use respectful forms of address.
- Common English words people use in India (OTP, UPI, WhatsApp, link, record) may stay in English.
Reply ONLY with JSON: {{"text": "<the full translation>"}}"""


async def localize(text: str, lang: str) -> str:
    """Hindi/English pass straight through; other languages get a cached, number-checked translation."""
    if lang in HAND_WRITTEN or lang not in LANGS or not text.strip():
        return text
    letters = re.findall(r"[^\W\d_]", text)
    if letters and sum(c.isascii() for c in letters) < len(letters) / 2:
        return text                               # already written in an Indian script (e.g. the model's own reply)
    cache = _load()
    k = _key(text, lang)
    if k in cache:
        return cache[k]
    for model in (settings.agent_model, settings.fast_model):
        try:
            out = await llm.chat_json(model, [
                {"role": "system", "content": TRANSLATE.format(lang=name(lang))},
                {"role": "user", "content": f"<line>{text}</line>"}], temperature=0.1, max_tokens=1200)
        except llm.LLMError:
            continue
        said = str(out.get("text") or "").strip()
        # a real translation keeps every number and is roughly as long as the original
        if said and numbers_in(said) == numbers_in(text) and 0.35 * len(text) <= len(said) < 4 * len(text) + 80:
            cache[k] = said
            _save()
            return said
    return text                                   # English is better than a wrong number


def _save() -> None:
    try:
        _CACHE_PATH.write_text(json.dumps(_load(), ensure_ascii=False))
    except OSError:
        pass


# ---- phone numbers said in words, in any language ---------------------------------------------
# The model only TRANSLATES each spoken group into English number words (it is good at that); the
# arithmetic is done here, exactly. Models are unreliable at turning "98 thousand 765" into digits.
_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine".split())} | {"oh": 0, "o": 0}
_TEENS = {w: i + 10 for i, w in enumerate("ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: (i + 2) * 10 for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"thousand": 1000, "lakh": 100000, "lac": 100000}


def english_digits(words: str) -> str | None:
    """English number words -> the digits as spoken, number after number:
    'ninety-eight thousand seven hundred sixty-five forty three thousand two hundred ten' -> '9876543210',
    'ninety eight seventy six' -> '9876', 'nine eight double seven' -> '9877'. None if a word isn't a number word."""
    toks = [t for t in re.findall(r"[a-z]+|\d+", (words or "").lower().replace("-", " ")) if t != "and"]
    out: list[str] = []
    total = cur = 0
    last = ""                      # kind of the previous token in the current number: unit|teen|tens|hundred|scale
    open_ = False
    rep = 1

    def flush():
        nonlocal total, cur, last, open_
        if open_:
            out.append(str(total + cur) * rep_used[0])
        total = cur = 0; last = ""; open_ = False

    rep_used = [1]
    for t in toks:
        if t in ("double", "triple"):
            flush(); rep = 2 if t == "double" else 3; continue
        kind = ("unit" if t in _UNITS else "teen" if t in _TEENS else "tens" if t in _TENS else
                "hundred" if t == "hundred" else "scale" if t in _SCALES else "digits" if t.isdigit() else None)
        if kind is None:
            return None
        if kind == "digits":
            flush(); out.append(t * rep); rep = 1; continue
        starts_new = open_ and (
            (kind == "unit" and last in ("unit", "teen")) or
            (kind in ("tens", "teen") and last in ("unit", "teen", "tens")) or
            (kind == "scale" and last in ("scale", "")))
        if starts_new:
            flush()
        if not open_:
            rep_used[0] = rep; rep = 1
        open_ = True
        if kind == "unit": cur += _UNITS[t]
        elif kind == "teen": cur += _TEENS[t]
        elif kind == "tens": cur += _TENS[t]
        elif kind == "hundred": cur = max(cur, 1) * 100
        else: total += max(cur, 1) * _SCALES[t]; cur = 0
        last = kind
    flush()
    return "".join(out) or None


PHONE = """A worker in India said a mobile phone number out loud in {lang}; below is the speech transcript. People say
numbers in groups ("98765 43210" as "ninety-eight thousand seven hundred sixty-five, forty-three thousand two hundred
ten"), in pairs, digit by digit, or with "double"/"triple". Split it into the groups as spoken and, for each group,
write the same words in ENGLISH number words, word for word (do not calculate; "தொண்ணூற்றி எட்டு ஆயிரத்தி" ->
"ninety eight thousand"). Ignore words that are not part of the number.
Reply ONLY with JSON: {{"groups": [{{"words": "<the group as transcribed>", "english": "<the same in English number words>"}}]}}"""


async def spoken_phone(text: str, lang: str) -> str | None:
    """Digits of a phone number said in words in any language, or None if it doesn't come out as a mobile number."""
    for model in (settings.agent_model, settings.fast_model):
        try:
            out = await llm.chat_json(model, [{"role": "system", "content": PHONE.format(lang=name(lang))},
                                             {"role": "user", "content": text}], temperature=0.0, max_tokens=1500)
        except llm.LLMError:
            continue
        words = " ".join(str(g.get("english") or "") for g in out.get("groups") or [] if isinstance(g, dict))
        number = english_digits(words)
        if not number:
            continue
        if len(number) == 12 and number.startswith("91"):
            number = number[2:]
        if len(number) == 10 and number[0] in "6789":
            return number
    return None
