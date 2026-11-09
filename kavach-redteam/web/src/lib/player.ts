/* One shared audio element routed through an AnalyserNode, so every waveform on
   screen reacts to the voice that is actually playing. */

export type Speaker = "caller" | "bot" | "mic" | null;

type Listener = () => void;

class Player {
  private ctx: AudioContext | null = null;
  private el: HTMLAudioElement | null = null;
  private src: MediaElementAudioSourceNode | null = null;
  analyser: AnalyserNode | null = null;
  speaker: Speaker = null;
  muted = false;
  private listeners = new Set<Listener>();
  private resolveCurrent: (() => void) | null = null;

  /** Must be called from a user gesture at least once (browser autoplay rules). */
  unlock() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.el = new Audio();
      this.el.crossOrigin = "anonymous";
      this.el.preload = "auto";
      this.src = this.ctx.createMediaElementSource(this.el);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0.6;
      this.src.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
      this.el.addEventListener("ended", () => this.finish());
      this.el.addEventListener("error", () => this.finish());
    }
    if (this.ctx.state === "suspended") void this.ctx.resume();
  }

  get context() { this.unlock(); return this.ctx!; }

  get currentTime() { return this.el?.currentTime ?? 0; }
  get duration() { return this.el && isFinite(this.el.duration) ? this.el.duration : 0; }

  subscribe(fn: Listener) { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; }
  private notify() { this.listeners.forEach((l) => l()); }

  private finish() {
    this.speaker = null;
    const r = this.resolveCurrent;
    this.resolveCurrent = null;
    this.notify();
    r?.();
  }

  /** Plays a clip and resolves when it ends (or is stopped). */
  play(url: string, speaker: Speaker): Promise<void> {
    this.unlock();
    this.stop();
    if (this.muted) return new Promise((r) => setTimeout(r, 350));
    const el = this.el!;
    return new Promise<void>((resolve) => {
      this.resolveCurrent = resolve;
      this.speaker = speaker;
      el.src = url;
      el.currentTime = 0;
      el.play().catch(() => this.finish());
      this.notify();
    });
  }

  stop() {
    if (this.el && !this.el.paused) this.el.pause();
    if (this.resolveCurrent) this.finish();
  }

  setMuted(m: boolean) {
    this.muted = m;
    if (m) this.stop();
    this.notify();
  }
}

export const player = new Player();
