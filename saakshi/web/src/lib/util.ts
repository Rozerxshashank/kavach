import { useEffect, useRef } from "react";

export function inr(n: number | null | undefined): string {
  if (n == null) return "—";
  const s = Math.round(Math.abs(n)).toString();
  let out = s;
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const tail = s.slice(-3);
    const groups: string[] = [];
    while (head.length > 2) { groups.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) groups.unshift(head);
    out = groups.join(",") + "," + tail;
  }
  return (n < 0 ? "-" : "") + "₹" + out;
}

export const STATUS_LABEL: Record<string, string> = {
  verified: "Verified", corrected: "Employer corrected", pending: "Awaiting call", calling: "Calling employer",
  disputed: "Not confirmed", unconfirmed: "Unreachable", self_declared: "Self-declared",
  queued: "Queued", ringing: "Ringing", in_call: "On call", callback: "Call back later", done: "Done",
  withdrawn: "Withdrawn",
};
export const STATUS_ICON: Record<string, string> = {
  verified: "✓", corrected: "✓", pending: "…", calling: "☎", disputed: "✕", unconfirmed: "–", self_declared: "✎",
  queued: "…", ringing: "☎", in_call: "☎", callback: "↻", done: "•", withdrawn: "↩",
};
export const OUTCOME_LABEL: Record<string, string> = {
  verified: "Confirmed", corrected: "Confirmed with corrections", disputed: "Not confirmed", declined: "Declined",
  callback: "Asked to call back", opted_out: "Opted out", unclear: "Couldn't hear", no_answer: "No answer", bulk: "Crew confirmed",
};
export const ROLE_LABEL: Record<string, string> = {
  domestic: "Domestic worker", cook: "Cook", nanny: "Nanny", driver: "Driver", construction: "Construction worker",
  painter: "Painter", plumber: "Plumber", electrician: "Electrician", tailor: "Tailor", security: "Security guard",
  delivery: "Delivery partner", other: "Worker",
};
export const PERSONA_LABEL: Record<string, string> = {
  honest: "Honest", corrects: "Corrects the amount", suspicious: "Suspicious of calls", busy: "Busy, call back",
  son: "Son answers", denies: "Denies", colluder: "Colluder", optout: "Opts out", contractor: "Contractor (crew)",
  english: "Answers in English",
};

export const LEVEL: Record<number, { name: string; hi: string; desc: string }> = {
  0: { name: "Unverified", hi: "अपुष्ट", desc: "The worker's own statement, or a record with a fraud signal" },
  1: { name: "Employer confirmed", hi: "नियोक्ता ने पुष्टि की", desc: "Confirmed by the employer on a recorded call or by voice on a link" },
  2: { name: "Payment proven", hi: "भुगतान साबित", desc: "Employer confirmed, and the UPI payment is backed by evidence" },
  3: { name: "Established", hi: "पक्का रिकॉर्ड", desc: "Payment proven, and 3+ months confirmed by the same employer" },
};

export function upiLink(vpa: string, name: string, amount: number, note: string) {
  const q = new URLSearchParams({ pa: vpa, pn: name, am: String(Math.round(amount)), cu: "INR", tn: note.slice(0, 60) });
  return `upi://pay?${q.toString()}`;
}

export function isDeva(s: string) { return /[ऀ-ॿ]/.test(s); }

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function monthRange(a: string, b: string, lang = "en-IN") {
  const s = new Date(a), e = new Date(b);
  const fmt = (d: Date) => { try { return d.toLocaleDateString(lang, { month: "short", year: "2-digit" }); } catch { return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" }); } };
  return fmt(s) === fmt(e) ? fmt(s) : `${fmt(s)} – ${fmt(e)}`;
}

/* One live connection per tab, shared by every component.
   Browsers allow ~6 open connections per site; one EventSource per component
   (worker phone, queue, log, employer phone…) used them all up and left every
   normal request waiting forever. */
type StreamListener = (e: { type: string; [k: string]: any }) => void;
const streamListeners = new Set<StreamListener>();
let sharedSource: EventSource | null = null;
let reopenTimer: ReturnType<typeof setTimeout> | undefined;

let lastSeq: number | null = null;

function emitLocal(ev: { type: string; [k: string]: any }) {
  streamListeners.forEach((l) => { try { l(ev); } catch { /* one bad listener must not break the rest */ } });
}

let ticket: { t: string; at: number } | null = null;
let opening = false;

/** A signed pass that lets this tab's live stream include the logged-in worker's own events (or, with the
    operator key, everything). Without one the stream carries only the public demo. Renewed every few hours. */
async function streamTicket(): Promise<string> {
  if (ticket && Date.now() - ticket.at < 6 * 3600_000) return ticket.t;
  try {
    const { api } = await import("./api");
    const { auth } = await import("./auth");
    const r = await api.streamTicket(auth.me());
    ticket = { t: r.ticket, at: Date.now() };
    return r.ticket;
  } catch { return ""; }
}

/** Forget the pass (after logging in or out) so the next connection asks again. */
export function resetStream() {
  ticket = null;
  if (sharedSource) { sharedSource.close(); sharedSource = null; void openShared(); }
}

async function openShared() {
  if (sharedSource || opening || !streamListeners.size) return;
  opening = true;
  const t = await streamTicket();
  opening = false;
  if (sharedSource || !streamListeners.size) return;
  // on reconnect, ask for everything after the last event we saw, so nothing is lost in the gap
  const q = new URLSearchParams();
  if (lastSeq !== null) q.set("after", String(lastSeq));
  if (t) q.set("t", t);
  const es = new EventSource(`/api/stream${q.toString() ? `?${q}` : ""}`);
  const isReconnect = lastSeq !== null;
  sharedSource = es;
  es.onmessage = (m) => {
    let ev: { type: string; seq?: number; restarted?: boolean };
    try { ev = JSON.parse(m.data); } catch { return; }
    if (ev.type === "hello") {
      const restarted = ev.restarted || (lastSeq !== null && (ev.seq ?? 0) < lastSeq);
      if (restarted) lastSeq = ev.seq ?? 0;
      if (lastSeq === null) lastSeq = ev.seq ?? 0;
      // after a server restart or a reconnect, every screen refreshes its data
      if (restarted || isReconnect) emitLocal({ type: "world.changed", local: true });
      return;
    }
    if (typeof ev.seq === "number") lastSeq = ev.seq;
    emitLocal(ev);
  };
  es.onerror = () => {
    es.close();
    if (sharedSource === es) sharedSource = null;
    clearTimeout(reopenTimer);
    reopenTimer = setTimeout(() => void openShared(), 2000);
  };
}

/** Subscribe to the server's live event stream. */
export function useStream(onEvent: (e: { type: string; [k: string]: any }) => void) {
  const ref = useRef(onEvent);
  ref.current = onEvent;
  useEffect(() => {
    const listener: StreamListener = (e) => ref.current(e);
    streamListeners.add(listener);
    void openShared();
    return () => {
      streamListeners.delete(listener);
      if (!streamListeners.size && sharedSource) { sharedSource.close(); sharedSource = null; }
    };
  }, []);
}
