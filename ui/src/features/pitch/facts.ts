// Plain-language facts for the public pitch site. Every number is read from reports/results_v2.json (via the snapshot)
// or the frozen confidence model; nothing is typed in by hand. `source` keeps each fact traceable.
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { resolveKey } from "@/lib/keys";

const num = (s: Snapshot, k: string) => resolveKey(s.results, k) as number;
const obj = <T,>(s: Snapshot, k: string) => resolveKey(s.results, k) as T;

type Confusion = Record<string, Record<string, number>>;

export const PLAIN_SYSTEMS: { id: string; name: string; blurb: string; ours?: boolean }[] = [
  { id: "comparator", name: "Our field-by-field comparator", blurb: "Lists 13 details of both rules (who, what, threshold, deadline…) and a fixed rule decides.", ours: true },
  { id: "class_blind", name: "AI assistant (plain search)", blurb: "A language model given the most similar paragraphs from all Directions." },
  { id: "class_aware", name: "AI assistant (filtered to the right institution)", blurb: "The same model, but it only sees paragraphs for the institution type you asked about." },
  { id: "long_context", name: "AI reading whole documents", blurb: "The model reads every relevant Direction in one go (up to 100K tokens)." },
  { id: "final_agentic", name: "AI with an automatic fact-checker", blurb: "Filtered AI plus a checker that makes it retry or decline when it can't back an answer." },
];

export interface SystemOutcome {
  id: string; name: string; ours?: boolean; blurb: string;
  diffFound: number; diffTotal: number; falseAlarms: number; agree: number; total: number; answeredShare: number; source: string;
}

export function systemOutcomes(s: Snapshot): SystemOutcome[] {
  return PLAIN_SYSTEMS.map((p) => {
    const key = p.id === "comparator" ? "phase4.comparator.different.judgement_confusion" : `phase4.t1_different.${p.id}.judgement_confusion`;
    const c = obj<Confusion>(s, key);
    const total = Object.values(c).reduce((a, r) => a + Object.values(r).reduce((x, y) => x + y, 0), 0);
    const agree = (["same", "different", "none"] as const).reduce((a, k) => a + (c[k]?.[k] ?? 0), 0);
    const covKey = p.id === "comparator" ? "phase4.comparator.metrics.coverage.value" : `phase4.t1_systems.${p.id}.coverage.value`;
    return { ...p, diffFound: c.different.different, diffTotal: Object.values(c.different).reduce((a, b) => a + b, 0),
      falseAlarms: c.same.different + c.none.different, agree, total, answeredShare: num(s, covKey), source: key };
  });
}

export function corpusFacts(s: Snapshot) {
  return {
    directions: num(s, "tables.01_corpus.directions"),
    paragraphs: num(s, "tables.01_corpus.paragraphs"),
    institutionTypes: num(s, "tables.01_corpus.core_entity_classes"),
    headings: num(s, "tables.01_corpus.entity_classes"),
    topics: num(s, "tables.01_corpus.subject_families"),
    examples: num(s, "tables.05_t1_benchmark.validated"),
    comparisons: s.classUnits.length,
    realDifferences: num(s, "phase4.missed_by_every_llm_system.gold_different_units"),
    missedByAllAI: num(s, "phase4.missed_by_every_llm_system.A_all_five_answered.missed"),
    comparatorRecovers: num(s, "phase4.missed_by_every_llm_system.A_all_five_answered.comparator_correct"),
  };
}

export function searchFacts(s: Snapshot) {
  const base = "tables.06_t2_retrieval.p3001.t2_xclass_t1";
  const sys = (id: string) => obj<{ recall: { mean: number }; ndcg: { mean: number } }>(s, `${base}.systems.${id}`);
  return {
    queries: num(s, `${base}.n_scored`),
    rows: [
      { name: "Keyword search", top10: sys("bm25").recall.mean, quality: sys("bm25").ndcg.mean },
      { name: "Meaning-based search", top10: sys("dense").recall.mean, quality: sys("dense").ndcg.mean },
      { name: "Both combined (standard)", top10: sys("hybrid_rrf").recall.mean, quality: sys("hybrid_rrf").ndcg.mean },
      { name: "Combined + filtered to the right institution (ours)", top10: sys("class_aware").recall.mean, quality: sys("class_aware").ndcg.mean, ours: true },
    ],
    source: `${base}.systems`,
  };
}

/** T3 without the amendment history: questions asked AFTER a rule changed (amended or deleted) vs before it. */
export function dateFacts(s: Snapshot) {
  const after = obj<{ n: number; status_exact_match: number }>(s, "tables.08_t3.t3.off.by_side.after");
  const before = obj<{ n: number; status_exact_match: number }>(s, "tables.08_t3.t3.off.by_side.before");
  const afterRight = Math.round(after.status_exact_match * after.n);
  return { changed: after.n, wrong: after.n - afterRight, right: afterRight, beforeN: before.n, beforeRight: Math.round(before.status_exact_match * before.n),
    source: "tables.08_t3.t3.off.by_side" };
}

export function metricFacts(s: Snapshot) {
  const t = (k: string) => num(s, `tables.09_t4.by_type.${k}.composite_score.mean`);
  return { genuine: t("genuine"), pasted: t("concatenated"), negated: t("adv_negated"), offTopic: t("adv_offtopic"),
    questions: num(s, "tables.09_t4.n_questions"), source: "tables.09_t4.by_type" };
}

export function trustFacts(model: ConfidenceModel | null) {
  if (!model) return null;
  const e = model.models.M2.eval;
  const band = (b: string) => e.bands.find((x) => x.band === b)!;
  return { high: band("High"), medium: band("Medium"), low: band("Low"), coverage: e.operatingPoint.coverage, base: e.baseRate,
    sameInHigh: e.bandComposition.High?.same?.n ?? 0, highN: band("High").n, experimental: e.experimental, ece: e.ece };
}

export function agreementFact(s: Snapshot) {
  const r = s.reliability.find((x) => x.id === "fleiss_class_row");
  return r ? { kappa: r.value, items: r.n } : null;
}

export const FIELD_LABEL: Record<string, string> = {
  actor: "Who must comply", action: "What they must do", object: "What it applies to", scope: "Scope", condition: "Condition",
  threshold: "Threshold", amount: "Amount", percentage: "Percentage", frequency: "How often", deadline: "Deadline",
  exception: "Exceptions", documentation: "Records to keep", reporting: "Reporting",
};

/** Fields that carry a substantive requirement (who/what/object differ trivially between institution types). */
const FIELD_WEIGHT: Record<string, number> = {
  reporting: 4, amount: 3, percentage: 3, threshold: 3, deadline: 3, frequency: 3, exception: 2, documentation: 2, scope: 2, condition: 1,
};

function trivialValue(v: string | null, classes: string[]) {
  if (!v) return true;
  return /paragraph\s+\d+/i.test(v) || classes.some((c) => v.toLowerCase().includes(c.toLowerCase()));
}

/** A real benchmark case for the story: a true difference every AI assistant missed and the comparator caught,
 *  chosen for the clearest substantive difference (both sides quoted, no paragraph cross-references). */
export function showcaseExample(s: Snapshot) {
  const items = new Map(s.t1Items.map((i) => [i.id, i]));
  const classes = [...new Set(s.t1Items.flatMap((i) => [i.sourceClass, ...i.comparedClasses]))];
  let best: { score: number; ex: ReturnType<typeof build> } | null = null;
  function build(u: Snapshot["classUnits"][number]) {
    const cf = s.comparatorFields[u.id];
    if (!cf?.parseOk || !cf.decisivePid) return null;
    const diffs = cf.rows.filter((r) => FIELD_WEIGHT[r.field] && ["differs", "only_source", "only_target"].includes(r.status)
      && r.sourceValue && r.targetValue && !trivialValue(r.sourceValue, classes) && !trivialValue(r.targetValue, classes));
    const item = items.get(u.itemId)!;
    const src = s.pointers[item.sourcePid];
    const tgt = s.pointers[cf.decisivePid];
    if (!diffs.length || !src?.excerpt || !tgt?.excerpt) return null;
    return { unit: u, item, cf, diffs, src, tgt };
  }
  for (const u of s.classUnits) {
    if (!u.missedA || u.predictions.comparator?.judgement !== "different") continue;
    const ex = build(u);
    if (!ex) continue;
    const score = ex.diffs.reduce((a, r) => a + (FIELD_WEIGHT[r.field] ?? 0), 0);
    if (!best || score > best.score) best = { score, ex };
  }
  return best?.ex ?? null;
}
