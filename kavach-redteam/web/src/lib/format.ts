export const ENV_LABEL: Record<string, string> = {
  none: "Clean line", airport: "Airport", traffic: "Roadside", crowd: "Market crowd", siren: "Sirens",
};

export const VERDICT_WORD: Record<string, string> = {
  compromised: "Compromised", at_risk: "At risk", resilient: "Resilient", incomplete: "Incomplete",
};

export const STATUS_WORD: Record<string, string> = {
  held: "Held", wavering: "Wavering", breached: "Breached", contained: "Contained",
};

export const LANG: Record<string, string> = { "en-IN": "English", "hi-IN": "Hindi" };

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function pad(n: number) { return String(n).padStart(2, "0"); }

export function isDeva(s: string) { return /[ऀ-ॿ]/.test(s); }

export function toolCall(name: string, args: Record<string, unknown>) {
  const a = Object.entries(args || {}).map(([k, v]) => `${k}: ${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`).join(", ");
  return `${name}(${a})`;
}

export function scoreColor(score: number | null | undefined) {
  if (score == null) return "var(--fg-3)";
  if (score >= 85) return "var(--held)";
  if (score >= 50) return "var(--amber)";
  return "var(--breach)";
}
