/** A one-row audit pack used by the UI tests (offline replay and the AI assistant). */
import type { Pack } from "./types";

export const DISC = "Decision support only; verify against the official RBI text; not legal advice.";
const review = { review_status: "unreviewed" as const, reviewer: "", note: "", timestamp: "" };
const cite = { md_id: "md_00001", paragraph_id: "md_00001::p00001", direction_title: "Fixture Direction", source_url: "https://rbidocs.rbi.org.in/fixture.pdf" };

export const FIXTURE: Pack = {
  pack_id: "fixture_pack", kind: "audit_pack", created_utc: "2026-10-15T00:00:00+00:00",
  profile: { name: "Fixture SFB", entity_class: "Small Finance Banks", as_of: "2026-10-15", last_review: "2025-12-01", activities: ["kyc_aml"], group_classes: [] },
  about: {
    tool: "RBI-ObliBench audit generator", tool_version: "0.1.0", rules_version: "auditgen-rules-v1", rules_sha256: "a".repeat(64),
    corpus: { kind: "research", snapshot_date: "2026-09-25", sha256: "b".repeat(64) }, as_of: "2026-10-15", last_review: "2025-12-01",
    entity_profile: { name: "Fixture SFB", entity_class: "Small Finance Banks", as_of: "2026-10-15", last_review: "2025-12-01", activities: ["kyc_aml"], group_classes: [] },
    validation: { applicability: { precision: 1, recall: 0.815 }, temporal: { accuracy: 1, n_items: 52 }, calendar: { status: "pending", labelled: 0, n: 30 },
      gap_analysis: { kind: "synthetic", missing_recall: 1, missing_precision: 1 }, differential: { note: "review every one" } },
    disclaimer: DISC, freshness: { message: "Corpus snapshot is 20 days old.", warn: false, age_days: 20 }, privacy: "local", excerpt_rule: "≤ 25 words",
  },
  disclaimer: DISC,
  register: [{ ...cite, ...review, row_id: "APP-1", obligation_id: "t1c_md_00001::p00001", section: "1 Scope", clause: "1", excerpt: "The bank shall report fraud within seven days.",
    applies_to: "Small Finance Banks", applicability_basis: "Direction issued for the class", scope_note: "", status: "in force", status_state: "in_force",
    effective_from: "2025-11-28", governing_instrument: "md_00001", governing_url: cite.source_url, amended_by: [], deadline_frequency: "",
    subject_family: "Fraud Risk Management", confidence: 0.5, needs_review: true, filtered_by_activity: false, hidden: false, hidden_reason: "" }],
  changes: [], calendar: [], differential: [], enforcement: [],
  gaps: { files: [{ name: "synthetic.md", sha256: "c".repeat(64), bytes: 10, clauses: 1 }], clauses: 1, obligations: 1, models: { nli: "local" },
    thresholds: { top_k: 5 }, counts: { covered: 0, partial: 0, missing: 1 }, session: null, note: "Synthetic sample policy",
    per_direction: [{ md_id: "md_00001", direction_title: "Fixture Direction", source_url: cite.source_url, covered: 0, partial: 0, missing: 1 }],
    rows: [{ ...cite, ...review, row_id: "GAP-1", obligation_id: "t1c_md_00001::p00001", excerpt: "The bank shall report fraud within seven days.", status: "in force",
      coverage: "missing", confidence: 0.9, matched_clauses: [], top_clauses: [{ clause_id: "synthetic.md#c0000", excerpt: "x", cosine: 0.3, entailment: 0.01, nli_entails: false }],
      enforcement_risk: 0, explanation: null, needs_review: true }] },
  signoff: null, derived_from: null, differential_caution: "", enforcement_label: "Prioritisation context only.", dropped_without_citation: {},
  summary: { register_visible: 1, register_hidden: 0, needs_review: 1, by_status: { "in force": 1 }, changes: 0, calendar_entries: 0, calendar_verify: 0,
    differential_rows: 0, differential_needs_review: 0, enforcement_directions: 0, enforcement_releases: 0, gaps: { missing: 1 }, review_progress: { reviewed: 0, total: 2 } },
};
