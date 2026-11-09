import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type AgentVersion, type Run, type TargetDetail } from "../api";
import { useMeta } from "../App";
import { Icon, PageHeader, Panel, Score, Stat, State } from "../components/ui";
import { findingRows } from "../lib/findings";
import { ago } from "../lib/format";
import { Defences } from "./Dashboard";

/** One protected agent: its security versions, hard gates, and what simulations found. */
export default function Lab() {
  const { id = "saakshi" } = useParams();
  const meta = useMeta();
  const nav = useNavigate();
  const [t, setT] = useState<TargetDetail | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.target(id).then((x) => {
    setT(x);
    setSel((s) => s ?? x.versions?.versions.find((v) => v.active)?.version ?? null);
  }).catch((e) => setErr(e.message));
  useEffect(() => { setT(null); setSel(null); setErr(""); void load(); api.runs(id).then(setRuns).catch(() => {}); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <div className="callout bad">{err}</div>;
  if (!t || !meta) return <div className="empty-s">Loading…</div>;
  const versions = t.versions?.versions ?? [];
  const v: AgentVersion | undefined = versions.find((x) => x.version === sel) ?? versions.find((x) => x.active);
  const live = versions.find((x) => x.active);
  const done = runs.filter((r) => r.verdict && r.verdict !== "incomplete");
  const open = findingRows(runs).filter((f) => f.status === "open");
  const avg = done.length ? Math.round(done.slice(0, 10).reduce((n, r) => n + (r.score ?? 0), 0) / Math.min(10, done.length)) : null;
  const activate = async (version: number) => {
    setBusy(true);
    try { await api.activate(id, version); setSel(version); await load(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title={<>{t.agent} <span className="pill dev-only" style={{ verticalAlign: "middle", marginLeft: 8 }}>{id === "saakshi" ? "production" : "demo"}</span></>}
        sub={t.description}
        actions={<><Link to={`/live?target=${id}`} className="btn btn-ghost btn-sm"><Icon name="mic" size={14} />Live test</Link>
          <Link to={`/arena?target=${id}`} className="btn btn-primary btn-sm"><Icon name="target" size={14} />Attack {t.agent}</Link></>} />

      {!t.available && <div className="callout bad" style={{ marginBottom: 16 }}>Unreachable: {t.unavailable_reason}</div>}

      <div className="grid g-4">
        <Stat label="Live version" value={live ? `v${live.version}` : "—"} sub={live?.title} />
        <Stat label="Resilience" value={<Score value={avg} />} sub={`mean of the last ${Math.min(10, done.length)} simulations`} />
        <Stat label="Open findings" value={open.length} tone={open.length ? "var(--breach)" : "var(--held)"} />
        <Stat label="Runtime protection" value={<span className="pill shield" style={{ fontSize: 13 }}>{id === "saakshi" ? "Shield SDK" : "Shield proxy"}</span>}
          sub={id === "saakshi" ? "every real call checked by Kavach Shield" : "Shield sits in front of the bot in simulations"} />
      </div>

      <div className="grid g-main mt">
        <Panel title="Security versions" sub="each one proven by a replay before it went live" flush>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Version</th><th>Title</th><th>Rules</th><th>Gates</th><th>Created</th><th>Status</th><th /></tr></thead>
              <tbody>
                {versions.slice().reverse().map((x) => (
                  <tr key={x.version} className={`click ${x.version === v?.version ? "sel-row" : ""}`} onClick={() => setSel(x.version)}>
                    <td className="mono">v{x.version}</td>
                    <td><span className="trunc" style={{ maxWidth: 260 }}>{x.title}</span></td>
                    <td className="mono">{x.rules.length}</td>
                    <td className="mono">{Object.values(x.gates).filter(Boolean).length}</td>
                    <td className="faint">{x.created_at ? ago(x.created_at) : "built in"}</td>
                    <td>{x.active ? <span className="state resilient">Live</span> : <span className="faint small">Inactive</span>}</td>
                    <td className="r">{!x.active && meta.operator && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={(e) => { e.stopPropagation(); void activate(x.version!); }}>Make live</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!meta.operator && <p className="faint small" style={{ margin: 0, padding: "10px 16px", borderTop: "1px solid var(--line)" }}>Operators can switch the live version (sign in at the bottom of the sidebar).</p>}
        </Panel>

        <Panel title="Hard gates" sub={v ? `v${v.version}` : ""} flush>
          <table className="tbl"><tbody>
            {Object.entries(t.gates ?? {}).map(([k, d]) => (
              <tr key={k}>
                <td><div className="cell-2"><b className="mono" style={{ fontSize: 12 }}>{k.replace(/_/g, " ")}</b><small>{d}</small></div></td>
                <td className="r">{v?.gates[k] ? <span className="state resilient">On</span> : <span className="state incomplete">Off</span>}</td>
              </tr>
            ))}
          </tbody></table>
        </Panel>
      </div>

      {v && (
        <Panel title={`Rules in v${v.version}`} sub={v.title} className="mt">
          {v.note && <p className="muted small" style={{ marginTop: 0 }}>{v.note}</p>}
          {v.rules.length ? <ol className="rules">{v.rules.map((r, i) => <li key={i}>{r}</li>)}</ol> : <p className="faint small" style={{ margin: 0 }}>No extra rules: the agent as first built.</p>}
          {v.prompt && <details style={{ marginTop: 12 }}><summary className="small faint" style={{ cursor: "pointer" }}>Base instructions</summary><pre className="code" style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>{v.prompt}</pre></details>}
          {v.source_run && <p className="small" style={{ margin: "12px 0 0" }}><Link className="link" to={`/simulations/${v.source_run}`}>The replay that proved this version</Link></p>}
        </Panel>
      )}

      <Panel title={`Simulations against ${t.agent}`} className="mt" flush actions={<Link to="/simulations" className="link small">All simulations</Link>}>
        {done.length ? (
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>When</th><th>Attack</th><th>Defences</th><th>Result</th><th className="r">Score</th></tr></thead>
            <tbody>
              {done.slice(0, 12).map((r) => (
                <tr key={r.id} className="click" onClick={() => nav(`/simulations/${r.id}`)}>
                  <td className="mono faint">{ago(r.created_at)}</td>
                  <td><div className="cell-2"><span>{r.objective_name}</span><small>{r.persona_name}{r.mode === "replay" ? " · replay" : ""}</small></div></td>
                  <td><Defences r={r} /></td>
                  <td><State verdict={r.verdict} status={r.status} /></td>
                  <td className="r"><Score value={r.score} /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : <div className="empty-s">No simulations against {t.agent} yet.</div>}
      </Panel>
    </div>
  );
}
