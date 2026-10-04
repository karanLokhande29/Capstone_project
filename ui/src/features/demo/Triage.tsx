import { useMemo, useState } from "react";
import { Button, Card, CardBody } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { PostPaper } from "./badges";
import { useCase, useIndex, useJson } from "./data";
import { Loading, LoadError, PageHead } from "./DemoLayout";
import { ConfidenceDetails } from "./case/parts";
import { FEATURE_LABEL, pct0, pct1, VERDICT } from "./names";
import type { Judgement, TriageGrid } from "./types";

const ci = (x: [number, number] | null) => (x ? `${pct1(x[0])}–${pct1(x[1])}` : "—");

export default function Triage() {
  const g = useJson<TriageGrid>("triage_grid.json");
  const rows = useMemo(() => [...(g.data?.rows ?? [])].sort((a, b) => a.t - b.t), [g.data]);
  const [i, setI] = useState<number | null>(null);
  if (g.error) return <LoadError error={g.error} />;
  if (!g.data) return <Loading what="the triage grid" />;
  const grid = g.data;
  const highIdx = rows.findIndex((r) => r.t === grid.presets.High);
  const k = i ?? highIdx;
  const r = rows[k];
  const n = grid.n;

  return (
    <div>
      <PageHead eyebrow="Triage" title="How much could a team let the system handle?">
        <p className="flex flex-wrap items-center gap-2"><span>Observed trade-off on the evaluated test set — not a recommended threshold.</span><PostPaper /></p>
        <p className="mt-2">Every comparator answer has a probability of being right, from a small model fitted on a separate 30-item development set and frozen before the
          test. Move the threshold: answers at or above it are “handled automatically”, everything else goes to a person. The numbers are what actually happened on the {n} expert-labelled comparisons.</p>
      </PageHead>

      <Card className="mt-6"><CardBody className="space-y-4">
        <div>
          <label htmlFor="thr" className="flex flex-wrap items-baseline justify-between gap-2 text-[14px]">
            <span className="font-medium">Threshold on the probability of being right</span>
            <span className="num text-[22px] font-semibold">{r.t.toFixed(3)}</span>
          </label>
          <input id="thr" type="range" min={0} max={rows.length - 1} step={1} value={k} onChange={(e) => setI(Number(e.target.value))}
            className="mt-2 w-full accent-[var(--accent)]" aria-valuetext={`threshold ${r.t.toFixed(3)}, ${r.nAuto} of ${n} handled automatically`} />
          <div className="mt-1 flex justify-between text-[11.5px] text-ink-3"><span>lower: handle more</span><span>higher: handle less</span></div>
          <div className="mt-2 flex flex-wrap gap-2 text-[12.5px]">
            <span className="text-ink-3">Band thresholds as frozen:</span>
            <Button size="sm" variant="outline" onClick={() => setI(highIdx)}>High (≥ {grid.bandThresholds.high})</Button>
            <Button size="sm" variant="outline" onClick={() => setI(rows.findIndex((x) => x.t === grid.presets.Medium))}>Medium and above (≥ {grid.bandThresholds.low})</Button>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Coverage: handled automatically" value={pct0(r.nAuto / n)} sub={`${r.nAuto} of ${n} comparisons`} />
          <Metric label="Accuracy among handled" value={r.accAuto != null ? pct1(r.accAuto) : "—"} sub={`${r.kAuto} of ${r.nAuto} correct · 95% range ${ci(r.ciAuto)}`} />
          <Metric label="Sent to review" value={`${r.nReview}`} sub={r.accReview != null ? `of which the comparator got ${pct1(r.accReview)} right (${r.kReview}/${r.nReview}) · 95% range ${ci(r.ciReview)}` : "nothing sent"} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-[13px]">
            <caption className="pb-1 text-left text-[12.5px] text-ink-3">Split by the comparator's verdict at this threshold</caption>
            <thead className="text-left text-ink-3"><tr><th className="py-1 font-medium">Verdict</th><th className="font-medium">Handled automatically</th><th className="font-medium">Correct among handled</th><th className="font-medium">Sent to review</th></tr></thead>
            <tbody>
              {(["same", "different", "none"] as Judgement[]).map((v) => {
                const s = r.split[v];
                return (
                  <tr key={v} className="border-t border-line">
                    <td className="py-1.5">{VERDICT[v]}</td>
                    <td className="num">{s.auto} of {s.total}</td>
                    <td className="num">{s.auto ? `${s.autoCorrect} (${pct0(s.autoCorrect / s.auto)})` : "—"}</td>
                    <td className="num">{s.total - s.auto}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-1 text-[12px] text-ink-3">“Different” verdicts almost never clear a high threshold: a flagged difference is a reason to look, not a conclusion. Two units the comparator could not read always go to review.</p>
        </div>
        <p className="text-[12px] text-ink-3">95% ranges: item-level bootstrap ({grid.resamples.toLocaleString()} resamples of the 106 items, seed {grid.seed} from {grid.seedSource}), precomputed at build time.</p>
      </CardBody></Card>

      <section className="mt-8 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="text-[18px] font-semibold">Is the probability honest? <PostPaper className="ml-1 align-middle" /></h2>
          <p className="mt-1 text-[13.5px] text-ink-2">Reliability diagram on the {n} test comparisons: each bar is the share right among answers whose probability fell in that bin. Empty bins are gaps.</p>
          <Reliability grid={grid} />
          <p className="mt-2 text-[13px] text-ink-2">Calibration error (ECE) {grid.calibration.ece.toFixed(3)} · Brier score {grid.calibration.brier.toFixed(3)} · base accuracy {grid.calibration.baseRate.correct}/{grid.calibration.baseRate.n} ({pct1(grid.calibration.baseRate.accuracy)}).</p>
        </div>
        <ScoreExplainer grid={grid} />
      </section>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-[12.5px] text-ink-3">{label}</p>
      <p className="num mt-1 text-[26px] font-semibold leading-none">{value}</p>
      <p className="mt-1 text-[12px] text-ink-2">{sub}</p>
    </div>
  );
}

function Reliability({ grid }: { grid: TriageGrid }) {
  const W = 320, H = 200, P = 28;
  const x = (v: number) => P + v * (W - P - 8);
  const y = (v: number) => H - P - v * (H - P - 8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full max-w-md" role="img" aria-label="Reliability diagram: predicted probability against observed accuracy">
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--ink-3)" strokeDasharray="4 3" />
      {grid.calibration.reliability.map((b) => b.n > 0 && b.accuracy != null ? (
        <g key={b.lo}>
          <rect x={x(b.lo) + 1} y={y(b.accuracy)} width={x(b.hi) - x(b.lo) - 2} height={y(0) - y(b.accuracy)} fill="var(--accent)" opacity={0.75}><title>{`${b.lo.toFixed(1)}–${b.hi.toFixed(1)}: ${pct0(b.accuracy)} right (n=${b.n})`}</title></rect>
          <text x={(x(b.lo) + x(b.hi)) / 2} y={y(b.accuracy) - 3} textAnchor="middle" fontSize="8" fill="var(--ink-3)">{b.n}</text>
        </g>
      ) : null)}
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(0)} stroke="var(--line)" />
      <line x1={x(0)} y1={y(0)} x2={x(0)} y2={y(1)} stroke="var(--line)" />
      {[0, 0.5, 1].map((v) => <text key={`x${v}`} x={x(v)} y={H - 10} fontSize="9" textAnchor="middle" fill="var(--ink-3)">{v}</text>)}
      {[0, 0.5, 1].map((v) => <text key={`y${v}`} x={P - 6} y={y(v) + 3} fontSize="9" textAnchor="end" fill="var(--ink-3)">{v}</text>)}
      <text x={W / 2} y={H - 1} fontSize="9" textAnchor="middle" fill="var(--ink-2)">predicted probability right</text>
    </svg>
  );
}

function ScoreExplainer({ grid }: { grid: TriageGrid }) {
  const idx = useIndex().data;
  const [unit, setUnit] = useState<string>("t1_md_12949::p00040|Rural Co-operative Banks");
  const c = useCase(unit);
  const options = useMemo(() => (idx?.units ?? []).filter((u) => u.p != null).slice(0, 412), [idx]);
  return (
    <div>
      <h2 className="text-[18px] font-semibold">How the score is computed</h2>
      <p className="mt-1 text-[13.5px] text-ink-2">A logistic model over eight features of the comparator's own output. Weights apply to standardised values (fitted on {grid.fittedOn}).</p>
      <ul className="mt-2 divide-y divide-line rounded-lg border border-line text-[13px]">
        {grid.features.map((f) => (
          <li key={f.feature} className="flex justify-between gap-2 px-3 py-1.5"><span>{FEATURE_LABEL[f.feature] ?? f.feature}</span><span className={cn("num", f.weight >= 0 ? "text-pos" : "text-neg")}>{f.weight >= 0 ? "+" : "−"}{Math.abs(f.weight).toFixed(3)}</span></li>
        ))}
      </ul>
      <label className="mt-3 flex flex-col gap-1 text-[12.5px] text-ink-3">See one case's contributions
        <select value={unit} onChange={(e) => setUnit(e.target.value)} className="h-9 rounded-md border border-line bg-panel px-2 text-[13px] text-ink">
          {options.map((u) => <option key={u.id} value={u.id}>{u.src} → {u.tgt} · {u.topic}</option>)}
        </select>
      </label>
      <div className="mt-2">{c.data ? <ConfidenceDetails unit={c.data.unit} open /> : <Loading />}</div>
    </div>
  );
}
