# Brief: Abstract

Word budget: **170 words** (6-page) / 200 (8-page, paid). Prose is written by the authors.

**Claims (in order):**
- Problem: obligations in parallel RBI Master Directions for different regulated-entity classes; a counterpart may exist but differ.
- Resource: corpus of **381** (`R:01_corpus.directions`) Directions / **76,188** (`R:01_corpus.paragraphs`) paragraphs; four tasks (T1–T4).
- T1: **106** (`R:05_t1_benchmark.validated`) expert-validated items (single expert). Inter-rater κ on a separate 30-item three-rater sample: **0.774 [0.645, 0.886] (n items 20)** (`R:05_t1_benchmark.irr.fleiss.per_class_judgement`) (class judgements); t1v3 supervised round {{T1V3-class-k}} if completed.
- Main finding: no LLM system beats the embedding-matching baseline on collapsed flag F1 (class-blind − P2-002 **-0.019 [-0.114, +0.072]** (`R:07_t1_systems.paired.Class-blind LLM − P2-002 candidates.collapsed_macro_f1`)). Every system is weak on `different`: **56** (`EA:a_different_missed.missed_by_every_llm_system`) of **78** (`EA:a_different_missed.gold_different_units`) missed by every LLM system.
- Targeted experiment: structured comparator {{cmp-diffF1}}.
- T4: RePASs is gameable by concatenation (**+0.375 [+0.325, +0.427]** (`R:09_t4.paired.concatenated - genuine.composite_score`)).
- Release: pointer-only, no RBI text.

**Must not say:**
- "three independent annotators" for the gold;
- "second-rater κ" without "on a separate 30-item sample, not part of the gold".

