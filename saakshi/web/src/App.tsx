import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";
import { meta } from "./lib/api";
import Landing from "./pages/Landing";
import Demo from "./pages/Demo";
import ConsolePage from "./pages/Console";
import PassportPage from "./pages/Passport";
import { Certificate, PublicPassport } from "./pages/Public";
import { PhoneFrame } from "./components/bits";
import { WorkerApp } from "./pages/WorkerApp";
import { EmployerPhone } from "./pages/EmployerPhone";
import Start from "./pages/Start";
import Confirm from "./pages/Confirm";
import { auth } from "./lib/auth";

export default function App() {
  const [ready, setReady] = useState<{ gnani: boolean; llm: boolean; telephony: boolean } | null>(null);
  const [down, setDown] = useState(false);
  const loc = useLocation();
  useEffect(() => { meta().then((m) => setReady(m.ready)).catch(() => setDown(true)); }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
    // on a phone the nav scrolls sideways: keep the current page's link in view
    requestAnimationFrame(() => {
      const el = document.querySelector<HTMLElement>(".nav-links a.active");
      const bar = el?.parentElement;
      if (el && bar) bar.scrollLeft = el.offsetLeft - bar.offsetLeft - (bar.clientWidth - el.clientWidth) / 2;
    });
  }, [loc.pathname]);
  const bare = loc.pathname.startsWith("/p/") || loc.pathname.startsWith("/c/");
  // the worker's own app: on a phone it takes the whole screen (no site nav, no footer)
  const appMode = loc.pathname.startsWith("/w/") || loc.pathname.startsWith("/worker/");

  return (
    <>
      {!bare && (
        <header className={`nav ${appMode ? "hide-on-phone" : ""}`}>
          <div className="wrap">
            <NavLink to="/" className="brand" aria-label="Saakshi home">
              <span className="brand-mark"><svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 3h10M2 7h10M2 11h6" stroke="#fbf3ee" strokeWidth="1.6" strokeLinecap="round" /></svg></span>
              <b>Saakshi</b><span>साक्षी</span>
            </NavLink>
            <nav className="nav-links">
              <NavLink to={auth.me() ? `/w/${auth.me()}` : "/start"}>{auth.me() ? "My record" : "Start"}</NavLink>
              <NavLink to="/demo">Live demo</NavLink>
              <NavLink to="/console">Witness desk</NavLink>
            </nav>
            <div className="nav-right" title="Gnani speech services configured on the server">
              <span><i className={`dot ${!ready?.gnani || down ? "off" : ""}`} />Timbre</span>
              <span><i className={`dot ${!ready?.gnani || down ? "off" : ""}`} />Prisma</span>
              <span title={ready?.telephony ? "Real calls via Twilio" : "Set TWILIO_* and SAAKSHI_PUBLIC_URL to enable real calls"}>
                <i className={`dot ${ready?.telephony ? "" : "idle"}`} />Phone line</span>
            </div>
          </div>
        </header>
      )}
      {down && <p className="wrap error-line" style={{ paddingTop: 16 }}>Can't reach the Saakshi server. Start it with ./run.sh in the saakshi folder.</p>}
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/console" element={<ConsolePage />} />
        <Route path="/passport/:id" element={<PassportPage />} />
        <Route path="/p/:token" element={<PublicPassport />} />
        <Route path="/bocw/:id" element={<Certificate />} />
        <Route path="/worker/:id" element={<SoloWorker />} />
        <Route path="/w/:id" element={<SoloWorker />} />
        <Route path="/start" element={<Start />} />
        <Route path="/c/:token" element={<Confirm />} />
        <Route path="/phone" element={<main className="solo"><PhoneFrame label="Employer's phone" tone="dark"><EmployerPhone /></PhoneFrame></main>} />
      </Routes>
      {!bare && (
        <footer className={`foot ${appMode ? "hide-on-phone" : ""}`}>
          <div className="wrap">
            <span>Saakshi · voice-verified work records for informal workers</span>
            <span className="mono">speech: Gnani timbre-v2.5 + prisma-v2.5</span>
            <span>Built for the Gnani.ai All-India Internship Challenge</span>
          </div>
        </footer>
      )}
    </>
  );
}

function SoloWorker() {
  const { id = "" } = useParams();
  return <main className="solo app-solo"><PhoneFrame label="Worker's phone"><WorkerApp workerId={id} /></PhoneFrame></main>;
}
