/**
 * Audit generator client. Live mode talks to the local backend (127.0.0.1:8765 through the Vite proxy, /api/auditgen)
 * or, on the public site, to the hosted service (VITE_AUDIT_API, ui/api_audit/). Without either, the pages fall back to
 * offline replay of the sample packs (one per entity class) in /auditgen/.
 */
import { AUDIT_API } from "@/lib/env";
import type { Pack, PackListItem, Profile, ReviewStatus, Section } from "./types";

/** The public site's hosted service: same routes as the local backend, minus uploads, corpus refresh and full text. */
export const HOSTED = import.meta.env.VITE_NO_PROXY === "1" && !!import.meta.env.VITE_AUDIT_API;

// Written on import.meta.env directly so the build folds it: a public build never contains the local backend's path.
export const API = import.meta.env.VITE_NO_PROXY === "1" ? (import.meta.env.VITE_AUDIT_API ? `${AUDIT_API}/api/auditgen` : "/no-backend") : "/api/auditgen";

export async function backendUp(timeoutMs = 1500): Promise<boolean> {
  if (HOSTED) return hosted.ready().then(() => true, () => false);
  if (import.meta.env.VITE_NO_PROXY === "1") return false;
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Hosted service transport. Azure's front end sometimes routes a request to a dead backend and answers 503 only after
 * 60 s, so every request is kept short and retried, and slow work (generate, exports, AI) runs as a background job on
 * the service that is polled until done. Retrying is safe: a request that hit the dead backend never reached the app.
 */
export const hosted = {
  readyAt: 0,
  async fetch(url: string, init: RequestInit = {}, timeoutMs = 12000, tries = 8): Promise<Response> {
    for (let i = 0; i < tries; i++) {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), timeoutMs);
      try {
        const r = await fetch(url, { ...init, signal: ctl.signal });
        clearTimeout(t);
        if (![502, 503, 504].includes(r.status)) return r;
      } catch { clearTimeout(t); }
      await sleep(300 * (i + 1));
    }
    throw new Error("The hosted service did not answer. Please try again in a minute.");
  },
  /** Waits until the service has loaded the corpus and models (a cold start takes about a minute). */
  async ready(): Promise<void> {
    if (Date.now() - hosted.readyAt < 60_000) return;
    for (let i = 0; i < 40; i++) {
      const j = (await (await hosted.fetch(`${API}/health`, {}, 8000)).json()) as { ok?: boolean; mode?: string; ready?: boolean };
      if (j.ok !== true || j.mode !== "hosted") throw new Error("not the hosted audit service");
      if (j.ready) { hosted.readyAt = Date.now(); return; }
      await sleep(3000);
    }
    throw new Error("The hosted service is still starting. Please try again in a minute.");
  },
  async get<T>(path: string, timeoutMs = 20000): Promise<T> {
    await hosted.ready();
    return json<T>(await hosted.fetch(`${API}${path}`, {}, timeoutMs));
  },
  /** Runs one route as a background job and returns the job id once it has finished. */
  async run(method: "GET" | "POST", path: string, body?: unknown): Promise<string> {
    await hosted.ready();
    const { job } = await json<{ job: string }>(await hosted.fetch(`${API}/jobs/start`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ method, path, body }),
    }, 15000));
    for (let i = 0; i < 400; i++) {
      await sleep(i < 5 ? 800 : 1500);
      const st = await json<{ status: string; error?: { detail: string } }>(await hosted.fetch(`${API}/jobs/${job}`, {}, 10000));
      if (st.status === "error") throw new Error(st.error?.detail ?? "failed");
      if (st.status === "done") return job;
    }
    throw new Error("This is taking too long. Please try again.");
  },
  async call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const job = await hosted.run(method, path, body);
    return json<T>(await hosted.fetch(`${API}/jobs/${job}/result`, {}, 30000));
  },
  /** Saves a file built by a job (or a quick GET) through a blob link. */
  async download(path: string, viaJob: boolean): Promise<void> {
    const url = viaJob ? `${API}/jobs/${await hosted.run("GET", path)}/file` : (await hosted.ready(), `${API}${path}`);
    const r = await hosted.fetch(url, {}, 30000);
    if (!r.ok) await json(r);
    const name = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? path.split("/").pop()!;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 30_000);
  },
};

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = ((await r.json()) as { detail?: string }).detail ?? msg; } catch { /* keep status */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

const local = {
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

const pid = (id: string) => `/packs/${encodeURIComponent(id)}`;

/** The live client: the local backend, or the hosted service through ``hosted`` (same routes, same results). */
export const live: typeof local = HOSTED ? {
  ...local,
  vocab: () => hosted.get("/vocab"),
  packs: () => hosted.get("/packs"),
  pack: (id) => hosted.get(pid(id), 40000),
  generate: (p) => hosted.call("POST", "generate", p),
  review: (id, updates) => hosted.call("POST", `${pid(id)}/review`.slice(1), updates),
  signoff: (id, signer) => hosted.call("POST", `${pid(id)}/signoff`.slice(1), { signer }),
} : local;

/** Downloads one export: a link to the local backend, or a file built by a hosted job. */
export async function downloadExport(id: string, fmt: "xlsx" | "docx" | "pdf" | "ics" | "json"): Promise<void> {
  await hosted.download(`${pid(id)}/export/${fmt}`.slice(1), true);
}

/** Packs this browser generated on the hosted service (the service lists only the samples; packs are kept 7 days). */
const MINE = "auditgen.hosted.mine";
export const mine = {
  list: (): PackListItem[] => { try { return JSON.parse(localStorage.getItem(MINE) ?? "[]") as PackListItem[]; } catch { return []; } },
  add: (p: Pack) => {
    const item: PackListItem = { pack_id: p.pack_id, kind: "run", created_utc: p.created_utc, profile: p.profile, summary: p.summary, signed_off: !!p.signoff };
    try { localStorage.setItem(MINE, JSON.stringify([item, ...mine.list().filter((x) => x.pack_id !== p.pack_id)].slice(0, 20))); } catch { /* storage blocked */ }
  },
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
