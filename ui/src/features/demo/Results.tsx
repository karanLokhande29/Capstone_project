import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Card, CardBody } from "@/components/ui/primitives";
import { resolveKey } from "@/lib/keys";
import { usePersona, type Persona } from "../pitch/persona";
import { Bars, Block, FinePrint, Meaning, plainCI, Term } from "../pitch/ui";
import { PostPaper } from "./badges";
import { useJson } from "./data";
import { Loading, LoadError, PageHead } from "./DemoLayout";
import { pct0, SYSTEM_NAME } from "./names";
import { RePASsPanel, T2FilterPanel, T3Timeline } from "./results/panels";
import type { ResultsShard, SystemId } from "./types";

type Section = "differences" | "search" | "trust" | "dates" | "moreai" | "metric";
const ORDER: Record<Persona, Section[]> = {
  compliance: ["differences", "search", "trust", "dates", "moreai", "metric"],
  researcher: ["differences", "moreai", "metric", "search", "trust", "dates"],
  investor: ["differences", "trust", "search", "dates", "moreai", "metric"],
};
const LABEL: Record<Section, string> = { differences: "Spotting differences", search: "Finding the rule", trust: "Confidence", dates: "Dates", moreai: "Our first pipeline", metric: "Gamed metrics" };
const OUTCOME_SYSTEMS: SystemId[] = ["comparator", "class_blind", "class_aware", "long_context", "final_agentic"];

type Confusion = Record<string, Record<string, number>>;

function outcomes(R: Record<string, unknown>) {
  const g = (k: string) => resolveKey(R, k);
  return OUTCOME_SYSTEMS.map((id) => {
    const c = g(id === "comparator" ? "phase4.comparator.different.judgement_confusion" : `phase4.t1_different.${id}.judgement_confusion`) as Confusion;
    const total = Object.values(c).reduce((a, r) => a + Object.values(r).reduce((x, y) => x + y, 0), 0);
    const agree = (["same", "different", "none"] as const).reduce((a, k) => a + (c[k]?.[k] ?? 0), 0);
    const answered = g(id === "comparator" ? "phase4.comparator.metrics.coverage.value" : `phase4.t1_systems.${id}.coverage.value`) as number;
    return { id, name: SYSTEM_NAME[id], ours: id === "comparator", diffFound: c.different.different, diffTotal: Object.values(c.different).reduce((a, b) => a + b, 0),
      falseAlarms: c.same.different + c.none.different, agree, total, answered };
  });
}

export default function Results() {
  const d = useJson<ResultsShard>("results.json");
  const persona = usePersona((p) => p.persona);
  const loc = useLocation();
  useEffect(() => {
    if (loc.hash && d.data) document.getElementById(loc.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [loc.hash, d.data]);
  if (d.error) return <LoadError error={d.error} />;
  if (!d.data) return <Loading what="the results" />;
  const R = d.data.results;
  const n = (k: string) => resolveKey(R, k) as number;
  const out = outcomes(R);
  const ours = out.find((o) => o.ours)!;
  const llms = out.filter((o) => !o.ours);
  const best = [...llms].sort((a, b) => b.diffFound - a.diffFound)[0];
  const first = out.find((o) => o.id === "final_agentic")!;
  const filtered = out.find((o) => o.id === "class_aware")!;
  const longCtx = out.find((o) => o.id === "long_context")!;
  const conf = d.data.confidence;
  const high = conf.bands.find((b) => b.band === "High")!;
  const kappa = d.data.reliability.find((r) => r.id === "fleiss_class_row");
  const pre = resolveKey(R, "phase4.preregistered_comparisons.comparator − class_aware.judgement.different_f1") as { diff: number; ci: [number, number] };
  const verifier = resolveKey(R, "phase4.t1_paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1") as { diff: number; ci: [number, number] };
  const t2base = "tables.06_t2_retrieval.p3001.t2_xclass_t1";
  const t2 = (id: string) => resolveKey(R, `${t2base}.systems.${id}`) as { recall: { mean: number }; ndcg: { mean: number } };
  const after = resolveKey(R, "tables.08_t3.t3.off.by_side.after") as { n: number; status_exact_match: number };
  const before = resolveKey(R, "tables.08_t3.t3.off.by_side.before") as { n: number; status_exact_match: number };
  const afterRight = Math.round(after.status_exact_match * after.n);
  const beforeRight = Math.round(before.status_exact_match * before.n);
  const t4 = (k: string) => n(`tables.09_t4.by_type.${k}.composite_score.mean`);
  const flags = conf.differentFlags;

  const sections: Record<Section, ReactNode> = {
    differences: (
      <Block id="differences" eyebrow="Result 1 · The core problem" title={<>The structured comparator finds {Math.round(ours.diffFound / Math.max(1, best.diffFound))}× more real differences than the best LLM system.</>}>
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          The expert found <b className="text-ink">{ours.diffTotal}</b> cases where two institution types have a rule on the same topic with a different requirement (a threshold, a deadline, a scope or an exception). How many did each system catch?
        </p>
        <div className="mt-6">
          <Bars max={ours.diffTotal} format={(v) => `${v}`}
            rows={out.map((o) => ({ label: o.name, value: o.diffFound, highlight: o.ours, note: `${o.diffFound} of ${o.diffTotal} real differences · ${o.falseAlarms} false alarms` }))}
            caption="Longer bar = more real differences caught. False alarms are pairs flagged as different that the expert judged the same or unmatched." />
        </div>
        <Meaning>
          LLM systems mostly answer “same” or “no match” when the rules actually differ. Making the model extract the rule's details and letting a fixed rule decide catches far more.
          The trade-off is over-flagging ({ours.falseAlarms} false alarms): when it flags a difference the expert agreed {flags.precision.k} of {flags.precision.n} times, so a flag is a reason to look, not a conclusion.
        </Meaning>
        <Card className="mt-4"><CardBody className="grid gap-4 text-[14px] sm:grid-cols-3">
          <div><p className="num text-[22px] font-semibold">{n("phase4.missed_by_every_llm_system.A_all_five_answered.missed")}</p><p className="text-ink-2">real differences none of the five LLM systems flagged</p></div>
          <div><p className="num text-[22px] font-semibold">{n("phase4.missed_by_every_llm_system.A_all_five_answered.comparator_correct")}</p><p className="text-ink-2">of those caught by the structured comparator</p></div>
          <div><p className="num text-[22px] font-semibold">{pct0(ours.agree / ours.total)} vs {pct0(best.agree / best.total)}</p><p className="text-ink-2">overall agreement with the expert: comparator vs {best.name} (which wins overall by saying “same” more often)</p></div>
        </CardBody></Card>
        <FinePrint source="phase4.t1_different, phase4.comparator, phase4.preregistered_comparisons">
          <p>Labels come from one expert. A separate 30-item sample labelled by three people agreed well on these judgements (agreement score {kappa?.value.toFixed(2)}), but the main labels were not double-checked.</p>
          <p>Pre-registered comparison: the comparator's prompt and rule were frozen before it ran on the test set. On the 0–1 score for spotting differences its advantage over the institution-filtered LLM is {plainCI(pre.diff, pre.ci[0], pre.ci[1])}.</p>
          <p>The comparator was shown the two candidate paragraphs the expert saw. It has not been run on retrieved evidence; that is future work. Retrieval systems never used the comparator.</p>
          <p>All systems use one fast, low-cost model (Gemini 3.5 Flash-Lite). Larger models may do better.</p>
        </FinePrint>
      </Block>
    ),
    search: (
      <Block id="search" eyebrow="Result 2 · Finding the rule" title="Telling the search which institution you mean makes it far better at finding the matching rule.">
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          Task: start from one institution's rule and find the matching rule for another institution type ({n(`${t2base}.n_scored`)} scored searches). How often is the correct paragraph in the top 10?
        </p>
        <div className="mt-6"><Bars format={pct0} caption="Correct paragraph in the top 10. Ranking quality (nDCG) also rewards putting it near the top." rows={[
          { label: "Keyword search", value: t2("bm25").recall.mean, note: `ranking quality ${t2("bm25").ndcg.mean.toFixed(2)}` },
          { label: "Meaning-based search", value: t2("dense").recall.mean, note: `ranking quality ${t2("dense").ndcg.mean.toFixed(2)}` },
          { label: "Both combined (standard)", value: t2("hybrid_rrf").recall.mean, note: `ranking quality ${t2("hybrid_rrf").ndcg.mean.toFixed(2)}` },
          { label: "Combined + institution filter", value: t2("class_aware").recall.mean, highlight: true, note: `ranking quality ${t2("class_aware").ndcg.mean.toFixed(2)}` },
        ]} /></div>
        <T2FilterPanel />
        <Meaning>Generic search keeps returning the original institution's own rule. Restricting to the institution type you asked about puts the right counterpart at or near the top.</Meaning>
        <FinePrint source={`${t2base}.systems`}>
          <p>The gain is partly built into the test: relevance labels cover only the target-class counterpart, so filtering to that class has a head start.</p>
          <p>The test answers were collected with help from meaning-based search, which slightly favours it. Better search alone did not make the LLM systems better at judging same vs different.</p>
        </FinePrint>
      </Block>
    ),
    trust: (
      <Block id="trust" eyebrow="Result 3 · Knowing when to trust it" title={<>When the comparator says “high confidence”, it was right {pct0(high.accuracy ?? 0)} of the time.</>}>
        <p className="flex max-w-3xl flex-wrap items-center gap-2 text-[15px] leading-relaxed text-ink-2"><span>A confidence model fitted on a separate 30-item practice set, frozen, then measured on the test set it had never seen.</span><PostPaper /></p>
        <div className="mt-6"><Bars format={pct0} caption="Share of answers in each band that matched the expert." rows={conf.bands.filter((b) => b.band !== "Abstain").map((b) => ({
          label: `${b.band} confidence`, value: b.accuracy ?? 0, highlight: b.band === "High", note: `right ${b.correct} of ${b.n} (likely range ${pct0(b.wilsonCI![0])}–${pct0(b.wilsonCI![1])})` }))} /></div>
        <Meaning>
          Accepting only high-confidence answers covers {pct0(conf.coverageHigh)} of comparisons at about {pct0(high.accuracy ?? 0)} accuracy. But high confidence is almost all “same rule” answers ({conf.highBySame} of {conf.highN}).
          Of the comparator's {flags.precision.k} correct “different” calls, {conf.differentCorrectByBand.Low ?? 0} are Low and {conf.differentCorrectByBand.Medium ?? 0} Medium, none High, which is why a flagged difference is shown as “Flagged for review”.
          <Link to="/triage" className="ml-1 text-accent hover:underline">Try the trade-off →</Link>
        </Meaning>
        <FinePrint source="confidence_model_v1.json → models.M2.eval">
          <p>Measured on {conf.baseRate.n} comparisons labelled by one expert, so the ranges are wide. Calibration error {conf.ece.toFixed(3)}, Brier {conf.brier.toFixed(3)}. Scores are never rescaled after the test.</p>
          <p>The confidence model is not in the paper (post-paper analysis).</p>
        </FinePrint>
      </Block>
    ),
    dates: (
      <Block id="dates" eyebrow="Result 4 · Dates matter" title={<>Without a date check, an LLM said {after.n - afterRight} of {after.n} already-changed rules were still “in force, unchanged”.</>}>
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">RBI updates Directions in place. We asked whether specific paragraphs were in force, amended or deleted on a given date, without the amendment history. Half the dates were before a change, half after.</p>
        <div className="mt-6"><Bars max={after.n} format={(v) => `${v} / ${after.n}`} rows={[
          { label: "Dates before the change: correct", value: beforeRight },
          { label: "Dates after an amendment or deletion: correct", value: afterRight, highlight: true },
        ]} caption="Without a date check the model answers “in force, original” almost every time: right before a change, wrong after it." /></div>
        <T3Timeline />
        <Meaning>A model doesn't know a rule changed unless you tell it, so the retrieval systems check the amendment record for the date you ask about.</Meaning>
        <FinePrint source="tables.08_t3">
          <p>Earlier wording isn't available: RBI consolidates amendments in place, so the corpus has only current text.</p>
          <p>No score is reported for the date filter itself: the gold statuses and the filter come from the same amendment parser, so a perfect score would be circular.</p>
        </FinePrint>
      </Block>
    ),
    moreai: (
      <Block id="moreai" eyebrow="Result 5 · Bigger pipelines aren't automatically better" title={<>{SYSTEM_NAME.final_agentic} scored lowest on differences, and reading whole Directions didn't solve the hard cases.</>}>
        <div className="grid gap-3 md:grid-cols-2">
          <Card><CardBody className="text-[14px] leading-relaxed text-ink-2">
            <p className="text-[15px] font-semibold text-ink">{SYSTEM_NAME.final_agentic}</p>
            <p className="mt-1">This was the system we originally built. It scored lowest on differences, which is why we designed the structured comparator.
              Its fact-checker made the LLM decline when it couldn't back an answer: it answered {pct0(first.answered)} of examples (vs {pct0(filtered.answered)} without it) and found {first.diffFound} of {first.diffTotal} real differences.</p>
          </CardBody></Card>
          <Card><CardBody className="text-[14px] leading-relaxed text-ink-2">
            <p className="text-[15px] font-semibold text-ink">{SYSTEM_NAME.long_context}</p>
            <p className="mt-1">Giving the model every relevant Direction at once did about as well overall ({pct0(longCtx.agree / longCtx.total)} agreement with the expert), so search wasn't the bottleneck, but it still found only {longCtx.diffFound} of {longCtx.diffTotal} real differences.</p>
          </CardBody></Card>
        </div>
        <Meaning>The hard part isn't finding the paragraph; it's noticing what changed between two similar paragraphs. In most LLM errors on real differences the right paragraph was already in context (<Link to="/cases/failures" className="text-accent hover:underline">Failure Map</Link>).</Meaning>
        <FinePrint source="phase4.t1_paired, phase4.t1_systems">
          <p>The fact-checker's change on the main 0–1 accuracy score was {plainCI(verifier.diff, verifier.ci[0], verifier.ci[1])}. Declined answers count as wrong.</p>
          <p>The whole-Directions model could not fit 4 of the 106 examples in its input limit; its numbers use the other 102.</p>
        </FinePrint>
      </Block>
    ),
    metric: (
      <Block id="metric" eyebrow="Result 6 · Testing the test" title="A popular answer-quality score can be fooled: copying the regulation scored twice as high as a real answer.">
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">RePASs scores answers in regulatory AI competitions. We gave it {n("tables.09_t4.n_questions")} RBI questions with four kinds of answers.</p>
        <div className="mt-6"><Bars format={(v) => v.toFixed(2)} caption="Average RePASs score (higher looks better)." rows={[
          { label: "Real answer written for the question", value: t4("genuine") },
          { label: "Just pasting the rule's sentences", value: t4("concatenated"), highlight: true },
          { label: "Pasted sentences with the meaning reversed", value: t4("adv_negated") },
          { label: "Text from an unrelated rule", value: t4("adv_offtopic") },
        ]} /></div>
        <RePASsPanel />
        <Meaning>A system can look great on this score by copying text instead of answering, so we judge systems with expert labels instead.</Meaning>
        <FinePrint source="tables.09_t4">
          <p>This confirms a weakness reported for the same score on other regulations. Our attempt to repair the score did not work well enough to use. Small study: {n("tables.09_t4.n_questions")} questions, one human rater.</p>
        </FinePrint>
      </Block>
    ),
  };

  return (
    <div>
      <PageHead eyebrow="Results" title="Six results, explained without the jargon.">
        Each result has a chart, a short “what this means”, and the fine print. The test set: {resolveKey(R, "phase4.comparator.metrics.n_units") as number ?? 412} rule comparisons checked by an expert, drawn from all {n("tables.01_corpus.directions")} RBI Master Directions.{" "}
        <Term def="One institution's obligation compared with the closest rule for another institution type, labelled same, different, or no matching rule.">What's a comparison?</Term>
      </PageHead>
      <nav className="mt-4 flex flex-wrap gap-2 text-[13px]" aria-label="Results">
        {ORDER[persona].map((k, i) => (
          <a key={k} href={`#${k}`} onClick={(e) => { e.preventDefault(); document.getElementById(k)?.scrollIntoView({ behavior: "smooth" }); }}
            className="rounded-full border border-line bg-panel px-3 py-1 text-ink-2 hover:border-accent">{i + 1}. {LABEL[k]}</a>
        ))}
      </nav>
      <div className="divide-y divide-line">{ORDER[persona].map((k) => <div key={k}>{sections[k]}</div>)}</div>
      <p className="pt-6 text-[14px]"><Link to="/cases" className="text-accent hover:underline">See the comparator on real rules →</Link></p>
    </div>
  );
}
