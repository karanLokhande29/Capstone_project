import { serve } from "@hono/node-server";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createApp } from "./app";
import { PythonBridge } from "./bridge";
import { GeminiClient } from "./llm";
import { Cache, loadEnv, Quota } from "./store";

// Local proxy for the opt-in routes only. Binds to 127.0.0.1. Keys: ASSISTANT_GEMINI_API_KEY (never GEMINI_API_KEY).
const UI = join(dirname(fileURLToPath(import.meta.url)), "..");
const env = loadEnv(join(UI, ".env"));
const key = env.ASSISTANT_GEMINI_API_KEY?.trim();
const app = createApp({
  llm: key ? new GeminiClient(key, env.ASSISTANT_GEMINI_MODEL || "gemini-3.5-flash-lite") : null,
  bridge: new PythonBridge(UI),
  quota: new Quota(join(UI, "server/.state"), Number(env.ASSISTANT_DAILY_CAP || 50)),
  cache: new Cache(join(UI, "server/.cache")),
  snapshotPath: join(UI, "src/data/snapshot.json"),
  modelPath: join(UI, "src/data/confidence_model_v1.json"),
});
const port = Number(env.ASSISTANT_PORT || 5182);
serve({ fetch: app.fetch, port, hostname: "127.0.0.1" }, () => {
  console.log(`assistant proxy on http://127.0.0.1:${port} — assistant ${key ? "ENABLED (own key)" : "OFF (no ASSISTANT_GEMINI_API_KEY)"}`);
});
