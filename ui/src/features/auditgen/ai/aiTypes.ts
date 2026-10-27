/** Shapes of the generative-AI outputs (src/auditgen/ai_features.py). Only the fields the UI reads are typed. */

export interface AiSource { label?: string; row_id: string; paragraph_id: string | null; direction_title: string; source_url: string }

export interface AiSentence {
  text: string; verified: boolean; reason?: string; entailment?: number | null; citations?: string[]; sources?: AiSource[];
  part?: string; facts?: string[]; check?: string; kind?: string;
}

export interface AiRow { row_id: string; md_id: string; paragraph_id: string | null; direction_title: string; source_url: string }

export interface AiBase {
  created_utc: string; model: string | null; seconds: number; genai_version: string; verifier: string; label: string; disclaimer: string;
  sentences: AiSentence[]; abstained?: boolean; note?: string; row?: AiRow;
}

export interface AskResult extends AiBase {
  question: string; answer: string; attempts: number;
  evidence: (AiSource & { status: string; deadline: string; excerpt: string; score: number; subject_family?: string })[];
}

export interface ExplainResult extends AiBase { evidence_quote: string; evidence_quote_found: boolean; rule_deadline: string; status: string }

export interface ChangeResult extends AiBase {
  change: string; amendment?: { id: string; title: string; url: string; effective: string | null; published?: string | null };
  before_excerpt?: string; after_excerpt?: string | null;
}

export interface Fact { id: string; text: string; ref: string | null; url?: string }

export interface MemoResult extends AiBase { subject: string; sections: { heading: string; sentences: AiSentence[] }[]; facts: Fact[] }

export interface PlanItem { item: string; ref: string | null; fact: string | null; url?: string | null; priority: "high" | "medium" | "low"; text: string; why: string; verified: boolean; reason: string }
export interface PlanResult extends AiBase { items: PlanItem[] }

export interface DraftResult extends AiBase {
  title: string; clause: string; owner: string; notes: string; company: string; stray_numbers: string[];
  check: { coverage: "covered" | "partial" | "missing"; entailment: number; cosine: number; obligation_sentence?: string; rule?: string };
}

export interface CalItem {
  entry_id: string; row_id: string; paragraph_id: string; direction_title: string; source_url: string; summary: string;
  ai: { kind: string; frequency: string | null; offset_days: number | null; trigger: string | null; due_date: string | null; what: string; quote: string; quote_found: boolean };
  rule: { kind: string; frequency: string | null; offset_days?: number | null; phrase?: string; confidence?: number } | null;
  agrees_with_rule: boolean | null; verified: boolean;
}
export interface CalendarResult extends AiBase { results: CalItem[]; agreement: { n: number; agree: number; rate: number | null } }

export interface DiffResult extends AiBase {
  judgement: string; rule: string; pack_label: string; caution: string; field_comparison: Record<string, string | null>;
  differences: { field: string; source: string; target: string; source_found: boolean; target_found: boolean }[];
}

export interface SuggestResult extends AiBase { section: string; suggestion: string; raw_suggestion: string; check: string; current_review_status: string }

export interface AiStore {
  pack_id: string; kind?: "ai_outputs"; label?: string; genai_version?: string;
  ask?: AskResult[]; explain?: Record<string, ExplainResult>; change?: Record<string, ChangeResult>; memo?: MemoResult; plan?: PlanResult;
  draft?: Record<string, DraftResult>; calendar?: CalendarResult; diff?: Record<string, DiffResult>; suggest?: Record<string, SuggestResult>;
}

export interface AiStatus {
  available: boolean; model: string | null; pulled: string[]; preferred?: string[]; reason?: string; genai_version?: string; host?: string;
  verifier?: string; embedding?: string; label?: string; privacy?: string; remote_api_calls?: boolean;
}

export interface ActivityRow { utc: string; pack_id: string; feature: string; key: string | null; model: string | null; seconds: number | null; verified: number; unverified: number; abstained: boolean; input_sha256: string; output_sha256: string }
