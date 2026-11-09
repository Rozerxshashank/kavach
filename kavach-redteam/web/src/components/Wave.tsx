import { useEffect, useState, useSyncExternalStore } from "react";
import type { Clip } from "../api";
import { player, type Speaker } from "../lib/player";

/** Static waveform from server-computed peaks; click to play, shows progress. */
export function Wave({ clip, who, compact = false, cut = false }: {
  clip: Clip; who: Exclude<Speaker, null | "mic">; compact?: boolean; cut?: boolean;
}) {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  useSyncExternalStore(player.subscribe.bind(player), () => player.speaker);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      setProgress(player.duration ? player.currentTime / player.duration : 0);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const toggle = async () => {
    if (playing) { player.stop(); return; }
    setPlaying(true);
    setProgress(0);
    await player.play(clip.url, who);
    setPlaying(false);
    setProgress(0);
  };

  const color = who === "caller" ? "var(--ember)" : "var(--ice)";
  const bars = compact ? clip.peaks.filter((_, i) => i % 2 === 0) : clip.peaks;
  return (
    <button className={`wave ${compact ? "compact" : ""}`} onClick={toggle} aria-label={playing ? "Stop" : "Play"}
      style={{ ["--c" as string]: color }}>
      <span className="wave-btn">{playing ? <StopIcon /> : <PlayIcon />}</span>
      <span className="wave-bars">
        {bars.map((p, i) => (
          <i key={i} style={{ height: `${12 + p * 88}%`, opacity: i / bars.length <= progress ? 1 : 0.35 }} />
        ))}
        {cut && <em className="wave-cut" />}
      </span>
      <span className="wave-dur mono">{clip.duration.toFixed(1)}s</span>
    </button>
  );
}

const PlayIcon = () => <svg width="10" height="12" viewBox="0 0 10 12"><path d="M0 0l10 6-10 6z" fill="currentColor" /></svg>;
const StopIcon = () => <svg width="10" height="10" viewBox="0 0 10 10"><rect width="10" height="10" rx="1" fill="currentColor" /></svg>;
