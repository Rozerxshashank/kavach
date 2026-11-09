"""The Kaam Passport: a worker-owned, verifiable record of work and income.

* Monthly income, split into verified (employer-confirmed, trusted) and claimed.
* A signed summary: anyone with the QR link can check the signature and that the
  worker's hash-chained record hasn't been edited.
* Scoped sharing: a landlord sees an income band, a welfare board sees work days,
  a lender sees the full history. The worker can revoke any link.
* The construction welfare-board certificate (90 days of building work in the
  last 12 months, as the BOCW Act requires for registration).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import lines, store
from .config import settings
from .lines import money
from .numbers import MONTH_NAMES_EN, inr
from .trust import _final_amount

TRUSTED = 0.6
CONSTRUCTION_ROLES = {"construction", "painter", "plumber", "electrician"}


def _months_back(n: int, today: date) -> list[tuple[int, int]]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _spread(e: dict) -> dict[tuple[int, int], float]:
    """Spread an entry's amount across the months it covers, by days."""
    s, t = date.fromisoformat(e["period_start"]), date.fromisoformat(e["period_end"])
    total_days = (t - s).days + 1
    amt = _final_amount(e)
    out: dict[tuple[int, int], float] = defaultdict(float)
    d = s
    while d <= t:
        out[(d.year, d.month)] += amt / total_days
        d += timedelta(days=1)
    return out


def build(worker_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    w = store.get_worker(worker_id)
    if not w:
        raise KeyError(worker_id)
    entries = [e for e in store.worker_entries(worker_id) if e["status"] != "withdrawn"]
    months = _months_back(12, today)
    verified = defaultdict(float)
    claimed = defaultdict(float)
    by_level = {2: defaultdict(float), 3: defaultdict(float)}
    for e in entries:
        if e["status"] == "disputed":
            continue
        lvl = e.get("level") or 0
        for ym, v in _spread(e).items():
            claimed[ym] += v
            if lvl >= 1:
                verified[ym] += v
            for k in (2, 3):
                if lvl >= k:
                    by_level[k][ym] += v

    series = [{"month": f"{y}-{m:02d}", "label": f"{MONTH_NAMES_EN[m][:3]} {str(y)[2:]}",
               "verified": round(verified[(y, m)]), "claimed": round(claimed[(y, m)]),
               "l2": round(by_level[2][(y, m)]), "l3": round(by_level[3][(y, m)])} for y, m in months]
    active = [s for s in series if s["claimed"] > 0]
    verified_months = [s for s in series if s["verified"] > 0]
    total_claimed = sum(s["claimed"] for s in series)
    total_verified = sum(s["verified"] for s in series)
    avg_verified = (total_verified / len(verified_months)) if verified_months else 0

    employers = {}
    for e in entries:
        emp = employers.setdefault(e["employer_id"], {"name": e["employer_name"], "kind": e["employer_kind"], "since": e["period_start"],
                                                     "until": e["period_end"], "records": 0, "verified": 0})
        emp["since"] = min(emp["since"], e["period_start"])
        emp["until"] = max(emp["until"], e["period_end"])
        emp["records"] += 1
        emp["verified"] += 1 if (e.get("level") or 0) >= 1 else 0
    longest = max(((date.fromisoformat(v["until"]) - date.fromisoformat(v["since"])).days / 30.4 for v in employers.values()),
                  default=0)

    share = (total_verified / total_claimed) if total_claimed else 0
    coverage = min(1.0, len(verified_months) / 6)
    flags = sum(1 for e in entries for r in json.loads(e["reasons"] or "[]") if r.get("kind") == "fraud")
    strength = round(100 * (0.55 * share + 0.35 * coverage + 0.10 * min(1, len(employers) / 3)) * (0.5 if flags else 1))

    level_counts = {k: sum(1 for e in entries if (e.get("level") or 0) == k and e["status"] != "disputed") for k in range(4)}
    lvl_avg = {}
    for k in (2, 3):
        ms = [s_[f"l{k}"] for s_ in series if s_[f"l{k}"] > 0]
        lvl_avg[k] = round(sum(ms) / len(ms)) if ms else 0
    summary = {
        "worker": {"id": w["id"], "name": w["name"], "role": w["role"], "city": w["city"], "state": w["state"],
                   "phone_last4": w["phone"][-4:], "language": w["language"], "since": w["created_at"][:10]},
        "months": series,
        "stats": {
            "months_active": len(active), "months_verified": len(verified_months),
            "avg_monthly_verified": round(avg_verified), "income_band": income_band(avg_verified),
            "verified_share": round(share, 3), "total_verified_12m": round(total_verified),
            "total_claimed_12m": round(total_claimed), "employers": len(employers),
            "longest_tenure_months": round(longest, 1), "strength": strength, "fraud_flags": flags,
            "levels": level_counts,
            "months_l2": sum(1 for s_ in series if s_["l2"] > 0), "avg_monthly_l2": lvl_avg[2],
            "months_l3": sum(1 for s_ in series if s_["l3"] > 0), "avg_monthly_l3": lvl_avg[3],
        },
        "employers": sorted(employers.values(), key=lambda v: v["since"]),
        "bocw": bocw(entries, today),
        "chain": {"length": len(entries), "head": entries[0]["hash"] if entries else "genesis",
                  "intact": store.verify_chain(worker_id)},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    summary["signature"] = sign(summary)
    return summary


def income_band(monthly: float) -> str:
    if monthly <= 0:
        return "Not enough verified records yet"
    bands = [3000, 6000, 10000, 15000, 20000, 30000, 50000]
    lo = 0
    for b in bands:
        if monthly < b:
            return f"{inr(lo)}–{inr(b)} per month"
        lo = b
    return f"Above {inr(bands[-1])} per month"


def bocw(entries: list[dict], today: date) -> dict:
    """Verified days of building / construction work in the last 365 days."""
    since = today - timedelta(days=365)
    days, est = 0.0, False
    rows = []
    for e in entries:
        if (e["role"] or "") not in CONSTRUCTION_ROLES or (e.get("level") or 0) < 1:
            continue
        if date.fromisoformat(e["period_end"]) < since:
            continue
        says = json.loads(e["employer_says"]) if e.get("employer_says") else {}
        d = says.get("days") or e.get("days")
        if not d:
            span = (date.fromisoformat(e["period_end"]) - date.fromisoformat(e["period_start"])).days + 1
            d, est = round(span * 26 / 30.4), True
        days += float(d)
        rows.append({"employer": e["employer_name"], "period": e["period_label"], "days": d})
    return {"days": days, "required": 90, "eligible": days >= 90, "estimated": est, "rows": rows}


def _canonical(summary: dict) -> bytes:
    core = {k: summary[k] for k in ("worker", "stats", "chain")}
    core["months"] = [(m["month"], m["verified"], m.get("l2", 0), m.get("l3", 0)) for m in summary["months"]]
    return json.dumps(core, sort_keys=True, ensure_ascii=False).encode()


def sign(summary: dict) -> str:
    return hmac.new(settings.signing_key.encode(), _canonical(summary), hashlib.sha256).hexdigest()


def verify(summary: dict) -> bool:
    return hmac.compare_digest(summary.get("signature", ""), sign(summary))


def scoped(summary: dict, scope: str) -> dict:
    """What a given audience is allowed to see."""
    base = {"worker": {k: summary["worker"][k] for k in ("name", "role", "city", "state", "phone_last4")},
            "generated_at": summary["generated_at"], "chain": summary["chain"], "scope": scope,
            "signature_valid": verify(summary)}
    s = summary["stats"]
    if scope == "income_band":
        base["stats"] = {k: s[k] for k in ("income_band", "months_verified", "employers", "verified_share", "strength",
                                           "levels", "months_l2", "months_l3")}
    elif scope == "bocw":
        base["bocw"] = summary["bocw"]
        base["stats"] = {"months_verified": s["months_verified"]}
    else:
        base.update({"stats": s, "months": summary["months"], "employers": summary["employers"], "bocw": summary["bocw"]})
    return base


def spoken_summary(worker: dict, lang: str) -> str:
    p = build(worker["id"])
    s = p["stats"]
    if not p["chain"]["length"]:
        return ("अभी आपका कोई रिकॉर्ड नहीं है। बताइए, किसके यहाँ काम किया?" if lang == "hi-IN"
                else lines.tr(lang, SUMMARY_EMPTY))
    if lang == "hi-IN":
        avg = money(s["avg_monthly_verified"], lang) if s["avg_monthly_verified"] else "अभी तय नहीं"
        return (f"आपके {s['months_active']} महीनों का रिकॉर्ड है, जिनमें {s['months_verified']} महीने पक्के हो चुके हैं। "
                f"आप {s['employers']} लोगों के यहाँ काम करती हैं। पक्की औसत महीने की कमाई {avg} है। "
                f"आपका भरोसा स्कोर सौ में से {s['strength']} है।")
    avg = money(s["avg_monthly_verified"], lang) if s["avg_monthly_verified"] else lines.tr(lang, "not yet established")
    return lines.tr(lang, SUMMARY, months=s["months_active"], verified=s["months_verified"], employers=s["employers"],
                    avg=avg, score=s["strength"])


SUMMARY_EMPTY = "You don't have any records yet. Tell me where you worked."
SUMMARY = ("You have records for {months} months, {verified} of them verified, across {employers} employers. "
           "Your verified average monthly income is {avg}. Your trust score is {score} out of 100.")
lines.EXTRA += [SUMMARY_EMPTY, SUMMARY, "not yet established"]


# ---- UPI SMS evidence ----------------------------------------------------------------------
_UPI = re.compile(r"(?:rs\.?|inr|₹)\s?([\d,]+(?:\.\d{1,2})?)", re.I)
_DATE = re.compile(r"(\d{1,2})[-/ ]([a-z]{3}|\d{1,2})[-/ ]?(\d{2,4})?", re.I)
_MON = {m[:3].lower(): i for i, m in enumerate(MONTH_NAMES_EN) if m}


def parse_upi_sms(text: str, today: date | None = None) -> dict | None:
    today = today or date.today()
    if not re.search(r"credit|received|deposited|जमा", text, re.I):
        return None
    m = _UPI.search(text)
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    when = None
    d = _DATE.search(text[m.end():]) or _DATE.search(text)
    if d:
        day = int(d.group(1))
        mon = d.group(2)
        month = int(mon) if mon.isdigit() else _MON.get(mon.lower()[:3])
        year = int(d.group(3)) if d.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            if month:
                when = date(year, month, day)
        except ValueError:
            when = None
    frm = re.search(r"(?:from|by)\s+([A-Za-z][A-Za-z .]{1,40}?)(?:\s+(?:on|via|ref|upi|a/c)|[.,]|$)", text, re.I)
    utr = re.search(r"(?:utr|ref(?:erence)?\s*(?:no|number)?|upi\s*ref(?:\s*no)?|txn\s*id|upi)[\s:.#-]*(\d{12})", text, re.I)
    return {"amount": amount, "date": when.isoformat() if when else None, "from": frm.group(1).strip() if frm else None,
            "utr": utr.group(1) if utr else None}


def match_evidence(worker_id: str, parsed: dict) -> str | None:
    """Find the entry this payment most plausibly belongs to."""
    best, best_gap = None, 1e9
    for e in store.worker_entries(worker_id):
        amt = _final_amount(e)
        if not amt or abs(amt - parsed["amount"]) / amt > 0.03:
            continue
        if parsed.get("date"):
            pd = date.fromisoformat(parsed["date"])
            s, t = date.fromisoformat(e["period_start"]), date.fromisoformat(e["period_end"])
            if not (s - timedelta(days=5) <= pd <= t + timedelta(days=20)):
                continue
            gap = abs((pd - t).days)
        else:
            gap = 30
        if gap < best_gap:
            best, best_gap = e["id"], gap
    return best
