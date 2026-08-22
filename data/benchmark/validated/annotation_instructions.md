# T1 Annotation Instructions (Week 5)

Annotators: Akash, Karan, Meer — label **independently**; do not share answers.

## Fields to fill

- `applies_to_label`: entity class(es) the obligation binds
- `differential_flag_label`: one of `shared` | `class-specific` | `absent`
- `in_force_confirmed`: yes/no/uncertain given temporal metadata
- `notes`: brief justification / ambiguity

## Rules

- Use the `obligation_span_ref` / `paragraph_id` to look up source text in
  `data/processed/{document_id}.jsonl` (local only).
- Do **not** invent obligations; if unclear, mark absent/uncertain in notes.
- Candidate flags in the sample are **not gold** — re-judge from source.

## Sample size rationale

Annotation capacity for this run capped at max_validation_sample=30 (config). Stratified round-robin over (differential_flag, entity_class). Not the dossier ~350–400 ceiling.
