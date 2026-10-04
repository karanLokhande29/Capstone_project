import { create } from "zustand";

export type Theme = "light" | "dark" | "system";

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
