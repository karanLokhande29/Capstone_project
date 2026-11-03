# Brief: Tasks, systems and metrics

Word budget: **300 words** (6-page) / 450 (8-page, paid). Prose is written by the authors.

**Claims:**
- T1: per-class judgement and derived flag. Metrics: 3-way flag Macro-F1 (a predicted `ambiguous` is wrong) and collapsed absent-vs-present Macro-F1 (the fair comparison with P2-002).
- T2: counterpart retrieval, nDCG@10, three relevance sets with stated biases.
- T3: status exact match and supersession F1.
- T4: RePASs composite paired differences; human faithful/answers_question ratings.
- Systems: majority (in-sample), P2-002 candidates, class-blind LLM, class-aware LLM, final agentic (class filter + NLI verifier), ablation A, long-context (100K cap).
- LLM: gemini-3.5-flash-lite, temperature 0, minimal thinking, frozen prompts (sha256).
- CIs: 2,000 item resamples (bootstrap \cite{efron1979}); Wilson intervals for proportions \cite{wilson1927}; paired differences via the one CI rule (`src/eval/ci_format.py`).
- External benchmarks (extensions): ObliQA was used for evaluation only and is not redistributed; no licence is stated by the maintainers. Report aggregate metrics only. IndiaFinBench \cite{indiafinbench} (CC BY 4.0) is cited, not redistributed.
- Citations: the LLMs \cite{gemini35fl,gptoss}; the verifier NLI model \cite{nlideberta} (DeBERTaV3 \cite{debertav3}); RePASs \cite{gokhan2024regnlp,repass}, whose obligation classifier is fine-tuned from LEGAL-BERT \cite{legalbert}.

**Floats:** Fig. 3 (architecture) is in the 8-page variant only.

