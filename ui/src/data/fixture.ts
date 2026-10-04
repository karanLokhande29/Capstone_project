import type { Snapshot } from "@/domain/types";

// FixtureAdapter data: ONLY numbers printed in reports/final/RBI-ObliBench_Master_Document_v2.md (headline findings).
// The single class unit below is synthetic; `meta.fixture = true` makes the app show the "synthetic fixture" watermark.
export function fixtureSnapshot(): Snapshot {
  const results = {
    tables: { "06_t2_retrieval": { p4_pipeline: { t2_xclass_t1: { paired: { diff: 0.451, ci: [0.421, 0.481] } } } } },
    phase4: {},
  };
  return {
    meta: {
      generatedUtc: "fixture", generator: "ui/src/data/fixture.ts", sources: [{ path: "reports/final/RBI-ObliBench_Master_Document_v2.md", sha256: "fixture" }],
      wordLimit: 25, excerptWords: 12, fixture: true, deadline: "2026-10-10T23:59:00+05:30", partAStatus: [],
    },
    results,
    rqs: [
      { id: "RQ1", label: "Applicability", text: "Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?" },
      { id: "RQ2", label: "Differential Obligation", text: "For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?" },
      { id: "RQ3", label: "Metric Integrity", text: "Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?" },
    ],
    findings: [
      { id: "F1", statement: "The class filter improves retrieval.", sourceKey: "tables.06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired", caveatIds: ["by_construction"], rqIds: ["RQ1"], paperLocations: ["MD §1"], delta: 0.451, ci: [0.421, 0.481], ciLabel: "+0.451 [+0.421, +0.481] (excludes 0 (above))" },
      { id: "F2", statement: "It doesn't translate into better T1 judgement.", sourceKey: "fixture", caveatIds: ["single_expert"], rqIds: ["RQ1", "RQ2"], paperLocations: ["MD §1"], delta: -0.05, ci: [-0.133, 0.027], ciLabel: "-0.050 [-0.133, +0.027] (does not exclude 0)" },
      { id: "F4", statement: "The verifier hurts T1.", sourceKey: "fixture", caveatIds: ["single_expert"], rqIds: ["RQ2"], paperLocations: ["MD §1"], delta: -0.068, ci: [-0.132, -0.012], ciLabel: "-0.068 [-0.132, -0.012] (excludes 0 (below))" },
      { id: "F7", statement: "The structured comparator lifts `different` F1.", sourceKey: "fixture", caveatIds: ["single_expert"], rqIds: ["RQ2"], paperLocations: ["MD §1"], delta: 0.255, ci: [0.094, 0.411], ciLabel: "+0.255 [+0.094, +0.411] (excludes 0 (above))" },
    ],
    caveats: [
      { id: "single_expert", kind: "single_expert", text: "T1 gold is single-expert.", appliesTo: ["task:T1"] },
      { id: "by_construction", kind: "by_construction", text: "T2 relevance covers only the target-class counterpart.", appliesTo: ["task:T2"] },
    ],
    paired: [], ablations: [], systems: [], metrics: [], reliability: [], constructionSteps: [], decisions: [], futureWork: [], limitations: [],
    submissionTasks: [], gaps: [], recommendations: [], placeholders: [], venue: { file: "", facts: [], differences: [], checked: "" }, claims: [],
    diff: { v1Sha: "", v2Sha: "", tablesNumericLeaves: 0, changed: [], removed: [], added: [], topLevelV1: [], topLevelV2: [], newSections: [], phase4Keys: [] },
    frozen: [], frozenComparator: { frozen_at_utc: "", sha256: {}, model: "" }, entityClasses: [], subjectFamilies: [], directions: [], matrix: [],
    corpusMeta: {}, t1Items: [],
    classUnits: [{ id: "fixture_item|Synthetic Class", itemId: "fixture_item", classId: "Synthetic Class", goldJudgement: "different", goldMatchedPid: null,
      predictions: { comparator: { judgement: "different", matchedPid: null } }, missedA: false, missedB: false }],
    pointers: {}, comparatorFields: {}, masterSections: [], changesV1: [], guidelineRules: [],
  };
}
