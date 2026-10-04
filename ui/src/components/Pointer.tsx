import { ExternalLink } from "lucide-react";
import { useData } from "@/data/store";
import { Tip } from "./ui/primitives";

/** A paragraph pointer: id, ≤ 25-word excerpt, URL, harvest date, sha256. Full text only via release/rehydrate.py. */
export function Pointer({ pid, label }: { pid: string; label?: string }) {
  const p = useData((s) => s.snapshot?.pointers[pid]);
  return (
    <div className="mt-1 text-[12px]">
      {label && <span className="text-[11px] text-ink-3">{label}: </span>}
      <Tip content={<span className="block max-w-xs">
        <span className="block">{pid}{p?.clausePath ? ` · clause ${p.clausePath}` : ""}</span>
        <span className="block text-ink-3">harvested {p?.harvestDate ?? "—"}</span>
        <span className="block break-all font-mono text-[10px] text-ink-3">sha256 {p?.sha256 ?? "—"}</span>
        <span className="mt-1 block text-ink-3">Full text: python3 release/rehydrate.py (local only; never bundled)</span>
      </span>}>
        <code className="cursor-help text-accent">{pid}</code>
      </Tip>
      {p?.url && <a href={p.url} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center text-ink-3 hover:text-accent" aria-label="Open RBI source"><ExternalLink size={11} /></a>}
      {p?.excerpt && <p className="mt-0.5 text-ink-2">“{p.excerpt}”</p>}
    </div>
  );
}
