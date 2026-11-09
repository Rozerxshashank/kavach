/* Per-browser credentials. Storage can be unavailable (private mode), so every access is guarded. */

const K = "saakshi.auth.v1";
type Store = { tokens: Record<string, string>; me?: string; admin?: string };

function read(): Store {
  try { return JSON.parse(localStorage.getItem(K) || "") as Store; } catch { return { tokens: {} }; }
}
function write(s: Store) { try { localStorage.setItem(K, JSON.stringify(s)); } catch { /* storage blocked */ } }

const mem: Store = read();
if (!mem.tokens) mem.tokens = {};

export const auth = {
  token: (wid: string) => mem.tokens[wid],
  setToken(wid: string, token: string, asMe = false) { mem.tokens[wid] = token; if (asMe) mem.me = wid; write(mem); },
  me: () => mem.me,
  logout() { if (mem.me) delete mem.tokens[mem.me]; mem.me = undefined; write(mem); },
  admin: () => mem.admin,
  setAdmin(k: string) { mem.admin = k; write(mem); },
};
