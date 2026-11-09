"""Offline tests: trust signals, passport integrity, evidence parsing, call yes/no (no network)."""

import json
import os
import tempfile
from datetime import date

os.environ.setdefault("SAAKSHI_DATA_DIR", tempfile.mkdtemp())

import asyncio  # noqa: E402

import pytest  # noqa: E402

from saakshi import passport, simulate, store, trust  # noqa: E402
from saakshi.calls import quick_yes_no  # noqa: E402
from saakshi.numbers import phone_digits  # noqa: E402


@pytest.fixture(scope="module")
def world():
    asyncio.run(simulate.seed_demo(with_voice=False))
    return {w["name"].split()[0]: w for w in store.list_workers()}


def reasons(entry):
    return [r["kind"] for r in json.loads(entry["reasons"] or "[]")]


def test_phone_numbers_said_any_way():
    assert phone_digits("nau aath ek ek, paanch paanch chhah, saat saat aath") == "9811556778"
    assert phone_digits("nine eight double one five five six seven seven eight") == "9811556778"
    assert store.normalize_phone("+91 98111-22334") == "+919811122334"
    assert store.normalize_phone("098111 22334") == "+919811122334"
    assert store.normalize_phone("12345") is None


@pytest.mark.parametrize("text,expected", [
    ("haan", "confirm"), ("ji haan, sahi hai", "confirm"), ("हाँ जी", "confirm"), ("nahi", "deny"),
    ("haan par 3000 the", None), ("nahi jaanta main", None), ("haan boliye", None),
])
def test_quick_yes_no(text, expected):
    assert quick_yes_no(text) == expected


def test_honest_worker_is_trusted(world):
    p = passport.build(world["Sunita"]["id"])
    assert p["stats"]["fraud_flags"] == 0
    assert p["stats"]["months_verified"] >= 6
    assert p["stats"]["strength"] >= 70


def test_collusion_ring_is_flagged(world):
    for name in ("Pinky", "Monu"):
        entries = store.worker_entries(world[name]["id"])
        assert all("fraud" in reasons(e) for e in entries)
        assert all((e["confidence"] or 0) < 0.5 for e in entries)
    ring = trust.recompute()["rings"]
    assert any(world["Pinky"]["id"] in r and world["Monu"]["id"] in r for r in ring)


def test_mutual_vouching_reason_is_explained(world):
    texts = [r["text"] for e in store.worker_entries(world["Monu"]["id"]) for r in json.loads(e["reasons"])]
    assert any("Mutual vouching" in t for t in texts)


def test_bocw_counts_verified_construction_days(world):
    b = passport.build(world["Raju"]["id"])["bocw"]
    assert b["days"] == 84 and not b["eligible"] and b["required"] == 90


def test_hash_chain_and_signature(world):
    wid = world["Sunita"]["id"]
    p = passport.build(wid)
    assert p["chain"]["intact"] and passport.verify(p)
    tampered = json.loads(json.dumps(p))
    tampered["stats"]["avg_monthly_verified"] += 5000
    assert not passport.verify(tampered)


def test_editing_a_stored_amount_breaks_the_chain(world):
    wid = world["Sohan"]["id"]
    e = store.worker_entries(wid)[-1]
    store._exec("UPDATE entries SET amount=? WHERE id=?", (99999, e["id"]))
    assert not store.verify_chain(wid)


def test_scoped_share_hides_details(world):
    p = passport.build(world["Sunita"]["id"])
    band = passport.scoped(p, "income_band")
    assert "months" not in band and "employers" not in band and "income_band" in band["stats"]


def test_upi_sms_parse_and_match(world):
    wid = world["Sunita"]["id"]
    e = [x for x in store.worker_entries(wid) if x["employer_name"] == "Dr. Iyer"][0]
    end = date.fromisoformat(e["period_end"])
    sms = f"Rs.4,000.00 credited to a/c XX4411 on {end.strftime('%d-%b-%y')} by IYER R via UPI Ref 4512. -Bank"
    parsed = passport.parse_upi_sms(sms)
    assert parsed and parsed["amount"] == 4000 and parsed["date"] == end.isoformat()
    assert passport.match_evidence(wid, parsed) is not None
    assert passport.parse_upi_sms("Your OTP is 4412") is None


def test_wage_outlier_is_flagged():
    w = store.create_worker("Test Inflator", "9123400001", "hi-IN", "domestic", "X", "Y")
    emp = store.upsert_employer("9988700001", "Mrs. Test")
    x = store.add_entry(w["id"], emp["id"], role="domestic", pay_type="monthly",
                        period={"start": "2026-09-01", "end": "2026-09-30", "label": "September 2026"},
                        days=None, rate=None, amount=60000, paid=None, paid_mode="cash", do_not_contact=False,
                        source_audio=None, transcript=None)
    store.update_entry(x["id"], status="verified")
    trust.recompute()
    assert "outlier" in reasons(store.get_entry(x["id"]))
