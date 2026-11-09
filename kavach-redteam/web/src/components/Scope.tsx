import { useEffect, useRef } from "react";
import { player } from "../lib/player";

const COLORS = { caller: [184, 85, 31], bot: [35, 112, 126], mic: [184, 85, 31], idle: [179, 170, 154] } as const;

/** Live oscilloscope bound to whatever is speaking right now (or a mic). */
export function Scope({ height = 180, mic = null, className = "" }: {
  height?: number; mic?: AnalyserNode | null; className?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const micRef = useRef(mic);
  micRef.current = mic;

  useEffect(() => {
    const canvas = ref.current!;
    const g = canvas.getContext("2d")!;
    let raf = 0;
    let w = 0, h = 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const N = 256;
    const shown = new Float32Array(N);
    const buf = new Float32Array(2048);
    let color: number[] = [...COLORS.idle];
    let t = 0;

    const ro = new ResizeObserver(() => {
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
    });
    ro.observe(canvas);

    const draw = () => {
      t += 0.016;
      const an = micRef.current ?? (player.speaker ? player.analyser : null);
      const who = micRef.current ? "mic" : player.speaker ?? "idle";
      const target = COLORS[who as keyof typeof COLORS] ?? COLORS.idle;
      color = color.map((c, i) => c + (target[i] - c) * 0.08);

      if (an) {
        an.getFloatTimeDomainData(buf);
        const step = Math.floor(buf.length / N);
        for (let i = 0; i < N; i++) {
          let v = 0;
          for (let k = 0; k < step; k++) v += buf[i * step + k];
          shown[i] += (v / step * 3.2 - shown[i]) * 0.5;
        }
      } else {
        for (let i = 0; i < N; i++) {
          const x = i / N;
          const idle = Math.sin(x * 9 + t * 1.3) * 0.018 + Math.sin(x * 23 - t * 2.1) * 0.01;
          shown[i] += (idle - shown[i]) * 0.08;
        }
      }

      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const mid = h / 2;
      const [r, gg, b] = color.map(Math.round);

      // centre hairline
      g.fillStyle = "rgba(29,27,23,0.08)";
      g.fillRect(0, mid, w, 1);

      const pts: [number, number][] = [];
      for (let i = 0; i < N; i++) {
        const x = (i / (N - 1)) * w;
        const edge = Math.sin((i / (N - 1)) * Math.PI); // taper at the ends
        pts.push([x, mid + Math.max(-1, Math.min(1, shown[i])) * mid * 0.92 * edge]);
      }

      // soft fill
      const grad = g.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, `rgba(${r},${gg},${b},0)`);
      grad.addColorStop(0.5, `rgba(${r},${gg},${b},0.16)`);
      grad.addColorStop(1, `rgba(${r},${gg},${b},0)`);
      g.beginPath();
      g.moveTo(0, mid);
      pts.forEach(([x, y]) => g.lineTo(x, y));
      g.lineTo(w, mid);
      g.closePath();
      g.fillStyle = grad;
      g.fill();

      // line with glow
      g.beginPath();
      pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
      g.strokeStyle = `rgb(${r},${gg},${b})`;
      g.lineWidth = 1.6;
      g.shadowColor = `rgba(${r},${gg},${b},0.35)`;
      g.shadowBlur = an ? 18 : 4;
      g.stroke();
      g.shadowBlur = 0;

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);

  return <canvas ref={ref} className={className} style={{ width: "100%", height, display: "block" }} />;
}
