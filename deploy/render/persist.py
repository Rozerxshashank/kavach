"""Keep an app's data alive on a host whose disk is wiped on every restart (Render free, Spaces).

    python persist.py <command...>

1. On start, restore DATA_DIR from a private Hugging Face Dataset (PERSIST_REPO, under PERSIST_PREFIX/).
2. Start the app (the given command) as a child process.
3. Every PERSIST_EVERY seconds, and once more on shutdown, push what changed: SQLite databases as consistent
   snapshots (the online backup API, safe while the app writes), every other file only if it changed, and
   deletions too (a deleted run's audio is deleted from the backup).

Without HF_TOKEN and PERSIST_REPO it just runs the command, so the same image works anywhere.
Never prints a secret."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = os.environ.get("PERSIST_REPO", "")
# Which folders to keep: "prefix:dir prefix:dir" (e.g. "kavach:/data/kavach saakshi:/data/saakshi"),
# or one folder from DATA_DIR + PERSIST_PREFIX.
PAIRS = [(p.split(":", 1)[0].strip("/"), Path(p.split(":", 1)[1])) for p in os.environ.get("PERSIST_DIRS", "").split()
         if ":" in p] or [(os.environ.get("PERSIST_PREFIX", "app").strip("/"), Path(os.environ.get("DATA_DIR", "/data")))]
EVERY = max(60, int(os.environ.get("PERSIST_EVERY", "300")))
TOKEN = os.environ.get("HF_TOKEN", "")
SKIP_DIRS = {"backups"}                                   # the app's own local rotations; the Dataset keeps history
SKIP_SUFFIX = (".db-wal", ".db-shm", ".db-journal", ".tmp")
INDEX_NAME = ".persist-index.json"                       # what the Dataset holds: path -> content hash

_lock = threading.Lock()


def log(msg: str) -> None:
    print(f"[persist] {msg}", flush=True)


def _api():
    from huggingface_hub import HfApi
    return HfApi(token=TOKEN)


def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def restore() -> None:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import RepositoryNotFoundError
    try:
        got = Path(snapshot_download(REPO, repo_type="dataset", token=TOKEN,
                                     allow_patterns=[f"{p}/**" for p, _ in PAIRS],
                                     local_dir=tempfile.mkdtemp(prefix="restore-")))
    except RepositoryNotFoundError:
        log("no backup repo yet: starting empty"); return
    for prefix, data in PAIRS:
        src = got / prefix
        data.mkdir(parents=True, exist_ok=True)
        if not src.is_dir():
            log(f"{prefix}: nothing backed up yet, starting fresh"); continue
        n, index = 0, {}
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                dst = data / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
                index[rel.as_posix()] = _hash(dst)
                n += 1
        (data / INDEX_NAME).write_text(json.dumps(index))
        log(f"{prefix}: restored {n} files")
    shutil.rmtree(got, ignore_errors=True)


def _snapshot_db(src: Path, dst: Path) -> None:
    """A consistent copy of a live SQLite database (WAL included)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close(); s.close()


def push(reason: str) -> None:
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete
    with _lock:
        stage = Path(tempfile.mkdtemp(prefix="persist-"))
        try:
            ops, after = [], []
            for prefix, data in PAIRS:
                idx_file = data / INDEX_NAME
                try:
                    index = json.loads(idx_file.read_text()) if idx_file.exists() else {}
                except ValueError:
                    index = {}
                now: dict[str, str] = {}
                files: dict[str, Path] = {}
                for f in data.rglob("*"):
                    rel = f.relative_to(data)
                    if (not f.is_file() or f.name == INDEX_NAME or rel.parts[0] in SKIP_DIRS
                            or f.name.endswith(SKIP_SUFFIX)):
                        continue
                    key = rel.as_posix()
                    try:
                        if f.suffix == ".db":
                            snap = stage / prefix / rel
                            _snapshot_db(f, snap)
                            f = snap
                        now[key], files[key] = _hash(f), f
                    except (OSError, sqlite3.Error) as e:      # a file vanished or is mid-write: next round
                        log(f"skipped {prefix}/{key}: {type(e).__name__}")
                ops += [CommitOperationAdd(f"{prefix}/{k}", str(files[k])) for k in now if index.get(k) != now[k]]
                ops += [CommitOperationDelete(f"{prefix}/{k}") for k in index if k not in now]
                after.append((idx_file, now))
            if not ops:
                return
            _api().create_commit(REPO, repo_type="dataset", operations=ops,
                                 commit_message=f"{reason}: {len(ops)} change(s)")
            for idx_file, now in after:
                idx_file.write_text(json.dumps(now))
            log(f"pushed {len(ops)} change(s) ({reason})")
        except Exception as e:  # noqa: BLE001 - a failed backup must never take the app down
            log(f"push failed ({reason}): {type(e).__name__}: {str(e)[:200]}")
        finally:
            shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    cmd = sys.argv[1:]
    if not cmd:
        print(__doc__); return 2
    for _, d in PAIRS:
        d.mkdir(parents=True, exist_ok=True)
    on = bool(TOKEN and REPO)
    if on:
        try:
            restore()
        except Exception as e:  # noqa: BLE001
            log(f"restore failed, starting with what is on disk: {type(e).__name__}: {str(e)[:200]}")
    else:
        log("HF_TOKEN or PERSIST_REPO not set: data is not backed up")
    child = subprocess.Popen(cmd)
    stop = threading.Event()

    def forward(sig, _frame):
        stop.set()
        child.send_signal(sig)
    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)

    def loop():
        while not stop.wait(EVERY):
            push("scheduled")
    if on:
        threading.Thread(target=loop, daemon=True).start()
    code = child.wait()
    if on:
        push("shutdown")
    return code


if __name__ == "__main__":
    sys.exit(main())
