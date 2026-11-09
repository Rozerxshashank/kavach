import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type TargetDetail } from "../api";
import { useMeta } from "../App";
import { Icon, PageHeader, Panel, Sev } from "../components/ui";
import { ENV_LABEL, LANG } from "../lib/format";
import { player } from "../lib/player";
import "./arena.css";

/** Configure and launch an adaptive voice attack against one of your agents. */
export default function Arena() {
  const meta = useMeta();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const tid = params.get("target") && meta?.targets[params.get("target")!] ? params.get("target")! : "saakshi";
  const t = meta?.targets[tid];
  const [detail, setDetail] = useState<TargetDetail | null>(null);
  const [persona, setPersona] = useState<string>(params.get("persona") || "");
  const [objective, setObjective] = useState<string>("");
  const [language, setLanguage] = useState<string | null>(null);
  const [environment, setEnvironment] = useState<string | null>(null);
  const [intensity, setIntensity] = useState("medium");
  const [turns, setTurns] = useState(5);
  const [hardening, setHardening] = useState<"live" | "original">("live");
  const [shield, setShield] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { setDetail(null); api.target(tid).then(setDetail).catch(() => {}); }, [tid]);
  useEffect(() => {
    if (!t) return;
    const p = persona && t.personas[persona] ? persona : Object.keys(t.personas)[0];
    setPersona(p);
    setObjective((o) => (o && t.objectives[o] ? o : Object.entries(t.objectives).find(([, x]) => x.persona === p)?.[0] ?? Object.keys(t.objectives)[0]));
  }, [tid, t]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!meta || !t || !persona || !objective || !t.personas[persona]) return <div className="empty-s">Loading…</div>;
  const p = t.personas[persona];
  const o = t.objectives[objective];
  const env = environment ?? p.environment;
  const lang = language && t.languages.includes(language) ? language : (t.languages.includes(p.language) ? p.language : t.languages[0]);
  const live = detail?.versions?.live;
  const original = detail?.versions?.versions.find((v) => v.version === (tid === "bank" ? 1 : 0));
  const unavailable = detail && !detail.available;
  const running = meta.running;
  const blocked = busy || !meta.ready.gnani || !meta.ready.llm || !!unavailable || !!running || meta.quota.left <= 0;

  // re-picking the current target changes nothing; a new target starts on its own first attacker and that
  // attacker's signature objective at once (clearing them showed "Loading…" until the next meta refresh)
  const pickTarget = (id: string) => {
    const nt = meta.targets[id];
    if (id === tid || !nt) return;
    const np = Object.keys(nt.personas)[0];
    setParams({ target: id }); setPersona(np);
    setObjective(Object.entries(nt.objectives).find(([, x]) => x.persona === np)?.[0] ?? Object.keys(nt.objectives)[0]);
    setLanguage(null); setEnvironment(null);
  };
  const go = async () => {
    player.unlock();
    setBusy(true); setErr("");
    try {
      const { id } = await api.start({ target: tid, persona, objective, language: lang, environment: env, intensity, max_turns: turns, hardening, shield });
      nav(`/call/${id}`);
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="New simulation" sub="An adaptive attacker phones the agent in a natural Indian voice (Gnani Timbre) over simulated background noise. The agent hears it only through Gnani Prisma. Every call runs in a sealed sandbox." />
      <div className="grid g-main">
        <div className="grid" style={{ alignContent: "start" }}>
          <Panel title="1 · Target agent">
            <div className="grid g-2">
              {Object.values(meta.targets).map((x) => (
                <button key={x.id} className={`opt ${x.id === tid ? "on" : ""}`} onClick={() => pickTarget(x.id)}>
                  <span className="opt-h"><Icon name="agent" /><b>{x.agent}</b><span className="pill">{x.id === "saakshi" ? "production" : "demo"}</span></span>
                  <span className="opt-d">{x.kind}</span>
                </button>
              ))}
            </div>
            {unavailable && <div className="callout bad" style={{ marginTop: 12 }}>{detail?.unavailable_reason}</div>}
          </Panel>

          <Panel title="2 · Attacker profile" sub={`${Object.keys(t.personas).length} profiles`}>
            <div className="grid g-2">
              {Object.entries(t.personas).map(([id, x]) => (
                <button key={id} className={`opt ${id === persona ? "on" : ""}`} onClick={() => {
                  setPersona(id); setEnvironment(null); setLanguage(null);
                  const sig = Object.entries(t.objectives).find(([, ob]) => ob.persona === id)?.[0];
                  if (sig) setObjective(sig);
                }}>
                  <span className="opt-h"><b>{x.name.replace(/^The /, "")}</b><span className="mono faint small">{x.voice}</span></span>
                  <span className="opt-d">{x.tagline}</span>
                </button>
              ))}
            </div>
            <p className="small faint" style={{ margin: "12px 0 0" }}>{p.brief}</p>
          </Panel>

          <Panel title="3 · Objective" flush>
            <div className="tbl-wrap">
              <table className="tbl">
                <tbody>
                  {Object.entries(t.objectives).map(([id, x]) => (
                    <tr key={id} className={`click ${id === objective ? "sel-row" : ""}`} onClick={() => setObjective(id)}>
                      <td style={{ width: 28 }}><span className={`radio ${id === objective ? "on" : ""}`} /></td>
                      <td><div className="cell-2"><b>{x.name}</b><small>Compromised if: {x.breaks_if}</small></div></td>
                      <td className="r"><Sev level={x.severity} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        <div className="grid" style={{ alignContent: "start", position: "sticky", top: 70 }}>
          <Panel title="Configuration">
            <div className="form">
              <label><span>Language</span>
                <div className="seg">{t.languages.map((l) => <button key={l} className={lang === l ? "on" : ""} onClick={() => setLanguage(l)}>{LANG[l]}</button>)}</div></label>
              <label><span>Line conditions</span>
                <select className="sel" value={env} onChange={(e) => setEnvironment(e.target.value)}>
                  {Object.keys(meta.environments).map((e) => <option key={e} value={e}>{ENV_LABEL[e]}</option>)}
                </select></label>
              {env !== "none" && <label><span>Noise level</span>
                <div className="seg">{["light", "medium", "heavy"].map((x) => <button key={x} className={intensity === x ? "on" : ""} onClick={() => setIntensity(x)}>{x}</button>)}</div></label>}
              <label><span>Max turns <b className="mono">{turns}</b></span>
                <input type="range" min={2} max={8} value={turns} onChange={(e) => setTurns(+e.target.value)} className="range" /></label>
              <label><span>Agent version</span>
                <div className="seg">
                  <button className={hardening === "live" ? "on" : ""} onClick={() => setHardening("live")}>Live · v{live?.version ?? "…"}</button>
                  <button className={hardening === "original" ? "on" : ""} onClick={() => setHardening("original")}>Original · v{original?.version ?? (tid === "bank" ? 1 : 0)}</button>
                </div></label>
              <button className={`toggle ${shield ? "on" : ""}`} onClick={() => setShield(!shield)} aria-pressed={shield}>
                <span><b>Kavach Shield</b><small>{tid === "saakshi" ? "Runs inside Saakshi via the Shield API" : "Sits in front of the bot as a proxy"}</small></span>
                <i aria-hidden />
              </button>
            </div>
          </Panel>

          <Panel title="Summary">
            <dl className="kv">
              <dt>Agent</dt><dd>{t.agent} · {hardening === "live" ? `live v${live?.version ?? "…"}` : "original"}</dd>
              <dt>Attacker</dt><dd>{p.name.replace(/^The /, "")} <span className="faint">· Timbre “{p.voice}”</span></dd>
              <dt>Objective</dt><dd>{o.name} <Sev level={o.severity} /></dd>
              <dt>Line</dt><dd>{LANG[lang]} · {ENV_LABEL[env]}{env !== "none" ? `, ${intensity}` : ""}</dd>
              <dt>Defences</dt><dd>{shield ? <span className="pill shield">Kavach Shield on</span> : <span className="faint">agent only</span>}</dd>
            </dl>
            <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: 16, height: 40 }} onClick={go} disabled={blocked}>
              {busy ? <><span className="spinner" /> Dialling</> : running ? "Another simulation is running" : meta.quota.left <= 0 ? "Daily budget used" : <><Icon name="play" size={14} />Launch simulation</>}
            </button>
            {running && <p className="small faint" style={{ margin: "10px 0 0" }}>One simulation at a time. <Link className="link" to={`/call/${running}`}>Watch the running one</Link></p>}
            <p className="small faint" style={{ margin: "10px 0 0" }}>{meta.quota.left} of {meta.quota.daily} simulations left today · about 1–2 minutes</p>
            {(!meta.ready.gnani || !meta.ready.llm) && <p className="error-line">Add GNANI_API_KEY and GROQ_API_KEY to .env</p>}
            {err && <p className="error-line" role="alert">{err}</p>}
          </Panel>
        </div>
      </div>
    </div>
  );
}
