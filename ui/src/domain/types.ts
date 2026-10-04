// §5 data model. Every displayed number is either a key into `results` (reports/results_v2.json) or an entity that carries
// `sourceKey`. Field names mirror ui/scripts/ingest.py.

export type RQId = "RQ1" | "RQ2" | "RQ3";
export type Judgement = "same" | "different" | "none";
export type PredJudgement = Judgement | "abstain" | "unanswered";
export type Flag = "shared" | "class-specific" | "absent";

export interface ResearchQuestion {
  id: RQId;
  label: string;
  text: string; // verbatim
}

export interface DerivedRQ extends ResearchQuestion {
  answeredStatus: "answered" | "partial" | "unanswered";
  statusReason: string;
  findingIds: string[];
  taskIds: string[];
  operationalisation?: string;
}

export interface Task {
  id: "T1" | "T2" | "T3" | "T4";
  title: string;
  rqIds: RQId[];
  datasetIds: string[];
  metrics: string[];
  caveatIds: string[];
  description: string;
}

export interface Dataset {
  id: string;
  task: Task["id"];
  n: number;
  nKey: string;
  constructionStepIds: string[];
  biasStatement?: string;
  biasKey?: string;
  sourcePath: string;
}

export interface ConstructionStep {
  id: string;
  title: string;
  inputs: string[];
  outputs: string[];
  metrics: { key: string; value: unknown }[];
  decisionIds: string[];
}

export interface EntityClass {
  id: string;
  label: string;
  kind: "regulated" | "rbi_function";
  paragraphs: number;
  paragraphsKey: string;
}

export interface SubjectFamily {
  id: string;
  label: string;
}

export interface MatrixCell {
  classId: string;
  familyId: string;
  populated: boolean;
  ambiguous: boolean;
  ambiguityReason?: string | null;
  directionIds: string[];
}

export interface Direction {
  id: string;
  title: string;
  subjectFamilyId?: string | null;
  classIds: string[];
  updatedAsOn?: string | null;
  defects: string[];
  url?: string;
  harvestDate?: string;
}

export interface ParagraphPointer {
  id: string;
  mdId: string;
  clausePath?: string | null;
  url?: string;
  harvestDate?: string;
  sha256?: string;
  excerpt?: string | null; // ≤ 25 words, budgeted per paragraph
}

export interface T1Item {
  id: string;
  sourcePid: string;
  mdId: string;
  sourceClass: string;
  subjectFamily?: string | null;
  clausePath?: string | null;
  comparedClasses: string[];
  route: string;
  goldFlag: Flag;
  unitIds: string[];
  inForceFrom?: string | null;
  amendedBy: string[];
  adjudicatedFields: number;
}

export interface UnitPrediction {
  judgement: PredJudgement;
  matchedPid: string | null;
  inContext?: boolean | null;
  failure?: "retrieval" | "reasoning" | "unknown" | null;
}

export interface ClassUnit {
  id: string; // `${itemId}|${classId}`
  itemId: string;
  classId: string;
  goldJudgement: Judgement;
  goldMatchedPid: string | null;
  predictions: Record<string, UnitPrediction>;
  missedA: boolean;
  missedB: boolean;
}

export type FieldStatus = "equal" | "differs" | "only_source" | "only_target" | "absent";

export interface ComparatorFieldRow {
  field: string;
  status: FieldStatus;
  material: boolean;
  sourceValue: string | null;
  targetValue: string | null;
  sourcePresent: boolean;
  targetPresent: boolean;
}

export interface ComparatorFields {
  parseOk: boolean;
  decisivePid: string | null;
  addressesSameDuty?: boolean;
  perCandidate: { pid: string; verdict: string; addressesSameDuty?: boolean }[];
  rows: ComparatorFieldRow[];
  hinge: boolean;
  nBoth: number;
  nMaterialDiff: number;
  rule?: string;
}

export interface System {
  id: string;
  displayName: string;
  family: "retrieval" | "t1" | "baseline";
  description: string;
  model?: string | null;
  frozenPromptSha?: Record<string, string> | null;
  componentIds: string[];
}

export interface MetricResult {
  systemId: string;
  datasetId: string;
  metric: string;
  value: number;
  ci: [number, number] | null;
  ciLabel: string | null;
  n: number;
  sourceKey: string;
  circular?: boolean;
}

export interface PairedComparison {
  id: string;
  label: string;
  a: string;
  b: string;
  n: number;
  metric: string;
  delta: number;
  ci: [number, number];
  ciLabel: string;
  sourceKey: string;
  preregistered: boolean;
  sameItems: boolean;
  family: "T1" | "T2" | "T3" | "T4";
  dataset?: string;
}

export interface Ablation {
  id: string;
  ablation: "A" | "B" | "C";
  toggle: string;
  measure: string;
  n: number;
  delta: number;
  ci: [number, number];
  ciLabel: string;
  sourceKey: string;
  condition: string | null;
  circular: boolean;
}

export interface Finding {
  id: string;
  statement: string;
  sourceKey: string;
  caveatIds: string[];
  rqIds: RQId[];
  paperLocations: string[];
  delta?: number;
  ci?: [number, number];
  ciLabel?: string;
  count?: number;
}

export type CaveatKind =
  | "by_construction" | "circular" | "single_expert" | "small_n" | "bias" | "superseded" | "exploratory" | "in_sample"
  | "scoring" | "item_set" | "scope" | "missing_ci";

export interface Caveat {
  id: string;
  kind: CaveatKind;
  text: string;
  appliesTo: string[];
}

export interface Limitation {
  id: string;
  title: string;
  text: string;
  futureWorkIds: number[];
}

export interface FutureWorkItem {
  rank: number;
  item: string;
  what: string;
  why: string;
  effort: string;
  limitationIds: string[];
  dependsOn: number[];
  blastRadius: string[];
  openQuestions: string[];
  strengthens: string[];
  couldOverturn: string[];
}

export interface ReliabilityStudy {
  id: string;
  design: string;
  raters: string;
  statistic: string;
  target: string;
  value: number;
  ci: [number, number];
  ciLabel: string;
  n: number;
  nUnits?: number;
  inGold: false;
  sourceKey: string;
  caveat: string | null;
  ciCrossesZero: boolean;
}

export interface Decision {
  id: string;
  decision: string;
  alternatives: string;
  rationale: string;
  record: string;
  sourceKey: string | null;
}

export interface FrozenArtifact {
  path: string;
  expectedSha256: string;
  expectedSource: string;
  actualSha256: string | null;
  status: "match" | "mismatch" | "unreadable";
}

export interface ClaimNumber {
  text: string;
  nKeys: number;
  keys: string[];
}

export interface PaperClaim {
  id: string;
  doc: "paper" | "table" | "master";
  section: string;
  sentence: string;
  numbers: ClaimNumber[];
  effectVerb: string | null;
}

export interface SubmissionTask {
  id: string;
  title: string;
  due: string;
  dependsOn: string[];
  status: "open" | "done";
  verifyCommand: string | null;
  note?: string;
}

export type GapStatus = "complete" | "partial" | "missing" | "unclear" | "conflicting" | "duplicate" | "needs_validation";

export interface GapFinding {
  id: string;
  category: string;
  status: GapStatus;
  expected: string;
  actual: string;
  sourceRefs: string[];
  reasonDetected: string;
  suggestedFix: string;
  fixedInPartA: string | null;
}

export interface Recommendation {
  id: string;
  tier: "REQUIRED" | "ENHANCEMENT" | "NEW_OPPORTUNITY";
  priority: "MUST" | "SHOULD" | "COULD";
  title: string;
  why: string;
  evidence: string[];
  unblocks: string[];
}

export interface Placeholder {
  file: string;
  line: number;
  text: string;
  kind: string;
  task: string;
}

export interface VenueFact {
  item: string;
  text: string;
  sources: { id: string; url: string }[];
  accessed: string;
}

export interface SnapshotDiffEntry {
  key: string;
  v1: number | null;
  v2: number | null;
  kind: "changed" | "added" | "removed";
}

export interface Snapshot {
  meta: {
    generatedUtc: string;
    generator: string;
    sources: { path: string; sha256: string }[];
    wordLimit: number;
    excerptWords: number;
    fixture: boolean;
    deadline: string;
    partAStatus: { id: string; status: string; note: string }[];
  };
  results: Record<string, unknown>;
  rqs: ResearchQuestion[];
  findings: Finding[];
  caveats: Caveat[];
  paired: PairedComparison[];
  ablations: Ablation[];
  systems: System[];
  metrics: MetricResult[];
  reliability: ReliabilityStudy[];
  constructionSteps: ConstructionStep[];
  decisions: Decision[];
  futureWork: FutureWorkItem[];
  limitations: Limitation[];
  submissionTasks: SubmissionTask[];
  gaps: GapFinding[];
  recommendations: Recommendation[];
  placeholders: Placeholder[];
  venue: { file: string; facts: VenueFact[]; differences: string[]; checked: string };
  claims: PaperClaim[];
  diff: {
    v1Sha: string;
    v2Sha: string;
    tablesNumericLeaves: number;
    changed: SnapshotDiffEntry[];
    removed: SnapshotDiffEntry[];
    added: SnapshotDiffEntry[];
    topLevelV1: string[];
    topLevelV2: string[];
    newSections: string[];
    phase4Keys: string[];
  };
  frozen: FrozenArtifact[];
  frozenComparator: { frozen_at_utc: string; sha256: Record<string, string>; model: string };
  entityClasses: EntityClass[];
  subjectFamilies: SubjectFamily[];
  directions: Direction[];
  matrix: MatrixCell[];
  corpusMeta: Record<string, unknown>;
  t1Items: T1Item[];
  classUnits: ClassUnit[];
  pointers: Record<string, ParagraphPointer>;
  comparatorFields: Record<string, ComparatorFields>;
  masterSections: { id: string; title: string; text: string }[];
  changesV1: string[];
  guidelineRules: { id: string; title: string }[];
}

// §8.2 confidence model (ui/src/data/confidence_model_v1.json)
export type Band = "High" | "Medium" | "Low" | "Abstain";

export interface BandStat {
  band: Band;
  n: number;
  correct: number;
  accuracy: number | null;
  wilsonCI: [number, number] | null;
  hidden: boolean;
}

export interface ModelEval {
  nUnits: number;
  baseRate: { correct: number; n: number; accuracy: number; wilsonCI: [number, number] };
  bands: BandStat[];
  ece: number;
  brier: number;
  reliability: { lo: number; hi: number; n: number; meanConfidence: number | null; accuracy: number | null; wilsonCI: [number, number] | null }[];
  selectiveCurve: { coverage: number; answered: number; accuracy: number; wilsonCI: [number, number]; threshold: number }[];
  operatingPoint: { band: "High"; coverage: number; answered: number; accuracy: number | null; wilsonCI: [number, number] | null };
  experimental: boolean;
  experimentalReasons: string[];
  bandComposition: Record<string, Record<string, { n: number; correct: number }>>;
  withinLabelAUC: Record<string, { auc: number | null; nRight: number; nWrong: number }>;
  mergedBands: string[];
}

export interface ConfidenceModelInfo {
  id: "M1" | "M2";
  name: string;
  label: string;
  features: string[];
  intercept: number;
  weights: number[];
  means: number[];
  sds: number[];
  fittedOn: string;
  evaluatedOn: string;
  use: string;
  eval: ModelEval;
}

export interface ConfidenceModel {
  version: string;
  specSha256: string;
  frozenSha256: string;
  evaluatedUtc: string;
  order: string[];
  models: { M1: ConfidenceModelInfo; M2: ConfidenceModelInfo };
  bandThresholds: { high: number; low: number };
  units: Record<string, { M1: { p: number | null; band: Band }; M2: { p: number | null; band: Band }; correct: boolean }>;
}

export interface AssistantAnswer {
  question: string;
  route: "palette" | "grounded_llm" | "pipeline";
  answer: string;
  citations: string[];
  confidence: { band: string; empiricalAccuracy: number | null; ci: [number, number] | null; basis: string; model?: string };
  caveats: string[];
  grounding?: "Exact" | "Partial" | "Unsupported";
}

export type NodeKind =
  | "rq" | "task" | "dataset" | "step" | "system" | "metric" | "paired" | "ablation" | "finding" | "claim" | "caveat" | "limitation"
  | "fw" | "unit" | "item" | "gap" | "decision" | "reliability" | "frozen" | "direction" | "class";

export interface GraphNode {
  id: string; // `${kind}:${key}`
  kind: NodeKind;
  title: string;
  subtitle?: string;
  sourceKey?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  rel: string;
}
