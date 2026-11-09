import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Run } from "../api";
import { useMeta } from "../App";
import { PageHeader, Panel, Sev, SevBar, Stat } from "../components/ui";
import { findingRows, sevCounts, STATUS_WORD } from "../lib/findings";
import { ago } from "../lib/format";

const SOURCE: Record<string, string> = {
  unverified_action: "Ground truth", disclosure: "Canary / auditor", policy_waver: "Auditor", contained: "Contained",
};

/** Every vulnerability the red team proved, and whether a fix or the Shield has closed it since. */
export default function Findings() {
  const meta = useMeta();
  const nav = useNavigate();
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [status, setStatus] = useState<"all" | "open" | "fixed" | "shielded">("open");
  const [agent, setAgent] = useState("all");
  const [sev, setSev] = useState("all");
  useEffect(() => { api.runs().then(setRuns).catch(() => setRuns([])); }, []);

  const rows = useMemo(() => findingRows(runs ?? []), [runs]);
  const shown = rows.filter((r) => (status === "all" || r.status === status) && (agent === "all" || (r.run.target || "bank") === agent)
    && (sev === "all" || r.severity === sev));
  const open = rows.filter((r) => r.status === "open");

  return (
    <div>
      <PageHeader title="Findings" sub="Vulnerabilities proven by attack simulations. A finding closes when the same recorded attack is replayed and holds, against a fix or with Kavach Shield." />
      <div className="grid g-4">
        <Stat label="Open" value={open.length} tone={open.length ? "var(--breach)" : "var(--held)"} />
        <Stat label="Critical open" value={open.filter((r) => r.severity === "critical").length} tone="var(--sev-critical)" />
        <Stat label="Fix proven" value={rows.filter((r) => r.status === "fixed").length} tone="var(--held)" />
        <Stat label="Blocked by Shield" value={rows.filter((r) => r.status === "shielded").length} tone="var(--ice)" />
      </div>

      <Panel title="Open by severity" className="mt"><SevBar counts={sevCounts(open)} /></Panel>

      <Panel className="mt" flush title={`${shown.length} finding${shown.length === 1 ? "" : "s"}`} actions={
        <>
          <div className="seg">{(["open", "fixed", "shielded", "all"] as const).map((s) => <button key={s} className={status === s ? "on" : ""} onClick={() => setStatus(s)}>{s === "all" ? "All" : STATUS_WORD[s]}</button>)}</div>
          <select value={agent} onChange={(e) => setAgent(e.target.value)} className="sel" aria-label="Agent">
            <option value="all">All agents</option>
            {Object.values(meta?.targets ?? {}).map((t) => <option key={t.id} value={t.id}>{t.agent}</option>)}
          </select>
          <select value={sev} onChange={(e) => setSev(e.target.value)} className="sel" aria-label="Severity">
            <option value="all">All severities</option>
            {["critical", "high", "medium", "low"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </>
      }>
        {runs === null ? <div className="empty-s">Loading…</div> : shown.length ? (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Severity</th><th>Finding</th><th>Agent</th><th>Attack</th><th>Evidence</th><th>Status</th><th>Found</th></tr></thead>
              <tbody>
                {shown.map((f) => (
                  <tr key={f.id + f.run.id} className="click" onClick={() => nav(`/simulations/${f.run.id}`)}>
                    <td><Sev level={f.severity} /></td>
                    <td><div className="cell-2"><span className="trunc" style={{ maxWidth: 340 }}>{f.title}</span><small>turn {f.turn} · {SOURCE[f.kind] ?? f.kind}</small></div></td>
                    <td>{f.run.agent_name ?? "Sahayak"} <span className="faint small">v{f.run.hardening?.version ?? f.run.target_version}</span></td>
                    <td><div className="cell-2"><span>{f.run.objective_name}</span><small>{f.run.persona_name}</small></div></td>
                    <td><span className="trunc faint" style={{ maxWidth: 280 }}>{f.evidence}</span></td>
                    <td>{f.status === "open" ? <span className="state compromised">Open</span>
                      : <Link to={`/simulations/${f.fixedBy!.id}`} onClick={(e) => e.stopPropagation()} className={`state ${f.status === "shielded" ? "shield" : "resilient"}`}>{STATUS_WORD[f.status]}</Link>}</td>
                    <td className="mono faint">{ago(f.run.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="empty-s">{status === "open" ? "No open findings. " : "Nothing here. "}<Link to="/arena" className="link">Run a simulation</Link></div>}
      </Panel>
    </div>
  );
}
