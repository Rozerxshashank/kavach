import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { VoiceLoop, type VoiceState } from "../lib/voice";
import { player } from "../lib/player";
import { t } from "../lib/i18n";

/** An always-open mic for a page. `start()` must be called from a tap (browsers require it once). */
export function useVoice(onUtterance: (wav: Blob) => void, silenceMs = 950) {
  const [state, setState] = useState<VoiceState>("off");
  const [blocked, setBlocked] = useState(false);
  const cb = useRef(onUtterance);
  cb.current = onUtterance;
  const loop = useRef<VoiceLoop | null>(null);

  const start = useCallback(async () => {
    player.unlock();
    loop.current ??= new VoiceLoop({ onUtterance: (w) => cb.current(w), onState: setState, silenceMs });
    try { await loop.current.start(); setBlocked(false); } catch { setBlocked(true); }
  }, [silenceMs]);
  const stop = useCallback(() => { loop.current?.stop(); loop.current = null; }, []);
  const toggle = useCallback(() => { if (!loop.current || loop.current.state === "off") void start(); else loop.current.toggle(); }, [start]);
  const setSilence = useCallback((ms: number) => { if (loop.current) loop.current.silenceMs = ms; }, []);
  useEffect(() => () => loop.current?.stop(), []);

  return { state, start, stop, toggle, setSilence, blocked, analyser: loop.current?.analyser ?? null };
}

/** The one control on a voice screen: shows whether Saakshi is listening, hearing, thinking or talking. */
export function VoiceOrb({ voice, busy, lang, tone = "khata", size = 76 }: {
  voice: ReturnType<typeof useVoice>; busy?: boolean; lang?: string; tone?: "khata" | "call"; size?: number;
}) {
  const who = useSyncExternalStore(player.subscribe, () => player.who);
  const ref = useRef<HTMLSpanElement>(null);
  const an = voice.analyser;

  useEffect(() => {
    if (!an) return;
    const buf = new Float32Array(an.fftSize);
    let raf = 0, lvl = 0;
    const draw = () => {
      an.getFloatTimeDomainData(buf);
      let s = 0;
      for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
      lvl += (Math.min(1, Math.sqrt(s / buf.length) * 9) - lvl) * 0.3;
      ref.current?.style.setProperty("--lvl", lvl.toFixed(3));
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [an]);

  const st = voice.state;
  const phase = st === "off" ? "off" : st === "paused" ? "paused" : st === "hearing" ? "hearing"
    : busy ? "thinking" : who === "saakshi" || who === "worker" ? "speaking" : "listening";
  const label = phase === "off" ? t("start", lang) : t(phase as "paused" | "hearing" | "thinking" | "speaking" | "listening", lang);

  return (
    <div className="orb-wrap">
      <button className={`orb ${tone} ${phase}`} style={{ width: size, height: size }} onClick={voice.toggle}
        aria-label={label} title={label}>
        <span className="orb-lvl" ref={ref} />
        <span className="orb-ring" />
        {phase === "thinking" ? <span className="spinner light" /> : phase === "paused" || phase === "off" ? (
          <svg width={size * 0.3} height={size * 0.3} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            {phase === "paused" && <path d="M4 4l16 16" />}
          </svg>
        ) : <span className="orb-bars"><i /><i /><i /><i /></span>}
      </button>
      <p className={`orb-label small ${phase}`} aria-live="polite">{label}</p>
      {voice.blocked && <p className="error-line" style={{ textAlign: "center", margin: 0 }}>{t("micBlocked", lang)}</p>}
    </div>
  );
}
