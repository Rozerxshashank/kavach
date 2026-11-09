import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

// `npm run dev:phone` (scripts/phone.mjs) serves over HTTPS on your WiFi so a phone can open it and use the
// microphone (phone browsers only allow the mic on HTTPS). The certificate is self-signed: accept the warning once.
const phone = process.env.SAAKSHI_PHONE === "1";

export default defineConfig({
  plugins: [react(), ...(phone ? [basicSsl()] : [])],
  server: {
    port: 5174,
    host: phone ? "127.0.0.1" : "localhost",     // phone mode: the gateway connects over IPv4
    // in phone mode the browser talks to the gateway port, so live-reload must use it too
    hmr: phone ? { clientPort: Number(process.env.SAAKSHI_PHONE_PUBLIC_PORT || 5175) } : undefined,
    proxy: {
      "/api": { target: "http://127.0.0.1:8100", changeOrigin: true },
      "/audio": { target: "http://127.0.0.1:8100", changeOrigin: true },
      "/tel": { target: "http://127.0.0.1:8100", changeOrigin: true },
    },
  },
});
