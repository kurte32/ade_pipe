/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// Same-origin in every environment: Vite proxies /api and /dev-idp locally, Front Door routes
// /api/* in Azure. No absolute backend URLs in code.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";
const idpTarget = process.env.VITE_DEV_IDP_PROXY_TARGET ?? "http://localhost:8001";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Pipeline de Posibles Tiendas",
        short_name: "Pipeline",
        description: "Captura de sitios candidatos para coordinadores",
        lang: "es-MX",
        start_url: "/",
        display: "standalone",
        background_color: "#f3f5f8",
        theme_color: "#d7121e",
        icons: [{ src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
      },
      workbox: {
        // Never serve the Entra redirect response or API calls from the shell cache (ADR-005).
        navigateFallbackDenylist: [/^\/api\//, /^\/dev-idp\//, /[#?&]code=/, /^\/auth/],
        runtimeCaching: [],
        globPatterns: ["**/*.{js,css,html,svg,woff2}"],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    host: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/dev-idp": { target: idpTarget, changeOrigin: true, rewrite: (p) => p.replace(/^\/dev-idp/, "") },
    },
  },
  preview: {
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/dev-idp": { target: idpTarget, changeOrigin: true, rewrite: (p) => p.replace(/^\/dev-idp/, "") },
    },
  },
  test: { environment: "jsdom", globals: true },
});
