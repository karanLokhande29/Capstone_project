"""Markdown report for P3-002 Part B: reports/p3002_t4_repass_audit.md."""

from __future__ import annotations

from typing import Any, Mapping

TYPES = ("genuine", "concatenated", "adv_negated", "adv_offtopic")
GAMING = ("concatenated", "adv_negated", "adv_offtopic")
LABEL = {"genuine": "Genuine (LLM, passages only)", "concatenated": "Concatenated (verbatim obligations)",
         "adv_negated": "Adversarial: negated", "adv_offtopic": "Adversarial: off-topic"}
COMP = {"composite_score": "RePASs", "entailment_score": "Entailment", "contradiction_score": "Contradiction",
        "obligation_coverage_score": "Obligation coverage"}


def _ci(v: Mapping[str, Any], d: int = 3) -> str:
    if v.get("mean") is None:
        return "n/a"
    return f"{v['mean']:.{d}f} [{v['ci_low']:.{d}f}, {v['ci_high']:.{d}f}]"


def _sd(v: Mapping[str, Any]) -> str:
    return f"{v['mean']:+.3f} [{v['ci_low']:+.3f}, {v['ci_high']:+.3f}]"


def _rho(v: Mapping[str, Any]) -> str:
    if v["rho"] is None:
        return "undefined"
    return f"{v['rho']:.3f} [{v['ci_low']:.3f}, {v['ci_high']:.3f}]"


def _excerpt(text: str, n: int = 240) -> str:
    t = " ".join(text.split())
    return (t[:n] + " …") if len(t) > n else t


def audit_report(m: Mapping[str, Any]) -> str:
    main, sens, hum = m["main"], m["sensitivity_without_bad_questions"], m["human"]
    prov = m["provenance"]
    rp, tr = prov["repass"], prov["repass"].get("training") or {}
    qrun, grun = prov.get("questions_run") or {}, prov.get("genuine_run_api") or {}
    n = main["n_questions"]
    L: list[str] = ["# P3-002 — T4: is RePASs gameable on RBI Master Directions?\n"]
    L.append("**RQ3.** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what "
             "minimal repair resists concatenation and verbatim extraction?\n")
    L.append("## Answer\n")
    for t in GAMING:
        c = main["paired"][f"{t} - genuine"]["composite_score"]
        L.append(f"- **{LABEL[t]} − genuine:** RePASs difference {_sd(c)}, n = {n} questions → "
                 f"**{main['verdicts'][t]}**.")
    rf = main["repair"]["genuine - concatenated"]
    rsp = hum["all_rated"]["spearman_repaired_vs_faithful"]
    L.append(f"- **Exploratory repair:** repaired(genuine) − repaired(concatenated) = {_sd(rf)} → **{rf['verdict']}**. "
             "This works only because the overlap penalty zeroes every verbatim answer. The repaired score no longer "
             f"tracks human faithfulness (ρ = {_rho(rsp)}), so it is **not** a usable repair as it stands. It was "
             "designed with the RIRAG finding in mind and tested on the same 30 questions, so even the ranking "
             "result is optimistic.")
    sp = hum["all_rated"]["spearman_composite_score_vs_faithful"]
    sq = hum["all_rated"]["spearman_composite_score_vs_answers_question"]
    L.append(f"- **Metric vs human:** Spearman ρ between RePASs and human faithfulness = {_rho(sp)}; between "
             f"RePASs and human `answers_question` = {_rho(sq)}; n = {sp['n']} rated answers (one rater).\n")
    hb = hum["all_rated"]["by_type"]
    rel = {t: main["by_type"][t]["relevance"]["mean"] for t in TYPES}
    L.append("## Interpretation\n")
    L.append(f"- **What RePASs rewards.** RePASs tracks faithfulness to the passages, and the human ratings agree "
             f"that verbatim extracts are faithful: concatenated answers were rated {hb['concatenated']['faithful']['mean']:.2f} "
             f"on `faithful` against {hb['genuine']['faithful']['mean']:.2f} for genuine ones. What it does not track is "
             f"whether the answer addresses the question: concatenated answers were rated "
             f"{hb['concatenated']['answers_question']['mean']:.2f} on `answers_question` against "
             f"{hb['genuine']['answers_question']['mean']:.2f} for genuine ones, and RePASs' correlation with "
             "`answers_question` is near zero. The gameability that reproduces is this one: concatenating the "
             "retrieved obligations outscores a genuine answer without answering the question better.")
    L.append("- **Adversarial answers.** RePASs is not fooled by negated or off-topic answers: both score clearly "
             "below genuine, mostly through contradiction (negated) and missing entailment and coverage (off-topic).")
    L.append(f"- **Why genuine answers score low.** Genuine answers carry high contradiction "
             f"({main['by_type']['genuine']['contradiction_score']['mean']:.2f}) and low coverage "
             f"({main['by_type']['genuine']['obligation_coverage_score']['mean']:.2f}). The small NLI model often "
             "scores rated-faithful paraphrases as contradictions: one example below (T4Q06, a \"No.\"-style answer "
             "with citation markers and bold text) is rated fully faithful by the human and scores contradiction "
             "0.99. Which of these features drives it was not tested. Coverage rewards restating every obligation in the passages, including those irrelevant to the "
             "question.")
    L.append(f"- **The repair.** The relevance term is close to zero for every type (genuine {rel['genuine']:.3f}, "
             f"concatenated {rel['concatenated']:.3f}), so the repaired ordering comes entirely from the overlap "
             "penalty. That penalty removes the concatenation advantage by construction. It also sends every "
             "faithful verbatim answer to 0, which is why the repaired score correlates with human faithfulness at "
             "about zero or below. A repair that resists concatenation without punishing faithful quotation would "
             "need a question-relevance signal that actually discriminates; this NLI model does not provide one. "
             "That design question belongs to later work and is not settled here.\n")
    L.append("Prior evidence, for context only: on ObliQA a naive obligation-concatenation system scored RePASs 0.947, "
             "above human experts (AUEB-Archimedes at RIRAG-2025, arXiv 2412.11567). Nothing here assumed that "
             "result; the verdict rule was fixed before scoring.\n")

    L.append("## Setup\n")
    L.append(f"- **RePASs:** {rp['url']} at commit `{rp['commit']}`, code unmodified. Their scripts ran in a "
             "separate venv (transformers 4.x: their tokenizer call `encode_plus` no longer exists in transformers "
             "5), called through `scripts/run_repass.py`, in their JSON format (`QuestionID`, `RetrievedPassages`, "
             "`Answer`).")
    L.append(f"  - NLI for entailment and contradiction: `{rp['nli_model']}`. NLI for obligation coverage: "
             f"`{rp['coverage_nli_model']}` (entailment above 0.7). Obligation classifier: `{rp['obligation_base_model']}` "
             "fine-tuned with their `scripts/train_model.py` on their dataset.")
    L.append("  - Composite, as implemented: **(obligation coverage + entailment − contradiction + 1) / 3**. "
             "Entailment and contradiction are the mean over answer sentences of the maximum over passage sentences; "
             "their code joins the passages into one string first.")
    ev = [e for e in tr.get("eval_by_epoch", []) if e.get("eval_loss") == tr.get("best_metric_eval_loss")]
    best = ev[0] if ev else {}
    L.append(f"  - Classifier training: device {tr.get('trainer_device')}, seed {tr.get('seed')}, "
             f"{(tr.get('runtime_seconds') or 0) / 60:.1f} min, early stop after epoch {tr.get('epochs_run')}; best "
             f"checkpoint validation F1 {best.get('eval_f1', float('nan')):.3f} (their 80/20 split, not our data).")
    scoring = (rp.get("scoring") or {}).get("runs", {})
    devs = sorted({v.get("device") for v in scoring.values() if v.get("device")})
    L.append(f"  - Scoring device: {', '.join(devs) or 'n/a'} (their code picks CUDA or CPU only).")
    smp = prov["sample"]
    L.append(f"- **Questions:** {n} obligation paragraphs from the T1 validated set, stratified by class "
             f"({smp['classes']} classes, {smp['families']} subject families, seed {smp['seed_used']}). "
             "One question per paragraph was drafted by the LLM (prompt, model id and output logged in "
             "`t4_questions_v1.jsonl`).")
    L.append(f"- **LLM:** questions and genuine answers ran on **Groq `{(qrun.get('models') or ['?'])[0]}`**, not the "
             f"configured Gemini `{prov['llm_config']['model']}`. Gemini's free tier allows 20 requests per day per "
             "model, and that quota ran out after 7 questions. Following the P3-002 rule, each step was rerun entirely "
             "on the fallback (the 7 Gemini questions were discarded, never mixed). Temperature 0, cached, capped. "
             f"Calls: questions {qrun.get('api_calls')}, genuine answers {grun.get('api_calls')}.")
    ranks = prov["retrieval_source_ranks"]
    in3 = sum(1 for r in ranks.values() if r and r <= 3)
    L.append(f"- **Passages:** the P3-001 class-aware hybrid top 3 for the question (target class = the paragraph's "
             f"class), plus the source paragraph when it was not in the top 3. The source was in the top 3 for "
             f"{in3}/{n} questions; ranks: {sorted(ranks.values(), key=lambda x: (x is None, x or 0))}.")
    L.append("- **Answer types** (each in its own file):")
    L.append("  - `genuine`: the LLM answers from the passages only and cites passage ids. The Groq model writes its "
             "citations as 【…】 rather than […].")
    L.append("  - `concatenated`: no LLM. Every sentence of the passages that holds a kept P2-001 (rules v4) deontic "
             "cue, verbatim, in passage order.")
    L.append("  - `adv_negated`: the concatenated answer with shall/must/is required to flipped and every number "
             "doubled (enumerators like \"(1)\" included).")
    L.append("  - `adv_offtopic`: verbatim kept-cue sentences from seeded random Directions in a different subject "
             "family, cut to the concatenated answer's length.\n")

    L.append(f"## RePASs by answer type (n = {n} each)\n")
    L.append("| Answer type | " + " | ".join(COMP.values()) + " |")
    L.append("|---|" + "---|" * len(COMP))
    for t in TYPES:
        L.append(f"| {LABEL[t]} | " + " | ".join(_ci(main["by_type"][t][c]) for c in COMP) + " |")
    L.append("\nMean [95% CI], bootstrap over questions (2,000 resamples, seeded).\n")
    L.append("## Paired differences against genuine (same questions, same resamples)\n")
    L.append("| Comparison | " + " | ".join(f"Δ {v}" for v in COMP.values()) + " | Verdict |")
    L.append("|---|" + "---|" * len(COMP) + "---|")
    for t in GAMING:
        p = main["paired"][f"{t} - genuine"]
        L.append(f"| {LABEL[t]} − genuine | " + " | ".join(_sd(p[c]) for c in COMP) + f" | {main['verdicts'][t]} |")
    L.append("\nVerdict rule (on the RePASs difference): CI entirely ≥ 0 → reproduces; entirely < 0 → does not "
             f"reproduce; otherwise inconclusive at n = {n}. For the adversarial types, \"reproduces\" means the "
             "metric scores the adversarial answer at least as high as the genuine one.\n")
    L.append(f"**Sensitivity:** excluding the {len(sens['excluded'])} questions flagged `bad_question` "
             f"({', '.join(sens['excluded']) or 'none'}), n = {sens['n_questions']}: "
             + "; ".join(f"{t} − genuine {_sd(sens['paired'][f'{t} - genuine']['composite_score'])} → "
                         f"{sens['verdicts'][t]}" for t in GAMING) + ".\n")

    L.append("## Human faithfulness vs the metric\n")
    L.append(f"One rater (Karan), blind to answer type, scores and model. {hum['all_rated']['n']} answers: "
             + ", ".join(f"{v} {k}" for k, v in hum["sheet_quotas"].items())
             + ". Each question appears once on the sheet.\n")
    L.append("| Answer type | n | Human `faithful` (0–2) | Human `answers_question` (0–2) |")
    L.append("|---|---|---|---|")
    for t in TYPES:
        b = hum["all_rated"]["by_type"][t]
        L.append(f"| {LABEL[t]} | {b['faithful']['n']} | {_ci(b['faithful'], 2)} | {_ci(b['answers_question'], 2)} |")
    L.append("\nPer-type n is 5–10, so these CIs are wide.\n")
    L.append("| Correlation (Spearman, n rated answers) | All rated | Without bad questions |")
    L.append("|---|---|---|")
    for metric, mlab in (("composite_score", "RePASs"), ("repaired", "Repaired score")):
        for h in ("faithful", "answers_question"):
            k = f"spearman_{metric}_vs_{h}"
            a, b = hum["all_rated"][k], hum["without_bad_questions"][k]
            L.append(f"| {mlab} vs `{h}` | {_rho(a)} (n = {a['n']}) | {_rho(b)} (n = {b['n']}) |")
    mins = hum["minutes"]
    L.append(f"\nRating time from the accepted minutes log: {mins['total']:.0f} min for {hum['all_rated']['n']} "
             f"answers, **{mins['per_answer']:.1f} min per answer** "
             f"(blocks: {', '.join(f'{b['minutes']:.0f}' for b in mins['blocks'])} min).")
    L.append(f"`bad_question` = yes on {hum['bad_question_count']} of 30 questions ({', '.join(hum['bad_questions'])}); "
             "the stop threshold is more than 5.\n")

    rep = m["protocol"]["repair"]
    L.append("## Exploratory repair\n")
    L.append(f"Declared in config (`t4.repair`) at {rep['declared_utc']}, before any answer was scored:")
    L.append(f"- `lcs_ratio` = token LCS(answer, retrieved passages) / answer tokens; `penalty` = "
             f"clip((lcs_ratio − τ) / (1 − τ), 0, 1), τ = {rep['lcs_tau']};")
    L.append("- `relevance` = mean over answer sentences of RePASs' own NLI entailment probability, with the question "
             "as premise (question ⇒ answer);")
    L.append("- `repaired` = (1 − penalty) × (RePASs + relevance) / 2.\n")
    L.append("| Answer type | LCS ratio | Penalty | Relevance | Repaired |")
    L.append("|---|---|---|---|---|")
    for t in TYPES:
        b = main["by_type"][t]
        L.append(f"| {LABEL[t]} | {_ci(b['lcs_ratio'])} | {_ci(b['overlap_penalty'])} | {_ci(b['relevance'])} | "
                 f"{_ci(b['repaired'])} |")
    L.append("\n| Repaired: genuine − | Difference | Reading |")
    L.append("|---|---|---|")
    for t in GAMING:
        r = main["repair"][f"genuine - {t}"]
        L.append(f"| {LABEL[t]} | {_sd(r)} | {r['verdict']} |")
    L.append("\n**Caveat:** τ and the repair were designed with the RIRAG concatenation finding in mind and are "
             "tested on the same 30 questions, so the result is optimistic. It is not validated on held-out data. "
             "The overlap penalty is aimed squarely at verbatim answers, so it also penalises a genuine answer that "
             "quotes heavily. The relevance term uses a small NLI model (`nli-deberta-v3-xsmall`) on "
             "question ⇒ sentence pairs, which is not what it was trained for.\n")

    L.append("## Examples (3 per type, seeded, from the rated answers)\n")
    L.append("Answer excerpts are limited to 25 words (P5-001 RBI-text policy); the full answers are pointers into the T4 "
             "answer files, rebuilt locally by `release/rehydrate.py`.\n")
    for t in TYPES:
        L.append(f"### {LABEL[t]}\n")
        for e in m["examples"][t]:
            L.append(f"- **{e['question_id']}** — {e['question']}  ")
            L.append(f"  Passages: {', '.join(e['passage_ids'])}  ")
            L.append(f"  Answer (excerpt, ≤ 25 words; full text via {e['answer_pointer']['file']}, "
                     f"{e['answer_pointer']['question_id']}): “{e['answer_excerpt']}”  ")
            L.append(f"  RePASs {e['composite_score']:.3f} (entail {e['entailment_score']:.3f}, contra "
                     f"{e['contradiction_score']:.3f}, coverage {e['obligation_coverage_score']:.3f}); repaired "
                     f"{e['repaired']:.3f}; human faithful {e['faithful']}, answers_question {e['answers_question']}"
                     + ("; **bad question**" if e["bad_question"] else ""))
        L.append("")

    L.append("## Limitations\n")
    L.append(f"- **n = {n} questions**, and 5–10 rated answers per type. Point estimates are unstable.")
    L.append("- **One rater.** No agreement statistic exists for the faithfulness labels.")
    L.append(f"- **LLM-drafted questions.** {hum['bad_question_count']} of 30 were flagged `bad_question`; results "
             "without them are under Sensitivity.")
    L.append("- **The repair is not validated on held-out data** (see its caveat).")
    L.append(f"- **Model ids.** Questions and genuine answers: Groq `{(qrun.get('models') or ['?'])[0]}` (Gemini's "
             "free daily quota was exhausted). RePASs models as listed under Setup. A different generator could "
             "change the genuine scores.")
    L.append("- **Blinding is partial.** Type, scores and model were hidden, but LLM answers read differently from "
             "verbatim extracts (citations, paraphrase), so a rater can infer the rough type.")
    wd = hum["receipt"].get("withdrawn_submissions") or []
    if wd:
        L.append(f"- **Sheet provenance.** The accepted sheet (sha256 `{hum['receipt']['sha256'][:12]}…`, saved "
                 f"{hum['receipt']['file_saved_local']}) was declared by Karan as manually annotated, final and "
                 f"complete. An earlier submission (sha256 `{wd[0]['sha256'][:12]}…`) was not ingested because its "
                 "minutes log post-dated its own arrival. Karan later described it as a mock file.")
    L.append("- **Genuine answers were scored as written,** including the model's 【…】 citation markers and markdown "
             "bold. These may depress their NLI scores. A rescoring with markers stripped was not run.")
    L.append("- RePASs was run on the CPU (their code), and its NLI inputs truncate long passages.\n")
    L.append(f"Generated {m['analysed_utc']} by `scripts/run_t4.py analyze`. Raw per-answer scores: "
             "`data/benchmark/t4/t4_per_answer_v1.jsonl` and `t4_repass_scores_v1.jsonl`.")
    return "\n".join(L) + "\n"
