import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMemo } from "react";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Card, CardBody, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { CICell } from "@/components/CICell";
import { CaveatChips } from "@/components/CaveatChip";
import { ForestPlot } from "@/components/ForestPlot";
import { Num } from "@/components/Provenance";
import { RuleCard } from "@/components/RuleCard";
import { r13MissingCI, r2ByConstruction, r3Circularity, r9SmallN } from "@/intelligence/rules";
import { resolveKey } from "@/lib/keys";
import { SYSTEM_ORDER } from "@/lib/utils";

export function ScoringAsymmetry() {
  return (
    <div className="mb-3 rounded-md border border-warn/40 bg-warn-soft px-3 py-2 text-[12.5px]">
      <b>Scoring asymmetry (A11).</b> Abstentions are scored as errors, so the verifier's loss in F1 reflects both wrong answers and declined correct ones
      (coverage <Num value="−0.217" sourceKey="phase4.t1_paired.Ablation C on T1: final agentic − class-aware.coverage" />). Long-context items that exceeded the
      input cap are excluded rather than penalised, and every comparison with long-context is made on the same{" "}
      <Num value="102" sourceKey="phase4.t1_systems.long_context.n_items" /> items. <CaveatChips ids={["scoring_asymmetry", "single_expert"]} />
    </div>
  );
}

const T1_METRICS = [["flag_macro_f1", "3-way flag F1"], ["collapsed_macro_f1", "Collapsed F1"], ["judgement_macro_f1", "Judgement macro-F1"], ["different_f1", "`different` F1"], ["coverage", "Coverage"]] as const;

function T1Tab() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const open = useDrawer((st) => st.open);
  const t1 = s.metrics.filter((m) => m.datasetId === "t1_gold_v1");
  const r13 = r13MissingCI(t1);
  const ea = resolveKey(s.results, "tables.05_t1_benchmark.by_source_class") as Record<string, { validated: number }>;
  return (
    <div>
      <ScoringAsymmetry />
      <Card><CardBody className="overflow-x-auto p-0">
        <table className="w-full min-w-[900px] text-[12.5px]">
          <thead><tr className="border-b border-line text-left text-ink-3"><th className="px-3 py-2 font-normal">System</th><th className="font-normal">n</th>
            {T1_METRICS.map(([, l]) => <th key={l} className="font-normal">{l}</th>)}</tr></thead>
          <tbody>
            {SYSTEM_ORDER.map((sys) => {
              const ms = t1.filter((m) => m.systemId === sys);
              if (!ms.length) return null;
              return (
                <tr key={sys} className="border-b border-line last:border-0">
                  <td className="px-3 py-2">
                    <button type="button" className="cursor-pointer hover:text-accent" onClick={() => open(`system:${sys}`)}>{d.systemName(sys)}</button>
                    {sys === "long_context" && <Badge tone="warn" className="ml-1">102 items</Badge>}
                    {sys === "majority" && <Badge className="ml-1">in-sample</Badge>}
                    {sys === "comparator" && <Badge tone="accent" className="ml-1">pre-registered</Badge>}
                  </td>
                  <td className="num">{ms[0].n}</td>
                  {T1_METRICS.map(([k]) => {
                    const m = ms.find((x) => x.metric === k);
                    return <td key={k} className="py-2 pr-3">{m ? <CICell point={m.value} ci={m.ci} label={m.ciLabel} sourceKey={m.sourceKey} compact onOpen={() => open(`metric:${m.systemId}:${m.datasetId}:${m.metric}`)} /> : "—"}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody></Card>
      <p className="mt-2 text-[12px] text-ink-3">Comparator flag metrics are derived from its judgements with rule v3.6 (secondary); its judgement metrics are the pre-registered ones. Majority (in-sample) is a reference baseline built from the gold distribution, not a deployable system. Collapsed F1 is the fair comparison with P2-002.</p>
      <div className="mt-3 grid gap-2 md:grid-cols-2">{r13.slice(0, 1).map((r, i) => <RuleCard key={i} r={r} />)}
        <RuleCard r={{ rule: "R4", verdict: "info", title: "Item-set mismatch", inputs: {}, reason: "Long-context is scored on 102 items; its comparisons in the Paired tab use the same-items keys automatically.", sourceRefs: ["phase4.long_context_same_items"] }} />
      </div>
      <Section title="Per source class (R9: slices of 7–15 items)">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(ea).map(([c, v]) => {
            const r = r9SmallN(v.validated, c);
            return <div key={c} className="rounded-md border border-line p-2 text-[12px]"><p className="font-medium">{c}</p>
              <p><Num value={v.validated} sourceKey={`tables.05_t1_benchmark.by_source_class.${c}.validated`} /> validated items {r.verdict === "warn" && <Badge tone="warn">wide CI</Badge>}</p></div>;
          })}
        </div>
      </Section>
    </div>
  );
}

function T2Tab() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const open = useDrawer((st) => st.open);
  return (
    <div className="space-y-4">
      {(["t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"] as const).map((ds) => {
        const ms = s.metrics.filter((m) => m.datasetId === ds);
        const pair = s.paired.find((p) => p.id === `t2:${ds}`)!;
        return (
          <Card key={ds}>
            <CardBody>
              <div className="mb-2 flex flex-wrap items-center gap-2"><h3 className="font-semibold">{ds}</h3><span className="text-ink-3">n = {d.datasets.find((x) => x.id === ds)?.n}</span><CaveatChips ids={["by_construction", `bias_${ds}`]} /></div>
              <RuleCard r={r2ByConstruction(ds, s)} className="mb-3" />
              <table className="w-full text-[12.5px]"><tbody>
                {ms.map((m) => (
                  <tr key={m.sourceKey} className="border-t border-line">
                    <td className="py-1.5 pr-2">{d.systemName(m.systemId)}</td>
                    <td><CICell point={m.value} ci={m.ci} label={m.ciLabel} sourceKey={m.sourceKey} compact onOpen={() => open(`metric:${m.systemId}:${m.datasetId}:${m.metric}`)} /></td>
                  </tr>
                ))}
              </tbody></table>
              <p className="mt-2 text-[12.5px]">Class filter, pipeline retrieval stage (ON − OFF): <CICell point={pair.delta} ci={pair.ci} label={pair.ciLabel} sourceKey={pair.sourceKey} signed compact onOpen={() => open(`paired:${pair.id}`)} /></p>
            </CardBody>
          </Card>
        );
      })}
      <p className="text-[12px] text-ink-3">Hybrid − source class = the class-blind hybrid RRF with every paragraph of the query's own source class removed before fusion (A7).</p>
    </div>
  );
}

function PairedTab() {
  const s = useData((st) => st.snapshot)!;
  const open = useDrawer((st) => st.open);
  const [sp, setSp] = useSearchParams();
  const prereg = sp.get("prereg") === "1";
  const fam = sp.get("family") ?? "all";
  const metric = sp.get("metric") ?? "headline";
  const rows = useMemo(() => s.paired.filter((p) => (!prereg || p.preregistered) && (fam === "all" || p.family === fam)
    && (metric === "all" || (metric === "headline" ? (p.family !== "T1" || p.metric === "flag_macro_f1" || p.id.startsWith("prereg:") && p.preregistered) : p.metric === metric)))
    .map((p) => ({ id: p.id, label: `${p.label}${p.family === "T1" && !p.id.startsWith("prereg") ? ` · ${p.metric.replace("_macro_f1", "")}` : p.id.startsWith("prereg") ? ` · ${p.metric}` : ""}`,
      delta: p.delta, ci: p.ci, ciLabel: p.ciLabel, sourceKey: p.sourceKey, badge: p.sameItems ? "102 items" : p.preregistered ? "pre-reg" : p.family === "T3" ? "circular" : p.family === "T2" ? "by constr." : undefined })),
  [s.paired, prereg, fam, metric]);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }); };
  return (
    <div>
      <ScoringAsymmetry />
      <div className="mb-3 flex flex-wrap items-center gap-3 text-[12.5px]">
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={prereg} onChange={(e) => set("prereg", e.target.checked ? "1" : "0")} />Pre-registered only</label>
        <label className="flex items-center gap-1.5">Family <select className="rounded border border-line bg-panel px-1 py-0.5" value={fam} onChange={(e) => set("family", e.target.value)}>
          {["all", "T1", "T2", "T3", "T4"].map((f) => <option key={f}>{f}</option>)}</select></label>
        <label className="flex items-center gap-1.5">Metric <select className="rounded border border-line bg-panel px-1 py-0.5" value={metric} onChange={(e) => set("metric", e.target.value)}>
          {["headline", "all", "flag_macro_f1", "collapsed_macro_f1", "coverage", "different_f1", "judgement_macro_f1"].map((f) => <option key={f}>{f}</option>)}</select></label>
        <span className="text-ink-3">{rows.length} comparison(s); green / red = CI excludes 0 above / below; grey = includes 0.</span>
      </div>
      <Card><CardBody><ForestPlot rows={rows} onOpen={(id) => open(`paired:${id}`)} name="paired_comparisons" /></CardBody></Card>
      <p className="mt-2 text-[12px] text-ink-3">Long-context rows use the same-items keys (`(same items)`, n = 102). T3's comparison is circular by construction (R3); T2 gains are partly by construction (R2).</p>
    </div>
  );
}

function AblationsTab() {
  const s = useData((st) => st.snapshot)!;
  return (
    <Card><CardBody className="overflow-x-auto p-0">
      <table className="w-full min-w-[760px] text-[12.5px]">
        <thead><tr className="border-b border-line text-left text-ink-3"><th className="px-3 py-2 font-normal">Ablation (toggle)</th><th className="font-normal">Measure</th><th className="font-normal">n</th><th className="font-normal">ON − OFF</th></tr></thead>
        <tbody>
          {s.ablations.map((a) => (
            <tr key={a.id} className="border-b border-line last:border-0">
              <td className="px-3 py-2"><b>{a.ablation}</b> · {a.toggle}</td>
              <td>{a.measure}{a.condition && <Badge tone="warn" className="ml-1">{a.condition}</Badge>}{a.circular && <Badge tone="neg" className="ml-1">circular</Badge>}
                {a.measure.startsWith("T2") && <CaveatChips ids={["by_construction"]} className="ml-1" />}
                {a.measure.startsWith("T1") && <CaveatChips ids={["scoring_asymmetry", "single_expert"]} className="ml-1" />}</td>
              <td className="num">{a.n}</td>
              <td className="py-2 pr-3"><CICell point={a.delta} ci={a.ci} label={a.ciLabel} sourceKey={a.sourceKey} signed compact /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 pb-3 text-[12px] text-ink-3">"Ablation A/B/C" name toggles only (A2). The class-filter-on-T1 number has two conditions: with verifier −0.049 (row above) and without verifier −0.050 (headline 2); neither CI excludes 0.</p>
    </CardBody></Card>
  );
}

function T3Tab() {
  const s = useData((st) => st.snapshot)!;
  const on = s.metrics.find((m) => m.datasetId === "t3" && m.systemId === "temporal_filter_on")!;
  const off = s.metrics.find((m) => m.datasetId === "t3" && m.systemId === "temporal_filter_off")!;
  const r3 = r3Circularity(on);
  const R = s.results;
  return (
    <div className="space-y-3">
      <RuleCard r={r3} />
      <Card><CardBody className="space-y-2 text-[13px]">
        <p>Filter <b>off</b>: status exact match <CICell point={off.value} ci={off.ci} label={off.ciLabel} sourceKey={off.sourceKey} compact />. The model answered "in force, original" on{" "}
          <Num value={resolveKey(R, "tables.08_t3.t3.off.pred_status.in_force_original") as number} sourceKey="tables.08_t3.t3.off.pred_status.in_force_original" /> of{" "}
          <Num value={off.n} sourceKey="tables.08_t3.t3.off.n" /> items.</p>
        <p>Filter <b>on</b>: <CICell point={on.value} ci={on.ci} label={on.ciLabel} sourceKey={on.sourceKey} compact /> <Badge tone="neg">circular by construction</Badge> <CaveatChips ids={["circular", "t3_parser_defect"]} /></p>
        <p className="text-ink-3">T3 measures whether a model uses the dates it is given. Gold and the temporal filter share one parser, so the filter-on score is not evidence of accuracy. Amended text only: earlier wording cannot be shown.</p>
      </CardBody></Card>
    </div>
  );
}

function T4Tab() {
  const s = useData((st) => st.snapshot)!;
  const R = s.results;
  const rho = (k: string) => resolveKey(R, k) as { rho: number; ci_low: number; ci_high: number };
  const rows = [["RePASs vs human faithful", "tables.09_t4.human.all_rated.spearman_composite_score_vs_faithful"],
    ["RePASs vs answers_question", "tables.09_t4.human.all_rated.spearman_composite_score_vs_answers_question"],
    ["Repaired vs human faithful (exploratory)", "tables.09_t4.human.all_rated.spearman_repaired_vs_faithful"]] as const;
  return (
    <div className="space-y-3">
      <Card><CardBody>
        <h3 className="mb-2 font-semibold">RePASs composite by answer type <CaveatChips ids={["small_n_t4"]} /></h3>
        <table className="w-full text-[12.5px]"><tbody>
          {s.metrics.filter((m) => m.datasetId === "t4").map((m) => <tr key={m.systemId} className="border-t border-line"><td className="py-1.5">{m.systemId}</td><td><CICell point={m.value} ci={m.ci} label={m.ciLabel} sourceKey={m.sourceKey} compact /></td></tr>)}
        </tbody></table>
        <h3 className="mb-1 mt-4 font-semibold">Paired (pre-registered verdicts)</h3>
        {s.paired.filter((p) => p.family === "T4").map((p) => (
          <p key={p.id} className="text-[12.5px]">{p.label}: <CICell point={p.delta} ci={p.ci} label={p.ciLabel} sourceKey={p.sourceKey} signed compact /> · verdict{" "}
            <b>{String(resolveKey(R, `tables.09_t4.verdicts.${p.a}`))}</b></p>
        ))}
      </CardBody></Card>
      <Card><CardBody>
        <h3 className="mb-2 font-semibold">RePASs vs human ratings (Spearman ρ)</h3>
        {rows.map(([l, k]) => { const v = rho(k); return <p key={k} className="text-[12.5px]">{l}: <CICell point={v.rho} ci={[v.ci_low, v.ci_high]} label={`${v.rho.toFixed(3)} [${v.ci_low.toFixed(3)}, ${v.ci_high.toFixed(3)}]`} sourceKey={k} domain={[-1, 1]} compact /></p>; })}
        <div className="mt-3 rounded-md border border-dashed border-line p-3 text-[12px] text-ink-3">Scatter of RePASs vs human ratings: per-answer human ratings are not in the public files this UI ingests (release/data/t4/scores.jsonl has metric scores only), so only ρ values are shown (DECISIONS D-11).</div>
        <CaveatChips ids={["repair_exploratory"]} className="mt-2" />
      </CardBody></Card>
    </div>
  );
}

const TABS = [["t1", "T1"], ["t2", "T2"], ["paired", "Paired differences"], ["ablations", "Ablations"], ["t3", "T3"], ["t4", "T4"]] as const;

export default function ResultsLab() {
  const { tab = "t1" } = useParams();
  const nav = useNavigate();
  return (
    <div>
      <PageHeader title="Results Lab" tier="MUST" subtitle="Every cell: hover shows its key in reports/results_v2.json; click opens evidence and lineage. CIs are 95% percentile bootstrap (2,000 item resamples), labelled exactly as src/eval/ci_format.py." />
      <Tabs value={tab} onValueChange={(v) => nav(`/workspace/results/${v}`)}>
        <TabsList className="mb-3">{TABS.map(([k, l]) => <TabsTrigger key={k} value={k}>{l}</TabsTrigger>)}</TabsList>
        <TabsContent value="t1"><T1Tab /></TabsContent>
        <TabsContent value="t2"><T2Tab /></TabsContent>
        <TabsContent value="paired"><PairedTab /></TabsContent>
        <TabsContent value="ablations"><AblationsTab /></TabsContent>
        <TabsContent value="t3"><T3Tab /></TabsContent>
        <TabsContent value="t4"><T4Tab /></TabsContent>
      </Tabs>
    </div>
  );
}
