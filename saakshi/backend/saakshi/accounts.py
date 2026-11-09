"""Worker accounts: phone + PIN, no SMS costs. Tokens are HMAC-signed, so no session table is needed."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

from .config import settings


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 120_000)
    return f"{salt}${dk.hex()}"


def check_pin(pin: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, want = stored.split("$", 1)
    got = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(got, want)


def valid_pin(pin: str) -> bool:
    return bool(re.fullmatch(r"\d{4,6}", pin or "")) and len(set(pin)) > 1   # not 0000 / 1111


TOKEN_DAYS = 30


def _pin_epoch(worker_id: str) -> str:
    """Changes whenever the PIN changes (new salt), so a PIN reset logs every old session out."""
    from . import store
    w = store.get_worker(worker_id) or {}
    return (w.get("pin_hash") or "").split("$", 1)[0]


def _sig(worker_id: str, exp: int, epoch: str) -> str:
    msg = f"worker:{worker_id}:{exp}:{epoch}".encode()
    return hmac.new(settings.signing_key.encode(), msg, hashlib.sha256).hexdigest()[:40]


def token_for(worker_id: str, days: int = TOKEN_DAYS) -> str:
    exp = int(time.time()) + days * 86400
    return f"{worker_id}.{exp}.{_sig(worker_id, exp, _pin_epoch(worker_id))}"


def worker_from_token(token: str | None) -> str | None:
    if not token or token.count(".") != 2:
        return None
    wid, exp_s, sig = token.split(".")
    if not exp_s.isdigit() or int(exp_s) < time.time():
        return None
    return wid if hmac.compare_digest(_sig(wid, int(exp_s), _pin_epoch(wid)), sig) else None


# ---- wrong-PIN lockout: 5 wrong tries locks the number for 15 minutes (kept in the database) -------------------
MAX_TRIES, LOCK_SECONDS = 5, 15 * 60


def locked_for(key: str) -> int:
    """Seconds until this phone may try a PIN again (0 = may try now)."""
    from . import store
    row = store.login_fails(key)
    return max(0, int(row["until"] - time.time())) if row and row["until"] else 0


def record_attempt(key: str, ok: bool) -> None:
    from . import store
    if ok:
        store.clear_login_fails(key)
        return
    row = store.login_fails(key)
    n = (row["n"] if row and not (row["until"] and row["until"] < time.time()) else 0) + 1
    store.set_login_fails(key, n, time.time() + LOCK_SECONDS if n >= MAX_TRIES else 0)


UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,64}$")


def valid_upi(vpa: str) -> bool:
    return bool(UPI_RE.match(vpa or ""))
