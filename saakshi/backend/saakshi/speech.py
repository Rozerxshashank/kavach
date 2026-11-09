"""Make text sound right before Timbre speaks it.

Names are stored in Roman letters ("Khanna", "Lakshmi"), but a Hindi voice reads Roman letters as English:
Timbre says "Khanna" as खाना (food). So before an Indian-language line is spoken, every Roman word in it is
written in that language's own script. Known names come from a small seed list; anything new is
transliterated once by the fast model and cached on disk, so the next call costs nothing. If that fails the
word is left as it is: speech is never blocked on this.

Only the audio changes. The text shown on screen and saved in the record stays exactly as written."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata

from . import llm
from .config import settings

SCRIPTS = {  # language -> (script name for the prompt, Unicode block)
    "hi": ("Devanagari (Hindi)", (0x0900, 0x097F)),
    "mr": ("Devanagari (Marathi)", (0x0900, 0x097F)),
    "bn": ("Bengali", (0x0980, 0x09FF)),
    "ta": ("Tamil", (0x0B80, 0x0BFF)),
    "te": ("Telugu", (0x0C00, 0x0C7F)),
    "kn": ("Kannada", (0x0C80, 0x0CFF)),
}

# Names that appear across the product, checked by ear (Timbre -> Prisma round trip).
SEED_DEVANAGARI = {
    "khanna": "खन्ना", "lakshmi": "लक्ष्मी", "sunita": "सुनीता", "bhatia": "भाटिया", "sharma": "शर्मा",
    "verma": "वर्मा", "gupta": "गुप्ता", "mehta": "मेहता", "kapoor": "कपूर", "singh": "सिंह", "rathore": "राठौर",
    "saakshi": "साक्षी", "sakshi": "साक्षी", "kavach": "कवच", "meena": "मीना", "kamla": "कमला", "kamala": "कमला",
    "rekha": "रेखा", "geeta": "गीता", "gita": "गीता", "anita": "अनीता", "savitri": "सावित्री", "pushpa": "पुष्पा",
    "radha": "राधा", "ramesh": "रमेश", "suresh": "सुरेश", "mahesh": "महेश", "raju": "राजू", "ravi": "रवि",
    "iyer": "अय्यर", "nair": "नायर", "reddy": "रेड्डी", "joshi": "जोशी", "agarwal": "अग्रवाल", "malhotra": "मल्होत्रा",
    "chopra": "चोपड़ा", "bansal": "बंसल", "jain": "जैन", "patel": "पटेल", "shah": "शाह", "desai": "देसाई",
    "kumar": "कुमार", "kumari": "कुमारी", "devi": "देवी", "ji": "जी",
}

_LATIN = re.compile(r"[A-Za-z][A-Za-z']*")
_lock = asyncio.Lock()
_cache: dict[str, str] | None = None


def _path():
    return settings.data_dir / "translit.json"


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        _cache = {f"hi:{k}": v for k, v in SEED_DEVANAGARI.items()} | {f"mr:{k}": v for k, v in SEED_DEVANAGARI.items()}
        try:
            _cache |= {k: v for k, v in json.loads(_path().read_text()).items() if isinstance(v, str)}
        except (OSError, ValueError):
            pass
    return _cache


def _save() -> None:
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(_cache, ensure_ascii=False, indent=0))
        tmp.replace(_path())
    except OSError:
        pass


def _in_script(word: str, block: tuple[int, int]) -> bool:
    lo, hi = block
    return bool(word) and all(lo <= ord(c) <= hi or c in "‌‍" for c in word)


def _words(text: str) -> list[str]:
    # ALL-CAPS tokens (OTP, UPI, PAN) are read letter by letter already; leave them alone.
    return [w for w in _LATIN.findall(text) if not (len(w) > 1 and w.isupper())]


async def _learn(lang: str, words: list[str]) -> None:
    script, block = SCRIPTS[lang]
    prompt = (f"Write each of these words in {script} script, spelled the way Indians pronounce it aloud. "
              "They are mostly Indian names written in English letters. Transliterate, never translate. Use the "
              "established native spelling of the name, with long vowels where Indians say them; a final 'a' in a "
              "name is usually long. Examples in Devanagari: Khanna=खन्ना, Bhardwaj=भारद्वाज, Parvathi=पार्वती, "
              "Bhatia=भाटिया, Rathore=राठौर, Iyer=अय्यर. "
              'Reply as JSON: {"map": {"<word>": "<transliteration>"}}\nWords: ' + json.dumps(words))
    try:
        out = await asyncio.wait_for(llm.chat_json(settings.agent_model, [{"role": "user", "content": prompt}],
                                                   temperature=0, max_tokens=1200), timeout=8)
    except Exception:  # noqa: BLE001 - speech must never wait on this
        return
    got = out.get("map") if isinstance(out.get("map"), dict) else {}
    cache = _load()
    lower = {k.lower(): v for k, v in got.items() if isinstance(v, str)}
    for w in words:
        v = unicodedata.normalize("NFC", (lower.get(w.lower()) or "").strip())
        if _in_script(v, block):
            cache[f"{lang}:{w.lower()}"] = v
    _save()


async def for_speech(text: str, language: str) -> str:
    """The text Timbre should read for `language` (e.g. "hi-IN")."""
    lang = (language or "").split("-")[0].lower()
    if lang in ("hi", "mr") and text:
        text = _say_numbers(text)
    if lang not in SCRIPTS or not text or not _LATIN.search(text):
        return text
    cache = _load()
    missing = sorted({w.lower() for w in _words(text)} - {k.split(":", 1)[1] for k in cache if k.startswith(lang + ":")})
    if missing:
        async with _lock:
            still = [w for w in missing if f"{lang}:{w}" not in cache]
            if still:
                await _learn(lang, still[:24])

    def swap(m: re.Match) -> str:
        w = m.group(0)
        if len(w) > 1 and w.isupper():
            return w
        return cache.get(f"{lang}:{w.lower()}", w)
    return _LATIN.sub(swap, text)


# ---- numbers, said the way people say them ------------------------------------------------------
_HI_0_99 = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस "
            "बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस "
            "अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास "
            "इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ "
            "अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी "
            "बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानबे बानबे तिरानबे चौरानबे पचानबे "
            "छियानबे सत्तानबे अट्ठानबे निन्यानबे").split()
assert len(_HI_0_99) == 100


def hindi_number(n: int) -> str:
    """4000 -> 'चार हज़ार', 3200 -> 'तीन हज़ार दो सौ', 150000 -> 'एक लाख पचास हज़ार'."""
    if n < 100:
        return _HI_0_99[n]
    out = []
    for size, word in ((10**7, "करोड़"), (10**5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= size:
            out.append(f"{hindi_number(n // size)} {word}")
            n %= size
    if n:
        out.append(_HI_0_99[n])
    return " ".join(out)


_RUPEE = re.compile(r"(?:₹|Rs\.?|INR)\s*(\d[\d,]*)(?![\d,])(?!\s*(?:रुपये|रुपए|रुपया))")
_INT = re.compile(r"(?<![\w.:,/-])(\d{1,3}(?:,\d{2,3})+|\d+)(?![\w.,:/-]*\w)")


def _say_numbers(text: str) -> str:
    text = re.sub(r"(?:₹|Rs\.?|INR)\s*(?=\d[\d,]*\s*(?:रुपये|रुपए|रुपया))", "", text)   # "₹500 रुपये"
    text = _RUPEE.sub(lambda m: f"{m.group(1)} रुपये", text)

    def word(m: re.Match) -> str:
        raw = m.group(1).replace(",", "")
        if len(raw) >= 7 and "," not in m.group(1):          # a phone or account number: digit by digit
            return " ".join(_HI_0_99[int(d)] for d in raw)
        return hindi_number(int(raw)) if len(raw) <= 9 else m.group(1)
    return _INT.sub(word, text)
