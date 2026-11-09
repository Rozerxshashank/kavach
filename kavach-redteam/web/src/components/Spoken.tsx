import { useEffect, useState } from "react";
import { player } from "../lib/player";

/** Text that reveals word-by-word in sync with the clip currently playing. */
export function Spoken({ text, active, className = "", cut = false }: {
  text: string; active: boolean; className?: string; cut?: boolean;
}) {
  const words = text.split(/(\s+)/);
  const [shown, setShown] = useState(active ? 0 : words.length);

  useEffect(() => {
    if (!active) { setShown(words.length); return; }
    let raf = 0;
    const tick = () => {
      const d = player.duration;
      const p = d ? player.currentTime / d : 0;
      setShown(player.muted ? words.length : Math.ceil(p * words.length * 1.08));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, text]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <span className={className}>
      {words.map((w, i) => (
        <span key={i} style={{ opacity: i < shown ? 1 : 0.14, transition: "opacity .25s" }}>{w}</span>
      ))}
      {cut && <span className="cut-mark"> — cut off</span>}
    </span>
  );
}
