import { auth } from "./auth";

export type Clip = { url: string; duration: number; peaks: number[] };
export type GnaniUsage = { calls: number; audio_seconds: number; languages: string[]; median_ms: number | null; p90_ms: number | null };
export type Stats = {
  workers: number; records: number; verified: number; employers_confirmed: number; verified_income_monthly: number;
  levels: Record<string, number>; flagged_workers: number; calls: number; languages: number;
  gnani: { timbre: GnaniUsage; prisma: GnaniUsage };
};
export type StoryTurn = { who: "worker" | "saakshi" | "employer"; voice: string; text: string; audio: Clip; timbre_ms: number;
  heard?: string; prisma_ms?: number; parsed_amount?: number; parsed_from?: string };
export type Story = { lang: string; turns: StoryTurn[] };
export type Hello = { lang: string; text: string; audio: Clip; heard: string; timbre_ms: number; prisma_ms: number };

export type Worker = {
  id: string; name: string; phone: string; language: "hi-IN" | "en-IN"; role: string; city: string; state: string;
  voice: string | null; created_at: string; stats?: Passport["stats"];
};

export type Reason = { text: string; impact: number; kind: "base" | "fraud" | "outlier" | "info" | "evidence" };

export type Link = {
  token: string; worker_id: string; employer_id: string; entry_ids: string[]; status: string; opened_at: string | null;
  done_at: string | null; outcome: string | null; url: string; message: string; whatsapp: string; employer_name: string;
  created_at: string;
};

export type LinkView = {
  token: string; status: string; outcome: string | null; language: string;
  worker: { name: string; role: string; upi_id: string | null; language: string };
  employer: { name: string; opted_out: boolean };
  entries: { id: string; period: { start: string; end: string; label: string }; amount: number; days: number | null; status: string;
    employer_says: { amount?: number; days?: number } | null; payment: { utr: string; amount: number } | null;
    payment_status: string; level: number }[];
};

export type Entry = {
  id: string; worker_id: string; employer_id: string; seq: number; role: string | null; pay_type: string;
  period_start: string; period_end: string; period_label: string | null; days: number | null; rate: number | null;
  amount: number; paid: number | null; paid_mode: string | null; status: string; claimed: Record<string, unknown>;
  employer_says: { amount?: number; days?: number; deny?: boolean } | null; attested_by: string | null;
  do_not_contact: number; source_audio: string | null; transcript: string | null; confidence: number | null;
  reasons: Reason[]; hash: string; prev_hash: string; created_at: string;
  level: number | null; attested_via: string | null; payment_status: string | null; payment_ref: string | null;
  employer_name: string; employer_phone: string; employer_kind: string;
};

export type Passport = {
  worker: { id: string; name: string; role: string; city: string; state: string; phone_last4: string; language: string; since: string };
  months: { month: string; label: string; verified: number; claimed: number; l2: number; l3: number }[];
  stats: {
    months_active: number; months_verified: number; avg_monthly_verified: number; income_band: string;
    verified_share: number; total_verified_12m: number; total_claimed_12m: number; employers: number;
    longest_tenure_months: number; strength: number; fraud_flags: number;
    levels: Record<string, number>; months_l2: number; avg_monthly_l2: number; months_l3: number; avg_monthly_l3: number;
  };
  employers: { name: string; kind: string; since: string; until: string; records: number; verified: number }[];
  bocw: { days: number; required: number; eligible: boolean; estimated: boolean; rows: { employer: string; period: string; days: number }[] };
  chain: { length: number; head: string; intact: boolean };
  generated_at: string; signature: string;
};

export type CallTurn = {
  who: "saakshi" | "employer"; text: string; audio: Clip | null; worker_clip?: string | null;
  follow_text?: string | null; follow_audio?: Clip | null; stage?: string; intent?: string; done?: boolean;
};

export type Call = {
  id: string; employer_id: string; entry_ids: string[]; status: string; outcome: string | null; mode: string;
  attempts: number; next_attempt_at: string | null; transcript: CallTurn[]; language: string | null; created_at: string;
  employer?: { id: string; name: string; persona: string | null; kind: string }; workers?: string[];
};

export type Draft = {
  employer_name: string; employer_phone: string | null; employer_id: string | null; role: string | null; pay_type: string;
  amount: number | null; amount_source: string; days: number | null; rate: number | null;
  period: { start: string; end: string; label: string } | null; paid: string; do_not_contact: boolean;
};

export type JournalReply = {
  heard: string; say: string; audio: Clip | null; worker_audio: Clip | null; intent: string; state: string; asked: string;
  drafts: Draft[]; saved: Entry[];
};

export type WorkerDetail = {
  worker: Worker & { upi_id: string | null }; entries: Entry[]; passport: Passport; calls: Call[]; links: Link[];
  evidence: { id: string; raw: string; parsed: string; entry_id: string | null; created_at: string }[];
  shares: { token: string; scope: string; audience: string | null; expires_at: string; revoked: number; views: number; created_at: string }[];
  events: { id: number; at: string; kind: string; text: string }[];
  journal: { state: string; drafts: Draft[] } | null;
};

export type Employer = { id: string; phone: string; name: string; kind: string; language: string | null; opted_out: number; persona: string | null; voice: string | null; pending: number };

export type GraphData = {
  nodes: { id: string; label: string; type: "worker" | "employer"; role?: string; kind?: string; ring: number | null; also_employer?: boolean }[];
  edges: { source: string; target: string; count: number; status: string; confidence: number }[];
  rings: string[][];
};

export type RedTeam = {
  status: string; progress?: number; total?: number; entries?: number; fraud_entries?: number; caught?: number;
  missed?: number; false_alarms?: number; precision?: number | null; recall?: number | null; honest_unresolved?: number;
};

let metaCache: Promise<Awaited<ReturnType<typeof api.meta>>> | null = null;
export const meta = () => (metaCache ??= api.meta());

export const OFFLINE = "Can't reach the Saakshi server. Start it with ./run.sh in the saakshi folder.";

function authHeaders(url: string): Record<string, string> {
  const h: Record<string, string> = {};
  const m = url.match(/^\/api\/workers\/([^/?]+)/);
  if (m && auth.token(m[1])) h["X-Worker-Token"] = auth.token(m[1]);
  if (auth.admin()) h["X-Admin-Key"] = auth.admin()!;
  return h;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function req<T>(url: string, init?: RequestInit, retried = false): Promise<T> {
  let res: Response;
  const headers = { ...(init?.headers as Record<string, string> | undefined), ...authHeaders(url) };
  // nothing a person waits on may spin forever: speech + model steps finish within ~70s or fail clearly
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 75_000);
  try { res = await fetch(url, { ...init, headers, signal: ctl.signal }); }
  catch (e) {
    clearTimeout(timer);
    if ((e as Error).name === "AbortError") throw new Error("This is taking too long. Please try again.");
    throw new Error(OFFLINE);
  }
  clearTimeout(timer);
  if (!res.ok) {
    // a worker's screen with no (or an expired) login: demo workers can be opened by anyone, so get a pass and retry
    const wid = url.match(/^\/api\/workers\/([^/?]+)/)?.[1];
    if (res.status === 401 && wid && !retried) {
      try {
        const t = await fetch(`/api/demo/token/${wid}`, { method: "POST", headers: authHeaders("/") });
        if (t.ok) { auth.setToken(wid, (await t.json()).token); return req<T>(url, init, true); }
      } catch { /* fall through to the original error */ }
    }
    let msg = `${res.status}`;
    try { const b = await res.json(); msg = b.detail || JSON.stringify(b); } catch { /* not json */ }
    throw new ApiError(msg, res.status);
  }
  return res.json();
}
const post = <T,>(url: string, body?: unknown) =>
  req<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
const form = <T,>(url: string, f: FormData) => req<T>(url, { method: "POST", body: f });

export const api = {
  stats: () => req<Stats>("/api/stats"),
  demoVoice: (text: string, voice: string, language: string) => post<Clip>("/api/demo/voice", { text, voice, language }),
  story: (lang: string) => req<Story>(`/api/showcase/story?lang=${lang}`),
  hello: (lang: string) => req<Hello>(`/api/showcase/hello/${lang}`),
  meta: () => req<{ ready: { gnani: boolean; llm: boolean; telephony: boolean }; hotline: string | null; lan_ip: string | null; models: Record<string, string>; counts: Record<string, number> }>("/api/meta"),
  seed: () => post<{ workers: number; employers: number; entries: number }>("/api/demo/seed"),
  workers: () => req<Worker[]>("/api/workers"),
  newWorker: (b: { name: string; phone: string; language: string; role: string; city: string; state: string }) => post<Worker>("/api/workers", b),
  worker: (id: string) => req<WorkerDetail>(`/api/workers/${id}`),
  welcome: (id: string) => post<{ say: string; audio: Clip | null }>(`/api/workers/${id}/welcome`),
  journal: (id: string, f: FormData) => form<JournalReply>(`/api/workers/${id}/journal`, f),
  evidence: (id: string, text: string) => post<{ matched_entry: string | null }>(`/api/workers/${id}/evidence`, { text }),
  share: (id: string, b: { scope: string; audience: string; days: number }) => post<WorkerDetail["shares"][number]>(`/api/workers/${id}/shares`, b),
  revoke: (wid: string, token: string) => req<{ ok: boolean }>(`/api/workers/${wid}/shares/${token}`, { method: "DELETE" }),
  streamTicket: (workerId?: string) => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (workerId && auth.token(workerId)) h["X-Worker-Token"] = auth.token(workerId);
    if (auth.admin()) h["X-Admin-Key"] = auth.admin()!;
    return req<{ ticket: string }>("/api/stream/ticket", { method: "POST", headers: h, body: JSON.stringify({ worker_id: workerId ?? null }) });
  },
  publicPassport: (token: string) => req<Record<string, any>>(`/api/p/${token}`),
  employers: () => req<Employer[]>("/api/employers"),
  calls: () => req<Call[]>("/api/calls"),
  call: (id: string) => req<Call>(`/api/calls/${id}`),
  ring: (id: string, mode: "auto" | "human" | "phone") => post<{ ok: boolean }>(`/api/calls/${id}/ring?mode=${mode}`),
  answer: (id: string) => post<CallTurn>(`/api/calls/${id}/answer`),
  decline: (id: string) => post<{ ok: boolean }>(`/api/calls/${id}/decline`),
  reply: (id: string, f: FormData) => form<CallTurn>(`/api/calls/${id}/reply`, f),
  graph: () => req<GraphData>("/api/trust/graph"),
  redteam: () => req<RedTeam>("/api/redteam"),
  runRedteam: () => post<{ ok: boolean }>("/api/redteam/run"),
  events: () => req<{ id: number; at: string; kind: string; text: string }[]>("/api/events"),
  join: (b: { name: string; phone: string; pin: string; language: string; role: string; city: string; state: string; upi_id: string }) =>
    post<{ worker: Worker; token: string }>("/api/auth/join", b),
  login: (phone: string, pin: string) => post<{ worker: Worker; token: string }>("/api/auth/login", { phone, pin }),
  profile: (id: string, b: { upi_id?: string; language?: string }) => post<Worker>(`/api/workers/${id}/profile`, b),
  demoToken: (id: string) => post<{ token: string }>(`/api/demo/token/${id}`),
  link: (t: string) => req<LinkView>(`/api/c/${t}`),
  linkIntro: (t: string, lang?: string) => post<Clip>(`/api/c/${t}/intro${lang ? `?lang=${lang}` : ""}`),
  withdraw: (wid: string, xid: string) => post<{ ok: boolean }>(`/api/workers/${wid}/entries/${xid}/withdraw`),
  deleteAccount: (wid: string, pin: string) => post<{ ok: boolean }>(`/api/workers/${wid}/delete`, { pin }),
  resetPin: (wid: string, pin: string) => post<{ ok: boolean }>(`/api/admin/workers/${wid}/pin`, { pin }),
  linkVoice: (t: string, f: FormData) => form<{ heard: string; accepted: boolean; reason?: string; view?: LinkView }>(`/api/c/${t}/voice`, f),
  linkTap: (t: string) => post<LinkView>(`/api/c/${t}/tap`),
  linkCorrect: (t: string, fixes: Record<string, { amount: number; days?: number | null }>) => post<LinkView>(`/api/c/${t}/correct`, { fixes }),
  linkDeny: (t: string) => post<LinkView>(`/api/c/${t}/deny`),
  linkPaid: (t: string, b: { entry_id: string; utr: string; amount: number }) => post<LinkView>(`/api/c/${t}/paid`, b),
};
