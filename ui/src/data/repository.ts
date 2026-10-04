import type { ConfidenceModel, Snapshot } from "@/domain/types";
import snapshotUrl from "./snapshot.json?url";
import confidenceUrl from "./confidence_model_v1.json?url";
import { fixtureSnapshot } from "./fixture";

export interface LoadedData {
  snapshot: Snapshot;
  confidence: ConfidenceModel | null;
}

/** The data layer every screen reads through. */
export interface ProjectRepository {
  kind: "repo" | "fixture";
  load(): Promise<LoadedData>;
}

export class SourceError extends Error {
  constructor(message: string, readonly file: string, readonly command: string) {
    super(message);
  }
}

/** Reads the typed snapshot produced by `npm run ingest` (and the frozen confidence model from `npm run calibrate`). */
export class RepoAdapter implements ProjectRepository {
  kind = "repo" as const;
  constructor(private readonly urls = { snapshot: snapshotUrl, confidence: confidenceUrl }) {}

  async load(): Promise<LoadedData> {
    const r = await fetch(this.urls.snapshot);
    if (!r.ok) throw new SourceError(`snapshot.json unreadable (${r.status})`, "ui/src/data/snapshot.json", "cd ui && npm run ingest");
    const snapshot = (await r.json()) as Snapshot;
    if (!snapshot?.meta || !Array.isArray(snapshot.findings)) {
      throw new SourceError("snapshot.json has an unexpected shape", "ui/src/data/snapshot.json", "cd ui && npm run ingest");
    }
    let confidence: ConfidenceModel | null = null;
    try {
      const c = await fetch(this.urls.confidence);
      if (c.ok) confidence = (await c.json()) as ConfidenceModel;
    } catch {
      confidence = null;
    }
    return { snapshot, confidence };
  }
}

/** Only numbers printed in the Master Document; any per-item row is synthetic and the app shows a watermark. */
export class FixtureAdapter implements ProjectRepository {
  kind = "fixture" as const;
  async load(): Promise<LoadedData> {
    return { snapshot: fixtureSnapshot(), confidence: null };
  }
}

export function chooseRepository(search: string): ProjectRepository {
  return new URLSearchParams(search).get("fixture") === "1" ? new FixtureAdapter() : new RepoAdapter();
}
