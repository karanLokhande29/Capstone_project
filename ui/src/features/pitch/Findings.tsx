import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useData } from "@/data/store";
import { Card, CardBody } from "@/components/ui/primitives";
import { resolveKey } from "@/lib/keys";
import { agreementFact, corpusFacts, dateFacts, metricFacts, searchFacts, systemOutcomes, trustFacts } from "./facts";
import { usePersona, type Persona } from "./persona";
import { Bars, Block, FinePrint, Meaning, pct0, plainCI, Term } from "./ui";

type Section = "differences" | "search" | "trust" | "dates" | "moreai" | "metric";
const ORDER: Record<Persona, Section[]> = {
  compliance: ["differences", "search", "trust", "dates", "moreai", "metric"],
  researcher: ["differences", "moreai", "metric", "search", "trust", "dates"],
  investor: ["differences", "trust", "search", "dates", "moreai", "metric"],
};

export default function Findings() {
  const s = useData((st) => st.snapshot)!;
  const model = useData((st) => st.confidence);
  const persona = usePersona((p) => p.persona);
  const loc = useLocation();
  useEffect(() => {
    if (loc.hash) document.getElementById(loc.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [loc.hash]);
  const c = corpusFacts(s);
  const out = systemOutcomes(s);
  const ours = out.find((o) => o.ours)!;
  const assistants = out.filter((o) => !o.ours && o.id !== "final_agentic");
  const best = [...assistants].sort((a, b) => b.diffFound - a.diffFound)[0];
  const checker = out.find((o) => o.id === "final_agentic")!;
  const longCtx = out.find((o) => o.id === "long_context")!;
  const search = searchFacts(s);
  const trust = trustFacts(model);
  const dates = dateFacts(s);
  const metric = metricFacts(s);
  const agreement = agreementFact(s);
  const pre = resolveKey(s.results, "phase4.preregistered_comparisons.comparator − class_aware.judgement.different_f1") as { diff: number; ci: [number, number] };
  const verifier = resolveKey(s.results, "phase4.t1_paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1") as { diff: number; ci: [number, number] };

  const sections: Record<Section, ReactNode> = {
    differences: (
      <Block id="differences" eyebrow="Result 1 · The core problem" title={<>Spotting what's different: our comparator finds {Math.round(ours.diffFound / Math.max(1, best.diffFound))}× more real differences than the best AI assistant.</>}>
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          The expert found <b className="text-ink">{c.realDifferences}</b> cases where two institution types have a rule on the same topic but with a different requirement
          (a threshold, a deadline, a scope or an exception). How many of those did each system catch?
        </p>
        <div className="mt-6">
          <Bars max={ours.diffTotal} format={(v) => `${v}`}
            rows={[ours, ...assistants, checker].map((o) => ({ label: o.name, value: o.diffFound, highlight: o.ours, note: `${o.diffFound} of ${o.diffTotal} real differences · ${o.falseAlarms} false alarms` }))}
            caption="How to read this: longer bar = more real differences caught. False alarms are rules flagged as different that the expert judged the same or unmatched." />
        </div>
        <Meaning>
          Ordinary AI assistants mostly say “same” or “no match” when the rules actually differ, which is the most expensive mistake in compliance.
          Making the model compare the two rules detail by detail catches far more. The trade-off is over-flagging ({ours.falseAlarms} false alarms),
          so flagged differences should be reviewed by a person; the confidence score below does that triage.
        </Meaning>
        <Card className="mt-4"><CardBody className="grid gap-4 text-[14px] sm:grid-cols-3">
          <div><p className="num text-[22px] font-semibold">{c.missedByAllAI}</p><p className="text-ink-2">real differences that none of the five AI assistants flagged</p></div>
          <div><p className="num text-[22px] font-semibold">{c.comparatorRecovers}</p><p className="text-ink-2">of those caught by our comparator</p></div>
          <div><p className="num text-[22px] font-semibold">{pct0(ours.agree / ours.total)} vs {pct0(best.agree / best.total)}</p><p className="text-ink-2">overall agreement with the expert: ours vs best AI assistant (the AI wins on overall agreement by saying “same” more often)</p></div>
        </CardBody></Card>
        <FinePrint source="phase4.t1_different, phase4.comparator, phase4.preregistered_comparisons">
          <p>Labels come from one expert. A separate 30-item sample labelled by three people agreed well on these judgements (agreement score {agreement?.kappa.toFixed(2)}), but the main labels were not double-checked.</p>
          <p>The comparison was planned before seeing results: the comparator's prompt and decision rule were frozen before it was run on the test set. On the score for spotting differences (0 to 1) its advantage over the filtered AI assistant is {plainCI(pre.diff, pre.ci[0], pre.ci[1])}.</p>
          <p>All AI systems use one fast, low-cost model (Gemini 3.5 Flash-Lite). Larger models may do better; that is the next experiment.</p>
          <p>The comparator was shown the same two candidate paragraphs the expert saw; with automatically retrieved paragraphs it may behave differently.</p>
        </FinePrint>
      </Block>
    ),
    search: (
      <Block id="search" eyebrow="Result 2 · Finding the right rule" title="Telling the search which institution you mean makes it far better at finding the matching rule.">
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          Task: start from one institution's rule and find the matching rule for another institution type ({search.queries} test searches).
          We measured how often the correct paragraph appears in the top 10 results.
        </p>
        <div className="mt-6"><Bars rows={search.rows.map((r) => ({ label: r.name, value: r.top10, highlight: r.ours, note: `ranking quality ${r.quality.toFixed(2)} on a 0–1 scale` }))} format={pct0} caption="Correct paragraph in the top 10 results. Ranking quality also rewards putting it near the top." /></div>
        <Meaning>
          Generic search keeps returning the original institution's own rule or near-duplicates. Restricting to the institution type you asked about puts the right counterpart
          at or near the top, so the comparison starts from the right document.
        </Meaning>
        <FinePrint source={search.source}>
          <p>This gain is partly built into the test: the correct answers were defined only within the target institution's Directions, so filtering to that institution has a head start.</p>
          <p>The test answers were collected with help from one of the search methods (meaning-based search), which slightly favours it.</p>
          <p>Better search alone did not make the AI assistants better at judging same vs different; that is why the comparator matters.</p>
        </FinePrint>
      </Block>
    ),
    trust: trust ? (
      <Block id="trust" eyebrow="Result 3 · Knowing when to trust it" title={<>When the system says “high confidence”, it was right {pct0(trust.high.accuracy ?? 0)} of the time.</>}>
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          Every comparator answer gets a confidence level. We built the score on a separate practice set, froze it, and then measured it on the test set it had never seen.
        </p>
        <div className="mt-6">
          <Bars format={pct0} rows={[trust.high, trust.medium, trust.low].map((b) => ({
            label: `${b.band} confidence`, value: b.accuracy ?? 0, highlight: b.band === "High",
            note: `right ${b.correct} of ${b.n} times (likely range ${pct0(b.wilsonCI![0])}–${pct0(b.wilsonCI![1])})` }))}
            caption="Share of answers in each confidence level that matched the expert." />
        </div>
        <Meaning>
          If you only accept high-confidence answers automatically, {pct0(trust.coverage)} of comparisons need no review and are right about {pct0(trust.high.accuracy ?? 0)} of the time.
          Everything else goes to a person. Honest limit: high confidence is mostly given to “same rule” answers ({trust.sameInHigh} of {trust.highN}); claimed differences are
          usually medium or low confidence, so they get a human look.
        </Meaning>
        <FinePrint source="ui/src/data/confidence_model_v1.json → models.M2.eval">
          <p>Measured on {trust.base.n} expert-labelled comparisons from one expert, so the ranges are wide.</p>
          <p>Calibration error is {trust.ece.toFixed(3)} (0 = confidence matches accuracy exactly). Scores are never adjusted after the test.</p>
        </FinePrint>
      </Block>
    ) : null,
    dates: (
      <Block id="dates" eyebrow="Result 4 · Dates matter" title={<>Without date checks, an AI said {dates.wrong} of {dates.changed} already-changed rules were still “in force, unchanged”.</>}>
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          RBI updates Directions in place. We asked an AI whether specific paragraphs were in force, amended or deleted on a given date, without giving it the amendment history.
          Half the questions were about dates before a change, half about dates after it.
        </p>
        <div className="mt-6"><Bars max={dates.changed} format={(v) => `${v} / ${dates.changed}`} rows={[
          { label: "Dates before the change: answered correctly", value: dates.beforeRight },
          { label: "Dates after the rule was amended or deleted: answered correctly", value: dates.right, highlight: true },
        ]} caption="The AI answers “in force, unchanged” almost every time, which is right before a change and wrong after it." /></div>
        <Meaning>A model doesn't know a rule changed unless you tell it. The system therefore checks the amendment record for the date you ask about before answering.</Meaning>
        <FinePrint source={dates.source}>
          <p>We don't report a score for our date filter: the test answers and the filter were produced by the same parsing tool, so a perfect score would prove nothing.</p>
          <p>RBI publishes only the current, amended text, so the system can say a rule changed but cannot show the old wording.</p>
        </FinePrint>
      </Block>
    ),
    moreai: (
      <Block id="moreai" eyebrow="Result 5 · Bigger pipelines aren't automatically better" title="An automatic fact-checker made the AI worse, and reading whole documents didn't solve the hard cases.">
        <div className="grid gap-3 md:grid-cols-2">
          <Card><CardBody className="text-[14px] leading-relaxed text-ink-2">
            <p className="text-[15px] font-semibold text-ink">The fact-checker</p>
            <p className="mt-1">It made the AI decline when it couldn't back up its answer. It ended up answering only {pct0(checker.answeredShare)} of examples (vs {pct0(out.find((o) => o.id === "class_aware")!.answeredShare)} without it),
              often declining answers that were right, and found {checker.diffFound} of {checker.diffTotal} real differences.</p>
          </CardBody></Card>
          <Card><CardBody className="text-[14px] leading-relaxed text-ink-2">
            <p className="text-[15px] font-semibold text-ink">Reading whole documents</p>
            <p className="mt-1">Giving the AI every relevant Direction at once did about as well overall ({pct0(longCtx.agree / longCtx.total)} agreement with the expert), so search wasn't the bottleneck,
              but it still found only {longCtx.diffFound} of {longCtx.diffTotal} real differences.</p>
          </CardBody></Card>
        </div>
        <Meaning>The hard part isn't finding the right paragraph; it's noticing what changed between two similar paragraphs. That is what the comparator is designed to do.</Meaning>
        <FinePrint source="phase4.t1_paired, phase4.t1_systems">
          <p>The fact-checker's change on the main 0-to-1 accuracy score was {plainCI(verifier.diff, verifier.ci[0], verifier.ci[1])}. Declined answers count as wrong in these scores.</p>
          <p>The whole-document model could not fit 4 of the 106 examples in its input limit; its numbers use the other 102.</p>
        </FinePrint>
      </Block>
    ),
    metric: (
      <Block id="metric" eyebrow="Result 6 · Testing the test" title="A popular answer-quality score can be fooled: pasting regulation text scored twice as high as a real answer.">
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
          RePASs is used in regulatory AI competitions to score answers. We gave it {metric.questions} RBI questions with four kinds of answers.
        </p>
        <div className="mt-6"><Bars format={(v) => v.toFixed(2)} rows={[
          { label: "Real answer written for the question", value: metric.genuine },
          { label: "Just pasting the rule's sentences", value: metric.pasted, highlight: true },
          { label: "Pasted sentences with the meaning reversed", value: metric.negated },
          { label: "Text from an unrelated rule", value: metric.offTopic },
        ]} caption="Average RePASs score (higher looks better)." /></div>
        <Meaning>A system can look great on this score by copying text instead of answering. We don't rely on it to judge our system; we use expert labels instead.</Meaning>
        <FinePrint source={metric.source}>
          <p>This confirms a weakness reported for the same score on other regulations. Our attempt to fix the score did not work well enough to use.</p>
          <p>Small study: {metric.questions} questions and one human rater.</p>
        </FinePrint>
      </Block>
    ),
  };

  return (
    <div>
      <header className="pb-2 pt-10 sm:pt-14">
        <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">Results</p>
        <h1 className="max-w-3xl text-[30px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[38px]">Six things we learned, explained without the jargon.</h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-2">
          Each result has a chart, a short “what this means”, and the fine print (caveats and how sure we are). The test set: {c.comparisons} rule comparisons
          checked by an expert, drawn from all {c.directions} RBI Master Directions. <Term def="A comparison of one institution's rule with the closest rule for another institution type, labelled same, different, or no matching rule.">What's a comparison?</Term>
        </p>
        <nav className="mt-5 flex flex-wrap gap-2 text-[13px]" aria-label="Results">
          {ORDER[persona].map((k, i) => (
            <a key={k} href={`#${k}`} onClick={(e) => { e.preventDefault(); document.getElementById(k)?.scrollIntoView({ behavior: "smooth" }); }}
              className="rounded-full border border-line bg-panel px-3 py-1 text-ink-2 hover:border-accent">{i + 1}. {{ differences: "Spotting differences", search: "Finding the rule", trust: "Confidence", dates: "Dates", moreai: "Bigger pipelines", metric: "Gamed metrics" }[k]}</a>
          ))}
        </nav>
      </header>
      <div className="divide-y divide-line">{ORDER[persona].map((k) => <div key={k}>{sections[k]}</div>)}</div>
      <p className="pt-6 text-[14px]"><Link to="/demo" className="text-accent hover:underline">See the comparator on real rules →</Link></p>
    </div>
  );
}
