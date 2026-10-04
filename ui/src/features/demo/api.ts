import { useEffect, useState } from "react";
import { API_BASE, NO_PROXY } from "@/lib/env";
import type { Band, FieldStatus, Judgement, RuleStep } from "./types";

/** Client for the comparator API (Phase H). The key never reaches the browser; the API reports what it can do via /api/health. */
export interface Health {
  ok: boolean;
  model: { id: string; available: boolean; reason?: string };
  hashes: { verified: boolean; prompt?: string; rule?: string; mismatches?: string[] };
  cache: { reachable: boolean; replays: number };
  mode: "public" | "presenter";
  streaming: "incremental" | "buffered";
  rehydrate: boolean;
}

export type ApiState = { status: "offline" | "checking" | "ready"; health: Health | null; reason?: string };

let healthPromise: Promise<Health> | null = null;
export function getHealth(force = false): Promise<Health> {
  if (API_BASE == null) return Promise.reject(new Error("No comparator API is configured for this build."));
  if (!healthPromise || force) {
    healthPromise = fetch(`${API_BASE}/api/health`, { cache: "no-store" }).then(async (r) => {
      if (!r.ok) throw new Error(`health HTTP ${r.status}`);
      return (await r.json()) as Health;
    });
    healthPromise.catch(() => { healthPromise = null; });
  }
  return healthPromise;
}

export function useApi(): ApiState {
  const [s, set] = useState<ApiState>(API_BASE == null ? { status: "offline", health: null, reason: "This public build has no comparator API." } : { status: "checking", health: null });
  useEffect(() => {
    if (API_BASE == null) return;
    let live = true;
    getHealth().then((h) => live && set({ status: "ready", health: h }), (e: Error) => live && set({ status: "offline", health: null, reason: e.message }));
    return () => { live = false; };
  }, []);
  return s;
}

/** Live model usable right now (key present, hashes verified). Otherwise the UI is replay-only. */
export const liveAvailable = (s: ApiState) => s.status === "ready" && !!s.health?.model.available && !!s.health?.hashes.verified;
export const presenter = (s: ApiState) => s.status === "ready" && s.health?.mode === "presenter" && !!s.health?.rehydrate;

/** Full RBI text exists only in local / presenter builds; public builds compile this path away (check_dist enforces it). */
const REHYDRATE: string | null = NO_PROXY ? null : "/api/rehydrate/";
const textCache = new Map<string, Promise<string | null>>();
export function useFullText(pid: string | null | undefined, enabled: boolean): string | null {
  const [t, set] = useState<{ pid: string; text: string | null } | null>(null);
  useEffect(() => {
    if (!pid || !enabled || API_BASE == null || REHYDRATE == null) return;
    let p = textCache.get(pid);
    if (!p) {
      p = fetch(`${API_BASE}${REHYDRATE}${encodeURIComponent(pid)}`).then(async (r) => (r.ok ? ((await r.json()) as { text: string }).text : null), () => null);
      textCache.set(pid, p);
    }
    let live = true;
    void p.then((text) => live && set({ pid, text }));
    return () => { live = false; };
  }, [pid, enabled]);
  return t && t.pid === pid ? t.text : null;
}

// ---- /api/compare (SSE over fetch) ----------------------------------------------------------------------------------

export interface LiveField { path: string; candidate?: string; field: string; kind: "source" | "target" | "comparison" | "same_duty"; value: string | boolean | null }
export interface LiveVerdict { judgement: Judgement | "unsure"; matchedPid: string | null; trace: RuleStep[]; rows: { field: string; status: FieldStatus }[]; perCandidate: { pid: string; verdict: string }[] }
export interface LiveDone { cacheKey: string; latencyMs: number; inputTokens: number | null; outputTokens: number | null; recordedUtc: string; replay: boolean }
export interface LiveConfidence { p: number | null; band: Band }

export type CompareEvent =
  | { type: "status"; data: { message: string; streaming?: "incremental" | "buffered" } }
  | { type: "field"; data: LiveField }
  | { type: "verdict"; data: LiveVerdict }
  | { type: "confidence"; data: LiveConfidence }
  | { type: "done"; data: LiveDone }
  | { type: "error"; data: { code: string; message: string; replayKey?: string | null } };

export type CompareBody =
  | { mode: "benchmark"; unitId: string }
  | { mode: "edit"; unitId: string; edits: { kind: string; from: string; to: string }[] }
  | { mode: "paste"; textA: string; textB: string; classA: string; classB: string };

export async function streamCompare(body: CompareBody, onEvent: (e: CompareEvent) => void, signal?: AbortSignal): Promise<void> {
  if (API_BASE == null) throw new Error("No comparator API is configured for this build.");
  const r = await fetch(`${API_BASE}/api/compare`, { method: "POST", headers: { "content-type": "application/json", accept: "text/event-stream" }, body: JSON.stringify(body), signal });
  if (!r.ok || !r.body) {
    let msg = `HTTP ${r.status}`;
    try { const j = (await r.json()) as { message?: string; replayKey?: string }; msg = j.message ?? msg; onEvent({ type: "error", data: { code: String(r.status), message: msg, replayKey: j.replayKey ?? null } }); return; } catch { /* not JSON */ }
    onEvent({ type: "error", data: { code: String(r.status), message: msg } });
    return;
  }
  await readSse(r.body, onEvent);
}

export async function readSse(stream: ReadableStream<Uint8Array>, onEvent: (e: CompareEvent) => void) {
  const reader = stream.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = /^event: (.+)$/m.exec(block)?.[1];
      const data = block.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
      if (ev && data) onEvent({ type: ev, data: JSON.parse(data) } as CompareEvent);
    }
  }
}

export async function fetchReplay(key: string): Promise<{ events: CompareEvent[]; recordedUtc: string } | null> {
  if (API_BASE == null) return null;
  const r = await fetch(`${API_BASE}/api/replay/${encodeURIComponent(key)}`);
  return r.ok ? ((await r.json()) as { events: CompareEvent[]; recordedUtc: string }) : null;
}

export type Freshness = { outcome: "match" | "differs" | "unverified"; harvestDate: string | null; detail?: string; checkedUtc: string };
export async function checkFreshness(pid: string): Promise<Freshness> {
  if (API_BASE == null) return { outcome: "unverified", harvestDate: null, detail: "No API in this build.", checkedUtc: new Date().toISOString() };
  const r = await fetch(`${API_BASE}/api/freshness/${encodeURIComponent(pid)}`);
  if (!r.ok) return { outcome: "unverified", harvestDate: null, detail: `HTTP ${r.status}`, checkedUtc: new Date().toISOString() };
  return (await r.json()) as Freshness;
}
