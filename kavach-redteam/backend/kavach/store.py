"""SQLite persistence: runs (as JSON documents) and target versions."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .bank import TargetConfig
from .config import settings

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(settings.db_path, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


_db = _conn()
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("PRAGMA busy_timeout=5000")
with _lock:
    _db.executescript("""
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS targets (
        version INTEGER PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shield_keys (
        id TEXT PRIMARY KEY, policy TEXT NOT NULL, name TEXT NOT NULL, prefix TEXT NOT NULL, hash TEXT NOT NULL,
        created_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, last_used TEXT);
    CREATE INDEX IF NOT EXISTS shield_keys_prefix ON shield_keys(prefix);
    CREATE TABLE IF NOT EXISTS shield_policies (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shield_calls (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, policy TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
        peak_risk INTEGER NOT NULL, turns INTEGER NOT NULL, data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS shield_calls_started ON shield_calls(started_at);
    """)
    _db.commit()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- runs ----------------------------------------------------------------------
def save_run(run: dict) -> None:
    with _lock:
        _db.execute("INSERT INTO runs(id, created_at, data) VALUES(?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (run["id"], run["created_at"], json.dumps(run, ensure_ascii=False)))
        _db.commit()


def get_run(run_id: str) -> dict | None:
    with _lock:
        row = _db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_runs(limit: int = 100) -> list[dict]:
    with _lock:
        rows = _db.execute("SELECT data FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["data"])
        d.pop("turns", None)
        d.pop("events", None)
        out.append(d)
    return out


def delete_run(run_id: str) -> None:
    with _lock:
        _db.execute("DELETE FROM runs WHERE id=?", (run_id,))
        _db.commit()


# ---- target versions -------------------------------------------------------------
def _ensure_baseline() -> None:
    with _lock:
        row = _db.execute("SELECT COUNT(*) AS n FROM targets").fetchone()
        if row["n"] == 0:
            base = TargetConfig()
            _db.execute("INSERT INTO targets(version, created_at, data) VALUES(?,?,?)",
                        (1, now(), json.dumps(base.to_dict())))
            _db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES('active_target', '1')")
            _db.commit()


_ensure_baseline()


def list_targets() -> list[dict]:
    with _lock:
        rows = _db.execute("SELECT version, created_at, data FROM targets ORDER BY version").fetchall()
    return [{**json.loads(r["data"]), "version": r["version"], "created_at": r["created_at"]} for r in rows]


def get_target(version: int | None = None) -> TargetConfig:
    if version is None:
        version = active_target_version()
    with _lock:
        row = _db.execute("SELECT data FROM targets WHERE version=?", (version,)).fetchone()
    if not row:
        return TargetConfig()
    t = TargetConfig.from_dict(json.loads(row["data"]))
    t.version = version
    return t


def active_target_version() -> int:
    with _lock:
        row = _db.execute("SELECT v FROM kv WHERE k='active_target'").fetchone()
    return int(row["v"]) if row else 1


def set_active_target(version: int) -> None:
    with _lock:
        _db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES('active_target', ?)", (str(version),))
        _db.commit()


def create_target(cfg: TargetConfig) -> TargetConfig:
    with _lock:
        row = _db.execute("SELECT COALESCE(MAX(version), 0) AS m FROM targets").fetchone()
        cfg.version = int(row["m"]) + 1
        _db.execute("INSERT INTO targets(version, created_at, data) VALUES(?,?,?)",
                    (cfg.version, now(), json.dumps(cfg.to_dict())))
        _db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES('active_target', ?)", (str(cfg.version),))
        _db.commit()
    return cfg


def backup(keep: int = 7) -> str | None:
    """One consistent copy of the database per day in data/backups; the last `keep` days are kept."""
    folder = settings.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"kavach-{datetime.now(timezone.utc):%Y%m%d}.db"
    if target.exists():
        return None
    tmp = target.with_suffix(".part")
    dst = sqlite3.connect(tmp)
    with _lock:
        _db.backup(dst)
    dst.close()
    tmp.rename(target)
    for old in sorted(folder.glob("kavach-*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    return str(target)


def healthy() -> bool:
    try:
        with _lock:
            return _db.execute("SELECT 1").fetchone()[0] == 1
    except sqlite3.Error:
        return False


def runs_since(iso: str, modes: tuple[str, ...] = ("campaign", "replay")) -> int:
    with _lock:
        rows = _db.execute("SELECT data FROM runs WHERE created_at >= ?", (iso,)).fetchall()
    return sum(1 for r in rows if json.loads(r["data"]).get("mode") in modes)


# ---- Shield: keys, custom policies, finished calls ---------------------------------------------------------------------
def shield_key_add(kid: str, policy: str, name: str, prefix: str, hashed: str) -> None:
    with _lock:
        _db.execute("INSERT INTO shield_keys(id, policy, name, prefix, hash, created_at) VALUES(?,?,?,?,?,?)",
                    (kid, policy, name, prefix, hashed, now()))
        _db.commit()


def shield_keys_by_prefix(prefix: str) -> list[dict]:
    with _lock:
        return [dict(r) for r in _db.execute("SELECT * FROM shield_keys WHERE prefix=? AND revoked=0", (prefix,))]


def shield_keys() -> list[dict]:
    with _lock:
        return [{k: r[k] for k in r.keys() if k != "hash"} for r in
                _db.execute("SELECT * FROM shield_keys ORDER BY created_at DESC").fetchall()]


def shield_key_revoke(kid: str) -> bool:
    with _lock:
        cur = _db.execute("UPDATE shield_keys SET revoked=1 WHERE id=?", (kid,))
        _db.commit()
        return cur.rowcount > 0


def shield_key_used(kid: str) -> None:
    with _lock:
        _db.execute("UPDATE shield_keys SET last_used=? WHERE id=?", (now(), kid))
        _db.commit()


def shield_policy_save(p: dict) -> None:
    with _lock:
        _db.execute("INSERT INTO shield_policies(id, created_at, data) VALUES(?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data", (p["id"], now(), json.dumps(p, ensure_ascii=False)))
        _db.commit()


def shield_policies() -> list[dict]:
    with _lock:
        return [json.loads(r["data"]) for r in _db.execute("SELECT data FROM shield_policies ORDER BY id")]


def shield_call_save(summary: dict, owner: str, started_at: str) -> None:
    with _lock:
        _db.execute("INSERT INTO shield_calls(id, owner, policy, started_at, ended_at, peak_risk, turns, data) "
                    "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ended_at=excluded.ended_at, "
                    "peak_risk=excluded.peak_risk, turns=excluded.turns, data=excluded.data",
                    (summary["session_id"], owner, summary["policy"], started_at, now(), summary["peak_risk"],
                     summary["turns"], json.dumps(summary, ensure_ascii=False)))
        _db.execute("DELETE FROM shield_calls WHERE id IN (SELECT id FROM shield_calls ORDER BY started_at DESC LIMIT -1 OFFSET 5000)")
        _db.commit()


def shield_calls(limit: int = 100, owner: str | None = None) -> list[dict]:
    with _lock:
        q = "SELECT data, owner, started_at, ended_at FROM shield_calls"
        args: tuple = ()
        if owner:
            q += " WHERE owner=?"
            args = (owner,)
        rows = _db.execute(q + " ORDER BY started_at DESC LIMIT ?", (*args, limit)).fetchall()
    return [{**json.loads(r["data"]), "owner": r["owner"], "started_at": r["started_at"], "ended_at": r["ended_at"]}
            for r in rows]
