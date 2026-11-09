import { useMemo, useState } from "react";
import type { Passport } from "../lib/api";
import { inr } from "../lib/util";
import { monthShort, tx } from "../lib/i18n";

/** Monthly income: verified (solid) with the not-yet-verified remainder stacked
    on top (hatched). One axis, legend, hover tooltip, and a table view. */
export function IncomeChart({ months: raw, height = 220, level = 1, lang = "en-IN" }: { months: Passport["months"]; height?: number; level?: 1 | 2 | 3; lang?: string }) {
  const L = (m: { month: string; label: string }) => lang === "en-IN" ? m.label : `${monthShort(m.month, lang)} ${m.month.slice(2, 4)}`;
  // "verified" means: counted at the chosen evidence level
  const months = raw.map((m) => ({ ...m, verified: level === 1 ? m.verified : level === 2 ? m.l2 ?? 0 : m.l3 ?? 0 }));
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const max = useMemo(() => {
    const m = Math.max(1, ...months.map((x) => x.claimed));
    const pow = 10 ** Math.floor(Math.log10(m));
    return Math.ceil(m / pow / 2) * pow * 2;
  }, [months]);
  const W = 640, H = height, padL = 52, padB = 26, padT = 12;
  const plotW = W - padL - 8, plotH = H - padB - padT;
  const bw = plotW / months.length;
  const y = (v: number) => padT + plotH - (v / max) * plotH;
  const ticks = [0, max / 2, max];

  return (
    <div className="income-chart">
      <div className="spread" style={{ marginBottom: 10 }}>
        <div className="legend">
          <span><i className="sw verified" />{level === 1 ? tx(lang, "Employer confirmed (L1+)") : level === 2 ? tx(lang, "Payment proven (L2+)") : tx(lang, "Established (L3)")}</span>
          <span><i className="sw claimed" />{level === 1 ? tx(lang, "Claimed, not yet confirmed") : tx(lang, "Below this level")}</span>
        </div>
        <button className="link small" onClick={() => setTable(!table)}>{table ? tx(lang, "Show chart") : tx(lang, "Show table")}</button>
      </div>
      {table ? (
        <table className="tbl">
          <thead><tr><th>{tx(lang, "Month")}</th><th>{tx(lang, "Verified")}</th><th>{tx(lang, "Claimed")}</th></tr></thead>
          <tbody>{months.map((m) => <tr key={m.month}><td>{L(m)}</td><td className="mono">{inr(m.verified)}</td><td className="mono">{inr(m.claimed)}</td></tr>)}</tbody>
        </table>
      ) : (
        <div style={{ position: "relative" }}>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Monthly income, verified and claimed">
            <defs>
              <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill="rgba(210,123,44,0.18)" />
                <line x1="0" y1="0" x2="0" y2="6" stroke="#d27b2c" strokeWidth="2" />
              </pattern>
            </defs>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={padL} x2={W - 8} y1={y(t)} y2={y(t)} stroke="rgba(29,27,23,0.09)" />
                <text x={padL - 8} y={y(t) + 4} textAnchor="end" className="axis">{t === 0 ? "0" : inr(t).replace("₹", "₹")}</text>
              </g>
            ))}
            {months.map((m, i) => {
              const x = padL + i * bw + bw * 0.2;
              const w = bw * 0.6;
              const vTop = y(m.verified);
              const cTop = y(m.claimed);
              const rest = m.claimed - m.verified;
              return (
                <g key={m.month} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <rect x={padL + i * bw} y={padT} width={bw} height={plotH} fill={hover === i ? "rgba(29,27,23,0.04)" : "transparent"} />
                  {rest > 0 && (
                    <path d={roundTop(x, cTop, w, Math.max(0, vTop - cTop - (m.verified > 0 ? 2 : 0)), m.verified > 0 ? 0 : 4)} fill="url(#hatch)" />
                  )}
                  {m.verified > 0 && <path d={roundTop(x, vTop, w, y(0) - vTop, rest > 0 ? 0 : 4)} fill="#3a6ccb" />}
                  <text x={x + w / 2} y={H - 8} textAnchor="middle" className="axis">{lang === "en-IN" ? m.label.split(" ")[0] : monthShort(m.month, lang)}</text>
                </g>
              );
            })}
            <line x1={padL} x2={W - 8} y1={y(0)} y2={y(0)} stroke="rgba(29,27,23,0.3)" />
          </svg>
          {hover !== null && (
            <div className="tip" style={{ left: `${((padL + hover * bw + bw / 2) / W) * 100}%` }}>
              <b>{L(months[hover])}</b>
              <span><i className="sw verified" />{tx(lang, "Verified")} <b className="mono">{inr(months[hover].verified)}</b></span>
              <span><i className="sw claimed" />{tx(lang, "Claimed")} <b className="mono">{inr(months[hover].claimed)}</b></span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function roundTop(x: number, top: number, w: number, h: number, r: number) {
  if (h <= 0) return "";
  const rr = Math.min(r, h, w / 2);
  return `M${x},${top + h} L${x},${top + rr} Q${x},${top} ${x + rr},${top} L${x + w - rr},${top} Q${x + w},${top} ${x + w},${top + rr} L${x + w},${top + h} Z`;
}
