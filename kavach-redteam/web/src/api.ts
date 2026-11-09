export type Clip = { url: string; duration: number; peaks: number[] };

export type Persona = {
  name: string; voice: string; language: string; environment: string; speed: number;
  tagline: string; brief: string;
};
export type Objective = { name: string; goal: string; severity: string; breaks_if: string; persona: string };

export type TargetPublic = {
  id: string; name: string; agent: string; kind: string; description: string; languages: string[];
  personas: Record<string, Persona>; objectives: Record<string, Objective>; gates: Record<string, string>;
  tactics: Record<string, string>;
};

export type Meta = {
  targets: Record<string, TargetPublic>;
  environments: Record<string, string>;
  shield_policies: Record<string, { name: string; description: string }>;
  models: { tts: string; asr: string; bot_voice: string; attacker: string; bot: string; judge: string; shield: string };
  ready: { gnani: boolean; llm: boolean };
  quota: { daily: number; used: number; left: number };
  running: string | null;
  operator: boolean;
};

export type Hardening = {
  kind: "live" | "version" | "candidate"; version: number | null; title: string; rules: string[];
  gates: Record<string, boolean>; patches?: { title: string; rules: string[] }[]; prompt?: string;
};
export type AgentVersion = Hardening & { active: boolean; created_at?: string; note?: string | null; source_run?: string | null };

export type TargetDetail = TargetPublic & {
  available: boolean; unavailable_reason: string;
  versions?: { live: Hardening; versions: AgentVersion[] };
};

export type ToolEvent = {
  name: string; args: Record<string, unknown>; result: unknown; executed: boolean;
  sensitive: boolean; verified_at_call: boolean; blocked_by_gate: boolean; blocked_by?: string | null;
};

export type Finding = {
  id: string; turn: number; kind: string; severity: string; title: string; evidence: string;
  detail: string; data?: string;
};

export type Verdict = { status: string; composure: number; note: string; findings: Finding[] };

export type ShieldSignal = { kind: string; weight: number; evidence: string; detail: string };
export type ShieldInbound = { decision: "allow" | "challenge" | "escalate"; risk: number; turn_risk: number;
  signals: ShieldSignal[]; claims: string[]; latency_ms?: number };
export type ShieldViolation = { check: string; label: string; severity: string; detail?: string };
export type ShieldOutbound = { decision: "allow" | "rewrite" | "block"; violations: ShieldViolation[]; original?: string };
export type ShieldTurn = { inbound?: ShieldInbound; outbound?: ShieldOutbound;
  actions?: { name: string; decision: string; reason: string }[] } | null;

export type Turn = {
  n: number; tactic: string | null; tactic_label: string; thinking: string; emotion: string | null;
  intensity: number | null; said: string; said_language: string; caller_audio: Clip; heard: string;
  drift: number | null; bot: string; bot_language: string; bot_audio: Clip; interrupted: boolean;
  intent?: string | null; tools: ToolEvent[]; verified_after: boolean; verdict: Verdict;
  latency: Record<string, number>; shield?: ShieldTurn;
};

export type Fix = { title: string; new_rules: string[]; gates: Record<string, boolean>; rationale: string };

export type Run = {
  id: string; created_at: string; mode: "campaign" | "replay" | "live"; status: string;
  target: string; target_name: string; agent_name: string;
  persona: string; persona_name: string; voice: string | null; objective: string; objective_name: string;
  breaks_if?: string; language: string; environment: string; intensity: string; max_turns: number;
  hardening: Hardening; shield: boolean;
  target_version: number | null; target_label: string; tool_gate: boolean; parent: string | null;
  turns: Turn[]; findings: Finding[]; score: number | null; verdict: string | null;
  objective_achieved: boolean; latency: Record<string, number>; error?: string;
  broke_at?: number | null; breaking_tactic?: string | null; turn_count?: number; tactics_used?: string[];
  summary?: string; reveal?: { facts: string[] } | null; outcome?: Record<string, unknown>;
  fix?: Fix; promoted?: number; shield_summary?: { peak_risk: number; claims: string[]; counts: Record<string, number> };
};

export type ShieldPolicy = {
  id: string; name: string; description: string; risk: { challenge: number; escalate: number };
  outbound: string[]; pii: string[]; protected: { label: string; values: string[] }[];
  actions: Record<string, { requires?: string[]; block_if?: string[]; reason?: string }>;
  replies: Record<string, Record<string, string>>;
};
export type ShieldStats = { live_sessions: number; calls_7d: number; escalated_7d: number; blocked_replies_7d: number;
  denied_actions_7d: number; signals_7d: Record<string, number> };
export type ShieldSession = { session_id: string; policy: string; risk: number; peak_risk: number; claims: string[];
  turns: number; counts: Record<string, number>; verified: boolean;
  timeline: { t: number; dir: string; decision?: string; risk?: number; signals?: ShieldSignal[]; violations?: ShieldViolation[]; name?: string }[] };
export type ShieldCall = ShieldSession & { owner: string; started_at: string; ended_at: string | null };
export type ShieldKey = { id: string; policy: string; name: string; prefix: string; created_at: string; revoked: number; last_used: string | null };

export const OFFLINE_MSG = "Can't reach the Kavach server. Start it with ./run.sh in kavach-redteam/ and try again.";

/* ---- credentials kept in this browser: the operator key, and the owner tokens of calls you started ---- */
const ADMIN = "kavach.admin";
const OWNERS = "kavach.owners";
function read<T>(k: string, d: T): T { try { return JSON.parse(localStorage.getItem(k) || "") as T; } catch { return d; } }
function write(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked */ } }
export const creds = {
  admin: () => read<string>(ADMIN, ""),
  setAdmin: (k: string) => write(ADMIN, k),
  owner: (id: string) => read<Record<string, string>>(OWNERS, {})[id],
  setOwner: (id: string, token: string) => {
    const o = read<Record<string, string>>(OWNERS, {});
    o[id] = token;
    const keys = Object.keys(o);
    if (keys.length > 200) for (const k of keys.slice(0, keys.length - 200)) delete o[k];
    write(OWNERS, o);
  },
};

/** fetch that turns a dead connection into a readable error instead of "Failed to fetch". */
function f(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (creds.admin()) headers.set("X-Admin-Key", creds.admin());
  return fetch(input, { ...init, headers }).catch(() => { throw new Error(OFFLINE_MSG); });
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status}`;
    try { const b = await res.json(); msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b); } catch { /* not json */ }
    throw new Error(msg);
  }
  return res.json();
}
const post = (url: string, body?: unknown, headers: Record<string, string> = {}) =>
  f(url, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: body !== undefined ? JSON.stringify(body) : undefined });

export type StartReq = {
  target: string; persona: string; objective: string; language?: string | null; environment: string; intensity: string;
  max_turns: number; hardening: "live" | "original" | number; shield: boolean;
};

export const api = {
  meta: () => f("/api/meta").then(j<Meta>),
  targets: () => f("/api/targets").then(j<TargetDetail[]>),
  target: (id: string) => f(`/api/targets/${id}`).then(j<TargetDetail>),
  activate: (target: string, v: number) => post(`/api/targets/${target}/versions/${v}/activate`).then(j<{ version: number }>),
  runs: (target?: string) => f(`/api/runs${target ? `?target=${target}` : ""}`).then(j<Run[]>),
  run: (id: string) => f(`/api/runs/${id}`).then(j<Run>),
  deleteRun: (id: string) => f(`/api/runs/${id}`, { method: "DELETE" }).then(j<{ ok: boolean }>),
  start: (b: StartReq) => post("/api/runs", b).then(j<{ id: string; owner: string }>)
    .then((r) => { creds.setOwner(r.id, r.owner); return r; }),
  replay: (id: string, b: { against: "candidate" | "live" | "same"; title?: string; rules?: string[]; gates?: Record<string, boolean>; shield?: boolean }) =>
    post(`/api/runs/${id}/replay`, b).then(j<{ id: string; owner: string }>).then((r) => { creds.setOwner(r.id, r.owner); return r; }),
  stop: (id: string) => post(`/api/runs/${id}/stop`, undefined, creds.owner(id) ? { "X-Run-Owner": creds.owner(id) } : {}).then(j<{ ok: boolean }>),
  fix: (id: string) => post(`/api/runs/${id}/fix`).then(j<Fix>),
  promote: (id: string, note: string) => post(`/api/runs/${id}/promote`, { note }).then(j<{ version: number }>),
  liveStart: (b: { target: string; environment: string; intensity: string; hardening: "live" | "original"; shield: boolean; language: string }) =>
    post("/api/live", b).then(j<{ id: string; owner: string; bot: string; audio: Clip; bot_name: string; target: string; target_version: number | null; tool_gate: boolean; shield: boolean }>)
      .then((r) => { creds.setOwner(r.id, r.owner); return r; }),
  liveTurn: (id: string, form: FormData) =>
    f(`/api/live/${id}/turn`, { method: "POST", body: form, headers: { "X-Run-Owner": creds.owner(id) ?? "" } })
      .then(j<{ turn: Turn; score: number; verdict: string; done: boolean }>),
  liveEnd: (id: string) => post(`/api/live/${id}/end`, undefined, { "X-Run-Owner": creds.owner(id) ?? "" }).then(j<Run>),
  // Kavach Shield
  shieldPolicies: () => f("/api/shield/policies").then(j<{ policies: ShieldPolicy[] }>),
  shieldStats: () => f("/api/shield/stats").then(j<ShieldStats>),
  shieldCalls: () => f("/api/shield/calls").then(j<ShieldCall[]>),
  shieldTry: (b: { policy: string; direction: "inbound" | "outbound" | "action"; text: string; session_id?: string | null; verified?: boolean; language?: string }) =>
    post("/api/shield/try", b).then(j<Record<string, any> & { session: ShieldSession }>),
  shieldKeys: () => f("/api/shield/keys").then(j<ShieldKey[]>),
  shieldNewKey: (policy: string, name: string) => post("/api/shield/keys", { policy, name }).then(j<{ id: string; key: string; policy: string; note: string }>),
  shieldRevoke: (id: string) => f(`/api/shield/keys/${id}`, { method: "DELETE" }).then(j<{ ok: boolean }>),
};

export type CallEvent = { seq: number; type: string; [k: string]: any };

/** The call's live events. A dropped connection resumes from the last event seen; once the call is over the
    server ends the stream and onEnd fires. */
export function streamRun(id: string, onEvent: (e: CallEvent) => void, onEnd: () => void): () => void {
  let closed = false;
  let last = -1;
  let es: EventSource | null = null;
  let retries = 0;
  const open = () => {
    es = new EventSource(`/api/runs/${id}/events${last >= 0 ? `?after=${last + 1}` : ""}`);
    es.onmessage = (m) => { retries = 0; const ev = JSON.parse(m.data); last = ev.seq; onEvent(ev); };
    es.addEventListener("end", () => { es?.close(); closed = true; onEnd(); });
    es.onerror = () => {
      es?.close();
      if (closed) return;
      if (++retries > 4) { closed = true; onEnd(); return; }
      setTimeout(open, 800 * retries);
    };
  };
  open();
  return () => { closed = true; es?.close(); };
}
