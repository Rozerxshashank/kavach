import type { WorkerDetail } from "../lib/api";
import { inr } from "../lib/util";
import { agoIn, eventText, monthShort, t, tx } from "../lib/i18n";

type Props = { d: WorkerDetail; lang: string; onSpeak: () => void; onOpen: (tab: "record" | "share") => void };

/** The worker's home: what her record is worth today, what is still waiting, and the one next thing to do. */
export function WorkerHome({ d, lang, onSpeak, onOpen }: Props) {
  const p = d.passport;
  const s = p.stats;
  const first = d.worker.name.split(" ")[0];
  const months = p.months.slice(-6);
  const peak = Math.max(1, ...months.map((m) => Math.max(m.verified, m.claimed)));
  const live = d.entries.filter((e) => e.status !== "withdrawn");

  // what is still waiting on someone else
  const openLinks = d.links.filter((l) => l.status !== "done");
  const calling = live.filter((e) => ["pending", "calling", "queued", "callback"].includes(e.status)
    && !openLinks.some((l) => l.entry_ids.includes(e.id)));
  const dues = live.filter((e) => e.paid != null && e.paid < e.amount && e.status !== "disputed")
    .map((e) => ({ e, owed: e.amount - (e.paid ?? 0) }));
  const owed = dues.reduce((n, x) => n + x.owed, 0);
  const isBuild = ["construction", "painter", "plumber", "electrician"].includes(d.worker.role);

  const next = !live.length
    ? { t: tx(lang, "Record your first work", "अपना पहला काम बोलकर लिखवाइए"), d: tx(lang, "Takes a minute. Just talk, like on a phone call.", "एक मिनट लगता है। जैसे फ़ोन पर बात करती हैं, वैसे ही बोलिए।"), act: onSpeak, cta: t("speakNew", lang) }
    : openLinks.some((l) => l.status === "sent")
      ? { t: tx(lang, "{n} confirmation link(s) not sent yet", "{n} लिंक भेजना बाकी है", { n: openLinks.filter((l) => l.status === "sent").length }), d: tx(lang, "Send them on WhatsApp. Employers confirm in about 20 seconds.", "व्हाट्सऐप पर भेजिए। नियोक्ता 20 सेकंड में पुष्टि कर देते हैं।"), act: undefined, cta: "" }
      : !d.worker.upi_id
        ? { t: tx(lang, "Add your UPI ID to reach Level 2", "UPI ID जोड़िए, लेवल 2 पाइए"), d: tx(lang, "When employers pay you there, the payment is proven from both sides.", "नियोक्ता उसी पर पैसे भेजें, तो भुगतान दोनों तरफ़ से साबित होता है।"), act: () => onOpen("share"), cta: tx(lang, "Add UPI", "UPI जोड़ें") }
        : isBuild && !p.bocw.eligible
          ? { t: tx(lang, "{n} more days for the welfare board", "कल्याण बोर्ड के लिए {n} दिन और", { n: p.bocw.required - p.bocw.days }), d: tx(lang, "At 90 verified days, the certificate prints from here.", "90 पक्के दिन होने पर प्रमाणपत्र यहीं से छपता है।"), act: () => onOpen("share"), cta: tx(lang, "See progress", "देखें") }
          : s.months_verified < 6
            ? { t: tx(lang, "{n} more verified month(s)", "{n} और पक्के महीने", { n: 6 - s.months_verified }), d: tx(lang, "Six verified months is what most lenders look for.", "छह महीने का पक्का रिकॉर्ड ज़्यादातर बैंकों के लिए काफ़ी होता है।"), act: onSpeak, cta: t("speakNew", lang) }
            : { t: tx(lang, "Your record is ready for a lender", "आपका रिकॉर्ड तैयार है"), d: tx(lang, "Send a bank or landlord one link. You choose what they see.", "बैंक या मकान मालिक को एक लिंक भेजिए। आप तय करती हैं कि वे क्या देखें।"), act: () => onOpen("share"), cta: tx(lang, "Share", "शेयर करें") };

  return (
    <div className="wh">
      <p className="wh-hello">{tx(lang, "Hello, {name}", "नमस्ते, {name}", { name: first })}</p>

      <section className="wh-card">
        <div className="wh-card-top">
          <div>
            <p className="eyebrow">{tx(lang, "Verified income · per month", "पक्की औसत कमाई · महीना")}</p>
            <p className="num wh-big">{s.avg_monthly_verified ? inr(s.avg_monthly_verified) : "—"}</p>
            <p className="small wh-band">{s.months_verified} {tx(lang, "verified months", "पक्के महीने")} · {s.employers} {tx(lang, "employers", "नियोक्ता")}</p>
          </div>
          <Ring value={s.strength} label={tx(lang, "trust", "भरोसा")} />
        </div>
        <div className="wh-bars" aria-label="Last six months">
          {months.map((m) => (
            <div key={m.month} title={`${m.label}: ${inr(m.verified)} verified, ${inr(m.claimed)} claimed`}>
              <span className="wh-bar">
                <i className="claimed" style={{ height: `${(Math.max(m.claimed, m.verified) / peak) * 100}%` }} />
                <i className="verified" style={{ height: `${(m.verified / peak) * 100}%` }} />
              </span>
              <span className="wh-bar-l">{monthShort(m.month, lang)}</span>
            </div>
          ))}
        </div>
        <div className="wh-levels">
          {[0, 1, 2, 3].map((k) => (
            <span key={k} className={`wh-lvl l${k}`}><b className="num">{s.levels[String(k)] ?? 0}</b> L{k}</span>
          ))}
          <button className="link small" onClick={() => onOpen("record")}>{tx(lang, "Full record", "पूरा रिकॉर्ड")} →</button>
        </div>
      </section>

      <section className="wh-next">
        <p className="eyebrow">{tx(lang, "Next step", "अगला कदम")}</p>
        <p className="wh-next-t">{next.t}</p>
        <p className="small muted" style={{ margin: 0 }}>{next.d}</p>
        {next.act && next.cta && <button className="btn btn-sm btn-ink" style={{ justifySelf: "start", marginTop: 8 }} onClick={next.act}>{next.cta}</button>}
      </section>

      {(openLinks.length > 0 || calling.length > 0) && (
        <section className="wh-list">
          <p className="eyebrow">{tx(lang, "Waiting for confirmation", "पुष्टि का इंतज़ार")}</p>
          {openLinks.map((l) => (
            <div key={l.token} className="wh-row">
              <div style={{ minWidth: 0 }}>
                <p className="wh-row-t">{l.employer_name}</p>
                <p className="small faint">{l.entry_ids.length} {tx(lang, "record(s)", "रिकॉर्ड")} · {l.status === "opened" ? (tx(lang, "link opened", "लिंक खोला गया")) : (tx(lang, "link not sent", "लिंक भेजना बाकी"))}</p>
              </div>
              <a className="btn btn-sm wa-green" href={l.whatsapp} target="_blank" rel="noreferrer">{l.status === "opened" ? (tx(lang, "Remind", "याद दिलाएँ")) : "WhatsApp"}</a>
            </div>
          ))}
          {calling.map((e) => (
            <div key={e.id} className="wh-row">
              <div style={{ minWidth: 0 }}>
                <p className="wh-row-t">{e.employer_name}</p>
                <p className="small faint">{e.period_label} · {inr(e.amount)}</p>
              </div>
              <span className="chip calling"><i>☎</i>{tx(lang, "Calling", "फ़ोन पर पुष्टि")}</span>
            </div>
          ))}
        </section>
      )}

      {dues.length > 0 && (
        <section className="wh-list wh-dues">
          <p className="eyebrow">{tx(lang, "Money still owed", "बाकी पैसे")} · <b className="num">{inr(owed)}</b></p>
          {dues.slice(0, 4).map(({ e, owed: o }) => (
            <div key={e.id} className="wh-row">
              <div style={{ minWidth: 0 }}>
                <p className="wh-row-t">{e.employer_name}</p>
                <p className="small faint">{e.period_label}</p>
              </div>
              <span className="num">{inr(o)}</span>
            </div>
          ))}
          <p className="small faint" style={{ margin: "4px 0 0" }}>{tx(lang, "This is on your record, as evidence if you ever need it.", "यह रिकॉर्ड में दर्ज है, ज़रूरत पड़े तो सबूत के तौर पर काम आएगा।")}</p>
        </section>
      )}

      {d.events.length > 0 && (
        <section className="wh-list">
          <p className="eyebrow">{tx(lang, "Recently", "हाल में")}</p>
          {d.events.slice(0, 4).map((ev) => (
            <div key={ev.id} className="wh-ev">
              <span className={`wh-ev-dot ${ev.kind.split(".")[0]}`} />
              <p className="small" style={{ margin: 0 }}>{eventText(ev.kind, ev.text, lang)}</p>
              <span className="small faint">{agoIn(ev.at, lang)}</span>
            </div>
          ))}
        </section>
      )}

      <button className="btn btn-primary wh-speak" onClick={onSpeak}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
        {t("speakNew", lang)}
      </button>
    </div>
  );
}

function Ring({ value, label }: { value: number; label: string }) {
  const r = 26, c = 2 * Math.PI * r;
  const color = value >= 70 ? "var(--ok)" : value >= 40 ? "var(--wait-mark)" : "var(--bad)";
  return (
    <div className="wh-ring" title={`Trust score ${value}/100`}>
      <svg width="66" height="66" viewBox="0 0 66 66">
        <circle cx="33" cy="33" r={r} fill="none" stroke="var(--rule)" strokeWidth="5" />
        <circle cx="33" cy="33" r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${(value / 100) * c} ${c}`} transform="rotate(-90 33 33)" />
      </svg>
      <span className="num">{value}</span>
      <span className="wh-ring-l">{label}</span>
    </div>
  );
}
