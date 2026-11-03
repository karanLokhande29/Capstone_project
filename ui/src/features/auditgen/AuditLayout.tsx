import { NavLink, Outlet } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { AuditProvider, useAudit } from "./state";
import { HOSTED } from "./api";
import { DISCLAIMER, PUBLIC_DEMO } from "./parts";

const TABS = [
  { to: "/auditgen", label: "Audit pack", end: true },
  { to: "/auditgen/gaps", label: "Policy gaps" },
  { to: "/auditgen/review", label: "Review" },
  { to: "/auditgen/downloads", label: "Downloads" },
  { to: "/auditgen/corpus", label: "Corpus status" },
  { to: "/auditgen/ai", label: "✦ AI assistant" },
];

function Bar() {
  const { mode, packs, pack, open, loading, error } = useAudit();
  return (
    <div className="mb-4 space-y-2">
      <div role="note" aria-label="Disclaimer" className="flex items-start gap-2 rounded-lg border border-warn/40 bg-warn-soft px-3 py-2 text-[12.5px] text-warn">
        <ShieldAlert size={15} className="mt-0.5 shrink-0" />
        <span><b>{DISCLAIMER}</b> {HOSTED
          ? "Hosted version: generate, review and export a pack for your entity; packs are kept for 7 days. RBI quotes are cut to 12 words and link to the official PDF. Policy uploads are only in the installed version, which runs inside your own network."
          : PUBLIC_DEMO
          ? "Read-only demo with a sample pack for each of the 11 regulated-entity types; RBI quotes are cut to 12 words and link to the official PDF. The full tool runs inside your own network, so uploaded policies never leave it."
          : "Runs locally; no API calls; uploaded policies never leave this machine."}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
        {mode === "checking" && <Badge tone="neutral">{HOSTED ? "connecting to the hosted service (first visit can take ~30 s)…" : PUBLIC_DEMO ? "loading…" : "checking for the local backend…"}</Badge>}
        {mode === "live" && <Badge tone="pos">{HOSTED ? "live · hosted service" : "live · local backend 127.0.0.1:8765"}</Badge>}
        {mode === "replay" && <Badge tone="warn">{PUBLIC_DEMO ? "read-only demo · sample packs" : "offline replay · sample packs (start the backend for live mode)"}</Badge>}
        {packs.length > 0 && (
          <label className="flex items-center gap-1.5">
            <span className="text-ink-3">Pack</span>
            <select aria-label="Select pack" className="h-7 rounded-md border border-line bg-panel px-2" value={pack?.pack_id ?? ""}
              onChange={(e) => { const it = packs.find((p) => p.pack_id === e.target.value); if (it) void open(it); }}>
              {pack && !packs.some((p) => p.pack_id === pack.pack_id) && <option value={pack.pack_id}>{pack.pack_id}</option>}
              {packs.map((p) => <option key={p.pack_id} value={p.pack_id}>{p.profile.name} · {p.profile.as_of}{p.kind === "sample" ? " (sample)" : HOSTED && p.kind === "run" ? " (yours)" : ""}{p.signed_off ? " · signed off" : ""}</option>)}
            </select>
          </label>
        )}
        {loading && <span className="text-ink-3">loading…</span>}
        {error && <span className="text-neg">{error}</span>}
      </div>
      <nav aria-label="Audit generator" className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => cn("-mb-px border-b-2 border-transparent px-2.5 py-1.5 text-[13px] text-ink-3 hover:text-ink",
            isActive && "border-accent text-ink")}>{t.label}</NavLink>
        ))}
      </nav>
    </div>
  );
}

export default function AuditLayout() {
  return (
    <AuditProvider>
      <Bar />
      <Outlet />
      <p className="mt-6 border-t border-line pt-2 text-[11.5px] text-ink-3">{DISCLAIMER}</p>
    </AuditProvider>
  );
}
