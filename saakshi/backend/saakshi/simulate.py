"""Demo world + red team.

seed_demo()   builds a believable neighbourhood: a domestic worker with four
              employers, a construction crew under a contractor (one worker a few
              days short of the 90-day welfare-board threshold), and a fraud ring.

red_team()    Kavach's attacker idea turned inward: generate a population of honest
              workers plus fraudsters (collusion rings with mutual vouching,
              near-sequential SIMs, a shared device, inflated wages), run every
              confirmation call through the real call engine and classifier, then
              measure how many frauds the trust engine catches and how many honest
              workers it wrongly flags.
"""

from __future__ import annotations

import asyncio
import random
from datetime import date, timedelta

from . import calls, gnani, store
from .bus import bus
from .numbers import MONTH_NAMES_EN
from .trust import recompute

RUN: dict = {"status": "idle"}


def _month(today: date, back: int) -> dict:
    y, m = today.year, today.month - back
    while m <= 0:
        y, m = y - 1, m + 12
    s = date(y, m, 1)
    e = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return {"start": s.isoformat(), "end": min(e, today).isoformat(), "label": f"{MONTH_NAMES_EN[m]} {y}"}


def _week(today: date, back: int) -> dict:
    start = today - timedelta(days=today.weekday() + 7 * back)
    end = start + timedelta(days=5)
    return {"start": start.isoformat(), "end": min(end, today).isoformat(), "label": f"week of {start.strftime('%-d %b')}"}


def _entry(w, emp, period, amount, *, status="verified", days=None, rate=None, pay_type="monthly", role=None,
           paid_mode="cash", clip=None, says=None):
    x = store.add_entry(w["id"], emp["id"], role=role or w["role"], pay_type=pay_type, period=period, days=days,
                        rate=rate, amount=amount, paid=amount, paid_mode=paid_mode, do_not_contact=False,
                        source_audio=clip, transcript=None)
    if status != "pending":
        store.update_entry(x["id"], status=status, attested_by="employer" if status in ("verified", "corrected") else None,
                           employer_says=says or ({"amount": amount, "days": days} if status == "verified" else None))
    return x


async def seed_demo(with_voice: bool = True) -> dict:
    from . import journal
    # only demo data is replaced; real users' records are never touched
    demo_ids = {w["id"] for w in store.list_workers() if w.get("sim_group")}
    store.reset_demo()
    for wid in demo_ids:
        journal.SESSIONS.pop(wid, None)
    calls.LIVE.clear()
    today = date.today()

    # --- Sunita: domestic worker in four homes -------------------------------------------
    from . import accounts, payments
    demo_pin = accounts.hash_pin("2468")
    sunita = store.create_worker("Sunita Devi", "9810011223", "hi-IN", "domestic", "New Delhi", "Delhi", voice="Urmila",
                                 sim_group="demo", upi_id="sunita.devi@okaxis", pin_hash=demo_pin)
    clip = None
    if with_voice:
        res = await gnani.timbre_speak("नमस्ते, मैं सुनीता हूँ। मैंने अक्टूबर में आपके घर सफ़ाई का काम किया था, "
                                       "इसलिए यह रिकॉर्ड बनाया है।", voice="Urmila", language="hi-IN")
        p = store.settings.audio_dir / "seed"
        p.mkdir(parents=True, exist_ok=True)
        (p / "sunita.wav").write_bytes(res.audio)
        clip = "/audio/seed/sunita.wav"
    mehta = store.upsert_employer("9811234567", "Mehta ji", persona="honest", voice="Vikrant", language="hi-IN", sim_group="demo")
    kapoor = store.upsert_employer("9873456120", "Kapoor madam (Kothi 12)", persona="corrects", voice="Shweta", language="hi-IN", sim_group="demo")
    sharma = store.upsert_employer("9958812345", "Sharma ji", persona="suspicious", voice="Omkar", language="hi-IN", sim_group="demo")
    iyer = store.upsert_employer("9845011876", "Dr. Iyer", persona="english", voice="Kartik", language="en-IN", sim_group="demo")
    for back in range(6, 0, -1):
        _entry(sunita, mehta, _month(today, back), 3000, clip=clip)
        _entry(sunita, kapoor, _month(today, back), 2500, clip=clip)
    # Dr. Iyer pays by UPI: he reports each payment's reference and Sunita's bank SMS shows the same one
    for back in range(3, 0, -1):
        x = _entry(sunita, iyer, _month(today, back), 4000, paid_mode="upi", clip=clip)
        utr = f"6{today.year % 100}{back:02d}41807{back}3"[:12].ljust(12, "7")
        paid_on = date.fromisoformat(x["period_end"])
        store.update_entry(x["id"], employer_payment={"utr": utr, "amount": 4000, "at": paid_on.isoformat()})
        sms = (f"Rs.4,000.00 credited to a/c XX4411 on {paid_on.strftime('%d-%b-%y')} by IYER R via UPI. "
               f"UPI Ref No {utr}. -Bank")
        from .passport import parse_upi_sms
        store.add_evidence(sunita["id"], "upi_sms", sms, parse_upi_sms(sms, today), x["id"])
    payments.reconcile(sunita["id"])
    # waiting for live confirmation calls in the demo
    sh = _entry(sunita, sharma, _month(today, 1), 3500, status="pending", clip=clip)
    kp = _entry(sunita, kapoor, _month(today, 0), 2500, status="pending", clip=clip)
    calls.queue_call(sharma["id"], [sh["id"]])
    calls.queue_call(kapoor["id"], [kp["id"]])
    store.create_link(sunita["id"], sharma["id"], [sh["id"]])
    store.create_link(sunita["id"], kapoor["id"], [kp["id"]])

    # --- Construction crew under a contractor -----------------------------------------------
    bablu = store.upsert_employer("9718800441", "Bablu Thekedar", kind="contractor", persona="contractor",
                                  voice="Jatin", language="hi-IN", sim_group="demo")
    crew = [
        store.create_worker("Raju Prasad", "9650012001", "hi-IN", "construction", "Gurugram", "Haryana", voice="Farhan",
                            sim_group="demo", pin_hash=demo_pin),
        store.create_worker("Sohan Lal", "9650013002", "hi-IN", "construction", "Gurugram", "Haryana", sim_group="demo",
                            pin_hash=demo_pin),
        store.create_worker("Meena Kumari", "9650014003", "hi-IN", "construction", "Gurugram", "Haryana",
                            sim_group="demo", pin_hash=demo_pin),
    ]
    for back in range(15, 1, -1):          # 14 past weeks, 6 days each at ₹700/day
        for w in crew:
            _entry(w, bablu, _week(today, back), 4200, days=6, rate=700, pay_type="daily")
    # Raju: 14 weeks × 6 = 84 verified days — this week's 6 days will push him past 90 on a live call
    this_week = [_entry(w, bablu, _week(today, 1), 4200, days=6, rate=700, pay_type="daily", status="pending")
                 for w in crew]
    calls.queue_call(bablu["id"], [x["id"] for x in this_week])     # one call confirms the whole crew

    # --- A collusion ring --------------------------------------------------------------------
    pinky = store.create_worker("Pinky Kumari", "9876500101", "hi-IN", "domestic", "Noida", "Uttar Pradesh", device="dev-ring-1", sim_group="demo")
    monu = store.create_worker("Monu Yadav", "9876500102", "hi-IN", "driver", "Noida", "Uttar Pradesh", sim_group="demo")
    e_monu = store.upsert_employer(monu["phone"], "Monu Yadav", persona="colluder", voice="Jatin", sim_group="demo")
    e_pinky = store.upsert_employer(pinky["phone"], "Pinky Kumari", persona="colluder", voice="Gauri", sim_group="demo")
    rinku = store.upsert_employer("9876500117", "Rinku Sharma", persona="colluder", voice="Kartik", device="dev-ring-1", sim_group="demo")
    for back in range(4, 0, -1):
        _entry(pinky, e_monu, _month(today, back), 38000)       # a maid "earning" ₹38k from a driver
        _entry(monu, e_pinky, _month(today, back), 42000)
        _entry(pinky, rinku, _month(today, back), 25000)

    store.log("demo.seeded", "Demo neighbourhood created: Sunita (4 homes), Bablu's crew, and one fraud ring")
    recompute()
    await bus.emit("world.changed")
    return {"workers": len(store.list_workers()), "employers": len(store.list_employers()), "entries": len(store.all_entries())}


# ---- red team ----------------------------------------------------------------------------
FIRST = ["Asha", "Rekha", "Geeta", "Lakshmi", "Sarita", "Rani", "Babita", "Kavita", "Ramesh", "Suresh", "Mukesh", "Dinesh",
         "Anil", "Pooja", "Meera", "Savita", "Raju", "Shankar", "Pappu", "Kiran"]
LAST = ["Devi", "Kumari", "Yadav", "Paswan", "Mandal", "Singh", "Prasad", "Sahu", "Rao", "Gowda"]
ROLES = [("domestic", 3000), ("cook", 5000), ("driver", 15000), ("security", 12000), ("tailor", 9000)]

SCRIPT = {
    "honest": {"opening": "haan boliye", "claim": "haan haan, sahi hai, woh hamare yahan kaam karti hai"},
    "colluder": {"opening": "haan haan bilkul, sab sahi hai", "claim": "haan ekdum sahi, sab sahi hai"},
    "corrects": {"opening": "haan boliye", "claim": "nahi, itne nahi, {fix} rupaye mahina dete hain",
                 "correction": "haan, yeh sahi hai"},
    "denies": {"opening": "haan kaun?", "claim": "main kisi {worker} ko nahi jaanta", "deny_check": "nahi jaanta, galat number hai"},
    "busy": {"opening": "abhi drive kar raha hoon, kal shaam ko call karna"},
}


def _num(rng: random.Random) -> str:
    return f"{rng.choice('6789')}{rng.randint(10**8, 10**9 - 1)}"


async def red_team(n_honest: int = 10, n_rings: int = 2, n_inflators: int = 2, seed: int = 11) -> dict:
    rng = random.Random(seed)
    today = date.today()
    RUN.clear()
    RUN.update({"status": "running", "progress": 0, "total": 0, "log": []})
    await bus.emit("redteam.started")
    truth: dict[str, bool] = {}            # entry_id -> is fraud
    jobs: list[tuple[str, str]] = []       # (call_id, persona)

    def new_worker(role):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        return store.create_worker(name, _num(rng), "hi-IN", role, "Delhi NCR", "Delhi", sim_group="rt")

    # honest workers with 1-3 real employers
    for _ in range(n_honest):
        role, base = rng.choice(ROLES)
        w = new_worker(role)
        for _ in range(rng.randint(1, 3)):
            persona = rng.choices(["honest", "corrects", "denies", "busy"], [0.7, 0.15, 0.05, 0.1])[0]
            emp = store.upsert_employer(_num(rng), f"{rng.choice(['Mr.', 'Mrs.', 'Dr.'])} {rng.choice(LAST)}",
                                        persona=persona, sim_group="rt")
            amt = round(base * rng.uniform(0.7, 1.3) / 100) * 100
            ids = []
            for back in range(3, 0, -1):
                x = _entry(w, emp, _month(today, back), amt, status="pending")
                truth[x["id"]] = False
                ids.append(x["id"])
            jobs.append((calls.queue_call(emp["id"], ids, mode="auto")["id"], persona))

    # collusion rings: 3 people vouching for each other, numbers bought together, inflated wages
    for r in range(n_rings):
        base_num = int(_num(rng)[:8] + "00")
        members = []
        for i in range(3):
            role, base = rng.choice(ROLES)
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            members.append(store.create_worker(name, str(base_num + i * 3), "hi-IN", role, "Delhi NCR", "Delhi",
                                               device=f"ring-{r}" if i == 0 else None, sim_group=f"ring{r}"))
        for i, w in enumerate(members):
            boss = members[(i + 1) % 3]
            emp = store.upsert_employer(boss["phone"], boss["name"], persona="colluder", sim_group=f"ring{r}")
            ids = []
            for back in range(3, 0, -1):
                x = _entry(w, emp, _month(today, back), rng.choice([28000, 35000, 40000]), status="pending")
                truth[x["id"]] = True
                ids.append(x["id"])
            jobs.append((calls.queue_call(emp["id"], ids, mode="auto")["id"], "colluder"))

    # inflators: a real employer, but the worker claims a wildly high wage and a friend confirms
    for _ in range(n_inflators):
        w = new_worker("domestic")
        emp = store.upsert_employer(_num(rng), f"Mrs. {rng.choice(LAST)}", persona="colluder", sim_group="rt")
        ids = []
        for back in range(3, 0, -1):
            x = _entry(w, emp, _month(today, back), rng.choice([45000, 60000]), status="pending")
            truth[x["id"]] = True
            ids.append(x["id"])
        jobs.append((calls.queue_call(emp["id"], ids, mode="auto")["id"], "colluder"))

    RUN["total"] = len(jobs)
    sem = asyncio.Semaphore(4)

    async def run(call_id: str, persona: str):
        async with sem:
            outcome = await scripted_call(call_id, persona)
            RUN["progress"] += 1
            RUN["log"].append({"call_id": call_id, "persona": persona, "outcome": outcome})
            await bus.emit("redteam.progress", done=RUN["progress"], total=RUN["total"])

    await asyncio.gather(*(run(c, p) for c, p in jobs))
    recompute()

    import json as _json
    # "flagged" = the trust engine raised a fraud or wage-outlier signal on the record
    flagged = {x["id"]: any(r.get("kind") in ("fraud", "outlier") for r in _json.loads(x["reasons"] or "[]"))
               for x in store.all_entries() if x["id"] in truth}
    tp = sum(1 for k, v in truth.items() if v and flagged.get(k))
    fp = sum(1 for k, v in truth.items() if not v and flagged.get(k))
    fn = sum(1 for k, v in truth.items() if v and not flagged.get(k))
    honest_disputed = sum(1 for k, v in truth.items()
                          if not v and store.get_entry(k)["status"] in ("disputed", "pending", "unconfirmed"))
    RUN.update({
        "status": "done",
        "entries": len(truth), "fraud_entries": sum(truth.values()),
        "caught": tp, "missed": fn, "false_alarms": fp,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "honest_unresolved": honest_disputed,
    })
    store.log("redteam.done", f"Red team: caught {tp}/{tp + fn} fraudulent records, {fp} false alarms")
    await bus.emit("redteam.done", **{k: v for k, v in RUN.items() if k != "log"})
    await bus.emit("world.changed")
    return RUN


async def scripted_call(call_id: str, persona: str) -> str:
    """Run a call through the real engine and classifier, with scripted employer lines (no audio)."""
    cs = calls._session(call_id)
    cs.voice = False
    if persona == "noanswer":
        await calls.no_answer(call_id)
        return "no_answer"
    await calls.answer(call_id)
    script = SCRIPT.get(persona, SCRIPT["honest"])
    worker = cs.worker_names[0]
    fix = round(cs.entries[0]["amount"] * 0.85 / 100) * 100
    for _ in range(5):
        line = script.get(cs.stage) or script.get("claim") or "haan"
        line = line.format(worker=worker, fix=fix)
        turn = await calls.employer_said(call_id, line)
        if turn.get("done"):
            break
    return cs.outcome or "unclear"
