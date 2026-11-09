import { useMemo, useState } from "react";
import type { GraphData } from "../lib/api";
import { ROLE_LABEL } from "../lib/util";

type P = { x: number; y: number; vx: number; vy: number };

/** Who vouches for whom. Workers are circles, households squares, contractors
    diamonds. Edge colour = record status (labelled in the legend); suspected
    rings get a red outline with a label, so nothing relies on colour alone. */
export function TrustGraph({ data, height = 520, onSelect }: { data: GraphData; height?: number; onSelect?: (id: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const W = 900, H = height;

  // Lay out each connected group on its own, then pack the groups side by side,
  // so a suspected ring never visually swallows unrelated (honest) people.
  const pos = useMemo(() => {
    const ids = data.nodes.map((n) => n.id);
    const edges = data.edges.filter((e) => ids.includes(e.source) && ids.includes(e.target));
    const adj: Record<string, string[]> = Object.fromEntries(ids.map((id) => [id, []]));
    edges.forEach((e) => { adj[e.source].push(e.target); adj[e.target].push(e.source); });
    const seen = new Set<string>();
    const groups: string[][] = [];
    for (const id of ids) {
      if (seen.has(id)) continue;
      const g: string[] = [], st = [id];
      while (st.length) { const n = st.pop()!; if (seen.has(n)) continue; seen.add(n); g.push(n); st.push(...adj[n]); }
      groups.push(g);
    }
    groups.sort((a, b) => b.length - a.length);

    const local: Record<string, P> = {};
    const boxes = groups.map((g) => {
      g.forEach((id, i) => {
        const a = (i / g.length) * Math.PI * 2;
        local[id] = { x: Math.cos(a) * 30 * Math.sqrt(g.length), y: Math.sin(a) * 30 * Math.sqrt(g.length), vx: 0, vy: 0 };
      });
      const ge = edges.filter((e) => g.includes(e.source));
      for (let it = 0; it < 300; it++) {
        const alpha = 1 - it / 300;
        for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) {
          const p1 = local[g[i]], p2 = local[g[j]];
          const dx = p1.x - p2.x, dy = p1.y - p2.y;
          const d = Math.max(8, Math.hypot(dx, dy));
          const f = (3200 / (d * d)) * alpha;
          p1.vx += (dx / d) * f; p1.vy += (dy / d) * f; p2.vx -= (dx / d) * f; p2.vy -= (dy / d) * f;
        }
        for (const e of ge) {
          const p1 = local[e.source], p2 = local[e.target];
          const dx = p2.x - p1.x, dy = p2.y - p1.y, d = Math.max(1, Math.hypot(dx, dy));
          const f = ((d - 78) / d) * 0.06 * alpha;
          p1.vx += dx * f; p1.vy += dy * f; p2.vx -= dx * f; p2.vy -= dy * f;
        }
        for (const id of g) { const n = local[id]; n.vx -= n.x * 0.01 * alpha; n.vy -= n.y * 0.01 * alpha; n.x += n.vx; n.y += n.vy; n.vx *= 0.55; n.vy *= 0.55; }
      }
      const xs = g.map((id) => local[id].x), ys = g.map((id) => local[id].y);
      return { g, minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
    });

    // pack groups into rows
    const pad = 70, out: Record<string, P> = {};
    let x = 50, y = 60, rowH = 0;
    const placed: { b: typeof boxes[number]; ox: number; oy: number }[] = [];
    for (const b of boxes) {
      const w = b.maxX - b.minX, h = b.maxY - b.minY;
      if (x + w > W - 50 && x > 50) { x = 50; y += rowH + pad; rowH = 0; }
      placed.push({ b, ox: x - b.minX, oy: y - b.minY });
      x += w + pad; rowH = Math.max(rowH, h);
    }
    const totalH = y + rowH, totalW = Math.max(...placed.map((p) => p.ox + p.b.maxX));
    const sx = Math.min(1.5, (W - 100) / Math.max(1, totalW - 50)), sy = Math.min(1.5, (H - 110) / Math.max(1, totalH - 60));
    const sc = Math.min(sx, sy);
    const offX = (W - (totalW - 50) * sc) / 2 - 50 * sc, offY = (H - (totalH - 60) * sc) / 2 - 60 * sc + 10;
    for (const p of placed) for (const id of p.b.g) {
      out[id] = { x: offX + (local[id].x + p.ox) * sc, y: offY + (local[id].y + p.oy) * sc, vx: 0, vy: 0 };
    }
    return out;
  }, [data, H]);

  const hovered = hover ? data.nodes.find((n) => n.id === hover) : null;
  const linked = new Set(hover ? data.edges.filter((e) => e.source === hover || e.target === hover).flatMap((e) => [e.source, e.target]) : []);
  const color = (s: string) => (s === "verified" || s === "corrected" ? "#2e8b57" : s === "disputed" ? "#c8402f" : "#d9a01e");

  return (
    <div className="graph">
      <div className="legend" style={{ marginBottom: 10 }}>
        <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#fbf8f2" stroke="#1d1b17" strokeWidth="1.5" /></svg>Worker</span>
        <span><svg width="12" height="12"><rect x="1.5" y="1.5" width="9" height="9" fill="#1d1b17" /></svg>Household</span>
        <span><svg width="12" height="12"><path d="M6 1 L11 6 L6 11 L1 6Z" fill="#1d1b17" /></svg>Contractor</span>
        <span><i className="ln" style={{ background: "#2e8b57" }} />Verified</span>
        <span><i className="ln dash" style={{ borderColor: "#d9a01e" }} />Awaiting</span>
        <span><i className="ln" style={{ background: "#c8402f" }} />Not confirmed</span>
        <span><i className="ring-key" />Suspected ring</span>
      </div>
      <div style={{ position: "relative" }}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Trust graph of workers and employers">
          {data.rings.map((r, i) => {
            const pts = r.map((id) => pos[id]).filter(Boolean);
            if (!pts.length) return null;
            const x0 = Math.min(...pts.map((q) => q.x)) - 34, x1 = Math.max(...pts.map((q) => q.x)) + 34;
            const y0 = Math.min(...pts.map((q) => q.y)) - 30, y1 = Math.max(...pts.map((q) => q.y)) + 40;
            return (
              <g key={i}>
                <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx={22} fill="rgba(200,64,47,0.06)" stroke="#c8402f" strokeWidth="1.5" strokeDasharray="5 4" />
                <text x={x0 + 12} y={y0 - 8} className="ring-label">Suspected ring {i + 1}</text>
              </g>
            );
          })}
          {data.edges.map((e, i) => {
            const a = pos[e.source], b = pos[e.target];
            if (!a || !b) return null;
            const dim = hover && !(e.source === hover || e.target === hover);
            const pending = !["verified", "corrected", "disputed"].includes(e.status);
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={color(e.status)} strokeWidth={1 + Math.min(3, e.count / 3)}
              strokeDasharray={pending ? "4 4" : undefined} opacity={dim ? 0.12 : 0.75} strokeLinecap="round" />;
          })}
          {data.nodes.map((n) => {
            const p = pos[n.id];
            if (!p) return null;
            const dim = hover && !linked.has(n.id) && hover !== n.id;
            const ring = n.ring != null;
            const stroke = ring ? "#c8402f" : "#1d1b17";
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.25 : 1} style={{ cursor: "pointer" }}
                onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} onClick={() => onSelect?.(n.id)}>
                <circle r="18" fill="transparent" />
                {n.type === "worker" ? <circle r="8" fill="#fbf8f2" stroke={stroke} strokeWidth="2" />
                  : n.kind === "contractor" ? <path d="M0 -10 L10 0 L0 10 L-10 0Z" fill={stroke} />
                  : <rect x="-7" y="-7" width="14" height="14" rx="2" fill={stroke} />}
                <text y="24" textAnchor="middle" className="node-label">{n.label.length > 16 ? n.label.slice(0, 15) + "…" : n.label}</text>
              </g>
            );
          })}
        </svg>
        {hovered && pos[hovered.id] && (
          <div className="tip" style={{ left: `${(pos[hovered.id].x / W) * 100}%`, top: `${(pos[hovered.id].y / H) * 100}%` }}>
            <b>{hovered.label}</b>
            <span>{hovered.type === "worker" ? ROLE_LABEL[hovered.role ?? "other"] : hovered.kind === "contractor" ? "Contractor" : "Household employer"}
              {hovered.also_employer ? " · also listed as an employer" : ""}</span>
            <span>{data.edges.filter((e) => e.source === hovered.id || e.target === hovered.id).length} connection(s)</span>
            {hovered.ring != null && <span style={{ color: "var(--bad)" }}>In suspected ring {hovered.ring + 1}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
