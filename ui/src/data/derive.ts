import type {
  Dataset, DerivedRQ, GraphEdge, GraphNode, NodeKind, PairedComparison, Snapshot, Task,
} from "@/domain/types";
import { resolveKey } from "@/lib/keys";

export interface Derived {
  tasks: Task[];
  datasets: Dataset[];
  rqs: DerivedRQ[];
  nodes: Map<string, GraphNode>;
  edges: GraphEdge[];
  out: Map<string, GraphEdge[]>;
  inc: Map<string, GraphEdge[]>;
  unitById: Map<string, Snapshot["classUnits"][number]>;
  itemById: Map<string, Snapshot["t1Items"][number]>;
  systemName: (id: string) => string;
}

export function buildTasks(s: Snapshot): Task[] {
  return [
    { id: "T1", title: "Applicability and differential obligation", rqIds: ["RQ1", "RQ2"], datasetIds: ["t1_gold_v1"],
      metrics: ["3-way flag F1", "collapsed F1", "judgement macro-F1", "`different` F1", "coverage"],
      caveatIds: ["single_expert", "scoring_asymmetry", "candidates_shown", "per_class_small_n"],
      description: "Per compared class: same / different / none with a matched paragraph; the item flag (shared / class-specific / absent) is derived by rule v3.6." },
    { id: "T2", title: "Cross-class counterpart retrieval", rqIds: ["RQ1"], datasetIds: ["t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"],
      metrics: ["nDCG@10"], caveatIds: ["by_construction", "bias_t2_xclass_t1", "bias_t2_xclass_p2002", "bias_t2_supp_p2003"],
      description: "Retrieve the counterpart paragraph in a named target class (RQ1's compliance question operationalised as source obligation + declared target class)." },
    { id: "T3", title: "Temporal status on an as-of date", rqIds: [], datasetIds: ["t3"], metrics: ["status exact match", "supersession F1"],
      caveatIds: ["circular", "t3_parser_defect", "amended_text_only"],
      description: "Status of a paragraph (in force, amended, deleted) on an as-of date; 60 built, 52 scored. Circular by construction." },
    { id: "T4", title: "RePASs faithfulness-metric audit", rqIds: ["RQ3"], datasetIds: ["t4"], metrics: ["RePASs composite", "Spearman ρ vs human"],
      caveatIds: ["small_n_t4", "repair_exploratory"],
      description: "Genuine, concatenated, negated and off-topic answers scored by RePASs and compared with human ratings." },
  ].map((t) => ({ ...t, rqIds: t.rqIds as Task["rqIds"], id: t.id as Task["id"] })).filter(() => s.rqs.length > 0);
}

export function buildDatasets(s: Snapshot): Dataset[] {
  const R = s.results;
  const n = (k: string) => (typeof resolveKey(R, k) === "number" ? (resolveKey(R, k) as number) : 0);
  const bias = (ds: string) => resolveKey(R, `tables.06_t2_retrieval.p3001.${ds}.bias`) as string | undefined;
  return [
    { id: "t1_gold_v1", task: "T1", n: n("tables.05_t1_benchmark.validated"), nKey: "tables.05_t1_benchmark.validated",
      constructionStepIds: ["P2-001", "P2-002", "P2-004"], sourcePath: "data/benchmark/t1/t1_validated_v1.jsonl (release/data/t1/validated.jsonl)",
      biasStatement: "Single-expert gold; annotators saw the two P2-002 candidates per compared class." },
    ...(["t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"] as const).map((ds) => ({
      id: ds, task: "T2" as const, n: n(`tables.06_t2_retrieval.p3001.${ds}.n_scored`), nKey: `tables.06_t2_retrieval.p3001.${ds}.n_scored`,
      constructionStepIds: ds === "t2_supp_p2003" ? ["P2-003", "P3-001"] : ds === "t2_xclass_p2002" ? ["P2-002", "P3-001"] : ["P2-004", "P3-001"],
      biasStatement: bias(ds), biasKey: `tables.06_t2_retrieval.p3001.${ds}.bias`, sourcePath: `release/data/t2/${ds}.jsonl`,
    })),
    { id: "t3", task: "T3", n: n("tables.08_t3.scored"), nKey: "tables.08_t3.scored", constructionStepIds: ["P2-003", "P4-001"],
      biasStatement: "Gold and temporal filter share one deterministic parser (circular).", sourcePath: "release/data/t3/items.jsonl" },
    { id: "t4", task: "T4", n: n("tables.09_t4.n_questions"), nKey: "tables.09_t4.n_questions", constructionStepIds: ["P3-002"],
      biasStatement: "LLM-drafted questions and genuine answers; one rater.", sourcePath: "release/data/t4/" },
    { id: "dev30", task: "T1", n: n("phase4.comparator_dev.final.n_units"), nKey: "phase4.comparator_dev.final.n_units",
      constructionStepIds: ["P2-004", "Final"], biasStatement: "Separate 30-item set (not the gold); used once to revise the comparator.",
      sourcePath: "data/benchmark/t1/p2004_irr_consensus_v1.jsonl" },
  ];
}

export function buildRQs(s: Snapshot): DerivedRQ[] {
  const meta: Record<string, Omit<DerivedRQ, "id" | "label" | "text">> = {
    RQ1: { answeredStatus: "answered", findingIds: ["F1", "F2", "F5"], taskIds: ["T2", "T1"],
      statusReason: "Retrieval half answered on T2: class-blind dense loses most of the counterpart retrieval quality that the class-aware hybrid reaches (partly by construction). On T1 the class filter gives no significant judgement gain.",
      operationalisation: "We operationalise RQ1's compliance question as a source obligation plus a declared target class (T2) and as per-class judgement (T1)." },
    RQ2: { answeredStatus: "answered", findingIds: ["F3", "F4", "F7"], taskIds: ["T1"],
      statusReason: "Answered, largely negatively: most gold `different` units are missed by every LLM system, mostly with the counterpart in context; the frozen comparator recovers part of the signal. Single-expert gold." },
    RQ3: { answeredStatus: "partial", findingIds: ["F6"], taskIds: ["T4"],
      statusReason: "Gameability half answered (concatenation reproduces). Repair half not achieved: the exploratory repair no longer tracks human faithfulness and is not usable." },
  };
  return s.rqs.map((r) => ({ ...r, ...(meta[r.id] ?? { answeredStatus: "unanswered", findingIds: [], taskIds: [], statusReason: "" }) }));
}

const PHRASES: [RegExp, string][] = [
  [/class-blind \+ verifier|ablation a(?! \()/i, "ablation_a"],
  [/final agentic/i, "final_agentic"],
  [/long-context/i, "long_context"],
  [/class-aware/i, "class_aware"],
  [/class-blind/i, "class_blind"],
  [/p2-?002|p2002/i, "p2002_candidates"],
  [/majority/i, "majority"],
  [/comparator/i, "comparator"],
];

export function systemsInSide(side: string): string[] {
  for (const [re, id] of PHRASES) if (re.test(side)) return [id];
  return [];
}

export function pairedSystems(p: PairedComparison): string[] {
  if (p.family === "T2") return ["class_aware_hybrid", "hybrid_rrf"];
  if (p.family !== "T1") return [];
  const body = p.label.includes(":") ? p.label.split(":").slice(1).join(":") : p.label;
  const [a, b] = body.split("−");
  return [...systemsInSide(a ?? ""), ...systemsInSide(b ?? "")];
}

const STEP_SYSTEMS: Record<string, string[]> = {
  "P2-002": ["p2002_candidates", "comparator"],
  "P2-004": ["majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a", "long_context", "comparator"],
  "P3-001": ["bm25", "dense", "hybrid_rrf", "hybrid_minus_source_class", "class_aware_hybrid", "class_blind", "class_aware"],
  "P4-001": ["class_aware", "final_agentic", "ablation_a", "long_context"],
  Final: ["comparator"],
};

const CAVEAT_LIMITATION: Record<string, string> = {
  single_expert: "single_expert_gold", retest_short_gap: "short_interval_retest", by_construction: "t2_construction_bias",
  bias_t2_xclass_t1: "t2_construction_bias", bias_t2_xclass_p2002: "t2_construction_bias", bias_t2_supp_p2003: "t2_construction_bias",
  circular: "t3", t3_parser_defect: "t3", amended_text_only: "historical_text", small_n_t4: "t4", repair_exploratory: "the_repass_repair",
  flash_lite: "models", per_class_small_n: "size", calibration: "single_expert_gold", candidates_shown: "single_expert_gold",
};

export function derive(s: Snapshot): Derived {
  const tasks = buildTasks(s);
  const datasets = buildDatasets(s);
  const rqs = buildRQs(s);
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];
  const sysName = new Map(s.systems.map((x) => [x.id, x.displayName]));
  const add = (kind: NodeKind, key: string, title: string, extra: Partial<GraphNode> = {}) => {
    const id = `${kind}:${key}`;
    if (!nodes.has(id)) nodes.set(id, { id, kind, title, ...extra });
    return id;
  };
  const link = (from: string, to: string, rel: string) => {
    if (nodes.has(from) && nodes.has(to) && !edges.some((e) => e.from === from && e.to === to)) edges.push({ from, to, rel });
  };

  rqs.forEach((r) => add("rq", r.id, `${r.id} — ${r.label}`, { subtitle: r.answeredStatus }));
  tasks.forEach((t) => add("task", t.id, `${t.id} — ${t.title}`));
  datasets.forEach((d) => add("dataset", d.id, d.id, { subtitle: `n = ${d.n}`, sourceKey: d.nKey }));
  s.constructionSteps.forEach((c) => add("step", c.id, `${c.id} — ${c.title}`));
  s.systems.forEach((x) => add("system", x.id, x.displayName, { subtitle: x.family }));
  s.paired.forEach((p) => add("paired", p.id, p.label, { subtitle: `${p.metric}: ${p.ciLabel}`, sourceKey: p.sourceKey }));
  s.metrics.forEach((m) => add("metric", `${m.systemId}:${m.datasetId}:${m.metric}`, `${sysName.get(m.systemId) ?? m.systemId} · ${m.metric}`,
    { subtitle: `${m.datasetId}: ${m.ciLabel ?? m.value.toFixed(3)}`, sourceKey: m.sourceKey }));
  for (const t of ["A", "B", "C"]) {
    const a = s.ablations.find((x) => x.ablation === t);
    if (a) add("ablation", t, `Ablation ${t} — ${a.toggle}`, { subtitle: "toggle" });
  }
  s.findings.forEach((f) => add("finding", f.id, `${f.id}: ${f.statement}`, { subtitle: f.ciLabel, sourceKey: f.sourceKey }));
  s.caveats.forEach((c) => add("caveat", c.id, c.text, { subtitle: c.kind }));
  s.limitations.forEach((l) => add("limitation", l.id, `Limitation: ${l.title}`, { subtitle: l.text }));
  s.futureWork.forEach((f) => add("fw", String(f.rank), `Future Work #${f.rank}: ${f.item}`, { subtitle: f.what }));
  s.gaps.forEach((g) => add("gap", g.id, `${g.id}: ${g.expected}`, { subtitle: g.status }));
  s.decisions.forEach((d) => add("decision", d.id, d.decision, { subtitle: d.record, sourceKey: d.sourceKey ?? undefined }));
  s.reliability.forEach((r) => add("reliability", r.id, `${r.statistic}, ${r.target}`, { subtitle: r.ciLabel, sourceKey: r.sourceKey }));
  add("metric", "repair_rho", "Exploratory RePASs repair: ρ with human faithfulness",
    { sourceKey: "tables.09_t4.human.all_rated.spearman_repaired_vs_faithful" });
  const paperClaims = s.claims.filter((c) => c.doc !== "master");
  paperClaims.forEach((c) => add("claim", c.id, c.sentence, { subtitle: `${c.doc === "paper" ? "paper" : "table"} · ${c.section}` }));

  // RQ → Task → Dataset → Step → System → Metric / Paired → Finding → Claim → Caveat → Limitation → Future Work
  tasks.forEach((t) => {
    t.rqIds.forEach((r) => link(`rq:${r}`, `task:${t.id}`, "operationalised by"));
    t.datasetIds.forEach((d) => link(`task:${t.id}`, `dataset:${d}`, "evaluated on"));
  });
  datasets.forEach((d) => d.constructionStepIds.forEach((c) => link(`dataset:${d.id}`, `step:${c}`, "built by")));
  for (const [step, sys] of Object.entries(STEP_SYSTEMS)) sys.forEach((x) => link(`step:${step}`, `system:${x}`, "produces / evaluates"));
  s.metrics.forEach((m) => link(`system:${m.systemId}`, `metric:${m.systemId}:${m.datasetId}:${m.metric}`, "scored"));
  s.paired.forEach((p) => {
    pairedSystems(p).forEach((x) => link(`system:${x}`, `paired:${p.id}`, "compared in"));
    if (p.family === "T2" && p.dataset) link(`dataset:${p.dataset}`, `paired:${p.id}`, "measured on");
    if (p.family === "T3") link("dataset:t3", `paired:${p.id}`, "measured on");
    if (p.family === "T4") link("dataset:t4", `paired:${p.id}`, "measured on");
  });
  link("dataset:t4", "metric:repair_rho", "measured on");
  link("metric:repair_rho", "caveat:repair_exploratory", "qualified by");
  link("metric:class_aware_hybrid:t2_xclass_t1:ndcg@10", "finding:F1", "supports");
  link("metric:hybrid_rrf:t2_xclass_t1:ndcg@10", "finding:F1", "supports");
  link("ablation:A", "paired:t2:t2_xclass_t1", "toggle");
  link("ablation:A", "paired:t1:Class filter, no verifier: class-aware − class-blind:flag_macro_f1", "toggle (without verifier)");
  link("ablation:A", "paired:t1:Ablation A (verifier on): final agentic − class-blind + verifier:flag_macro_f1", "toggle (with verifier)");
  link("ablation:B", "paired:t3:status", "toggle");
  link("ablation:C", "paired:t1:Ablation C on T1: final agentic − class-aware:flag_macro_f1", "toggle");
  link("paired:t3:status", "caveat:circular", "qualified by");
  s.paired.filter((p) => p.family === "T2").forEach((p) => {
    link(`paired:${p.id}`, "caveat:by_construction", "qualified by");
    link(`paired:${p.id}`, `caveat:bias_${p.dataset}`, "qualified by");
  });
  s.paired.filter((p) => p.family === "T1").forEach((p) => {
    link(`paired:${p.id}`, "caveat:single_expert", "qualified by");
    if (p.sameItems) link(`paired:${p.id}`, "caveat:item_set_102", "qualified by");
  });
  s.findings.forEach((f) => {
    const fp = s.paired.find((p) => p.sourceKey === f.sourceKey);
    if (fp) link(`paired:${fp.id}`, `finding:${f.id}`, "supports");
    f.rqIds.forEach((r) => link(`rq:${r}`, `finding:${f.id}`, "answered by"));
    f.caveatIds.forEach((c) => link(`finding:${f.id}`, `caveat:${c}`, "qualified by"));
  });
  link("paired:prereg:comparator − class_aware:different_f1", "finding:F7", "supports");
  link("metric:repair_rho", "finding:F6", "context");
  // Claims: a paper or table sentence whose numbers resolve to a finding's key.
  paperClaims.forEach((c) => {
    for (const f of s.findings) {
      if (c.numbers.some((n) => n.keys.some((k) => k.startsWith(f.sourceKey)))) link(`finding:${f.id}`, `claim:${c.id}`, "stated in");
    }
  });
  s.caveats.forEach((c) => {
    const lim = CAVEAT_LIMITATION[c.id];
    if (lim) link(`caveat:${c.id}`, `limitation:${lim}`, "recorded as");
    c.appliesTo.forEach((a) => link(a, `caveat:${c.id}`, "qualified by"));
  });
  s.limitations.forEach((l) => l.futureWorkIds.forEach((fw) => link(`limitation:${l.id}`, `fw:${fw}`, "addressed by")));
  s.futureWork.forEach((f) => f.dependsOn.forEach((d) => link(`fw:${d}`, `fw:${f.rank}`, "prerequisite of")));
  s.reliability.forEach((r) => { if (r.caveat) link(`reliability:${r.id}`, `caveat:${r.caveat}`, "qualified by"); });
  link("step:P2-004", "reliability:fleiss_class_row", "measured");
  link("step:P2-004", "reliability:retest_flag", "measured");
  s.decisions.forEach((d) => {
    const step = s.constructionSteps.find((c) => c.decisionIds.includes(d.id));
    if (step) link(`step:${step.id}`, `decision:${d.id}`, "decided");
  });

  const out = new Map<string, GraphEdge[]>();
  const inc = new Map<string, GraphEdge[]>();
  for (const e of edges) {
    (out.get(e.from) ?? out.set(e.from, []).get(e.from)!).push(e);
    (inc.get(e.to) ?? inc.set(e.to, []).get(e.to)!).push(e);
  }
  return {
    tasks, datasets, rqs, nodes, edges, out, inc,
    unitById: new Map(s.classUnits.map((u) => [u.id, u])),
    itemById: new Map(s.t1Items.map((i) => [i.id, i])),
    systemName: (id: string) => sysName.get(id) ?? id,
  };
}

/** All nodes reachable forward (downstream) or backward (upstream). */
export function reach(d: Pick<Derived, "out" | "inc">, start: string, dir: "down" | "up"): string[] {
  const seen = new Set<string>([start]);
  const q = [start];
  while (q.length) {
    const cur = q.shift()!;
    const next = dir === "down" ? (d.out.get(cur) ?? []).map((e) => e.to) : (d.inc.get(cur) ?? []).map((e) => e.from);
    for (const n of next) if (!seen.has(n)) { seen.add(n); q.push(n); }
  }
  seen.delete(start);
  return [...seen];
}

/** Shortest backward path from `start` to any node of `kind` (e.g. Finding 4 → its RQ). */
export function pathUpTo(d: Pick<Derived, "inc">, start: string, kind: NodeKind): string[] | null {
  const prev = new Map<string, string | null>([[start, null]]);
  const q = [start];
  while (q.length) {
    const cur = q.shift()!;
    if (cur !== start && cur.startsWith(`${kind}:`)) {
      const path = [cur];
      let p = prev.get(cur);
      while (p) { path.push(p); p = prev.get(p) ?? null; }
      return path.reverse(); // start → … → the node of `kind`
    }
    for (const e of d.inc.get(cur) ?? []) if (!prev.has(e.from)) { prev.set(e.from, cur); q.push(e.from); }
  }
  return null;
}
