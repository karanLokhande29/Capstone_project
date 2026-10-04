import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { pathUpTo, reach, type Derived } from "@/data/derive";
import { linkedCIs, r1ClaimCheck, r11Deadline } from "@/intelligence/rules";
import { excludesZero } from "@/lib/ci";

export interface QueryRow { label: string; detail?: string; node?: string; href?: string }
export interface QueryResult { title: string; summary: string; rows: QueryRow[]; sourceKeys: string[]; href?: string }
export interface Ctx { s: Snapshot; d: Derived; model: ConfidenceModel | null; now: Date }
export interface PaletteQuery { id: string; label: string; keywords: string[]; run: (c: Ctx) => QueryResult }

/** Deterministic, typed queries: same answer every time, every row traceable. Used by ⌘K and the assistant's palette route. */
export const QUERIES: PaletteQuery[] = [
  {
    id: "ci-includes-zero", label: "Which claims rest on a CI that includes 0?", keywords: ["ci", "includes 0", "over-claim", "claims", "zero"],
    run: ({ s }) => {
      const rows = s.claims.map((c) => ({ c, r: r1ClaimCheck(c, s.results), cis: linkedCIs(c, s.results).filter((x) => !excludesZero(x.lo, x.hi)) }))
        .filter((x) => x.cis.length > 0);
      const warn = rows.filter((x) => x.r.verdict === "warn");
      return {
        title: "Claims resting on a CI that includes 0",
        summary: `${rows.length} sentence(s) cite or resolve to a CI that includes 0; ${warn.length} of them pair it with an unhedged effect verb (R1 ⚠). The rest state no or uncertain effect.`,
        rows: [...warn, ...rows.filter((x) => x.r.verdict !== "warn")].map(({ c, r, cis }) => ({ label: c.sentence.slice(0, 160),
          detail: `${c.doc} · ${c.section} · CI [${cis[0].lo.toFixed(3)}, ${cis[0].hi.toFixed(3)}] · R1 ${r.verdict}`, node: c.doc === "master" ? undefined : `claim:${c.id}`, href: "/claims" })),
        sourceKeys: ["claims (main.tex, tables, MD v2)"], href: "/claims?filter=r1",
      };
    },
  },
  {
    id: "single-expert-deps", label: "Show everything that depends on the single-expert gold", keywords: ["single-expert", "gold", "depends", "rater"],
    run: ({ d }) => {
      const nodes = reach(d, "dataset:t1_gold_v1", "down");
      return { title: "Downstream of the single-expert T1 gold (R5)", summary: `${nodes.length} node(s) inherit the single-expert caveat.`,
        rows: nodes.map((n) => ({ label: d.nodes.get(n)?.title ?? n, detail: n.split(":")[0], node: n })), sourceKeys: ["dataset:t1_gold_v1"] };
    },
  },
  {
    id: "trace-f4", label: "Trace Finding 4 back to its RQ", keywords: ["trace", "finding 4", "f4", "verifier", "rq"],
    run: ({ d }) => {
      const path = pathUpTo(d, "finding:F4", "rq") ?? [];
      const viaPaired = pathUpTo(d, "paired:t1:Ablation C on T1: final agentic − class-aware:flag_macro_f1", "rq") ?? [];
      const rows = (viaPaired.length ? ["finding:F4", ...viaPaired] : path).map((n) => ({ label: d.nodes.get(n)?.title ?? n, detail: n.split(":")[0], node: n }));
      return { title: "Finding 4 → RQ", summary: rows.map((r) => r.detail).join(" ← "), rows, sourceKeys: ["phase4.t1_paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1"] };
    },
  },
  {
    id: "missed-def-a", label: "Show `different` units missed by every LLM (definition A)", keywords: ["different", "missed", "definition a", "every llm"],
    run: ({ s, d }) => {
      const units = s.classUnits.filter((u) => u.missedA);
      const recovered = units.filter((u) => u.predictions.comparator?.judgement === "different").length;
      return { title: "`different` units missed by every LLM system (definition A)",
        summary: `${units.length} of ${s.classUnits.filter((u) => u.goldJudgement === "different").length} gold \`different\` units; the comparator gets ${recovered} of them right.`,
        rows: units.map((u) => ({ label: `${d.itemById.get(u.itemId)?.sourceClass} → ${u.classId}`, detail: `${u.itemId} · comparator: ${u.predictions.comparator?.judgement}`, node: `unit:${u.id}` })),
        sourceKeys: ["phase4.missed_by_every_llm_system.A_all_five_answered.missed"], href: "/different?def=A&missed=1" };
    },
  },
  {
    id: "t3-parser", label: "What breaks if the T3 parser is fixed?", keywords: ["t3", "parser", "fixed", "blast", "temporal"],
    run: ({ d, s }) => {
      const nodes = [...new Set([...reach(d, "dataset:t3", "down"), ...reach(d, "caveat:circular", "down"), "ablation:B"])];
      const fw = s.futureWork.find((f) => f.rank === 6);
      return { title: "Blast radius of a T3 parser fix",
        summary: `Regenerate: T3 gold and the temporal filter (shared parser), ablation B (+0.462), tables tab_t3_t4_ablation, MD §7 and §9.5, paper §Results RQ3. Related: Future Work #6 (${fw?.item ?? "broad T3"}).`,
        rows: nodes.map((n) => ({ label: d.nodes.get(n)?.title ?? n, detail: n.split(":")[0], node: n })),
        sourceKeys: ["tables.08_t3", "tables.10_ablations.rows"] };
    },
  },
  {
    id: "by-construction", label: "Show all by-construction caveats", keywords: ["by-construction", "construction", "caveats", "bias", "circular"],
    run: ({ s }) => {
      const cs = s.caveats.filter((c) => ["by_construction", "circular", "bias"].includes(c.kind));
      return { title: "By-construction and bias caveats", summary: `${cs.length} caveat(s).`, rows: cs.map((c) => ({ label: c.text, detail: c.kind, node: `caveat:${c.id}` })), sourceKeys: [] };
    },
  },
  {
    id: "left-before-deadline", label: "What's left before 10 Oct?", keywords: ["left", "10 oct", "deadline", "todo", "submission"],
    run: ({ s, now }) => {
      const open = s.submissionTasks.filter((t) => t.status !== "done");
      const r11 = r11Deadline(open, now);
      return { title: "Open before the 10 Oct CMT deadline", summary: `${open.length} open task(s); ${s.placeholders.filter((p) => p.kind === "placeholder").length} placeholder(s) in main.tex.`,
        rows: open.map((t, i) => ({ label: `${t.due} · ${t.title}`, detail: r11[i].reason, href: "/readiness" })), sourceKeys: ["submissionTasks"], href: "/readiness" };
    },
  },
  {
    id: "comparator-vs-class-aware", label: "Compare comparator vs class-aware", keywords: ["compare", "comparator", "class-aware", "pre-registered"],
    run: ({ s }) => {
      const rows = s.paired.filter((p) => p.id.startsWith("prereg:comparator − class_aware"));
      return { title: "Pre-registered: comparator − class-aware (106 items)", summary: rows.map((r) => `${r.metric} ${r.ciLabel}`).join("; "),
        rows: rows.map((r) => ({ label: `${r.metric}: ${r.ciLabel}`, detail: r.preregistered ? "pre-registered (amendment 3)" : "secondary", node: `paired:${r.id}` })),
        sourceKeys: rows.map((r) => r.sourceKey), href: "/results/paired?prereg=1" };
    },
  },
  {
    id: "open-fw3", label: "Open Future Work #3", keywords: ["future work 3", "fw3", "reranking", "cross-encoder"],
    run: ({ s }) => {
      const f = s.futureWork.find((x) => x.rank === 3);
      return { title: `Future Work #3: ${f?.item}`, summary: `${f?.what} Why: ${f?.why}`, rows: [{ label: f?.item ?? "", node: "fw:3" }], sourceKeys: ["MD v2 §12"], href: "/next" };
    },
  },
  {
    id: "high-conf-wrong", label: "Show high-confidence answers that were wrong", keywords: ["high confidence", "wrong", "errors", "confidence"],
    run: ({ d, model }) => {
      if (!model) return { title: "High-confidence errors", summary: "Confidence model missing: run `npm run calibrate`.", rows: [], sourceKeys: [] };
      const wrong = Object.entries(model.units).filter(([, u]) => u.M2.band === "High" && !u.correct);
      const high = model.models.M2.eval.bands.find((b) => b.band === "High");
      return { title: "Comparator verdicts in the High band (M2) that disagree with gold",
        summary: `${wrong.length} of ${high?.n ?? "?"} High-band units are wrong (model M2, fitted on the dev set, frozen before gold evaluation).`,
        rows: wrong.map(([uid]) => {
          const u = d.unitById.get(uid)!;
          return { label: `${d.itemById.get(u.itemId)?.sourceClass} → ${u.classId}`, detail: `comparator ${u.predictions.comparator.judgement} · gold ${u.goldJudgement}`, node: `unit:${uid}` };
        }), sourceKeys: ["ui/src/data/confidence_model_v1.json"], href: "/review-queue" };
    },
  },
];

/** Palette route for free text: keyword match → a deterministic query (exact answer, cited). */
export function matchQuery(q: string): PaletteQuery | null {
  const t = q.toLowerCase();
  let best: { q: PaletteQuery; score: number } | null = null;
  for (const pq of QUERIES) {
    const score = pq.keywords.reduce((a, k) => a + (t.includes(k.toLowerCase()) ? k.length : 0), 0) + (t === pq.label.toLowerCase() ? 100 : 0);
    if (score > 0 && (!best || score > best.score)) best = { q: pq, score };
  }
  return best && best.score >= 6 ? best.q : null;
}
