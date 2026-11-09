import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Fix, type Run, type TargetDetail } from "../api";
import { useMeta } from "../App";
import { Score, State } from "./ui";
import { player } from "../lib/player";

/** Find → Fix → Prove, for any target: Kavach writes rules and picks hard gates, then the exact recorded attack is
    replayed against the fix (in the sandbox only). Or prove the Shield: the same attack, same agent, Shield on. */
export function FixFlow({ run }: { run: Run }) {
  const nav = useNavigate();
  const meta = useMeta();
  const [detail, setDetail] = useState<TargetDetail | null>(null);
  const [fix, setFix] = useState<Fix | null>(run.fix ?? null);
  const [rules, setRules] = useState<string[]>(run.fix?.new_rules ?? []);
  const [gates, setGates] = useState<Record<string, boolean>>(run.fix?.gates ?? run.hardening?.gates ?? {});
  const [busy, setBusy] = useState<"" | "write" | "replay" | "shield" | "live">("");
  const [err, setErr] = useState("");

  useEffect(() => { api.target(run.target || "bank").then(setDetail).catch(() => {}); }, [run.target]);
  const gateInfo = detail?.gates ?? meta?.targets[run.target || "bank"]?.gates ?? {};
  const base = run.hardening?.rules ?? [];
  const blocked = !!meta?.running || (meta?.quota.left ?? 1) <= 0;

  const write = async () => {
    setBusy("write"); setErr("");
    try { const f = await api.fix(run.id); setFix(f); setRules(f.new_rules); setGates(f.gates); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  };
  const replay = async (kind: "candidate" | "shield" | "live") => {
    setBusy(kind === "candidate" ? "replay" : kind); setErr("");
    player.unlock();
    try {
      const r = kind === "candidate"
        ? await api.replay(run.id, { against: "candidate", title: fix?.title ?? "Candidate fix", rules: rules.map((x) => x.trim()).filter(Boolean), gates, shield: run.shield })
        : kind === "shield" ? await api.replay(run.id, { against: "same", shield: true })
        : await api.replay(run.id, { against: "live", shield: run.shield });
      nav(`/call/${r.id}`);
    } catch (e) { setErr((e as Error).message); setBusy(""); }
  };

  if (!run.findings.length) {
    return (
      <div className="patch">
        <p className="h3">Nothing to fix.</p>
        <p className="muted">{run.agent_name ?? "The agent"} held for the whole call. Try a different caller, objective or heavier noise, or attack the original version.</p>
      </div>
    );
  }

  return (
    <div className="patch">
      <AnimatePresence mode="wait">
        {!fix ? (
          <motion.div key="a" initial={{ y: 6 }} animate={{ y: 0 }} exit={{ opacity: 0 }}>
            <p className="h3">Fix it, then prove it.</p>
            <p className="muted" style={{ maxWidth: "58ch" }}>
              Two ways to close this hole. Kavach can write rules for the agent and switch on hard gates, then replay the
              exact attack against the fix. Or put <span className="c-ice">Kavach Shield</span> on the line and replay the
              same attack against the same agent.
            </p>
            <div className="row" style={{ marginTop: 14, flexWrap: "wrap" }}>
              <button className="btn btn-ice" onClick={write} disabled={!!busy}>
                {busy === "write" ? <><span className="spinner" /> Writing the fix</> : <>Write a fix <span className="arrow">→</span></>}
              </button>
              {!run.shield && (
                <button className="btn btn-ghost" onClick={() => replay("shield")} disabled={!!busy || blocked}>
                  {busy === "shield" ? <><span className="spinner" /> Dialling</> : <>⛨ Replay with Kavach Shield</>}
                </button>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.div key="b" initial={{ y: 10 }} animate={{ y: 0 }}>
            <p className="eyebrow">Candidate fix for {run.hardening?.kind === "candidate" ? "a candidate" : `v${run.hardening?.version}`} · runs only in the sandbox</p>
            <p className="h3" style={{ marginTop: 6 }}>{fix.title}</p>
            {fix.rationale && <p className="muted" style={{ maxWidth: "62ch" }}>{fix.rationale}</p>}
            <p className="eyebrow" style={{ marginTop: 18 }}>New rules for the agent · edit freely</p>
            <ol className="patch-rules">
              {rules.map((r, i) => (
                <li key={i} className="rule-row">
                  <textarea value={r} rows={2} maxLength={320} aria-label={`Rule ${i + 1}`}
                    onChange={(e) => setRules(rules.map((x, j) => (j === i ? e.target.value : x)))} />
                  <button className="rule-x" onClick={() => setRules(rules.filter((_, j) => j !== i))} aria-label={`Remove rule ${i + 1}`}>×</button>
                </li>
              ))}
            </ol>
            {rules.length + base.length < 8 && <button className="link" style={{ fontSize: 13 }} onClick={() => setRules([...rules, ""])}>+ add a rule</button>}
            {base.length > 0 && (
              <details className="faint" style={{ marginTop: 10, fontSize: 13 }}>
                <summary style={{ cursor: "pointer" }}>{base.length} rule{base.length === 1 ? "" : "s"} this version already has</summary>
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>{base.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </details>
            )}
            {Object.keys(gateInfo).length > 0 && (
              <>
                <p className="eyebrow" style={{ marginTop: 20 }}>Hard gates · code, so they hold even if the model is fooled</p>
                <div className="gate-grid">
                  {Object.entries(gateInfo).map(([k, d]) => (
                    <label key={k} className={`gate ${gates[k] ? "on" : ""}`}>
                      <input type="checkbox" checked={!!gates[k]} onChange={(e) => setGates({ ...gates, [k]: e.target.checked })} />
                      <span><b className="mono">{k.replace(/_/g, " ")}</b><span className="faint">{d}</span></span>
                    </label>
                  ))}
                </div>
              </>
            )}
            <div className="row" style={{ marginTop: 22, flexWrap: "wrap" }}>
              <button className="btn btn-primary" onClick={() => replay("candidate")} disabled={!!busy || blocked}>
                {busy === "replay" ? <><span className="spinner" /> Dialling</> : <>↻ Replay the exact attack against this fix</>}
              </button>
              {!run.shield && (
                <button className="btn btn-ghost" onClick={() => replay("shield")} disabled={!!busy || blocked}>⛨ Or with Kavach Shield</button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {blocked && <p className="faint" style={{ fontSize: 13, marginTop: 10 }}>{meta?.running ? "Another call is on the line; replays wait for it." : "Today's call budget is used."}</p>}
      {err && <p className="error-line" role="alert">{err}</p>}
    </div>
  );
}

/** For a replay: before and after, and (for operators) promoting a fix that held. */
export function ReplayCompare({ run }: { run: Run }) {
  const meta = useMeta();
  const [parent, setParent] = useState<Run | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [promoted, setPromoted] = useState<number | null>(run.promoted ?? null);
  const [err, setErr] = useState("");
  useEffect(() => { if (run.parent) api.run(run.parent).then(setParent).catch(() => {}); }, [run.parent]);
  if (!parent) return null;
  const label = (r: Run) => `${r.hardening?.kind === "candidate" ? "candidate fix" : `v${r.hardening?.version ?? r.target_version}`}${r.shield ? " + Shield" : ""}`;
  const changed = parent.shield !== run.shield ? (run.shield ? "Only Kavach Shield was added." : "Only Kavach Shield was removed.")
    : run.hardening?.kind === "candidate" ? "Only the agent's rules and gates changed." : "Only the agent's version changed.";
  const canPromote = run.hardening?.kind === "candidate" && run.verdict !== "compromised";
  return (
    <div>
      <div className="cmp">
        <div className="cmp-side">
          <span className="eyebrow">Before · {label(parent)}</span>
          <div className="row"><Score value={parent.score} /><State verdict={parent.verdict} status={parent.status} /></div>
          <Link to={`/simulations/${parent.id}`} className="link small">Original simulation</Link>
        </div>
        <span className="cmp-arrow" aria-hidden>→</span>
        <div className="cmp-side">
          <span className="eyebrow">After · {label(run)}</span>
          <div className="row"><Score value={run.score} /><State verdict={run.verdict} status={run.status} /></div>
          <span className="faint small">this simulation</span>
        </div>
      </div>
      <p className="faint" style={{ fontSize: 13, marginTop: 10 }}>Same attacker, same words, same recorded audio. {changed}</p>
      {run.hardening?.kind === "candidate" && (
        promoted ? <p className="tag held" style={{ marginTop: 14 }}>Promoted · live as v{promoted}</p>
        : !canPromote ? <p className="muted" style={{ marginTop: 14 }}>This fix didn't hold. Go back to the <Link className="link" to={`/simulations/${parent.id}`}>original call</Link>, change it, and replay again.</p>
        : meta?.operator ? (
          <div className="promote">
            <p className="h3">Make it live</p>
            <p className="muted" style={{ margin: 0 }}>Every real call to {run.agent_name} will run these {run.hardening.rules.length} rules and {Object.values(run.hardening.gates).filter(Boolean).length} gates. You can switch back any time on its Targets page.</p>
            <input placeholder="Note for the changelog (optional)" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
            <button className="btn btn-ice" disabled={busy} onClick={async () => {
              setBusy(true); setErr("");
              try { setPromoted((await api.promote(run.id, note)).version); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
            }}>{busy ? "Promoting…" : "Promote to the live agent"}</button>
            {err && <p className="error-line">{err}</p>}
          </div>
        ) : <p className="muted" style={{ marginTop: 14 }}>The fix held. An operator can promote it to the live agent from here.</p>
      )}
    </div>
  );
}
