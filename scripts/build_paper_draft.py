#!/usr/bin/env python3
"""FINAL-MASTER-AND-PAPER Part C: the complete paper draft, paper/aisigh/main.tex. Every number is read from the bundles
(scripts/docnum.py); the tables come from scripts/build_paper_tables_final.py.

    python3 scripts/build_paper_draft.py [--zip] [--docx]

Writes:
- main.tex;
- with --zip: the Overleaf zip (main.tex, refs_verified.bib, the tables, the figures);
- with --docx: a pandoc .docx for reading (approximate).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import docnum as D  # noqa: E402

PAPER = ROOT / "paper/aisigh"
T, P = "R2:tables", "R2:phase4"


def x(s: str) -> str:
    """Make a rendered number string LaTeX-safe (math minus, escaped percent)."""
    s = re.sub(r"(?<![\w$])-(?=\d)", "$-$", s)
    return s.replace("%", "\\%").replace("−", "$-$")


def ci(ref): return x(D.ci(ref))
def n(ref): return x(D.n(ref))
def f3(ref): return x(D.f3(ref))
def kap(ref): return x(D.ci(ref))


def build() -> str:
    cmp_ok = D.opt(f"{P}.comparator.metrics.n_items", 0) > 0
    pa = f"{P}.t1_paired"
    m = f"{P}.missed_by_every_llm_system"
    irr = T + ".05_t1_benchmark.irr.fleiss"
    rt = T + ".05_t1_benchmark.retest.phase2.all_25"
    lo_c, hi_c = D.class_range()
    gap = D.gap().replace("–", "--")
    cmpk = f"{P}.preregistered_comparisons.comparator − class_aware.judgement"
    rr = f"{P}.retrieval_vs_reasoning.per_system"
    reas = D.n(f"{P}.retrieval_vs_reasoning.five_llm_systems_total.reasoning")
    errs = D.n(f"{P}.retrieval_vs_reasoning.five_llm_systems_total.errors")

    ea = "EA:b_verifier_abstentions.Final agentic"
    pi = "EA:a_different_missed.per_system_predicted_instead"
    cmp_abs = (f" A pairwise structured comparator, frozen before any test run, reaches \\textit{{different}} F1 "
               f"{f3(P + '.comparator.different.different_f1')}.") if cmp_ok else ""
    cmp_res = ""
    if cmp_ok:
        cmp_res = (
            f"\\subsection{{Targeted experiment: structured comparison}}\n"
            f"Table~\\ref{{tab:cmp}} gives the pre-registered comparisons. Against the class-aware LLM, the comparator changes "
            f"\\textit{{different}} F1 by {ci(cmpk + '.different_f1')}, \\textit{{different}} recall by {ci(cmpk + '.different_recall')} and "
            f"judgement Macro-F1 by {ci(cmpk + '.judgement_macro_f1')}. Of the units every LLM system missed, it recovers "
            f"{n(m + '.A_all_five_answered.comparator_correct')} of {n(m + '.A_all_five_answered.missed')}. Its errors run "
            f"\\textit{{different}}$\\rightarrow$\\textit{{same}} {n(P + '.comparator.different.different_to_same')} times and "
            f"\\textit{{different}}$\\rightarrow$\\textit{{none}} {n(P + '.comparator.different.different_to_none')} times. "
            f"On its development set (the separate 30-item set) it had reached \\textit{{different}} F1 "
            f"{f3(P + '.comparator_dev.final.per_label.different.f1')}.\n\n\\input{{tables/tab_comparator}}\n")

    return rf"""% DRAFT for author revision — authors must rewrite prose in their own words before submission (venue AI-content limit < 20%)
% AISIGH-SD 2026 (IEEE, CMT). IEEEtran conference, two-column. Overleaf: pdfLaTeX, no shell-escape. Not anonymous.
% Target 6 pages (7-page fallback, paid). Numbers are generated from reports/results_v2.json by scripts/build_paper_draft.py
% and scripts/build_paper_tables_final.py — regenerate rather than hand-edit numbers.
\documentclass[conference]{{IEEEtran}}
\IEEEoverridecommandlockouts
\usepackage{{cite}}
\usepackage{{amsmath,amssymb}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{url}}
\usepackage{{xcolor}}
\newcommand{{\placeholder}}[1]{{\textcolor{{red}}{{\textbf{{[#1]}}}}}}

\begin{{document}}

\title{{RBI-ObliBench: Entity-Class Applicability, Differential Obligations and Metric Integrity on Reserve Bank of India Master Directions}}

\author{{\IEEEauthorblockN{{Karan Lokhande}}
\IEEEauthorblockA{{SVKM's NMIMS Mukesh Patel School of\\ Technology Management \& Engineering\\ Mumbai, India\\ \placeholder{{email}}}}
\and
\IEEEauthorblockN{{Akash Goyal}}
\IEEEauthorblockA{{SVKM's NMIMS Mukesh Patel School of\\ Technology Management \& Engineering\\ Mumbai, India\\ \placeholder{{email}}}}
\and
\IEEEauthorblockN{{Meer Magia}}
\IEEEauthorblockA{{SVKM's NMIMS Mukesh Patel School of\\ Technology Management \& Engineering\\ Mumbai, India\\ \placeholder{{email}}}}
}}

\maketitle

\begin{{abstract}}
Regulated entities in India follow parallel Master Directions issued by the Reserve Bank of India (RBI) for banks,
non-banking companies, co-operative banks and other classes. The same duty often appears for several classes, sometimes with a
different threshold, deadline or scope. We present RBI-ObliBench, built on {n(T + '.01_corpus.directions')} Master Directions,
with four tasks: entity-class applicability and differential obligation (T1), cross-class counterpart retrieval (T2), temporal status
(T3) and an audit of the RePASs faithfulness metric (T4). T1 has {n(T + '.05_t1_benchmark.validated')} expert-validated items.
A class filter sharply improves counterpart retrieval, but no LLM system beats an embedding-matching baseline on collapsed T1
flag F1, and most gold \textit{{different}} judgements are missed by every system, usually with the counterpart already in
context.{cmp_abs} An NLI verifier lowers T1 F1, and a long-context model is competitive with retrieval. RePASs rewards verbatim
concatenation on RBI text, as reported for ObliQA. The release is pointer-only and contains no RBI text.
\end{{abstract}}

\begin{{IEEEkeywords}}
regulatory NLP, benchmark, retrieval-augmented generation, differential obligations, evaluation metrics
\end{{IEEEkeywords}}

\section{{Introduction}}\label{{sec:intro}}
Compliance teams in Indian finance work across entity classes: a commercial bank, a small finance bank and an urban co-operative
bank each have their own Master Direction on the same subject \cite{{rbi}}. A question that recurs in practice is not only
\emph{{which}} obligations bind a class, but \emph{{where parallel Directions differ}}. A duty may exist for two classes with a
different threshold or deadline, and a system that reports ``same'' hides exactly the difference a compliance officer needs.

Consider a requirement to put a Board-approved outsourcing policy in place. It appears in the Directions for several classes, but
the scope, the approving body or the reporting line can differ from one class to the next. A retrieval system that finds the
right counterpart paragraph has done only half the job. The question that matters is whether the two paragraphs impose the same
obligation in substance, or whether a threshold, deadline, condition or actor has changed. Errors here are costly in both
directions: reporting a difference that is not there wastes review effort, and missing one leaves a compliance gap.

Regulatory question answering has a growing evaluation literature, notably ObliQA and the RePASs metric \cite{{gokhan2024regnlp}},
its multi-passage extension \cite{{obliqamp}} and the RIRAG-2025 shared task \cite{{gokhan2025riragtask}}. None of these tests
the cross-class \emph{{differential}} case. We ask three questions:

\textbf{{RQ1 (Applicability):}} Given a compliance question and a declared entity class, can a retrieval system return the
obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?

\textbf{{RQ2 (Differential obligation):}} For a subject issued in parallel across entity classes, can the system identify what
one entity class is required to do that another entity class is not?

\textbf{{RQ3 (Metric integrity):}} Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal
evaluation repair makes the metric resistant to concatenation/verbatim extraction?

Our contributions are: (i) a pointer-only corpus of RBI Master Directions with an entity-class $\times$ subject-family matrix;
(ii) T1, an expert-validated applicability and differential-obligation set, with its reliability evidence stated precisely;
(iii) T2 relevance sets with their construction biases; (iv) T3, a deterministic temporal set; (v) T4, an audit of RePASs on
RBI text; and (vi) an evaluation of class- and date-aware retrieval systems, including a pre-registered structured comparator
aimed at the \textit{{different}} failure. The benchmark is the contribution; the agentic pipeline is the engineering artefact we
evaluate on it.

\section{{Related Work}}\label{{sec:related}}
Gokhan et al.\ introduced ObliQA, built from financial regulations of Abu Dhabi Global Market, together with the RePASs
answer-stability score, which combines entailment, contradiction and obligation coverage \cite{{gokhan2024regnlp}}. We use the
RePASs code at a pinned commit \cite{{repass}}; its obligation classifier is fine-tuned from LEGAL-BERT \cite{{legalbert}}.
ObliQA-MP extends the setting to multi-passage answers with learning-to-rank \cite{{obliqamp}}. In the RIRAG-2025 shared task
\cite{{gokhan2025riragtask}}, the AUEB-Archimedes team showed that concatenating retrieved obligations scores highly under RePASs
\cite{{aueb2025rirag}}; RQ3 tests whether this carries over to RBI text. IndiaFinBench evaluates LLMs on Indian financial
regulatory questions \cite{{indiafinbench}}, but it does not compare obligations across entity classes. For retrieval we use
BM25 \cite{{bm25s}}, dense embeddings from the BGE family \cite{{bge}} through Sentence-BERT \cite{{sbert}}, and reciprocal rank
fusion \cite{{rrf}}.

\section{{RBI-ObliBench}}\label{{sec:bench}}
\textbf{{Corpus.}} We harvested {n(T + '.01_corpus.directions')} Master Directions ({n(T + '.01_corpus.paragraphs')} paragraphs)
with stable paragraph ids. RBI's listing uses {n(T + '.01_corpus.entity_classes')} entity-class headings:
{n(T + '.01_corpus.core_entity_classes')} regulated-entity classes and {n(T + '.01_corpus.function_headings')} function headings.
Subject families are derived from titles ({n(T + '.01_corpus.subject_families')} families). Of the
{n(T + '.01_corpus.matrix.total_cells')} class $\times$ family cells, {n(T + '.01_corpus.matrix.populated_cells')} are populated.
RBI consolidates amendments in place, so the corpus holds only current text.

\textbf{{T1 construction.}} Rule-based extraction finds obligation spans by deontic cues; over four precision rounds the final rules
keep {n(T + '.02_candidates.candidates_kept')} candidates. Each candidate is matched to counterpart paragraphs in other classes with
bge-base embeddings plus lexical similarity, and a threshold fixed on validation pairs. We drew
{n(T + '.05_t1_benchmark.sample')} items, seeded and stratified by source class, with at most four compared classes each. For each
compared class, the annotator judges \textit{{same}} (the same obligation in substance), \textit{{different}} (same topic, different
requirement) or \textit{{none}}, citing the counterpart paragraph. The item's differential flag (shared, class-specific or absent) is
derived from these judgements by guideline rule v3.6 (v3 is the guideline family for this sheet; v3.1--v3.10 are its numbered
rules). {n(T + '.05_t1_benchmark.validated')} items were validated and {n(T + '.05_t1_benchmark.rejected')}
rejected as not an obligation (Table~\ref{{tab:benchmark}}, Fig.~\ref{{fig:construction}}).

\textbf{{T2--T4.}} T2 has three relevance sets for retrieving the target-class counterpart. The first is derived from the T1 labels,
the second from the P2-002 validation pairs, and the third from a hand alignment of FAQ and press-release questions. Each favours one retriever, because
of how its candidates were shown to raters. T3 asks for the status of a paragraph on an as-of date. Its {n(T + '.08_t3.scored')}
items come from a deterministic parser of Amendment Directions and update stamps; human spot-checks gave parse precision
{x(D.wilson(T + '.08_t3.precision_v1_human'))}. T4 has {n(T + '.09_t4.n_questions')} questions, each with a genuine RAG answer and
three rule-built variants: a concatenation of the retrieved obligation sentences, a negated version of that concatenation,
and an off-topic answer of matched length drawn from an unrelated Direction. Thirty answers also carry blind human ratings of
faithfulness and of whether they answer the question. Matching was validated on {n(T + '.03_matching.overall.n')} pairs, with
counterpart rate {x(D.wilson(T + '.03_matching.overall.counterpart_rate'))}. We operationalise RQ1's compliance question as a
source obligation plus a declared target class (T2) and as per-class judgement (T1).

\input{{tables/tab_benchmark}}
\begin{{figure}}[t]\centering\includegraphics[width=\columnwidth]{{figures/fig1_benchmark_construction.png}}
\caption{{Benchmark construction: corpus, candidate extraction, cross-class matching, the T1 sample and expert labels, and T2--T4.}}\label{{fig:construction}}\end{{figure}}

\section{{Annotation and Reliability}}\label{{sec:annotation}}
The gold labels come from a single expert annotator (rater\_1), following written guidelines and using blind sheets. Of the gold
items, {n(T + '.05_t1_benchmark.route_counts.single-pass')} are single-pass,
{n(T + '.05_t1_benchmark.route_counts.retest-consistent')} were consistent across a blind retest, and
{n(T + '.05_t1_benchmark.route_counts.adjudicated')} were adjudicated by the same annotator. No gold item has an independent
second-rater label. The guidelines define each judgement operationally: \textit{{same}} means the same obligation in substance,
\textit{{different}} means the same topic with a different threshold, timeline, scope or carve-out, and \textit{{none}} covers only the
paragraphs checked, never the whole class. Spans that impose no duty on a regulated entity, such as definitions or duties on
customers, are rejected as not an obligation. A timed blind re-label of twenty single-pass items gave a flag $\kappa$ of
{kap(T + '.05_t1_benchmark.timed_relabel.differential_flag')}; it is evidence about stability, not a validation route.

Our reliability evidence is therefore indirect (Table~\ref{{tab:reliability}}, Fig.~\ref{{fig:provenance}}). On a separate sample
of thirty items drawn outside the T1 sample, three raters labelled independently before adjudication. Fleiss' $\kappa$
\cite{{fleiss1971}} is {kap(irr + '.per_class_judgement')} on class judgements and {kap(irr + '.differential_flag')} on the flag.
The annotator's blind test--retest on {n(rt + '.n_items')} items, with a gap of {gap} between passes, gives Cohen's $\kappa$
\cite{{cohen1960}} of {kap(rt + '.differential_flag')} on the flag. We treat the retest as supplementary, because recall over so short
a gap may inflate agreement. Every sheet showed the same two P2-002 candidate paragraphs per compared class, without scores; this may
bias judgements toward those candidates.

\input{{tables/tab_reliability}}
\begin{{figure}}[t]\centering\includegraphics[width=\columnwidth]{{figures/fig2_annotation_provenance.png}}
\caption{{Annotation and reliability: the single-expert gold, and the separately measured reliability evidence.}}\label{{fig:provenance}}\end{{figure}}

\section{{Systems}}\label{{sec:systems}}
Retrieval systems are BM25, dense bge-base, hybrid reciprocal rank fusion (with $k={x(D.n('RM:retrieval.rrf_k'))}$), a class-aware
hybrid restricted to the target class's Directions, and, as a diagnostic, hybrid $-$ source class: the class-blind hybrid with every
paragraph of the query's own source class removed before fusion. The class filter uses the entity-class metadata of each Direction; when the query
names a class, only that class's paragraphs (and its function-heading Directions) can be returned. A temporal filter keeps only
paragraphs in force on the as-of date, using the same amendment index that builds T3. Fig.~\ref{{fig:architecture}} shows how these
components feed the judgement step. The T1 judgement systems all use gemini-3.5-flash-lite \cite{{gemini35fl}} at temperature zero, with minimal thinking and
frozen prompts:
\begin{{itemize}}
\item a class-blind LLM and a class-aware LLM (judging retrieved evidence);
\item the final agentic system: the class filter plus an NLI verifier, which retries or abstains when a rationale is not entailed
\cite{{nlideberta,debertav3}};
\item a class-blind LLM with the verifier (class-blind + verifier);
\item a long-context system given every Direction of the compared classes, up to a 100K-token cap.
\end{{itemize}}
The baselines are the majority class, computed in-sample from the gold distribution (a reference, not a deployable system), and
the P2-002 candidate labels. Ablations A--C toggle the class filter, the temporal filter and the verifier. T4 questions and genuine answers were drafted with gpt-oss-120b
\cite{{gptoss}}.

\begin{{figure}}[t]\centering\includegraphics[width=\columnwidth]{{figures/fig3_evaluation_architecture.png}}
\caption{{Evaluation architecture: retrieval with optional class and temporal filters, LLM judgement, the NLI verifier, the
long-context alternative, and the structured comparator.}}\label{{fig:architecture}}\end{{figure}}

The pairwise structured comparator is our targeted experiment. For each item and compared class, it gives the model the source
obligation and the two shown candidate paragraphs. The model extracts thirteen fields from both sides (actor, action, object, scope,
condition, threshold, amount, percentage, frequency, deadline, exception, documentation and reporting) and marks each field equal,
different, or present on one side only. A fixed rule, not the model, then decides \textit{{same}}, \textit{{different}} or
\textit{{none}}. The prompt and rule were developed only on the separate 30-item set, with a single revision for a field-extraction
bug, and were frozen by hash before any run on T1.

\section{{Results}}\label{{sec:results}}
All confidence intervals are 95\% percentile bootstrap intervals over 2,000 item resamples \cite{{efron1979}}, and differences
are paired on the same items; proportions use Wilson intervals \cite{{wilson1927}}. Abstentions stay in the denominator: an
abstained class judgement is scored as \textit{{unsure}}, which matches no label, and an item whose flag cannot be derived is
\textit{{ambiguous}} and counts as wrong in both flag F1s. Coverage is the share of items with a derived flag. The long-context model
is scored only on the {n(P + '.t1_systems.long_context.n_items')} items it answered, and its comparisons use the same items.

\subsection{{RQ1: applicability and retrieval}}
The class filter raises nDCG@10 on \texttt{{t2\_xclass\_t1}} by {ci(T + '.06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired')}
(Table~\ref{{tab:t2}}). The gain is partly by construction, because relevance was labelled only for the target-class counterpart. It holds on all three
sets: {ci(T + '.06_t2_retrieval.p4_pipeline.t2_xclass_p2002.paired')} on \texttt{{t2\_xclass\_p2002}} and
{ci(T + '.06_t2_retrieval.p4_pipeline.t2_supp_p2003.paired')} on \texttt{{t2\_supp\_p2003}}. Removing only the source class from a
class-blind system is not enough: \texttt{{hybrid\_minus\_source\_class}} reaches
{ci(T + '.06_t2_retrieval.p3001.t2_xclass_t1.systems.hybrid_minus_source_class.ndcg')} on \texttt{{t2\_xclass\_t1}}. The
class-blind dense retriever reaches {ci(T + '.06_t2_retrieval.p3001.t2_xclass_t1.systems.dense.ndcg')} against
{ci(T + '.06_t2_retrieval.p3001.t2_xclass_t1.systems.class_aware.ndcg')} for the class-aware hybrid. On T1 the filter has no
significant effect: with the class filter and without the verifier, class-aware minus class-blind 3-way F1 is
{ci(pa + '.Class filter, no verifier: class-aware − class-blind.flag_macro_f1')}.

\input{{tables/tab_t2}}

\subsection{{RQ2: differential obligation}}
No LLM system significantly beats the P2-002 candidate labels on collapsed flag F1 (Table~\ref{{tab:t1}}). For example, class-blind
minus P2-002 is {ci(pa + '.Class-blind LLM − P2-002 candidates.collapsed_macro_f1')}, and class-aware minus P2-002 is
{ci(pa + '.Class-aware LLM − P2-002 candidates.collapsed_macro_f1')}.

The \textit{{different}} judgement is the core failure. Of {n(m + '.gold_different_units')} gold \textit{{different}} class units,
{n(m + '.A_all_five_answered.missed')} are missed by every LLM system when all five answered, and {n(m + '.B_answered_only.missed')}
when only the systems that answered are counted. Across the five systems, {reas} of {errs} \textit{{different}} errors occurred with
the gold counterpart paragraph in context. These are reasoning failures, not retrieval failures.

The errors differ in direction by system. Asked about a gold \textit{{different}} unit, the class-aware LLM answers
\textit{{same}} {n(pi + '.Class-aware LLM.same')} times and \textit{{none}} {n(pi + '.Class-aware LLM.none')} times; the long-context
model answers \textit{{same}} {n(pi + '.Long-context (100K).same')} times. Both behaviours erase the difference a compliance
reviewer needs. The P2-002 baseline cannot express \textit{{different}} at all.

The verifier lowers 3-way flag F1 by {ci(pa + '.Ablation C on T1: final agentic − class-aware.flag_macro_f1')} and coverage by
{ci(pa + '.Ablation C on T1: final agentic − class-aware.coverage')}, because it abstains on many correct first answers: the final agentic system abstained on {n(ea + '.abstained_judgements')} class
judgements, {n(ea + '.abstained_judgements_correct_before_retry')} of which were correct before the retry. The
long-context model answered {n(P + '.t1_systems.long_context.n_items')} items at the 100K cap. On those items it ties the retrieval
systems on 3-way F1 and beats the final agentic system on collapsed F1
({ci(pa + '.Long-context − final agentic (same items).collapsed_macro_f1')}).

\input{{tables/tab_t1_systems}}

{cmp_res}
\subsection{{RQ3: metric integrity, and T3}}
Concatenation gameability reproduces: concatenated minus genuine RePASs is
{ci(T + '.09_t4.paired.concatenated - genuine.composite_score')} (pre-registered verdict:
{D.get(T + '.09_t4.verdicts.concatenated')}). Negated and off-topic answers score lower than genuine ones (Table~\ref{{tab:t3t4}}).
RePASs tracks human faithfulness (Spearman $\rho$ {ci(T + '.09_t4.human.all_rated.spearman_composite_score_vs_faithful')}) but not
whether the answer addresses the question ($\rho$ {ci(T + '.09_t4.human.all_rated.spearman_composite_score_vs_answers_question')}).
An exploratory repair, combining an overlap penalty with a relevance term, ranks genuine answers first. It is not usable, however,
because it no longer tracks human faithfulness ($\rho$ {ci(T + '.09_t4.human.all_rated.spearman_repaired_vs_faithful')}).

On T3 the temporal filter yields exact match {ci(T + '.08_t3.t3.on.status_exact_match')}. This is circular, since the gold and the
filter share one parser. Without the filter the score is {ci(T + '.08_t3.t3.off.status_exact_match')}: the model answered ``in force, original'' on
{n(T + '.08_t3.t3.off.pred_status.in_force_original')} of {n(T + '.08_t3.t3.off.n')} items. T3 therefore measures whether a model uses
the dates it is given, and it shows that it does not infer amendment status unaided. Because the corpus holds only amended text,
the system can flag a later amendment but cannot show the earlier wording.

\input{{tables/tab_t3_t4_ablation}}

\section{{Discussion}}\label{{sec:discussion}}
Six findings stand out. First, class-aware filtering improves retrieval. Second, that gain does not carry over to T1 judgement:
finding the counterpart is not the hard part, and deciding what differs is. Third, \textit{{different}} is the core failure, and it is
mostly a reasoning failure. Fourth, the verifier hurts T1, because a whole-paragraph entailment premise is a poor test for a
one-sentence rationale. Abstentions are scored as errors, so the verifier's loss in F1 reflects both wrong answers and declined
correct ones (coverage {x(f"{D.get(pa + '.Ablation C on T1: final agentic − class-aware.coverage.diff'):+.3f}")}). Long-context items
that exceeded the input cap are excluded rather than penalised, and every comparison with long-context is made on the same
{n(P + '.t1_systems.long_context.n_items')} items. Fifth, a long-context model without retrieval is competitive where the relevant Directions fit in its window.
Sixth, RePASs concatenation gameability reproduces on RBI text, while negation and off-topic text do not fool it. We present these as
findings about what the benchmark exposes, not as evidence that our agent wins.

The structured comparator suggests where the difficulty lies. Asking the model to fill in the same fields for both paragraphs, and
leaving the verdict to a fixed rule, recovers part of the \textit{{different}} signal that free-form judgement misses. Its remaining
errors are mostly \textit{{different}} answered as \textit{{none}}: the model decides the two paragraphs are not about the same duty.
That points to the topic-matching step, not field extraction, as the next bottleneck. For evaluation design, the RePASs result is a
reminder that a metric built on entailment and coverage rewards copying the evidence. A faithfulness score needs a relevance
component that cannot be satisfied by verbatim text.

\section{{Limitations}}\label{{sec:limitations}}
T1 has {n(T + '.05_t1_benchmark.validated')} items, with {lo_c} to {hi_c} per source class, so per-class results are uncertain. The
gold is single-expert. Inter-rater agreement is measured on a separate sample, and the retest interval was short. Compared classes
are capped at four per item. Each T2 relevance set is biased toward one retriever. T3 is circular, and it has a known parser defect.
The corpus lacks pre-amendment text. T4 is small, with LLM-drafted questions and one rater. All LLM results come from a
Flash-Lite-class model on free tiers. The RePASs repair is exploratory and was designed and tested on the same thirty questions. Following our scope plan, we did not run
reranking, IndiaFinBench transfer or an ObliQA baseline. A public inspection interface accompanies the release; it reads the sealed outputs and does not affect any reported result. Finally, the comparator saw only the two shown
candidate paragraphs per class, the same ones the annotator saw; a comparator over retrieved evidence might behave differently.

\section{{Future Work}}\label{{sec:future}}
In order of priority: a test--retest with a proper gap; independent second raters on every gold item; cross-encoder reranking;
a run with a stronger (frontier) LLM; an ObliQA baseline; a broader T3; a larger T4 study with two raters; IndiaFinBench transfer;
a LangGraph port of the pipeline; and full use of the FAQ and enforcement sources.

\section{{Conclusion}}\label{{sec:conclusion}}
RBI-ObliBench isolates a case that generic regulatory QA does not test: an obligation whose counterpart exists in another entity
class but says something different. Every system we evaluated, from embedding matching to long-context reading, is weak on this
case, even with the counterpart in context. Data and code are released as pointers: \placeholder{{Zenodo DOI}}.

\section*{{Acknowledgment}}
\textbf{{AI use.}} Claude Code (Anthropic) wrote the repository code and analysis scripts under the authors' direction, and drafted
internal reports. Claude Code also wrote the inspection interface and its build scripts under the authors' direction. gemini-3.5-flash-lite and gpt-oss-120b are systems under study; their outputs are never labels. All human labels
are manual. Under the Gemini API free tier, outputs may be published and were not used to train any model, and free-tier inputs may
be used by Google; our prompts contained only public RBI text and no personal data.

\bibliographystyle{{IEEEtran}}
\bibliography{{refs_verified}}

\end{{document}}
"""


def page_estimate(tex: str) -> dict:
    body = re.sub(r"(?s)\\begin\{(table\*?|figure\*?)\}.*?\\end\{\1\}", " ", tex)
    body = re.sub(r"\\input\{[^}]+\}", " ", body)
    body = re.sub(r"%.*", "", body)
    body = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", body)
    words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-']*", body))
    floats = {"tab_benchmark": 0.12, "fig1 (column)": 0.17, "tab_reliability (wide)": 0.12, "fig2 (column)": 0.15, "tab_t2 (wide)": 0.15,
              "tab_t1 (wide)": 0.25, "fig3 (column)": 0.2, "tab_comparator": 0.13, "tab_t3t4": 0.25, "references": 0.55, "title/authors": 0.25}
    pages = words / 880 + sum(floats.values())
    return {"words": words, "float_pages": round(sum(floats.values()), 2), "estimated_pages": round(pages, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--docx", action="store_true")
    a = ap.parse_args()
    tex = build()
    (PAPER / "main.tex").write_text(tex, encoding="utf-8")
    est = page_estimate(tex)
    print(f"main.tex written; {est}")
    if a.zip:
        z = PAPER / "RBI-ObliBench_AISIGH_overleaf.zip"
        figs = ["fig1_benchmark_construction.png", "fig2_annotation_provenance.png", "fig3_evaluation_architecture.png"]
        for f in figs:
            (PAPER / "figures" / f).write_bytes((ROOT / "reports/private/final_push/figures" / f).read_bytes())
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zz:
            zz.write(PAPER / "main.tex", "main.tex")
            zz.write(PAPER / "refs_verified.bib", "refs_verified.bib")
            for t in sorted((PAPER / "tables").glob("*.tex")):
                zz.write(t, f"tables/{t.name}")
            for f in figs:
                zz.write(PAPER / "figures" / f, f"figures/{f}")
        print(f"zip: {z.relative_to(ROOT)} ({len(zipfile.ZipFile(z).namelist())} files)")
    if a.docx:
        out = PAPER / "RBI-ObliBench_paper_draft.docx"
        subprocess.run(["pandoc", "main.tex", "--from", "latex", "--to", "docx", "--citeproc", "--bibliography", "refs_verified.bib",
                        "-o", str(out)], cwd=PAPER, check=True)
        print(f"docx: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
