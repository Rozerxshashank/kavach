"""Access rules for a public deployment: real people's data stays private, demo data stays open."""

import dataclasses
import io
import struct
import time

import pytest
from starlette.testclient import TestClient

from saakshi import accounts, config, security, store

ADMIN = "operator-key-for-tests-0123"


@pytest.fixture()
def prod(monkeypatch):
    """The server as deployed: an operator key is set, so nobody else is an operator."""
    s = dataclasses.replace(config.settings, admin_key=ADMIN, env="production")
    monkeypatch.setattr(security, "settings", s)
    security.limiter.hits.clear()
    security._last_global.clear()
    from saakshi.server import app
    return TestClient(app)


def _people(tag: str):
    n = abs(hash(tag)) % 10_000
    real = store.create_worker(f"Real {tag}", f"91{n:04d}5001", "hi-IN", "cook", "Pune", "MH",
                               pin_hash=accounts.hash_pin("4826"))
    demo = store.create_worker(f"Demo {tag}", f"91{n:04d}5002", "hi-IN", "cook", "Pune", "MH", sim_group="demo")
    boss = store.upsert_employer(f"98{n:04d}5003", f"Boss {tag}")
    demo_boss = store.upsert_employer(f"98{n:04d}5004", f"Demo boss {tag}", sim_group="demo")
    period = {"start": "2026-10-01", "end": "2026-10-31", "label": "October"}
    e = store.add_entry(real["id"], boss["id"], role="cook", pay_type="monthly", period=period, days=None, rate=None,
                        amount=4000, paid=None, paid_mode=None, do_not_contact=False, source_audio=None, transcript=None)
    de = store.add_entry(demo["id"], demo_boss["id"], role="cook", pay_type="monthly", period=period, days=None,
                         rate=None, amount=3500, paid=None, paid_mode=None, do_not_contact=False, source_audio=None,
                         transcript=None)
    call = store.create_call(boss["id"], [e["id"]], "human")
    demo_call = store.create_call(demo_boss["id"], [de["id"]], "human")
    return real, demo, call, demo_call


def test_visitors_see_demo_workers_only(prod):
    real, demo, *_ = _people("list")
    ids = {w["id"] for w in prod.get("/api/workers").json()}
    assert demo["id"] in ids and real["id"] not in ids
    assert real["id"] in {w["id"] for w in prod.get("/api/workers", headers={"X-Admin-Key": ADMIN}).json()}
    assert all("pin_hash" not in w for w in prod.get("/api/workers").json())


def test_a_real_worker_needs_her_own_login(prod):
    real, demo, *_ = _people("login")
    assert prod.get(f"/api/workers/{real['id']}").status_code == 401
    assert prod.post(f"/api/demo/token/{real['id']}").status_code == 401           # no pass for real people
    assert prod.get(f"/api/workers/{real['id']}", headers={"X-Worker-Token": accounts.token_for(real["id"])}).status_code == 200
    other = accounts.token_for(demo["id"])
    assert prod.get(f"/api/workers/{real['id']}", headers={"X-Worker-Token": other}).status_code == 401
    t = prod.post(f"/api/demo/token/{demo['id']}").json()["token"]                  # demo workers: open to visitors
    assert prod.get(f"/api/workers/{demo['id']}", headers={"X-Worker-Token": t}).status_code == 200


def test_tokens_expire_and_die_with_a_pin_reset(prod):
    real, *_ = _people("token")
    assert accounts.worker_from_token(accounts.token_for(real["id"], days=-1)) is None
    forged = f"{real['id']}.{int(time.time()) + 999}.{'0' * 40}"
    assert accounts.worker_from_token(forged) is None
    t = accounts.token_for(real["id"])
    assert accounts.worker_from_token(t) == real["id"]
    r = prod.post(f"/api/admin/workers/{real['id']}/pin", json={"pin": "5937"}, headers={"X-Admin-Key": ADMIN})
    assert r.status_code == 200
    assert accounts.worker_from_token(t) is None                                    # old sessions logged out


def test_wrong_pins_lock_the_number(prod):
    real, *_ = _people("pin")
    for _ in range(accounts.MAX_TRIES):
        assert prod.post("/api/auth/login", json={"phone": real["phone"], "pin": "1357"}).status_code == 401
    r = prod.post("/api/auth/login", json={"phone": real["phone"], "pin": "4826"})  # even the right PIN waits
    assert r.status_code == 429


def test_login_is_rate_limited_per_visitor(prod):
    codes = [prod.post("/api/auth/login", json={"phone": f"90000{i:05d}", "pin": "1357"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429


def test_real_calls_and_their_events_are_private(prod):
    real, demo, call, demo_call = _people("calls")
    ids = {c["id"] for c in prod.get("/api/calls").json()}
    assert demo_call["id"] in ids and call["id"] not in ids
    assert prod.get(f"/api/calls/{call['id']}").status_code == 404
    assert prod.post(f"/api/calls/{call['id']}/ring?mode=human").status_code == 404
    assert prod.post(f"/api/calls/{demo_call['id']}/ring?mode=phone").status_code == 401   # real dialling: operators only
    store.log("test.private", "secret thing", worker_id=real["id"])
    store.log("test.public", "demo thing", worker_id=demo["id"])
    texts = {e["text"] for e in prod.get("/api/events").json()}
    assert "demo thing" in texts and "secret thing" not in texts
    v = security.Viewer(wid=real["id"])                                             # her own events on the live stream
    assert v.sees_event({"type": "call.ended", "worker_ids": [real["id"]]})
    assert not security.Viewer().sees_event({"type": "call.turn", "call_id": call["id"]})
    assert security.Viewer().sees_event({"type": "call.turn", "call_id": demo_call["id"]})
    assert security.from_ticket(security.ticket(False, real["id"])).wid == real["id"]
    assert security.from_ticket("1::9999999999:forged").admin is False


def test_trust_graph_hides_real_people(prod):
    real, demo, *_ = _people("graph")
    ids = {n["id"] for n in prod.get("/api/trust/graph").json()["nodes"]}
    assert real["id"] not in ids


def _wav(seconds: float) -> bytes:
    n = int(16000 * seconds)
    head = b"RIFF" + struct.pack("<I", 36 + 2 * n) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    return head + b"data" + struct.pack("<I", 2 * n) + b"\0\0" * n


def test_uploads_are_capped_and_must_be_wav(prod):
    real, *_ = _people("upload")
    h = {"X-Worker-Token": accounts.token_for(real["id"])}
    url = f"/api/workers/{real['id']}/journal"
    assert prod.post(url, files={"audio_file": ("a.wav", io.BytesIO(b"not audio" * 10), "audio/wav")}, headers=h).status_code == 400
    assert prod.post(url, files={"audio_file": ("a.wav", io.BytesIO(_wav(200)), "audio/wav")}, headers=h).status_code == 413


def test_share_links_can_only_be_revoked_by_their_owner(prod):
    real, demo, *_ = _people("share")
    s = store.create_share(real["id"], "full", None, "2099-01-01T00:00:00+00:00")
    assert prod.delete(f"/api/workers/{demo['id']}/shares/{s['token']}",
                       headers={"X-Worker-Token": accounts.token_for(demo["id"])}).status_code == 404
    assert prod.delete(f"/api/workers/{real['id']}/shares/{s['token']}",
                       headers={"X-Worker-Token": accounts.token_for(real["id"])}).status_code == 200


def test_security_headers(prod):
    r = prod.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"]
    for h in ("x-content-type-options", "x-frame-options", "referrer-policy", "strict-transport-security"):
        assert h in r.headers
    assert r.headers["cache-control"] == "no-store"


def test_production_refuses_unsafe_settings():
    bad = dataclasses.replace(config.settings, signing_key=config.DEV_SIGNING_KEY, admin_key="", public_base_url="")
    assert len(config.production_problems(bad)) >= 3
    good = dataclasses.replace(config.settings, signing_key="x" * 48, admin_key="y" * 24,
                               public_base_url="https://saakshi.example.org", gnani_api_key="g", groq_api_key="q")
    assert config.production_problems(good) == []
