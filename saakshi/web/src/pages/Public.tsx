import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Passport } from "../lib/api";
import { ROLE_LABEL, inr } from "../lib/util";
import { Chip } from "../components/bits";
import { IncomeChart } from "../components/IncomeChart";
import { LevelBadge } from "../components/Level";

/** What a lender, landlord or welfare board sees after scanning the QR. */
export function PublicPassport() {
  const { token = "" } = useParams();
  const [d, setD] = useState<Record<string, any> | null>(null);
  const [err, setErr] = useState("");
  const [lvl, setLvl] = useState<1 | 2 | 3>(1);
  useEffect(() => { api.publicPassport(token).then(setD).catch((e) => setErr(e.message)); }, [token]);
  if (err) return <main className="wrap page verify"><div className="sheet verify-card"><p className="eyebrow">Saakshi verification</p><p className="h2" style={{ marginTop: 10 }}>{err}</p></div></main>;
  if (!d) return <main className="wrap page"><span className="spinner" /></main>;
  const s = d.stats || {};
  const scopeName: Record<string, string> = { full: "Full work & income history", income_band: "Income band only", bocw: "Construction work days" };
  return (
    <main className="wrap page verify">
      <article className="sheet verify-card">
        <div className="spread" style={{ flexWrap: "wrap" }}>
          <p className="eyebrow">Saakshi verification · {scopeName[d.scope]}</p>
          <div className="row">
            <Chip status={d.signature_valid ? "verified" : "disputed"} label={d.signature_valid ? "Signature valid" : "Signature invalid"} />
            <Chip status={d.chain.intact ? "verified" : "disputed"} label={d.chain.intact ? "Records unaltered" : "Records altered"} />
          </div>
        </div>
        <h1 className="h1" style={{ marginTop: 14 }}>{d.worker.name}</h1>
        <p className="muted">{ROLE_LABEL[d.worker.role]} · {d.worker.city}, {d.worker.state} · phone ending {d.worker.phone_last4}</p>
        {d.audience && <p className="small faint">Shared with: {d.audience} · link expires {new Date(d.expires_at).toLocaleDateString()}</p>}

        <div className="pp-kpis" style={{ marginTop: 24 }}>
          {s.income_band && <div><span className="num" style={{ fontSize: 21, lineHeight: 1.2 }}>{s.income_band}</span><span className="eyebrow">verified income band</span></div>}
          {s.avg_monthly_verified != null && <div><span className="num">{inr(s.avg_monthly_verified)}</span><span className="eyebrow">verified avg / month</span></div>}
          {s.months_verified != null && <div><span className="num">{s.months_verified}</span><span className="eyebrow">months verified (12 mo)</span></div>}
          {s.employers != null && <div><span className="num">{s.employers}</span><span className="eyebrow">employers</span></div>}
          {s.strength != null && <div><span className="num">{s.strength}</span><span className="eyebrow">trust score</span></div>}
        </div>

        {s.levels && (
          <div className="pp-sec">
            <p className="eyebrow" style={{ marginBottom: 10 }}>How strong is the evidence?</p>
            <div className="lvl-summary">
              {[3, 2, 1, 0].map((k) => <div key={k}><LevelBadge level={k} /><span className="num">{s.levels[k] ?? 0}</span><span className="small faint">records</span></div>)}
            </div>
          </div>
        )}
        {d.months && (
          <div className="pp-sec">
            <div className="spread" style={{ flexWrap: "wrap", marginBottom: 12 }}>
              <p className="eyebrow" style={{ margin: 0 }}>Income, last 12 months · count only evidence at or above</p>
              <div className="seg">{([1, 2, 3] as const).map((k) => <button key={k} className={lvl === k ? "on" : ""} onClick={() => setLvl(k)}>L{k}</button>)}</div>
            </div>
            <IncomeChart months={d.months as Passport["months"]} level={lvl} />
          </div>
        )}
        {d.employers && (
          <div className="pp-sec">
            <p className="eyebrow">Employers</p>
            <table className="ledger"><thead><tr><th>Employer</th><th>Since</th><th>Until</th><th className="r">Records</th><th className="r">Verified</th></tr></thead>
              <tbody>{(d.employers as Passport["employers"]).map((e, i) => <tr key={i}><td><b>{e.name}</b></td><td>{e.since}</td><td>{e.until}</td><td className="r">{e.records}</td><td className="r">{e.verified}</td></tr>)}</tbody></table>
          </div>
        )}
        {d.bocw && d.scope === "bocw" && (
          <div className="pp-sec">
            <p className="eyebrow">Construction work days (last 12 months)</p>
            <p className="h2">{d.bocw.days} verified days <span className="faint">/ {d.bocw.required} required</span></p>
            <Chip status={d.bocw.eligible ? "verified" : "pending"} label={d.bocw.eligible ? "Meets the 90-day requirement" : "Below 90 days"} />
          </div>
        )}
        <p className="small faint" style={{ marginTop: 28 }}>
          Every record was confirmed by the employer on a recorded phone call, or is marked otherwise. Records are hash-chained,
          so any edit after the fact breaks the chain. Generated {new Date(d.generated_at).toLocaleString()}.
        </p>
      </article>
    </main>
  );
}

/** Printable certificate for a construction welfare board (90 days of building work). */
export function Certificate() {
  const { id = "" } = useParams();
  const [p, setP] = useState<Passport | null>(null);
  useEffect(() => { api.worker(id).then((d) => setP(d.passport)).catch(() => {}); }, [id]);
  if (!p) return <main className="wrap page"><span className="spinner" /></main>;
  const b = p.bocw;
  return (
    <main className="wrap page">
      <article className="sheet cert">
        <p className="eyebrow" style={{ textAlign: "center" }}>Saakshi · employment certificate for welfare board registration</p>
        <h1 className="h1" style={{ textAlign: "center", margin: "18px 0 6px" }}>Certificate of building work</h1>
        <p className="deva" style={{ textAlign: "center", fontSize: 20, margin: 0 }}>भवन निर्माण कार्य प्रमाणपत्र</p>
        <p className="cert-body">
          This is to record that <b>{p.worker.name}</b>, {ROLE_LABEL[p.worker.role].toLowerCase()} of {p.worker.city}, {p.worker.state}{" "}
          (mobile ending {p.worker.phone_last4}), performed <b>{b.days} days</b> of building or other construction work in the twelve
          months preceding {new Date(p.generated_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })},
          as confirmed by the employers listed below on recorded calls.
        </p>
        <table className="ledger"><thead><tr><th>Employer / contractor</th><th>Period</th><th className="r">Days</th></tr></thead>
          <tbody>{b.rows.map((r, i) => <tr key={i}><td>{r.employer}</td><td>{r.period}</td><td className="r num">{r.days}</td></tr>)}</tbody></table>
        <div className="cert-foot">
          <Chip status={b.eligible ? "verified" : "pending"} label={b.eligible ? `Meets the ${b.required}-day requirement` : `${b.required - b.days} days short of ${b.required}`} />
          <span className="mono small faint">signature {p.signature.slice(0, 20)}… · chain {p.chain.intact ? "intact" : "broken"}</span>
        </div>
        <p className="small faint">Prepared from voice-confirmed records. The welfare board makes the final decision on registration.</p>
      </article>
      <div className="row no-print" style={{ marginTop: 16 }}><button className="btn btn-ghost" onClick={() => window.print()}>Print / save PDF</button></div>
    </main>
  );
}
