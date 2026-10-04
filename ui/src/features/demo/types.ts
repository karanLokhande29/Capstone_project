// Shapes of the per-route JSON shards written by ui/scripts/build_demo_data.py (Demo Build Spec §C1).

export type Judgement = "same" | "different" | "none";
export type SystemId = "p2002_candidates" | "class_blind" | "class_aware" | "final_agentic" | "ablation_a" | "long_context" | "comparator";
export type Field = "actor" | "action" | "object" | "scope" | "condition" | "threshold" | "amount" | "percentage" | "frequency"
  | "deadline" | "exception" | "documentation" | "reporting";
export type FieldStatus = "equal" | "differs" | "only_source" | "only_target" | "absent";
export type Band = "High" | "Medium" | "Low" | "Abstain";
export type Withheld = { withheld: true };
export type FieldValue = string | null | Withheld;

export interface RuleStep { step: string; fields: Field[]; result: "pass" | "fail" | "fired"; verdict?: Judgement | "abstain"; pid?: string | null }

export interface Prediction {
  status: "answered" | "abstained" | "not_answered" | "not_run";
  judgement?: Judgement;
  matchedPid?: string | null;
  inContext?: boolean | null;
  retryUsed?: boolean;
}

export interface FieldRow {
  field: Field; status: FieldStatus; material: boolean;
  sourceValue: FieldValue; targetValue: FieldValue;
  note?: "entity_name_by_construction" | "extraction_anomaly";
}

export interface Contribution { feature: string; value: number; z: number; weight: number; term: number }

export interface Unit {
  id: string; itemId: string; sourcePid: string; sourceClass: string; targetClass: string; topic: string | null;
  route: string; goldJudgement: Judgement; goldMatchedPid: string | null; goldFlag: string;
  shownCandidates: string[];
  predictions: Record<SystemId, Prediction>;
  missedA: boolean; missedB: boolean;
  comparator: {
    parseOk: boolean; decisivePid: string | null; addressesSameDuty: boolean | null;
    perCandidate: { pid: string; verdict: Judgement | "abstain"; addressesSameDuty: boolean | null }[];
    rows: FieldRow[]; trace: RuleStep[];
  };
  confidence: { model: "M2"; version: string; p: number | null; band: Band; intercept?: number; contributions: Contribution[] };
  xray: Partial<Record<SystemId, XRayLog>>;
  provenance: Record<string, string | number | null>;
}

export interface Pointer {
  id: string; mdId: string; clausePath: string | null; url: string | null; harvestDate: string | null; sha256: string | null;
  excerpt: string | null; focused?: boolean; directionTitle: string; entityClass: string | null;
}

export interface Shard {
  item: { id: string; sourcePid: string; sourceClass: string; topic: string | null; route: string; goldFlag: string; inForceFrom: string | null; comparedClasses: string[] };
  units: Unit[]; pointers: Record<string, Pointer>;
}

export interface IndexUnit {
  id: string; itemId: string; shard: string; src: string; tgt: string; topic: string | null; route: string; gold: Judgement;
  missedA: boolean; missedB: boolean; band: Band; p: number | null; srcPid: string;
  sys: Record<SystemId, Judgement | "abstained" | "not_answered">;
  inCtx: Partial<Record<SystemId, boolean | null>>;
  sameDuty: (boolean | null)[];
}

export interface CasesIndex { generatedUtc: string; systems: SystemId[]; units: IndexUnit[] }

export interface Home {
  hero: Unit; heroPointers: Record<string, Pointer>;
  classes: string[];
  stats: { directions: number; paragraphs: number; institutionTypes: number; units: number; items: number; realDifferences: number; missedA: number; recovered: number; comparatorFound: number; falseAlarms: number };
  generatedUtc: string;
}

export interface BandStat { band: Band; n: number; correct: number; accuracy: number | null; wilsonCI: [number, number] | null }

export interface ResultsShard {
  results: Record<string, unknown>;
  reliability: { id: string; value: number; n: number; label?: string }[];
  confidence: {
    model: "M2"; label: string; bands: BandStat[]; ece: number; brier: number; baseRate: { correct: number; n: number; accuracy: number; wilsonCI: [number, number] };
    coverageHigh: number; highBySame: number; highN: number; differentCorrectByBand: Partial<Record<Band, number>>; recoveredByBand: Partial<Record<Band, number>>;
    differentFlags: { precision: { k: number; n: number }; recall: { k: number; n: number } };
  };
  resultsSha256: string;
}

export interface TriageRow {
  t: number; nAuto: number; kAuto: number; accAuto: number | null; ciAuto: [number, number] | null;
  nReview: number; kReview: number; accReview: number | null; ciReview: [number, number] | null;
  split: Record<Judgement, { auto: number; autoCorrect: number; total: number }>;
}
export interface TriageGrid {
  n: number; seed: number; seedSource: string; resamples: number; unitOfResampling: string; rows: TriageRow[];
  bandThresholds: { high: number; low: number }; presets: { High: number; Medium: number };
  calibration: { ece: number; brier: number; baseRate: { correct: number; n: number; accuracy: number }; bands: BandStat[];
    reliability: { lo: number; hi: number; n: number; meanConfidence: number | null; accuracy: number | null; wilsonCI: [number, number] | null }[] };
  features: { feature: string; weight: number; mean: number; sd: number }[]; intercept: number; fittedOn: string; label: string;
}

export interface MethodShard {
  hashes: Record<string, string>; ledger: { path: string; expectedSha256: string; actualSha256: string | null; status: string }[]; model: string; frozenAtUtc: string; ruleVersion: string; fields: Field[]; material: Field[];
  sensitivity: { label: string; frozen: { tp: number; fp: number; sameSame: number }; actorMasked: { tp: number; fp: number; sameSame: number }; lostCorrect: string[] };
  withheldNote: string; missesSameDuty: number;
  reliability: { id: string; value: number; n: number; label?: string }[];
}

export interface T3Item { id: string; pid: string; asOf: string; side: "before" | "after"; gold: string; action: string; scope: string;
  effective: string | null; published: string | null; amendmentUrl: string | null; url: string | null; off: string; on: string }
export interface T2Query { id: string; src: string; tgt: string; judgement: string | null; srcPid: string; gold: string[]; ranks: Record<string, number | null> }
export interface T4Shard {
  questions: { id: string; question: string; entityClass: string | null; topic: string | null; url: string | null; pid: string | null; scores: Record<string, { composite: number; human: number | null }> }[];
  byType: Record<string, { composite_score: { mean: number } }>; gap: { mean: number; ci: [number, number]; key: string };
}
export interface MatrixShard {
  classes: string[]; families: string[];
  cells: { classId: string; familyId: string; populated: boolean; ambiguous: boolean; ambiguityReason?: string | null; directionIds: string[]; t1Items: string[] }[];
  directions: Record<string, { title: string; url: string | null }>;
}
export interface CostShard { t1: { calls: number; inputTokens: number; outputTokens: number; perCall: { input: number; output: number } }; dev: { calls: number; inputTokens: number; outputTokens: number }; price: null; priceNote: string }

export interface XRayLog {
  classFilter: boolean | null; verifier: boolean | null; temporalFilter: string | boolean | null;
  attempts: { attempt: number; shown: string[]; pooled?: boolean; retryRequested: boolean; parseProblems: boolean }[];
}
