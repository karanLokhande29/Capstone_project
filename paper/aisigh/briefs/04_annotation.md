# Brief: Annotation and reliability

Word budget: **420 words** (6-page) / 620 (8-page, paid). Prose is written by the authors.

**Claims:**
- Guidelines v3/v3.1; per-class judgement same / different / none / unsure; the flag is derived (v3.6).
- **The gold is single-expert:** **106** (`R:05_t1_benchmark.validated`) items labelled by rater_1.
  - Routes: adjudicated **38** (`R:05_t1_benchmark.route_counts.adjudicated`), retest-consistent **6** (`R:05_t1_benchmark.route_counts.retest-consistent`), single-pass **62** (`R:05_t1_benchmark.route_counts.single-pass`).
  - Adjudication was by the same annotator (against his own second pass, a non-independent team review, or his own `unsure`).
- Inter-rater reliability on a **separate 30-item sample drawn outside the gold** (three raters, before adjudication):
  - class **0.774 [0.645, 0.886] (n items 20)** (`R:05_t1_benchmark.irr.fleiss.per_class_judgement`);
  - flag **0.571 [0.289, 0.807] (n items 20)** (`R:05_t1_benchmark.irr.fleiss.differential_flag`);
  - not_obligation **0.392 [-0.015, 0.689] (n items 30)** (`R:05_t1_benchmark.irr.fleiss.not_obligation`).
  - It is reported as evidence about the guidelines and raters, **not** as reliability of the 106 gold labels.
- **t1v3** (supervised independent annotation by annotators not otherwise involved in the project; FINAL-PHASE-4X): {{T1V3-class-k}}, {{T1V3-flag-k}} (pre-registered; if completed).
- **Test–retest (supplementary; recall may inflate agreement):** rater_1 blind retest, actual gap 11.7–18.6 h:
  - flag **0.426 [0.091, 0.730] (n items 20)** (`R:05_t1_benchmark.retest.phase2.all_25.differential_flag`);
  - class **0.550 [0.333, 0.752] (n items 20)** (`R:05_t1_benchmark.retest.phase2.all_25.per_class_judgement`).
  - t1v3 short-interval retest: {{…}}.
- **Disclosure (one sentence):** an earlier second-rater round was excluded because the independence check failed (identical free text across the two raters' files), so independence could not be established; its ratings are not used anywhere.

**Floats:** Fig. `fig:provenance` (two-column); Table `tab:reliability`.

**Disclosures (required):**
- The same two P2-002 candidates were shown in every pass (bias toward P2-002; as for T2).
- The guidelines do not define incomplete passages, classifications or examples.
- The 26–27 Sep team-review episode (not independent; never in κ).
- The minutes logs are the time record.
- Statistics: Fleiss \cite{fleiss1971}, Cohen \cite{cohen1960}, bootstrap \cite{efron1979}, Wilson \cite{wilson1927}.

