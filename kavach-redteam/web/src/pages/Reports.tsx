import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Run } from "../api";
import { useMeta } from "../App";
import { PageHeader, Panel, Score, State } from "../components/ui";
import { ENV_LABEL, ago } from "../lib/format";
import { Defences } from "./Dashboard";

const FILTERS = [["all", "All"], ["compromised", "Compromised"], ["at_risk", "At risk"], ["resilient", "Resilient"],
  ["replay", "Replays"], ["shield", "With Shield"], ["live", "Human tests"]] as const;

/** Every attack simulation, newest first. */
export default function Reports() {
  const meta = useMeta();
  const nav = useNavigate();
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [agent, setAgent] = useState("all");
  const [q, setQ] = useState("");
  useEffect(() => {
    const load = () => api.runs().then(setRuns).catch(() => setRuns([]));
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  const shown = useMemo(() => (runs ?? []).filter((r) => {
    if (r.mode === "live" && !r.turn_count) return false;
    if (agent !== "all" && (r.target || "bank") !== agent) return false;
    if (q && !`${r.id} ${r.persona_name} ${r.objective_name} ${r.agent_name}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (filter === "all") return true;
    if (filter === "live") return r.mode === "live";
    if (filter === "replay") return r.mode === "replay";
    if (filter === "shield") return r.shield;
    return r.verdict === filter;
  }), [runs, filter, agent, q]);

  return (
    <div>
      <PageHeader title="Simulations" sub="Voice attack simulations against your agents: adaptive attacks, exact replays against fixes or the Shield, and human tests." />
      <Panel flush title={`${shown.length} simulation${shown.length === 1 ? "" : "s"}`} actions={
        <>
          <input className="sel" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search simulations" />
          <select className="sel" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
            <option value="all">All agents</option>
            {Object.values(meta?.targets ?? {}).map((t) => <option key={t.id} value={t.id}>{t.agent}</option>)}
          </select>
          <div className="seg">{FILTERS.map(([k, l]) => <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{l}</button>)}</div>
        </>
      }>
        {runs === null ? <div className="empty-s">Loading…</div> : shown.length ? (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>ID</th><th>Agent</th><th>Attack</th><th>Type</th><th>Defences</th><th>Line</th><th>Result</th><th>Broke at</th><th className="r">Score</th><th>When</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} className="click" onClick={() => nav(r.status === "running" && r.mode !== "live" ? `/call/${r.id}` : `/simulations/${r.id}`)}>
                    <td className="mono">{r.id.replace(/^(run|live)_/, "").slice(0, 8)}</td>
                    <td>{r.agent_name ?? "Sahayak"}</td>
                    <td><div className="cell-2"><span>{r.mode === "live" ? "Freestyle" : r.objective_name}</span><small>{r.persona_name}</small></div></td>
                    <td>{r.mode === "replay" ? <span className="pill fix">replay</span> : r.mode === "live" ? <span className="pill">human</span> : <span className="pill attack">adaptive</span>}</td>
                    <td><Defences r={r} /></td>
                    <td className="faint">{ENV_LABEL[r.environment] ?? r.environment}</td>
                    <td><State verdict={r.verdict} status={r.status} /></td>
                    <td className="faint">{r.broke_at ? `turn ${r.broke_at}` : "—"}</td>
                    <td className="r"><Score value={r.score} /></td>
                    <td className="mono faint">{ago(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="empty-s">No simulations match. <Link to="/arena" className="link">Run one</Link></div>}
      </Panel>
    </div>
  );
}
