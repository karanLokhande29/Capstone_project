import { useMemo } from "react";
import { Button, Card, CardBody } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { StatusBadge } from "../badges";
import { VerdictPill } from "../case/parts";
import { FIELD_LABEL, FIELD_ORDER, STATUS_LABEL, VERDICT } from "../names";
import type { Unit } from "../types";
import { diffWithSealed, type LiveRun } from "./live";

export function SealedPanel({ unit }: { unit: Unit }) {
  return (
    <Card><CardBody className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold">Sealed output</p><StatusBadge status="sealed" /></div>
      <p className="flex items-center gap-2 text-[13.5px]">Verdict <VerdictPill j={unit.predictions.comparator.judgement ?? "abstain"} /></p>
      <RowsTable rows={unit.comparator.rows.map((r) => ({ field: r.field, status: r.status }))} />
    </CardBody></Card>
  );
}

function RowsTable({ rows, pending }: { rows: { field: string; status: string | null }[]; pending?: boolean }) {
  return (
    <table className="w-full text-[12.5px]">
      <tbody>{FIELD_ORDER.map((f) => {
        const r = rows.find((x) => x.field === f);
        return <tr key={f} className="border-t border-line"><td className="py-1 pr-2 text-ink-2">{FIELD_LABEL[f]}</td><td className={cn("py-1 text-right", r?.status && r.status !== "equal" && r.status !== "absent" && "font-medium text-warn")}>{r?.status ? STATUS_LABEL[r.status as "equal"] : pending ? "" : "—"}</td></tr>;
      })}</tbody>
    </table>
  );
}

export function LivePanel({ run, unit, unvalidated }: { run: LiveRun; unit?: Unit; unvalidated?: boolean }) {
  const diff = unit && run.phase === "done" ? diffWithSealed(unit, run.verdict) : null;
  const decisive = run.verdict?.matchedPid ?? null;
  const rows = useMemo(() => {
    if (run.verdict) return run.verdict.rows;
    // Before the verdict: the most recent candidate whose comparisons have parsed so far.
    const comps = run.fields.filter((f) => f.kind === "comparison");
    const cand = comps.length ? comps[comps.length - 1].candidate : null;
    return comps.filter((f) => f.candidate === cand).map((f) => ({ field: f.field, status: f.value as string }));
  }, [run.fields, run.verdict]);
  return (
    <Card><CardBody className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{run.source === "replay" ? "Replayed run" : "Live run"}</p>
        <span className="flex flex-wrap gap-1">
          {run.source === "live" && <StatusBadge status="live" />}
          {run.source === "replay" && <StatusBadge status="replay" detail={run.recordedUtc ? `recorded ${run.recordedUtc.slice(0, 16).replace("T", " ")} UTC` : undefined} />}
          {unvalidated && <StatusBadge status="unvalidated" />}
          {diff && !diff.same && <StatusBadge status="mismatch" />}
        </span>
      </div>
      {run.phase === "idle" && <p className="text-[13.5px] text-ink-3">Not run yet.</p>}
      {run.phase === "receiving" && rows.length === 0 && <p className="text-[13.5px] text-ink-2" role="status">Receiving structured output…</p>}
      {(rows.length > 0 || run.verdict) && (
        <>
          {run.verdict && <p className="flex items-center gap-2 text-[13.5px]">Verdict <VerdictPill j={run.verdict.judgement === "unsure" ? "abstain" : run.verdict.judgement} />{decisive && <span className="font-mono text-[11px] text-ink-3">{decisive}</span>}</p>}
          <RowsTable rows={rows} pending={run.phase === "receiving"} />
          {run.phase === "receiving" && <p className="text-[12px] text-ink-3" role="status">{run.streaming === "buffered" ? "Receiving structured output…" : "Fields appear as each one is fully parsed from the model's response."}</p>}
        </>
      )}
      {run.confidence && <p className="text-[12.5px] text-ink-2">Confidence (M2, post-paper): {run.verdict?.judgement === "different" ? "Flagged for review" : run.confidence.band}{run.confidence.p != null ? ` · p = ${run.confidence.p.toFixed(3)}` : ""}</p>}
      {diff && (diff.same ? <p className="text-[13px] text-pos">Live output matches the sealed output field by field.</p> : (
        <div className="rounded-md border border-neg/40 bg-neg-soft p-2 text-[12.5px]">
          <p className="font-semibold text-neg">Live ≠ sealed</p>
          {diff.verdictDiffers && <p>Verdict: sealed {VERDICT[diff.sealedJ as "same"] ?? diff.sealedJ}, live {run.verdict?.judgement}.</p>}
          {diff.pidDiffers && <p>Matched paragraph changed.</p>}
          {diff.rows.map((r) => <p key={r.field}>{FIELD_LABEL[r.field as "actor"]}: sealed {r.sealed ? STATUS_LABEL[r.sealed] : "—"}, live {STATUS_LABEL[r.live]}</p>)}
          <p className="mt-1 text-ink-3">Both are shown; neither replaces the other. The benchmark result is the sealed one.</p>
        </div>
      ))}
    </CardBody></Card>
  );
}

export function ErrorNote({ run, onReplay }: { run: LiveRun; onReplay?: () => void }) {
  return (
    <div className="rounded-lg border border-neg/40 bg-neg-soft p-3 text-[13.5px]" role="alert">
      <p className="font-semibold">{run.error?.code === "429" ? "Too many live runs right now." : "The live run did not complete."}</p>
      <p className="text-ink-2">{run.error?.message}</p>
      {onReplay && <Button size="sm" variant="outline" className="mt-2" onClick={onReplay}>Show the cached replay instead</Button>}
    </div>
  );
}

