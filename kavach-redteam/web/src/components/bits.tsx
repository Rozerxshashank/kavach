import type { ToolEvent } from "../api";
import { STATUS_WORD, toolCall } from "../lib/format";

export function ToolLine({ t }: { t: ToolEvent }) {
  const bad = t.sensitive && t.executed && !t.verified_at_call;
  const cls = t.blocked_by_gate ? "blocked" : bad ? "bad" : "";
  const res = typeof t.result === "object" ? JSON.stringify(t.result) : String(t.result);
  return (
    <div className={`toolcall ${cls}`}>
      <span className="gear">⚙ banking API</span>
      <code>{toolCall(t.name, t.args)}</code>
      <span className="res">→ {res.length > 120 ? res.slice(0, 120) + "…" : res}</span>
      {bad && <span className="tag breached">unverified</span>}
      {t.blocked_by_gate && <span className="tag contained">blocked by {t.blocked_by === "Kavach Shield" ? "Shield" : "gate"}</span>}
    </div>
  );
}

export function StatusTag({ status }: { status: string }) {
  return <span className={`tag ${status}`}>{STATUS_WORD[status] ?? status}</span>;
}

export function Composure({ value, label = "Agent composure" }: { value: number; label?: string }) {
  const color = value >= 75 ? "var(--held)" : value >= 45 ? "var(--amber)" : "var(--breach)";
  const lit = Math.round(value / 5);
  return (
    <div className="composure">
      <p className="eyebrow" style={{ margin: "0 0 10px" }}>{label}</p>
      <span className="num" style={{ color }}>{value}</span>
      <div className="bar">
        {Array.from({ length: 20 }, (_, i) => <i key={i} style={{ background: i < lit ? color : undefined }} />)}
      </div>
    </div>
  );
}
