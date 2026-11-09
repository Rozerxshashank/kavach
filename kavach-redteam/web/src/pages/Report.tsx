import { Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Run } from "../api";
import { targetOf, useMeta } from "../App";
import { ToolLine } from "../components/bits";
import { FixFlow, ReplayCompare } from "../components/FixFlow";
import { PageHeader, Panel, Sev, Stat, State, scoreTone } from "../components/ui";
import { Wave } from "../components/Wave";
import { ENV_LABEL, LANG, STATUS_WORD, isDeva, pad } from "../lib/format";

const STAGES: { k: string; label: string; c: string }[] = [
  { k: "timbre_caller_ms", label: "Gnani Timbre · attacker voice", c: "var(--ember)" },
  { k: "prisma_bot_ear_ms", label: "Gnani Prisma · agent's ears", c: "var(--info)" },
  { k: "shield_in_ms", label: "Kavach Shield · caller line", c: "var(--ice)" },
  { k: "agent_ms", label: "Agent · reasoning + actions", c: "var(--fg-3)" },
  { k: "bot_brain_ms", label: "Agent · reasoning + banking", c: "var(--fg-3)" },
  { k: "shield_out_ms", label: "Kavach Shield · agent reply", c: "var(--ice)" },
  { k: "timbre_bot_ms", label: "Gnani Timbre · agent voice", c: "var(--info)" },
  { k: "prisma_attacker_ear_ms", label: "Gnani Prisma · attacker's ears", c: "var(--ember)" },
];
const KIND: Record<string, string> = { unverified_action: "Ground truth", disclosure: "Canary / auditor", policy_waver: "Auditor", contained: "Contained" };

export default function Report() {
  const { id = "" } = useParams();
  const meta = useMeta();
  const nav = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => { setRun(null); api.run(id).then(setRun).catch((e) => setErr(e.message)); }, [id]);

  if (err) return <div className="callout bad">{err} · <Link className="link" to="/simulations">All simulations</Link></div>;
  if (!run) return <div className="empty-s">Loading…</div>;

  const target = targetOf(meta, run);
  const agent = run.agent_name ?? target?.agent ?? "Agent";
  const caller = run.mode === "live" ? "Human tester" : run.persona_name.replace(/^The /, "");
  const maxLat = Math.max(1, ...STAGES.map((s) => run.latency?.[s.k] ?? 0));
  const real = run.findings.filter((f) => f.kind !== "contained");
  const del = async () => { if (confirm("Delete this simulation and its recordings?")) { await api.deleteRun(run.id); nav("/simulations"); } };

  return (
    <div>
      <PageHeader title={run.mode === "live" ? "Human test" : run.objective_name}
        sub={<>{agent} · {caller} · <span className="mono">{run.id}</span> · {new Date(run.created_at).toLocaleString()}</>}
        actions={<>
          {run.mode !== "live" && <Link to={`/arena?target=${run.target || "bank"}&persona=${run.persona}`} className="btn btn-ghost btn-sm">Run again</Link>}
          {meta?.operator && <button className="btn btn-danger btn-sm" onClick={del}>Delete</button>}
        </>} />

      <div className="grid g-4">
        <Stat label="Result" value={<State verdict={run.verdict} status={run.status} />} sub={run.error ? run.error : run.objective_achieved ? "objective achieved by the attacker" : "objective not achieved"} />
        <Stat label="Resilience score" value={run.score ?? "—"} tone={scoreTone(run.score)} sub="100 = nothing given away" />
        <Stat label="Broke at" value={run.broke_at ? `Turn ${run.broke_at}` : "—"} sub={`${run.turn_count ?? run.turns.length} turns · ${run.breaking_tactic?.replace(/_/g, " ") ?? "no breaking tactic"}`} />
        <Stat label="Defences" value={<span style={{ fontSize: 18 }}>{run.hardening?.kind === "candidate" ? "Candidate fix" : `v${run.hardening?.version ?? run.target_version}`}{run.shield ? " + Shield" : ""}</span>}
          sub={run.shield_summary ? `Shield peak risk ${run.shield_summary.peak_risk}` : run.shield ? "Kavach Shield on" : "agent only"} />
      </div>

      {run.summary && <div className={`callout mt ${run.verdict === "compromised" ? "bad" : run.verdict === "resilient" ? "good" : ""}`}>{run.summary}</div>}
      {run.mode === "replay" && <Panel title="Before and after" sub="same recorded attack audio" className="mt"><ReplayCompare run={run} /></Panel>}

      <div className="grid g-main mt">
        <Panel title="Findings" sub={`${real.length} proven`} flush>
          {run.findings.length ? (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>Severity</th><th>Finding</th><th>Turn</th><th>Evidence</th><th>Source</th></tr></thead>
              <tbody>
                {run.findings.map((f) => (
                  <tr key={f.id}>
                    <td>{f.kind === "contained" ? <span className="pill shield">contained</span> : <Sev level={f.severity} />}</td>
                    <td>{f.title}</td>
                    <td><a className="link" href={`#t-${f.turn}`}>{f.turn}</a></td>
                    <td><span className="faint" style={{ display: "block", maxWidth: 380 }}>{f.evidence}</span></td>
                    <td className="faint small">{KIND[f.kind] ?? f.kind}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : <div className="empty-s">No findings. Every guardrail held.</div>}
        </Panel>

        <div className="grid" style={{ alignContent: "start" }}>
          <Panel title="Details">
            <dl className="kv">
              <dt>Objective</dt><dd>{run.objective_name}</dd>
              {run.breaks_if && <><dt>Compromised if</dt><dd className="muted">{run.breaks_if}</dd></>}
              <dt>Agent</dt><dd>{agent} · {target?.name}</dd>
              <dt>Attacker</dt><dd>{caller}{run.voice ? <span className="faint"> · Timbre “{run.voice}”</span> : ""}</dd>
              <dt>Line</dt><dd>{LANG[run.language] ?? run.language} · {ENV_LABEL[run.environment]}{run.environment !== "none" ? `, ${run.intensity}` : ""}</dd>
              <dt>Type</dt><dd>{run.mode === "replay" ? "Exact replay" : run.mode === "live" ? "Human test" : "Adaptive attack"}</dd>
              {run.reveal?.facts?.map((x, i) => <Fragment key={i}><dt>{i === 0 ? "Sandbox secrets" : ""}</dt><dd className="muted">{x}</dd></Fragment>)}
            </dl>
          </Panel>
          <Panel title="Latency per turn" sub="mean">
            {STAGES.filter((s) => run.latency?.[s.k] != null).map((s) => (
              <div key={s.k} className="spread" style={{ gap: 10, padding: "4px 0" }}>
                <span className="small" style={{ width: 200, flex: "none" }}>{s.label}</span>
                <div className="meter" style={{ flex: 1 }}><i style={{ width: `${((run.latency[s.k] ?? 0) / maxLat) * 100}%`, background: s.c }} /></div>
                <span className="mono small" style={{ width: 56, textAlign: "right" }}>{(run.latency[s.k] ?? 0) < 10 ? `${run.latency[s.k]} ms` : `${((run.latency[s.k] ?? 0) / 1000).toFixed(2)} s`}</span>
              </div>
            ))}
            {!Object.keys(run.latency ?? {}).length && <p className="faint small" style={{ margin: 0 }}>No timing data.</p>}
          </Panel>
        </div>
      </div>

      <Panel title="Transcript" sub="play any line" className="mt" flush>
        {run.turns.map((t) => (
          <div key={t.n} id={`t-${t.n}`} className={`tr-row ${t.verdict.status}`}>
            <div className="tr-n"><span className="mono">{pad(t.n)}</span><span className={`state ${t.verdict.status === "breached" ? "compromised" : t.verdict.status === "held" ? "resilient" : "at_risk"}`}>{STATUS_WORD[t.verdict.status] ?? t.verdict.status}</span></div>
            <div className="tr-side">
              <div className="tr-who"><b className="c-ember">{caller}</b>{t.tactic && <span className="pill attack">{t.tactic_label}</span>}</div>
              <Wave clip={t.caller_audio} who="caller" />
              {run.mode !== "live" && <p className={isDeva(t.said) ? "deva" : ""}>{t.said}</p>}
              <p className="tr-heard"><span>Prisma heard</span>{t.heard || "[nothing intelligible]"}</p>
              {t.shield?.inbound && (
                <div className="shield-line">
                  <span className={`shield-dec ${t.shield.inbound.decision}`}>Shield {t.shield.inbound.decision}</span>
                  <span className="shield-risk">risk {t.shield.inbound.risk}</span>
                  {t.shield.inbound.signals.map((x, i) => <span key={i} className="shield-sig" title={x.evidence}>{x.kind.replace(/_/g, " ")}</span>)}
                </div>
              )}
            </div>
            <div className="tr-side">
              <div className="tr-who"><b className="c-ice">{agent}</b>{t.intent && <span className="pill">understood as {t.intent}</span>}</div>
              <Wave clip={t.bot_audio} who="bot" cut={t.interrupted} />
              <p className={isDeva(t.bot) ? "deva" : ""}>{t.bot}{t.interrupted && <span className="faint"> (cut off by barge-in)</span>}</p>
              {t.tools.map((x, i) => <ToolLine key={i} t={x} />)}
              {t.shield?.outbound && t.shield.outbound.decision !== "allow" && (
                <div className="shield-line"><span className={`shield-dec ${t.shield.outbound.decision}`}>Shield {t.shield.outbound.decision === "block" ? "blocked" : "rewrote"}</span>
                  {t.shield.outbound.original && <span className="struck small">{t.shield.outbound.original}</span>}</div>
              )}
              {t.shield?.actions?.filter((a) => a.decision !== "allow").map((a, i) => (
                <div key={i} className="shield-line"><span className="shield-dec deny">Shield denied {a.name.replace(/_/g, " ")}</span><span className="faint small">{a.reason}</span></div>
              ))}
              {t.verdict.note && <p className="tr-note">Judge: {t.verdict.note}</p>}
            </div>
          </div>
        ))}
        {!run.turns.length && <div className="empty-s">No turns recorded.</div>}
      </Panel>

      {run.mode === "campaign" && real.length > 0 && <Panel title="Remediate" sub="fix it, then prove it with the same recorded attack" className="mt"><FixFlow run={run} /></Panel>}
    </div>
  );
}
