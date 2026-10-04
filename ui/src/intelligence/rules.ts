// §8.1 deterministic rules. Pure functions: every output carries {rule, inputs, reason, sourceRefs} and a verdict.
import type {
  BandStat, ClaimNumber, FrozenArtifact, MetricResult, PaperClaim, Snapshot, SubmissionTask,
} from "@/domain/types";
import { ciReading, findCIs, fmtCI, NEITHER } from "@/lib/ci";
import { resolveKey } from "@/lib/keys";

export type Verdict = "supported" | "warn" | "fail" | "info" | "ok" | "block" | "unclear" | "missing";

export interface RuleOutput {
  rule: `R${number}`;
  verdict: Verdict;
  title: string;
  reason: string;
  inputs: Record<string, unknown>;
  sourceRefs: string[];
  suggestion?: string;
}

const POS = /\b(improv\w*|rais\w*|beat\w*|outperform\w*|lead\w*|win\w*|lift\w*|increas\w*|gain\w*|helps?|recover\w*|reproduc\w*|sharply)\b/i;
const NEG = /\b(hurt\w*|lower\w*|reduc\w*|decreas\w*|worsen\w*|drops?)\b/i;
const HEDGED = /\b(no significant|not significant|does not|doesn't|no LLM system significantly|not enough|without|cannot|may|might|suggests?)\b/i;

export function effectDirection(sentence: string): "up" | "down" | null {
  if (NEG.test(sentence)) return "down";
  if (POS.test(sentence)) return "up";
  return null;
}

export interface LinkedCI { point: number; lo: number; hi: number; key?: string }

/** Linked CIs for a claim: CIs written in the sentence, else the CI objects behind its numbers' result keys. */
export function linkedCIs(claim: Pick<PaperClaim, "sentence" | "numbers">, results?: unknown): LinkedCI[] {
  const inline = findCIs(claim.sentence).map((c) => ({ point: c.point, lo: c.lo, hi: c.hi }));
  if (inline.length || !results) return inline;
  const out: LinkedCI[] = [];
  for (const n of claim.numbers) {
    for (const k of n.keys) {
      const parent = k.replace(/\.(diff|value|mean|kappa|rho)$/, "");
      const obj = resolveKey(results, parent) as Record<string, unknown> | undefined;
      if (obj && typeof obj === "object") {
        const ci = (obj.ci as number[] | undefined) ?? (typeof obj.ci_low === "number" ? [obj.ci_low as number, obj.ci_high as number] : undefined);
        const point = (obj.diff ?? obj.value ?? obj.mean) as number | undefined;
        if (ci && typeof point === "number") { out.push({ point, lo: ci[0], hi: ci[1], key: parent }); break; }
      }
    }
  }
  return out;
}

/** R1 CI over-claim: an effect verb backed by a CI that includes 0, or excludes 0 in the opposite direction. */
export function r1ClaimCheck(claim: Pick<PaperClaim, "sentence" | "numbers">, results?: unknown): RuleOutput {
  const dir = effectDirection(claim.sentence);
  const cis = linkedCIs(claim, results);
  const base = { rule: "R1" as const, title: "Claim check", inputs: { sentence: claim.sentence, direction: dir, cis },
    sourceRefs: cis.map((c) => c.key).filter(Boolean) as string[] };
  if (!dir) return { ...base, verdict: "info", reason: "No effect verb; nothing to check." };
  if (!cis.length) return { ...base, verdict: "info", reason: "Effect verb, but no CI is linked to this sentence." };
  if (HEDGED.test(claim.sentence)) return { ...base, verdict: "supported", reason: "The sentence is hedged (states no or uncertain effect)." };
  const bad = cis.filter((c) => {
    const r = ciReading(c.lo, c.hi);
    return r === NEITHER || (dir === "up" && r.includes("below")) || (dir === "down" && r.includes("above"));
  });
  if (!bad.length) {
    const c = cis[0];
    return { ...base, verdict: "supported",
      reason: `The effect verb is backed by ${fmtCI(c.point, c.lo, c.hi, { signed: true, reading: true })}, which excludes 0 in the asserted direction.` };
  }
  const c = bad[0];
  return { ...base, verdict: "warn",
    reason: `Effect verb "${(claim.sentence.match(dir === "up" ? POS : NEG) ?? [""])[0]}" but ${fmtCI(c.point, c.lo, c.hi, { signed: true, reading: true })}.`,
    suggestion: "Hedge: \"… changes by X [CI] (the interval includes 0)\" or \"no significant effect\"." };
}

const T2_BIAS: Record<string, string> = {
  t2_xclass_t1: "bias_t2_xclass_t1", t2_xclass_p2002: "bias_t2_xclass_p2002", t2_supp_p2003: "bias_t2_supp_p2003",
};

/** R2 by-construction: any T2 result carries its dataset's bias statement and the target-class-only relevance caveat. */
export function r2ByConstruction(datasetId: string, s: Pick<Snapshot, "results">): RuleOutput {
  const bias = resolveKey(s.results, `tables.06_t2_retrieval.p3001.${datasetId}.bias`) as string | undefined;
  return { rule: "R2", verdict: "info", title: "By construction", inputs: { datasetId },
    reason: `${bias ?? "Biased relevance set."} Relevance covers only the target-class counterpart, so class filtering gains partly by construction.`,
    sourceRefs: [`tables.06_t2_retrieval.p3001.${datasetId}.bias`, `caveat:by_construction`, `caveat:${T2_BIAS[datasetId] ?? ""}`] };
}

/** R3 circularity: a T3 filter-on result carries the caveat and is blocked from any "wins" / showcase view. */
export function r3Circularity(m: { datasetId?: string; circular?: boolean; sourceKey?: string }): RuleOutput & { blockShowcase: boolean } {
  const circular = !!m.circular || (m.datasetId === "t3" && /\.on\./.test(m.sourceKey ?? ""));
  return { rule: "R3", verdict: circular ? "block" : "ok", title: "Circularity", inputs: m, blockShowcase: circular,
    reason: circular ? "Gold and temporal filter come from the same deterministic parser: circular by construction. Never shown as a win." : "Not a T3 filter-on result.",
    sourceRefs: circular ? ["caveat:circular", m.sourceKey ?? ""] : [] };
}

/** R4 item-set mismatch: long-context (n = 102) must not be compared with n = 106 numbers. */
export function r4ItemSet(ns: number[], hasLongContext: boolean): RuleOutput {
  const mixed = hasLongContext && new Set(ns).size > 1;
  return { rule: "R4", verdict: mixed ? "warn" : "ok", title: "Item-set mismatch", inputs: { ns, hasLongContext },
    reason: mixed ? "Long-context answered 102 items; use the same-items comparisons (phase4.t1_paired \"(same items)\")." : "Same item set.",
    sourceRefs: mixed ? ["phase4.long_context_same_items", "caveat:item_set_102"] : [] };
}

/** R5 single-expert dependency: anything derived from T1 gold inherits the caveat. */
export function r5SingleExpert(upstream: string[]): RuleOutput {
  const dep = upstream.some((n) => n === "dataset:t1_gold_v1" || n === "task:T1");
  return { rule: "R5", verdict: dep ? "info" : "ok", title: "Single-expert dependency", inputs: { upstreamCount: upstream.length },
    reason: dep ? "Derived from the single-expert T1 gold (rater_1); agreement was measured on a separate sample only." : "Not derived from T1 gold.",
    sourceRefs: dep ? ["caveat:single_expert"] : [] };
}

/** R6 number drift: a document number with no results key (within rounding). Integers/1-decimal values are "?" not ✗. */
export function r6NumberDrift(n: ClaimNumber): RuleOutput {
  const metricLike = /\d\.\d{2,}/.test(n.text);
  if (n.nKeys > 0) return { rule: "R6", verdict: "ok", title: "Number drift", inputs: { ...n }, reason: `Matched ${n.nKeys} key(s).`, sourceRefs: n.keys };
  return { rule: "R6", verdict: metricLike ? "fail" : "unclear", title: "Number drift", inputs: { ...n },
    reason: metricLike ? `${n.text} matches no key in the public sources (results_v2.json, error analysis, phase metrics).`
      : `${n.text} is not in the public sources; it may be a named private constant (see gap G-22).`, sourceRefs: [] };
}

const PLACEHOLDER = /\\placeholder\{[^}]*\}|DOI to be assigned|\bTODO\b|\[verify\]/g;

/** R7 placeholders. */
export function r7Placeholders(text: string, file: string): RuleOutput[] {
  return [...text.matchAll(PLACEHOLDER)].map((m) => ({ rule: "R7" as const, verdict: "missing" as const, title: "Placeholder",
    inputs: { file, text: m[0] }, reason: `${m[0]} in ${file}`, sourceRefs: [file] }));
}

/** R8 terminology collision: one label used for two different referents. */
export function r8Terminology(usages: { label: string; referent: string; where: string }[]): RuleOutput[] {
  const by = new Map<string, Set<string>>();
  usages.forEach((u) => (by.get(u.label) ?? by.set(u.label, new Set()).get(u.label)!).add(u.referent));
  return [...by.entries()].map(([label, refs]) => ({ rule: "R8" as const, verdict: refs.size > 1 ? "unclear" as const : "ok" as const,
    title: "Terminology", inputs: { label, referents: [...refs] },
    reason: refs.size > 1 ? `"${label}" names ${refs.size} things: ${[...refs].join(" / ")}` : `"${label}" has one meaning.`,
    sourceRefs: usages.filter((u) => u.label === label).map((u) => u.where) }));
}

/** R9 small-n slice. */
export function r9SmallN(n: number, label: string): RuleOutput {
  return { rule: "R9", verdict: n < 20 ? "warn" : "ok", title: "Small-n slice", inputs: { n, label },
    reason: n < 20 ? `Only ${n} items in this slice: the interval is wide; read as descriptive only.` : `n = ${n}.`,
    sourceRefs: n < 20 ? ["caveat:per_class_small_n"] : [] };
}

/** R10 freeze integrity. */
export function r10Freeze(rows: FrozenArtifact[]): RuleOutput {
  const bad = rows.filter((r) => r.status !== "match");
  return { rule: "R10", verdict: bad.length ? "fail" : "ok", title: "Freeze integrity", inputs: { checked: rows.length, bad: bad.map((b) => b.path) },
    reason: bad.length ? `${bad.length} frozen artefact(s) do not match their recorded sha256: ${bad.map((b) => b.path).join(", ")}`
      : `All ${rows.length} frozen artefacts match their recorded sha256.`, sourceRefs: rows.map((r) => r.path) };
}

/** R11 deadline risk on the critical path (dependency chain to CMT). */
export function r11Deadline(tasks: SubmissionTask[], now: Date): RuleOutput[] {
  const due = (t: SubmissionTask) => new Date(`${t.due}T23:59:00+05:30`).getTime();
  return tasks.filter((t) => t.status !== "done").map((t) => {
    const slackDays = (due(t) - now.getTime()) / 86_400_000;
    const verdict: Verdict = slackDays < 0 ? "fail" : slackDays < 1 ? "warn" : "ok";
    return { rule: "R11" as const, verdict, title: "Deadline risk", inputs: { task: t.id, due: t.due, slackDays: Number(slackDays.toFixed(2)) },
      reason: slackDays < 0 ? `${t.title}: overdue by ${Math.abs(slackDays).toFixed(1)} days.` : slackDays < 1 ? `${t.title}: less than 1 day of slack.`
        : `${t.title}: ${slackDays.toFixed(1)} days left.`, sourceRefs: [t.id] };
  });
}

/** R12 undefined scoring: is abstention handling documented? */
export function r12Scoring(masterText: string): RuleOutput {
  const ok = /How abstentions are scored/.test(masterText) && /Scoring asymmetry/.test(masterText);
  return { rule: "R12", verdict: ok ? "ok" : "unclear", title: "Abstention scoring", inputs: {},
    reason: ok ? "Documented in Master Document v2 §9.2 (A4) and the scoring-asymmetry note (A11)." : "Abstention handling is not documented.",
    sourceRefs: ["reports/final/RBI-ObliBench_Master_Document_v2.md §9.2"] };
}

/** R13 missing CI: a metric without an interval where its siblings have one. */
export function r13MissingCI(metrics: MetricResult[]): RuleOutput[] {
  const groups = new Map<string, MetricResult[]>();
  metrics.forEach((m) => (groups.get(m.datasetId) ?? groups.set(m.datasetId, []).get(m.datasetId)!).push(m));
  const out: RuleOutput[] = [];
  for (const [ds, ms] of groups) {
    if (!ms.some((m) => m.ci)) continue;
    const missing = [...new Set(ms.filter((m) => !m.ci).map((m) => m.metric))];
    missing.forEach((metric) => out.push({ rule: "R13", verdict: "unclear", title: "Missing CI", inputs: { datasetId: ds, metric },
      reason: `${metric} has no CI while sibling metrics on ${ds} do (A5: "CIs not computed").`, sourceRefs: ms.filter((m) => m.metric === metric).map((m) => m.sourceKey) }));
  }
  return out;
}

/** R14 confidence honesty: a badge needs its band's empirical accuracy + CI, and the band needs n ≥ 20. */
export function r14Confidence(b: Partial<BandStat> | null | undefined): RuleOutput {
  const missing = !b || b.accuracy === null || b.accuracy === undefined || !b.wilsonCI;
  const small = !!b && typeof b.n === "number" && b.n < 20;
  const verdict: Verdict = missing || small || b?.hidden ? "block" : "ok";
  return { rule: "R14", verdict, title: "Confidence honesty", inputs: { band: b?.band, n: b?.n },
    reason: verdict === "block" ? (missing ? "Insufficient evidence: no empirical accuracy and CI for this band." : `Insufficient evidence: band n = ${b?.n} < 20.`)
      : `Band ${b?.band}: empirical accuracy with Wilson CI, n = ${b?.n}.`, sourceRefs: ["ui/src/data/confidence_model_v1.json"] };
}

export const TERMINOLOGY_USAGES = [
  { label: "Ablation A", referent: "toggle: class filter", where: "MD v2 §9.7" },
  { label: "Ablation A", referent: "toggle: class filter", where: "MD v2 §9.3 row label (ablation A toggle)" },
  { label: "Ablation B", referent: "toggle: temporal filter", where: "MD v2 §9.7" },
  { label: "Ablation C", referent: "toggle: verifier", where: "MD v2 §9.7" },
  { label: "class-blind + verifier", referent: "system ablation_a", where: "MD v2 §8, §9.3, §9.8" },
  { label: "v3.6", referent: "rule: flag derivation", where: "MD v2 §5 (A8)" },
  { label: "Guidelines v3", referent: "guideline family", where: "MD v2 §5 (A8)" },
];
