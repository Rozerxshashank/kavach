import { useEffect, useRef } from "react";

/** Decorative field of voice lines for the landing page: one ember voice
    pushing, one ice voice holding, until the ice line fractures. */
export function HeroField() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!;
    const g = c.getContext("2d")!;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let w = 0, h = 0, raf = 0, t = 0;
    const ro = new ResizeObserver(() => { w = c.clientWidth; h = c.clientHeight; c.width = w * dpr; c.height = h * dpr; });
    ro.observe(c);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const line = (y0: number, amp: number, freq: number, speed: number, color: string, alpha: number, glitch = 0) => {
      g.beginPath();
      for (let x = 0; x <= w; x += 3) {
        const u = x / w;
        const env = Math.pow(Math.sin(Math.PI * u), 1.6);
        let y = y0 + env * amp * (
          Math.sin(u * freq + t * speed) * 0.6 +
          Math.sin(u * freq * 2.7 - t * speed * 1.4) * 0.3 +
          Math.sin(u * freq * 6.1 + t * speed * 0.7) * 0.1);
        if (glitch && Math.sin(u * 40 + t * 9) > 0.96) y += (Math.random() - 0.5) * glitch;
        x === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      }
      g.strokeStyle = color;
      g.globalAlpha = alpha;
      g.lineWidth = 1.2;
      g.stroke();
      g.globalAlpha = 1;
    };

    const frame = () => {
      t += reduce ? 0 : 0.012;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const pressure = (Math.sin(t * 0.5) + 1) / 2; // 0..1
      for (let i = 0; i < 7; i++) {
        line(h * 0.5 + (i - 3) * 6, h * (0.16 + pressure * 0.2) * (1 - i * 0.08), 7 + i, 1.1 + i * 0.15,
          "#b8551f", 0.08 + (i === 3 ? 0.55 : 0.05));
      }
      for (let i = 0; i < 4; i++) {
        line(h * 0.5 + (i - 1.5) * 4, h * 0.07 * (1 + i * 0.1), 4 + i, -0.8 - i * 0.1,
          "#23707e", i === 1 ? 0.5 : 0.08, pressure > 0.82 ? 30 * (pressure - 0.82) * 5 : 0);
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);
  return <canvas ref={ref} className="hero-field" aria-hidden />;
}
