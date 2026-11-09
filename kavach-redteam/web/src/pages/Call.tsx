import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, creds, streamRun, type CallEvent, type Clip, type Run, type ShieldTurn, type ToolEvent, type Verdict } from "../api";
import { targetOf, useMeta } from "../App";
import { Composure, StatusTag, ToolLine } from "../components/bits";
import { FixFlow, ReplayCompare } from "../components/FixFlow";
import { Scope } from "../components/Scope";
import { Spoken } from "../components/Spoken";
import { ENV_LABEL, VERDICT_WORD, isDeva, pad, scoreColor } from "../lib/format";
import { player } from "../lib/player";
import "./call.css";
import "./callstage.css";

type LiveTurn = {
  n: number; tactic?: string; tactic_label?: string; thinking?: string; emotion?: string; intensity?: number;
  said?: string; caller_audio?: Clip; heard?: string; drift?: number | null; tools: ToolEvent[];
  bot?: string; bot_audio?: Clip; interrupted?: boolean; verdict?: Verdict; shield?: NonNullable<ShieldTurn>;
  phase: "move" | "caller" | "hearing" | "thinking" | "bot" | "done";
};

type State = {
  greeting?: { text: string; audio: Clip };
  turns: LiveTurn[];
  planning: number | null;
  speaking: { who: "caller" | "bot"; n: number } | null;
  composure: number;
  achieved: number | null;
  ended: Run | null;
  error: string | null;
  targetVersion?: number;
  toolGate?: boolean;
  shieldMode?: "native" | "proxy" | null;
  shieldRisk: number;
  hungup: "agent" | "shield" | null;
  judging: boolean;
};

const initial: State = { turns: [], planning: null, speaking: null, composure: 100, achieved: null, ended: null, error: null,
  shieldRisk: 0, hungup: null, judging: false };

export default function Call() {
  const { id = "" } = useParams();
  return <CallView key={id} id={id} />;          // a new call starts from a clean slate
}

/** The live call. Embedded (in the demo) it has no end sheet and reports the finished run to onEnded. */
export function CallView({ id, embedded = false, onEnded }: { id: string; embedded?: boolean; onEnded?: (run: Run) => void }) {
  const meta = useMeta();
  const nav = useNavigate();
  const endedRef = useRef(onEnded);
  endedRef.current = onEnded;
  const [run, setRun] = useState<Run | null>(null);
  const [st, setSt] = useState<State>(initial);
  const [flash, setFlash] = useState<string | null>(null);
  const [start, setStart] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [endAt, setEndAt] = useState<number | null>(null);
  const muted = useSyncExternalStore(player.subscribe.bind(player), () => player.muted);
  const endRef = useRef<HTMLDivElement>(null);

  // header info
  useEffect(() => { api.run(id).then(setRun).catch(() => {}); }, [id]);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, []);

  // event queue → "director" that paces the call to the audio
  useEffect(() => {
    let cancelled = false;
    const queue: CallEvent[] = [];
    let ended = false;
    let wake: (() => void) | null = null;
    const push = () => { const w = wake; wake = null; w?.(); };

    const close = streamRun(id, (e) => { queue.push(e); push(); }, () => { ended = true; push(); });

    const next = async (): Promise<CallEvent | null> => {
      while (!queue.length) {
        if (ended || cancelled) return null;
        await new Promise<void>((r) => (wake = r));
      }
      return queue.shift()!;
    };
    const patchTurn = (n: number, f: (t: LiveTurn) => LiveTurn) =>
      setSt((s) => ({ ...s, turns: s.turns.map((t) => (t.n === n ? f(t) : t)) }));

    (async () => {
      let sawAny = false;
      for (;;) {
        const ev = await next();
        if (!ev || cancelled) break;
        sawAny = true;
        switch (ev.type) {
          case "call.connected":
            setStart(Date.now());
            setSt((s) => ({ ...s, greeting: { text: ev.bot, audio: ev.audio }, targetVersion: ev.target_version, toolGate: ev.tool_gate,
              shieldMode: ev.shield_mode, speaking: { who: "bot", n: 0 } }));
            await player.play(ev.audio.url, "bot");
            setSt((s) => ({ ...s, speaking: null }));
            break;
          case "caller.planning":
            setSt((s) => ({ ...s, planning: ev.n }));
            break;
          case "caller.move":
            setSt((s) => ({
              ...s, planning: null,
              turns: [...s.turns, { n: ev.n, tactic: ev.tactic, tactic_label: ev.tactic_label, thinking: ev.thinking, emotion: ev.emotion, intensity: ev.intensity, tools: [], phase: "move" }],
            }));
            break;
          case "caller.spoke":
            patchTurn(ev.n, (t) => ({ ...t, said: ev.text, caller_audio: ev.audio, phase: "caller" }));
            setSt((s) => ({ ...s, speaking: { who: "caller", n: ev.n } }));
            await player.play(ev.audio.url, "caller");
            setSt((s) => ({ ...s, speaking: null }));
            patchTurn(ev.n, (t) => ({ ...t, phase: "hearing" }));
            break;
          case "bot.heard":
            patchTurn(ev.n, (t) => ({ ...t, heard: ev.text, drift: ev.drift, phase: "thinking" }));
            break;
          case "shield.inbound":
            patchTurn(ev.n, (t) => ({ ...t, shield: { ...t.shield, inbound: { decision: ev.decision, risk: ev.risk, turn_risk: ev.turn_risk, signals: ev.signals ?? [], claims: ev.claims ?? [] } } }));
            setSt((s) => ({ ...s, shieldRisk: ev.risk ?? s.shieldRisk }));
            break;
          case "shield.outbound":
            patchTurn(ev.n, (t) => ({ ...t, shield: { ...t.shield, outbound: { decision: ev.decision, violations: ev.violations ?? [], original: ev.original } } }));
            break;
          case "shield.action":
            patchTurn(ev.n, (t) => ({ ...t, shield: { ...t.shield, actions: [...(t.shield?.actions ?? []), { name: ev.name, decision: ev.decision, reason: ev.reason }] } }));
            break;
          case "call.hungup":
            setSt((s) => ({ ...s, hungup: ev.by }));
            break;
          case "judging":
            setSt((s) => ({ ...s, judging: true, planning: null }));
            break;
          case "bot.acted":
            patchTurn(ev.n, (t) => ({ ...t, tools: ev.tools }));
            break;
          case "bot.spoke":
            patchTurn(ev.n, (t) => ({ ...t, bot: ev.text, bot_audio: ev.audio, interrupted: ev.interrupted, phase: "bot" }));
            setSt((s) => ({ ...s, speaking: { who: "bot", n: ev.n } }));
            await player.play(ev.audio.url, "bot");
            setSt((s) => ({ ...s, speaking: null }));
            break;
          case "verdict": {
            const v: Verdict = { status: ev.status, composure: ev.composure, note: ev.note, findings: ev.findings };
            patchTurn(ev.n, (t) => ({ ...t, verdict: v, phase: "done" }));
            setSt((s) => ({ ...s, composure: ev.composure }));
            if (ev.status === "breached") {
              setFlash(ev.findings?.[0]?.title ?? ev.note);
              setTimeout(() => setFlash(null), 2600);
              await new Promise((r) => setTimeout(r, player.muted ? 400 : 1600));
            }
            break;
          }
          case "objective.achieved":
            setSt((s) => ({ ...s, achieved: ev.n }));
            break;
          case "error":
            setSt((s) => ({ ...s, error: ev.message }));
            break;
          case "call.ended":
            setEndAt(Date.now());
            setSt((s) => ({ ...s, ended: ev.run, planning: null, judging: false }));
            api.run(id).then((r) => { setSt((s) => ({ ...s, ended: r })); endedRef.current?.(r); }).catch(() => {});   // the full run
            break;
        }
      }
      if (!sawAny && !cancelled) {
        // not live any more (e.g. server restarted, or it finished): show the stored report instead
        api.run(id).then((r) => {
          if (r.status === "running") return;
          if (endedRef.current) endedRef.current(r); else nav(`/simulations/${id}`, { replace: true });
        }).catch(() => {});
      }
    })();

    return () => { cancelled = true; close(); push(); player.stop(); };
  }, [id, nav]);

  // keep the newest line in view
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [st.turns.length, st.speaking, st.planning, st.ended]);

  const target = targetOf(meta, run);
  const p = run && target?.personas[run.persona];
  const elapsed = start ? Math.max(0, Math.floor(((endAt ?? now) - start) / 1000)) : 0;
  const live = !st.ended;
  const callerName = p?.name.replace(/^The /, "") ?? "Caller";
  const botName = run?.agent_name ?? target?.agent ?? "Agent";
  const mine = !!(run && (creds.owner(run.id) || meta?.operator));
  const speaking = st.speaking?.who;
  const last = st.turns[st.turns.length - 1];
  const phase: Phase = st.error ? "error" : st.ended ? "ended" : st.judging ? "judging" : speaking ? speaking
    : st.planning ? "planning" : last?.phase === "hearing" ? "hearing" : last?.phase === "thinking" ? "thinking"
    : !st.greeting ? "dialling" : "idle";
  // the big caption: what is being said right now (or the last thing said)
  const spokeTurn = st.speaking ? st.turns.find((t) => t.n === st.speaking!.n) : null;
  const captionWho = st.speaking?.who ?? null;
  const captionText = st.speaking
    ? (st.speaking.n === 0 ? st.greeting?.text : st.speaking.who === "caller" ? spokeTurn?.said : spokeTurn?.bot) ?? ""
    : "";
  const captionKey = st.speaking ? `${st.speaking.who}-${st.speaking.n}` : "none";

  return (
    <div className={`call ${embedded ? "embedded" : ""} ${flash ? "shake" : ""}`}>
      <header className="call-bar">
        <Link to="/arena" className="call-back" onClick={() => player.stop()}>← <span>Kavach</span></Link>
        <div className="call-title">
          <span className="c-ember">{callerName}</span>
          <span className="faint"> calls </span>
          <span className="c-ice">{botName} <span className="mono" style={{ fontSize: 13 }}>{run?.hardening?.kind === "candidate" ? "candidate fix" : `v${st.targetVersion ?? run?.target_version ?? "…"}`}</span></span>
          {run?.mode === "replay" && <span className="tag neutral" style={{ marginLeft: 10 }}>exact replay</span>}
          {run?.shield && <span className="tag shieldtag" style={{ marginLeft: 10 }}>⛨ Kavach Shield</span>}
        </div>
        <div className="call-meta mono">
          {live ? <span className="tag running">live</span> : <span className="tag neutral">ended</span>}
          {live && mine && <button className="call-mute" onClick={() => api.stop(id).catch(() => {})}>hang up</button>}
          <span>{pad(Math.floor(elapsed / 60))}:{pad(elapsed % 60)}</span>
          <button className="call-mute" onClick={() => player.setMuted(!muted)} title={muted ? "Turn sound on" : "Fast mode: skip audio"}>
            {muted ? "sound off" : "sound on"}
          </button>
        </div>
      </header>

      <div className="call-grid">
        <main className="stage">
          <div className="stage-top">
            <div className="pods">
              <Pod side="caller" on={speaking === "caller"} initials={initials(callerName)} name={callerName}
                sub={<>Gnani Timbre · “{run?.voice ?? "…"}”</>}
                chip={run && run.environment !== "none" ? `${ENV_LABEL[run.environment]} · ${run.intensity}` : "clean line"} />
              <div className="pod-mid">
                <span className={`phase ${phase}`}><i />{PHASE_LABEL[phase](callerName, botName)}</span>
                <Scope height={120} />
                <ol className="path">
                  {PATH.filter((x) => x.k !== "shield" || run?.shield).map((x) => (
                    <li key={x.k} className={x.lit.includes(phase) ? "lit" : ""}>{x.k === "line" && run && run.environment !== "none" ? `Phone line · ${ENV_LABEL[run.environment]}` : x.label}</li>
                  ))}
                </ol>
              </div>
              <Pod side="bot" on={speaking === "bot"} initials={initials(botName)} name={botName}
                sub={<>{run?.hardening?.kind === "candidate" ? "candidate fix" : `v${st.targetVersion ?? run?.target_version ?? "…"}`} · Timbre “{meta?.models.bot_voice ?? "Nalini"}”</>}
                chip={run?.shield ? "⛨ Kavach Shield on" : "no Shield"} shield={!!run?.shield} />
            </div>
            {st.ended ? (
              <div className={`caption verdict ${st.ended.verdict ?? ""}`}>
                <span className="caption-who">Verdict · {st.ended.turn_count ?? st.turns.length} turn{(st.ended.turn_count ?? st.turns.length) === 1 ? "" : "s"}</span>
                <div className="verdict-band">
                  <p>{st.ended.verdict === "compromised" ? `Broken in ${st.ended.broke_at ?? "?"} turn${st.ended.broke_at === 1 ? "" : "s"}.`
                    : st.ended.verdict === "resilient" ? (run?.shield ? "It held. The Shield stopped it." : "It held.")
                    : st.ended.verdict === "at_risk" ? "It bent, but held." : "The call didn't finish."}</p>
                  {st.ended.score != null && <span className="vb-score">{st.ended.score}<small>/100</small></span>}
                </div>
              </div>
            ) : (
            <div className={`caption ${captionWho ?? "idle"}`}>
              <span className="caption-who">{captionWho === "caller" ? callerName : captionWho === "bot" ? botName : ""}</span>
              <p className={isDeva(captionText) ? "deva" : ""}>
                {captionText ? <Spoken key={captionKey} text={captionText} active={!!captionWho} /> : <span className="faint">{PHASE_LABEL[phase](callerName, botName)}</span>}
              </p>
            </div>
            )}
          </div>

          <div className="script">
            {st.greeting && (
              <div className="bub bot">
                <span className="bub-who">{botName} · opening</span>
                <p className={isDeva(st.greeting.text) ? "deva" : ""}>{st.greeting.text}</p>
              </div>
            )}
            {!st.greeting && !st.error && <p className="faint mono dial">Dialling {target?.agent ?? "the agent"}<span className="dots" /></p>}

            {st.turns.map((t) => (
              <TurnBlock key={t.n} t={t} speaking={st.speaking} callerName={callerName} botName={botName} />
            ))}

            {st.planning && (
              <div className="planning">
                <span className="turn-n">{pad(st.planning)}</span>
                <span className="mono faint">{callerName} is choosing a tactic<span className="dots" /></span>
              </div>
            )}

            {st.hungup && <p className="mono small" style={{ marginTop: 18 }}>{st.hungup === "shield"
              ? <span className="c-ice">⛨ Kavach Shield ended the call: the risk was too high to continue.</span>
              : <span className="faint">{botName} ended the call.</span>}</p>}
            {st.judging && <p className="faint mono dial" style={{ marginTop: 18 }}>Checking what ended up on the record and auditing the call<span className="dots" /></p>}
            {st.error && <p className="error-line" style={{ marginTop: 24 }}>Call failed: {st.error}</p>}

            <AnimatePresence>
              {st.ended && !embedded && <EndSheet run={st.ended} />}
            </AnimatePresence>
            <div ref={endRef} style={{ height: 40 }} />
          </div>
        </main>

        <aside className="rail">
          <Composure value={st.composure} label={`${botName} composure`} />
          {run?.shield && (
            <div className="rail-block">
              <p className="eyebrow">Kavach Shield · call risk</p>
              <div className="shield-meter"><i style={{ width: `${st.shieldRisk}%` }} /><span className="num">{st.shieldRisk}</span></div>
              <p className="faint mono small">{st.shieldMode === "native" || (!st.shieldMode && run?.target === "saakshi") ? `inside ${botName}, via the Shield API` : "in front of the agent (proxy)"}</p>
            </div>
          )}

          <div className="rail-block">
            <p className="eyebrow">Objective</p>
            <p className="rail-objective">{run?.objective_name ?? "…"}</p>
            {run?.breaks_if && <p className="faint small" style={{ margin: "6px 0" }}>{run.breaks_if}</p>}
            <p className={st.achieved ? "c-breach mono small" : "faint mono small"}>
              {st.achieved ? `achieved on turn ${st.achieved}` : st.ended ? "not achieved" : "in play"}
            </p>
          </div>

          <div className="rail-block">
            <p className="eyebrow">Tactics</p>
            <ol className="tactics">
              {st.turns.map((t) => (
                <li key={t.n} className={`${t.verdict?.status ?? "pending"} ${t.phase !== "done" ? "now" : ""}`}>
                  <span className="t-dot" />
                  <div>
                    <span className="t-name">{t.tactic_label}</span>
                    {t.thinking && <span className="t-why">{t.thinking}</span>}
                  </div>
                </li>
              ))}
              {!st.turns.length && <li className="pending"><span className="t-dot" /><div className="faint">Waiting for the first move</div></li>}
            </ol>
          </div>
        </aside>
      </div>

      <AnimatePresence>
        {flash && (
          <>
            <motion.div className="flash" initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 0.6] }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }} />
            <motion.div className="stamp" initial={{ opacity: 0, scale: 1.25, rotate: -4 }} animate={{ opacity: 1, scale: 1, rotate: -4 }} exit={{ opacity: 0 }} transition={{ type: "spring", stiffness: 300, damping: 18 }}>
              <div><b>Breached</b><span>{flash}</span></div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function TurnBlock({ t, speaking, callerName, botName }: {
  t: LiveTurn; speaking: State["speaking"]; callerName: string; botName: string;
}) {
  const callerActive = speaking?.who === "caller" && speaking.n === t.n;
  const botActive = speaking?.who === "bot" && speaking.n === t.n;
  const blocked = (t.shield?.outbound && t.shield.outbound.decision !== "allow") || t.shield?.actions?.some((a) => a.decision !== "allow");
  return (
    <motion.section className={`turn ${t.verdict?.status ?? ""}`} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
      <div className="turn-head">
        <span className="turn-n">Turn {pad(t.n)}</span>
        {t.tactic_label && <span className="turn-tactic">{t.tactic_label}</span>}
        {t.emotion && <span className="turn-mood">{t.emotion} · pressure {t.intensity}</span>}
        {t.verdict && <span className="turn-verdict"><StatusTag status={t.verdict.status} /></span>}
      </div>

      {t.said && (
        <div className={`bub caller ${callerActive ? "on" : ""}`}>
          <span className="bub-who">{callerName}</span>
          <p className={isDeva(t.said) ? "deva" : ""}><Spoken text={t.said} active={callerActive} /></p>
          {t.phase === "hearing" && <p className="bub-heard"><b>Gnani Prisma</b> transcribing<span className="dots" /></p>}
          {t.heard != null && (
            <p className="bub-heard"><b>Prisma heard</b> {t.heard || <span className="c-amber">[nothing intelligible]</span>}
              {t.drift != null && t.drift > 0.2 && <span className="tag contained" style={{ marginLeft: 8 }}>{Math.round(t.drift * 100)}% misheard</span>}</p>
          )}
        </div>
      )}

      {t.shield?.inbound && (
        <div className="sh-row in">
          <span className="sh-badge">⛨ Shield</span>
          <span className={`shield-dec ${t.shield.inbound.decision}`}>{t.shield.inbound.decision}</span>
          <span className="shield-risk">risk <i><b style={{ width: `${t.shield.inbound.risk}%` }} /></i> {t.shield.inbound.risk}</span>
          {t.shield.inbound.signals.map((x, i) => <span key={i} className="shield-sig" title={`${x.detail} · "${x.evidence}"`}>{x.kind.replace(/_/g, " ")}</span>)}
          {!t.shield.inbound.signals.length && <span className="faint">no manipulation signals</span>}
        </div>
      )}

      {t.phase === "thinking" && !t.bot && <div className="bub bot typing"><span className="bub-who">{botName}</span><p><span className="dots" /></p></div>}

      {t.bot && (
        <div className={`bub bot ${botActive ? "on" : ""}`}>
          <span className="bub-who">{botName}</span>
          <p className={isDeva(t.bot) ? "deva" : ""}><Spoken text={t.bot} active={botActive} cut={t.interrupted} /></p>
        </div>
      )}

      {t.tools.length > 0 && <div className="sys-row">{t.tools.map((x, i) => <ToolLine key={i} t={x} />)}</div>}

      {blocked && (
        <div className="sh-row out">
          <span className="sh-badge">⛨ Shield</span>
          {t.shield?.outbound && t.shield.outbound.decision !== "allow" && <>
            <span className={`shield-dec ${t.shield.outbound.decision}`}>{t.shield.outbound.decision === "block" ? "blocked reply" : "rewrote reply"}</span>
            {t.shield.outbound.violations.map((v, i) => <span key={i} className="shield-sig">{v.label}</span>)}
            {t.shield.outbound.original && <p className="struck small" style={{ flexBasis: "100%", margin: "4px 0 0" }}>{t.shield.outbound.original}</p>}
          </>}
          {t.shield?.actions?.filter((a) => a.decision !== "allow").map((a, i) => (
            <span key={i} className="sh-act"><span className="shield-dec deny">denied {a.name.replace(/_/g, " ")}</span><span className="faint">{a.reason}</span></span>
          ))}
        </div>
      )}

      {t.verdict && (
        <div className={`judge ${t.verdict.status}`}>
          <span className="judge-k">Judge</span><span>{t.verdict.note}</span>
        </div>
      )}
    </motion.section>
  );
}

type Phase = "dialling" | "idle" | "planning" | "caller" | "hearing" | "thinking" | "bot" | "judging" | "ended" | "error";
const PHASE_LABEL: Record<Phase, (c: string, b: string) => string> = {
  dialling: (_c, b) => `Dialling ${b}…`, idle: () => "On the line", planning: (c) => `${c} is choosing a tactic…`,
  caller: (c) => `${c} is speaking`, hearing: () => "Gnani Prisma is transcribing…", thinking: (_c, b) => `${b} is thinking…`,
  bot: (_c, b) => `${b} is speaking`, judging: () => "Checking the ground truth…", ended: () => "Call ended", error: () => "Call failed",
};
const PATH: { k: string; label: string; lit: Phase[] }[] = [
  { k: "timbre", label: "Gnani Timbre", lit: ["caller"] },
  { k: "line", label: "Phone line", lit: ["caller", "bot"] },
  { k: "prisma", label: "Gnani Prisma", lit: ["hearing"] },
  { k: "shield", label: "Kavach Shield", lit: ["hearing", "thinking"] },
  { k: "agent", label: "Agent", lit: ["thinking", "bot"] },
];
const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

function Pod({ side, on, initials: ini, name, sub, chip, shield }: {
  side: "caller" | "bot"; on: boolean; initials: string; name: string; sub: ReactNode; chip: string; shield?: boolean;
}) {
  return (
    <div className={`pod ${side} ${on ? "on" : ""}`}>
      <span className="pod-av"><span className="ring" /><span className="ring r2" /><b>{ini}</b>{shield && <span className="pod-shield">⛨</span>}</span>
      <div className="pod-txt">
        <span className="pod-role">{side === "caller" ? "Attacker" : "Target agent"}</span>
        <span className="pod-name">{name}</span>
        <span className="pod-sub">{sub}</span>
        <span className={`pod-chip ${shield ? "shield" : ""}`}>{chip}</span>
      </div>
    </div>
  );
}

function EndSheet({ run }: { run: Run }) {
  const v = run.verdict ?? "resilient";
  const headline = v === "compromised"
    ? <>Broken in <em>{run.broke_at} turn{run.broke_at === 1 ? "" : "s"}</em>.</>
    : v === "incomplete" ? <>The call <em>didn't finish</em>.</>
    : v === "at_risk" ? <>It bent, <em>but held</em>.</> : <>It <em>held</em>.</>;
  return (
    <motion.section className="endsheet" initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: [0.2, 0.7, 0.1, 1] }}>
      <div className="end-top">
        <div>
          <p className="eyebrow">Call ended · {run.turn_count} turns</p>
          <h2 className={`h1 end-head ${v}`}>{headline}</h2>
        </div>
        <div className="end-score">
          <span className="num" style={{ color: scoreColor(run.score) }}>{run.score ?? "—"}</span>
          <span className="eyebrow">resistance score · {VERDICT_WORD[v]}</span>
        </div>
      </div>

      {v === "incomplete" && <p className="muted" style={{ maxWidth: "70ch", marginTop: 18 }}>No verdict: {run.error ?? "the call stopped early"}. Nothing here counts as a pass. Try the call again in a minute.</p>}
      {run.summary && <p className="muted" style={{ maxWidth: "70ch", marginTop: 18 }}>{run.summary}</p>}
      {run.findings.length > 0 && (
        <ul className="findings" style={{ marginTop: 28 }}>
          {run.findings.map((f) => (
            <li key={f.id}>
              <div><span className={`tag ${f.kind === "contained" ? "contained" : f.severity}`}>{f.kind === "contained" ? "contained" : f.severity}</span><p className="mono faint small" style={{ margin: "8px 0 0" }}>turn {f.turn}</p></div>
              <div><p className="ft">{f.title}</p><p className="fe">{f.evidence}</p></div>
            </li>
          ))}
        </ul>
      )}
      {run.reveal?.facts?.length ? (
        <div className="reveal"><p className="eyebrow">Sandbox secrets, revealed after the verdict</p>{run.reveal.facts.map((x, i) => <p key={i} className="small muted" style={{ margin: "4px 0 0" }}>{x}</p>)}</div>
      ) : null}

      <div className="end-actions">
        {run.mode !== "replay" && run.status !== "error" && <FixFlow run={run} />}
        {run.mode === "replay" && <ReplayCompare run={run} />}
        <div className="row" style={{ flexWrap: "wrap", marginTop: 28 }}>
          <Link to={`/simulations/${run.id}`} className="btn btn-ghost">Open full report</Link>
          <Link to="/arena" className="btn btn-ghost">New attack</Link>
        </div>
      </div>
    </motion.section>
  );
}
