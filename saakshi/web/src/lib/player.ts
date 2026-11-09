import { at } from "./base";
/* One audio element routed through an analyser so waveforms react to whoever is
   speaking. play() resolves when the clip ends; sequences play back to back. */

export type Who = "saakshi" | "worker" | "employer" | "mic" | null;
type Listener = () => void;

class Player {
  private ctx: AudioContext | null = null;
  private el: HTMLAudioElement | null = null;
  analyser: AnalyserNode | null = null;
  who: Who = null;
  muted = false;
  private listeners = new Set<Listener>();
  private done: (() => void) | null = null;

  unlock() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.el = new Audio();
      this.el.crossOrigin = "anonymous";
      const src = this.ctx.createMediaElementSource(this.el);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 2048;
      src.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
      // any later tap or key wakes audio back up if the browser suspended it (e.g. after a phone call)
      const wake = () => { if (this.ctx && this.ctx.state !== "running") void this.ctx.resume(); };
      document.addEventListener("pointerdown", wake, true);
      document.addEventListener("keydown", wake, true);
      this.el.addEventListener("ended", () => this.finish());
      this.el.addEventListener("error", () => this.finish());
    }
    if (this.ctx.state === "suspended") void this.ctx.resume();
  }

  get context() { this.unlock(); return this.ctx!; }
  get progress() { return this.el && this.el.duration ? this.el.currentTime / this.el.duration : 0; }

  subscribe = (fn: Listener) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private notify() { this.listeners.forEach((l) => l()); }

  private finish() {
    this.who = null;
    const d = this.done;
    this.done = null;
    this.notify();
    d?.();
  }

  play(url: string, who: Who): Promise<void> {
    this.unlock();
    this.stop();
    if (this.muted) return new Promise((r) => setTimeout(r, 250));
    const el = this.el!;
    return new Promise<void>((resolve) => {
      this.done = resolve;
      this.who = who;
      el.src = at(url);
      el.play().catch(() => this.finish());
      this.notify();
      // if the browser holds audio suspended (no tap yet, a phone call interrupted it), don't sit on "speaking" forever
      const myUrl = url;
      setTimeout(() => {
        if (this.done === resolve && el.src.endsWith(myUrl) && (this.ctx?.state !== "running" || el.currentTime === 0)) {
          void this.ctx?.resume();
          setTimeout(() => { if (this.done === resolve && el.currentTime === 0) { el.pause(); this.finish(); } }, 1500);
        }
      }, 2500);
    });
  }

  async sequence(items: { url?: string | null; who: Who }[]) {
    for (const it of items) if (it.url) await this.play(it.url, it.who);
  }

  stop() {
    if (this.el && !this.el.paused) this.el.pause();
    if (this.done) this.finish();
  }

  setMuted(m: boolean) { this.muted = m; if (m) this.stop(); this.notify(); }
}

export const player = new Player();
