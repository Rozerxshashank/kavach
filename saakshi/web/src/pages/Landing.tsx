import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { api, type Hello, type Stats, type Story, type StoryTurn } from "../lib/api";
import { player } from "../lib/player";
import { LANGS } from "../lib/i18n";
import { inr } from "../lib/util";
import "./landing.css";

export default function Landing() {
  const [stats, setStats] = useState<Stats | null>(null);
  useEffect(() => { api.stats().then(setStats).catch(() => {}); }, []);
  useEffect(() => () => player.stop(), []);

  return (
    <main className="ld">
      <section className="wrap ld-hero">
        <div className="ld-hero-copy">
          <p className="eyebrow">For India's informal workers · voice by Gnani Timbre + Prisma</p>
          <h1 className="display ld-title">30 crore people work every day with <em>no proof</em> that they do.</h1>
          <p className="lede">
            A maid, a mason, a driver: paid in cash or a UPI ping, with no payslip. So the bank says no and the moneylender
            charges 40%. <b>Saakshi</b> (साक्षी, “witness”) listens to a worker, calls the people she worked for, and turns
            their spoken “haan, sahi hai” into proof of income she owns.
          </p>
          <div className="ld-cta">
            <Link to="/start" className="btn btn-primary">Start your record →</Link>
            <Link to="/demo" className="btn btn-ghost">Try the live demo</Link>
          </div>
          <p className="ld-langline">{LANGS.map((l) => <span key={l.code}>{l.native}</span>)}</p>
        </div>
        <StoryPlayer />
      </section>

      <LiveNumbers stats={stats} />

      <section className="wrap ld-section">
        <SectionHead kicker="How a record becomes proof" title={<>No forms. <em>Just talk.</em></>} />
        <ol className="ld-flow">
          {FLOW.map((f, i) => (
            <li key={f.t}>
              <span className="ld-flow-icon"><Icon name={f.icon} /></span>
              <span className="ld-flow-n mono">0{i + 1} · {f.model}</span>
              <p className="h3">{f.t}</p>
              <p className="muted small">{f.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <LanguageWall />

      <Pipeline stats={stats} />

      <section className="wrap ld-section">
        <SectionHead kicker="Evidence a lender can read" title={<>Not one score. <em>Four levels of proof.</em></>}
          sub="Every record says how strongly it is backed, and why. A bank chooses the level it needs." />
        <div className="ld-levels">
          {LEVELS.map((l, i) => (
            <div key={l.k} className={`ld-level l${i}`}>
              <div className="ld-level-bar"><i style={{ height: `${28 + i * 24}%` }} /></div>
              <p className="mono small">{l.k}</p>
              <p className="h3">{l.t}</p>
              <p className="muted small">{l.d}</p>
              {stats && <p className="ld-level-n num">{stats.levels[String(i)] ?? 0} <span className="small faint">records today</span></p>}
            </div>
          ))}
        </div>
      </section>

      <section className="wrap ld-section">
        <SectionHead kicker="What the proof opens" title={<>One record. <em>Many doors.</em></>} />
        <div className="ld-doors">
          {DOORS.map((d) => (
            <div key={d.t}>
              <span className="ld-door-icon"><Icon name={d.icon} /></span>
              <p className="h3">{d.t}</p>
              <p className="muted small">{d.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="ld-final">
        <div className="wrap ld-final-in">
          <div>
            <p className="eyebrow" style={{ color: "rgba(251,243,238,.7)" }}>Free · no app to install · works on any phone</p>
            <h2 className="h1">Her work already happened.<br /><em>Now it counts.</em></h2>
          </div>
          <div className="ld-cta">
            <Link to="/start" className="btn ld-btn-light">Start your record →</Link>
            <Link to="/demo" className="btn ld-btn-outline">Watch it work</Link>
          </div>
        </div>
      </section>
    </main>
  );
}

/* ---- the hero: a real conversation, voiced by Timbre and heard by Prisma --------------------- */
const WHO: Record<StoryTurn["who"], string> = { worker: "Sunita · worker", saakshi: "Saakshi", employer: "Mehta ji · employer" };

function StoryPlayer() {
  const [lang, setLang] = useState<"hi-IN" | "en-IN">("hi-IN");
  const [story, setStory] = useState<Story | null>(null);
  const [err, setErr] = useState(false);
  const [idx, setIdx] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const run = useRef(0);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    setStory(null); setErr(false); setIdx(-1);
    const load = (tries: number) => api.story(lang).then((s) => alive && setStory(s)).catch(() => {
      if (!alive) return;
      if (tries > 0) setTimeout(() => load(tries - 1), 4000); else setErr(true);
    });
    load(8);
    return () => { alive = false; run.current++; player.stop(); };
  }, [lang]);
  useEffect(() => { logRef.current?.scrollTo({ top: 1e6, behavior: "smooth" }); }, [idx]);

  const play = async () => {
    if (!story) return;
    if (playing) { run.current++; player.stop(); setPlaying(false); return; }
    player.unlock();
    const me = ++run.current;
    setPlaying(true);
    for (let i = 0; i < story.turns.length; i++) {
      if (run.current !== me) return;
      setIdx(i);
      const t = story.turns[i];
      await player.play(t.audio.url, t.who === "employer" ? "employer" : t.who === "worker" ? "worker" : "saakshi");
      await new Promise((r) => setTimeout(r, 250));
    }
    if (run.current === me) setPlaying(false);
  };

  const shown = story ? (idx < 0 ? [] : story.turns.slice(0, idx + 1)) : [];
  const n = story?.turns.length ?? 8;
  const stage = idx < 2 ? "draft" : idx < n - 1 ? "calling" : "verified";
  const done = !playing && idx === n - 1;

  return (
    <div className="ld-story sheet">
      <div className="ld-story-head">
        <div>
          <p className="eyebrow">Listen · a record becomes proof</p>
          <p className="small faint" style={{ margin: "2px 0 0" }}>Real audio from Gnani's APIs, not a recording of us</p>
        </div>
        <div className="seg">
          <button className={lang === "hi-IN" ? "on" : ""} onClick={() => setLang("hi-IN")}>हिन्दी</button>
          <button className={lang === "en-IN" ? "on" : ""} onClick={() => setLang("en-IN")}>English</button>
        </div>
      </div>

      <div className="ld-story-log" ref={logRef}>
        {!shown.length && (
          <div className="ld-story-empty">
            <button className="ld-play" onClick={play} disabled={!story} aria-label="Play the conversation">
              {story ? <svg width="26" height="26" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" fill="currentColor" /></svg> : <span className="spinner light" />}
            </button>
            <p className="h3">{story ? "Press play" : err ? "Voice is warming up" : "Voicing the conversation…"}</p>
            <p className="small muted" style={{ maxWidth: 300 }}>
              {err ? "Gnani's API is busy right now. Reload in a moment." : "Sunita logs a month of work by voice. Saakshi reads it back, calls her employer, answers his question, and the record turns green."}
            </p>
          </div>
        )}
        {shown.map((t, i) => (
          <div key={i}>
            {i === 3 && <p className="ld-story-scene mono">☎ Saakshi calls Mehta ji</p>}
            <div className={`ld-turn ${t.who} ${i === idx && playing ? "now" : ""}`}>
              <p className="ld-turn-who mono">{WHO[t.who]} <span className="faint">· Timbre “{t.voice}”</span></p>
              <p className="ld-turn-text">{t.text}</p>
              {i === idx && playing && <TurnProgress peaks={t.audio.peaks} />}
              {t.heard && (
                <p className="ld-heard mono">
                  <span>Prisma heard</span> “{t.heard}” <span className="faint">· {t.prisma_ms} ms</span>
                </p>
              )}
              {t.parsed_amount && <p className="ld-parsed mono">✓ Saakshi's number rules read “{t.parsed_from}” as {inr(t.parsed_amount)}</p>}
            </div>
          </div>
        ))}
      </div>

      <div className={`ld-entry ${stage}`}>
        <div>
          <p className="ld-entry-who">Mehta ji</p>
          <p className="small faint" style={{ margin: 0 }}>Cooking · this month</p>
        </div>
        <p className="num ld-entry-amt">₹4,750</p>
        <span className={`ld-entry-state ${stage}`}>
          {idx < 0 ? "Not recorded yet" : stage === "draft" ? "Draft · read back" : stage === "calling" ? "Saved · confirming…" : "✓ L1 · confirmed by voice"}
        </span>
        {(shown.length > 0 || done) && (
          <button className="ld-replay" onClick={play} aria-label={playing ? "Stop" : "Play again"}>{playing ? "■" : "↺"}</button>
        )}
      </div>
    </div>
  );
}

function TurnProgress({ peaks }: { peaks: number[] }) {
  const [p, setP] = useState(0);
  useEffect(() => {
    let raf = 0;
    const tick = () => { setP(player.progress); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <span className="ld-bars" aria-hidden>
      {peaks.map((v, i) => <i key={i} style={{ height: `${18 + v * 82}%`, opacity: i / peaks.length <= p ? 1 : 0.25 }} />)}
    </span>
  );
}

/* ---- live numbers ---------------------------------------------------------------------------- */
function LiveNumbers({ stats }: { stats: Stats | null }) {
  const mins = stats ? Math.round((stats.gnani.timbre.audio_seconds + stats.gnani.prisma.audio_seconds) / 60) : 0;
  const items = stats ? [
    [inr(stats.verified_income_monthly), "verified monthly income on record"],
    [String(stats.verified), "records confirmed by employers"],
    [String(stats.employers_confirmed), "employers who said “sahi hai”"],
    [String(stats.flagged_workers), "accounts caught faking records"],
    [`${mins} min`, "of speech through Timbre + Prisma"],
  ] : [];
  return (
    <section className="ld-numbers">
      <div className="wrap">
        <p className="eyebrow"><i className="dot" /> Live from this server</p>
        <div className="ld-numbers-row">
          {stats ? items.map(([v, l]) => (
            <div key={l}><span className="num">{v}</span><span className="small">{l}</span></div>
          )) : Array.from({ length: 5 }, (_, i) => <div key={i}><span className="num ld-skel">₹00,000</span><span className="small">&nbsp;</span></div>)}
        </div>
      </div>
    </section>
  );
}

/* ---- nine languages, each one tap away --------------------------------------------------------- */
function LanguageWall() {
  const [sel, setSel] = useState<string | null>(null);
  const [hello, setHello] = useState<Record<string, Hello>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const who = useSyncExternalStore(player.subscribe, () => player.who);

  const tap = async (code: string) => {
    player.unlock();
    setSel(code); setErr("");
    let h = hello[code];
    if (!h) {
      setLoading(code);
      try { h = await api.hello(code); setHello((x) => ({ ...x, [code]: h })); }
      catch { setErr("Gnani is busy right now; tap again in a moment."); setLoading(null); return; }
      setLoading(null);
    }
    void player.play(h.audio.url, "saakshi");
  };
  const h = sel ? hello[sel] : null;

  return (
    <section className="wrap ld-section">
      <SectionHead kicker="Gnani Timbre speaks · Gnani Prisma listens" title={<>She chooses the language. <em>Saakshi follows.</em></>}
        sub="Every language below was checked end to end: Timbre speaks it, and Prisma hears it back. Tap one to hear Saakshi." />
      <div className="ld-langs">
        <div className="ld-lang-grid">
          {LANGS.map((l) => (
            <button key={l.code} className={`ld-lang ${sel === l.code ? "on" : ""}`} onClick={() => tap(l.code)}>
              <b>{l.native}</b>
              <span className="small">{l.english}</span>
              <span className="ld-lang-play">{loading === l.code ? <span className="spinner" /> : sel === l.code && who === "saakshi" ? "■" : "▶"}</span>
            </button>
          ))}
        </div>
        <div className="ld-lang-out">
          {h ? (
            <>
              <p className="eyebrow">Timbre said · {h.timbre_ms} ms</p>
              <p className="ld-lang-text">{h.text}</p>
              <p className="eyebrow" style={{ marginTop: 18 }}>Prisma heard it back · {h.prisma_ms} ms</p>
              <p className="ld-lang-heard mono">{h.heard}</p>
            </>
          ) : (
            <p className="muted">{err || (loading ? "Asking Timbre…" : "Pick a language. You'll hear Timbre speak it, then see what Prisma heard back.")}</p>
          )}
        </div>
      </div>
    </section>
  );
}

/* ---- the pipeline, with real latencies ------------------------------------------------------- */
function Pipeline({ stats }: { stats: Stats | null }) {
  const t = stats?.gnani.timbre, p = stats?.gnani.prisma;
  const ms = (v?: number | null) => (v ? `${(v / 1000).toFixed(1)} s median` : "—");
  return (
    <section className="wrap ld-section">
      <SectionHead kicker="Gnani AI models in Saakshi" title={<>Ears, a brain, <em>and a voice.</em></>}
        sub="Everything a person says or hears passes through Gnani. The language model understands and answers; code checks every number." />
      <div className="ld-pipe">
        <div className="ld-pipe-node edge"><Icon name="mic" /><p className="small">A worker or employer speaks</p></div>
        <span className="ld-pipe-arrow" aria-hidden />
        <div className="ld-pipe-node gnani">
          <p className="mono small">Gnani Prisma · prisma-v2.5</p>
          <p className="h3">The ears</p>
          <p className="small muted">Speech to text in nine languages: noisy kitchens, building sites and 8 kHz phone lines, including numbers said in words.</p>
          <p className="ld-pipe-stat mono">{p ? `${p.calls} calls · ${ms(p.median_ms)}` : "…"}</p>
        </div>
        <span className="ld-pipe-arrow" aria-hidden />
        <div className="ld-pipe-node brain">
          <p className="mono small">Groq · gpt-oss-120b</p>
          <p className="h3">The brain</p>
          <p className="small muted">Understands what was meant and answers questions. Every amount, date and phone number is then re-checked by code.</p>
        </div>
        <span className="ld-pipe-arrow" aria-hidden />
        <div className="ld-pipe-node gnani">
          <p className="mono small">Gnani Timbre · timbre-v2.5</p>
          <p className="h3">The voice</p>
          <p className="small muted">Reads every record back before saving, makes the confirmation call, and explains the request on the employer's link.</p>
          <p className="ld-pipe-stat mono">{t ? `${t.calls} lines spoken · ${ms(t.median_ms)}` : "…"}</p>
        </div>
        <span className="ld-pipe-arrow" aria-hidden />
        <div className="ld-pipe-node edge"><Icon name="speaker" /><p className="small">They hear it, in their language</p></div>
      </div>
    </section>
  );
}

function SectionHead({ kicker, title, sub }: { kicker: string; title: React.ReactNode; sub?: string }) {
  return (
    <div className="ld-head">
      <p className="eyebrow">{kicker}</p>
      <h2 className="h1">{title}</h2>
      {sub && <p className="lede">{sub}</p>}
    </div>
  );
}

const FLOW = [
  { icon: "mic", model: "Prisma", t: "She says it", d: "“Is mahine Mehta ji ke yahan, paune paanch hazaar.” Several homes in one breath, in her own language." },
  { icon: "check", model: "Timbre", t: "Saakshi reads it back", d: "Nothing is saved until she hears it and says “haan”. Anything missing is asked, one thing at a time." },
  { icon: "phone", model: "Timbre + Prisma", t: "The employer confirms", d: "By a free WhatsApp link or a call. Their spoken “sahi hai” is the evidence. They can correct it, or say no." },
  { icon: "upi", model: "UPI, both sides", t: "Payment is proven", d: "The employer's UPI reference matches her bank SMS. No gateway, no cost." },
  { icon: "passport", model: "Kaam Passport", t: "She owns the proof", d: "A signed, tamper-evident history. She shares an income band, the full record, or work days, and can revoke it." },
];

const LEVELS = [
  { k: "L0", t: "Her word", d: "Recorded by the worker; not confirmed yet, or a fraud signal." },
  { k: "L1", t: "Employer confirmed", d: "A recorded spoken “yes” on a call or the link." },
  { k: "L2", t: "Payment proven", d: "The same UPI reference on both sides." },
  { k: "L3", t: "Established", d: "Payment proven, from the same employer, for 3+ months." },
];

const DOORS = [
  { icon: "bank", t: "A loan at bank rates", d: "Verified income history instead of a guess, through a link she can revoke." },
  { icon: "home", t: "A rented room", d: "The landlord sees only an income band and how long she has worked." },
  { icon: "doc", t: "Welfare board", d: "Construction workers need 90 verified days a year. Saakshi counts them and prints the certificate." },
  { icon: "rupee", t: "Unpaid wages", d: "“Do mahine se paise nahi mile” is logged as dues, with the call as evidence." },
];

function Icon({ name }: { name: string }) {
  const p: Record<string, React.ReactNode> = {
    mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
    check: <><path d="M4 12.5l5 5L20 6.5" /></>,
    phone: <><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z" /></>,
    upi: <><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18M7 15h4" /></>,
    passport: <><rect x="5" y="3" width="14" height="18" rx="2" /><circle cx="12" cy="10" r="3" /><path d="M9 16h6" /></>,
    speaker: <><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11" /></>,
    bank: <><path d="M3 10l9-6 9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18" /></>,
    home: <><path d="M4 11l8-7 8 7v9H4z" /><path d="M10 20v-5h4v5" /></>,
    doc: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4M10 12h5M10 16h5" /></>,
    rupee: <><path d="M7 5h10M7 9h10M7 5c6 0 6 8 0 8l7 7" /></>,
  };
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{p[name]}</svg>;
}
