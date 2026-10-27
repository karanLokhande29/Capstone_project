/** Shapes of the audit generator's pack JSON (src/auditgen/pack.py). Only the fields the UI reads are typed. */

export type ReviewStatus = "unreviewed" | "confirmed" | "disputed" | "not applicable";

export interface ReviewFields { review_status: ReviewStatus; reviewer: string; note: string; timestamp: string }

export interface Cited extends ReviewFields {
  row_id: string; md_id: string; paragraph_id: string | null; direction_title: string; source_url: string;
  citation_level?: "direction"; needs_review: boolean; confidence?: number | null; excerpt?: string; subject_family?: string;
}

export interface RegisterRow extends Cited {
  obligation_id: string; section: string; clause: string; applies_to: string; applicability_basis: string; scope_note: string;
  status: string; status_state: string; effective_from: string | null; governing_instrument: string; governing_url: string;
  amended_by: { id: string; effective: string | null; url: string; action: string }[]; deadline_frequency: string;
  filtered_by_activity: boolean; hidden: boolean; hidden_reason: string; confidence: number;
}

export interface ChangeRow extends Cited { change: string; governing_instrument: string; governing_title: string; governing_url: string; effective: string | null; status: string }

export interface CalendarRow extends Cited {
  entry_id: string; kind: "recurring" | "fixed" | "event"; frequency: string | null; offset_days?: number; phrase: string; summary: string;
  next_due: string[]; verify: boolean; confidence: number; status: string;
}

export interface DiffRow extends Cited {
  source_class: string; target_class: string; differential: string; semantic_score: number | null; lexical_score: number | null;
  counterpart_paragraph_id: string | null; counterpart_title: string | null; counterpart_url: string | null; counterpart_excerpt: string | null; caution: string;
}

export interface EnfRow extends Cited {
  penalty_count: number; first_date: string | null; last_date: string | null; label: string; link_note: string; link_basis: string[];
  press_releases: { id: string; date: string | null; url: string; amount?: string | null; entity?: string | null }[]; cited_subjects: string[];
}

export interface Clause { clause_id: string; excerpt: string; cosine: number; entailment: number; nli_entails: boolean }

export interface GapRow extends Cited {
  obligation_id: string; coverage: "covered" | "partial" | "missing"; confidence: number; matched_clauses: Clause[]; top_clauses: Clause[];
  enforcement_risk: number; explanation: string | null; status: string;
}

export interface Gaps {
  files: { name: string; sha256: string; bytes: number; clauses: number }[]; clauses: number; obligations: number;
  models: Record<string, string>; thresholds: Record<string, number>; counts: Record<string, number>; rows: GapRow[];
  per_direction: { md_id: string; direction_title: string; source_url: string; covered: number; partial: number; missing: number }[];
  session: string | null; note?: string; explained_with?: string;
}

export interface Validation {
  applicability: { precision?: number; recall?: number; precision_ci?: number[]; recall_ci?: number[]; note?: string; units?: string };
  temporal: { accuracy?: number; accuracy_ci?: number[]; n_items?: number; note?: string };
  calendar: { status: string; precision?: number; n?: number; labelled?: number; sheet?: string; note?: string };
  gap_analysis: { kind?: string; missing_precision?: number; missing_recall?: number; not_covered_recall?: number; kept_marked_covered?: number; note?: string };
  differential: { note?: string; miss_rate?: number };
}

export interface Profile { name: string; entity_class: string; as_of: string; last_review: string; activities: string[]; group_classes: string[] }

export interface About {
  tool: string; tool_version: string; rules_version: string; rules_sha256: string;
  corpus: { kind: string; snapshot_date: string; sha256: string }; as_of: string; last_review: string; entity_profile: Profile;
  validation: Validation; disclaimer: string; freshness: { message: string; warn: boolean; age_days: number | null }; privacy: string; excerpt_rule: string;
}

export interface Summary {
  register_visible: number; register_hidden: number; needs_review: number; by_status: Record<string, number>;
  changes: number; calendar_entries: number; calendar_verify: number; differential_rows: number; differential_needs_review: number;
  enforcement_directions: number; enforcement_releases: number; gaps: Record<string, number> | null;
  review_progress: { reviewed: number; total: number };
}

export interface Pack {
  pack_id: string; kind: "audit_pack"; created_utc: string; profile: Profile; about: About; disclaimer: string;
  register: RegisterRow[]; changes: ChangeRow[]; calendar: CalendarRow[]; differential: DiffRow[]; enforcement: EnfRow[];
  gaps: Gaps | null; signoff: { signer: string; signed_utc: string; complete: boolean; progress: { reviewed: number; total: number } } | null;
  derived_from: string | null; summary: Summary; differential_caution: string; enforcement_label: string;
  dropped_without_citation: Record<string, { count: number; md_ids: string[] }>;
}

export interface PackListItem { pack_id: string; kind?: string; created_utc: string; profile: Profile; summary: Partial<Summary>; file?: string; signed_off?: boolean }

export type Section = "register" | "changes" | "calendar" | "differential" | "enforcement" | "gaps";
