import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader, Section } from "@/components/Page";
import { Card, CardBody } from "@/components/ui/primitives";
import { Num } from "@/components/Provenance";
import { CIBar } from "@/components/CICell";
import { resolveKey } from "@/lib/keys";
import { fmtInt } from "@/lib/utils";

export default function Construction() {
  const s = useData((st) => st.snapshot)!;
  const open = useDrawer((st) => st.open);
  const R = s.results;
  const n = (k: string) => resolveKey(R, k) as number;
  const funnel = [
    ["Directions", "tables.01_corpus.directions"], ["Paragraphs", "tables.01_corpus.paragraphs"], ["Deontic-cue paragraphs", "tables.02_candidates.paragraphs_with_cue"],
    ["Candidates (rules v4)", "tables.02_candidates.candidates_kept"], ["Sampled (P2-004)", "tables.05_t1_benchmark.sample"], ["Validated gold", "tables.05_t1_benchmark.validated"],
  ] as const;
  const max = Math.log10(n(funnel[1][1]));
  const rounds = resolveKey(R, "tables.02_candidates.precision_rounds") as { rules: string; n: number; true: number; precision: number; wilson_95: [number, number] }[];
  const dec = resolveKey(R, "tables.04_supplementary.decisions") as { source: string; n: number; clean: number; rate: number; wilson95: [number, number]; decision: string }[];
  const dist = (k: string) => Object.entries(resolveKey(R, k) as Record<string, number>).filter(([, v]) => v > 0);
  return (
    <div>
      <PageHeader title="Benchmark Construction" tier="SHOULD" subtitle="From 381 Directions to 106 validated T1 items. Every count is a results_v2.json key." />
      <Card><CardBody className="space-y-1.5">
        {funnel.map(([l, k]) => (
          <div key={k} className="flex items-center gap-3 text-[13px]">
            <span className="w-44 shrink-0 text-ink-2">{l}</span>
            <div className="h-5 rounded bg-accent/70" style={{ width: `${Math.max(4, (Math.log10(Math.max(n(k), 1)) / max) * 70)}%` }} />
            <Num value={fmtInt(n(k))} sourceKey={k} />
          </div>
        ))}
        <p className="pt-1 text-[12px] text-ink-3">Log-scaled bars. <Num value={n("tables.05_t1_benchmark.rejected")} sourceKey="tables.05_t1_benchmark.rejected" /> sampled items were rejected as not an obligation. Matching threshold{" "}
          <Num value={String(resolveKey(R, "tables.03_matching.threshold.value"))} sourceKey="tables.03_matching.threshold.value" />.</p>
      </CardBody></Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Candidate precision by rule version (Wilson 95%)">
          <Card><CardBody className="space-y-2">
            {rounds.map((r, i) => (
              <div key={r.rules} className="flex flex-wrap items-center gap-3 text-[12.5px]">
                <span className="w-8 font-medium">{r.rules}</span><CIBar point={r.precision} lo={r.wilson_95[0]} hi={r.wilson_95[1]} domain={[0.4, 1]} width={160} />
                <Num value={`${r.true}/${r.n} = ${r.precision.toFixed(3)} [${r.wilson_95[0].toFixed(3)}, ${r.wilson_95[1].toFixed(3)}]`} sourceKey={`tables.02_candidates.precision_rounds.${i}`} />
              </div>
            ))}
          </CardBody></Card>
        </Section>
        <Section title="Routes, flags and judgements (gold v1)">
          <Card><CardBody className="grid gap-3 text-[12.5px] sm:grid-cols-3">
            {[["Routes", "tables.05_t1_benchmark.route_counts"], ["Flags", "tables.05_t1_benchmark.flag_distribution"], ["Judgements", "tables.05_t1_benchmark.judgement_distribution"]].map(([l, k]) => (
              <div key={k}><p className="mb-1 font-medium">{l}</p>{dist(k).map(([a, v]) => <p key={a}>{a}: <Num value={v} sourceKey={`${k}.${a}`} /></p>)}</div>
            ))}
          </CardBody></Card>
        </Section>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Guidelines v3 and the flag derivation (rule v3.6)">
          <Card><CardBody className="text-[12.5px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border border-line px-2 py-1">per-class judgements</span><span>→</span>
              <span className="rounded bg-pos-soft px-2 py-1">any <b>different</b> → class-specific</span><span>else</span>
              <span className="rounded bg-accent-soft px-2 py-1">any <b>same</b> → shared</span><span>else</span>
              <span className="rounded bg-panel-2 px-2 py-1">all <b>none</b> → absent</span><span>else</span>
              <span className="rounded bg-warn-soft px-2 py-1">ambiguous → adjudication</span>
            </div>
            <p className="mt-2 text-ink-3">"Guidelines v3" is the guideline family; v3.1–v3.10 are its numbered rules (A8). Implemented in <code>src/benchmark/t1.py</code> <code>derive_flag</code>.</p>
            <ul className="mt-2 grid gap-x-4 sm:grid-cols-2">{s.guidelineRules.map((r) => <li key={r.id}><b>{r.id}</b> {r.title.replace(/`/g, "")}</li>)}</ul>
          </CardBody></Card>
        </Section>
        <Section title="P2-003 source decisions (locked rule)">
          <Card><CardBody className="space-y-2 text-[12.5px]">
            {dec.map((x, i) => (
              <div key={x.source} className="flex flex-wrap items-center gap-2">
                <b className="w-24">{x.source}</b><CIBar point={x.rate} lo={x.wilson95[0]} hi={x.wilson95[1]} domain={[0, 1]} width={140} />
                <Num value={`${x.clean}/${x.n} clean`} sourceKey={`tables.04_supplementary.decisions.${i}`} /><code className="text-[11px]">{x.decision}</code>
              </div>
            ))}
            <p className="text-ink-3">FAQ → validation / motivation only; enforcement → Direction-level weak labels only.</p>
          </CardBody></Card>
        </Section>
      </div>
      <Section title="Construction steps">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {s.constructionSteps.map((c) => (
            <button key={c.id} type="button" onClick={() => open(`step:${c.id}`)} className="cursor-pointer rounded-md border border-line bg-panel p-2.5 text-left text-[12.5px] hover:border-accent">
              <b>{c.id}</b> {c.title}<span className="mt-1 block text-ink-3">{c.outputs.join(" · ")}</span>
            </button>
          ))}
        </div>
      </Section>
    </div>
  );
}
