/* The demo's autopilot talks to the two phones through window events, and waits for them to go quiet
   (no request in flight, no audio playing) before the next line. Phones report their busy state here. */

import { player } from "./player";

const busy = { worker: false, employer: false };

export function setBusy(who: keyof typeof busy, v: boolean) { busy[who] = v; }

/** Typed as the worker, or (voiced) spoken by Timbre in her voice and sent as audio through Prisma. */
export function workerSay(text: string, voiced = false) {
  window.dispatchEvent(new CustomEvent("saakshi:worker-say", { detail: { text, voiced } }));
}

/** "__accept__" picks up a ringing call; anything else is said on the live call (voiced like workerSay). */
export function employerSay(text: string, voiced = false) {
  window.dispatchEvent(new CustomEvent("saakshi:employer-say", { detail: { text, voiced } }));
}

export type Line = { text: string; voiced: boolean };

export async function waitIdle(signal: { stopped: boolean }, quietMs = 1100, timeoutMs = 90000) {
  const t0 = Date.now();
  let quiet = 0;
  await new Promise((r) => setTimeout(r, 300));
  while (!signal.stopped && Date.now() - t0 < timeoutMs) {
    await new Promise((r) => setTimeout(r, 150));
    if (!busy.worker && !busy.employer && player.who === null) quiet += 150; else quiet = 0;
    if (quiet >= quietMs) return;
  }
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
