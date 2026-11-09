/* Kavach's mark: a voice waveform held inside a shield. Below ~22 px it switches to five thicker bars so it stays crisp. */
const SHIELD = "M32 4.5C25.6 7.8 18.2 9.9 9.5 10.8V30.2C9.5 44.6 18.6 54.7 32 60C45.4 54.7 54.5 44.6 54.5 30.2V10.8C45.8 9.9 38.4 7.8 32 4.5Z";
const FULL: [number, number, number, number][] = [
  [15.5, 27.0, 3.6, 9],
  [20.4, 20.5, 3.6, 22],
  [25.3, 24.5, 3.6, 14],
  [30.2, 16.0, 3.6, 31],
  [35.1, 24.5, 3.6, 14],
  [40.0, 20.5, 3.6, 22],
  [44.9, 27.0, 3.6, 9],
];
const SMALL: [number, number, number, number][] = [
  [12.3, 26.0, 5.8, 11],
  [20.7, 20.0, 5.8, 23],
  [29.1, 15.0, 5.8, 33],
  [37.5, 20.0, 5.8, 23],
  [45.9, 26.0, 5.8, 11],
];

export function LogoMark({ size = 28, className }: { size?: number; className?: string }) {
  const bars = size < 22 ? SMALL : FULL;
  return (
    <svg className={"logo-mark" + (className ? " " + className : "")} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <path d={SHIELD} fill="var(--khata, #9e2a2b)" />
      <g fill="#fbf3ee">{bars.map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} rx={w / 2} />)}</g>
    </svg>
  );
}
