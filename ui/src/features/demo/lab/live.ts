import { useCallback, useRef, useState } from "react";
import { fetchReplay, streamCompare, type CompareBody, type CompareEvent, type LiveConfidence, type LiveDone, type LiveField, type LiveVerdict } from "../api";
import type { FieldStatus, Unit } from "../types";

export interface LiveRun {
  phase: "idle" | "receiving" | "done" | "error";
  source: "live" | "replay" | null;
  streaming: "incremental" | "buffered" | null;
  fields: LiveField[];
  verdict: LiveVerdict | null;
  confidence: LiveConfidence | null;
  done: LiveDone | null;
  error: { code: string; message: string; replayKey?: string | null } | null;
  recordedUtc: string | null;
}

const IDLE: LiveRun = { phase: "idle", source: null, streaming: null, fields: [], verdict: null, confidence: null, done: null, error: null, recordedUtc: null };

/** Canonical cache key, identical to the server's: sha256(prompt_sha|rule_sha|model|mode|payload). */
export async function cacheKey(promptSha: string, ruleSha: string, model: string, body: CompareBody): Promise<string> {
  const payload = body.mode === "benchmark" ? JSON.stringify({ unitId: body.unitId })
    : body.mode === "edit" ? JSON.stringify({ unitId: body.unitId, edits: body.edits }) : null;
  if (payload == null) throw new Error("paste runs are never cached by content");
  const data = new TextEncoder().encode(`${promptSha}|${ruleSha}|${model}|${body.mode}|${payload}`);
  const h = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function useLiveRun() {
  const [run, setRun] = useState<LiveRun>(IDLE);
  const abort = useRef<AbortController | null>(null);
  const apply = useCallback((e: CompareEvent, source: "live" | "replay") => {
    setRun((r) => {
      switch (e.type) {
        case "status": return { ...r, source, phase: "receiving", streaming: e.data.streaming ?? r.streaming };
        case "field": return { ...r, source, fields: [...r.fields, e.data] };
        case "verdict": return { ...r, verdict: e.data };
        case "confidence": return { ...r, confidence: e.data };
        case "done": return { ...r, phase: "done", done: e.data, recordedUtc: e.data.recordedUtc };
        case "error": return { ...r, phase: "error", error: e.data };
      }
    });
  }, []);
  const start = useCallback(async (body: CompareBody) => {
    abort.current?.abort();
    const ac = new AbortController();
    abort.current = ac;
    setRun({ ...IDLE, phase: "receiving", source: "live" });
    try {
      await streamCompare(body, (e) => apply(e, "live"), ac.signal);
      setRun((r) => (r.phase === "receiving" ? { ...r, phase: "error", error: { code: "incomplete", message: "The stream ended before the result was complete." } } : r));
    } catch (err) {
      if (ac.signal.aborted) return;
      setRun((r) => ({ ...r, phase: "error", error: { code: "network", message: (err as Error).message } }));
    }
  }, [apply]);
  const replay = useCallback(async (key: string) => {
    setRun({ ...IDLE, phase: "receiving", source: "replay" });
    const rec = await fetchReplay(key);
    if (!rec) { setRun({ ...IDLE, phase: "error", source: "replay", error: { code: "no-replay", message: "No cached replay is recorded for this pair." } }); return; }
    for (const e of rec.events) apply(e, "replay");
    setRun((r) => ({ ...r, recordedUtc: rec.recordedUtc }));
  }, [apply]);
  const stop = useCallback(() => { abort.current?.abort(); setRun(IDLE); }, []);
  return { run, start, replay, stop };
}

/** Field-level comparison of a finished live run against the sealed benchmark output (decisive candidate). */
export function diffWithSealed(unit: Unit, v: LiveVerdict | null) {
  if (!v) return null;
  const sealedJ = unit.predictions.comparator.judgement ?? "unsure";
  const sealedRows = new Map(unit.comparator.rows.map((r) => [r.field, r.status]));
  const rows: { field: string; sealed: FieldStatus | undefined; live: FieldStatus }[] = [];
  for (const r of v.rows) if (sealedRows.get(r.field as never) !== r.status) rows.push({ field: r.field, sealed: sealedRows.get(r.field as never), live: r.status });
  const verdictDiffers = v.judgement !== sealedJ;
  const pidDiffers = (v.matchedPid ?? null) !== (unit.predictions.comparator.matchedPid ?? null);
  return { same: !verdictDiffers && !pidDiffers && rows.length === 0, verdictDiffers, pidDiffers, rows, sealedJ };
}
