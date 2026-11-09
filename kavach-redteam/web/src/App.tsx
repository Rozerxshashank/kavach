import { createContext, useContext, useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, creds, type Meta, type Run, type TargetPublic } from "./api";
import { Icon } from "./components/ui";
import { LogoMark } from "./components/Logo";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import Findings from "./pages/Findings";
import Arena from "./pages/Arena";
import Call from "./pages/Call";
import Live from "./pages/Live";
import Reports from "./pages/Reports";
import Report from "./pages/Report";
import Lab from "./pages/Lab";
import Shield from "./pages/Shield";
import Demo from "./pages/Demo";
import Film from "./pages/Film";
import "./console.css";

const MetaCtx = createContext<Meta | null>(null);
export const useMeta = () => useContext(MetaCtx);

/** The target a run attacked (older runs, before targets existed, were all the bank bot). */
export function targetOf(meta: Meta | null, run: Pick<Run, "target"> | null | undefined): TargetPublic | undefined {
  return meta?.targets[run?.target || "bank"];
}

const CRUMBS: [RegExp, string, string][] = [
  [/^\/$/, "Overview", ""],
  [/^\/findings/, "Findings", "Red team"],
  [/^\/(arena|simulate)/, "New simulation", "Red team"],
  [/^\/(simulations|reports)\/./, "Simulation report", "Red team"],
  [/^\/(simulations|reports)/, "Simulations", "Red team"],
  [/^\/call\//, "Live simulation", "Red team"],
  [/^\/live/, "Live test", "Red team"],
  [/^\/shield/, "Kavach Shield", "Runtime protection"],
  [/^\/targets/, "Agents", "Assets"],
  [/^\/about/, "About Kavach", ""],
];

/** Presentation mode (?present, remembered for the tab): the console without its developer chrome, for recordings. */
function presenting(): boolean {
  try {
    const q = new URLSearchParams(location.search);
    if (q.has("present")) sessionStorage.setItem("kv-present", q.get("present") === "0" ? "" : "1");
    return !!sessionStorage.getItem("kv-present");
  } catch { return false; }
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [down, setDown] = useState(false);
  const [open, setOpen] = useState(false);
  const loc = useLocation();

  useEffect(() => {
    const load = () => api.meta().then((m) => { setMeta(m); setDown(false); }).catch(() => setDown(true));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { window.scrollTo(0, 0); setOpen(false); }, [loc.pathname]);

  const crumb = CRUMBS.find(([rx]) => rx.test(loc.pathname)) ?? [null, "Kavach", ""];

  if (loc.pathname.startsWith("/film")) {
    return <div className="console"><Film /></div>;
  }
  if (loc.pathname.startsWith("/demo")) {
    // the recording page: full screen, no console chrome
    return <MetaCtx.Provider value={meta}><div className="console demo-shell"><Demo /></div></MetaCtx.Provider>;
  }

  return (
    <MetaCtx.Provider value={meta}>
      <div className={`console ${open ? "open" : ""} ${presenting() ? "present" : ""}`}>
        <Sidebar meta={meta} down={down} />
        {open && <div className="scrim" onClick={() => setOpen(false)} />}
        <div className="main">
          <header className="topbar">
            <button className="side-toggle" onClick={() => setOpen(!open)} aria-label="Menu"><Icon name="menu" /></button>
            <div className="crumbs">{crumb[2] && <><span>{crumb[2]}</span><span>/</span></>}<b>{crumb[1]}</b></div>
            <div className="topbar-r">
              {meta?.running && <Link to={`/call/${meta.running}`} className="pill attack"><span className="state running" />simulation running</Link>}
              {meta && <span className="env-chip dev-only" title="Attack simulations left today (protects the speech and model quotas)">budget {meta.quota.left}/{meta.quota.daily}</span>}
              <Link to="/arena" className="btn btn-primary btn-sm"><Icon name="plus" size={14} />New simulation</Link>
            </div>
          </header>
          <main className="content">
            {down && <div className="callout bad" style={{ marginBottom: 16 }}>Can't reach the Kavach API. Start it with ./run.sh in kavach-redteam/.</div>}
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/about" element={<Home />} />
              <Route path="/findings" element={<Findings />} />
              <Route path="/arena" element={<Arena />} />
              <Route path="/simulate" element={<Navigate to="/arena" replace />} />
              <Route path="/call/:id" element={<Call />} />
              <Route path="/live" element={<Live />} />
              <Route path="/simulations" element={<Reports />} />
              <Route path="/simulations/:id" element={<Report />} />
              <Route path="/reports" element={<Navigate to="/simulations" replace />} />
              <Route path="/reports/:id" element={<Report />} />
              <Route path="/shield" element={<Shield />} />
              <Route path="/targets" element={<Navigate to="/targets/saakshi" replace />} />
              <Route path="/targets/:id" element={<Lab />} />
              <Route path="/lab" element={<Navigate to="/targets/bank" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </MetaCtx.Provider>
  );
}

function Sidebar({ meta, down }: { meta: Meta | null; down: boolean }) {
  const loc = useLocation();
  const shieldTab = new URLSearchParams(loc.search).get("tab") ?? "monitor";
  const sub = (tab: string) => loc.pathname === "/shield" && shieldTab === tab ? "active" : "";
  return (
    <aside className="side" aria-label="Kavach">
      <Link to="/" className="side-brand">
        <LogoMark size={34} className="side-logo" />
        <span><b>Kavach</b><span>Voice agent security</span></span>
      </Link>
      <NavLink to="/" end><Icon name="overview" />Overview</NavLink>

      <p className="side-sec">Red team</p>
      <NavLink to="/simulations"><Icon name="list" />Simulations</NavLink>
      <NavLink to="/findings"><Icon name="alert" />Findings</NavLink>
      <NavLink to="/arena"><Icon name="target" />New simulation</NavLink>
      <NavLink to="/live"><Icon name="mic" />Live test</NavLink>
      <NavLink to="/demo" className="dev-only"><Icon name="play" />Demo walkthrough</NavLink>

      <p className="side-sec">Runtime protection</p>
      <Link to="/shield" className={sub("monitor")}><Icon name="shield" />Shield monitor</Link>
      <Link to="/shield?tab=test" className={sub("test")}><Icon name="play" />Test console</Link>
      <Link to="/shield?tab=policies" className={sub("policies")}><Icon name="policy" />Policies</Link>
      <Link to="/shield?tab=integrate" className={sub("integrate")}><Icon name="key" />Integration &amp; keys</Link>

      <p className="side-sec">Assets</p>
      {Object.values(meta?.targets ?? {}).map((t) => (
        <NavLink key={t.id} to={`/targets/${t.id}`}><Icon name="agent" />{t.agent}<span className="count dev-only">{t.id === "saakshi" ? "prod" : "demo"}</span></NavLink>
      ))}

      <div className="side-foot">
        <span className="svc"><i className={!meta?.ready.gnani || down ? "off" : ""} />Gnani Timbre<span>TTS</span></span>
        <span className="svc"><i className={!meta?.ready.gnani || down ? "off" : ""} />Gnani Prisma<span>STT</span></span>
        <span className="svc"><i className={!meta?.ready.llm || down ? "off" : ""} />Reasoning<span>Groq</span></span>
        <span className="svc"><i className={down ? "off" : ""} />Kavach Shield<span>API</span></span>
        <div className="spread" style={{ marginTop: 4 }}>
          <Link to="/about" className="link" style={{ fontSize: 12 }}>About Kavach</Link>
          <span className="dev-only"><OperatorKey operator={!!meta?.operator} /></span>
        </div>
      </div>
    </aside>
  );
}

function OperatorKey({ operator }: { operator: boolean }) {
  const ask = () => {
    const k = prompt("Operator key (KAVACH_ADMIN_KEY). Leave empty to sign out.");
    if (k === null) return;
    creds.setAdmin(k.trim());
    location.reload();
  };
  return <button className="link" onClick={ask} style={{ fontSize: 12 }}>{operator ? "Operator ✓" : "Operator sign-in"}</button>;
}
