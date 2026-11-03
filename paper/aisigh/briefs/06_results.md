# Brief: Results

Word budget: **650 words** (6-page) / 950 (8-page, paid). Prose is written by the authors.

**RQ1 / T2:**
- The class filter gain is **+0.451 [+0.421, +0.481]** (`R:06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired`) on xclass_t1, **partly by construction**.
- Dense **0.421** (`R:06_t2_retrieval.p3001.t2_xclass_t1.systems.dense.ndcg.mean`) vs BM25 **0.458** (`R:06_t2_retrieval.p3001.t2_xclass_t1.systems.bm25.ndcg.mean`) (xclass_t1).

**RQ2 / T1** (106-item gold; these numbers are final):
- No LLM system beats P2-002 on collapsed F1 (class-blind − P2-002 **-0.019 [-0.114, +0.072]** (`R:07_t1_systems.paired.Class-blind LLM − P2-002 candidates.collapsed_macro_f1`)).
- Every system is weak on `different`:
  - different F1 class-blind **0.321** (`R:07_t1_systems.systems.class_blind.judgement_f1_per_label.different`);
  - missed by all five systems **56** (`EA:a_different_missed.missed_by_every_llm_system`) of **78** (`EA:a_different_missed.gold_different_units`) (definition: all five answered).
  - comparator: {{cmp-diffF1}}.
- Verifier (ablation C): 3-way **-0.068 [-0.132, -0.012]** (`R:07_t1_systems.paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1`), coverage **-0.217 [-0.292, -0.142]** (`R:07_t1_systems.paired.Ablation C on T1: final agentic − class-aware.coverage`). 
- Long-context: **102** (`R:07_t1_systems.systems.long_context.n_items`) of 106 answered at the 100K cap.

**RQ3 / T4:**
- Concatenated − genuine **+0.375 [+0.325, +0.427]** (`R:09_t4.paired.concatenated - genuine.composite_score`) (pre-registered: reproduces the gameability reported by \cite{aueb2025rirag}; metric \cite{gokhan2024regnlp}).
- Negated **-0.322 [-0.390, -0.243]** (`R:09_t4.paired.adv_negated - genuine.composite_score`); off-topic **-0.141 [-0.206, -0.080]** (`R:09_t4.paired.adv_offtopic - genuine.composite_score`).
- ρ(RePASs, faithful) **0.731 [0.535, 0.845]** (`R:09_t4.human.all_rated.spearman_composite_score_vs_faithful`); ρ(answers_question) **0.008 [-0.323, 0.339]** (`R:09_t4.human.all_rated.spearman_composite_score_vs_answers_question`).
- Three-rater T4 (T4v3, if completed): {{T4V3-k}}.

**T3:**
- Filter on **1.000 [1.000, 1.000]** (`R:08_t3.t3.on.status_exact_match`) — **circular by construction**; filter off **0.538 [0.404, 0.673]** (`R:08_t3.t3.off.status_exact_match`).

**Floats:** `tab:t2`, `tab:t1`, `tab:t3t4`.

