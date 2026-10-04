import { useEffect, useMemo, useState } from "react";
import type { CasesIndex, Home, Shard, Unit } from "./types";

// Per-route JSON shards (public/data/*.json). Each file is fetched once and cached for the session.
const cache = new Map<string, Promise<unknown>>();

export function dataUrl(name: string) {
  return `${import.meta.env.BASE_URL}data/${name}`;
}

export function fetchJson<T>(name: string): Promise<T> {
  let p = cache.get(name);
  if (!p) {
    p = fetch(dataUrl(name)).then((r) => {
      if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
      return r.json();
    });
    p.catch(() => cache.delete(name));
    cache.set(name, p);
  }
  return p as Promise<T>;
}

export type Loaded<T> = { data: T | null; error: string | null };

export function useJson<T>(name: string | null): Loaded<T> {
  const [state, set] = useState<Loaded<T> & { name: string | null }>({ data: null, error: null, name: null });
  useEffect(() => {
    if (!name) return;
    let live = true;
    fetchJson<T>(name).then((data) => live && set({ data, error: null, name }), (e: Error) => live && set({ data: null, error: e.message, name }));
    return () => { live = false; };
  }, [name]);
  return state.name === name ? state : { data: null, error: null };
}

export const shardName = (itemId: string) => itemId.replace("::", "__");
export const itemOf = (unitId: string) => unitId.split("|")[0];

export function useIndex() { return useJson<CasesIndex>("cases/index.json"); }
export function useHome() { return useJson<Home>("home.json"); }

export function useCase(unitId: string | null): Loaded<{ shard: Shard; unit: Unit }> {
  const s = useJson<Shard>(unitId ? `cases/${shardName(itemOf(unitId))}.json` : null);
  // Stable identity across renders (callers use it in effect dependencies).
  return useMemo(() => {
    if (!s.data) return { data: null, error: s.error };
    const unit = s.data.units.find((u) => u.id === unitId);
    return unit ? { data: { shard: s.data, unit }, error: null } : { data: null, error: `Unknown case ${unitId}` };
  }, [s.data, s.error, unitId]);
}

export const caseHref = (unitId: string, system?: string) => `/case/${encodeURIComponent(unitId)}${system ? `?system=${system}` : ""}`;
