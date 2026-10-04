import { create } from "zustand";
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { derive, type Derived } from "./derive";
import { chooseRepository, SourceError, type ProjectRepository } from "./repository";

type Theme = "light" | "dark" | "system";

interface DataState {
  status: "idle" | "loading" | "ready" | "error";
  error: { message: string; file?: string; command?: string } | null;
  snapshot: Snapshot | null;
  confidence: ConfidenceModel | null;
  derived: Derived | null;
  adapter: ProjectRepository["kind"] | null;
  load: (repo?: ProjectRepository) => Promise<void>;
  setLoaded: (snapshot: Snapshot, confidence: ConfidenceModel | null, adapter?: ProjectRepository["kind"]) => void;
}

export const useData = create<DataState>((set, get) => ({
  status: "idle",
  error: null,
  snapshot: null,
  confidence: null,
  derived: null,
  adapter: null,
  async load(repo) {
    if (get().status === "loading") return;
    const r = repo ?? chooseRepository(typeof window === "undefined" ? "" : window.location.search);
    set({ status: "loading", error: null, adapter: r.kind });
    try {
      const { snapshot, confidence } = await r.load();
      get().setLoaded(snapshot, confidence, r.kind);
    } catch (e) {
      const err = e as Error;
      set({ status: "error", error: e instanceof SourceError ? { message: err.message, file: e.file, command: e.command } : { message: err.message } });
    }
  },
  setLoaded(snapshot, confidence, adapter = "repo") {
    set({ status: "ready", snapshot, confidence, derived: derive(snapshot), adapter });
  },
}));

function safeGet(k: string): string | null {
  try { return localStorage.getItem(k); } catch { return null; }
}
function safeSet(k: string, v: string) {
  try { localStorage.setItem(k, v); } catch { /* storage unavailable: keep in memory only */ }
}

interface SettingsState {
  theme: Theme;
  assistantEnabled: boolean;
  liveEnabled: boolean;
  assistantOpen: boolean;
  setTheme: (t: Theme) => void;
  setAssistantEnabled: (v: boolean) => void;
  setLiveEnabled: (v: boolean) => void;
  setAssistantOpen: (v: boolean) => void;
}

export function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  const host = document.documentElement.getAttribute("data-theme");
  const system = host === "dark" ? true : host === "light" ? false
    : typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = t === "dark" || (t === "system" && system);
  document.documentElement.classList.toggle("dark", dark);
}

export const useSettings = create<SettingsState>((set) => ({
  theme: (safeGet("cc-theme") as Theme) || "system",
  // The assistant and live mode are OFF by default (§8.3); the toggles are per-viewer conveniences.
  assistantEnabled: safeGet("cc-assistant") === "on",
  liveEnabled: safeGet("cc-live") === "on",
  assistantOpen: false,
  setTheme(t) { safeSet("cc-theme", t); applyTheme(t); set({ theme: t }); },
  setAssistantEnabled(v) { safeSet("cc-assistant", v ? "on" : "off"); set({ assistantEnabled: v }); },
  setLiveEnabled(v) { safeSet("cc-live", v ? "on" : "off"); set({ liveEnabled: v }); },
  setAssistantOpen(v) { set({ assistantOpen: v }); },
}));
