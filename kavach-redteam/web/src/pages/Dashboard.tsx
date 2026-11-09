import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Run, type ShieldCall, type ShieldStats } from "../api";
import { useMeta } from "../App";
import { Icon, PageHeader, Panel, Score, Sev, SevBar, Stat, State, scoreTone } from "../components/ui";
import { findingRows, sevCounts, STATUS_WORD, within } from "../lib/findings";
import { ago } from "../lib/format";

/** The security posture of every protected voice agent, at a glance. */
export default function Dashboard() {
  const meta = useMeta();
  const nav = useNavigate();
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [stats, setStats] = useState<ShieldStats | null>(null);
  const [calls, setCalls] = useState<ShieldCall[]>([]);
  useEffect(() => {
    const load = () => {
      api.runs().then(setRuns).catch(() => setRuns([]));
      api.shieldStats().then(setStats).catch(() => {});
      api.shieldCalls().then(setCalls).catch(() => {});
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const d = useMemo(() => {
    const all = (runs ?? []).filter((r) => r.mode !== "live" || r.turn_count);
    const done = all.filter((r) => r.verdict && r.verdict !== "incomplete");
    const rows = findingRows(all);
    const open = rows.filter((r) => r.status === "open");
    const recent = done.filter((r) => within(r.created_at, 30));
    const posture = recent.length ? Math.round(recent.slice(0, 12).reduce((n, r) => n + (r.score ?? 0), 0) / Math.min(12, recent.length)) : null;
    const tactics: Record<string, number> = {};
    for (const r of done) if (r.verdict === "compromised" && r.breaking_tactic) tactics[r.breaking_tactic] = (tactics[r.breaking_tactic] ?? 0) + 1;
    const agents = Object.values(meta?.targets ?? {}).map((t) => {
      const mine = done.filter((r) => (r.target || "bank") === t.id);
      const last = mine[0];
      const openHere = open.filter((f) => (f.run.target || "bank") === t.id);
      const avg = mine.length ? Math.round(mine.slice(0, 10).reduce((n, r) => n + (r.score ?? 0), 0) / Math.min(10, mine.length)) : null;
      return { t, last, avg, open: openHere.length, crit: openHere.filter((f) => f.severity === "critical").length, sims: mine.length };
    });
    return { all, done, rows, open, posture, tactics, agents,
      sims7: all.filter((r) => within(r.created_at, 7) && r.mode !== "live").length,
      proven: rows.filter((r) => r.status !== "open").length };
  }, [runs, meta]);

  const blocked = stats ? stats.escalated_7d + stats.blocked_replies_7d + stats.denied_actions_7d : null;
  const openSev = sevCounts(d.open);
  const topTactics = Object.entries(d.tactics).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const maxT = Math.max(1, ...topTactics.map((x) => x[1]));

  return (
    <div>
      <PageHeader title="Security overview"
        sub="Posture of the voice agents Kavach protects: what the red team found, what was fixed, and what the Shield is blocking on live calls."
        actions={<><Link to="/shield?tab=test" className="btn btn-ghost btn-sm"><Icon name="shield" size={14} />Test the Shield</Link></>} />

      <div className="grid g-4">
        <Stat label="Security posture" value={d.posture ?? "—"} tone={scoreTone(d.posture)}
          sub={d.posture == null ? "Run a simulation to score your agents" : "mean resilience, last 12 simulations (0–100)"} />
        <Stat label="Open findings" value={d.open.length} tone={d.open.length ? "var(--breach)" : "var(--held)"}
          sub={`${openSev.critical ?? 0} critical · ${openSev.high ?? 0} high · ${d.proven} resolved`} />
        <Stat label="Simulations · 7 days" value={d.sims7} sub={meta ? `${meta.quota.left} of ${meta.quota.daily} left today` : ""} />
        <Stat label="Threats blocked live · 7 days" value={blocked ?? "—"} tone="var(--ice)"
          sub={stats ? `${stats.escalated_7d} escalated · ${stats.blocked_replies_7d} replies · ${stats.denied_actions_7d} actions` : ""} />
      </div>

      <div className="grid g-main" style={{ marginTop: 16 }}>
        <Panel title="Protected agents" sub={`${d.agents.length} agents`} flush>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Agent</th><th>Environment</th><th>Resilience</th><th>Open findings</th><th>Last simulation</th><th>Shield</th></tr></thead>
              <tbody>
                {d.agents.map(({ t, last, avg, open, crit, sims }) => (
                  <tr key={t.id} className="click" onClick={() => nav(`/targets/${t.id}`)}>
                    <td><div className="cell-2"><b>{t.agent}</b><small className="trunc" style={{ maxWidth: 260 }} title={t.kind}>{t.kind}</small></div></td>
                    <td><span className="pill">{t.id === "saakshi" ? "production · separate service" : "demo · in-process"}</span></td>
                    <td><Score value={avg} /> <span className="faint small">{sims} runs</span></td>
                    <td>{open ? <span className="state compromised">{open}{crit ? ` (${crit} critical)` : ""}</span> : <span className="state resilient">None</span>}</td>
                    <td className="faint">{last ? ago(last.created_at) : "never"}</td>
                    <td><span className="pill shield">{t.id === "saakshi" ? "SDK · every call" : "proxy"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Open findings by severity" actions={<Link to="/findings" className="link small">View all</Link>}>
          <SevBar counts={openSev} />
          <p className="eyebrow" style={{ margin: "20px 0 10px" }}>Tactics that broke agents</p>
          {topTactics.length ? topTactics.map(([k, n]) => (
            <div key={k} className="spread" style={{ gap: 12, padding: "5px 0" }}>
              <span className="small" style={{ width: 150, flex: "none" }}>{k.replace(/_/g, " ")}</span>
              <div className="meter" style={{ flex: 1 }}><i style={{ width: `${(n / maxT) * 100}%`, background: "var(--ember)" }} /></div>
              <span className="mono small faint">{n}</span>
            </div>
          )) : <p className="faint small" style={{ margin: 0 }}>No breaks recorded yet.</p>}
        </Panel>
      </div>

      <div className="grid g-main" style={{ marginTop: 16 }}>
        <Panel title="Recent simulations" actions={<Link to="/simulations" className="link small">View all</Link>} flush>
          {d.all.length ? (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>When</th><th>Agent</th><th>Attack</th><th>Defences</th><th>Result</th><th className="r">Score</th></tr></thead>
                <tbody>
                  {d.all.slice(0, 8).map((r) => (
                    <tr key={r.id} className="click" onClick={() => nav(r.status === "running" ? `/call/${r.id}` : `/simulations/${r.id}`)}>
                      <td className="mono faint">{ago(r.created_at)}</td>
                      <td>{r.agent_name ?? "Sahayak"}</td>
                      <td><div className="cell-2"><span className="trunc" style={{ maxWidth: 260 }}>{r.objective_name}</span><small>{r.persona_name}{r.mode === "replay" ? " · replay" : r.mode === "live" ? " · human" : ""}</small></div></td>
                      <td><Defences r={r} /></td>
                      <td><State verdict={r.verdict} status={r.status} /></td>
                      <td className="r"><Score value={r.score} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty-s">No simulations yet. <Link to="/arena" className="link">Run the first one</Link></div>}
        </Panel>

        <Panel title="Shield activity" sub="live guarded calls" actions={<Link to="/shield" className="link small">Monitor</Link>} flush>
          {calls.length ? (
            <div className="feed">
              {calls.slice(0, 8).map((c) => {
                const worst = c.timeline.some((e) => ["escalate", "block", "deny"].includes(e.decision ?? "")) ? "var(--breach)"
                  : c.timeline.some((e) => ["challenge", "rewrite"].includes(e.decision ?? "")) ? "var(--amber)" : "var(--held)";
                const n = c.timeline.filter((e) => ["escalate", "block", "deny", "rewrite"].includes(e.decision ?? "")).length;
                return (
                  <div key={c.session_id} className="feed-row">
                    <i className="ic" style={{ background: worst }} />
                    <div className="cell-2"><span>{c.policy === "saakshi-employer-calls" ? "Saakshi" : "Sahayak"} · peak risk <b className="mono">{c.peak_risk}</b></span>
                      <small>{n ? `${n} intervention${n > 1 ? "s" : ""}` : "no intervention needed"} · {c.owner === "internal" ? "red-team call" : c.owner === "playground" ? "test console" : "agent"}</small></div>
                    <time>{ago(c.started_at)}</time>
                  </div>
                );
              })}
            </div>
          ) : <div className="empty-s">No guarded calls yet.</div>}
        </Panel>
      </div>

      {d.open.length > 0 && (
        <Panel title="Top open findings" className="mt" actions={<Link to="/findings" className="link small">Triage</Link>} flush>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Severity</th><th>Finding</th><th>Agent</th><th>Attack</th><th>Status</th></tr></thead>
              <tbody>
                {d.open.slice(0, 5).map((f) => (
                  <tr key={f.id + f.run.id} className="click" onClick={() => nav(`/simulations/${f.run.id}`)}>
                    <td><Sev level={f.severity} /></td>
                    <td><span className="trunc">{f.title}</span></td>
                    <td>{f.run.agent_name ?? "Sahayak"}</td>
                    <td className="muted">{f.run.objective_name}</td>
                    <td><span className="state compromised">{STATUS_WORD[f.status]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}

export function Defences({ r }: { r: Run }) {
  return (
    <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
      <span className="pill">{r.hardening?.kind === "candidate" ? "candidate fix" : `v${r.hardening?.version ?? r.target_version ?? "–"}`}</span>
      {r.shield && <span className="pill shield">Shield</span>}
    </span>
  );
}
