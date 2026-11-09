import type { Finding, Run } from "../api";

export type FindingRow = Finding & {
  run: Run;
  status: "open" | "fixed" | "shielded";
  fixedBy?: Run;
};

/** Every finding from attack simulations, with its status taken from the evidence:
    fixed     a replay of the same attack against a candidate fix (or a newer version) held;
    shielded  a replay of the same attack with Kavach Shield on held;
    open      nothing has held against it yet. */
export function findingRows(runs: Run[]): FindingRow[] {
  const children = new Map<string, Run[]>();
  for (const r of runs) if (r.parent) children.set(r.parent, [...(children.get(r.parent) ?? []), r]);
  const out: FindingRow[] = [];
  for (const run of runs) {
    if (run.mode !== "campaign" || !run.findings?.length) continue;
    const held = (children.get(run.id) ?? []).filter((c) => c.verdict === "resilient")
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
    const fix = held.find((c) => !(c.shield && !run.shield && c.hardening?.kind !== "candidate"));
    const shield = held.find((c) => c.shield && !run.shield);
    for (const f of run.findings) {
      if (f.kind === "contained") continue;
      out.push({ ...f, run, status: fix ? "fixed" : shield ? "shielded" : "open", fixedBy: fix ?? shield });
    }
  }
  const rank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  return out.sort((a, b) => (a.status === "open" ? 0 : 1) - (b.status === "open" ? 0 : 1)
    || rank[a.severity] - rank[b.severity] || b.run.created_at.localeCompare(a.run.created_at));
}

export function sevCounts(rows: FindingRow[]): Record<string, number> {
  const c: Record<string, number> = {};
  for (const r of rows) c[r.severity] = (c[r.severity] ?? 0) + 1;
  return c;
}

export const STATUS_WORD = { open: "Open", fixed: "Fix proven", shielded: "Blocked by Shield" } as const;

export function within(iso: string, days: number) {
  return Date.now() - new Date(iso).getTime() < days * 86400_000;
}
