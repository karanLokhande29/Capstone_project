/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const HOSTED = process.env.VITE_ARTIFACT === "1";
// The demo's comparator API (ui/api/server.py, port 5190) and the workspace assistant proxy (ui/server, port 5182).
const COMPARATOR = "http://127.0.0.1:5190";
const API_PROXY = {
  "^/api/(health|compare|replay|rehydrate|freshness)": COMPARATOR,
  "/api": "http://127.0.0.1:5182",
};
const AZURE = process.env.VITE_NO_PROXY === "1" && !HOSTED;

export default defineConfig({
  // Hosted (Artifact) build: relative asset paths and its own output folder.
  base: HOSTED ? "./" : "/",
  plugins: [react(), tailwindcss()],
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
