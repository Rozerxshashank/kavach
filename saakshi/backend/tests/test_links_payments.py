"""Accounts, confirmation links, two-sided payment proof and evidence levels (offline)."""

import asyncio

import pytest

from saakshi import accounts, links, passport, payments, simulate, store, trust
from saakshi.passport import parse_upi_sms


@pytest.fixture()
def world():
    asyncio.run(simulate.seed_demo(with_voice=False))
    import random
    w = store.create_worker("Test Cook", f"91{random.randint(10**7, 10**8 - 1)}", "hi-IN", "cook", "Pune", "MH",
                            upi_id="cook@okaxis", pin_hash=accounts.hash_pin("4826"))
    emp = store.upsert_employer(f"98{random.randint(10**7, 10**8 - 1)}", "Deshpande madam")
    x = store.add_entry(w["id"], emp["id"], role="cook", pay_type="monthly",
                        period={"start": "2026-10-01", "end": "2026-10-31", "label": "October 2026"},
                        days=None, rate=None, amount=5500, paid=None, paid_mode="upi", do_not_contact=False,
                        source_audio=None, transcript=None)
    link = store.create_link(w["id"], emp["id"], [x["id"]])
    return w, emp, x, link


def test_pin_and_tokens():
    h = accounts.hash_pin("4826")
    assert accounts.check_pin("4826", h) and not accounts.check_pin("4827", h)
    assert not accounts.valid_pin("1111") and not accounts.valid_pin("12") and accounts.valid_pin("4826")
    t = accounts.token_for("w_abc")
    assert accounts.worker_from_token(t) == "w_abc"
    assert accounts.worker_from_token("w_other." + t.split(".")[1]) is None
    assert accounts.valid_upi("asha.k@okicici") and not accounts.valid_upi("asha")


def test_utr_parsed_from_bank_sms():
    p = parse_upi_sms("Rs 5,500.00 credited to A/c XX9921 on 31-Oct-26 by DESHPANDE S. UPI Ref No 612944710083.")
    assert p["amount"] == 5500 and p["utr"] == "612944710083" and p["date"] == "2026-10-31"


def test_whatsapp_link_is_prefilled():
    url = links.whatsapp_url("+919988700111", "नमस्ते https://x/c/abc")
    assert url.startswith("https://wa.me/919988700111?text=") and "https%3A%2F%2Fx%2Fc%2Fabc" in url


def test_tap_confirmation_is_level_1_but_weaker(world):
    w, emp, x, link = world
    links.confirm_by_tap(link["token"])
    e = store.get_entry(x["id"])
    assert e["status"] == "verified" and e["attested_via"] == "link_tap" and e["level"] == 1
    assert any("without a spoken confirmation" in r["text"] for r in __import__("json").loads(e["reasons"]))


def test_correction_and_denial(world):
    w, emp, x, link = world
    with pytest.raises(ValueError):
        links.correct(link["token"], {x["id"]: {"amount": 0}})
    links.correct(link["token"], {x["id"]: {"amount": 5000}})
    e = store.get_entry(x["id"])
    assert e["status"] == "corrected" and '"amount": 5000' in e["employer_says"]
    link2 = store.create_link(w["id"], emp["id"], [x["id"]])
    links.deny(link2["token"])
    assert store.get_entry(x["id"])["status"] == "disputed" and store.get_entry(x["id"])["level"] == 0


def test_payment_needs_both_sides_for_level_2(world):
    w, emp, x, link = world
    links.confirm_by_tap(link["token"])
    with pytest.raises(ValueError):
        payments.employer_reports_payment(x["id"], "1234", 5500)
    payments.employer_reports_payment(x["id"], "6129 4471 0083", 5500)
    trust.recompute()
    e = store.get_entry(x["id"])
    assert e["payment_status"] == "claimed" and e["level"] == 1          # one side only

    sms = "Rs 5,500.00 credited to A/c XX9921 on 31-Oct-26 by DESHPANDE S. UPI Ref No 612944710083."
    store.add_evidence(w["id"], "upi_sms", sms, parse_upi_sms(sms), None)
    payments.reconcile(w["id"])
    trust.recompute()
    e = store.get_entry(x["id"])
    assert e["payment_status"] == "verified" and e["level"] == 2


def test_mismatched_utr_does_not_verify(world):
    w, emp, x, link = world
    links.confirm_by_tap(link["token"])
    payments.employer_reports_payment(x["id"], "612944710083", 5500)
    sms = "Rs 5,500.00 credited on 31-Oct-26 by SOMEONE ELSE. UPI Ref No 999999999999."
    store.add_evidence(w["id"], "upi_sms", sms, parse_upi_sms(sms), None)
    payments.reconcile(w["id"])
    assert store.get_entry(x["id"])["payment_status"] == "claimed"


def test_demo_world_levels():
    asyncio.run(simulate.seed_demo(with_voice=False))
    sunita = next(w for w in store.list_workers() if w["name"].startswith("Sunita"))
    levels = {e["employer_name"]: e["level"] for e in store.worker_entries(sunita["id"]) if e["status"] == "verified"}
    assert levels["Dr. Iyer"] == 3 and levels["Mehta ji"] == 1        # UPI-proven 3 months vs cash
    p = passport.build(sunita["id"])
    assert p["stats"]["months_l3"] == 3 and passport.verify(p)


def test_demo_reset_never_touches_real_users():
    real = store.create_worker("Real Person", "9123477001", "hi-IN", "cook", "Pune", "MH", pin_hash=accounts.hash_pin("4826"))
    emp = store.upsert_employer("9988711122", "Real Employer")
    x = store.add_entry(real["id"], emp["id"], role="cook", pay_type="monthly",
                        period={"start": "2026-10-01", "end": "2026-10-31", "label": "October 2026"},
                        days=None, rate=None, amount=4000, paid=None, paid_mode="cash", do_not_contact=False,
                        source_audio=None, transcript=None)
    asyncio.run(simulate.seed_demo(with_voice=False))
    asyncio.run(simulate.seed_demo(with_voice=False))          # twice: no duplicates, real data intact
    assert store.get_worker(real["id"]) and store.get_entry(x["id"]) and store.get_employer(emp["id"])
    assert sum(1 for w in store.list_workers() if w["name"] == "Sunita Devi") == 1


def test_withdraw_and_delete_account():
    from starlette.testclient import TestClient
    from saakshi.server import app
    import random
    c = TestClient(app)
    r = c.post("/api/auth/join", json={"name": "Del Test", "phone": f"97{random.randint(10**7, 10**8 - 1)}", "pin": "4826"}).json()
    wid, H = r["worker"]["id"], {"X-Worker-Token": r["token"]}
    emp = store.upsert_employer(f"96{random.randint(10**7, 10**8 - 1)}", "Someone")
    x = store.add_entry(wid, emp["id"], role="cook", pay_type="monthly",
                        period={"start": "2026-10-01", "end": "2026-10-31", "label": "October 2026"}, days=None, rate=None,
                        amount=4000, paid=None, paid_mode="cash", do_not_contact=False, source_audio=None, transcript=None)
    assert c.post(f"/api/workers/{wid}/entries/{x['id']}/withdraw", headers=H).status_code == 200
    assert store.get_entry(x["id"])["status"] == "withdrawn"
    assert passport.build(wid)["chain"]["length"] == 0 and store.verify_chain(wid)     # hidden, chain intact
    assert c.post(f"/api/workers/{wid}/delete", json={"pin": "0000"}, headers=H).status_code == 401
    assert c.post(f"/api/workers/{wid}/delete", json={"pin": "4826"}, headers=H).status_code == 200
    assert store.get_worker(wid) is None and store.get_entry(x["id"]) is None
