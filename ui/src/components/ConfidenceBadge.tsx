import type { UnitConfidence } from "@/data/confidence";
import { Badge, Tip } from "./ui/primitives";
import { pct } from "@/lib/utils";

const TONE = { High: "pos", Medium: "warn", Low: "neg", Abstain: "neutral" } as const;

/** "Answers in this band were correct X% of the time on the RBI-ObliBench gold [Wilson 95% CI], n = N." Blocked by R14 otherwise. */
export function ConfidenceBadge({ c, compact }: { c: UnitConfidence | null; compact?: boolean }) {
  if (!c) return <Badge tone="outline">confidence: not calibrated</Badge>;
  if (c.blocked) {
    return (
      <Tip content={<span>{c.reason}<br /><span className="text-ink-3">R14 · model {c.model} ({c.modelLabel})</span></span>}>
        <span><Badge tone="neutral">Insufficient evidence</Badge></span>
      </Tip>
    );
  }
  const s = c.stat!;
  const text = `${c.band} · ${pct(s.accuracy, 0)} correct in benchmark [${pct(s.wilsonCI![0], 0)}, ${pct(s.wilsonCI![1], 0)}] · n=${s.n}`;
  return (
    <Tip content={
      <span className="block max-w-xs space-y-1">
        <span className="block">Answers in the <b>{c.band}</b> band were correct {pct(s.accuracy, 1)} of the time on the RBI-ObliBench gold
          (Wilson 95% [{pct(s.wilsonCI![0], 1)}, {pct(s.wilsonCI![1], 1)}]), n = {s.n}.</span>
        {c.p !== null && <span className="block text-ink-3">This unit's score p = {c.p.toFixed(3)} (unscaled model output).</span>}
        <span className="block font-medium">Model {c.model}: {c.modelLabel}</span>
        {c.experimental && <span className="block text-warn">Bands marked experimental by the honesty rule.</span>}
        <span className="block text-ink-3">Single-expert gold · Flash-Lite-class model · 412 units: wide intervals.</span>
      </span>
    }>
      <span className="inline-flex max-w-full"><Badge tone={TONE[c.band]} className="max-w-full whitespace-normal leading-snug">{compact ? `${c.band} · ${pct(s.accuracy, 0)} · ${c.model}` : `${text} · ${c.model}`}</Badge></span>
    </Tip>
  );
}
