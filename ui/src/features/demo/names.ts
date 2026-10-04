import type { Band, Field, FieldStatus, Judgement, SystemId } from "./types";

/** Display names (Demo Build Spec B2). The internal id goes in a tooltip. */
export const SYSTEM_NAME: Record<SystemId, string> = {
  p2002_candidates: "Embedding match (P2-002 candidates)",
  class_blind: "LLM with standard search",
  class_aware: "LLM with institution-filtered search",
  final_agentic: "Our first pipeline (institution filter + fact-checker)",
  ablation_a: "LLM with standard search + fact-checker",
  long_context: "LLM reading whole Directions (100K)",
  comparator: "Structured comparator (pre-registered)",
};
export const SYSTEM_SHORT: Record<SystemId, string> = {
  p2002_candidates: "Embedding match",
  class_blind: "Standard search",
  class_aware: "Filtered search",
  final_agentic: "Our first pipeline",
  ablation_a: "Search + fact-checker",
  long_context: "Whole Directions",
  comparator: "Comparator",
};
export const LLM_SYSTEMS: SystemId[] = ["class_blind", "class_aware", "final_agentic", "ablation_a", "long_context"];
export const ALL_SYSTEMS: SystemId[] = ["p2002_candidates", ...LLM_SYSTEMS, "comparator"];

export const VERDICT: Record<Judgement, string> = { same: "Same requirement", different: "Different requirement", none: "No matching rule" };
export const VERDICT_SHORT: Record<Judgement, string> = { same: "Same", different: "Different", none: "No match" };

export const FIELD_LABEL: Record<Field, string> = {
  actor: "Who must comply", action: "What they must do", object: "What it applies to", scope: "Scope", condition: "Condition",
  threshold: "Threshold", amount: "Amount", percentage: "Percentage", frequency: "How often", deadline: "Deadline",
  exception: "Exceptions", documentation: "Records to keep", reporting: "Reporting",
};
export const FIELD_ORDER: Field[] = ["actor", "action", "object", "scope", "condition", "threshold", "amount", "percentage", "frequency",
  "deadline", "exception", "documentation", "reporting"];

export const STATUS_LABEL: Record<FieldStatus, string> = {
  equal: "equal", differs: "differs", only_source: "source only", only_target: "target only", absent: "absent",
};

export const FEATURE_LABEL: Record<string, string> = {
  pred_different: "Verdict is DIFFERENT",
  pred_none: "Verdict is NO MATCH",
  n_fields_both_sides: "Fields stated on both sides",
  n_material_diff: "Material differences found",
  single_field_hinge: "Verdict rests on a single field",
  candidates_agree: "Both candidates got the same verdict",
  target_amended_text_only: "Target Direction amended in place",
  ambiguous_matrix_cell: "Class × topic cell marked ambiguous",
};

export const bandTone = (b: Band) => (b === "High" ? "pos" : b === "Medium" ? "warn" : b === "Low" ? "neg" : "neutral") as "pos" | "warn" | "neg" | "neutral";

export const pct0 = (x: number) => `${Math.round(x * 100)}%`;
export const pct1 = (x: number) => `${(x * 100).toFixed(1)}%`;
