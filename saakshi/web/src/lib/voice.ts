/* Hands-free listening, like a phone call: the mic stays open, Saakshi notices when you start
   and stop speaking, and you can talk over her (barge-in) to interrupt.

   How it decides:
   - a running noise floor is learnt while nobody speaks; speech must rise clearly above it;
   - an utterance starts after ~150 ms of speech (~280 ms while Saakshi herself is talking, so her
     voice leaking from the speaker doesn't trigger it; the browser's echo cancellation removes most);
   - it ends after `silenceMs` of quiet (a natural pause), or at 25 s (Prisma's limit is 30 s);
   - 400 ms before the start is kept, so the first syllable isn't clipped;
   - blips under 300 ms of actual speech (a cough, a door) are ignored.
   Audio goes out as 16 kHz mono 16-bit WAV, the format Prisma expects. */

import { player } from "./player";

export type VoiceState = "off" | "listening" | "hearing" | "paused";

type Opts = {
  onUtterance: (wav: Blob) => void;
  onState?: (s: VoiceState) => void;
  onBargeIn?: () => void;
  silenceMs?: number;
};

export class VoiceLoop {
  analyser: AnalyserNode | null = null;
  state: VoiceState = "off";
  private stream: MediaStream | null = null;
  private src: MediaStreamAudioSourceNode | null = null;
  private proc: ScriptProcessorNode | null = null;
  private sink: GainNode | null = null;
  private rate = 48000;
  private pre: Float32Array[] = [];
  private cur: Float32Array[] | null = null;
  private floor = 0.006;
  private above = 0;
  private quiet = 0;
  private speechMs = 0;
  private wasPlaying = false;
  private playEndedAt = 0;
  private startedAt = 0;
  silenceMs: number;

  constructor(private opts: Opts) { this.silenceMs = opts.silenceMs ?? 950; }

  async start() {
    if (this.stream) { this.resume(); return; }
    const ctx = player.context;
    if (ctx.state === "suspended") await ctx.resume();
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.rate = ctx.sampleRate;
    this.src = ctx.createMediaStreamSource(this.stream);
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.src.connect(this.analyser);
    this.proc = ctx.createScriptProcessor(2048, 1, 1);
    this.sink = ctx.createGain();
    this.sink.gain.value = 0;                     // the processor must reach the output to run; keep it silent
    this.src.connect(this.proc);
    this.proc.connect(this.sink);
    this.sink.connect(ctx.destination);
    this.proc.onaudioprocess = (e) => this.frame(e.inputBuffer.getChannelData(0));
    this.startedAt = performance.now();
    this.set("listening");
  }

  pause() { this.cur = null; this.above = 0; this.set("paused"); }
  resume() { if (this.stream) { this.above = 0; this.set("listening"); } }
  toggle() { if (this.state === "paused") this.resume(); else this.pause(); }

  stop() {
    this.proc?.disconnect(); this.sink?.disconnect(); this.src?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null; this.proc = null; this.analyser = null; this.cur = null;
    this.set("off");
  }

  private set(s: VoiceState) { if (this.state !== s) { this.state = s; this.opts.onState?.(s); } }

  private frame(data: Float32Array) {
    if (this.state === "off" || this.state === "paused") return;
    const f = new Float32Array(data);
    const ms = (f.length / this.rate) * 1000;
    let sum = 0;
    for (let i = 0; i < f.length; i++) sum += f[i] * f[i];
    const rms = Math.sqrt(sum / f.length);
    const now = performance.now();
    const playing = player.who !== null;
    if (this.wasPlaying && !playing) this.playEndedAt = now;
    this.wasPlaying = playing;
    const echoTail = now - this.playEndedAt < 250;      // the room still rings for a moment after she stops

    if (!this.cur) {
      this.pre.push(f);
      let keep = 0;
      for (let i = this.pre.length - 1; i >= 0; i--) { keep += this.pre[i].length; if (keep > this.rate * 0.4) { this.pre = this.pre.slice(i); break; } }
      const startTh = Math.max(this.floor * 3.2, 0.012) * (playing || echoTail ? 2.2 : 1);
      if (rms > startTh) this.above += ms;
      else {
        this.above = Math.max(0, this.above - ms * 2);
        if (!playing && !echoTail) this.floor = Math.min(0.05, Math.max(0.002, this.floor * 0.96 + rms * 0.04));
      }
      const warm = now - this.startedAt > 300;            // let the floor settle first
      if (warm && this.above >= (playing ? 280 : 150)) {
        if (playing) { player.stop(); this.opts.onBargeIn?.(); }
        this.cur = this.pre; this.pre = [];
        this.quiet = 0; this.speechMs = this.above; this.above = 0;
        this.set("hearing");
      }
      return;
    }
    this.cur.push(f);
    const contTh = Math.max(this.floor * 2, 0.008);
    if (rms > contTh) { this.quiet = 0; this.speechMs += ms; } else this.quiet += ms;
    const total = this.cur.reduce((n, x) => n + x.length, 0) / this.rate * 1000;
    if (this.quiet >= this.silenceMs || total > 25000) this.finish();
  }

  private finish() {
    const frames = this.cur!;
    this.cur = null;
    this.set("listening");
    if (this.speechMs < 300) return;
    const drop = Math.max(0, Math.floor(((this.quiet - 300) / 1000) * this.rate));   // trim most trailing silence
    const len = Math.max(0, frames.reduce((n, x) => n + x.length, 0) - drop);
    const pcm = new Float32Array(len);
    let o = 0;
    for (const x of frames) { if (o >= len) break; pcm.set(x.subarray(0, Math.min(x.length, len - o)), o); o += x.length; }
    void toWav16k(pcm, this.rate).then((w) => this.opts.onUtterance(w));
  }
}

async function toWav16k(pcmIn: Float32Array, rateIn: number): Promise<Blob> {
  const rate = 16000;
  const buf = new AudioBuffer({ length: pcmIn.length, numberOfChannels: 1, sampleRate: rateIn });
  buf.copyToChannel(pcmIn, 0);
  const offline = new OfflineAudioContext(1, Math.ceil((pcmIn.length / rateIn) * rate), rate);
  const src = offline.createBufferSource();
  src.buffer = buf;
  src.connect(offline.destination);
  src.start();
  const pcm = (await offline.startRendering()).getChannelData(0);
  const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const w = (o: number, s: string) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); out.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVE");
  w(12, "fmt "); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true);
  out.setUint32(24, rate, true); out.setUint32(28, rate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true);
  w(36, "data"); out.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    out.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([out], { type: "audio/wav" });
}
