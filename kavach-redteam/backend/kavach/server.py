"""HTTP API, event streams and static hosting for Kavach.

    /api/targets ...     the voice agents Kavach protects (Saakshi over its harness, the Navyug bank bot in-process)
    /api/runs ...        attacks, exact replays against a fix, fixes and promotion
    /api/live ...        a person attacks an agent with their own voice
    /api/shield/...      Kavach Shield: the runtime guard (product API, operator API, playground)
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audio, engine, gnani, security, store
from .config import settings
from .security import is_admin, require_admin
from .shield.api import router as shield_router
from .shield.policies import BUILTIN as SHIELD_POLICIES
from .targets import TARGETS, TargetError
from .targets import get as get_target

app = FastAPI(title="Kavach", version="3.0.0", docs_url=None if settings.production else "/docs", redoc_url=None,
              openapi_url=None if settings.production else "/openapi.json")
if not settings.production:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(security.Guard)
app.include_router(shield_router)

Env = Literal["none", "airport", "traffic", "crowd", "siren"]
Intensity = Literal["light", "medium", "heavy"]
Lang = Literal["en-IN", "hi-IN"]


@app.on_event("startup")
async def startup() -> None:
    engine.recover()

    async def backups():
        while True:
            try:
                await asyncio.to_thread(store.backup)
            except Exception:
                pass
            await asyncio.sleep(6 * 3600)
    asyncio.get_running_loop().create_task(backups())


def _target(tid: str):
    try:
        return get_target(tid)
    except KeyError:
        raise HTTPException(404, "No such target.")


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    if not store.healthy():
        raise HTTPException(503, "database unavailable")
    return {"ok": True, "gnani": bool(settings.gnani_api_key), "llm": bool(settings.groq_api_key)}


@app.get("/api/meta")
def meta(x_admin_key: str | None = Header(None)):
    return {
        "targets": {k: t.public() for k, t in TARGETS.items()},
        "environments": audio.ENVIRONMENTS,
        "shield_policies": {k: {"name": p["name"], "description": p["description"]} for k, p in SHIELD_POLICIES.items()},
        "models": {"tts": settings.tts_model, "asr": "prisma-v2.5", "bot_voice": gnani.BOT_VOICE,
                   "attacker": settings.attacker_model, "bot": settings.bot_model, "judge": settings.judge_model,
                   "shield": settings.shield_model},
        "ready": {"gnani": bool(settings.gnani_api_key), "llm": bool(settings.groq_api_key)},
        "quota": engine.quota(), "running": engine.running(),
        "operator": is_admin(x_admin_key) and bool(settings.admin_key),
    }


# ---- targets ------------------------------------------------------------------------------------------------------------
@app.get("/api/targets")
async def targets():
    out = []
    for t in TARGETS.values():
        ok, why = await t.available()
        out.append({**t.public(), "available": ok, "unavailable_reason": why})
    return out


@app.get("/api/targets/{tid}")
async def target_detail(tid: str):
    t = _target(tid)
    ok, why = await t.available()
    data = {**t.public(), "available": ok, "unavailable_reason": why}
    if ok:
        try:
            data["versions"] = await t.versions()
            data["gates"] = t.gates
        except TargetError as e:
            data.update(available=False, unavailable_reason=str(e))
    return data


@app.post("/api/targets/{tid}/versions/{version}/activate")
async def activate_version(tid: str, version: int, x_admin_key: str | None = Header(None)):
    require_admin(x_admin_key)
    try:
        return await _target(tid).activate(version)
    except TargetError as e:
        raise HTTPException(404, str(e))


# ---- attacks ------------------------------------------------------------------------------------------------------------
class AttackReq(BaseModel):
    target: str = "saakshi"
    persona: str
    objective: str
    language: Lang | None = None
    environment: Env = "none"
    intensity: Intensity = "medium"
    max_turns: int = Field(6, ge=2, le=8)
    hardening: Literal["live", "original"] | int = "live"
    shield: bool = False


async def _hardening(t, choice, admin: bool) -> dict:
    if not isinstance(choice, str) and not admin:
        raise HTTPException(401, "Operator key required to attack an older version.")
    try:
        return await t.hardening(choice)
    except TargetError as e:
        raise HTTPException(503 if "unreachable" in str(e) or "connected" in str(e) else 404, str(e))


def _gatekeep(admin: bool) -> None:
    if engine.running():
        raise HTTPException(409, "Another attack is on the line. Watch it, or try again in a minute.")
    if not admin and engine.quota()["left"] <= 0:
        raise HTTPException(429, "Today's attack budget is used up. It resets at midnight UTC.")


@app.post("/api/runs", status_code=202)
async def start_run(body: AttackReq, x_admin_key: str | None = Header(None)):
    admin = is_admin(x_admin_key)
    t = _target(body.target)
    if body.persona not in t.personas or body.objective not in t.objectives:
        raise HTTPException(400, "Unknown persona or objective for this target.")
    if body.language and body.language not in t.languages:
        raise HTTPException(400, "This target doesn't speak that language.")
    _gatekeep(admin)
    hardening = await _hardening(t, body.hardening, admin)
    h = engine.new_run("campaign", target=t, persona=body.persona, objective=body.objective, language=body.language,
                       environment=body.environment, intensity=body.intensity, max_turns=body.max_turns,
                       hardening=hardening, shield=body.shield)
    engine.start(h)
    return {"id": h.run["id"], "owner": engine.owner_token(h.run["id"])}


class ReplayReq(BaseModel):
    against: Literal["candidate", "live", "same"] = "candidate"
    title: str = Field("Candidate fix", max_length=80)
    rules: list[str] = Field(default_factory=list, max_length=8)
    gates: dict[str, bool] = Field(default_factory=dict)
    shield: bool | None = None


def _clean_rules(rules: list[str]) -> list[str]:
    out = []
    for r in rules:
        r = " ".join(str(r).split())
        if r:
            out.append(r[:320])
    return out[:8]


@app.post("/api/runs/{run_id}/replay", status_code=202)
async def replay(run_id: str, body: ReplayReq, x_admin_key: str | None = Header(None)):
    """The exact recorded attack audio again: against a candidate fix (only in this sandbox call), the live agent,
    or the same version, optionally with the Shield in front."""
    admin = is_admin(x_admin_key)
    parent = store.get_run(run_id)
    if not parent or parent["mode"] == "live" or parent.get("status") == "running":
        raise HTTPException(404, "Run not found or not replayable yet.")
    if parent.get("parent"):
        parent = store.get_run(parent["parent"]) or parent    # always replay the original attack, not a replay
    if not any(t.get("caller_audio") for t in parent.get("turns", [])):
        raise HTTPException(409, "This run has no recorded caller audio to replay.")
    t = _target(parent["target"])
    _gatekeep(admin)
    if body.against == "candidate":
        gates = {k: bool(v) for k, v in body.gates.items() if k in (t.gates or {})}
        hardening = t.candidate(parent["hardening"], body.title.strip() or "Candidate fix", _clean_rules(body.rules), gates)
    elif body.against == "live":
        hardening = await _hardening(t, "live", admin)
    else:
        hardening = parent["hardening"]
    h = engine.new_run("replay", target=t, persona=parent["persona"], objective=parent["objective"],
                       language=parent["language"], environment=parent["environment"], intensity=parent["intensity"],
                       max_turns=max(2, len(parent["turns"])), hardening=hardening,
                       shield=parent["shield"] if body.shield is None else body.shield, parent=parent["id"],
                       world=parent.get("world"))
    engine.start(h)
    return {"id": h.run["id"], "owner": engine.owner_token(h.run["id"])}


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str, x_run_owner: str | None = Header(None), x_admin_key: str | None = Header(None)):
    h = engine.RUNS.get(run_id)
    if not h or h.done:
        raise HTTPException(404, "That call isn't on the line.")
    if not (engine.is_owner(run_id, x_run_owner) or is_admin(x_admin_key)):
        raise HTTPException(403, "Only the person who started this call can hang it up.")
    h.stop = True
    return {"ok": True}


@app.get("/api/runs")
def runs(target: str | None = None):
    rows = store.list_runs(150)
    if target:
        rows = [r for r in rows if r.get("target", "bank") == target]
    return [engine.public_run(r) for r in rows]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    h = engine.RUNS.get(run_id)
    run = h.run if h else store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    return engine.public_run(run)


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str, x_admin_key: str | None = Header(None)):
    require_admin(x_admin_key)
    if engine.RUNS.get(run_id) and not engine.RUNS[run_id].done:
        raise HTTPException(409, "Stop the call first.")
    store.delete_run(run_id)
    shutil.rmtree(settings.audio_dir / run_id, ignore_errors=True)
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, after: int = 0):
    h = engine.RUNS.get(run_id)
    if not h:
        raise HTTPException(404, "This call isn't live any more (open its report instead).")

    async def gen():
        async for ev in h.stream(max(0, after)):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _finished(run_id: str) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    if run.get("status") not in ("complete", "stopped") or run.get("verdict") is None:
        raise HTTPException(409, "Wait for this call's verdict first.")
    return run


@app.post("/api/runs/{run_id}/fix")
async def propose_fix(run_id: str, x_admin_key: str | None = Header(None)):
    run = _finished(run_id)
    if not run.get("findings"):
        raise HTTPException(400, "Nothing to fix: this call had no findings.")
    if run.get("fix") and not is_admin(x_admin_key):
        return run["fix"]                                  # one model-written fix per run (quota)
    from . import llm
    try:
        fix = await _target(run["target"]).propose_fix(run)
    except (llm.LLMError, TargetError) as e:
        raise HTTPException(503, f"The fix writer is busy right now ({str(e)[:80]}). Try again in a moment.")
    fix["new_rules"] = _clean_rules(fix.get("new_rules") or [])
    run["fix"] = fix
    store.save_run(run)
    return fix


class PromoteReq(BaseModel):
    note: str = Field("", max_length=300)


@app.post("/api/runs/{run_id}/promote")
async def promote(run_id: str, body: PromoteReq, x_admin_key: str | None = Header(None)):
    """An operator makes a fix live. Only a candidate that held on replay can be promoted."""
    require_admin(x_admin_key)
    run = _finished(run_id)
    if run["hardening"].get("kind") != "candidate":
        raise HTTPException(400, "Promote a replay that ran a candidate fix.")
    if run.get("verdict") == "compromised":
        raise HTTPException(409, "This fix didn't hold. Change it and replay before promoting.")
    if run.get("promoted"):
        raise HTTPException(409, f"Already promoted as v{run['promoted']}.")
    try:
        res = await _target(run["target"]).promote(run["hardening"], run_id, body.note or None)
    except TargetError as e:
        raise HTTPException(503, str(e))
    run["promoted"] = res["version"]
    store.save_run(run)
    return res


# ---- live human calls ------------------------------------------------------------------------------------------------
class LiveStart(BaseModel):
    target: str = "saakshi"
    environment: Env = "none"
    intensity: Intensity = "medium"
    hardening: Literal["live", "original"] = "live"
    shield: bool = False
    language: Lang = "hi-IN"


@app.post("/api/live")
async def live_start(body: LiveStart):
    t = _target(body.target)
    hardening = await _hardening(t, body.hardening, False)
    try:
        return await engine.start_live(t, body.environment, body.intensity, hardening, body.shield,
                                       body.language if body.language in t.languages else t.languages[0])
    except engine.Busy:
        raise HTTPException(429, "Too many live calls right now. Try again in a few minutes.")
    except TargetError as e:
        raise HTTPException(503, str(e))


@app.post("/api/live/{session_id}/turn")
async def live_turn(session_id: str, audio_file: UploadFile | None = File(None),
                    text: str | None = Form(None, max_length=600), language: Lang = Form("en-IN"),
                    voice: str | None = Form(None, max_length=20), x_run_owner: str | None = Header(None)):
    if not engine.is_owner(session_id, x_run_owner):
        raise HTTPException(403, "This live call belongs to someone else.")
    wav = await security.read_wav(audio_file) if audio_file else None
    if wav is None and not (text or "").strip():
        raise HTTPException(400, "Send audio_file or text.")
    if voice and voice not in {p.get("voice") for t in TARGETS.values() for p in t.personas.values()} | {"Vikrant"}:
        raise HTTPException(400, "Unknown voice.")
    try:
        return await engine.live_turn(session_id, wav=wav, text=text, language=language, voice=voice)
    except KeyError:
        raise HTTPException(404, "Live call not found or already ended.")
    except TargetError as e:
        raise HTTPException(503, str(e))


@app.post("/api/live/{session_id}/end")
async def live_end(session_id: str, x_run_owner: str | None = Header(None)):
    if not engine.is_owner(session_id, x_run_owner):
        raise HTTPException(403, "This live call belongs to someone else.")
    run = await engine.end_live(session_id)
    if not run:
        raise HTTPException(404, "Live call not found.")
    return engine.public_run(run)


# ---- static ------------------------------------------------------------------------------------------------------------
app.mount("/audio", StaticFiles(directory=settings.audio_dir), name="audio")

if settings.web_dist.exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def spa(path: str):
        f = (settings.web_dist / path).resolve()
        if path and f.is_file() and settings.web_dist.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(settings.web_dist / "index.html")
