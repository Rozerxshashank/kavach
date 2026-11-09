"""Pre-translate everything Saakshi says and shows into the seven languages beyond Hindi and English.

    cd backend && .venv/bin/python scripts/build_i18n.py            # only what's missing
    cd backend && .venv/bin/python scripts/build_i18n.py --redo      # everything again

Spoken lines: the English templates from saakshi/lines.py (+ passport, links)  ->  saakshi/i18n_lines.json
Screen text:  every tx(lang, "English", ...) string in web/src                  ->  web/src/lib/ui-strings.json

Each translation is checked before it is kept: the {placeholders} and numbers must be identical, and the
text must really be in the target script (not English echoed back). Anything that fails is retried alone.
Runs once at build time, so speaking and rendering never wait on a translation service.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from saakshi import agent, langs, links, llm, passport, server, trust  # noqa: E402,F401  (imports register templates)
from saakshi import lines  # noqa: E402
from saakshi.config import settings  # noqa: E402

LINES_OUT = HERE.parent / "saakshi" / "i18n_lines.json"
WEB_SRC = HERE.parents[1] / "web" / "src"
UI_OUT = WEB_SRC / "lib" / "ui-strings.json"
TARGETS = [l for l in langs.LANGS if l != "en-IN"]   # Hindi too: for text without a hand-written Hindi version
KEEP = {"saakshi", "whatsapp", "upi", "otp", "pin", "qr", "sms", "utr", "id", "l0", "l1", "l2", "l3", "bocw", "kaam",
        "passport", "timbre", "prisma", "gnani", "ji", "a", "c", "sbi", "e", "g"}

PROMPT = """You translate the words of Saakshi, a free voice app that keeps work records for informal workers in India
(maids, cooks, drivers, construction workers). Translate each item into {lang} as ordinary people in India speak and
read it: simple, warm, respectful, natural. Saakshi is a woman. Rules:
- Keep every {{placeholder}} exactly as written, e.g. {{worker}} stays {{worker}}. Never translate inside braces.
- Keep every number exactly, in Western digits.
- Write in {lang} script. Only these may stay as they are: Saakshi, WhatsApp, UPI, OTP, PIN, QR, SMS, UTR, L0-L3.
- Translate the whole item: every sentence, including quoted words. Don't add anything.
- Kind: "{kind}". {kind_note}
Input: a JSON object {{"items": [{{"id": 0, "text": "..."}}]}}.
Reply ONLY with JSON: {{"items": [{{"id": 0, "text": "<translation>"}}]}}"""
KIND = {"speech": "These lines are SPOKEN aloud by Saakshi on a call or in the app.",
        "ui": "These are short labels, buttons and messages on a phone screen. Keep them short."}


def _ph(t: str) -> list[str]:
    return sorted(re.findall(r"\{[a-z_]*\}", t))


SCRIPT = {"hi-IN": (0x0900, 0x097F), "mr-IN": (0x0900, 0x097F), "bn-IN": (0x0980, 0x09FF), "gu-IN": (0x0A80, 0x0AFF),
          "ta-IN": (0x0B80, 0x0BFF), "te-IN": (0x0C00, 0x0C7F), "kn-IN": (0x0C80, 0x0CFF), "ml-IN": (0x0D00, 0x0D7F)}


def ok(src: str, out: str, lang: str) -> bool:
    if not out or _ph(src) != _ph(out) or langs.numbers_in(src) != langs.numbers_in(out):
        return False
    lo, hi = SCRIPT[lang]
    if any(c.isalpha() and not c.isascii() and not lo <= ord(c) <= hi for c in out):
        return False                                       # a stray word from another script (seen: Korean in Kannada)
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", re.sub(r"\{[a-z_]*\}", "", out))]
    latin = sum(len(w) for w in words if w not in KEEP)
    letters = sum(1 for c in re.sub(r"\{[a-z_]*\}", "", out) if c.isalpha())
    return letters == 0 or latin / letters < 0.25          # really in the target script, not English echoed back


async def _ask(messages: list[dict]) -> dict:
    """The big model first; on its daily limit, the fast one (every answer is still validated by ok())."""
    try:
        return await llm.chat_json(settings.agent_model, messages, temperature=0.1, max_tokens=6000)
    except llm.LLMError as e:
        if "429" not in str(e):
            raise
        return await llm.chat_json(settings.fast_model, messages, temperature=0.1, max_tokens=6000)


async def translate(texts: list[str], lang: str, kind: str) -> dict[str, str]:
    done: dict[str, str] = {}
    todo = list(texts)
    for attempt in range(4):
        if not todo:
            break
        size = 14 if attempt == 0 else (5 if attempt == 1 else 1)
        nxt: list[str] = []
        for i in range(0, len(todo), size):
            chunk = todo[i:i + size]
            msg = json.dumps({"items": [{"id": n, "text": t} for n, t in enumerate(chunk)]}, ensure_ascii=False)
            try:
                out = await _ask([
                    {"role": "system", "content": PROMPT.format(lang=langs.name(lang), kind=kind, kind_note=KIND[kind])},
                    {"role": "user", "content": msg}])
                got = {int(x["id"]): str(x.get("text") or "").strip() for x in out.get("items", []) if isinstance(x, dict)}
            except (llm.LLMError, ValueError, KeyError, TypeError):
                got = {}
            for n, t in enumerate(chunk):
                if ok(t, got.get(n, ""), lang):
                    done[t] = got[n]
                else:
                    nxt.append(t)
        todo = nxt
    for t in todo:
        print(f"  ! {lang}: could not translate: {t[:70]}", flush=True)
    return done


def ui_strings() -> list[str]:
    found: list[str] = []
    for f in sorted([*WEB_SRC.rglob("*.tsx"), *WEB_SRC.rglob("*.ts")]):
        for m in re.finditer(r'\btx\(\s*[\w.?]+\s*,\s*"((?:[^"\\]|\\.)*)"', f.read_text()):
            s = m.group(1).encode().decode("unicode_escape") if "\\" in m.group(1) else m.group(1)
            if s not in found:
                found.append(s)
    return found


async def build(path: Path, texts: list[str], kind: str, redo: bool) -> None:
    data: dict[str, dict[str, str]] = {} if redo or not path.exists() else json.loads(path.read_text())
    for lang in TARGETS:
        have = data.setdefault(lang, {})
        for k in [k for k in have if k not in texts or not ok(k, have[k], lang)]:
            del have[k]                                         # no longer in the code, or fails today's checks
        missing = [t for t in texts if t not in have]
        if not missing:
            continue
        print(f"{path.name} · {lang}: translating {len(missing)}", flush=True)
        have.update(await translate(missing, lang, kind))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))
    gaps = {l: sum(1 for t in texts if t not in data.get(l, {})) for l in TARGETS}
    print(f"{path.name}: {len(texts)} strings · missing {gaps}")


async def main() -> None:
    redo = "--redo" in sys.argv
    only = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), None)
    if only in (None, "lines"):
        await build(LINES_OUT, lines.all_templates(), "speech", redo)
    if only in (None, "ui"):
        await build(UI_OUT, ui_strings(), "ui", redo)


if __name__ == "__main__":
    asyncio.run(main())
