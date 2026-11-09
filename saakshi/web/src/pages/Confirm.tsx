import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type LinkView } from "../lib/api";
import { inr, upiLink } from "../lib/util";
import { Chip, Scope, Wave } from "../components/bits";
import { VoiceOrb, useVoice } from "../components/VoiceOrb";
import { LANGS, tx } from "../lib/i18n";
import { player } from "../lib/player";
import { LevelBadge } from "../components/Level";

/** What the employer opens from the worker's WhatsApp message. */
export default function Confirm() {
  const { token = "" } = useParams();
  const [v, setV] = useState<LinkView | null>(null);
  const [intro, setIntro] = useState<{ url: string; duration: number; peaks: number[] } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [heard, setHeard] = useState<string | null>(null);
  const [mode, setMode] = useState<"main" | "correct">("main");
  const [fix, setFix] = useState<Record<string, string>>({});
  const [lang, setLang] = useState<string | null>(null);
  const onVoiceRef = useRef<(w: Blob) => void>(() => {});
  const busyRef = useRef(false);
  const voice = useVoice((w) => onVoiceRef.current(w));

  useEffect(() => {
    api.link(token).then((x) => { setV(x); setFix(Object.fromEntries(x.entries.map((e) => [e.id, String(Math.round(e.amount))]))); })
      .catch((e) => setErr(e.message));
  }, [token]);
  useEffect(() => {
    if (!v) return;
    setIntro(null);
    api.linkIntro(token, lang ?? v.language).then(setIntro).catch(() => {});
  }, [token, lang, v?.token]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err && !v) return <main className="confirm"><div className="confirm-card sheet"><p className="h2">{err}</p></div></main>;
  if (!v) return <main className="confirm"><span className="spinner" /></main>;
  const L = lang ?? v.language;
  const first = v.worker.name.split(" ")[0];
  const done = v.status === "done";

  const act = async (fn: () => Promise<LinkView>) => {
    setBusy(true); setErr("");
    try { setV(await fn()); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const begin = async () => {                    // one tap: Saakshi explains, then simply listens
    player.unlock();
    await voice.start();
    if (intro) void player.play(intro.url, "saakshi");
  };
  const onVoice = async (wav: Blob) => {
    if (busyRef.current || v.status === "done") return;
    busyRef.current = true;
    setBusy(true); setErr(""); setHeard(null);
    try {
      const f = new FormData(); f.append("audio_file", wav, "employer.wav");
      const r = await api.linkVoice(token, f);
      setHeard(r.heard || "—");
      if (r.accepted && r.view) { setV(r.view); voice.stop(); }
      else setErr(r.reason === "negative"
        ? (tx(lang, "You said no. If the details are wrong, change the amount below, or tell us you don't know this person.", "आपने 'नहीं' कहा। अगर जानकारी गलत है, तो नीचे 'राशि बदलें' या 'मैं नहीं जानता' चुनें।"))
        : (tx(lang, "Didn't catch that clearly. Please say: 'Yes, that's correct'.", "साफ़ सुनाई नहीं दिया। दोबारा बोलिए: 'हाँ, सही है'।")));
    } catch (e) { setErr((e as Error).message); } finally { busyRef.current = false; setBusy(false); }
  };
  onVoiceRef.current = (w) => void onVoice(w);

  return (
    <main className="confirm">
      <article className="confirm-card sheet">
        <select className="lang-select" style={{ float: "right" }} value={L} aria-label="Language"
          onChange={(e) => { player.stop(); setLang(e.target.value); }}>
          {LANGS.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
        </select>
        <div className="brand" style={{ marginBottom: 18 }}>
          <span className="brand-mark"><svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 3h10M2 7h10M2 11h6" stroke="#fbf3ee" strokeWidth="1.6" strokeLinecap="round" /></svg></span>
          <b>Saakshi</b><span>साक्षी</span>
        </div>
        <p className="eyebrow">{tx(lang, "Confirm work", "काम की पुष्टि")} · {v.employer.name}</p>
        <h1 className="h2" style={{ margin: "8px 0 6px" }}>
          <b>{v.worker.name}</b> {tx(L, "says they worked for you.", "का कहना है कि उन्होंने आपके यहाँ काम किया।")}
        </h1>
        {intro && !done && (
          <div className="confirm-listen">
            <Wave clip={intro} who="saakshi" label="Listen" />
            <span className="small faint">{tx(lang, "Hear it from Saakshi (Gnani Timbre)", "साक्षी से सुनिए (Gnani Timbre)")}</span>
          </div>
        )}

        <div className="confirm-rows">
          {v.entries.map((e) => (
            <div key={e.id} className="confirm-row">
              <div>
                <p className="confirm-period">{e.period.label}</p>
                {e.days ? <p className="small faint">{e.days} {tx(lang, "days", "दिन")}</p> : null}
              </div>
              {mode === "correct" && !done ? (
                <label className="fld" style={{ margin: 0, width: 140 }}><span>{tx(lang, "Actually paid", "असल में दिए")} ₹</span>
                  <input inputMode="numeric" value={fix[e.id] ?? ""} onChange={(x) => setFix({ ...fix, [e.id]: x.target.value })} /></label>
              ) : (
                <div style={{ textAlign: "right" }}>
                  <p className="num confirm-amt">{inr(e.employer_says?.amount ?? e.amount)}</p>
                  {done && <LevelBadge level={e.level} small lang={L} />}
                </div>
              )}
              {done && v.outcome !== "disputed" && v.worker.upi_id && (
                <PayBlock token={token} entry={e} vpa={v.worker.upi_id} name={v.worker.name} lang={L} onDone={setV} />
              )}
            </div>
          ))}
        </div>

        {done ? (
          <div className="confirm-done">
            <Chip status={v.outcome === "disputed" ? "disputed" : "verified"}
              label={v.outcome === "disputed" ? (tx(lang, "You did not confirm this", "आपने पुष्टि नहीं की"))
                : v.outcome === "corrected" ? (tx(lang, "Recorded with your figures", "आपकी बताई राशि दर्ज हुई")) : (tx(lang, "Confirmed, thank you!", "पुष्टि हो गई, धन्यवाद!"))} />
            <p className="small muted" style={{ marginTop: 10 }}>
              {tx(L, "Your confirmation is now part of {first}'s work record. It helps them get loans, housing and government schemes.", "आपकी पुष्टि {first} के काम के रिकॉर्ड में जुड़ गई है। इससे उन्हें कर्ज़, किराये का घर और सरकारी योजनाएँ मिलने में मदद मिलती है।", { first })}
            </p>
          </div>
        ) : mode === "main" ? (
          <>
            <div className="confirm-voice">
              <Scope mic={voice.state === "hearing" ? voice.analyser : null} height={34} tone="call" />
              {voice.state === "off" ? (
                <button className="btn btn-primary" style={{ background: "var(--call)" }} onClick={begin}>
                  {tx(lang, "Listen and answer", "सुनें और जवाब दें")}
                </button>
              ) : <VoiceOrb voice={voice} busy={busy} lang={L} size={76} tone="call" />}
              <p className="small" style={{ textAlign: "center", margin: 0 }}>
                {tx(L, "If it's right, just say yes, in your own language. There is no button to hold.", "सही है तो बस बोलिए: “हाँ, सही है”। बटन दबाने की ज़रूरत नहीं।")}
              </p>
              {heard && <p className="small faint" style={{ textAlign: "center" }}>{tx(lang, "Heard (Prisma):", "सुना गया (Prisma):")} “{heard}”</p>}
            </div>
            <div className="confirm-alt">
              <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => act(() => api.linkTap(token))}>{tx(lang, "Can't speak? Confirm with a tap", "बोल नहीं सकते? टैप से पुष्टि")}</button>
              <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => setMode("correct")}>{tx(lang, "Change amount", "राशि बदलें")}</button>
              <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => { if (confirm(tx(lang, "You don't know this person?", "क्या आप सच में इन्हें नहीं जानते?"))) void act(() => api.linkDeny(token)); }}>{tx(lang, "I don't know them", "मैं इन्हें नहीं जानता")}</button>
            </div>
          </>
        ) : (
          <div className="row" style={{ marginTop: 16, flexWrap: "wrap" }}>
            <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.linkCorrect(token,
              Object.fromEntries(Object.entries(fix).map(([k, a]) => [k, { amount: Number(a.replace(/\D/g, "")) }]))))}>{tx(lang, "Confirm with these amounts", "इस राशि से पुष्टि करें")}</button>
            <button className="btn btn-ghost" onClick={() => setMode("main")}>{tx(lang, "Back", "वापस")}</button>
          </div>
        )}
        {err && <p className="error-line" style={{ marginTop: 12 }}>{err}</p>}
        <p className="small faint confirm-foot">
          {tx(L, "Saakshi never asks for money, OTPs or bank details. Your spoken confirmation is kept as evidence for this record.", "साक्षी कभी पैसे, OTP या बैंक की जानकारी नहीं माँगती। आपकी आवाज़ की पुष्टि रिकॉर्ड के सबूत के रूप में रखी जाती है।")}
        </p>
      </article>
    </main>
  );
}

function PayBlock({ token, entry, vpa, name, lang, onDone }: {
  token: string; entry: LinkView["entries"][number]; vpa: string; name: string; lang: string; onDone: (v: LinkView) => void;
}) {
  const [open, setOpen] = useState(false);
  const [utr, setUtr] = useState("");
  const [err, setErr] = useState("");
  const amount = entry.employer_says?.amount ?? entry.amount;
  if (entry.payment) {
    return <p className="small pay-note">✓ {tx(lang, "Payment noted", "भुगतान दर्ज")} · UTR …{entry.payment.utr.slice(-4)}
      {entry.payment_status === "verified" ? (tx(lang, " · matched on both sides", " · दोनों तरफ़ से मिलान हुआ")) : (tx(lang, " · waiting for the worker's bank SMS", " · कर्मचारी के बैंक SMS का इंतज़ार"))}</p>;
  }
  return (
    <div className="pay">
      {!open ? (
        <div className="row" style={{ flexWrap: "wrap" }}>
          <a className="btn btn-sm btn-ink" href={upiLink(vpa, name, amount, `Saakshi ${entry.period.label} wages`)} onClick={() => setOpen(true)}>
            {tx(lang, "Pay {amount} by UPI", "UPI से {amount} भेजें", { amount: inr(amount) })}
          </a>
          <button className="link small" onClick={() => setOpen(true)}>{tx(lang, "Already paid?", "पहले ही भेज दिया?")}</button>
        </div>
      ) : (
        <div className="row" style={{ flexWrap: "wrap" }}>
          <input className="utr" value={utr} onChange={(e) => setUtr(e.target.value)} inputMode="numeric" placeholder={tx(lang, "12-digit UPI reference (UTR)", "12 अंकों का UPI रेफ़रेंस (UTR)")} />
          <button className="btn btn-sm btn-ink" onClick={async () => {
            try { setErr(""); onDone(await api.linkPaid(token, { entry_id: entry.id, utr, amount })); } catch (e) { setErr((e as Error).message); }
          }}>{tx(lang, "Add", "जोड़ें")}</button>
          {err && <p className="error-line" style={{ width: "100%" }}>{err}</p>}
        </div>
      )}
      <p className="small faint" style={{ margin: "6px 0 0" }}>
        {tx(lang, "Adding the UTR proves the payment from both sides: the worker's bank SMS will show the same number.", "UTR जोड़ने से भुगतान दोनों तरफ़ से साबित होता है: कर्मचारी के बैंक SMS में भी यही नंबर होगा।")}
      </p>
    </div>
  );
}
