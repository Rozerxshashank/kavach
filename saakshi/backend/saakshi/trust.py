"""Trust engine: how much should a lender believe each record, and why.

Every entry gets a confidence (0-1) built from transparent, explainable signals.
Nothing here is a black box: each adjustment carries a plain-language reason that
the worker, the lender and the judge can all read.

Signals
  + employer confirmed on a call (or a household member did, weighted lower)
  + employer corrected it (we use their number, which is a strong honesty signal)
  + a UPI credit SMS matches the amount and month
  - mutual vouching: A says B employs her, B says A employs him
  - employer's number is near-sequential to the worker's (SIMs bought together)
  - employer and worker used the same device
  - one household "employer" vouching for an unusual number of workers
  - wage far outside the typical band for the role
  - sudden income jump versus the worker's own history
"""

from __future__ import annotations

import json
from collections import defaultdict

from . import store

BASE = {
    "verified": (0.88, "Employer confirmed on a recorded call"),
    "corrected": (0.84, "Employer confirmed with their own figures"),
    "self_declared": (0.35, "Worker's own statement; employer not contacted at worker's request"),
    "pending": (0.3, "Waiting for employer confirmation"),
    "calling": (0.3, "Confirmation call in progress"),
    "unconfirmed": (0.25, "Employer could not be reached or declined to answer"),
    "disputed": (0.05, "Employer did not confirm this"),
    "withdrawn": (0.0, "Withdrawn by the worker"),
}

# Indicative monthly-equivalent bands (₹) used only to flag outliers, never to reject.
WAGE_BANDS = {
    "domestic": (800, 15000), "cook": (1500, 20000), "nanny": (4000, 25000), "driver": (8000, 35000),
    "construction": (300, 1500), "painter": (400, 1500), "plumber": (400, 2000), "electrician": (400, 2000),
    "tailor": (3000, 30000), "security": (7000, 25000), "delivery": (8000, 40000), "other": (500, 50000),
}
DAILY_ROLES = {"construction", "painter", "plumber", "electrician"}
HOUSEHOLD_MAX_WORKERS = 5


LINK_WHY = {"link_voice": "Employer confirmed by voice on the confirmation link (recording kept)",
            "link_tap": "Employer confirmed on the confirmation link",
            "link_form": "Employer confirmed on the link with their own figures"}


def _r(tpl: str, impact: float, kind: str, **v) -> dict:
    """A reason in English, plus its template and values so it can be shown in the worker's language."""
    return {"text": tpl.format(**v) if v else tpl, "tpl": tpl, "vars": v, "impact": impact, "kind": kind}


def _phone_num(p: str) -> int:
    return int(p[-10:]) if p and p[-10:].isdigit() else 0


def _monthly_equiv(e: dict) -> float:
    amt = _final_amount(e)
    if e["pay_type"] == "daily":
        return (amt / e["days"]) if e.get("days") else amt
    from datetime import date
    s, t = date.fromisoformat(e["period_start"]), date.fromisoformat(e["period_end"])
    months = max(1.0, ((t - s).days + 1) / 30.4)
    return amt / months


def _final_amount(e: dict) -> float:
    says = e.get("employer_says")
    if says:
        try:
            d = json.loads(says) if isinstance(says, str) else says
            if d.get("amount"):
                return float(d["amount"])
        except (ValueError, TypeError):
            pass
    return float(e["amount"] or 0)


def recompute() -> dict:
    """Score every entry and return ring clusters for the trust graph."""
    workers = {w["id"]: w for w in store.list_workers()}
    employers = {e["id"]: e for e in store.list_employers()}
    entries = store.all_entries()
    worker_by_phone = {w["phone"]: w for w in workers.values()}

    vouches = defaultdict(set)              # employer_id -> worker_ids it confirmed
    for e in entries:
        if e["status"] in ("verified", "corrected"):
            vouches[e["employer_id"]].add(e["worker_id"])

    by_worker = defaultdict(list)
    for e in entries:
        by_worker[e["worker_id"]].append(e)

    # who each worker names as employer, by phone: used to find vouching loops (A→B→C→A)
    names_as_employer: dict[str, set[str]] = defaultdict(set)   # worker phone -> employer phones
    for e in entries:
        w0, emp0 = workers.get(e["worker_id"]), employers.get(e["employer_id"])
        if w0 and emp0:
            names_as_employer[w0["phone"]].add(emp0["phone"])

    def loop_back(start: str, first: str) -> int:
        """Length of a vouching loop that returns to `start`, or 0."""
        frontier, seen = {first}, {first}
        for depth in range(2, 5):
            nxt = set()
            for ph in frontier:
                for boss in names_as_employer.get(ph, ()):
                    if boss == start:
                        return depth
                    if boss not in seen:
                        seen.add(boss)
                        nxt.add(boss)
            frontier = nxt
        return 0

    # how many distinct months each worker-employer pair has employer-confirmed records for
    months_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    for e in entries:
        if e["status"] in ("verified", "corrected"):
            months_by_pair[(e["worker_id"], e["employer_id"])].add(e["period_start"][:7])
    tenure_months = {k: len(v) for k, v in months_by_pair.items()}

    suspicious_edges: list[tuple[str, str]] = []
    for e in entries:
        w = workers.get(e["worker_id"])
        emp = employers.get(e["employer_id"])
        if not w or not emp:
            continue
        conf, why = BASE.get(e["status"], (0.3, e["status"]))
        via = e.get("attested_via") or ""
        if e["status"] in ("verified", "corrected") and via.startswith("link"):
            why = LINK_WHY.get(via, why)
        reasons = [_r(why, round(conf, 2), "base")]
        flagged = False

        if (e.get("attested_by") or "").startswith("household:"):
            conf -= 0.12
            reasons.append(_r("Confirmed by a household member ({who}), not the employer", -0.12, "info",
                              who=e["attested_by"].split(":", 1)[1]))

        # vouching loops: the employer is also a worker, and following "who employs whom" leads back here
        emp_as_worker = worker_by_phone.get(emp["phone"])
        if emp_as_worker:
            loop = loop_back(w["phone"], emp["phone"])
            if loop:
                conf -= 0.5
                flagged = True
                reasons.append(_r("Mutual vouching: this employer is a worker who lists this worker as their employer", -0.5, "fraud")
                               if loop == 2 else
                               _r("Circular vouching: a loop of {n} people who all claim to employ each other", -0.5, "fraud", n=loop))
            else:
                conf -= 0.1
                reasons.append(_r("Employer is also registered as a worker", -0.1, "info"))

        if emp.get("kind") != "private":
            gap = abs(_phone_num(emp["phone"]) - _phone_num(w["phone"]))
            if 0 < gap <= 50:
                conf -= 0.3
                flagged = True
                reasons.append(_r("Employer's and worker's numbers are near-sequential (differ by {gap}), as if bought together",
                                  -0.3, "fraud", gap=gap))
            if emp.get("device") and emp["device"] == w.get("device"):
                conf -= 0.4
                flagged = True
                reasons.append(_r("Employer confirmation came from the worker's own device", -0.4, "fraud"))

        n_vouched = len(vouches.get(emp["id"], ()))
        if emp.get("kind") == "household" and n_vouched > HOUSEHOLD_MAX_WORKERS:
            conf -= 0.25
            flagged = True
            reasons.append(_r("A household vouching for {n} different workers is unusual", -0.25, "fraud", n=n_vouched))

        role = e.get("role") or w["role"]
        lo, hi = WAGE_BANDS.get(role, WAGE_BANDS["other"])
        val = _monthly_equiv(e)
        unit = "per day" if role in DAILY_ROLES and e["pay_type"] == "daily" else "per month"
        if val > hi * 2:
            conf -= 0.2
            reasons.append(_r("{amount} per month is far above the usual range for this work (up to about {top})" if unit == "per month"
                              else "{amount} per day is far above the usual range for this work (up to about {top})",
                              -0.2, "outlier", amount=f"₹{val:,.0f}", top=f"₹{hi:,}"))
        elif val and val < lo * 0.4:
            reasons.append(_r("{amount} is below the usual range for this work", 0, "info", amount=f"₹{val:,.0f}"))

        mine = sorted((x for x in by_worker[w["id"]] if x["id"] != e["id"] and x["status"] in ("verified", "corrected")),
                      key=lambda x: x["period_start"])
        if mine:
            typical = sorted(_monthly_equiv(x) for x in mine)[len(mine) // 2]
            if typical and val > typical * 3 and e["pay_type"] == mine[-1]["pay_type"]:
                conf -= 0.12
                reasons.append(_r("Sudden jump: about {x}× this worker's usual record", -0.12, "outlier", x=f"{val / typical:.1f}"))

        pay = e.get("payment_status") or "none"
        if pay == "verified":
            conf += 0.1
            reasons.append(_r("Payment proven from both sides: employer's UPI reference matches the worker's bank SMS (UTR ending {utr})",
                              0.1, "evidence", utr=(e.get("payment_ref") or "")[-4:]))
        elif pay == "matched":
            conf += 0.06
            reasons.append(_r("Worker's bank SMS shows a matching payment from someone with the employer's name", 0.06, "evidence"))
        elif pay == "claimed":
            reasons.append(_r("Payment reported by one side only; waiting for the other side", 0, "info"))
        elif [x for x in store.worker_evidence(w["id"]) if x.get("entry_id") == e["id"]]:
            conf += 0.04
            reasons.append(_r("A UPI credit of this amount was received (payer not identified)", 0.04, "evidence"))

        if e.get("attested_via") == "link_tap":
            conf -= 0.06
            reasons.append(_r("Confirmed with a tap on the link, without a spoken confirmation", -0.06, "info"))

        conf = round(max(0.0, min(0.99, conf)), 2)
        level = evidence_level(e, flagged, tenure_months.get((w["id"], emp["id"]), 0))
        if flagged:
            # an "employer" who is also a registered worker is the same person: one node
            other = worker_by_phone.get(emp["phone"])
            suspicious_edges.append((w["id"], other["id"] if other else emp["id"]))
        store.update_entry(e["id"], confidence=conf, reasons=reasons, level=level)

    return {"rings": _rings(suspicious_edges)}


def _rings(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Connected groups of suspicious worker↔employer links."""
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, rings = set(), []
    for node in adj:
        if node in seen:
            continue
        stack, comp = [node], []
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.append(n)
            stack.extend(adj[n] - seen)
        rings.append(sorted(comp))
    return rings


def graph() -> dict:
    """Nodes and edges for the trust-graph view."""
    rings = recompute()["rings"]
    ring_of = {n: i for i, r in enumerate(rings) for n in r}
    nodes, edges = [], []
    for w in store.list_workers():
        nodes.append({"id": w["id"], "label": w["name"], "type": "worker", "role": w["role"], "ring": ring_of.get(w["id"])})
    worker_by_phone = {w["phone"]: w for w in store.list_workers()}
    alias: dict[str, str] = {}            # employer id -> worker id when they are the same person
    for e in store.list_employers():
        if e.get("kind") == "private":
            continue
        if e["phone"] in worker_by_phone:
            alias[e["id"]] = worker_by_phone[e["phone"]]["id"]
            continue
        nodes.append({"id": e["id"], "label": e["name"], "type": "employer", "kind": e["kind"], "ring": ring_of.get(e["id"])})
    for n in nodes:
        if n["type"] == "worker" and n["id"] in alias.values():
            n["also_employer"] = True
    agg: dict[tuple[str, str], dict] = {}
    for x in store.all_entries():
        tgt = alias.get(x["employer_id"], x["employer_id"])
        k = (x["worker_id"], tgt)
        a = agg.setdefault(k, {"source": x["worker_id"], "target": tgt, "count": 0, "status": x["status"],
                               "confidence": x["confidence"] or 0})
        a["count"] += 1
        a["confidence"] = min(a["confidence"], x["confidence"] or 0)
        if x["status"] == "disputed":
            a["status"] = "disputed"
    edges = list(agg.values())
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["target"] in node_ids]
    return {"nodes": nodes, "edges": edges, "rings": rings}


LEVELS = {
    0: ("Unverified", "Worker's statement, or a record with a fraud signal"),
    1: ("Employer confirmed", "The employer confirmed it on a recorded call or by voice on a link"),
    2: ("Payment proven", "Employer confirmed, and the payment is backed by UPI evidence"),
    3: ("Established", "Payment proven, and the same employer has confirmed 3 or more months"),
}


def evidence_level(e: dict, flagged: bool, tenure_months: int) -> int:
    """How strong is this record? A lender or board decides which level it needs."""
    if flagged or e["status"] not in ("verified", "corrected"):
        return 0
    level = 1
    if (e.get("payment_status") or "none") in ("verified", "matched"):
        level = 2
        if tenure_months >= 3:
            level = 3
    return level


def _register_templates() -> None:
    import re as _re
    from . import lines
    src = open(__file__, encoding="utf-8").read()
    found = _re.findall(r'_r\(\s*"((?:[^"\\]|\\.)*)"', src)
    found += [r for _, r in BASE.values()] + list(LINK_WHY.values())
    found += ["{amount} per day is far above the usual range for this work (up to about {top})"]
    lines.EXTRA.extend(t for t in found if t not in lines.EXTRA)


_register_templates()
