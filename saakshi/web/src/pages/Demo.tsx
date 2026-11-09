import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, meta, type Worker } from "../lib/api";
import { useStream } from "../lib/util";
import { PhoneFrame, QR } from "../components/bits";
import { WorkerApp } from "./WorkerApp";
import { EmployerPhone } from "./EmployerPhone";
import { ActivityLog, CallQueue, OperatorGate } from "./Console";
import { employerSay, sleep, waitIdle, workerSay } from "../lib/director";
import { player } from "../lib/player";

const WORKER_LINES = [
  "इस महीने वर्मा जी के यहाँ खाना बनाया, पौने पाँच हज़ार मिले, उनका नंबर नौ आठ एक एक दो दो तीन तीन चार चार है",
  "Mehta ji ke yahan dhai hazaar, aur Gupta madam ke yahan saade teen hazaar, dono is mahine",
  "नहीं, वर्मा जी के यहाँ पाँच हज़ार थे",
  "हाँ, सही है",
  "मेरा रिकॉर्ड सुनाओ",
];

type Step = { cap: string; run: (ctx: { ring: () => Promise<boolean> }) => Promise<boolean | void> | void };

const STORY: Step[] = [
  { cap: "Sunita tells Saakshi about a new job, in Hindi, with her employer's number said in words.", run: () => workerSay(WORKER_LINES[0], true) },
  { cap: "Saakshi read it back, number and all. Sunita says yes: the record is saved and a WhatsApp link is ready.", run: () => workerSay("हाँ, सही है", true) },
  { cap: "Now Saakshi phones Sharma ji, to confirm an older record of hers.", run: ({ ring }) => ring() },
  { cap: "Sharma ji picks up. Saakshi introduces herself and asks if she may explain.", run: () => employerSay("__accept__") },
  { cap: "He agrees. Saakshi reads out exactly what Sunita claimed.", run: () => employerSay("हाँ बोलिए", true) },
  { cap: "He asks a question. Saakshi answers it from the record, then asks again, briefly.", run: () => employerSay("वो मेरे यहाँ क्या काम करती है?", true) },
  { cap: "He confirms. His spoken “yes” is the evidence: Sunita's record is now L1, employer confirmed.", run: () => employerSay("हाँ, सही है", true) },
];

/** The judge's view: the worker's phone, the witness desk, and the employer's phone, side by side. */
export default function Demo() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [wid, setWid] = useState<string>("");
  const [seeding, setSeeding] = useState(false);
  const [err, setErr] = useState("");
  const [hotline, setHotline] = useState<string | null>(null);
  const [lanIp, setLanIp] = useState<string | null>(null);
  const [showPhone, setShowPhone] = useState(false);
  const [step, setStep] = useState(-1);          // autopilot: -1 idle, STORY.length = finished
  const [note, setNote] = useState("");
  const run = useRef<{ stopped: boolean }>({ stopped: true });
  useEffect(() => { meta().then((m) => { setHotline(m.hotline); setLanIp(m.lan_ip); }).catch(() => {}); }, []);
  useEffect(() => () => { run.current.stopped = true; }, []);
  // phone-test mode (npm run dev:phone) serves HTTPS on port 5175; phones need HTTPS for the microphone
  const phoneUrl = lanIp ? (location.protocol === "https:" ? `https://${lanIp}:${location.port}/start` : `https://${lanIp}:5175/start`) : null;
  const sunita = workers.find((w) => w.name.startsWith("Sunita"));

  const load = useCallback(async () => {
    try {
      const ws = await api.workers();
      setWorkers(ws);
      setWid((cur) => (cur && ws.some((w) => w.id === cur) ? cur : ws.find((w) => w.name.startsWith("Sunita"))?.id ?? ws[0]?.id ?? ""));
    } catch (e) { setErr((e as Error).message); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => { if (e.type === "world.changed") void load(); });

  const seed = async () => {
    setSeeding(true); setErr("");
    try { await api.seed(); await load(); } catch (e) { setErr((e as Error).message); } finally { setSeeding(false); }
  };

  const ring = async () => {
    const calls = await api.calls();
    const c = calls.find((x) => x.status === "queued" && x.employer?.name.startsWith("Sharma"))
      ?? calls.find((x) => x.status === "queued" && (x.workers ?? []).length === 1);
    if (!c) { setNote("No call left in the queue. Press “Reset demo world” to replay the call."); return false; }
    await api.ring(c.id, "human");
    await sleep(2600);                                    // the employer's phone rings
    return true;
  };

  const play = async () => {
    if (!run.current.stopped) { run.current.stopped = true; player.stop(); setStep(-1); return; }
    if (!sunita) return;
    player.unlock();
    const me = { stopped: false };
    run.current = me;
    setNote("");
    if (wid !== sunita.id) { setWid(sunita.id); await sleep(1500); }
    for (let i = 0; i < STORY.length; i++) {
      if (me.stopped) return;
      setStep(i);
      const ok = await STORY[i].run({ ring });
      if (ok === false) { me.stopped = true; setStep(-1); return; }
      await waitIdle(me);
      await sleep(500);
    }
    if (!me.stopped) setStep(STORY.length);
    me.stopped = true;
  };
  const playing = step >= 0 && step < STORY.length;

  return (
    <main className="demo">
      <div className="demo-top wrap">
        <div>
          <p className="eyebrow">Live demo · real Gnani speech, real records</p>
          <h1 className="h2">Watch a record <em>become proof.</em></h1>
          {hotline && <p className="hotline">Or call from any phone to log work: <b className="mono">{hotline}</b></p>}
        </div>
        <div className="demo-actions">
          {sunita && (
            <button className={`btn ${playing ? "btn-ink" : "btn-primary"}`} onClick={play}>
              {playing ? <>■ Stop</> : <><svg width="14" height="14" viewBox="0 0 24 24"><path d="M7 4v16l13-8z" fill="currentColor" /></svg> Play the whole story</>}
            </button>
          )}
          {workers.length > 0 && (
            <select className="select" value={wid} onChange={(e) => setWid(e.target.value)} aria-label="Worker" disabled={playing}>
              {workers.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          )}
          <button className="btn btn-ghost btn-sm" onClick={seed} disabled={seeding || playing}>{seeding ? <><span className="spinner" /> Building</> : workers.length ? "Reset demo world" : "Build demo world"}</button>
          {phoneUrl && (
            <div className="demo-pop-wrap">
              <button className="btn btn-ghost btn-sm" onClick={() => setShowPhone((x) => !x)} aria-expanded={showPhone}>On your phone</button>
              {showPhone && (
                <div className="demo-pop sheet">
                  <QR text={phoneUrl} size={132} />
                  <p className="small">Same WiFi, then scan. Phones allow the microphone only over HTTPS, so
                    {location.protocol === "https:" ? " this page is already in phone mode." : <> first run <code>npm run dev:phone</code> in <code>saakshi/web</code>.</>}
                    {" "}Accept the certificate warning once.</p>
                  <p className="mono small faint">{phoneUrl}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {err && <div className="wrap"><OperatorGate error={err} onSet={() => { setErr(""); void load(); }} /></div>}

      {workers.length > 0 && (step >= 0 ? (
        <div className="wrap demo-caption" aria-live="polite">
          <div className="demo-caption-dots">{STORY.map((_, i) => <i key={i} className={i < step ? "done" : i === step ? "now" : ""} />)}</div>
          <p className="demo-caption-text">
            {step < STORY.length ? STORY[step].cap : <>That's the whole loop. <Link className="link" to={`/passport/${sunita?.id}`}>Open Sunita's passport</Link> to see the proof, or play again.</>}
          </p>
          {step >= STORY.length && <button className="link small" onClick={() => setStep(-1)}>Close</button>}
        </div>
      ) : (
        <ol className="wrap demo-steps">
          <li>
            <span className="demo-n num">1</span>
            <div>
              <p className="demo-step-t">Speak as the worker</p>
              <p className="small muted">Tap Start on her phone and talk, or send a line:</p>
              <div className="demo-chips">{WORKER_LINES.map((l) => <button key={l} onClick={() => workerSay(l)} title={l}>{l}</button>)}</div>
            </div>
          </li>
          <li>
            <span className="demo-n num">2</span>
            <div>
              <p className="demo-step-t">Answer as the employer</p>
              <p className="small muted">Press <b>☎ Ring phone</b> on the desk and pick up. Ask what the money is for, doubt it, correct it, or say “call me tomorrow”.</p>
            </div>
          </li>
          <li>
            <span className="demo-n num">3</span>
            <div>
              <p className="demo-step-t">See the proof</p>
              <p className="small muted">
                <Link className="link" to={`/passport/${wid}`}>Passport</Link> · <Link className="link" to="/console?tab=graph">fraud ring</Link> · <Link className="link" to="/console?tab=redteam">red team</Link>
              </p>
            </div>
          </li>
        </ol>
      ))}
      {note && <p className="wrap small" style={{ color: "var(--wait)" }}>{note}</p>}

      {!workers.length && !err ? (
        <div className="wrap demo-empty">
          <p className="h2">Start with a neighbourhood.</p>
          <p className="muted">Creates Sunita (a domestic worker in four homes), Bablu Thekedar's construction crew, and one fraud ring for the trust engine to find.</p>
          <button className="btn btn-primary" onClick={seed} disabled={seeding}>{seeding ? "Building…" : "Build demo world"}</button>
        </div>
      ) : (
        <div className="demo-grid">
          <PhoneFrame label="① Worker's phone">{wid && <WorkerApp key={wid} workerId={wid} />}</PhoneFrame>
          <section className="demo-desk sheet">
            <p className="eyebrow">② Saakshi · the witness desk</p>
            <CallQueue compact />
            <p className="eyebrow" style={{ margin: "20px 0 6px" }}>Activity</p>
            <ActivityLog limit={10} />
          </section>
          <PhoneFrame label="③ Employer's phone" tone="dark"><EmployerPhone /></PhoneFrame>
        </div>
      )}
    </main>
  );
}
