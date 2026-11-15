import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND = process.env.NAM_BACKEND_URL || "http://127.0.0.1:8000";

const API_PREFIXES = [
  "/health",
  "/search",
  "/locations",
  "/location",
  "/landing_sites",
  "/bookmarks",
  "/share",
  "/elevation",
  "/terrain",
  "/imagery",
  "/tiles",
  "/connectors",
  "/measure",
  "/layers",
  "/discoveries",
  "/sites",
  "/datasets",
  "/science",
  "/panoramas",
  "/traverses",
  "/walkview",
  "/jev",
  "/missions",
  "/environment",
  "/water",
  "/shelters",
  "/nodes",
  "/presence",
  "/events",
  "/docs",
  "/openapi.json",
];

const proxy: Record<string, { target: string; changeOrigin: boolean; ws?: boolean }> = {
  "/ws": { target: BACKEND, changeOrigin: true, ws: true },
};
for (const prefix of API_PREFIXES) {
  proxy[prefix] = { target: BACKEND, changeOrigin: true };
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy,
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
    allowedHosts: true,
    proxy,
  },
});
