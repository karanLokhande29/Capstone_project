import {
  effectDirection, r10Freeze, r11Deadline, r12Scoring, r13MissingCI, r14Confidence, r1ClaimCheck, r2ByConstruction, r3Circularity,
  r4ItemSet, r5SingleExpert, r6NumberDrift, r7Placeholders, r8Terminology, r9SmallN, TERMINOLOGY_USAGES,
} from "./rules";
import type { FrozenArtifact, MetricResult, SubmissionTask } from "@/domain/types";

const claim = (sentence: string, numbers: { text: string; nKeys: number; keys: string[] }[] = []) => ({ sentence, numbers });

describe("R1 CI over-claim", () => {
  it("supports an effect verb whose CI excludes 0 in the asserted direction", () => {
    const r = r1ClaimCheck(claim("The verifier hurts T1: final agentic − class-aware −0.068 [−0.132, −0.012]."));
    expect(r.verdict).toBe("supported");
    expect(r.reason).toContain("excludes 0 (below)");
  });
  it("warns when the CI includes 0", () => {
    const r = r1ClaimCheck(claim("The class filter improves T1 judgement by −0.050 [−0.133, +0.027]."));
    expect(r.verdict).toBe("warn");
    expect(r.suggestion).toBeTruthy();
  });
  it("warns when the CI excludes 0 in the opposite direction", () => {
    expect(r1ClaimCheck(claim("This improves coverage: −0.217 [−0.292, −0.142].")).verdict).toBe("warn");
  });
  it("accepts hedged sentences", () => {
    expect(r1ClaimCheck(claim("The class filter does not improve T1 judgement: −0.050 [−0.133, +0.027].")).verdict).toBe("supported");
  });
  it("resolves the CI through result keys when none is written inline", () => {
    const results = { phase4: { x: { flag: { diff: 0.2, ci: [0.1, 0.3] } } } };
    const r = r1ClaimCheck(claim("The comparator improves it by 0.200.", [{ text: "0.200", nKeys: 1, keys: ["phase4.x.flag.diff"] }]), results);
    expect(r.verdict).toBe("supported");
    expect(r.sourceRefs).toEqual(["phase4.x.flag"]);
  });
  it("is informational without an effect verb or CI", () => {
    expect(r1ClaimCheck(claim("T1 has 106 items.")).verdict).toBe("info");
    expect(effectDirection("The verifier lowers F1")).toBe("down");
  });
});

describe("R2–R5", () => {
  it("R2 attaches the bias statement and by-construction caveat", () => {
    const r = r2ByConstruction("t2_xclass_t1", { results: { tables: { "06_t2_retrieval": { p3001: { t2_xclass_t1: { bias: "Favours dense." } } } } } });
    expect(r.reason).toMatch(/Favours dense\..*target-class counterpart/);
    expect(r.sourceRefs).toContain("caveat:by_construction");
  });
  it("R3 blocks T3 filter-on from showcase", () => {
    expect(r3Circularity({ datasetId: "t3", sourceKey: "tables.08_t3.t3.on.status_exact_match" }).blockShowcase).toBe(true);
    expect(r3Circularity({ datasetId: "t3", sourceKey: "tables.08_t3.t3.off.status_exact_match" }).blockShowcase).toBe(false);
  });
  it("R4 redirects mixed 102/106 comparisons", () => {
    expect(r4ItemSet([102, 106], true).verdict).toBe("warn");
    expect(r4ItemSet([102, 102], true).verdict).toBe("ok");
  });
  it("R5 inherits the single-expert caveat", () => {
    expect(r5SingleExpert(["task:T1", "rq:RQ2"]).sourceRefs).toContain("caveat:single_expert");
    expect(r5SingleExpert(["task:T4"]).verdict).toBe("ok");
  });
});

describe("R6–R9", () => {
  it("R6 flags metric-like numbers with no key, and marks small integers as unclear", () => {
    expect(r6NumberDrift({ text: "0.512", nKeys: 0, keys: [] }).verdict).toBe("fail");
    expect(r6NumberDrift({ text: "11.7", nKeys: 0, keys: [] }).verdict).toBe("unclear");
    expect(r6NumberDrift({ text: "0.409", nKeys: 2, keys: ["a", "b"] }).verdict).toBe("ok");
  });
  it("R7 finds placeholders", () => {
    const r = r7Placeholders("a \\placeholder{email} b DOI to be assigned c [verify] TODO", "x.tex");
    expect(r.map((x) => x.inputs.text)).toEqual(["\\placeholder{email}", "DOI to be assigned", "[verify]", "TODO"]);
  });
  it("R8 detects a collision and stays clear after A2", () => {
    expect(r8Terminology(TERMINOLOGY_USAGES).every((r) => r.verdict === "ok")).toBe(true);
    const bad = r8Terminology([{ label: "Ablation A", referent: "toggle", where: "a" }, { label: "Ablation A", referent: "system", where: "b" }]);
    expect(bad[0].verdict).toBe("unclear");
  });
  it("R9 warns on small slices", () => {
    expect(r9SmallN(7, "Local Area Banks").verdict).toBe("warn");
    expect(r9SmallN(106, "all").verdict).toBe("ok");
  });
});

describe("R10–R14", () => {
  const row = (status: FrozenArtifact["status"]): FrozenArtifact => ({ path: "p", expectedSha256: "a", expectedSource: "s", actualSha256: "a", status });
  it("R10 freeze integrity", () => {
    expect(r10Freeze([row("match")]).verdict).toBe("ok");
    expect(r10Freeze([row("match"), row("mismatch")]).verdict).toBe("fail");
  });
  it("R11 deadline risk", () => {
    const t = (id: string, due: string): SubmissionTask => ({ id, title: id, due, dependsOn: [], status: "open", verifyCommand: null });
    const now = new Date("2026-10-05T12:00:00+05:30");
    const out = r11Deadline([t("old", "2026-10-04"), t("today", "2026-10-05"), t("later", "2026-10-09")], now);
    expect(out.map((o) => o.verdict)).toEqual(["fail", "warn", "ok"]);
  });
  it("R12 recognises the documented scoring", () => {
    expect(r12Scoring("**Scoring asymmetry.** … **How abstentions are scored.**").verdict).toBe("ok");
    expect(r12Scoring("nothing").verdict).toBe("unclear");
  });
  it("R13 flags a metric without CI among CI siblings", () => {
    const m = (metric: string, ci: [number, number] | null): MetricResult => ({ systemId: "s", datasetId: "t1", metric, value: 0.4, ci, ciLabel: null, n: 106, sourceKey: metric });
    const out = r13MissingCI([m("flag", [0.1, 0.2]), m("different_f1", null)]);
    expect(out).toHaveLength(1);
    expect(out[0].inputs.metric).toBe("different_f1");
  });
  it("R14 blocks confidence without accuracy/CI or with n < 20", () => {
    expect(r14Confidence({ band: "High", n: 162, accuracy: 0.96, wilsonCI: [0.92, 0.98], hidden: false }).verdict).toBe("ok");
    expect(r14Confidence({ band: "High", n: 12, accuracy: 0.9, wilsonCI: [0.6, 0.98], hidden: false }).verdict).toBe("block");
    expect(r14Confidence({ band: "Low", n: 40, accuracy: null, wilsonCI: null, hidden: false }).verdict).toBe("block");
    expect(r14Confidence(null).verdict).toBe("block");
  });
});
