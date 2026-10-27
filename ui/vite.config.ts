/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const HOSTED = process.env.VITE_ARTIFACT === "1";
// The demo's comparator API (ui/api/server.py, port 5190) and the workspace assistant proxy (ui/server, port 5182).
const COMPARATOR = "http://127.0.0.1:5190";
// The audit generator's local backend (src/auditgen/api.py, 127.0.0.1 only).
const AUDITGEN = "http://127.0.0.1:8765";
const API_PROXY = {
  "^/api/auditgen": AUDITGEN,
  "^/api/(health|compare|replay|rehydrate|freshness)": COMPARATOR,
  "/api": "http://127.0.0.1:5182",
};
const AZURE = process.env.VITE_NO_PROXY === "1" && !HOSTED;

const PUBLIC_BUILD = HOSTED || process.env.VITE_NO_PROXY === "1";

/** Public builds never ship the audit generator's replay packs (they carry RBI excerpts and are local-only). */
function stripAuditReplay() {
  return {
    name: "strip-auditgen-replay",
    apply: "build" as const,
    async closeBundle() {
      if (!PUBLIC_BUILD) return;
      const { rm } = await import("node:fs/promises");
      const out = HOSTED ? "dist-artifact" : "dist-azure";
      await rm(fileURLToPath(new URL(`./${out}/auditgen`, import.meta.url)), { recursive: true, force: true });
    },
  };
}

export default defineConfig({
  // Hosted (Artifact) build: relative asset paths and its own output folder.
  base: HOSTED ? "./" : "/",
  plugins: [react(), tailwindcss(), stripAuditReplay()],
  resolve: {
    alias: [
      // Public builds (Azure / Artifact) contain only the demo, which reads public/data/*.json. The workspace's snapshot and
      // confidence-model URLs are stubbed so Vite does not emit them as assets.
      ...(process.env.VITE_NO_PROXY === "1" || HOSTED ? [
        { find: /^\.\/snapshot\.json\?url$/, replacement: "./public_stub.json?url" },
        { find: /^\.\/confidence_model_v1\.json\?url$/, replacement: "./public_stub.json?url" },
      ] : []),
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
    ],
  },
  server: { port: 5181, strictPort: true, proxy: API_PROXY },
  preview: { port: 5183, strictPort: true, proxy: API_PROXY },
  build: { chunkSizeWarningLimit: 2500, sourcemap: false, outDir: HOSTED ? "dist-artifact" : AZURE ? "dist-azure" : "dist" },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "server/**/*.test.ts"],
    environmentMatchGlobs: [["server/**", "node"]],
  },
});
