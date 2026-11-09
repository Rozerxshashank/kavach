import { LEVEL } from "../lib/util";
import { levelName } from "../lib/i18n";

/** Evidence level: four filled steps, always with a text label (never colour alone). */
export function LevelBadge({ level, small = false, lang }: { level: number | null | undefined; small?: boolean; lang?: string }) {
  const l = level ?? 0;
  return (
    <span className={`lvl l${l} ${small ? "sm" : ""}`} title={LEVEL[l].desc}>
      <span className="lvl-steps" aria-hidden>{[1, 2, 3].map((i) => <i key={i} className={i <= l ? "on" : ""} />)}</span>
      <span>L{l} · {lang ? levelName(l, lang) : LEVEL[l].name}</span>
    </span>
  );
}
