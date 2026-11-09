"""SQLite persistence.

Workers own records. Employers are identified by phone number, so the same
"Sharma ji" named by five different maids is one employer. Every work entry is
hash-chained per worker, so a passport can prove nothing was edited after the fact.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import settings

_lock = threading.RLock()
_db = sqlite3.connect(settings.db_path, check_same_thread=False)
_db.row_factory = sqlite3.Row
# one connection behind a lock (one process); WAL keeps the file consistent if the machine dies mid-write
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("PRAGMA synchronous=NORMAL")
_db.execute("PRAGMA busy_timeout=5000")

SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT UNIQUE NOT NULL, language TEXT NOT NULL,
  role TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL, voice TEXT, device TEXT,
  created_at TEXT NOT NULL, sim_group TEXT
);
CREATE TABLE IF NOT EXISTS employers (
  id TEXT PRIMARY KEY, phone TEXT UNIQUE NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'household',
  language TEXT, opted_out INTEGER NOT NULL DEFAULT 0, device TEXT, persona TEXT, voice TEXT,
  created_at TEXT NOT NULL, sim_group TEXT
);
CREATE TABLE IF NOT EXISTS entries (
  id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, employer_id TEXT NOT NULL, seq INTEGER NOT NULL,
  role TEXT, pay_type TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, period_label TEXT,
  days REAL, rate REAL, amount REAL NOT NULL, paid REAL, paid_mode TEXT,
  status TEXT NOT NULL, claimed TEXT NOT NULL, employer_says TEXT, attested_by TEXT,
  do_not_contact INTEGER NOT NULL DEFAULT 0, source_audio TEXT, transcript TEXT,
  confidence REAL, reasons TEXT, prev_hash TEXT, hash TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY, employer_id TEXT NOT NULL, entry_ids TEXT NOT NULL, status TEXT NOT NULL,
  outcome TEXT, mode TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT,
  transcript TEXT NOT NULL DEFAULT '[]', language TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, kind TEXT NOT NULL, raw TEXT NOT NULL, parsed TEXT,
  entry_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shares (
  token TEXT PRIMARY KEY, worker_id TEXT NOT NULL, scope TEXT NOT NULL, audience TEXT,
  expires_at TEXT, revoked INTEGER NOT NULL DEFAULT 0, views INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_versions (
  version INTEGER PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL, rules TEXT NOT NULL,
  gates TEXT NOT NULL, source_attack TEXT, note TEXT, active INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS login_fails (key TEXT PRIMARY KEY, n INTEGER NOT NULL, until REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, worker_id TEXT, employer_id TEXT,
  call_id TEXT, text TEXT NOT NULL
);
"""
MIGRATIONS = {
    "workers": {"upi_id": "TEXT", "pin_hash": "TEXT"},
    "entries": {"level": "INTEGER", "attested_via": "TEXT", "payment_status": "TEXT", "payment_ref": "TEXT",
                "employer_payment": "TEXT"},
}
LINKS = """
CREATE TABLE IF NOT EXISTS links (
  token TEXT PRIMARY KEY, worker_id TEXT NOT NULL, employer_id TEXT NOT NULL, entry_ids TEXT NOT NULL,
  status TEXT NOT NULL, opened_at TEXT, done_at TEXT, outcome TEXT, voice_clip TEXT, heard TEXT,
  created_at TEXT NOT NULL
);
"""
with _lock:
    _db.executescript(SCHEMA)
    _db.executescript(LINKS)
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in _db.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, typ in cols.items():
            if col not in have:
                _db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    _db.commit()


def backup(keep: int = 7) -> str | None:
    """A consistent copy of the database in data/backups (one per day, the last `keep` days kept)."""
    folder = settings.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    target = folder / f"saakshi-{day}.db"
    if target.exists():
        return None
    tmp = target.with_suffix(".part")
    dst = sqlite3.connect(tmp)
    with _lock:
        _db.backup(dst)
    dst.close()
    tmp.rename(target)
    for old in sorted(folder.glob("saakshi-*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    return str(target)


def healthy() -> bool:
    try:
        return _rows("SELECT 1 AS ok")[0]["ok"] == 1
    except sqlite3.Error:
        return False


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def normalize_phone(raw: str) -> str | None:
    """Any Indian mobile format -> +91XXXXXXXXXX. Returns None if it isn't one."""
    from .numbers import phone_digits
    digits = re.sub(r"\D", "", (raw or "").translate(str.maketrans("०१२३४५६७८९", "0123456789")))
    if len(digits) < 10:
        digits = phone_digits(raw)              # said in words: "nau aath ek ek …"
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    return None


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _db.execute(sql, args).fetchall()]


def _one(sql: str, args: tuple = ()) -> dict | None:
    rows = _rows(sql, args)
    return rows[0] if rows else None


def _exec(sql: str, args: tuple = ()) -> None:
    with _lock:
        _db.execute(sql, args)
        _db.commit()


# ---- events (audit log shown in the console) -----------------------------------------
# ---- Kavach sandbox worlds, and the call agent's hardening versions -------------------------------------------------
def delete_sandbox_world(worker_id: str, employer_id: str, call_id: str) -> None:
    """Remove one Kavach sandbox world. Only rows marked sim_group='kavach' can be touched."""
    with _lock:
        w = _db.execute("SELECT sim_group FROM workers WHERE id=?", (worker_id,)).fetchone()
        if w and w[0] == "kavach":
            for t in ("entries", "events"):
                _db.execute(f"DELETE FROM {t} WHERE worker_id=?", (worker_id,))
            _db.execute("DELETE FROM workers WHERE id=?", (worker_id,))
        _db.execute("DELETE FROM calls WHERE id=? AND employer_id IN (SELECT id FROM employers WHERE sim_group='kavach')",
                    (call_id,))
        _db.execute("DELETE FROM events WHERE call_id=?", (call_id,))
        _db.execute("DELETE FROM employers WHERE id=? AND sim_group='kavach'", (employer_id,))
        _db.commit()


def delete_all_sandbox_worlds() -> int:
    with _lock:
        wids = [r[0] for r in _db.execute("SELECT id FROM workers WHERE sim_group='kavach'").fetchall()]
        eids = [r[0] for r in _db.execute("SELECT id FROM employers WHERE sim_group='kavach'").fetchall()]
        for e in eids:
            for (cid,) in _db.execute("SELECT id FROM calls WHERE employer_id=?", (e,)).fetchall():
                _db.execute("DELETE FROM events WHERE call_id=?", (cid,))
            _db.execute("DELETE FROM calls WHERE employer_id=?", (e,))
        for w in wids:
            for t in ("entries", "events"):
                _db.execute(f"DELETE FROM {t} WHERE worker_id=?", (w,))
        _db.execute("DELETE FROM workers WHERE sim_group='kavach'")
        _db.execute("DELETE FROM employers WHERE sim_group='kavach'")
        _db.execute("DROP TABLE IF EXISTS attacks")           # the old in-app lab moved to Kavach
        _db.commit()
    return len(wids)


def agent_versions() -> list[dict]:
    out = _rows("SELECT * FROM agent_versions ORDER BY version")
    for v in out:
        v["rules"], v["gates"] = json.loads(v["rules"]), json.loads(v["gates"])
    return out


def add_agent_version(version: int, title: str, rules: list[str], gates: dict, source_attack: str | None,
                      note: str | None, active: bool) -> None:
    with _lock:
        if active:
            _db.execute("UPDATE agent_versions SET active=0")
        _db.execute("INSERT OR IGNORE INTO agent_versions(version, created_at, title, rules, gates, source_attack, note, active)"
                    " VALUES(?,?,?,?,?,?,?,?)", (version, now(), title, json.dumps(rules, ensure_ascii=False),
                                                 json.dumps(gates), source_attack, note, int(active)))
        _db.commit()


def sync_agent_version(version: int, title: str, rules: list[str], gates: dict, note: str | None) -> None:
    """Built-in versions are defined in code; keep their stored copy identical to it."""
    _exec("UPDATE agent_versions SET title=?, rules=?, gates=?, note=? WHERE version=?",
          (title, json.dumps(rules, ensure_ascii=False), json.dumps(gates), note, version))


def activate_agent_version(version: int) -> bool:
    with _lock:
        if not _db.execute("SELECT 1 FROM agent_versions WHERE version=?", (version,)).fetchone():
            return False
        _db.execute("UPDATE agent_versions SET active=CASE WHEN version=? THEN 1 ELSE 0 END", (version,))
        _db.commit()
    return True


def login_fails(key: str) -> dict | None:
    r = _rows("SELECT * FROM login_fails WHERE key=?", (key,))
    return r[0] if r else None


def set_login_fails(key: str, n: int, until: float) -> None:
    _exec("INSERT INTO login_fails(key, n, until) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET n=excluded.n, until=excluded.until",
          (key, n, until))


def clear_login_fails(key: str) -> None:
    _exec("DELETE FROM login_fails WHERE key=?", (key,))


def log(kind: str, text: str, worker_id: str | None = None, employer_id: str | None = None,
        call_id: str | None = None) -> None:
    _exec("INSERT INTO events(at, kind, worker_id, employer_id, call_id, text) VALUES(?,?,?,?,?,?)",
          (now(), kind, worker_id, employer_id, call_id, text))


def events(limit: int = 80, worker_id: str | None = None) -> list[dict]:
    if worker_id:
        return _rows("SELECT * FROM events WHERE worker_id=? ORDER BY id DESC LIMIT ?", (worker_id, limit))
    return _rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


# ---- workers & employers ---------------------------------------------------------------
def create_worker(name: str, phone: str, language: str, role: str, city: str, state: str,
                  voice: str | None = None, device: str | None = None, sim_group: str | None = None,
                  upi_id: str | None = None, pin_hash: str | None = None) -> dict:
    p = normalize_phone(phone)
    if not p:
        raise ValueError(f"not a valid Indian mobile number: {phone}")
    existing = _one("SELECT * FROM workers WHERE phone=?", (p,))
    if existing:
        return existing
    wid = _id("w")
    _exec("""INSERT INTO workers(id, name, phone, language, role, city, state, voice, device, created_at, sim_group,
             upi_id, pin_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (wid, name, p, language, role, city, state, voice, device or secrets.token_hex(4), now(), sim_group,
           upi_id, pin_hash))
    log("worker.joined", f"{name} joined as {role} in {city}", worker_id=wid)
    return get_worker(wid)  # type: ignore[return-value]


def get_worker(wid: str) -> dict | None:
    return _one("SELECT * FROM workers WHERE id=?", (wid,))


def worker_by_phone(phone: str) -> dict | None:
    p = normalize_phone(phone)
    return _one("SELECT * FROM workers WHERE phone=?", (p,)) if p else None


def update_worker(wid: str, **fields) -> None:
    for k, v in fields.items():
        _exec(f"UPDATE workers SET {k}=? WHERE id=?", (v, wid))


def list_workers() -> list[dict]:
    return _rows("SELECT * FROM workers ORDER BY created_at")


def upsert_employer(phone: str, name: str, kind: str = "household", language: str | None = None,
                    persona: str | None = None, voice: str | None = None, device: str | None = None,
                    sim_group: str | None = None) -> dict:
    p = normalize_phone(phone)
    if not p:
        raise ValueError(f"not a valid Indian mobile number: {phone}")
    e = _one("SELECT * FROM employers WHERE phone=?", (p,))
    if e:
        if persona and not e.get("persona"):
            _exec("UPDATE employers SET persona=?, voice=? WHERE id=?", (persona, voice, e["id"]))
        return get_employer(e["id"])  # type: ignore[return-value]
    eid = _id("e")
    _exec("""INSERT INTO employers(id, phone, name, kind, language, opted_out, device, persona, voice, created_at,
             sim_group) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          (eid, p, name, kind, language, 0, device or secrets.token_hex(4), persona, voice, now(), sim_group))
    return get_employer(eid)  # type: ignore[return-value]


def get_employer(eid: str) -> dict | None:
    return _one("SELECT * FROM employers WHERE id=?", (eid,))


def employer_by_phone(phone: str) -> dict | None:
    p = normalize_phone(phone)
    return _one("SELECT * FROM employers WHERE phone=?", (p,)) if p else None


def list_employers() -> list[dict]:
    return _rows("SELECT * FROM employers ORDER BY created_at")


def update_employer(eid: str, **fields) -> None:
    for k, v in fields.items():
        _exec(f"UPDATE employers SET {k}=? WHERE id=?", (v, eid))


def worker_employers(wid: str) -> list[dict]:
    return _rows("""SELECT DISTINCT e.* FROM employers e JOIN entries x ON x.employer_id = e.id
                    WHERE x.worker_id=? ORDER BY e.created_at""", (wid,))


# ---- entries (hash-chained) --------------------------------------------------------------
_HASHED = ("worker_id", "employer_id", "seq", "pay_type", "period_start", "period_end", "days", "rate", "amount",
           "claimed")


def _canon_val(v):
    # numbers hash identically whether they come from Python (3000) or SQLite (3000.0)
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return f"{float(v):.2f}"
    return v


def _entry_hash(prev: str, row: dict) -> str:
    payload = json.dumps({k: _canon_val(row.get(k)) for k in _HASHED}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev + payload).encode()).hexdigest()


def add_entry(worker_id: str, employer_id: str, *, role: str | None, pay_type: str, period: dict,
              days: float | None, rate: float | None, amount: float, paid: float | None, paid_mode: str | None,
              do_not_contact: bool, source_audio: str | None, transcript: str | None) -> dict:
    with _lock:
        last = _one("SELECT seq, hash FROM entries WHERE worker_id=? ORDER BY seq DESC LIMIT 1", (worker_id,))
        seq = (last["seq"] + 1) if last else 1
        prev = last["hash"] if last else "genesis"
        claimed = json.dumps({"amount": amount, "days": days, "rate": rate, "period": period}, ensure_ascii=False)
        row = {
            "id": _id("x"), "worker_id": worker_id, "employer_id": employer_id, "seq": seq, "role": role,
            "pay_type": pay_type, "period_start": period["start"], "period_end": period["end"],
            "period_label": period.get("label"), "days": days, "rate": rate, "amount": amount, "paid": paid,
            "paid_mode": paid_mode, "status": "self_declared" if do_not_contact else "pending", "claimed": claimed,
            "employer_says": None, "attested_by": None, "do_not_contact": int(do_not_contact),
            "source_audio": source_audio, "transcript": transcript, "confidence": None, "reasons": "[]",
            "prev_hash": prev, "hash": "", "created_at": now(), "updated_at": now(),
        }
        row["hash"] = _entry_hash(prev, row)
        cols = ",".join(row)
        _db.execute(f"INSERT INTO entries({cols}) VALUES({','.join('?' * len(row))})", tuple(row.values()))
        _db.commit()
    return get_entry(row["id"])  # type: ignore[return-value]


def get_entry(xid: str) -> dict | None:
    return _one("SELECT * FROM entries WHERE id=?", (xid,))


def worker_entries(wid: str) -> list[dict]:
    return _rows("""SELECT x.*, e.name AS employer_name, e.phone AS employer_phone, e.kind AS employer_kind
                    FROM entries x JOIN employers e ON e.id = x.employer_id
                    WHERE x.worker_id=? ORDER BY x.period_start DESC, x.seq DESC""", (wid,))


def all_entries() -> list[dict]:
    return _rows("SELECT * FROM entries")


def update_entry(xid: str, **fields) -> None:
    fields["updated_at"] = now()
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        _exec(f"UPDATE entries SET {k}=? WHERE id=?", (v, xid))


def verify_chain(wid: str) -> bool:
    prev = "genesis"
    for row in _rows("SELECT * FROM entries WHERE worker_id=? ORDER BY seq", (wid,)):
        if row["prev_hash"] != prev or row["hash"] != _entry_hash(prev, row):
            return False
        prev = row["hash"]
    return True


# ---- calls ------------------------------------------------------------------------------
def create_call(employer_id: str, entry_ids: list[str], mode: str) -> dict:
    cid = _id("c")
    _exec("INSERT INTO calls(id, employer_id, entry_ids, status, mode, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
          (cid, employer_id, json.dumps(entry_ids), "queued", mode, now(), now()))
    return get_call(cid)  # type: ignore[return-value]


def get_call(cid: str) -> dict | None:
    c = _one("SELECT * FROM calls WHERE id=?", (cid,))
    if c:
        c["entry_ids"] = json.loads(c["entry_ids"])
        c["transcript"] = json.loads(c["transcript"] or "[]")
    return c


def list_calls(limit: int = 100) -> list[dict]:
    out = _rows("SELECT * FROM calls ORDER BY created_at DESC LIMIT ?", (limit,))
    for c in out:
        c["entry_ids"] = json.loads(c["entry_ids"])
        c["transcript"] = json.loads(c["transcript"] or "[]")
    return out


def update_call(cid: str, **fields) -> None:
    fields["updated_at"] = now()
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        _exec(f"UPDATE calls SET {k}=? WHERE id=?", (v, cid))


def pending_calls_for(employer_id: str) -> list[dict]:
    return [c for c in list_calls(500) if c["employer_id"] == employer_id and c["status"] in ("queued", "callback")]


# ---- evidence & shares --------------------------------------------------------------------
def add_evidence(worker_id: str, kind: str, raw: str, parsed: dict | None, entry_id: str | None) -> dict:
    eid = _id("ev")
    _exec("INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",
          (eid, worker_id, kind, raw, json.dumps(parsed or {}, ensure_ascii=False), entry_id, now()))
    return _one("SELECT * FROM evidence WHERE id=?", (eid,))  # type: ignore[return-value]


def worker_evidence(wid: str) -> list[dict]:
    return _rows("SELECT * FROM evidence WHERE worker_id=? ORDER BY created_at DESC", (wid,))


def create_share(worker_id: str, scope: str, audience: str | None, expires_at: str | None) -> dict:
    token = secrets.token_urlsafe(9)
    _exec("INSERT INTO shares VALUES(?,?,?,?,?,?,?,?)", (token, worker_id, scope, audience, expires_at, 0, 0, now()))
    return get_share(token)  # type: ignore[return-value]


def get_share(token: str) -> dict | None:
    return _one("SELECT * FROM shares WHERE token=?", (token,))


def worker_shares(wid: str) -> list[dict]:
    return _rows("SELECT * FROM shares WHERE worker_id=? ORDER BY created_at DESC", (wid,))


def update_share(token: str, **fields) -> None:
    for k, v in fields.items():
        _exec(f"UPDATE shares SET {k}=? WHERE token=?", (v, token))


# ---- employer confirmation links ------------------------------------------------------------------
def create_link(worker_id: str, employer_id: str, entry_ids: list[str]) -> dict:
    token = secrets.token_urlsafe(8)
    _exec("INSERT INTO links(token, worker_id, employer_id, entry_ids, status, created_at) VALUES(?,?,?,?,?,?)",
          (token, worker_id, employer_id, json.dumps(entry_ids), "sent", now()))
    return get_link(token)  # type: ignore[return-value]


def get_link(token: str) -> dict | None:
    l = _one("SELECT * FROM links WHERE token=?", (token,))
    if l:
        l["entry_ids"] = json.loads(l["entry_ids"])
    return l


def worker_links(wid: str) -> list[dict]:
    out = _rows("SELECT * FROM links WHERE worker_id=? ORDER BY created_at DESC", (wid,))
    for l in out:
        l["entry_ids"] = json.loads(l["entry_ids"])
    return out


def update_link(token: str, **fields) -> None:
    for k, v in fields.items():
        _exec(f"UPDATE links SET {k}=? WHERE token=?", (v, token))


def delete_worker_everything(wid: str) -> list[str]:
    """Erase a worker and everything about them. Returns audio folders to remove."""
    with _lock:
        entry_ids = [r[0] for r in _db.execute("SELECT id FROM entries WHERE worker_id=?", (wid,)).fetchall()]
        for t in ("entries", "evidence", "shares", "links", "events"):
            _db.execute(f"DELETE FROM {t} WHERE worker_id=?", (wid,))
        for c in _db.execute("SELECT id, entry_ids FROM calls").fetchall():
            if set(json.loads(c[1])) & set(entry_ids):
                _db.execute("DELETE FROM calls WHERE id=?", (c[0],))
        _db.execute("DELETE FROM workers WHERE id=?", (wid,))
        _db.commit()
    return [f"j_{wid}"]


def reset_demo() -> None:
    """Remove only demo / simulation data (anything with a sim_group). Real users' records are never touched."""
    with _lock:
        # Kavach's sandbox worlds are kept: they are the evidence behind each attack report (pruned on their own)
        wids = [r[0] for r in _db.execute("SELECT id FROM workers WHERE sim_group IS NOT NULL AND sim_group != 'kavach'").fetchall()]
        eids = [r[0] for r in _db.execute("SELECT id FROM employers WHERE sim_group IS NOT NULL AND sim_group != 'kavach'").fetchall()]
        if wids:
            q = ",".join("?" * len(wids))
            entry_ids = [r[0] for r in _db.execute(f"SELECT id FROM entries WHERE worker_id IN ({q})", wids).fetchall()]
            for t in ("entries", "evidence", "shares", "links", "events"):
                _db.execute(f"DELETE FROM {t} WHERE worker_id IN ({q})", wids)
            for c in _db.execute("SELECT id, entry_ids FROM calls").fetchall():
                if set(json.loads(c[1])) & set(entry_ids):
                    _db.execute("DELETE FROM calls WHERE id=?", (c[0],))
            _db.execute(f"DELETE FROM workers WHERE id IN ({q})", wids)
        if eids:
            q = ",".join("?" * len(eids))
            still_used = {r[0] for r in _db.execute(f"SELECT DISTINCT employer_id FROM entries WHERE employer_id IN ({q})", eids)}
            gone = [e for e in eids if e not in still_used]
            if gone:
                _db.execute(f"DELETE FROM employers WHERE id IN ({','.join('?' * len(gone))})", gone)
        # employers nobody has a record with any more (left over from demo runs or deleted accounts)
        _db.execute("""DELETE FROM employers WHERE id NOT IN (SELECT DISTINCT employer_id FROM entries)
                       AND id NOT IN (SELECT DISTINCT employer_id FROM calls)""")
        _db.execute("DELETE FROM events WHERE worker_id IS NULL AND kind LIKE 'demo.%' OR kind LIKE 'redteam.%'")
        _db.commit()


def reset_all() -> None:
    with _lock:
        for t in ("workers", "employers", "entries", "calls", "evidence", "shares", "events", "links"):
            _db.execute(f"DELETE FROM {t}")
        _db.commit()
