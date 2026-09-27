import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// În dezvoltare, /api merge la backend (în Docker: http://backend:8000). În producție, nginx
// servește fișierele construite și face același lucru.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: process.env.API_PROXY_TARGET ?? "http://localhost:8000" },
    },
  },
});
