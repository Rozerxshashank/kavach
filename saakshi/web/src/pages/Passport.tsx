import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type WorkerDetail } from "../lib/api";
import { ROLE_LABEL, inr, monthRange, useStream } from "../lib/util";
import { Chip, Confidence, QR, Reasons, Wave } from "../components/bits";
import { IncomeChart } from "../components/IncomeChart";
import { LevelBadge } from "../components/Level";

export default function PassportPage() {
  const { id = "" } = useParams();
  const [d, setD] = useState<WorkerDetail | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [lvl, setLvl] = useState<1 | 2 | 3>(1);
  const load = useCallback(() => api.worker(id).then(setD).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { void load(); }, [load]);
  useStream((e) => { if (e.type === "call.ended" || e.type === "world.changed") void load(); });

  if (err) return <main className="wrap page"><p className="error-line">{err}</p></main>;
  if (!d) return <main className="wrap page"><span className="spinner" /></main>;
  const p = d.passport, s = p.stats, w = d.worker;
  const share = async () => {
    const sh = await api.share(id, { scope: "full", audience: "Lender", days: 30 });
    setLink(`${location.origin}/p/${sh.token}`);
  };
  const isBuild = ["construction", "painter", "plumber", "electrician"].includes(w.role);

  return (
    <main className="wrap page passport">
      <article className="sheet pp">
        <header className="pp-head">
          <div>
            <p className="eyebrow">Kaam Passport · कामपासपोर्ट</p>
            <h1 className="h1" style={{ marginTop: 8 }}>{w.name}</h1>
            <p className="muted">{ROLE_LABEL[w.role]} · {w.city}, {w.state} · phone ending {w.phone.slice(-4)}</p>
          </div>
          <div className="pp-qr">
            {link ? <><QR text={link} size={112} /><a className="link small mono" href={link} target="_blank" rel="noreferrer">verify link</a></>
              : <button className="btn btn-ghost btn-sm no-print" onClick={share}>Create verification QR</button>}
          </div>
        </header>

        <div className="pp-kpis">
          <div><span className="num">{inr(s.avg_monthly_verified)}</span><span className="eyebrow">verified income / month</span><span className="small faint">{s.income_band}</span></div>
          <div><span className="num">{s.months_verified}<span className="faint" style={{ fontSize: "0.5em" }}> / 12</span></span><span className="eyebrow">months verified</span></div>
          <div><span className="num">{Math.round(s.verified_share * 100)}%</span><span className="eyebrow">of claimed income verified</span></div>
          <div><span className="num">{s.employers}</span><span className="eyebrow">employers · longest {s.longest_tenure_months} mo</span></div>
          <div><span className={`num ${s.fraud_flags ? "c-bad" : ""}`}>{s.strength}</span><span className="eyebrow">trust score / 100</span>{s.fraud_flags > 0 && <span className="small" style={{ color: "var(--bad)" }}>{s.fraud_flags} fraud signal(s)</span>}</div>
        </div>

        <section className="pp-sec">
          <p className="eyebrow">Evidence behind this income</p>
          <div className="lvl-summary">
            {[3, 2, 1, 0].map((k) => (
              <div key={k}><LevelBadge level={k} /><span className="num">{s.levels?.[k] ?? 0}</span><span className="small faint">records</span></div>
            ))}
          </div>
        </section>

        <section className="pp-sec">
          <div className="spread" style={{ flexWrap: "wrap", marginBottom: 12 }}>
            <p className="eyebrow" style={{ margin: 0 }}>Income, last 12 months</p>
            <div className="seg">{([1, 2, 3] as const).map((k) => <button key={k} className={lvl === k ? "on" : ""} onClick={() => setLvl(k)}>Count from L{k}</button>)}</div>
          </div>
          <IncomeChart months={p.months} level={lvl} />
        </section>

        <section className="pp-sec">
          <p className="eyebrow">Records · newest first · tap one to see why it's trusted</p>
          <table className="ledger">
            <thead><tr><th>Employer</th><th>Period</th><th className="r">Amount</th><th>Evidence</th><th>Confidence</th></tr></thead>
            <tbody>
              {d.entries.map((e) => (
                <Fragment key={e.id}>
                  <tr onClick={() => setOpen(open === e.id ? null : e.id)} className={open === e.id ? "open" : ""}>
                    <td><b>{e.employer_name}</b><span className="small faint"> {e.employer_kind === "contractor" ? "· contractor" : ""}</span></td>
                    <td>{monthRange(e.period_start, e.period_end)}{e.days ? <span className="faint"> · {e.days} d</span> : ""}</td>
                    <td className="r num">{inr(e.employer_says?.amount ?? e.amount)}{e.employer_says?.amount && e.employer_says.amount !== e.amount ? <span className="small faint"> (said {inr(e.amount)})</span> : ""}</td>
                    <td>{(e.level ?? 0) > 0 ? <LevelBadge level={e.level} small /> : <Chip status={e.status} />}</td>
                    <td><Confidence value={e.confidence} /></td>
                  </tr>
                  {open === e.id && (
                    <tr className="ledger-x"><td colSpan={5}>
                      <div className="ledger-more">
                        <Reasons reasons={e.reasons} />
                        <div className="small faint mono">
                          record #{e.seq} · hash {e.hash.slice(0, 12)}… · prev {e.prev_hash.slice(0, 8)}…
                          {e.attested_by ? ` · confirmed by ${e.attested_by.replace("household:", "household member: ")}` : ""}
                        </div>
                        {e.source_audio && <div style={{ maxWidth: 360 }}><Wave clip={{ url: e.source_audio, duration: 0, peaks: Array(48).fill(0.5) }} who="worker" label="Worker's voice note" /></div>}
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </section>

        {isBuild && (
          <section className="pp-sec">
            <p className="eyebrow">Construction welfare board (BOCW) eligibility</p>
            <div className="bocw">
              <div className="bocw-bar"><i style={{ width: `${Math.min(100, (p.bocw.days / p.bocw.required) * 100)}%` }} /><span className="bocw-mark" /></div>
              <p><b className="num" style={{ fontSize: 26 }}>{p.bocw.days}</b> of {p.bocw.required} verified days in the last 12 months{p.bocw.estimated ? " (some estimated)" : ""} ·
                {p.bocw.eligible ? <> <Chip status="verified" label="Eligible to register" /> <Link className="link" to={`/bocw/${id}`}>Certificate →</Link></> : <> <Chip status="pending" label={`${p.bocw.required - p.bocw.days} days to go`} /></>}
              </p>
            </div>
          </section>
        )}

        <footer className="pp-foot">
          <span className="mono small">{p.chain.intact ? "✓ record chain intact" : "✕ record chain broken"} · {p.chain.length} records · head {p.chain.head.slice(0, 10)}…</span>
          <span className="mono small">signature {p.signature.slice(0, 16)}… · {new Date(p.generated_at).toLocaleString()}</span>
        </footer>
      </article>
      <div className="row no-print" style={{ marginTop: 18, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" onClick={() => window.print()}>Print / save PDF</button>
        <Link className="btn btn-ghost" to="/demo">Back to demo</Link>
      </div>
    </main>
  );
}
