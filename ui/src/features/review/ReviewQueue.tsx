import { useMemo, useState } from "react";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { unitConfidence } from "@/data/confidence";
import { PageHeader } from "@/components/Page";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { pct } from "@/lib/utils";

function load(): Record<string, string> { try { return JSON.parse(localStorage.getItem("cc-review") || "{}"); } catch { return {}; } }
function save(v: Record<string, string>) { try { localStorage.setItem("cc-review", JSON.stringify(v)); } catch { /* memory only */ } }

/** Selective prediction as a workflow: High-band comparator verdicts pass; everything else is routed to an analyst. Model M2 only (product). */
export default function ReviewQueue() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const open = useDrawer((st) => st.open);
  const [done, setDone] = useState<Record<string, string>>(load);
  const [band, setBand] = useState<"Low" | "Medium" | "Abstain" | "all">("Low");
  const queue = useMemo(() => s.classUnits.map((u) => ({ u, c: unitConfidence(model, u.id, "M2") })).filter((x) => x.c && x.c.band !== "High"), [s.classUnits, model]);
  if (!model) return <p className="text-sm">Confidence model missing: run <code>npm run calibrate</code>.</p>;
  const ev = model.models.M2.eval;
  const shown = queue.filter((x) => band === "all" || x.c!.band === band);
  const mark = (id: string, v: string) => { const n = { ...done, [id]: v }; setDone(n); save(n); };
  return (
    <div>
      <PageHeader title="Human-review queue" tier="COULD" product subtitle="Comparator verdicts outside the High band are routed to an analyst. Benchmark units are used as a demonstration; decisions stay in this browser." />
      <Card className="mb-3"><CardBody className="text-[13px]">
        At the fixed operating point (answer at High only, model M2 fitted on the dev set and frozen before gold evaluation) the comparator answers{" "}
        <b>{pct(ev.operatingPoint.coverage)}</b> of units automatically, correct <b>{pct(ev.operatingPoint.accuracy)}</b> of the time on gold
        [{pct(ev.operatingPoint.wilsonCI?.[0])}, {pct(ev.operatingPoint.wilsonCI?.[1])}]. The other <b>{queue.length}</b> go to review.
        <p className="mt-1 text-[12px] text-warn">The High band holds almost only `same` (and a few `none`) verdicts; nearly every `different` verdict is routed to review. That is the honest product story: the system is trusted for "same obligation", and a human checks claimed differences.</p>
      </CardBody></Card>
      <div className="mb-2 flex flex-wrap gap-1.5 text-[12px]">{(["Low", "Medium", "Abstain", "all"] as const).map((b) => (
        <Button key={b} size="sm" variant={band === b ? "default" : "outline"} onClick={() => setBand(b)}>{b} · {b === "all" ? queue.length : queue.filter((x) => x.c!.band === b).length}</Button>))}
        <span className="ml-2 self-center text-ink-3">{Object.keys(done).length} reviewed in this browser</span></div>
      <div className="space-y-2">
        {shown.slice(0, 80).map(({ u, c }) => (
          <Card key={u.id}><CardBody className="flex flex-wrap items-center gap-2 py-2 text-[12.5px]">
            <button type="button" className="cursor-pointer text-left hover:text-accent" onClick={() => open(`unit:${u.id}`)}>
              <span className="text-ink-2">{d.itemById.get(u.itemId)?.sourceClass}</span> → <b>{u.classId}</b></button>
            <Badge tone="outline">comparator: {u.predictions.comparator.judgement}</Badge>
            <ConfidenceBadge c={c} compact />
            <span className="ml-auto flex gap-1">
              {done[u.id] ? <Badge tone={done[u.id] === "confirm" ? "pos" : "warn"}>{done[u.id]}{done[u.id] && ` · gold ${u.goldJudgement}`}</Badge> : <>
                <Button size="sm" variant="outline" onClick={() => mark(u.id, "confirm")}>Confirm</Button>
                <Button size="sm" variant="outline" onClick={() => mark(u.id, "override")}>Override</Button></>}
            </span>
          </CardBody></Card>
        ))}
        {shown.length > 80 && <p className="text-[12px] text-ink-3">Showing 80 of {shown.length}.</p>}
      </div>
    </div>
  );
}
