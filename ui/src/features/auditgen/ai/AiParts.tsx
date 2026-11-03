import { useMemo, useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, Sparkles, XCircle } from "lucide-react";
import { Badge, Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { useAudit } from "../state";
import { useAi } from "./aiState";
import type { AiBase, AiSentence, AiSource } from "./aiTypes";
import { PUBLIC_DEMO } from "../parts";

export function AiBadge() {
  return <Badge tone="product"><Sparkles size={11} />AI draft · needs review</Badge>;
}

export function SourceChip({ s }: { s: AiSource }) {
  return (
    <a href={s.source_url} target="_blank" rel="noreferrer" title={s.direction_title}
      className="inline-flex items-center gap-1 rounded border border-line bg-panel-2 px-1.5 py-0.5 text-[11px] text-accent hover:underline"
      aria-label={`RBI source for ${s.paragraph_id ?? s.row_id}`}>
      {s.label && <b>{s.label}</b>}{s.paragraph_id ?? s.row_id}<ExternalLink size={10} />
    </a>
  );
}

/** Verified sentences are shown; unverified ones are hidden behind a toggle, struck through and labelled. */
export function Sentences({ items, empty, render }: { items: AiSentence[]; empty?: string; render?: (s: AiSentence) => React.ReactNode }) {
  const [show, setShow] = useState(false);
  const ok = items.filter((s) => s.verified);
  const bad = items.filter((s) => !s.verified);
  return (
    <div className="space-y-1.5">
      {ok.length === 0 && <p className="text-[12.5px] text-ink-3">{empty ?? "No verified sentence."}</p>}
      <ul className="space-y-1.5">
        {ok.map((s, i) => (
          <li key={i} className="flex items-start gap-1.5 text-[13px]">
            <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-pos" aria-label="verified" />
            <span className="min-w-0">{render ? render(s) : s.text}
              {s.sources && s.sources.length > 0 && <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">{s.sources.map((c, k) => <SourceChip key={k} s={c} />)}</span>}
              {s.facts && s.facts.length > 0 && <span className="ml-1 text-[11px] text-ink-3">[{s.facts.join(", ")}]</span>}
            </span>
          </li>
        ))}
      </ul>
      {bad.length > 0 && (
        <div className="text-[12px]">
          <button className="text-ink-3 hover:text-ink" onClick={() => setShow(!show)}>
            {show ? "Hide" : "Show"} {bad.length} unverified sentence{bad.length > 1 ? "s" : ""} (not supported by the cited text)
          </button>
          {show && (
            <ul className="mt-1 space-y-1 rounded-md border border-neg/30 bg-neg-soft/40 p-2">
              {bad.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-ink-3">
                  <XCircle size={13} className="mt-0.5 shrink-0 text-neg" aria-label="unverified" />
                  <span><span className="line-through">{s.text}</span> <span className="text-neg">· {s.reason || "unverified"}</span></span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function Meta({ r }: { r: AiBase }) {
  return (
    <p className="mt-2 text-[11px] text-ink-3">
      {r.model ? <>model <code>{r.model}</code> · </> : null}{r.seconds}s · verifier <code>{r.verifier}</code> · {r.created_utc.replace("T", " ").slice(0, 16)} UTC
    </p>
  );
}

export function RunButton({ k, onClick, children, disabled }: { k: string; onClick: () => void; children: React.ReactNode; disabled?: boolean }) {
  const { canRun, busy } = useAi();
  const { mode } = useAudit();
  return (
    <Button type="button" size="sm" variant="product" disabled={!canRun || busy[k] || disabled} onClick={onClick}
      title={mode !== "live" ? (PUBLIC_DEMO ? "Runs in the installed version; this demo shows recorded outputs" : "Needs the local backend (offline replay shows recorded outputs)") : !canRun ? "No model available" : undefined}>
      {busy[k] ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}{busy[k] ? "Thinking locally…" : children}
    </Button>
  );
}

export function Err({ k }: { k: string }) {
  const { errors } = useAi();
  return errors[k] ? <p className="text-[12px] text-neg">{errors[k]}</p> : null;
}

/** A searchable list of pack rows; the caller renders each row's label. */
export function RowPicker<T extends { row_id: string }>({ rows, text, label, value, onPick, marks, limit = 40 }: {
  rows: T[]; text: (r: T) => string; label: string; value: string | null; onPick: (r: T) => void; marks?: Record<string, unknown>; limit?: number;
}) {
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const s = q.toLowerCase().trim();
    return (s ? rows.filter((r) => text(r).toLowerCase().includes(s)) : rows).slice(0, limit);
  }, [rows, q, text, limit]);
  return (
    <div className="min-w-0">
      <input aria-label={`Search ${label}`} placeholder={`Search ${rows.length.toLocaleString()} ${label}…`} value={q} onChange={(e) => setQ(e.target.value)}
        className="mb-1.5 h-7 w-full rounded-md border border-line bg-panel px-2 text-[12.5px]" />
      <ul className="max-h-[420px] overflow-y-auto rounded-md border border-line bg-panel" aria-label={label}>
        {shown.map((r) => (
          <li key={r.row_id}>
            <button onClick={() => onPick(r)} className={cn("w-full border-b border-line px-2 py-1.5 text-left text-[12px] hover:bg-panel-2",
              value === r.row_id && "bg-accent-soft")}>
              {marks?.[r.row_id] ? <Sparkles size={11} className="mr-1 inline text-product" aria-label="has AI output" /> : null}{text(r)}
            </button>
          </li>
        ))}
        {shown.length === 0 && <li className="px-2 py-3 text-center text-[12px] text-ink-3">No rows.</li>}
      </ul>
    </div>
  );
}
