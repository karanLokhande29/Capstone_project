/**
 * Audit generator client. Live mode talks to the local backend (127.0.0.1:8765 through the Vite proxy, /api/auditgen).
 * When the backend is not running, the pages fall back to offline replay of the three sample packs in /auditgen/.
 */
import type { Pack, PackListItem, Profile, ReviewStatus, Section } from "./types";

export const API = "/api/auditgen";

export async function backendUp(timeoutMs = 1500): Promise<boolean> {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), timeoutMs);
    const r = await fetch(`${API}/health`, { signal: ctl.signal });
    clearTimeout(t);
    if (!r.ok) return false;
    const j = (await r.json()) as { ok?: boolean; remote_api_calls?: boolean };
    return j.ok === true && j.remote_api_calls === false;
  } catch {
    return false;
  }
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = ((await r.json()) as { detail?: string }).detail ?? msg; } catch { /* keep status */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

export const live = {
  vocab: async () => json<{ classes: string[]; activities: { id: string; label: string }[]; subject_families: string[] }>(await fetch(`${API}/vocab`)),
  packs: async () => json<PackListItem[]>(await fetch(`${API}/packs`)),
  pack: async (id: string) => json<Pack>(await fetch(`${API}/packs/${encodeURIComponent(id)}`)),
  generate: async (p: Profile) => json<Pack>(await fetch(`${API}/generate`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(p) })),
  review: async (id: string, updates: { section: Section; row_id: string; review_status: ReviewStatus; reviewer: string; note: string }[]) =>
    json<{ updated: number }>(await fetch(`${API}/packs/${encodeURIComponent(id)}/review`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(updates) })),
  signoff: async (id: string, signer: string, workbook?: File) => {
    const fd = new FormData();
    fd.append("signer", signer);
    if (workbook) fd.append("workbook", workbook);
    return json<{ pack_id: string }>(await fetch(`${API}/packs/${encodeURIComponent(id)}/signoff`, { method: "POST", body: fd }));
  },
  gaps: async (id: string, files: File[], families: string[], explain: boolean) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("families", families.join("|"));
    fd.append("explain", String(explain));
    return json<{ session: string; counts: Record<string, number> }>(await fetch(`${API}/packs/${encodeURIComponent(id)}/gaps`, { method: "POST", body: fd }));
  },
  deleteUpload: async (session: string, packId: string, clear: boolean) =>
    json<{ deleted: boolean }>(await fetch(`${API}/uploads/${session}?pack_id=${encodeURIComponent(packId)}&clear_results=${clear}`, { method: "DELETE" })),
  fulltext: async (pid: string) => json<{ text: string; label: string; source_url: string }>(await fetch(`${API}/fulltext/${encodeURIComponent(pid)}`)),
  freshness: async () => json<{ snapshot_date: string; age_days: number | null; warn: boolean; message: string; sha256: string; kind: string; directions: number; paragraphs: number }>(await fetch(`${API}/freshness`)),
  dryRun: async () => json<Record<string, unknown>>(await fetch(`${API}/refresh/dry-run`, { method: "POST" })),
  llm: async () => json<{ available: boolean; reason?: string; model?: string }>(await fetch(`${API}/llm`)),
  exportUrl: (id: string, fmt: "xlsx" | "docx" | "pdf" | "ics" | "json") => `${API}/packs/${encodeURIComponent(id)}/export/${fmt}`,
};

/** Offline replay: the sample packs written by `python3 scripts/auditgen.py samples` into ui/public/auditgen/. */
export const replay = {
  index: async () => {
    const r = await fetch("/auditgen/index.json");
    if (!r.ok) throw new Error("No replay packs: run `python3 scripts/auditgen.py samples`.");
    return ((await r.json()) as { packs: PackListItem[] }).packs;
  },
  pack: async (item: PackListItem): Promise<Pack> => {
    const r = await fetch(`/auditgen/${item.file}`);
    if (!r.ok) throw new Error(`replay pack ${item.pack_id} is missing`);
    const buf = new Uint8Array(await r.arrayBuffer());
    // The server may already have decoded a gzip Content-Encoding; only gunzip when the gzip magic bytes are present.
    if (buf[0] === 0x1f && buf[1] === 0x8b) {
      const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
      return JSON.parse(await new Response(stream).text()) as Pack;
    }
    return JSON.parse(new TextDecoder().decode(buf)) as Pack;
  },
};
