import { AnimatePresence, motion } from "framer-motion";
import { at } from "../lib/base";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Clip, type Draft, type Link as SendLink, type WorkerDetail } from "../lib/api";
import { player } from "../lib/player";
import { inr, isDeva, monthRange, useStream } from "../lib/util";
import { Chip, Confidence, QR, Reasons, Scope, Wave } from "../components/bits";
import { VoiceOrb, useVoice } from "../components/VoiceOrb";
import { LANGS, roleName, statusName, t, tx } from "../lib/i18n";
import { LevelBadge } from "../components/Level";
import { auth } from "../lib/auth";
import { IncomeChart } from "../components/IncomeChart";
import { WorkerHome } from "../components/WorkerHome";
import { setBusy as reportBusy } from "../lib/director";

type Line = { who: "worker" | "saakshi"; text: string; audio?: Clip | null };
type Tab = "home" | "bolo" | "record" | "share";

export function WorkerApp({ workerId }: { workerId: string }) {
  const [d, setD] = useState<WorkerDetail | null>(null);
  const [tab, setTab] = useState<Tab>("home");
  const [lines, setLines] = useState<Line[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => api.worker(workerId).then((x) => { setD(x); if (x.journal) setDrafts(x.journal.drafts); }).catch((e) => setErr(e.message)), [workerId]);
  useEffect(() => { setLines([]); setDrafts([]); void load(); }, [load]);
  useEffect(() => { logRef.current?.scrollTo({ top: 1e6, behavior: "smooth" }); }, [lines, drafts]);

  useStream((e) => {
    if (e.type === "call.ended" && (e.worker_ids || []).includes(workerId)) {
      void load();
      const l = d?.worker.language ?? "hi-IN";
      const msg: Record<string, string> = {
        verified: tx(l, "An employer confirmed your record ✓", "नियोक्ता ने आपके रिकॉर्ड की पुष्टि कर दी ✓"),
        corrected: tx(l, "An employer confirmed, with their figures", "नियोक्ता ने अपनी बताई राशि से पुष्टि की"),
        disputed: tx(l, "An employer did not confirm a record", "एक नियोक्ता ने रिकॉर्ड की पुष्टि नहीं की"),
        callback: tx(l, "The employer asked to be called back later", "नियोक्ता ने बाद में फ़ोन करने को कहा"),
        bulk: tx(l, "Your contractor confirmed the crew ✓", "ठेकेदार ने पूरी टीम की पुष्टि कर दी ✓"),
      };
      setToast(msg[e.outcome] ?? tx(l, "A confirmation call finished", "पुष्टि की कॉल पूरी हुई"));
      setTimeout(() => setToast(null), 4200);
    }
    if (e.type === "world.changed") void load();
  });

  const lang = d?.worker.language ?? "hi-IN";

  // hands-free: the mic stays open; what the worker says while Saakshi is thinking is kept and sent next
  const busyRef = useRef(false);
  const pending = useRef<Blob | null>(null);
  const onAudioRef = useRef<(w: Blob) => void>(() => {});
  const voice = useVoice((w) => onAudioRef.current(w));
  const typingPaused = useRef(false);
  useEffect(() => { voice.setSilence(asked.startsWith("employer_phone") ? 1500 : 950); }, [asked, voice]);   // people pause between digits

  const start = async () => {
    player.unlock();
    void voice.start();
    setBusy(true);
    try {
      const w = await api.welcome(workerId);
      setLines([{ who: "saakshi", text: w.say, audio: w.audio }]);
      setBusy(false);
      if (w.audio) void player.play(w.audio.url, "saakshi");
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  useEffect(() => { reportBusy("worker", busy); }, [busy]);

  const send = async (f: FormData) => {
    busyRef.current = true; setBusy(true); reportBusy("worker", true); setErr("");
    try {
      const r = await api.journal(workerId, f);
      setLines((l) => [...l, { who: "worker", text: r.heard, audio: r.worker_audio }, { who: "saakshi", text: r.say, audio: r.audio }]);
      setDrafts(r.drafts); setAsked(r.asked);
      if (r.saved.length) void load();
      busyRef.current = false; setBusy(false);
      const next = pending.current;
      pending.current = null;
      if (next) { onAudioRef.current(next); return; }          // they kept talking: answer that, don't talk over them
      if (r.audio) void player.play(r.audio.url, "saakshi");   // speaking again interrupts her
    } catch (e) { setErr((e as Error).message); busyRef.current = false; setBusy(false); }
  };

  const onAudio = async (wav: Blob) => {
    if (busyRef.current) { pending.current = wav; return; }
    const f = new FormData(); f.append("audio_file", wav, "worker.wav"); await send(f);
  };
  onAudioRef.current = (w) => void onAudio(w);
  const onTypedRef = useRef<(t?: string) => Promise<void>>(async () => {});
  const onTyped = async (text?: string) => {
    const t = (text ?? typed).trim();
    if (!t) return;
    setTyped("");
    player.stop();
    if (!lines.length) player.unlock();
    const f = new FormData(); f.append("text", t); await send(f);
  };

  // the guided demo can speak for the worker
  useEffect(() => {
    const h = (ev: Event) => {
      const { text, voiced } = (ev as CustomEvent<{ text: string; voiced: boolean }>).detail;
      setTab("bolo");
      if (voiced) void sayVoicedRef.current(text); else void onTypedRef.current(text);
    };
    window.addEventListener("saakshi:worker-say", h);
    return () => window.removeEventListener("saakshi:worker-say", h);
  }, []);

  onTypedRef.current = onTyped;
  // the demo autopilot: Timbre speaks the worker's line in her voice, we play it, then send that audio to Prisma
  const sayVoicedRef = useRef<(t: string) => Promise<void>>(async () => {});
  sayVoicedRef.current = async (text: string) => {
    reportBusy("worker", true);
    try {
      const c = await api.demoVoice(text, "Urmila", lang);
      await player.play(c.url, "worker");
      const blob = await (await fetch(c.url)).blob();
      await onAudio(blob);
    } catch { await onTyped(text); } finally { if (!busyRef.current) reportBusy("worker", false); }
  };
  if (err && !d) return (
    <div className="wa-empty" style={{ padding: 24, textAlign: "center" }}>
      <p className="error-line">{err}</p>
      {/log in/i.test(err) && <Link className="btn btn-primary" to="/start">Log in</Link>}
    </div>
  );
  if (!d) return err
    ? <div className="wa-empty" style={{ display: "grid", gap: 12, justifyItems: "center", padding: 24, textAlign: "center" }}>
        <p className="small">{err}</p>
        <button className="btn btn-sm btn-ink" onClick={() => { auth.logout(); location.href = at("/start?login=1"); }}>{tx(lang, "Log in", "लॉग इन करें")}</button>
      </div>
    : <div className="wa-empty"><span className="spinner" /></div>;
  const p = d.passport;
  const hi = lang === "hi-IN";

  return (
    <div className="wa">
      <header className="wa-head">
        <div className="wa-avatar">{d.worker.name.split(" ").map((x) => x[0]).join("").slice(0, 2)}</div>
        <div style={{ minWidth: 0 }}>
          <p className="wa-name">{d.worker.name}</p>
          <p className="small faint">{roleName(d.worker.role, lang)} · {d.worker.city}</p>
        </div>
        <select className="lang-select" style={{ marginLeft: "auto" }} title="भाषा / Language" value={lang} aria-label="Language"
          onChange={async (ev) => { player.stop(); await api.profile(workerId, { language: ev.target.value }); setLines([]); void load(); }}>
          {LANGS.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
        </select>
        {auth.me() === workerId && <button className="link small" onClick={() => { auth.logout(); location.href = at("/start"); }}>{tx(lang, "Log out", "लॉग आउट")}</button>}
      </header>

      <nav className="wa-tabs">
        {(["home", "bolo", "record", "share"] as Tab[]).map((tb) => (
          <button key={tb} className={tab === tb ? "on" : ""} onClick={() => setTab(tb)}>
            {tb === "home" ? t("tabHome", lang) : tb === "bolo" ? t("tabSpeak", lang) : tb === "record" ? t("tabRecord", lang) : t("tabShare", lang)}
          </button>
        ))}
      </nav>

      <AnimatePresence>
        {toast && <motion.div className="wa-toast" initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -20, opacity: 0 }}>{toast}</motion.div>}
      </AnimatePresence>

      {tab === "home" && (
        <div className="wa-scroll">
          <WorkerHome d={d} lang={lang} onOpen={setTab}
            onSpeak={() => { setTab("bolo"); if (!lines.length) void start(); else if (voice.state === "off") void voice.start(); }} />
        </div>
      )}

      {tab === "bolo" && (
        <>
          <div className="wa-log" ref={logRef}>
            {!lines.length && (
              <div className="wa-intro">
                <p className="h3">{t("introTitle", lang)}</p>
                <p className="small muted">{t("introHint", lang)}</p>
                {hi && <p className="small faint">जैसे: “इस महीने मेहता जी के यहाँ काम किया, पौने पाँच हज़ार मिले।”</p>}
                <button className="btn btn-primary" onClick={start} disabled={busy}>{busy ? <span className="spinner light" /> : t("start", lang)}</button>
              </div>
            )}
            {lines.map((l, i) => (
              <motion.div key={i} className={`wa-line ${l.who}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                <span className="eyebrow">{l.who === "worker" ? (tx(lang, "You · heard by Prisma", "आप · Prisma ने सुना")) : tx(lang, "Saakshi · Timbre", "साक्षी · Timbre")}</span>
                <p className={isDeva(l.text) ? "deva-text" : ""}>{l.text}</p>
                {l.audio && <Wave clip={l.audio} who={l.who === "worker" ? "worker" : "saakshi"} />}
              </motion.div>
            ))}
            {drafts.length > 0 && (
              <div className="wa-draft">
                <p className="eyebrow">{tx(lang, "Draft · not saved yet", "कच्चा रिकॉर्ड · अभी सेव नहीं")}</p>
                {drafts.map((x, i) => <DraftRow key={i} d={x} asked={asked} lang={lang} />)}
              </div>
            )}
            {busy && lines.length > 0 && <p className="small faint" style={{ padding: "4px 2px" }}>Saakshi<span className="dots" /></p>}
            <SendPanel links={d.links} lang={lang} />
          </div>
          <div className="wa-dock">
            <Scope mic={voice.state === "hearing" ? voice.analyser : null} height={34} tone="khata" />
            <VoiceOrb voice={voice} busy={busy} lang={lang} size={72} />
            <div className="wa-type">
              <input value={typed} onChange={(e) => setTyped(e.target.value)} onFocus={() => { if (voice.state === "listening") { typingPaused.current = true; voice.toggle(); } }}
                onBlur={() => { if (typingPaused.current && voice.state === "paused") voice.toggle(); typingPaused.current = false; }} onKeyDown={(e) => e.key === "Enter" && onTyped()}
                placeholder={asked.startsWith("employer_phone") ? "98xxxxxxxx" : t("orType", lang)} disabled={busy}
                inputMode={asked.startsWith("employer_phone") ? "tel" : "text"} />
              <button className="btn btn-sm btn-ink" onClick={() => onTyped()} disabled={busy || !typed.trim()}>↵</button>
            </div>
            <div className="wa-quick">
              {[tx(lang, "Yes, that's right", "हाँ, सही है"), tx(lang, "Read my record", "मेरा रिकॉर्ड सुनाओ"), tx(lang, "Don't call them", "फ़ोन मत करना")].map((q) => (
                <button key={q} onClick={() => onTyped(q)} disabled={busy}>{q}</button>
              ))}
            </div>
            {err && <p className="error-line">{err}</p>}
          </div>
        </>
      )}

      {tab === "record" && (
        <div className="wa-scroll">
          <div className="wa-kpis">
            <div><span className="num">{inr(p.stats.avg_monthly_verified)}</span><span className="eyebrow">{tx(lang, "verified avg / month", "पक्की औसत / महीना")}</span></div>
            <div><span className="num">{p.stats.months_verified}</span><span className="eyebrow">{tx(lang, "verified months", "पक्के महीने")}</span></div>
            <div><span className="num">{p.stats.employers}</span><span className="eyebrow">{tx(lang, "employers", "नियोक्ता")}</span></div>
          </div>
          <IncomeChart months={p.months.slice(-6)} height={170} lang={lang} />
          <div className="wa-records">
            {d.entries.map((e) => (
              <div key={e.id} className={`wa-rec ${e.status === "withdrawn" ? "withdrawn" : ""}`} onClick={() => setOpen(open === e.id ? null : e.id)}>
                <div className="spread">
                  <div style={{ minWidth: 0 }}>
                    <p className="wa-rec-who">{e.employer_name}</p>
                    <p className="small faint">{monthRange(e.period_start, e.period_end, lang)}{e.days ? ` · ${tx(lang, "{n} days", "{n} दिन", { n: e.days })}` : ""}</p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p className="num wa-rec-amt">{inr(e.employer_says?.amount ?? e.amount)}</p>
                    {(e.level ?? 0) > 0 ? <LevelBadge level={e.level} small lang={lang} /> : <Chip status={e.status} label={statusName(e.status, lang)} />}
                  </div>
                </div>
                {open === e.id && (
                  <div className="wa-rec-more">
                    <Confidence value={e.confidence} />
                    <Reasons reasons={e.reasons} />
                    {e.employer_says?.amount && e.employer_says.amount !== e.amount && <p className="small muted">{tx(lang, "You said {a}; your employer said {b}. Their figure is used.", "आपने {a} बताया; नियोक्ता ने {b} बताया। उनकी राशि मानी गई है।", { a: inr(e.amount), b: inr(e.employer_says.amount) })}</p>}
                    {e.status !== "withdrawn" && (
                      <button className="link small" style={{ justifySelf: "start", color: "var(--bad)" }} onClick={async (ev) => {
                        ev.stopPropagation();
                        if (!confirm(tx(lang, "Withdraw this record? It will be removed from your passport.", "यह रिकॉर्ड वापस लें? यह आपके पासपोर्ट से हट जाएगा।"))) return;
                        await api.withdraw(workerId, e.id); void load();
                      }}>{tx(lang, "Withdraw this record", "यह रिकॉर्ड वापस लें")}</button>
                    )}
                  </div>
                )}
              </div>
            ))}
            {!d.entries.length && <p className="small faint">{tx(lang, "No records yet.", "अभी कोई रिकॉर्ड नहीं।")}</p>}
          </div>
          <Link to={`/passport/${workerId}`} className="btn btn-ghost" style={{ width: "100%" }}>{tx(lang, "Open full Kaam Passport", "पूरा कामपासपोर्ट देखें")} →</Link>
        </div>
      )}

      {tab === "share" && <ShareTab d={d} reload={load} lang={lang} />}
    </div>
  );
}

function DraftRow({ d, asked, lang }: { d: Draft; asked: string; lang: string }) {
  const needPhone = !d.employer_id && !d.employer_phone && !d.do_not_contact;
  return (
    <div className="draft-row">
      <div className="spread">
        <b>{d.employer_name || "?"}</b>
        <span className="num">{d.amount ? inr(d.amount) : <em className="need">{tx(lang, "amount?", "राशि?")}</em>}</span>
      </div>
      <div className="spread small">
        <span className={d.period ? "faint" : "need"}>{d.period ? d.period.label : tx(lang, "when?", "कब का?")}</span>
        <span className={needPhone ? "need" : "faint"}>
          {d.do_not_contact ? (tx(lang, "won't call", "फ़ोन नहीं करेंगे")) : d.employer_phone ? `•••${d.employer_phone.slice(-4)}` : d.employer_id ? (tx(lang, "known employer", "पुराने नियोक्ता")) : asked.startsWith("employer_phone") ? (tx(lang, "number needed", "नंबर चाहिए")) : "—"}
        </span>
      </div>
      {d.amount_source === "parsed" && <span className="parsed mono">✓ {tx(lang, "amount read from your words", "राशि शब्दों से पढ़ी गई")}</span>}
    </div>
  );
}

function ShareTab({ d, reload, lang }: { d: WorkerDetail; reload: () => void; lang: string }) {
  const [scope, setScope] = useState("full");
  const [aud, setAud] = useState("");
  const [busy, setBusy] = useState(false);
  const [sms, setSms] = useState("");
  const [smsMsg, setSmsMsg] = useState("");
  const live = d.shares.filter((s) => !s.revoked);
  const create = async () => {
    setBusy(true);
    try { await api.share(d.worker.id, { scope, audience: aud, days: 30 }); setAud(""); reload(); } finally { setBusy(false); }
  };
  const addSms = async () => {
    try { const r = await api.evidence(d.worker.id, sms); setSmsMsg(r.matched_entry ? "Matched to a record ✓" : "Saved, but no record matched yet"); setSms(""); reload(); }
    catch (e) { setSmsMsg((e as Error).message); }
  };
  const isBuild = ["construction", "painter", "plumber", "electrician"].includes(d.worker.role);
  return (
    <div className="wa-scroll">
      <UpiField d={d} reload={reload} lang={lang} />
      <p className="h3">{tx(lang, "Who should see it?", "किसे दिखाना है?")}</p>
      <div className="seg" style={{ margin: "10px 0" }}>
        {[["full", tx(lang, "Full (lender)", "पूरा (बैंक)")], ["income_band", tx(lang, "Income band (landlord)", "आय सीमा (मकान मालिक)")], ["bocw", tx(lang, "Work days (board)", "काम के दिन (बोर्ड)")]].map(([k, l]) => (
          <button key={k} className={scope === k ? "on" : ""} onClick={() => setScope(k)}>{l}</button>
        ))}
      </div>
      <div className="wa-type" style={{ marginBottom: 14 }}>
        <input value={aud} onChange={(e) => setAud(e.target.value)} placeholder={tx(lang, "For whom? (e.g. SBI branch)", "किसके लिए? (जैसे: SBI शाखा)")} />
        <button className="btn btn-sm btn-primary" onClick={create} disabled={busy}>{tx(lang, "Create link", "लिंक बनाओ")}</button>
      </div>
      {live.map((s) => {
        const url = `${location.origin}/p/${s.token}`;
        return (
          <div key={s.token} className="share-row">
            <QR text={url} size={84} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <p style={{ margin: 0, fontWeight: 500 }}>{s.audience || "Anyone with the link"}</p>
              <p className="small faint" style={{ margin: "2px 0 6px" }}>{s.scope.replace("_", " ")} · {s.views} views · 30 days</p>
              <div className="row">
                <a className="link small" href={at(`/p/${s.token}`)} target="_blank" rel="noreferrer">Open</a>
                <button className="link small" onClick={async () => { await api.revoke(d.worker.id, s.token); reload(); }}>{tx(lang, "Revoke", "वापस लो")}</button>
              </div>
            </div>
          </div>
        );
      })}
      {isBuild && <Link className="btn btn-ghost" style={{ width: "100%", marginTop: 12 }} to={`/bocw/${d.worker.id}`}>{tx(lang, "Welfare board certificate", "निर्माण कल्याण बोर्ड प्रमाणपत्र")} →</Link>}
      <hr className="rule" style={{ margin: "22px 0 16px" }} />
      <p className="h3">{tx(lang, "Add a UPI message", "UPI का मैसेज जोड़ें")}</p>
      <p className="small muted">{tx(lang, "Paste a payment-received SMS; a match raises trust.", "पैसे मिलने का SMS चिपकाइए; मिलान होने पर भरोसा बढ़ता है।")}</p>
      <textarea className="sms" value={sms} onChange={(e) => setSms(e.target.value)} rows={3} placeholder="Rs.4,000.00 credited to a/c XX4411 on 31-Oct-26 by IYER R via UPI…" />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn btn-sm btn-ink" onClick={addSms} disabled={!sms.trim()}>{tx(lang, "Add", "जोड़ें")}</button>
        {smsMsg && <span className="small muted">{smsMsg}</span>}
      </div>
      <DeleteAccount wid={d.worker.id} lang={lang} />
    </div>
  );
}


function SendPanel({ links, lang }: { links: SendLink[]; lang: string }) {
  const open = links.filter((l) => l.status !== "done");
  const [copied, setCopied] = useState<string | null>(null);
  if (!open.length) return null;
  const label: Record<string, string> = { sent: tx(lang, "Not sent yet", "भेजना बाकी"), opened: tx(lang, "Opened", "खोला गया") };
  return (
    <div className="send">
      <p className="eyebrow">{tx(lang, "Send for confirmation", "पुष्टि के लिए भेजें")}</p>
      {open.map((l) => (
        <div key={l.token} className="send-row">
          <div style={{ minWidth: 0 }}>
            <p className="send-who">{l.employer_name}</p>
            <p className="small faint">{l.entry_ids.length} {tx(lang, "record(s)", "रिकॉर्ड")} · {label[l.status] ?? l.status}</p>
          </div>
          <div className="row">
            <a className="btn btn-sm wa-green" href={l.whatsapp} target="_blank" rel="noreferrer">WhatsApp</a>
            <button className="btn btn-sm btn-ghost" onClick={async () => {
              try { await navigator.clipboard.writeText(l.message); setCopied(l.token); setTimeout(() => setCopied(null), 1800); } catch { /* clipboard blocked */ }
            }}>{copied === l.token ? "✓" : tx(lang, "Copy", "कॉपी")}</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function UpiField({ d, reload, lang }: { d: WorkerDetail; reload: () => void; lang: string }) {
  const [v, setV] = useState(d.worker.upi_id ?? "");
  const [msg, setMsg] = useState("");
  const save = async () => {
    try { await api.profile(d.worker.id, { upi_id: v }); setMsg("✓"); reload(); } catch (e) { setMsg((e as Error).message); }
  };
  return (
    <div className="upi-field">
      <p className="h3">{tx(lang, "Your UPI ID", "आपकी UPI ID")}</p>
      <p className="small muted">{tx(lang, "Employers can pay you here and prove the payment (Level 2).", "नियोक्ता इसी पर पैसे भेजकर भुगतान साबित कर सकते हैं (लेवल 2)।")}</p>
      <div className="wa-type">
        <input value={v} onChange={(e) => setV(e.target.value)} placeholder="name@okaxis" autoCapitalize="none" />
        <button className="btn btn-sm btn-ink" onClick={save}>{tx(lang, "Save", "सेव")}</button>
      </div>
      {msg && <p className="small muted">{msg}</p>}
    </div>
  );
}


function DeleteAccount({ wid, lang }: { wid: string; lang: string }) {
  const [open, setOpen] = useState(false);
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  return (
    <div className="danger">
      {!open ? (
        <button className="link small" style={{ color: "var(--bad)" }} onClick={() => setOpen(true)}>{tx(lang, "Delete my account and all my data", "मेरा खाता और सारा डेटा मिटाएँ")}</button>
      ) : (
        <>
          <p className="small muted">{tx(lang, "All your records, recordings and share links will be erased permanently. This can't be undone.", "आपके सारे रिकॉर्ड, आवाज़ें और शेयर लिंक हमेशा के लिए मिट जाएँगे। यह वापस नहीं होगा।")}</p>
          <div className="wa-type">
            <input value={pin} onChange={(e) => setPin(e.target.value)} type="password" inputMode="numeric" placeholder={tx(lang, "Enter your PIN", "अपना PIN डालें")} />
            <button className="btn btn-sm btn-bad" onClick={async () => {
              try { await api.deleteAccount(wid, pin); auth.logout(); location.href = at("/"); } catch (e) { setErr((e as Error).message); }
            }}>{tx(lang, "Delete", "मिटाएँ")}</button>
          </div>
          {err && <p className="error-line">{err}</p>}
        </>
      )}
    </div>
  );
}
