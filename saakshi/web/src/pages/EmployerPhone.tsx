import { motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Call, type CallTurn } from "../lib/api";
import { player } from "../lib/player";
import { OUTCOME_LABEL, isDeva, useStream } from "../lib/util";
import { Scope } from "../components/bits";
import { VoiceOrb, useVoice } from "../components/VoiceOrb";
import { setBusy as reportBusy } from "../lib/director";

type Phase = "idle" | "ringing" | "connecting" | "live" | "ended";

const QUICK_HI = ["हाँ बोलिए", "ये पैसे किस बात के हैं? समझाइए", "आप कौन हैं? मेरा नंबर किसी को देंगे?", "हाँ, सही है", "सब सही है, बस राजू 3 दिन आया", "कौन बोल रहा है? फ्रॉड है क्या?", "नहीं, 2000 ही दिए थे", "मैं इन्हें नहीं जानता", "अभी बिज़ी हूँ, कल शाम को फ़ोन करना", "मैं उनका बेटा बोल रहा हूँ", "दोबारा फ़ोन मत करना"];
const QUICK_EN = ["Yes, go ahead", "What is this amount for?", "Who are you? Will you share my number?", "Yes, that's correct", "Who is this? Is this a scam?", "No, I paid only 2000", "I don't know this person", "Busy now, call me tomorrow evening"];

/** The employer's handset. Follows whichever call is ringing for `employerId`, or any human-mode call. */
export function EmployerPhone({ employerId }: { employerId?: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [call, setCall] = useState<Call | null>(null);
  const [turns, setTurns] = useState<CallTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [start, setStart] = useState(0);
  const [, tick] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const pending = useRef<Blob | null>(null);
  const onAudioRef = useRef<(w: Blob) => void>(() => {});
  const voice = useVoice((w) => onAudioRef.current(w), 900);
  useEffect(() => { if (phase === "ended" || phase === "idle") voice.stop(); }, [phase, voice]);

  useEffect(() => { if (phase !== "live") return; const t = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(t); }, [phase]);
  useEffect(() => { logRef.current?.scrollTo({ top: 1e6, behavior: "smooth" }); }, [turns]);

  const ringFor = useCallback(async (callId: string) => {
    const c = await api.call(callId);
    if (employerId && c.employer_id !== employerId) return;
    if (c.mode !== "human") return;
    const list = await api.calls();
    setCall(list.find((x) => x.id === callId) ?? c);
    setTurns([]); setOutcome(null); setErr("");
    setPhase("ringing");
  }, [employerId]);

  // a call may already be ringing (page reload, dropped connection): check now, and every few seconds while idle
  useEffect(() => {
    if (phase !== "idle" && phase !== "ended") return;
    const check = () => api.calls().then((cs) => {
      const r = cs.find((c) => c.status === "ringing" && c.mode === "human" && (!employerId || c.employer_id === employerId));
      if (r) void ringFor(r.id);
    }).catch(() => {});
    void check();
    const t = setInterval(check, 4000);
    return () => clearInterval(t);
  }, [employerId, ringFor, phase]);

  useStream((e) => {
    if (e.type === "call.ringing" && (phase === "idle" || phase === "ended")) void ringFor(e.call_id);
  });

  const playTurn = async (t: CallTurn) => {
    setTurns((x) => [...x, t]);
    if (t.done) { setPhase("ended"); setOutcome("ended"); }
    await player.sequence([
      { url: t.audio?.url, who: "saakshi" },
      { url: t.worker_clip, who: "worker" },
      { url: t.follow_audio?.url, who: "saakshi" },
    ]);
  };

  const accept = async (withMic = true) => {
    if (!call) return;
    player.unlock();
    if (withMic) void voice.start();            // the line is open, like a real call: no button to hold
    setPhase("connecting"); reportBusy("employer", true);
    try {
      const t = await api.answer(call.id);
      setStart(Date.now()); setPhase("live"); reportBusy("employer", false);
      await playTurn(t);
    } catch (e) { setErr((e as Error).message); setPhase("idle"); reportBusy("employer", false); }
  };

  const decline = async () => { if (call) await api.decline(call.id); setPhase("idle"); setCall(null); };

  const say = async (f: FormData, shown?: string) => {
    if (!call) return;
    busyRef.current = true; setBusy(true); reportBusy("employer", true); setErr("");
    try {
      if (shown) setTurns((x) => [...x, { who: "employer", text: shown, audio: null }]);
      const t = await api.reply(call.id, f);
      if (!shown) {
        const c = await api.call(call.id);
        const mine = [...c.transcript].reverse().find((x) => x.who === "employer");
        if (mine) setTurns((x) => [...x, mine]);
      }
      busyRef.current = false; setBusy(false); reportBusy("employer", false);
      if (t.done) api.call(call.id).then((c) => setOutcome(c.outcome)).catch(() => {});
      const next = pending.current;
      pending.current = null;
      if (next && !t.done) { setTurns((x) => [...x, t]); onAudioRef.current(next); return; }   // they kept talking
      void playTurn(t);                          // speaking again interrupts Saakshi
    } catch (e) {
      const msg = (e as Error).message;
      busyRef.current = false; setBusy(false); reportBusy("employer", false);
      if (/dropped|no longer/i.test(msg)) { setPhase("ended"); setOutcome("dropped"); }
      else setErr(msg);
    }
  };

  const onAudio = async (wav: Blob) => {
    if (busyRef.current) { pending.current = wav; return; }
    const f = new FormData(); f.append("audio_file", wav, "employer.wav"); await say(f);
  };
  onAudioRef.current = (w) => { if (phase === "live") void onAudio(w); };

  // the demo's autopilot can pick up and speak for the employer (no microphone needed)
  const autoRef = useRef<(text: string, voiced: boolean) => void>(() => {});
  autoRef.current = (text, voiced) => {
    if (text === "__accept__") { if (phase === "ringing") void accept(false); return; }
    if (phase !== "live") return;
    if (!voiced) { void quick(text); return; }
    void (async () => {                         // spoken by Timbre in the employer's voice, heard by Prisma
      reportBusy("employer", true);
      try {
        const c = await api.demoVoice(text, "Vikrant", lang);
        await player.play(c.url, "employer");
        await onAudio(await (await fetch(c.url)).blob());
      } catch { await quick(text); } finally { if (!busyRef.current) reportBusy("employer", false); }
    })();
  };
  useEffect(() => {
    const h = (ev: Event) => { const d = (ev as CustomEvent<{ text: string; voiced: boolean }>).detail; autoRef.current(d.text, d.voiced); };
    window.addEventListener("saakshi:employer-say", h);
    return () => window.removeEventListener("saakshi:employer-say", h);
  }, []);
  const quick = async (text: string) => { player.stop(); const f = new FormData(); f.append("text", text); await say(f, text); };

  const secs = start ? Math.floor((Date.now() - start) / 1000) : 0;
  const lang = call?.language ?? "hi-IN";

  return (
    <div className={`ep ${phase}`}>
        {(phase === "idle") && (
          <motion.div key="idle" className="ep-idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <p className="ep-clock num">{new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</p>
            <p className="small" style={{ opacity: 0.7 }}>Employer's phone</p>
            <p className="small" style={{ opacity: 0.5, marginTop: 40, textAlign: "center", maxWidth: 220 }}>
              When Saakshi calls to confirm a worker's record, it rings here. Use “Ring phone” in the call queue.
            </p>
          </motion.div>
        )}

        {phase === "ringing" && call && (
          <motion.div key="ring" className="ep-ring" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}>
            <p className="small" style={{ opacity: 0.7 }}>Incoming call · for {call.employer?.name}</p>
            <div className="ep-caller">
              <div className="ep-avatar">स</div>
              <p className="ep-caller-name">Saakshi</p>
              <p className="small" style={{ opacity: 0.7 }}>काम-रिकॉर्ड सेवा · work-record service</p>
              <p className="small" style={{ opacity: 0.55, marginTop: 6 }}>about {call.workers?.join(", ")}</p>
            </div>
            <div className="ep-actions">
              <button className="ep-btn decline" onClick={decline} aria-label="Decline">✕</button>
              <button className="ep-btn accept" onClick={() => accept()} aria-label="Accept">☎</button>
            </div>
          </motion.div>
        )}

        {(phase === "connecting" || phase === "live" || phase === "ended") && (
          <motion.div key="live" className="ep-live" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="ep-top">
              <div>
                <p className="ep-caller-name small-name">Saakshi</p>
                <p className="small mono" style={{ opacity: 0.7 }}>{phase === "ended" ? "Call ended" : phase === "connecting" ? "Connecting…" : `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`} · Timbre → you → Prisma</p>
              </div>
              {phase !== "ended" && <button className="ep-btn decline sm" onClick={decline} aria-label="Hang up">✕</button>}
            </div>
            <Scope mic={voice.state === "hearing" ? voice.analyser : null} height={40} tone="call" />
            <div className="ep-log" ref={logRef}>
              {turns.map((t, i) => (
                <div key={i} className={`ep-line ${t.who}`}>
                  <span className="eyebrow">{t.who === "saakshi" ? "Saakshi" : "You"}{t.intent ? ` · ${t.intent.replace("_", " ")}` : ""}</span>
                  <p className={isDeva(t.text) ? "deva-text" : ""}>{t.text}</p>
                  {t.worker_clip && <p className="ep-clip small">▶ plays the worker's own voice note</p>}
                  {t.follow_text && <p className={isDeva(t.follow_text) ? "deva-text" : ""}>{t.follow_text}</p>}
                </div>
              ))}
              {busy && <p className="small" style={{ opacity: 0.6 }}>Prisma heard you · Saakshi is thinking<span className="dots" /></p>}
            </div>
            {phase === "live" && (
              <div className="ep-dock">
                <VoiceOrb voice={voice} busy={busy} lang={lang} size={60} tone="call" />
                <div className="ep-quick">
                  {(lang === "en-IN" ? QUICK_EN : QUICK_HI).map((q) => <button key={q} onClick={() => quick(q)} disabled={busy}>{q}</button>)}
                </div>
              </div>
            )}
            {phase === "ended" && (
              <div className="ep-ended">
                <p className="h3" style={{ color: "#fff" }}>{outcome === "dropped" ? "Call dropped · Saakshi will call again" : outcome && OUTCOME_LABEL[outcome] ? OUTCOME_LABEL[outcome] : "Call ended"}</p>
                <button className="btn btn-sm" style={{ background: "rgba(255,255,255,.12)", color: "#fff" }} onClick={() => { setPhase("idle"); setCall(null); }}>Done</button>
              </div>
            )}
            {err && <p className="error-line">{err}</p>}
          </motion.div>
        )}
    </div>
  );
}
