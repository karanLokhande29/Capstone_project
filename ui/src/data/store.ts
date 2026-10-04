import { create } from "zustand";
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { derive, type Derived } from "./derive";
import { chooseRepository, SourceError, type ProjectRepository } from "./repository";

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

// Theme and per-viewer toggles live in ./settings (no snapshot import), re-exported here for the workspace screens.
export { applyTheme, useSettings } from "./settings";
