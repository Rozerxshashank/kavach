import type { ReactNode } from "react";

/* Console building blocks: one look for every screen. */

const P: Record<string, string> = {
  overview: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z",
  target: "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 16a6 6 0 1 1 6-6 6 6 0 0 1-6 6zm0-9a3 3 0 1 0 3 3 3 3 0 0 0-3-3z",
  play: "M8 5v14l11-7z",
  list: "M4 6h16M4 12h16M4 18h10",
  alert: "M12 2 1 21h22L12 2zm0 6v6m0 3v.5",
  shield: "M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5l-8-3z",
  policy: "M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8",
  key: "M15 7a4 4 0 1 1-3.9 5H9v2H7v2H4v-3l6.1-6.1A4 4 0 0 1 15 7z",
  agent: "M12 2a4 4 0 0 1 4 4v1h1a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3v-7a3 3 0 0 1 3-3h1V6a4 4 0 0 1 4-4zM9 13h.01M15 13h.01",
  mic: "M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zm-7 9a7 7 0 0 0 14 0M12 19v3",
  info: "M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20zm0-14v.5M12 11v6",
  menu: "M4 6h16M4 12h16M4 18h16",
  plus: "M12 5v14M5 12h14",
  check: "M5 13l4 4L19 7",
  x: "M6 6l12 12M18 6 6 18",
};

export function Icon({ name, size = 16 }: { name: keyof typeof P | string; size?: number }) {
  const filled = ["overview", "play"].includes(name);
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={P[name] ?? P.info} />
    </svg>
  );
}

export function PageHeader({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ph">
      <div className="ph-t"><h1 className="h1">{title}</h1>{sub && <p>{sub}</p>}</div>
      {actions && <div className="ph-a">{actions}</div>}
    </header>
  );
}

export function Panel({ title, sub, actions, children, flush, className = "" }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-h">{title && <h2>{title}</h2>}{sub && <span className="sub">{sub}</span>}{actions && <div className="act">{actions}</div>}</div>
      )}
      <div className={`panel-b ${flush ? "flush" : ""}`}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone, dot }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: string; dot?: string }) {
  return (
    <div className="panel stat">
      <span className="stat-l">{dot && <i className="dot" style={{ background: dot }} />}{label}</span>
      <span className="stat-v" style={tone ? { color: tone } : undefined}>{value}</span>
      {sub && <span className="stat-s">{sub}</span>}
    </div>
  );
}

const SEV_ORDER = ["critical", "high", "medium", "low"] as const;
export const SEV_COLOR: Record<string, string> = { critical: "var(--sev-critical)", high: "var(--sev-high)", medium: "var(--sev-medium)", low: "var(--sev-low)" };

export function Sev({ level }: { level: string }) {
  return <span className={`sev ${level}`}>{level[0].toUpperCase() + level.slice(1)}</span>;
}

const STATE_WORD: Record<string, string> = {
  compromised: "Compromised", at_risk: "At risk", resilient: "Resilient", running: "Running", incomplete: "Incomplete", error: "Failed",
};
export function State({ verdict, status }: { verdict?: string | null; status?: string }) {
  const k = status === "running" ? "running" : status === "error" && verdict !== "compromised" ? "incomplete" : verdict ?? "incomplete";
  return <span className={`state ${k}`}>{STATE_WORD[k] ?? k}</span>;
}

export function Score({ value }: { value: number | null | undefined }) {
  const c = value == null ? "none" : value >= 85 ? "good" : value >= 50 ? "warn" : "bad";
  return <span className={`score ${c}`}>{value ?? "—"}</span>;
}

/** A stacked bar of findings by severity. */
export function SevBar({ counts }: { counts: Record<string, number> }) {
  const total = SEV_ORDER.reduce((n, k) => n + (counts[k] ?? 0), 0);
  return (
    <div className="grid" style={{ gap: 10 }}>
      <div className="bar" role="img" aria-label="Findings by severity">
        {total ? SEV_ORDER.map((k) => counts[k] ? <i key={k} style={{ width: `${(counts[k] / total) * 100}%`, background: SEV_COLOR[k] }} /> : null)
          : <i style={{ width: "100%", background: "var(--ink-4)" }} />}
      </div>
      <div className="legend">
        {SEV_ORDER.map((k) => <span key={k}><i style={{ background: SEV_COLOR[k] }} />{k[0].toUpperCase() + k.slice(1)} <b className="mono">{counts[k] ?? 0}</b></span>)}
      </div>
    </div>
  );
}

export function scoreTone(v: number | null | undefined) {
  return v == null ? "var(--fg-3)" : v >= 85 ? "var(--held)" : v >= 50 ? "var(--amber)" : "var(--breach)";
}
