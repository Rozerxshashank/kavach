import { resetStream } from "../lib/util";
import { at } from "../lib/base";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, meta, type Call, type GraphData, type RedTeam, type Stats, type Worker } from "../lib/api";
import { auth } from "../lib/auth";
import { player } from "../lib/player";
import { OUTCOME_LABEL, PERSONA_LABEL, ROLE_LABEL, ago, inr, isDeva, useStream } from "../lib/util";
import { Chip, Wave } from "../components/bits";
import { TrustGraph } from "../components/TrustGraph";

export function CallQueue({ compact = false }: { compact?: boolean }) {
  const [calls, setCalls] = useState<Call[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [phoneLine, setPhoneLine] = useState(false);
  useEffect(() => { meta().then((m) => setPhoneLine(m.ready.telephony)).catch(() => {}); }, []);
  const load = useCallback(() => api.calls().then(setCalls).catch((e) => setErr(e.message)), []);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => {
    if (e.type.startsWith("call.") || e.type === "world.changed") void load();
    if (e.type === "call.turn" && e.call_id === open) void load();
  });

  const ring = async (c: Call, mode: "auto" | "human" | "phone") => {
    player.unlock();
    setErr("");
    try { await api.ring(c.id, mode); setOpen(c.id); await load(); } catch (e) { setErr((e as Error).message); }
  };

  const active = calls.filter((c) => ["queued", "callback", "ringing", "in_call"].includes(c.status));
  const done = calls.filter((c) => c.status === "done").slice(0, compact ? 6 : 30);

  return (
    <div className="queue">
      {err && <p className="error-line">{err}</p>}
      <p className="eyebrow" style={{ marginBottom: 8 }}>Confirmation calls · {active.length} open</p>
      {!active.length && <p className="small faint" style={{ padding: "6px 0 14px" }}>No calls waiting. Save a record from the worker's phone and Saakshi queues one.</p>}
      {active.map((c) => <CallRow key={c.id} c={c} open={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)} onRing={ring} phoneLine={phoneLine} />)}
      {done.length > 0 && <p className="eyebrow" style={{ margin: "18px 0 8px" }}>Finished</p>}
      {done.map((c) => <CallRow key={c.id} c={c} open={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)} onRing={ring} phoneLine={phoneLine} />)}
    </div>
  );
}

function CallRow({ c, open, onToggle, onRing, phoneLine }: { c: Call; open: boolean; onToggle: () => void; onRing: (c: Call, m: "auto" | "human" | "phone") => void; phoneLine: boolean }) {
  const canRing = ["queued", "callback"].includes(c.status);
  const persona = c.employer?.persona;
  return (
    <div className={`call-row ${open ? "open" : ""}`}>
      <div className="call-main" onClick={onToggle}>
        <div style={{ minWidth: 0 }}>
          <p className="call-who">{c.employer?.name} <span className="faint">→ {c.workers?.join(", ")}</span></p>
          <p className="small faint">
            {c.mode === "phone" ? "real phone line · " : ""}{c.entry_ids.length} record{c.entry_ids.length > 1 ? "s" : ""}{persona ? ` · simulated: ${PERSONA_LABEL[persona] ?? persona}` : ""} · {ago(c.created_at)}
          </p>
        </div>
        {c.status === "done" ? <Chip status={c.outcome === "verified" || c.outcome === "corrected" || c.outcome === "bulk" ? "verified" : c.outcome === "disputed" ? "disputed" : "neutral"} label={OUTCOME_LABEL[c.outcome ?? ""] ?? c.outcome ?? "done"} />
          : <Chip status={c.status} />}
      </div>
      {canRing && (
        <div className="row call-actions">
          {phoneLine && <button className="btn btn-sm btn-primary" onClick={() => onRing(c, "phone")} title="Dials the employer's real number through Twilio">📞 Call real number</button>}
          <button className="btn btn-sm btn-ink" onClick={() => onRing(c, "human")} title="Rings the employer phone in this browser">☎ Ring phone</button>
          {persona && <button className="btn btn-sm btn-ghost" onClick={() => onRing(c, "auto")} title="A simulated employer answers with its own Timbre voice">Let {c.employer?.name?.split(" ")[0]} answer</button>}
        </div>
      )}
      {open && c.transcript.length > 0 && (
        <div className="call-transcript">
          {c.transcript.map((t, i) => (
            <div key={i} className={`ct ${t.who}`}>
              <span className="eyebrow">{t.who === "saakshi" ? "Saakshi" : "Employer"}{t.intent ? ` · ${t.intent.replace("_", " ")}` : ""}</span>
              <p className={isDeva(t.text) ? "deva-text" : ""}>{t.text}{t.follow_text ? " " + t.follow_text : ""}</p>
              {t.audio && <Wave clip={t.audio} who={t.who === "saakshi" ? "saakshi" : "employer"} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ActivityLog({ limit = 18 }: { limit?: number }) {
  const [ev, setEv] = useState<{ id: number; at: string; kind: string; text: string }[]>([]);
  const load = useCallback(() => api.events().then(setEv).catch(() => {}), []);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => { if (e.type.startsWith("call.") || e.type === "world.changed" || e.type === "journal.turn") void load(); });
  return (
    <ol className="activity">
      {ev.slice(0, limit).map((e) => (
        <li key={e.id} className={e.kind.split(".")[0]}>
          <span className="mono faint">{new Date(e.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
          <span>{e.text}</span>
        </li>
      ))}
    </ol>
  );
}

export function RedTeamPanel() {
  const [r, setR] = useState<RedTeam>({ status: "idle" });
  const load = useCallback(() => api.redteam().then(setR).catch(() => {}), []);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => { if (e.type.startsWith("redteam")) void load(); });
  const run = async () => { await api.runRedteam(); void load(); };
  const pct = (v?: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  return (
    <div className="redteam">
      <div className="spread" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ maxWidth: 560 }}>
          <p className="h2">Red team the trust engine</p>
          <p className="muted">Generates a neighbourhood of honest workers plus fraudsters (collusion rings who vouch for each other with numbers bought together, and people inflating wages), runs every confirmation call through the real call engine and classifier, then measures what the trust engine catches.</p>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={r.status === "running"}>
          {r.status === "running" ? <><span className="spinner light" /> Running {r.progress}/{r.total}</> : "Run red team"}
        </button>
      </div>
      {r.status === "running" && <div className="progress"><i style={{ width: `${((r.progress ?? 0) / Math.max(1, r.total ?? 1)) * 100}%` }} /></div>}
      {r.status === "done" && (
        <div className="rt-tiles">
          <div><span className="num">{r.caught}/{(r.caught ?? 0) + (r.missed ?? 0)}</span><span className="eyebrow">fraudulent records caught</span></div>
          <div><span className="num">{r.false_alarms}</span><span className="eyebrow">honest records wrongly flagged</span></div>
          <div><span className="num">{pct(r.precision)}</span><span className="eyebrow">precision</span></div>
          <div><span className="num">{pct(r.recall)}</span><span className="eyebrow">recall</span></div>
          <div><span className="num">{r.honest_unresolved}</span><span className="eyebrow">honest records still awaiting a call</span></div>
        </div>
      )}
      <p className="small faint" style={{ marginTop: 14 }}>Synthetic population; numbers describe this simulation, not real-world accuracy.</p>
    </div>
  );
}

export function WorkerList({ onPick, active }: { onPick?: (id: string) => void; active?: string }) {
  const [ws, setWs] = useState<Worker[]>([]);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.workers().then((x) => { setWs(x); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => { if (e.type === "call.ended" || e.type === "world.changed") void load(); });
  if (err) return <OperatorGate error={err} onSet={load} />;
  return (
    <div className="wlist">
      {ws.map((w) => (
        <button key={w.id} className={`wl ${active === w.id ? "on" : ""}`} onClick={() => onPick?.(w.id)}>
          <span className={`wl-av ${(w.stats?.fraud_flags ?? 0) > 0 ? "bad" : ""}`}>{w.name.split(" ").map((x) => x[0]).join("").slice(0, 2)}</span>
          <span className="wl-name">{w.name}</span>
          <span className="small faint">{ROLE_LABEL[w.role]} · {w.city}</span>
          <span className="wl-pin link small" role="button" onClick={async (ev) => {
            ev.stopPropagation();
            const pin = prompt(`New PIN for ${w.name} (4–6 digits). Check it's really them first.`);
            if (!pin) return;
            try { await api.resetPin(w.id, pin); alert("PIN reset."); } catch (e) { alert((e as Error).message); }
          }}>Reset PIN</span>
          <span className="wl-stats">
            <span className="num">{inr(w.stats?.avg_monthly_verified)}</span>
            <span className={`wl-score ${(w.stats?.fraud_flags ?? 0) > 0 ? "bad" : (w.stats?.strength ?? 0) >= 60 ? "ok" : "wait"}`}>
              {(w.stats?.fraud_flags ?? 0) > 0 ? "flagged" : `trust ${w.stats?.strength ?? 0}`}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

/** At a glance: how much income is on record, how strong the evidence is, and whether Gnani is healthy. */
function DeskOverview() {
  const [s, setS] = useState<Stats | null>(null);
  const [ws, setWs] = useState<Worker[]>([]);
  const [calls, setCalls] = useState<Call[]>([]);
  const load = useCallback(() => {
    api.stats().then(setS).catch(() => {});
    api.workers().then(setWs).catch(() => {});
    api.calls().then(setCalls).catch(() => {});
  }, []);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => { if (e.type === "call.ended" || e.type === "world.changed" || e.type === "journal.turn") void load(); });
  if (!s) return <div className="desk-ov sheet" style={{ minHeight: 132 }}><span className="spinner" /></div>;
  const total = Math.max(1, [0, 1, 2, 3].reduce((n, k) => n + (s.levels[String(k)] ?? 0), 0));
  const flagged = ws.filter((w) => (w.stats?.fraud_flags ?? 0) > 0);
  const callbacks = calls.filter((c) => c.status === "callback");
  const disputed = calls.filter((c) => c.status === "done" && c.outcome === "disputed");
  const g = (u: Stats["gnani"]["timbre"]) => u.median_ms ? `${(u.median_ms / 1000).toFixed(1)} s` : "—";
  return (
    <div className="desk-ov">
      <div className="desk-kpis sheet">
        <div><span className="num">{inr(s.verified_income_monthly)}</span><span className="small faint">verified income / month</span></div>
        <div><span className="num">{s.workers}</span><span className="small faint">workers</span></div>
        <div><span className="num">{s.verified}<span className="faint" style={{ fontSize: "0.55em" }}> / {s.records}</span></span><span className="small faint">records confirmed</span></div>
        <div><span className="num">{s.calls}</span><span className="small faint">confirmation calls</span></div>
        <div className="desk-levels">
          <span className="small faint">Evidence behind every record</span>
          <div className="desk-lvbar" role="img" aria-label="Records by evidence level">
            {[0, 1, 2, 3].map((k) => {
              const n = s.levels[String(k)] ?? 0;
              return n ? <i key={k} className={`l${k}`} style={{ flexGrow: n }} title={`L${k}: ${n} records (${Math.round((n / total) * 100)}%)`} /> : null;
            })}
          </div>
          <div className="desk-lvkey">{[0, 1, 2, 3].map((k) => <span key={k}><i className={`l${k}`} />L{k} {s.levels[String(k)] ?? 0}</span>)}</div>
        </div>
      </div>
      <div className="desk-side">
        <div className="desk-gnani sheet">
          <p className="eyebrow">Gnani speech · live</p>
          <div className="desk-g"><b>Prisma</b><span className="mono small">{s.gnani.prisma.calls} calls · {g(s.gnani.prisma)}</span></div>
          <div className="desk-g"><b>Timbre</b><span className="mono small">{s.gnani.timbre.calls} lines · {g(s.gnani.timbre)}</span></div>
          <p className="small faint" style={{ margin: "6px 0 0" }}>{s.gnani.timbre.languages.length + s.gnani.prisma.languages.length > 0 ? `Languages used: ${[...new Set([...s.gnani.timbre.languages, ...s.gnani.prisma.languages])].map((l) => l.slice(0, 2)).join(" · ")}` : "No speech yet"}</p>
        </div>
        <div className="desk-attn sheet">
          <p className="eyebrow">Needs a look</p>
          {!flagged.length && !callbacks.length && !disputed.length && <p className="small faint" style={{ margin: 0 }}>Nothing right now.</p>}
          {flagged.map((w) => <Link key={w.id} to={`/passport/${w.id}`} className="desk-attn-row bad"><b>{w.name}</b><span className="small">fraud signals</span></Link>)}
          {callbacks.map((c) => <p key={c.id} className="desk-attn-row wait"><b>{c.employer?.name}</b><span className="small">asked for a callback</span></p>)}
          {disputed.slice(0, 3).map((c) => <p key={c.id} className="desk-attn-row bad"><b>{c.employer?.name}</b><span className="small">did not confirm</span></p>)}
        </div>
      </div>
    </div>
  );
}

export default function ConsolePage() {
  const initial = new URLSearchParams(location.search).get("tab");
  const [tab, setTab] = useState<"calls" | "graph" | "redteam">(initial === "graph" || initial === "redteam" ? initial : "calls");
  const [graph, setGraph] = useState<GraphData | null>(null);
  const loadGraph = useCallback(() => api.graph().then(setGraph).catch(() => {}), []);
  useEffect(() => { if (tab === "graph") void loadGraph(); }, [tab, loadGraph]);
  useStream((e) => { if (tab === "graph" && (e.type === "call.ended" || e.type === "world.changed" || e.type === "redteam.done")) void loadGraph(); });
  return (
    <main className="wrap page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Operations</p>
          <h1 className="h1">The <em>witness</em> desk.</h1>
        </div>
        <div className="seg">
          {(["calls", "graph", "redteam"] as const).map((t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t === "calls" ? "Calls & workers" : t === "graph" ? "Trust graph" : "Red team"}</button>
          ))}
        </div>
      </div>
      {tab === "calls" && (
        <>
          <DeskOverview />
          <div className="console-grid">
            <section>
              <CallQueue />
              <p className="eyebrow" style={{ margin: "26px 0 8px" }}>Activity</p>
              <div className="desk-activity"><ActivityLog /></div>
            </section>
            <section>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Workers</p>
              <WorkerList onPick={(id) => { location.href = at(`/passport/${id}`); }} />
            </section>
          </div>
        </>
      )}
      {tab === "graph" && (
        <section className="sheet" style={{ padding: 22 }}>
          <div className="spread" style={{ marginBottom: 6, flexWrap: "wrap" }}>
            <p className="h2">Who vouches for whom</p>
            <p className="small faint">Hover a node to trace its links · click a worker to open their passport</p>
          </div>
          {graph ? <TrustGraph data={graph} onSelect={(id) => { if (id.startsWith("w_")) location.href = at(`/passport/${id}`); }} /> : <span className="spinner" />}
        </section>
      )}
      {tab === "redteam" && <section className="sheet" style={{ padding: 26 }}><RedTeamPanel /></section>}
      <p className="small faint" style={{ marginTop: 24 }}>Looking for the side-by-side demo? <Link className="link" to="/demo">Open the live demo</Link></p>
    </main>
  );
}


/** Shown when the server is protected with SAAKSHI_ADMIN_KEY. */
export function OperatorGate({ error, onSet }: { error: string; onSet: () => void }) {
  const [k, setK] = useState("");
  if (!/operator key/i.test(error)) return <p className="error-line">{error}</p>;
  return (
    <div className="sheet" style={{ padding: 22, maxWidth: 460 }}>
      <p className="h3">Operator access</p>
      <p className="small muted">This server is protected. Enter the operator key (SAAKSHI_ADMIN_KEY).</p>
      <div className="wa-type" style={{ marginTop: 10 }}>
        <input type="password" value={k} onChange={(e) => setK(e.target.value)} />
        <button className="btn btn-sm btn-ink" onClick={() => { auth.setAdmin(k); resetStream(); onSet(); }}>Unlock</button>
      </div>
    </div>
  );
}
