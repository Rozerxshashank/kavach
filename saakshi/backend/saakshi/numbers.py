"""Deterministic parsing of how Indians actually say money and dates.

The LLM proposes what a worker meant; this module checks it. Money is the one
thing Saakshi must never get wrong, so amounts are always re-derived here from
the exact words the worker used, and read back before anything is saved.

Handles:
  * digits with Indian grouping and Devanagari numerals:  4,500 · ४५०० · 4.5k
  * Hindi / Hinglish number words (1-100, sau, hazaar, lakh, crore)
  * fractional idioms:  sava (+¼), saade (+½), paune (−¼), dedh (1½), dhai (2½)
        "paune paanch hazaar" = 4,750 · "saade teen sau" = 350 · "dedh lakh" = 1,50,000
  * English number words:  "four thousand five hundred"
  * relative and named periods:  parso · pichle hafte · is mahine · October · अक्टूबर
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_HINDI_1_100 = """
ek do teen chaar paanch chhah saat aath nau das gyaarah baarah terah chaudah pandrah solah satrah athaarah
unnees bees ikkees baaees teyees chaubees pachchees chhabbees sattaees atthaees untees tees ikattees battees
taintees chauntees paintees chhattees saintees adtees untaalees chaalees iktaalees bayaalees taintaalees
chavaalees paintaalees chhiyaalees saintaalees adtaalees unchaas pachaas ikyaavan baavan tirpan chauvan pachpan
chhappan sattaavan atthaavan unsath saath iksath baasath tirsath chaunsath painsath chhiyaasath sadsath adsath
unhattar sattar ikhattar bahattar tihattar chauhattar pachhattar chhihattar sathattar athhattar unaasi assi
ikyaasi bayaasi tiraasi chauraasi pachaasi chhiyaasi sattaasi atthaasi navaasi nabbe ikyaanbe baanbe tiraanbe
chauraanbe pachaanbe chhiyaanbe sattaanbe atthaanbe ninyaanbe
""".split()

_EXTRA_ROMAN = {
    "char": 4, "panch": 5, "chhe": 6, "che": 6, "chha": 6, "chah": 6, "gyara": 11, "bara": 12, "pandra": 15,
    "pachis": 25, "pachees": 25, "pacchis": 25, "pachas": 50, "tis": 30, "bis": 20, "chalis": 40, "sath": 60,
    "nabbe": 90, "nabe": 90, "zero": 0, "shunya": 0,
}

_DEVA_WORDS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30,
    "पैंतीस": 35, "चालीस": 40, "पैंतालीस": 45, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}

_ENGLISH = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}

MULTIPLIERS = {
    "sau": 100, "so": 100, "hundred": 100, "सौ": 100,
    "hazaar": 1000, "hazar": 1000, "hajar": 1000, "hajaar": 1000, "thousand": 1000, "हज़ार": 1000, "हजार": 1000, "k": 1000,
    "lakh": 100000, "lac": 100000, "lakhs": 100000, "लाख": 100000,
    "crore": 10000000, "karod": 10000000, "करोड़": 10000000,
}

# fraction idioms: (kind, value). "prefix" modifies the following number, "whole" is a quantity by itself.
FRACTIONS = {
    "sava": ("plus", 0.25), "savaa": ("plus", 0.25), "सवा": ("plus", 0.25),
    "saade": ("plus", 0.5), "sade": ("plus", 0.5), "saadhe": ("plus", 0.5), "sadhe": ("plus", 0.5), "साढ़े": ("plus", 0.5), "साढे": ("plus", 0.5),
    "paune": ("minus", 0.25), "pone": ("minus", 0.25), "पौने": ("minus", 0.25),
    "dedh": ("whole", 1.5), "derh": ("whole", 1.5), "डेढ़": ("whole", 1.5), "डेढ": ("whole", 1.5),
    "dhai": ("whole", 2.5), "adhai": ("whole", 2.5), "dhaai": ("whole", 2.5), "ढाई": ("whole", 2.5),
    "aadha": ("whole", 0.5), "adha": ("whole", 0.5), "आधा": ("whole", 0.5),
}

_NOISE = {"rs", "rupees", "rupaye", "rupay", "rupiya", "rupye", "rupaiye", "रुपये", "रुपए", "रूपये", "रुपया", "₹",
          "inr", "ka", "ke", "ki", "and", "aur", "rupee"}


def _canon(word: str) -> str:
    w = word.lower()
    for a, b in (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("w", "v"), ("chch", "ch"), ("tth", "th")):
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


_WORD_VALUES: dict[str, int] = {}
for _i, _w in enumerate(_HINDI_1_100, start=1):
    _WORD_VALUES[_canon(_w)] = _i
for _w, _v in {**_EXTRA_ROMAN, **_ENGLISH}.items():
    _WORD_VALUES.setdefault(_canon(_w), _v)
_MULT_CANON = {_canon(k): v for k, v in MULTIPLIERS.items()}
_FRAC_CANON = {_canon(k): v for k, v in FRACTIONS.items()}


def _tokens(text: str) -> list[str]:
    t = (text or "").translate(DEVA_DIGITS).lower().replace("₹", " ₹ ")
    t = re.sub(r"(\d),(?=\d)", r"\1", t)                 # 4,500 / 1,42,890 -> plain digits
    t = re.sub(r"(\d)\s*k\b", r"\1 k", t)                 # 4k / 4.5k
    return re.findall(r"\d+(?:\.\d+)?|[a-z]+|[ऀ-ॿ]+|₹", t)


def _number_value(tok: str) -> float | None:
    if re.fullmatch(r"\d+(?:\.\d+)?", tok):
        return float(tok)
    if tok in _DEVA_WORDS:
        return float(_DEVA_WORDS[tok])
    c = _canon(tok)
    if c in _WORD_VALUES:
        return float(_WORD_VALUES[c])
    return None


def _mult(tok: str) -> int | None:
    return MULTIPLIERS.get(tok) or _MULT_CANON.get(_canon(tok))


def _frac(tok: str):
    return FRACTIONS.get(tok) or _FRAC_CANON.get(_canon(tok))


def _classify(text: str) -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    for tok in _tokens(text):
        if tok in _NOISE:
            continue
        frac = _frac(tok)
        if frac:
            items.append(("frac", frac))
            continue
        n = _number_value(tok)
        if n is not None:
            items.append(("num", n))
            continue
        m = _mult(tok)
        if m:
            items.append(("mult", m))
            continue
        items.append(("other", tok))
    return items


def parse_numbers(text: str) -> list[float]:
    """Every numeric quantity in the text, in order, with Indian idioms resolved.

    Grammar (informally):  quantity := term (MULT)* [quantity-after-thousands]
                           term     := NUM | FRAC_PREFIX NUM | FRAC_WHOLE
    """
    items = _classify(text)
    out: list[float] = []
    i = 0
    while i < len(items):
        if items[i][0] not in ("num", "frac"):
            i += 1
            continue
        total, cur, from_hundred, started = 0.0, None, False, False
        while i < len(items):
            kind, val = items[i]
            if kind == "frac":
                fkind, fval = val  # type: ignore[misc]
                if cur is not None:
                    break                               # a new quantity starts here
                if fkind == "whole":
                    cur, started = float(fval), True
                    i += 1
                    continue
                if i + 1 < len(items) and items[i + 1][0] == "num":
                    n = float(items[i + 1][1])          # type: ignore[arg-type]
                    # speech-to-text writes "paune paanch hazaar" as "पौने 5,000": the fraction is of the
                    # leading unit (a quarter of a thousand), not of one rupee
                    unit = 10 ** (len(str(int(n))) - 1) if n >= 10 and n == int(n) else 1
                    if unit > 1 and n % unit:
                        unit = 1
                    cur, started = (n + fval * unit if fkind == "plus" else n - fval * unit), True
                    i += 2
                    continue
                i += 1
                break
            if kind == "num":
                n = float(val)                          # type: ignore[arg-type]
                if cur is None:
                    cur, started = n, True
                    i += 1
                    continue
                if from_hundred and n < 100:            # "do sau pachaas" = 250
                    cur += n
                    from_hundred = False
                    i += 1
                    continue
                break                                   # "3000 2500" = two quantities
            if kind == "mult":
                if not started:
                    i += 1
                    break
                base = cur if cur is not None else 1.0
                if val == 100:
                    cur, from_hundred = base * 100, True
                else:
                    total += base * float(val)          # type: ignore[arg-type]
                    cur, from_hundred = None, False
                i += 1
                continue
            break                                       # any other word ends the quantity
        if started:
            out.append(round(total + (cur or 0.0), 2))
    return out


def parse_amount(text: str) -> float | None:
    """The money amount in a phrase: the largest quantity mentioned (₹ amounts dwarf day counts)."""
    nums = [n for n in parse_numbers(text) if n > 0]
    return max(nums) if nums else None


def inr(amount: float | None) -> str:
    """Indian digit grouping: 142890.5 -> ₹1,42,890.50 ; 4500 -> ₹4,500"""
    if amount is None:
        return "—"
    neg = amount < 0
    whole = int(abs(amount) + 0.5)           # half-up, not banker's rounding
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if neg else "") + "₹" + s


def spoken_amount_hi(amount: float) -> str:
    """How Saakshi says money back in Hindi, unambiguous for read-back: '4 हज़ार 750 रुपये'."""
    a = int(amount + 0.5)
    parts = []
    lakh, rem = divmod(a, 100000)
    thou, rem = divmod(rem, 1000)
    if lakh:
        parts.append(f"{lakh} लाख")
    if thou:
        parts.append(f"{thou} हज़ार")
    if rem or not parts:
        parts.append(str(rem))
    return " ".join(parts) + " रुपये"


# ---- periods -------------------------------------------------------------------------
MONTHS = {
    1: ["jan", "january", "janvari", "january", "जनवरी"],
    2: ["feb", "february", "farvari", "farwari", "फरवरी", "फ़रवरी"],
    3: ["mar", "march", "maarch", "मार्च"],
    4: ["apr", "april", "aprail", "अप्रैल"],
    5: ["may", "mai", "मई"],
    6: ["jun", "june", "joon", "जून"],
    7: ["jul", "july", "julai", "जुलाई"],
    8: ["aug", "august", "agast", "अगस्त"],
    9: ["sep", "sept", "september", "sitambar", "सितंबर", "सितम्बर"],
    10: ["oct", "october", "aktubar", "aktoobar", "अक्टूबर", "अक्तूबर"],
    11: ["nov", "november", "navambar", "नवंबर", "नवम्बर"],
    12: ["dec", "december", "disambar", "दिसंबर", "दिसम्बर"],
}
_MONTH_LOOKUP = {_canon(w): m for m, ws in MONTHS.items() for w in ws}
MONTH_NAMES_EN = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"]
MONTH_NAMES_HI = ["", "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
                  "नवंबर", "दिसंबर"]


@dataclass
class Period:
    start: date
    end: date
    label: str          # human label, English
    exact: bool = True  # False when we had to guess

    def to_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "label": self.label, "exact": self.exact}


def _month_period(year: int, month: int, today: date) -> Period:
    start = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    end = min(nxt - timedelta(days=1), today) if (year, month) == (today.year, today.month) else nxt - timedelta(days=1)
    return Period(start, end, f"{MONTH_NAMES_EN[month]} {year}")


def parse_period(text: str, today: date) -> Period | None:
    t = (text or "").lower().translate(DEVA_DIGITS)
    words = re.findall(r"[a-z]+|[ऀ-ॿ]+|\d+", t)
    canon = [_canon(w) for w in words]
    joined = " ".join(words)

    def has(*phrases: str) -> bool:
        return any(p in joined for p in phrases)

    if has("aaj", "today", "आज"):
        return Period(today, today, "today")
    if has("parso", "parson", "परसों", "day before yesterday"):
        d = today - timedelta(days=2)
        return Period(d, d, d.isoformat())
    if has("kal", "yesterday", "कल"):
        d = today - timedelta(days=1)          # a work log is about the past
        return Period(d, d, d.isoformat())
    if has("pichle hafte", "pichhle hafte", "last week", "पिछले हफ्ते", "पिछले हफ़्ते", "pichle saptah"):
        start = today - timedelta(days=today.weekday() + 7)
        return Period(start, start + timedelta(days=6), f"week of {start.isoformat()}")
    if has("is hafte", "this week", "इस हफ्ते", "इस हफ़्ते"):
        start = today - timedelta(days=today.weekday())
        return Period(start, today, f"week of {start.isoformat()}")
    if has("pichle mahine", "pichhle mahine", "last month", "पिछले महीने", "pichla mahina"):
        m, y = (today.month - 1 or 12), today.year - (today.month == 1)
        return _month_period(y, m, today)
    if has("is mahine", "this month", "इस महीने", "is mahina"):
        return _month_period(today.year, today.month, today)

    for i, c in enumerate(canon):
        if c in _MONTH_LOOKUP:
            month = _MONTH_LOOKUP[c]
            year = None
            for w in words[i + 1:i + 3]:
                if re.fullmatch(r"(19|20)\d\d", w):
                    year = int(w)
            if year is None:
                year = today.year if month <= today.month else today.year - 1
            return _month_period(year, month, today)
    return None


# ---- phone numbers said out loud ----------------------------------------------------------
_DIGIT_WORD = {
    "zero": "0", "shunya": "0", "sunya": "0", "oh": "0", "o": "0", "शून्य": "0", "जीरो": "0",
    "one": "1", "ek": "1", "एक": "1", "two": "2", "do": "2", "दो": "2", "three": "3", "teen": "3", "तीन": "3",
    "four": "4", "char": "4", "chaar": "4", "चार": "4", "five": "5", "paanch": "5", "panch": "5", "पांच": "5", "पाँच": "5",
    "six": "6", "chhah": "6", "chhe": "6", "che": "6", "chah": "6", "chha": "6", "छह": "6", "छः": "6", "छे": "6",
    "seven": "7", "saat": "7", "सात": "7", "eight": "8", "aath": "8", "आठ": "8", "nine": "9", "nau": "9", "नौ": "9",
}
_REPEAT = {"double": 2, "dabal": 2, "डबल": 2, "triple": 3, "tripal": 3, "ट्रिपल": 3}


def phone_digits(text: str) -> str:
    """Digits of a phone number however it was said: '98111 22334', 'nau aath ek ek…', 'double five'."""
    t = (text or "").lower().translate(DEVA_DIGITS)
    out: list[str] = []
    repeat = 1
    for tok in re.findall(r"\d+|[a-z]+|[\u0900-\u097F]+", t):
        if tok.isdigit():
            out.append(tok * repeat if len(tok) == 1 else tok)
            repeat = 1
        elif tok in _REPEAT:
            repeat = _REPEAT[tok]
        elif tok in _DIGIT_WORD:
            out.append(_DIGIT_WORD[tok] * repeat)
            repeat = 1
    return "".join(out)
