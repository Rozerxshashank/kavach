import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import QRCode from "qrcode";
import type { Clip, Reason } from "../lib/api";
import { player, type Who } from "../lib/player";
import { STATUS_ICON, STATUS_LABEL } from "../lib/util";

export function Chip({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`chip ${status}`}>
      <i aria-hidden>{STATUS_ICON[status] ?? "•"}</i>
      {label ?? STATUS_LABEL[status] ?? status}
    </span>
  );
}

/** Static waveform from peaks; click to play. */
export function Wave({ clip, who, label }: { clip: Clip; who: Exclude<Who, null>; label?: string }) {
  const [playing, setPlaying] = useState(false);
  const [p, setP] = useState(0);
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => { setP(player.progress); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);
  const color = who === "saakshi" ? "var(--khata)" : who === "employer" ? "var(--call)" : "var(--ink)";
  const toggle = async () => {
    if (playing) { player.stop(); return; }
    setPlaying(true); setP(0);
    await player.play(clip.url, who);
    setPlaying(false); setP(0);
  };
  return (
    <button className="wave" onClick={toggle} style={{ ["--c" as string]: color }} aria-label={label ?? "Play"}>
      <span className="wave-btn">{playing ? "■" : "▶"}</span>
      <span className="wave-bars">
        {clip.peaks.map((v, i) => <i key={i} style={{ height: `${14 + v * 86}%`, opacity: i / clip.peaks.length <= p ? 1 : 0.35 }} />)}
      </span>
      <span className="wave-dur mono">{clip.duration.toFixed(1)}s</span>
    </button>
  );
}

/** Live waveform of whatever is playing (or the mic). */
export function Scope({ mic, height = 64, tone = "ink" }: { mic?: AnalyserNode | null; height?: number; tone?: "ink" | "khata" | "call" }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const micRef = useRef(mic);
  micRef.current = mic;
  useSyncExternalStore(player.subscribe, () => player.who);
  useEffect(() => {
    const c = ref.current!;
    const g = c.getContext("2d")!;
    const dpr = Math.min(2, devicePixelRatio || 1);
    const buf = new Float32Array(1024);
    const N = 120;
    const shown = new Float32Array(N);
    let raf = 0, t = 0;
    const colors = { ink: "29,27,23", khata: "158,42,43", call: "58,108,203" };
    const draw = () => {
      t += 0.02;
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      const an = micRef.current ?? (player.who ? player.analyser : null);
      if (an) {
        an.getFloatTimeDomainData(buf);
        const step = Math.floor(buf.length / N);
        for (let i = 0; i < N; i++) {
          let m = 0;
          for (let k = 0; k < step; k++) m = Math.max(m, Math.abs(buf[i * step + k]));
          shown[i] += (Math.min(1, m * 2.4) - shown[i]) * 0.35;
        }
      } else {
        for (let i = 0; i < N; i++) shown[i] += ((Math.sin(i * 0.3 + t * 2) + 1) * 0.02 - shown[i]) * 0.1;
      }
      const who = micRef.current ? "khata" : player.who === "employer" ? "call" : player.who === "saakshi" ? "khata" : tone;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const bw = w / N;
      g.fillStyle = `rgba(${colors[who as keyof typeof colors] ?? colors.ink},0.85)`;
      for (let i = 0; i < N; i++) {
        const bh = Math.max(2, shown[i] * h * 0.95);
        const x = i * bw + bw * 0.25;
        const r = Math.min(bw * 0.25, bh / 2);
        g.beginPath();
        g.roundRect(x, (h - bh) / 2, bw * 0.5, bh, r);
        g.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [tone]);
  return <canvas ref={ref} style={{ width: "100%", height, display: "block" }} aria-hidden />;
}

export function PhoneFrame({ children, label, tone = "paper" }: { children: React.ReactNode; label?: string; tone?: "paper" | "dark" }) {
  return (
    <div className={`phone ${tone}`}>
      {label && <p className="phone-label eyebrow">{label}</p>}
      <div className="phone-body">
        <div className="phone-notch" />
        {children}
      </div>
    </div>
  );
}

export function Reasons({ reasons }: { reasons: Reason[] }) {
  return (
    <ul className="reasons">
      {reasons.map((r, i) => (
        <li key={i} className={r.kind}>
          <span className="mono">{r.kind === "base" ? "" : r.impact > 0 ? `+${r.impact.toFixed(2)}` : r.impact < 0 ? r.impact.toFixed(2) : "·"}</span>
          <span>{r.text}</span>
        </li>
      ))}
    </ul>
  );
}

export function Confidence({ value }: { value: number | null }) {
  const v = value ?? 0;
  const status = v >= 0.6 ? "ok" : v >= 0.4 ? "wait" : "bad";
  return (
    <span className={`conf ${status}`} title={`Confidence ${Math.round(v * 100)}%`}>
      <span className="conf-bar"><i style={{ width: `${v * 100}%` }} /></span>
      <span className="mono">{Math.round(v * 100)}</span>
    </span>
  );
}

export function QR({ text, size = 132 }: { text: string; size?: number }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    QRCode.toDataURL(text, { margin: 1, width: size * 2, color: { dark: "#1d1b17", light: "#fbf8f2" } }).then(setSrc).catch(() => setSrc(""));
  }, [text, size]);
  return src ? <img src={src} width={size} height={size} alt="QR code to verify this passport" style={{ borderRadius: 8 }} /> : null;
}
