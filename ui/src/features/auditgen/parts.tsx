import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge, Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { NO_PROXY } from "@/lib/env";
import { live } from "./api";
import { useAudit } from "./state";
import type { Cited } from "./types";

export const DISCLAIMER = "Decision support only; verify against the official RBI text; not legal advice.";

/** Public site: a read-only demo of the sample packs. Generating, uploading, reviewing and the local model run in the installed version. */
export const PUBLIC_DEMO = NO_PROXY;
export const INSTALLED = "the installed version, which runs inside your own network";

export function SourceLink({ row }: { row: Pick<Cited, "source_url" | "md_id" | "paragraph_id"> }) {
  return (
    <a href={row.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline"
      aria-label={`RBI source for ${row.paragraph_id ?? (row.md_id || "the press release")}`}>
      {row.paragraph_id ?? (row.md_id ? `${row.md_id} (Direction)` : "RBI press release")}<ExternalLink size={11} />
    </a>
  );
}

export function ReviewBadge({ row }: { row: Pick<Cited, "needs_review" | "review_status"> }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {row.needs_review && row.review_status === "unreviewed" && <Badge tone="warn">needs human review</Badge>}
      {row.review_status === "confirmed" && <Badge tone="pos">confirmed</Badge>}
      {row.review_status === "disputed" && <Badge tone="neg">disputed</Badge>}
      {row.review_status === "not applicable" && <Badge tone="outline">not applicable</Badge>}
    </span>
  );
}

export function Conf({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-ink-3">–</span>;
  return <span className={cn("num", v < 0.7 ? "text-warn" : "text-ink-2")}>{v.toFixed(2)}</span>;
}

/** The ≤ 25-word excerpt, plus a "full text" toggle that reads the local corpus at runtime (live mode only). */
export function Excerpt({ text, pid }: { text?: string; pid: string | null }) {
  const { mode } = useAudit();
  const [full, setFull] = useState<{ text: string; label: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="min-w-0">
      <p className="text-[12.5px] text-ink">{text}</p>
      {pid && mode === "live" && !full && (
        <button className="text-[11px] text-accent hover:underline" onClick={async () => {
          try { setFull(await live.fulltext(pid)); } catch (e) { setErr((e as Error).message); }
        }}>full text</button>
      )}
      {full && (
        <div className="mt-1 rounded border border-line bg-panel-2 p-2 text-[12px]">
          <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-warn">{full.label}</p>
          <p className="whitespace-pre-wrap">{full.text}</p>
          <button className="mt-1 text-[11px] text-accent" onClick={() => setFull(null)}>hide</button>
        </div>
      )}
      {err && <p className="text-[11px] text-neg">{err}</p>}
    </div>
  );
}

export interface Col<T> { key: string; label: string; render: (r: T) => React.ReactNode; className?: string }

/** A paged, filterable table. Every row type the audit pack holds carries its citation. */
export function RowTable<T extends { row_id: string }>({ rows, cols, pageSize = 50, filterText, label }: {
  rows: T[]; cols: Col<T>[]; pageSize?: number; filterText?: (r: T) => string; label: string;
}) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const shown = useMemo(() => {
    if (!q || !filterText) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) => filterText(r).toLowerCase().includes(s));
  }, [rows, q, filterText]);
  const pages = Math.max(1, Math.ceil(shown.length / pageSize));
  const cur = shown.slice(page * pageSize, page * pageSize + pageSize);
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
        {filterText && (
          <input aria-label={`Filter ${label}`} placeholder="Filter…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }}
            className="h-7 w-64 rounded-md border border-line bg-panel px-2" />
        )}
        <span className="text-ink-3 num">{shown.length.toLocaleString()} rows</span>
        <span className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</Button>
          <span className="num text-ink-3">{page + 1} / {pages}</span>
          <Button size="sm" variant="outline" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</Button>
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-panel">
        <table className="w-full text-left text-[12.5px]" aria-label={label}>
          <thead className="bg-panel-2 text-[11.5px] text-ink-3">
            <tr>{cols.map((c) => <th key={c.key} className={cn("px-2 py-1.5 font-medium", c.className)}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {cur.map((r) => (
              <tr key={r.row_id} className="border-t border-line align-top">
                {cols.map((c) => <td key={c.key} className={cn("px-2 py-1.5", c.className)}>{c.render(r)}</td>)}
              </tr>
            ))}
            {cur.length === 0 && <tr><td colSpan={cols.length} className="px-2 py-4 text-center text-ink-3">No rows.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "warn" | "neg" | "pos" }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-3 py-2">
      <p className="text-[11px] text-ink-3">{label}</p>
      <p className={cn("num text-[18px] font-semibold", tone === "warn" && "text-warn", tone === "neg" && "text-neg", tone === "pos" && "text-pos")}>{value}</p>
    </div>
  );
}
