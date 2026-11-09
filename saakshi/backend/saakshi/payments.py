"""Two-sided payment proof, at zero cost.

No payment gateway tells us a UPI transfer happened, so Saakshi proves it the way
an auditor would: from two independent sides.

  employer side  the 12-digit UPI reference (UTR) from their payment app
  worker side    her bank's credit SMS, forwarded or pasted

  verified  both sides show the same UTR (and the amounts agree)
  matched   no shared UTR, but the worker's credit SMS matches amount, timing,
            and the payer's name looks like the employer's
  claimed   only one side has reported anything
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

from . import store
from .trust import _final_amount

_HONORIFIC = {"ji", "jee", "mr", "mrs", "ms", "dr", "madam", "sir", "sahab", "saab", "bhai", "didi", "kothi", "the"}


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]{3,}", (name or "").lower()) if t not in _HONORIFIC}


def same_person(a: str | None, b: str | None) -> bool:
    return bool(_name_tokens(a or "") & _name_tokens(b or ""))


def _in_window(day: str | None, e: dict) -> bool:
    if not day:
        return False
    d = date.fromisoformat(day)
    return date.fromisoformat(e["period_start"]) - timedelta(days=5) <= d <= date.fromisoformat(e["period_end"]) + timedelta(days=25)


def _close(a: float, b: float) -> bool:
    return bool(a) and abs(a - b) / a <= 0.03


def reconcile(worker_id: str) -> None:
    """Re-derive every entry's payment status from what both sides have reported."""
    evidence = []
    for ev in store.worker_evidence(worker_id):
        p = json.loads(ev["parsed"] or "{}")
        if p.get("amount"):
            evidence.append({**p, "id": ev["id"]})
    for e in store.worker_entries(worker_id):
        emp_pay = json.loads(e["employer_payment"]) if e.get("employer_payment") else None
        amount = _final_amount(e)
        status, ref = "none", None
        if emp_pay and emp_pay.get("utr"):
            hit = next((x for x in evidence if x.get("utr") == emp_pay["utr"]), None)
            if hit and _close(float(emp_pay.get("amount") or amount), hit["amount"]):
                status, ref = "verified", emp_pay["utr"]
            else:
                status, ref = "claimed", emp_pay["utr"]
        if status != "verified":
            hit = next((x for x in evidence if _close(amount, x["amount"]) and _in_window(x.get("date"), e)
                        and same_person(x.get("from"), e["employer_name"])), None)
            if hit:
                status, ref = "matched", hit.get("utr") or ref
        if (e.get("payment_status") or "none") != status or e.get("payment_ref") != ref:
            store.update_entry(e["id"], payment_status=status, payment_ref=ref)


def employer_reports_payment(entry_id: str, utr: str, amount: float) -> dict:
    utr = re.sub(r"\D", "", utr or "")
    if len(utr) != 12:
        raise ValueError("A UPI reference (UTR) has 12 digits. You can find it in your payment app's receipt.")
    e = store.get_entry(entry_id)
    if not e:
        raise KeyError(entry_id)
    store.update_entry(entry_id, employer_payment={"utr": utr, "amount": amount, "at": store.now()})
    reconcile(e["worker_id"])
    return store.get_entry(entry_id)  # type: ignore[return-value]
