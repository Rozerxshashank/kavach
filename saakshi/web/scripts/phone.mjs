// Phone-test mode: HTTPS on your WiFi (phones only allow the microphone on HTTPS).
// A tiny gateway on :5175 looks at the first byte of each connection:
//   TLS handshake  -> passed through to the HTTPS dev server on :5176
//   plain HTTP     -> redirected to the https:// address
// so typing "10.x.x.x:5175" on a phone works even without "https://".
import net from "node:net";
import { spawn } from "node:child_process";

const PUBLIC_PORT = 5175;
const VITE_PORT = 5176;

const vite = spawn("npx", ["vite", "--port", String(VITE_PORT), "--strictPort"], {
  stdio: "inherit",
  env: { ...process.env, SAAKSHI_PHONE: "1", SAAKSHI_PHONE_PUBLIC_PORT: String(PUBLIC_PORT) },
});

const gateway = net.createServer((client) => {
  client.once("data", (first) => {
    if (first[0] === 0x16) {
      const upstream = net.connect(VITE_PORT, "127.0.0.1", () => {
        upstream.write(first);
        client.pipe(upstream).pipe(client);
      });
      upstream.on("error", () => client.destroy());
      client.on("error", () => upstream.destroy());
      return;
    }
    const req = first.toString("latin1");
    const path = (req.split(" ")[1] || "/").replace(/[\r\n]/g, "");
    const host = (/\r\nhost:\s*([^\r\n:]+)/i.exec(req) || [])[1] || "localhost";
    client.end(`HTTP/1.1 301 Moved Permanently\r\nLocation: https://${host}:${PUBLIC_PORT}${path}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n`);
  });
  client.on("error", () => {});
});

gateway.listen(PUBLIC_PORT, "0.0.0.0", () => console.log(`\n  ➜  Phone:   open  <this computer's IP>:${PUBLIC_PORT}  (http or https both work)\n`));

const stop = () => { gateway.close(); vite.kill(); process.exit(0); };
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
vite.on("exit", (code) => { gateway.close(); process.exit(code ?? 0); });
