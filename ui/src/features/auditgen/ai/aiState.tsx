import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useAudit } from "../state";
import { ai, replayStore } from "./aiApi";
import type { AiStatus, AiStore } from "./aiTypes";

interface AiCtx {
  status: AiStatus | null;
  store: AiStore;
  model: string | undefined;
  setModel: (m: string | undefined) => void;
  /** Live and a local model is ready: the run buttons are enabled. */
  canRun: boolean;
  /** Run one AI call; ``put`` merges its result into the store. Returns the result or null (error shown). */
  run: <T>(key: string, fn: () => Promise<T>, put: (s: AiStore, r: T) => AiStore) => Promise<T | null>;
  busy: Record<string, boolean>;
  errors: Record<string, string>;
  refreshStatus: () => Promise<void>;
}

const Ctx = createContext<AiCtx | null>(null);

export function AiProvider({ children }: { children: React.ReactNode }) {
  const { mode, pack } = useAudit();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [store, setStore] = useState<AiStore>({ pack_id: "" });
  const [model, setModel] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const refreshStatus = useCallback(async () => {
    if (mode !== "live") { setStatus(null); return; }
    try { setStatus(await ai.status()); } catch (e) { setStatus({ available: false, model: null, pulled: [], reason: (e as Error).message }); }
  }, [mode]);

  useEffect(() => { void refreshStatus(); }, [refreshStatus]);

  useEffect(() => {
    if (!pack || mode === "checking") return;
    let cancelled = false;
    void (async () => {
      let s: AiStore;
      try { s = mode === "live" ? await ai.store(pack.pack_id) : await replayStore(pack.pack_id); } catch { s = { pack_id: pack.pack_id }; }
      if (!cancelled) setStore(s);
    })();
    return () => { cancelled = true; };
  }, [pack, mode]);

  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, put: (s: AiStore, r: T) => AiStore) => {
    setBusy((b) => ({ ...b, [key]: true }));
    setErrors((e) => { const n = { ...e }; delete n[key]; return n; });
    try {
      const r = await fn();
      setStore((s) => put(s, r));
      return r;
    } catch (e) {
      setErrors((x) => ({ ...x, [key]: (e as Error).message }));
      return null;
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  }, []);

  const canRun = mode === "live" && !!status?.available && !!pack;
  const value = useMemo(() => ({ status, store, model, setModel, canRun, run, busy, errors, refreshStatus }),
    [status, store, model, canRun, run, busy, errors, refreshStatus]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAi(): AiCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAi outside AiProvider");
  return c;
}
