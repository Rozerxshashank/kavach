/* Where the app is served from: "/" normally, "/saakshi" when it shares a host with Kavach (vite build --base).
   Server paths like "/api/..." and "/audio/..." are written from the root; `at` puts them under the base. */
export const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export function at(path: string): string {
  return BASE && path.startsWith("/") && !path.startsWith("//") && path !== BASE && !path.startsWith(BASE + "/")
    ? BASE + path : path;
}

/** Under a base, every root-relative fetch and EventSource goes under it too (one place, instead of every call). */
export function installBase(): void {
  if (!BASE) return;
  const fetch0 = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => fetch0(typeof input === "string" ? at(input) : input, init);
  const ES = window.EventSource;
  window.EventSource = class extends ES {
    constructor(url: string | URL, init?: EventSourceInit) { super(typeof url === "string" ? at(url) : url, init); }
  } as typeof EventSource;
}
