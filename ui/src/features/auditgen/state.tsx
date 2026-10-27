import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { backendUp, live, replay } from "./api";
import type { Pack, PackListItem } from "./types";

export type Mode = "checking" | "live" | "replay";

interface Ctx {
  mode: Mode;
  packs: PackListItem[];
  pack: Pack | null;
  error: string | null;
  loading: boolean;
  open: (item: PackListItem | string) => Promise<void>;
  setPack: (p: Pack) => void;
  refreshList: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuditCtx = createContext<Ctx | null>(null);

export function AuditProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("checking");
  const [packs, setPacks] = useState<PackListItem[]>([]);
  const [pack, setPackState] = useState<Pack | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshList = useCallback(async () => {
    try {
      setPacks(mode === "live" ? await live.packs() : mode === "replay" ? await replay.index() : []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [mode]);

  const open = useCallback(async (item: PackListItem | string) => {
    setLoading(true);
    setError(null);
    try {
      if (mode === "live") setPackState(await live.pack(typeof item === "string" ? item : item.pack_id));
      else {
        const it = typeof item === "string" ? (await replay.index()).find((p) => p.pack_id === item) : item;
        if (!it) throw new Error("no such replay pack");
        setPackState(await replay.pack(it));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [mode]);

  const reload = useCallback(async () => { if (pack) await open(pack.pack_id); }, [pack, open]);

  useEffect(() => {
    let cancelled = false;
    void backendUp().then((up) => { if (!cancelled) setMode(up ? "live" : "replay"); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (mode === "checking") return;
    let cancelled = false;
    void (async () => {
      try {
        const list = mode === "live" ? await live.packs() : await replay.index();
        if (cancelled) return;
        setPacks(list);
        if (!pack && list.length) await open(list.find((p) => p.kind !== "run") ?? list[0]);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load the list once per mode
  }, [mode]);

  const value = useMemo(() => ({ mode, packs, pack, error, loading, open, setPack: setPackState, refreshList, reload }),
    [mode, packs, pack, error, loading, open, refreshList, reload]);
  return <AuditCtx.Provider value={value}>{children}</AuditCtx.Provider>;
}

export function useAudit(): Ctx {
  const c = useContext(AuditCtx);
  if (!c) throw new Error("useAudit outside AuditProvider");
  return c;
}
