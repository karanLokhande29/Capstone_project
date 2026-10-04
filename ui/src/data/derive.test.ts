import { readJson } from "@/test/files";
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { derive, pathUpTo, reach } from "./derive";
import { QUERIES, matchQuery } from "@/features/palette/queries";

const s = readJson<Snapshot>("src/data/snapshot.json");
const model = readJson<ConfidenceModel>("src/data/confidence_model_v1.json");
const d = derive(s);
const down = (n: string) => new Set(reach(d, n, "down"));
const up = (n: string) => new Set(reach(d, n, "up"));

describe("§6 traceability chains (day one)", () => {
  it("RQ2 → T1 → gold → P2-002 + P2-004 → comparator vs class-aware → F7 → paper → caveats → limitation → Future Work #2", () => {
    const r = down("rq:RQ2");
    for (const n of ["task:T1", "dataset:t1_gold_v1", "step:P2-002", "step:P2-004", "system:comparator", "system:class_aware",
      "paired:prereg:comparator − class_aware:different_f1", "finding:F7", "caveat:single_expert", "caveat:candidates_shown",
      "limitation:single_expert_gold", "fw:2"]) expect(r.has(n), n).toBe(true);
    expect([...down("finding:F7")].some((n) => n.startsWith("claim:paper:"))).toBe(true);
  });
  it("Finding 1 ← class-aware hybrid 0.894 vs hybrid RRF 0.443 ← t2_xclass_t1, with by-construction caveat", () => {
    const u = up("finding:F1");
    for (const n of ["metric:class_aware_hybrid:t2_xclass_t1:ndcg@10", "metric:hybrid_rrf:t2_xclass_t1:ndcg@10", "paired:t2:t2_xclass_t1", "dataset:t2_xclass_t1", "task:T2", "rq:RQ1"])
      expect(u.has(n), n).toBe(true);
    expect(down("finding:F1").has("caveat:by_construction")).toBe(true);
  });
  it("T3 → ablation B +0.462 → circular → Future Work #6", () => {
    const r = down("task:T3");
    for (const n of ["dataset:t3", "paired:t3:status", "caveat:circular", "limitation:t3", "fw:6"]) expect(r.has(n), n).toBe(true);
    expect(up("paired:t3:status").has("ablation:B")).toBe(true);
    expect(s.paired.find((p) => p.id === "t3:status")!.delta).toBeCloseTo(0.4615, 3);
  });
  it("RQ3 → T4 → +0.375 → repair ρ −0.126 → Future Work #7", () => {
    const r = down("rq:RQ3");
    for (const n of ["task:T4", "dataset:t4", "paired:t4:concatenated - genuine", "finding:F6", "metric:repair_rho", "caveat:repair_exploratory", "fw:7"])
      expect(r.has(n), n).toBe(true);
    expect(d.rqs.find((x) => x.id === "RQ3")!.answeredStatus).toBe("partial");
  });
  it("Finding 4 traces back to an RQ", () => {
    const p = pathUpTo(d, "finding:F4", "rq");
    expect(p?.at(-1)).toMatch(/^rq:/);
  });
});

describe("§7 palette queries are deterministic and non-empty", () => {
  const ctx = { s, d, model, now: new Date("2026-10-04T10:00:00+05:30") };
  it.each(QUERIES.map((q) => [q.id, q] as const))("%s", (_id, q) => {
    const a = q.run(ctx);
    const b = q.run(ctx);
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    expect(a.rows.length).toBeGreaterThan(0);
    expect(a.title.length).toBeGreaterThan(5);
  });
  it("matches free text to the right query", () => {
    expect(matchQuery("which claims rest on a CI that includes 0?")?.id).toBe("ci-includes-zero");
    expect(matchQuery("what's left before 10 oct")?.id).toBe("left-before-deadline");
    expect(matchQuery("tell me a joke")).toBeNull();
  });
  it("definition A count equals results_v2", () => {
    const r = QUERIES.find((q) => q.id === "missed-def-a")!.run(ctx);
    expect(r.rows).toHaveLength(56);
  });
});
