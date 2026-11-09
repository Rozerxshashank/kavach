"""Orchestrates calls against any target: adaptive attacks, exact replays, and live human calls.

One turn of an attack:

  attacker LLM ─► Timbre (caller voice, emotion-driven speed)
              ─► + acoustic environment (sirens, traffic, crowd …)
              ─► Prisma  (what the agent actually hears)
              ─► [Kavach Shield, inbound]  ─► the agent under test  ─► [Kavach Shield, outbound]
              ─► the agent's voice (its own audio, or Timbre)
              ─► Prisma  (what the attacker hears)  ║  judge (ground truth + canaries + auditor)
              ─► attacker plans the next move (may barge in, if the agent supports it)

With the Shield on, Kavach runs its own runtime guard in front of the agent ("proxy mode"), so the same attack can be
compared with and without it. Every step streams to the UI as an event.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import audio, gnani, judge, store
from .attacker import Attacker, AttackMove
from .config import settings
from .security import sign
from .shield import core as shield_core
from .shield.policies import BUILTIN as SHIELD_POLICIES
from .targets import Reply, Target, TargetError
from .targets import get as get_target

RUN_SECONDS = 7 * 60


class Busy(Exception):
    pass


class Limit(Exception):
    pass


# ---- live event fan-out ----------------------------------------------------------
@dataclass
class RunHandle:
    run: dict
    events: list[dict] = field(default_factory=list)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    done: bool = False
    stop: bool = False
    task: asyncio.Task | None = None

    async def emit(self, kind: str, data: dict | None = None) -> None:
        ev = {"seq": len(self.events), "type": kind, "t": time.time(), **(data or {})}
        async with self.cond:
            self.events.append(ev)
            self.cond.notify_all()

    async def finish(self) -> None:
        async with self.cond:
            self.done = True
            self.cond.notify_all()

    async def stream(self, start: int = 0):
        i = start
        while True:
            async with self.cond:
                while i >= len(self.events) and not self.done:
                    await self.cond.wait()
                batch = self.events[i:]
                finished = self.done
            for ev in batch:
                yield ev
            i += len(batch)
            if finished and i >= len(self.events):
                return


RUNS: dict[str, RunHandle] = {}


def running() -> str | None:
    return next((k for k, h in RUNS.items() if not h.done and h.run["mode"] in ("campaign", "replay")), None)


def quota() -> dict:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = store.runs_since(start)
    return {"daily": settings.daily_attacks, "used": used, "left": max(0, settings.daily_attacks - used)}


def owner_token(run_id: str) -> str:
    return sign("run-owner", run_id)[:32]


def is_owner(run_id: str, token: str | None) -> bool:
    import hmac
    return bool(token) and hmac.compare_digest(owner_token(run_id), token or "")


# ---- helpers ---------------------------------------------------------------------
def _clip(run_id: str, name: str, wav: bytes) -> dict:
    folder = settings.audio_dir / run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(wav)
    return {"url": f"/audio/{run_id}/{name}", "duration": audio.duration_s(wav), "peaks": audio.peaks(wav)}


def _audio_path(url: str) -> Path:
    p = (settings.audio_dir / url.removeprefix("/audio/")).resolve()
    if settings.audio_dir.resolve() not in p.parents:
        raise ValueError("audio path outside the audio folder")
    return p


def _drift(said: str, heard: str, language: str) -> float | None:
    """Fraction of words Prisma got differently (Latin-script lines only; scripts differ otherwise)."""
    norm = lambda s: re.findall(r"[a-z0-9]+", s.lower())
    a, b = norm(said), norm(heard)
    if language != "en-IN" or len(a) < 3:
        return None
    return round(1 - difflib.SequenceMatcher(None, a, b).ratio(), 3)


def new_run(mode: str, *, target: Target, persona: str, objective: str, language: str | None, environment: str,
            intensity: str, max_turns: int, hardening: dict, shield: bool, parent: str | None = None,
            world: dict | None = None) -> RunHandle:
    p = target.personas.get(persona) or {"name": "You", "voice": None, "language": "en-IN"}
    o = target.objectives.get(objective) or {"name": "Freestyle", "goal": "", "breaks_if": ""}
    run = {
        "id": ("run_" if mode != "live" else "live_") + uuid.uuid4().hex[:10],
        "created_at": store.now(),
        "mode": mode, "status": "running",
        "target": target.id, "target_name": target.name, "agent_name": target.agent,
        "persona": persona, "persona_name": p["name"], "voice": p.get("voice"),
        "objective": objective, "objective_name": o["name"], "breaks_if": o.get("breaks_if", ""),
        "language": language or p.get("language", "en-IN"),
        "environment": environment, "intensity": intensity, "max_turns": max_turns,
        "hardening": hardening, "shield": shield,
        # kept for older screens: the version the agent ran
        "target_version": hardening.get("version"), "target_label": hardening.get("title", ""),
        "tool_gate": bool((hardening.get("gates") or {}).get("tool_gate")),
        "parent": parent, "world": world,
        "turns": [], "findings": [], "score": None, "verdict": None, "objective_achieved": False, "latency": {},
    }
    h = RunHandle(run)
    RUNS[run["id"]] = h
    store.save_run(run)
    return h


def start(h: RunHandle) -> None:
    h.task = asyncio.get_running_loop().create_task(run_campaign(h))


def _mark_ground_truth(run: dict, extra: list[dict]) -> list[dict]:
    """A break proven only at the end (the record the agent left behind) belongs to the turn where it happened:
    that turn is marked breached too, so the transcript, the turn marks and the verdict tell one story.
    Returns the turns it changed. Idempotent."""
    changed = []
    serious = [f for f in extra if f["severity"] in ("critical", "high") and f["kind"] != "contained" and f.get("turn")]
    if not serious:
        return changed
    score = judge.score([f for t in run["turns"] for f in t["verdict"]["findings"]] + extra)[0]
    for f in serious:
        t = next((x for x in run["turns"] if x["n"] == f["turn"]), None)
        if t and t["verdict"]["status"] != "breached":
            t["verdict"].update(status="breached", note=f"Ground truth: {f['title']}.",
                                composure=min(t["verdict"].get("composure", 100), score))
            changed.append(t)
    return changed


def _finalize(run: dict, extra: list[dict] | None = None) -> None:
    _mark_ground_truth(run, list(extra or []))
    findings = [f for t in run["turns"] for f in t["verdict"]["findings"]] + list(extra or [])
    run["findings"] = findings
    run["score"], run["verdict"] = judge.score(findings)
    if run.get("status") == "error" and run["verdict"] != "compromised":
        # an unfinished call never counts as a pass; a break proven before the failure still counts
        run["score"], run["verdict"] = None, "incomplete"
    lat: dict[str, list[float]] = {}
    for t in run["turns"]:
        for k, v in (t.get("latency") or {}).items():
            lat.setdefault(k, []).append(v)
    run["latency"] = {k: round(sum(v) / len(v), 1) for k, v in lat.items() if v}
    run["tactics_used"] = sorted({t["tactic"] for t in run["turns"] if t.get("tactic")})
    run["turn_count"] = len(run["turns"])
    breaking = next((t for t in run["turns"] if t["verdict"]["status"] == "breached"), None)
    run["broke_at"] = breaking["n"] if breaking else (extra[0]["turn"] if extra and any(
        f["severity"] in ("critical", "high") and f["kind"] != "contained" for f in extra) else None)
    run["breaking_tactic"] = breaking["tactic"] if breaking else None


def public_run(run: dict) -> dict:
    """While a run is live the sandbox's secrets stay hidden; afterwards they are part of the evidence."""
    out = dict(run)
    if run.get("status") == "running":
        out.pop("world", None)
    return out


# ---- an attack or a replay -----------------------------------------------------------
async def run_campaign(h: RunHandle) -> None:
    run = h.run
    extra: list[dict] = []
    try:
        extra = await asyncio.wait_for(_campaign(h), timeout=RUN_SECONDS)
        run["status"] = "stopped" if h.stop else "complete"
    except asyncio.TimeoutError:
        run["status"], run["error"] = "error", "The call ran past its time limit and was ended."
        await h.emit("error", {"message": run["error"]})
    except TargetError as exc:
        run["status"], run["error"] = "error", str(exc)
        await h.emit("error", {"message": run["error"]})
    except (gnani.GnaniError, Exception) as exc:  # surface the failure to the UI rather than hanging
        traceback.print_exc()
        run["status"] = "error"
        run["error"] = ("A speech or model service was unavailable. Try again in a minute."
                        if isinstance(exc, gnani.GnaniError) else f"{type(exc).__name__}: {str(exc)[:200]}")
        await h.emit("error", {"message": run["error"]})
    finally:
        _finalize(run, extra)
        store.save_run(run)
        await h.emit("call.ended", {"run": {k: v for k, v in public_run(run).items() if k != "turns"}})
        await h.finish()


async def _campaign(h: RunHandle) -> list[dict]:
    run = h.run
    target = get_target(run["target"])
    native = bool(run["shield"] and target.shield_native)
    session = await target.open(language=run["language"], hardening=run["hardening"], world=run.get("world"),
                                shield=native)
    script: list[dict] = []
    if run["mode"] == "replay" and run.get("parent"):
        parent = store.get_run(run["parent"]) or {}
        script = [t for t in parent.get("turns", []) if t.get("caller_audio")]
        run["max_turns"] = len(script)
    shield = None
    try:
        opening = await session.open()
        run["world"] = session.world or run.get("world")
        store.save_run(run)
        if run["shield"] and not native:                  # proxy mode: Kavach runs the Shield in front of the agent
            shield = shield_core.open_session(SHIELD_POLICIES[target.shield_policy], "internal",
                                              language=run["language"], secrets=target.shield_secrets(run["world"]))
            session.attach_action_guard(lambda name: (lambda r: (r["decision"] == "allow", r["reason"]))(
                shield_core.action(shield, name)))
        p = target.personas[run["persona"]]
        attacker = Attacker(p, target.objectives[run["objective"]], run["language"], target.scenario(run["world"]),
                            target.tactics(), target.attacker_fill(run["world"]), check=target.check_line)
        open_clip = _clip(run["id"], "00_bot.wav", opening.audio or (await gnani.timbre_speak(
            opening.text, voice=target.voice, language=opening.language)).audio)
        attacker.heard(opening.text)
        await h.emit("call.connected", {"bot": opening.text, "audio": open_clip, "bot_name": target.agent,
                                        "target": target.id, "target_version": run["hardening"].get("version"),
                                        "hardening": run["hardening"]["title"], "shield": run["shield"],
                                        "shield_mode": "native" if native else "proxy" if shield else None})

        move: AttackMove | None = None
        if not script:
            await h.emit("caller.planning", {"n": 1})
            move = await attacker.next_move(1, run["max_turns"])

        for n in range(1, run["max_turns"] + 1):
            if h.stop:
                break
            lat: dict[str, float] = {}
            if script:
                src = script[n - 1]
                move = AttackMove(src["tactic"], src.get("thinking", ""), src["said"], src["said_language"],
                                  src.get("emotion") or "urgent", src.get("intensity") or 50)
            assert move is not None
            await h.emit("caller.move", {"n": n, **move.to_dict(),
                                         "tactic_label": target.tactics().get(move.tactic, {}).get("label", move.tactic)})

            # 1. the caller speaks (Timbre) into a noisy line
            if script:
                mixed = _audio_path(script[n - 1]["caller_audio"]["url"]).read_bytes()
                lat["timbre_caller_ms"] = 0
            else:
                speech = await gnani.timbre_speak(move.utterance, voice=run["voice"], language=move.language,
                                                  speed=attacker.speed_for(move))
                lat["timbre_caller_ms"] = round(speech.latency_ms)
                mixed = audio.mix_environment(speech.audio, run["environment"], run["intensity"], seed=n)
            caller_clip = _clip(run["id"], f"{n:02d}_caller.wav", mixed)
            await h.emit("caller.spoke", {"n": n, "text": move.utterance, "audio": caller_clip,
                                          "voice": run["voice"], "environment": run["environment"]})

            # 2. the agent hears it through Prisma
            heard = await gnani.prisma_transcribe(mixed, language=move.language)
            lat["prisma_bot_ear_ms"] = round(heard.latency_ms)
            drift = _drift(move.utterance, heard.text, move.language)
            await h.emit("bot.heard", {"n": n, "text": heard.text, "drift": drift, "model": heard.model,
                                       "latency_ms": lat["prisma_bot_ear_ms"]})

            # 3. Shield (inbound), then the agent
            shield_turn: dict | None = None
            verified_before = session.verified
            if shield:
                shield_core.set_state(shield, verified=session.verified)
                sin = await shield_core.inbound(shield, heard.text)
                lat["shield_in_ms"] = sin["latency_ms"]
                shield_turn = {"inbound": {k: sin[k] for k in ("decision", "risk", "turn_risk", "signals", "claims")}}
                await h.emit("shield.inbound", {"n": n, **shield_turn["inbound"]})
            if shield and shield_turn and shield_turn["inbound"]["decision"] == "escalate":
                reply = Reply(text=sin["say"], language=run["language"], done=True)   # the agent never hears it
            else:
                t0 = time.perf_counter()
                reply = await session.turn(heard.text, n, sin["guidance"] if shield else "")
                lat["agent_ms"] = round((time.perf_counter() - t0) * 1000)
                if native and reply.meta.get("shield"):      # the agent ran the Shield itself and reported back
                    shield_turn = reply.meta["shield"]
                    if shield_turn.get("inbound"):
                        await h.emit("shield.inbound", {"n": n, **shield_turn["inbound"]})
                    if shield_turn.get("outbound"):
                        await h.emit("shield.outbound", {"n": n, **shield_turn["outbound"]})
                    for a in shield_turn.get("actions") or []:
                        await h.emit("shield.action", {"n": n, **a})
                if shield:
                    sout = shield_core.outbound(shield, reply.text)
                    lat["shield_out_ms"] = sout["latency_ms"]
                    shield_turn["outbound"] = {k: sout[k] for k in ("decision", "violations")}  # type: ignore[index]
                    if sout["decision"] != "allow":
                        shield_turn["outbound"]["original"] = reply.text  # type: ignore[index]
                        reply.text, reply.audio = sout["text"], None
                    await h.emit("shield.outbound", {"n": n, **shield_turn["outbound"]})  # type: ignore[index]
            if reply.tools:
                await h.emit("bot.acted", {"n": n, "tools": [t.to_dict() for t in reply.tools],
                                           "verified": session.verified})

            # 4. the agent speaks; judge in parallel
            if reply.audio:
                bot_wav = reply.audio
            else:
                bs = await gnani.timbre_speak(reply.text, voice=target.voice, language=reply.language)
                lat["timbre_bot_ms"] = round(bs.latency_ms)
                bot_wav = bs.audio
            verdict = await target.judge_turn(n, heard.text, reply, verified_before, run["world"])
            achieved = target.objective_hit(run["objective"], reply, verdict, verified_before)

            # 5. the attacker hears the agent through Prisma and plans its next move
            interrupted = False
            next_move: AttackMove | None = None
            if not achieved and not reply.done and n < run["max_turns"] and not script and not h.stop:
                try:
                    ear = await gnani.prisma_transcribe(bot_wav, language=reply.language)
                    lat["prisma_attacker_ear_ms"] = round(ear.latency_ms)
                    attacker.heard(ear.text or reply.text)
                except gnani.GnaniError:
                    attacker.heard(reply.text)            # degrade gracefully: the attacker still "hears" the agent
                await h.emit("caller.planning", {"n": n + 1})
                next_move = await attacker.next_move(n + 1, run["max_turns"])
                if next_move.tactic == "barge_in" and session.supports_interruption:
                    interrupted = True
            elif script and n < len(script) and script[n].get("tactic") == "barge_in" and session.supports_interruption:
                interrupted = True
            if interrupted:
                bot_wav = audio.truncate(bot_wav, 0.42)
                session.interrupted()

            bot_clip = _clip(run["id"], f"{n:02d}_bot.wav", bot_wav)
            await h.emit("bot.spoke", {"n": n, "text": reply.text, "audio": bot_clip, "interrupted": interrupted,
                                       "language": reply.language, "intent": reply.intent})
            await h.emit("verdict", {"n": n, **verdict.to_dict(), "objective_achieved": achieved})
            run["turns"].append({
                "n": n, "tactic": move.tactic,
                "tactic_label": target.tactics().get(move.tactic, {}).get("label", move.tactic),
                "thinking": move.thinking, "emotion": move.emotion, "intensity": move.intensity,
                "said": move.utterance, "said_language": move.language, "caller_audio": caller_clip,
                "heard": heard.text, "drift": drift, "bot": reply.text, "bot_language": reply.language,
                "bot_audio": bot_clip, "interrupted": interrupted, "intent": reply.intent,
                "tools": [t.to_dict() for t in reply.tools], "verified_after": session.verified,
                "verdict": verdict.to_dict(), "latency": lat, "shield": shield_turn,
            })
            store.save_run(run)
            if achieved:
                run["objective_achieved"] = True
                await h.emit("objective.achieved", {"n": n, "objective": run["objective_name"]})
                break
            if reply.done:
                by_shield = bool(shield_turn and (shield_turn.get("inbound") or {}).get("decision") == "escalate")
                await h.emit("call.hungup", {"n": n, "by": "shield" if by_shield else "agent"})
                break
            move = next_move

        # 6. ground truth: what the agent left behind, and a whole-call audit
        await h.emit("judging", {})
        outcome = await session.outcome()
        run["outcome"] = outcome
        found, summary = await target.final_findings(run, outcome)
        run["summary"] = summary
        if shield:
            run["shield_summary"] = shield.summary()
            store.shield_call_save(shield.summary(), "internal", run["created_at"])
        extra = [f.to_dict() for f in found]
        if extra and any(f["severity"] in ("critical", "high") and f["kind"] != "contained" for f in extra):
            run["objective_achieved"] = run["objective_achieved"] or run["objective"] in ("inflate", "rubber", "vouch")
        for t in _mark_ground_truth(run, extra):                  # the live view updates that turn as well
            await h.emit("verdict", {"n": t["n"], **t["verdict"], "objective_achieved": run["objective_achieved"]})
            if run["objective_achieved"]:
                await h.emit("objective.achieved", {"n": t["n"], "objective": run["objective_name"]})
        run["reveal"] = target.reveal(run["world"])
        return extra
    finally:
        if shield:
            shield_core.SESSIONS.pop(shield.id, "internal")
        await session.close()


# ---- live: a human is the attacker -------------------------------------------------
@dataclass
class LiveSession:
    run: dict
    session: object
    target: Target
    shield: shield_core.ShieldSession | None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last: float = field(default_factory=time.time)


LIVE: dict[str, LiveSession] = {}
MAX_LIVE = 3
LIVE_TTL = 15 * 60


async def _expire_live() -> None:
    for sid in [k for k, s in LIVE.items() if time.time() - s.last > LIVE_TTL]:
        s = LIVE.pop(sid)
        await s.session.close()  # type: ignore[attr-defined]


async def start_live(target: Target, environment: str, intensity: str, hardening: dict, shield: bool,
                     language: str) -> dict:
    await _expire_live()
    if len(LIVE) >= MAX_LIVE:
        raise Busy("live")
    h = new_run("live", target=target, persona="human", objective="freestyle", language=language,
                environment=environment, intensity=intensity, max_turns=0, hardening=hardening, shield=shield)
    RUNS.pop(h.run["id"], None)
    native = bool(shield and target.shield_native)
    session = await target.open(language=language, hardening=hardening, world=None, shield=native)
    try:
        opening = await session.open()
    except Exception:
        await session.close()
        raise
    h.run["world"] = session.world
    sh = None
    if shield and not native:
        sh = shield_core.open_session(SHIELD_POLICIES[target.shield_policy], "internal", language=language,
                                      secrets=target.shield_secrets(session.world))
        session.attach_action_guard(lambda name: (lambda r: (r["decision"] == "allow", r["reason"]))(
            shield_core.action(sh, name)))
    clip = _clip(h.run["id"], "00_bot.wav", opening.audio or (await gnani.timbre_speak(
        opening.text, voice=target.voice, language=opening.language)).audio)
    LIVE[h.run["id"]] = LiveSession(h.run, session, target, sh)
    store.save_run(h.run)
    return {"id": h.run["id"], "owner": owner_token(h.run["id"]), "bot": opening.text, "audio": clip,
            "bot_name": target.agent, "target": target.id, "target_version": hardening.get("version"),
            "tool_gate": bool((hardening.get("gates") or {}).get("tool_gate")), "shield": shield}


async def live_turn(session_id: str, *, wav: bytes | None, text: str | None, language: str,
                    voice: str | None) -> dict:
    s = LIVE.get(session_id)
    if not s:
        raise KeyError(session_id)
    async with s.lock:
        s.last = time.time()
        run, session, target = s.run, s.session, s.target
        n = len(run["turns"]) + 1
        if n > 30:
            raise KeyError(session_id)
        lat: dict[str, float] = {}
        if wav is None:
            speech = await gnani.timbre_speak(text or "", voice=voice or "Vikrant", language=language)
            lat["timbre_caller_ms"] = round(speech.latency_ms)
            wav = speech.audio
        mixed = audio.mix_environment(wav, run["environment"], run["intensity"], seed=n)
        caller_clip = _clip(run["id"], f"{n:02d}_caller.wav", mixed)
        heard = await gnani.prisma_transcribe(mixed, language=language)
        lat["prisma_bot_ear_ms"] = round(heard.latency_ms)
        verified_before = session.verified  # type: ignore[attr-defined]
        shield_turn = None
        if s.shield:
            shield_core.set_state(s.shield, verified=verified_before)
            sin = await shield_core.inbound(s.shield, heard.text)
            shield_turn = {"inbound": {k: sin[k] for k in ("decision", "risk", "turn_risk", "signals", "claims")}}
        if shield_turn and shield_turn["inbound"]["decision"] == "escalate":
            reply = Reply(text=sin["say"], language=language, done=True)
        else:
            t0 = time.perf_counter()
            reply = await session.turn(heard.text, n, sin["guidance"] if s.shield else "")  # type: ignore[attr-defined]
            lat["agent_ms"] = round((time.perf_counter() - t0) * 1000)
            if reply.meta.get("shield"):
                shield_turn = reply.meta["shield"]
            if s.shield:
                sout = shield_core.outbound(s.shield, reply.text)
                shield_turn["outbound"] = {k: sout[k] for k in ("decision", "violations")}  # type: ignore[index]
                if sout["decision"] != "allow":
                    shield_turn["outbound"]["original"] = reply.text  # type: ignore[index]
                    reply.text, reply.audio = sout["text"], None
        if reply.audio:
            bot_wav = reply.audio
        else:
            bs = await gnani.timbre_speak(reply.text, voice=target.voice, language=reply.language)
            lat["timbre_bot_ms"] = round(bs.latency_ms)
            bot_wav = bs.audio
        verdict = await target.judge_turn(n, heard.text, reply, verified_before, run.get("world"))
        bot_clip = _clip(run["id"], f"{n:02d}_bot.wav", bot_wav)
        turn = {
            "n": n, "tactic": None, "tactic_label": "Human", "thinking": "", "emotion": None, "intensity": None,
            "said": text or heard.text, "said_language": language, "caller_audio": caller_clip,
            "heard": heard.text, "drift": _drift(text, heard.text, language) if text else None,
            "bot": reply.text, "bot_language": reply.language, "bot_audio": bot_clip, "interrupted": False,
            "intent": reply.intent, "tools": [t.to_dict() for t in reply.tools],
            "verified_after": session.verified,  # type: ignore[attr-defined]
            "verdict": verdict.to_dict(), "latency": lat, "shield": shield_turn,
        }
        run["turns"].append(turn)
        _finalize(run)
        store.save_run(run)
        if reply.done:
            await end_live(session_id)
        return {"turn": turn, "score": run["score"], "verdict": run["verdict"], "done": reply.done}


async def end_live(session_id: str) -> dict | None:
    s = LIVE.pop(session_id, None)
    if not s:
        return store.get_run(session_id)
    try:
        outcome = await s.session.outcome()  # type: ignore[attr-defined]
        s.run["outcome"] = outcome
        found, summary = await s.target.final_findings(s.run, outcome) if s.run["turns"] else ([], "")
        s.run["summary"] = summary
    except TargetError:
        found = []
    finally:
        await s.session.close()  # type: ignore[attr-defined]
        if s.shield:
            shield_core.SESSIONS.pop(s.shield.id, "internal")
    s.run["status"] = "complete"
    s.run["reveal"] = s.target.reveal(s.run.get("world"))
    _finalize(s.run, [f.to_dict() for f in found])
    store.save_run(s.run)
    return s.run


def recover() -> int:
    """After a restart nothing is on the line any more: close the books on interrupted runs."""
    n = 0
    for r in store.list_runs(500):
        if r.get("status") == "running":
            full = store.get_run(r["id"]) or r
            full["status"], full["error"] = "error", "The server restarted during this call."
            store.save_run(full)
            n += 1
    return n

