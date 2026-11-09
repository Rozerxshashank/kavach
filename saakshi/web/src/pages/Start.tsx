import { resetStream } from "../lib/util";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { auth } from "../lib/auth";
import { ROLE_LABEL } from "../lib/util";
import { LANGS, langName, roleName, t, tx, type Lang } from "../lib/i18n";

/** Real sign-up and login. Phone + PIN: no SMS cost, works for anyone. */
export default function Start() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"join" | "login">(auth.me() || new URLSearchParams(location.search).has("login") ? "login" : "join");
  const [f, setF] = useState({ name: "", phone: "", pin: "", pin2: "", language: (navigator.language?.startsWith("hi") ? "hi-IN" : LANGS.find((l) => navigator.language?.startsWith(l.code.slice(0, 2)))?.code ?? "hi-IN") as Lang, role: "domestic", city: "", state: "", upi_id: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [picked, setPicked] = useState(false);       // language comes first: nothing else is asked until it's chosen
  const L = mode === "join" ? f.language : "en-IN";
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (mode === "join" && f.pin !== f.pin2) { setErr(tx(L, "The two PINs don't match.", "दोनों PIN एक जैसे नहीं हैं।")); return; }
    setBusy(true);
    try {
      const r = mode === "join"
        ? await api.join({ name: f.name, phone: f.phone, pin: f.pin, language: f.language, role: f.role, city: f.city, state: f.state, upi_id: f.upi_id })
        : await api.login(f.phone, f.pin);
      auth.setToken(r.worker.id, r.token, true);
      resetStream();
      nav(`/w/${r.worker.id}`);
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  };

  return (
    <main className="wrap page start">
      <div className="start-grid">
        <div>
          <p className="eyebrow">{mode === "join" ? "Start your record" : "Welcome back"}</p>
          <h1 className="h1" style={{ marginTop: 10 }}>{mode === "join" ? <>Your work, <em>on record.</em></> : <>Open your <em>Kaam Passport.</em></>}</h1>
          <p className="lede">
            {mode === "join"
              ? "Takes a minute. Then just speak your work, and Saakshi gets each employer to confirm it."
              : "Log in with the phone number and PIN you chose."}
          </p>
          <ul className="start-points">
            <li>No app to install. Works in any phone's browser.</li>
            <li>Free. Your employer confirms through a WhatsApp link you send.</li>
            <li>Your record belongs to you. You choose who sees it, and for how long.</li>
          </ul>
        </div>
        {mode === "join" && !picked ? (
          <div className="sheet start-form">
            <p className="eyebrow">Step 1 of 2</p>
            <p className="h3" style={{ marginTop: 8 }}>{t("choose", f.language)}</p>
            <p className="small faint" style={{ margin: "4px 0 0" }}>Saakshi will talk to you, and to your employers, in this language. You can change it any time.</p>
            <div className="lang-grid" role="radiogroup" aria-label="Language">
              {LANGS.map((l) => (
                <button key={l.code} type="button" role="radio" aria-checked={f.language === l.code}
                  className={`lang-tile ${f.language === l.code ? "on" : ""}`}
                  onClick={() => setF({ ...f, language: l.code })} onDoubleClick={() => { setF({ ...f, language: l.code }); setPicked(true); }}>
                  <b>{l.native}</b><span>{l.hello}{l.code !== "en-IN" ? ` · ${l.english}` : ""}</span>
                </button>
              ))}
            </div>
            <button className="btn btn-primary" style={{ width: "100%", marginTop: 10 }} onClick={() => setPicked(true)}>{t("continue", f.language)} →</button>
            <p className="small faint" style={{ marginTop: 14 }}>Already have a record? <button className="link" onClick={() => setMode("login")}>Log in</button></p>
          </div>
        ) : (
        <form className="sheet start-form" onSubmit={submit}>
          <div className="seg" style={{ marginBottom: 18 }}>
            <button type="button" className={mode === "join" ? "on" : ""} onClick={() => setMode("join")}>New here</button>
            <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>I have an account</button>
          </div>
          {mode === "join" && (
            <label className="fld"><span>{tx(L, "Your name", "आपका नाम")}</span><input value={f.name} onChange={set("name")} required autoComplete="name" /></label>
          )}
          <label className="fld"><span>{tx(L, "Mobile number", "मोबाइल नंबर")}</span>
            <input value={f.phone} onChange={set("phone")} required inputMode="tel" placeholder="98xxxxxxxx" autoComplete="tel" /></label>
          <div className="fld-row">
            <label className="fld"><span>{tx(L, "PIN (4–6 digits)", "PIN (4–6 अंक)")}</span>
              <input value={f.pin} onChange={set("pin")} required inputMode="numeric" type="password" maxLength={6} autoComplete={mode === "join" ? "new-password" : "current-password"} /></label>
            {mode === "join" && <label className="fld"><span>{tx(L, "PIN again", "PIN दोबारा")}</span>
              <input value={f.pin2} onChange={set("pin2")} required inputMode="numeric" type="password" maxLength={6} autoComplete="new-password" /></label>}
          </div>
          {mode === "join" && (
            <>
              <div className="fld-row">
                <label className="fld"><span>{tx(L, "Language", "भाषा")}</span>
                  <button type="button" className="lang-chosen" onClick={() => setPicked(false)}>{langName(f.language)} <span className="faint small">· {tx(L, "change", "बदलें")}</span></button></label>
                <label className="fld"><span>{tx(L, "Your work", "आपका काम")}</span>
                  <select value={f.role} onChange={set("role")}>{Object.keys(ROLE_LABEL).map((k) => <option key={k} value={k}>{roleName(k, L)}</option>)}</select></label>
              </div>
              <div className="fld-row">
                <label className="fld"><span>{tx(L, "City", "शहर")}</span><input value={f.city} onChange={set("city")} /></label>
                <label className="fld"><span>{tx(L, "State", "राज्य")}</span><input value={f.state} onChange={set("state")} /></label>
              </div>
              <label className="fld"><span>{tx(L, "UPI ID (optional): so employers can pay you and prove it", "UPI ID (ज़रूरी नहीं): ताकि नियोक्ता भुगतान करके साबित कर सकें")}</span>
                <input value={f.upi_id} onChange={set("upi_id")} placeholder="name@okaxis" autoCapitalize="none" /></label>
            </>
          )}
          {err && <p className="error-line">{err}</p>}
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 8 }} disabled={busy}>
            {busy ? <span className="spinner light" /> : mode === "join" ? tx(L, "Create my record", "मेरा रिकॉर्ड बनाएँ") : "Log in"}
          </button>
          {mode === "login" && <p className="small faint" style={{ marginTop: 12 }}>Forgot your PIN? Ask the Saakshi helper at your union, NGO or bank-mitra point to reset it. They'll check it's really you.</p>}
          <p className="small faint" style={{ marginTop: 12 }}>Just exploring? <Link className="link" to="/demo">See the live demo</Link></p>
        </form>
        )}
      </div>
    </main>
  );
}
