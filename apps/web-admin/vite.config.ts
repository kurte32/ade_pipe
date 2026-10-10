/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
const idpTarget = process.env.VITE_DEV_IDP_PROXY_TARGET ?? "http://localhost:8001";
const proxy = {
  "/api": { target: apiTarget, changeOrigin: true },
  "/dev-idp": { target: idpTarget, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/dev-idp/, "") },
};

export default defineConfig({
  plugins: [react()],
  server: { host: true, proxy },
  preview: { proxy },
  test: { environment: "jsdom", globals: true },
});
