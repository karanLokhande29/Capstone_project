"""Builds the MPSTME capstone project report (.docx) for RBI-ObliBench.

    python build/build_report.py            # from capstone_submission/

Numbers are copied from reports/final/RBI-ObliBench_Master_Document_v2.md (results_v2.json); student and mentor
details come from build/details.json.
"""

import json
import re
import sys
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

sys.path.insert(0, str(Path(__file__).parent))
from docx_kit import Report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
D = json.loads((ROOT / "build" / "details.json").read_text())
C, L = WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT

TITLE = D["title"]
SHORT = D["title_short"]
STUDENTS = D["students"]

from references import REFS  # noqa: E402

R = Report(SHORT, D["academic_year"])
doc = R.doc

# =====================================================================================================================
# Title page (no header or footer)
# =====================================================================================================================
R.center(f"**{TITLE}**", size=18, space_after=20)
R.center("Project Report submitted in the partial fulfilment", space_after=0)
R.center("of the degree of", space_after=12)
R.center(f"**{D['program']}**", size=14, space_after=0)
R.center("in", space_after=0)
R.center(f"**{D['stream']}**", size=14, space_after=18)
R.center("by", space_after=10)
for s in STUDENTS:
    R.center(f"**{s['name']} ({s['roll']})**", space_after=0)
R.blank(1)
R.center("Under the supervision of", space_after=2)
R.center(f"**{D['mentor']}**", space_after=0)
R.center(f"({D['mentor_designation']}, {D['department']}, MPSTME)", size=11, space_after=20)
R.center("**SVKM's NMIMS University**", size=16, space_after=0)
R.center("(Deemed-to-be University)", size=10, space_after=6)
lp = doc.add_paragraph()
lp.alignment = C
lp.add_run().add_picture(str(FIG / "nmims_logo.jpeg"), width=Inches(1.4))
R.center("**MUKESH PATEL SCHOOL OF TECHNOLOGY**", size=15, space_after=0)
R.center("**MANAGEMENT & ENGINEERING (MPSTME)**", size=15, space_after=0)
R.center("**Vile Parle (W), Mumbai-56**", size=13, space_after=0)
R.center(f"**({D['academic_year']})**", size=13, space_after=0)

# =====================================================================================================================
# Certificate
# =====================================================================================================================
R.page_break()
SCANS = ROOT / "scans"
signed_certificate = sorted(SCANS.glob("certificate_signed_p*.jpg"))
if signed_certificate:  # the signed scan replaces the generated certificate
    lp = doc.add_paragraph()
    lp.alignment = C
    lp.add_run().add_picture(str(signed_certificate[0]), width=Inches(5.77))
else:
    lp = doc.add_paragraph()
    lp.alignment = C
    lp.add_run().add_picture(str(FIG / "nmims_logo.jpeg"), width=Inches(1.3))
    R.center("**SVKM's NMIMS (Deemed-to-be University)**", size=13, space_after=0)
    R.center("**Mukesh Patel School of Technology Management & Engineering**", size=13, space_after=0)
    R.center("Vile Parle (W), Mumbai-56", size=12, space_after=0)
    R.center(f"({D['academic_year']})", size=12, space_after=18)
    R.center("**CERTIFICATE**", size=18, space_after=18, underline=True)
    by = ", ".join(f"{s['name']} (Roll No. {s['roll']})" for s in STUDENTS[:-1]) + \
         f" and {STUDENTS[-1]['name']} (Roll No. {STUDENTS[-1]['roll']})"
    R.p(f"This is to certify that the project entitled **“{TITLE}”** has been done by {by} under my guidance "
        f"and supervision, and has been submitted in partial fulfilment of the degree of {D['program']} in "
        f"{D['stream']} of MPSTME, SVKM's NMIMS (Deemed-to-be University), Mumbai, India.")
    R.blank(2)
    R.borderless_table([
        [("_____________________________", L), ("_____________________________", L)],
        [(f"**{D['mentor']}**", L), ("**Examiner**", L)],
        [("Project Mentor (Internal Guide)", L), ("(Name and Signature)", L)],
        [("(Name and Signature)", L), ("", L)],
    ], [3.0, 2.8])
    R.blank(1)
    R.p("**Date:**", align=L, space_after=0)
    R.p("**Place:** Mumbai", align=L, space_after=0)
    R.blank(1)
    R.borderless_table([
        [("", L), ("_____________________________", L)],
        [("", L), (f"**{D['hod']}**", L)],
        [("", L), ("Head of Department (HoD)", L)],
        [("", L), ("(Name and Signature)", L)],
    ], [3.0, 2.8])

# =====================================================================================================================
# Front matter (roman page numbers)
# =====================================================================================================================
R.new_section(page_format="lowerRoman", start=1)
R.center("**ACKNOWLEDGEMENT**", size=18, space_after=18)
R.p(f"We are grateful to our project mentor, **{D['mentor']}**, who reviewed our work every week and guided the "
    "project from topic selection to this report. Her feedback at each review shaped our research questions, the "
    "annotation protocol and the care we took in reporting the evaluation.")
R.p(f"We thank **{D['co_author_faculty']}** for support throughout the project and for contributing to the research "
    "paper that grew out of it. We also thank the Head of the Department, "
    f"**{D['hod']}**, and the members of the review panels, whose comments at the topic-approval and mid-term reviews "
    "improved both the scope and the methodology of the project.")
R.p('Our thanks also go to the Dean and faculty of Mukesh Patel School of Technology Management & Engineering, '
    "SVKM's NMIMS, for the facilities and support we relied on throughout. The corpus exists because the Reserve "
    'Bank of India publishes its Master Directions openly, and the project builds on open-source tools and models '
    'whose authors we gratefully acknowledge.')
R.p("Finally, we thank our families and friends for their patience and support.")
R.blank(1)
R.p("**Student Names**", align=L)
R.table("Project team", ["NAME", "ROLL NO.", "SAP ID", "SIGNATURE"],
        [[s["name"], s["roll"], s["sap"], ""] for s in STUDENTS], [2.1, 1.2, 1.4, 1.2], font=11,
        label_prefix="0.1")
# The front-matter team table is not a numbered report table: drop its caption.
caption = [p for p in doc.paragraphs if p.text.startswith("Table 0.1")][0]
caption._p.getparent().remove(caption._p)

R.front_title("ABSTRACT")
R.p("The Reserve Bank of India (RBI) regulates commercial banks, small finance banks, co-operative banks, "
    "non-banking financial companies and several other classes of institution through separate Master Directions. As "
    "a result, the same duty, such as a Board-approved policy or a reporting requirement, often appears in the "
    "Directions of several entity classes, sometimes with a different threshold, deadline, scope or approving "
    "authority. Compliance officers need to know both which obligations bind their class and where the parallel "
    "Directions differ, yet existing regulatory question-answering benchmarks do not test this cross-class "
    "differential case.")
R.p("We present **RBI-ObliBench**, a benchmark built on all 381 RBI Master Directions (76,188 paragraphs). It defines "
    "four tasks: entity-class applicability and differential obligation (T1, with 106 expert-validated items and 412 "
    "class judgements), cross-class counterpart retrieval (T2), the temporal status of a paragraph on an as-of date "
    "(T3), and an audit of the RePASs answer-faithfulness metric (T4). Around the benchmark we built a class- and "
    "date-aware retrieval-augmented generation (RAG) pipeline, a pairwise structured comparator, an interactive "
    "inspection website and a local compliance audit generator.")
R.p('Filtering by entity class raises counterpart retrieval nDCG@10 by +0.451 [+0.421, +0.481]. Yet no '
    'large-language-model system beats an embedding-matching baseline on collapsed T1 flag F1, and 56 of the 78 '
    'gold ‘different’ judgements are missed by every LLM system, usually with the correct counterpart already in '
    'context. A structured comparator, frozen before any test run, extracts thirteen fields from both paragraphs '
    'and leaves the verdict to a fixed rule; it raises ‘different’ F1 to 0.409, a gain of +0.255 [+0.094, +0.411] '
    'over the class-aware LLM. An NLI verifier lowers T1 F1, a long-context model is competitive with retrieval, '
    'and RePASs rewards verbatim concatenation of the evidence on RBI text (+0.375 over genuine answers). Every '
    'result is reported with a 95% bootstrap confidence interval, and the released data holds pointers rather '
    'than RBI text. A paper based on this work has been submitted to AISIGH-SD 2026 (IEEE).')
R.p("**Keywords:** regulatory NLP, retrieval-augmented generation, benchmark, differential obligations, Reserve Bank of "
    "India, evaluation metrics, compliance.", align=L)

R.front_title("Table of Contents")
R.toc('TOC \\o "1-3" \\h \\z \\u',
      "Right-click here and choose Update Field (or press F9) to build the table of contents.")

R.chapter_heading("List of Figures", numbered=False)
R.toc('TOC \\h \\z \\t "Figure Caption,1"', "Right-click here and choose Update Field to build the list of figures.")
R.chapter_heading("List of Tables", numbered=False)
R.toc('TOC \\h \\z \\t "Table Caption,1"', "Right-click here and choose Update Field to build the list of tables.")

R.chapter_heading("Abbreviations", numbered=False)
ABBR = [
    ("AML", "Anti-Money Laundering"), ("API", "Application Programming Interface"),
    ("BM25", "Best Matching 25 (probabilistic lexical ranking function)"),
    ("bge", "BAAI General Embedding (bge-base-en-v1.5 dense encoder)"), ("CI", "Confidence Interval"),
    ("CMT", "Microsoft Conference Management Toolkit"), ("DOCX", "Office Open XML word-processing document"),
    ("F1", "Harmonic mean of precision and recall"), ("FAQ", "Frequently Asked Questions"),
    ("ICS", "iCalendar file format (RFC 5545)"), ("IEEE", "Institute of Electrical and Electronics Engineers"),
    ("IR", "Information Retrieval"), ("JSON", "JavaScript Object Notation"), ("KYC", "Know Your Customer"),
    ("LLM", "Large Language Model"), ("MD", "Master Direction (RBI)"),
    ("NBFC", "Non-Banking Financial Company"), ("nDCG", "normalised Discounted Cumulative Gain"),
    ("NLI", "Natural Language Inference"), ("NLP", "Natural Language Processing"),
    ("ObliQA", "Obligation Question Answering dataset (ADGM regulations)"),
    ("RAG", "Retrieval-Augmented Generation"), ("RBI", "Reserve Bank of India"),
    ("RePASs", "Regulatory Passage Answer Stability score"), ("RQ", "Research Question"),
    ("RRF", "Reciprocal Rank Fusion"), ("SFB", "Small Finance Bank"), ("T1-T4", "Benchmark tasks 1 to 4"),
    ("UCB", "Urban Co-operative Bank"), ("UI", "User Interface"),
    ("κ (kappa)", "Cohen's or Fleiss' chance-corrected agreement coefficient"),
]
R.table("List of abbreviations", ["Abbreviation", "Full form"], ABBR, [1.4, 4.4], font=10.5,
        label_prefix="0.2")
caption = [p for p in doc.paragraphs if p.text.startswith("Table 0.2")][0]
caption._p.getparent().remove(caption._p)

# =====================================================================================================================
# Chapters (decimal page numbers from 1)
# =====================================================================================================================
R.new_section(page_format="decimal", start=1)

# ------------------------------------------------------------------------------------------------ Chapter 1
R.chapter_heading("Introduction", new_page=False)
R.p('Chapter 1 introduces the problem of parallel RBI obligations that do not quite match, explains why it '
    'matters, states the research questions and lists what the project delivered.')
R.h2("1.1 Background of the project topic")
R.p("The Reserve Bank of India (RBI) regulates most of India's banks and non-bank lenders [@rbi]. Its binding "
    'rules are issued as Master Directions, each on one subject (for instance KYC or priority-sector lending) and '
    'each addressed to particular classes of regulated entity: commercial banks, small finance banks, payments '
    'banks, urban and rural co-operative banks, NBFCs, all-India financial institutions, asset reconstruction '
    'companies and others. Amendments are written into the consolidated text, which is then marked “Updated as '
    'on” a date.')
R.p('So one subject can appear in several near-parallel Directions. A Board-approved outsourcing policy, for '
    'example, is required of several classes, but the scope, the approving body or the reporting line may change '
    'between them. Table 1.1 lists the kinds of difference we look for. Groups owning both a bank and an NBFC, '
    'auditors covering several classes and RegTech vendors all have to catch them.')
R.table('Ways in which parallel obligations can differ', ['Dimension', 'What changes between classes'], [
    ['Threshold or amount', 'A monetary or numeric limit is set differently'],
    ['Deadline or frequency', 'A reporting period or due date is shorter or longer'],
    ['Approving body or actor', 'A different body must approve or carry out the duty'],
    ['Scope or carve-out', 'The duty covers less, or one class is exempted'],
], [2.0, 3.8], font=10)
R.p('NLP for legal text has grown with pre-trained transformers [@vaswani2017, @devlin2019bert, @legalbert] and '
    'benchmarks such as LexGLUE [@chalkidis2022lexglue]. Regulatory question answering mostly uses '
    'retrieval-augmented generation (RAG), in which a large language model (LLM) answers from retrieved passages '
    '[@lewis2020rag], and it has its own dataset and metric in ObliQA and RePASs [@gokhan2024regnlp, @repass].')
R.h2("1.2 Motivation and scope of the report")
R.p('Both kinds of error cost something: a false difference wastes review time, and a missed one can leave an '
    'entity non-compliant and exposed to supervisory action or penalties. Existing regulatory QA benchmarks test '
    "faithfulness to the retrieved passage only; whether the passage suits the asker's class, or whether two "
    'parallel passages agree, goes unchecked.')
R.p('We see the benchmark and its evaluation as the contribution and the class- and date-aware RAG pipeline as '
    'the thing under test. The project covers the 381 Master Directions listed at harvest time, eleven '
    'regulated-entity classes and English text; it leaves out unconsolidated circulars and gives no legal advice. '
    'It also produced a public results website and a local compliance audit generator.')
R.h2("1.3 Problem statement")
R.p("For an obligation in one entity class's Master Direction, the task is to decide for each other class whether "
    'a counterpart exists and whether it imposes the same or a different requirement, to retrieve that '
    'counterpart, to determine whether a paragraph is in force on a given date, and to test whether the usual '
    'faithfulness metric for regulatory answers can be gamed on Indian regulatory text.')
R.p("Three research questions follow from this problem:")
R.bullets([
    "**RQ1 (Applicability):** Given a compliance question and a declared entity class, can a retrieval system return "
    "the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a "
    "class-aware system?",
    "**RQ2 (Differential obligation):** For a subject issued in parallel across entity classes, can the system "
    "identify what one entity class is required to do that another entity class is not?",
    "**RQ3 (Metric integrity):** Does the documented gameability of RePASs reproduce on Indian regulatory text, and "
    "what minimal evaluation repair makes the metric resistant to concatenation or verbatim extraction?",
])
R.p('We use research questions rather than objectives because the project is an evaluation and Chapter 4 answers '
    'each question with measurements; the objectives on the topic approval form (Annexure I) describe the work '
    'done to reach those answers.')
R.h2("1.4 Salient contribution")
R.p('Table 1.2 lists the contributions.')
R.table('Contributions of the project', ['Contribution', 'Description'], [
    ['Corpus', 'All 381 RBI Master Directions, 76,188 paragraphs with stable ids, released as pointers, with an entity class × subject family matrix'],
    ['T1', '106 expert-validated items and 412 class judgements on applicability and differential obligations, with their reliability evidence'],
    ['T2', 'Three counterpart-retrieval relevance sets, each with its construction bias stated'],
    ['T3 and T4', 'Temporal status from Amendment Directions; an audit of RePASs on RBI text'],
    ['Evaluation', 'Retrieval and judgement systems with and without class and date filters, paired bootstrap intervals, and a pre-registered structured comparator for the ‘different’ failure'],
    ['Applications', 'A public inspection website with a live comparator API; a local compliance audit generator whose AI assistant must cite RBI text'],
    ['Paper', 'Submitted to AISIGH-SD 2026, an IEEE-sponsored conference'],
], [1.3, 4.5], font=10)
R.h2("1.5 Organization of report")
R.p('The rest of the report follows Table 1.3.')
R.table('Organisation of the report', ['Part', 'Content'], [
    ['Chapter 2', 'Earlier work on legal NLP, retrieval, RAG evaluation and AI ethics; the research gap'],
    ['Chapter 3', 'Design and implementation: corpus, benchmark, annotation, systems, comparator, scoring, applications, standards'],
    ['Chapter 4', 'Results for RQ1, RQ2 and RQ3, and additional experiments'],
    ['Chapter 5', 'Advantages, limitations and applications'],
    ['Chapter 6', 'Conclusions and future work'],
    ['Appendices A to D', 'Algorithms, data sheets, software component list, research paper'],
    ['Annexures I to III', 'Topic approval form, weekly log book, proof of paper submission'],
], [1.6, 4.2], font=10)
R.p('**Summary:** Parallel RBI Directions sometimes differ, and RBI-ObliBench tests whether systems notice. RQ1 '
    'to RQ3 frame the study.')

# ------------------------------------------------------------------------------------------------ Chapter 2
R.chapter_heading("Literature Survey")
R.p('Background comes first (Section 2.1), then the closest studies (Section 2.2), a comparison (Section 2.3) and '
    'the research gap (Section 2.4).')
R.h2("2.1 Introduction to the overall topic")
R.p("**Language models for legal and regulatory text.** The transformer [@vaswani2017] and BERT's bidirectional "
    "pre-training [@devlin2019bert] reset the baseline for most NLP tasks, and domain adaptation soon followed. "
    "LEGAL-BERT, pre-trained on legislation, court cases and contracts, improved legal classification over general "
    "BERT [@legalbert], and LexGLUE gathered seven English legal-understanding tasks into one benchmark, on which "
    "legal-domain models led but still left substantial headroom [@chalkidis2022lexglue]. Regulatory text has "
    "difficulties of its own: deontic language (“shall”, “must”, “is required to”), long nested "
    "clauses, defined terms and cross-references. The deontic cues matter directly here, because our candidate "
    "extractor relies on them (Section 3.4).")
R.p("**Lexical and dense retrieval.** BM25, derived from the probabilistic relevance framework, remains a strong "
    "passage-retrieval baseline [@robertson2009bm25], and we use the BM25S implementation for speed [@bm25s]. Dense "
    "retrieval instead encodes queries and passages with neural encoders. Dense Passage Retrieval showed that a dual "
    "encoder can beat BM25 on open-domain QA [@karpukhin2020dpr], Sentence-BERT made sentence embeddings cheap to "
    "compute [@sbert], and the BGE family from C-Pack offers strong general-purpose English embeddings [@bge]. "
    "Reciprocal rank fusion merges ranked lists without calibrating their scores and often outperforms each input "
    "[@rrf], while a BERT cross-encoder can re-score a short candidate list jointly with the query "
    "[@nogueira2019passage]. Graded measures such as nDCG are the standard way to evaluate the resulting rankings "
    "[@jarvelin2002ndcg].")
R.p("**Retrieval-augmented generation and its evaluation.** RAG conditions a generator on retrieved passages "
    "[@lewis2020rag], so its evaluation has to separate the quality of retrieval from the quality of the answer. "
    "Reference-free frameworks such as RAGAS use LLM judges to score faithfulness and answer relevance [@es2024ragas]. "
    "Faithfulness checks frequently rest on natural language inference (NLI) models trained on SNLI and MultiNLI "
    "[@bowman2015snli, @williams2018mnli], including DeBERTa-v3 cross-encoders [@debertav3, @nlideberta]. Long-context "
    "models are an alternative to retrieval, but they use information in the middle of a long input less reliably "
    "than information at its start or end [@liu2024lost]. Open and hosted models such as gpt-oss-120b [@gptoss] and "
    "Gemini 3.5 Flash-Lite [@gemini35fl] have made such systems inexpensive to run.")
R.p("**Annotation and statistical evaluation.** A benchmark's labels are only as useful as the evidence for their "
    "reliability. Cohen's κ measures chance-corrected agreement between two raters [@cohen1960], Fleiss' κ "
    "generalises it to several raters [@fleiss1971], and Landis and Koch's scale is the usual guide to interpreting "
    "the values [@landis1977]. Wilson's score interval gives dependable confidence intervals for proportions "
    "[@wilson1927], and the bootstrap provides intervals for statistics such as F1 and nDCG that have no simple "
    "closed form [@efron1979]. Datasheets for datasets recommend recording a dataset's motivation, composition, "
    "collection process and intended use [@gebru2021datasheets]; Appendix B follows that practice.")
R.p('**Ethics of AI in regulated domains.** A review of 84 AI ethics guidelines found that they converge on a '
    'small set of principles: transparency, justice and fairness, non-maleficence, responsibility and privacy '
    '[@jobin2019]. Floridi and Cowls unify such principles into five (beneficence, non-maleficence, autonomy, '
    "justice and explicability) [@floridi2019], and IEEE's Ethically Aligned Design translates them into "
    'recommendations for engineers, closely linked to the IEEE 7000 series of standards [@ead2019]. For language '
    'models in particular, Bender et al. warn that fluent output can be mistaken for understanding and that large '
    'models absorb the biases of their training data [@bender2021]; model cards and datasheets respond by '
    "documenting a model's or dataset's intended use and limitations [@mitchell2019, @gebru2021datasheets]. In "
    "the Indian financial sector, the RBI's FREE-AI committee report sets out seven guiding principles for the "
    'responsible adoption of AI by regulated entities, among them fairness, accountability and explainability '
    '[@freeai2025]. Section 3.11.2 shows how we applied them.')
R.h2("2.2 Survey of closely related work")
R.p('**Gokhan et al. (2024), RIRAG and ObliQA** [@gokhan2024regnlp]. This paper set up the retrieve-then-answer '
    'task that we also use. Its dataset, ObliQA, has 27,869 questions on the financial regulations of the Abu '
    'Dhabi Global Market, and its metric, RePASs, scores an answer without a reference by combining entailment, '
    'contradiction and obligation coverage from an NLI model and an obligation classifier. Every ObliQA question '
    "sits inside one regulator's rulebook with one regulatory context, which is exactly the boundary our T1 and "
    'T2 cross.')
R.p('**RegNLP, RePASs implementation** [@repass]. RePASs is computed by an NLI cross-encoder plus an obligation '
    'classifier fine-tuned from LEGAL-BERT [@legalbert]. We ran the released code unchanged at a pinned commit, '
    'so our T4 audit can be reproduced.')
R.p("**Gokhan et al. (2025), RIRAG-2025 shared task** [@gokhan2025riragtask]. The shared task at the first Regulatory "
    "NLP workshop evaluated retrieval and generation systems from several teams on ObliQA, with RePASs as the "
    "official answer metric. For this project its main consequence is that RePASs became the reference metric for "
    "regulatory RAG, which is why its robustness is worth testing.")
R.p("**Chasandras et al. (2025), AUEB-Archimedes at RIRAG-2025** [@aueb2025rirag]. This team found that concatenating "
    "the obligation sentences of the retrieved passages, with no generation step, already scores highly under "
    "RePASs. The finding exposes a structural weakness of a metric built on entailment and coverage: copying the "
    "evidence is rewarded. It was shown on ObliQA only, so our RQ3 asks whether it reproduces on RBI text.")
R.p("**Gokhan and Briscoe (2025), ObliQA-MP** [@obliqamp]. ObliQA-MP extends ObliQA to answers grounded in several "
    "passages and applies learning-to-rank to regulatory RAG. Multi-passage answers are closer to real compliance "
    "questions, which often draw on more than one provision; the passages, however, still come from a single "
    "rulebook.")
R.p("**Pall (2026), IndiaFinBench** [@indiafinbench]. IndiaFinBench evaluates LLMs on 406 expert-annotated questions "
    "over SEBI and RBI text, covering regulatory interpretation, numerical reasoning, contradiction and temporal "
    "questions. It is the Indian benchmark closest to ours. Its questions test the understanding of individual "
    "documents, so it complements a cross-document task such as T1, and we use it as an external check in Section 4.9.")
R.p("**Xiao et al. (2024), C-Pack and BGE embeddings** [@bge]. C-Pack released the BGE models and their training "
    "recipe; we use bge-base-en-v1.5 both for cross-class matching and as the dense retriever. General-purpose "
    "embeddings are good at finding paragraphs on the same topic. T1 asks a harder question of them: whether they can "
    "separate “same topic, same rule” from “same topic, different rule”.")
R.p("**Cormack et al. (2009), reciprocal rank fusion** [@rrf]. RRF scores each document by summing 1/(k + rank) over "
    "the input rankings. It needs no training and is robust, which is why our hybrid retriever uses it as the fusion "
    "step (k = 60).")
R.p("**Karpukhin et al. (2020), Dense Passage Retrieval** [@karpukhin2020dpr] and **Lewis et al. (2020), RAG** "
    "[@lewis2020rag]. DPR established dual-encoder retrieval as a serious alternative to BM25, and RAG established the "
    "retrieve-then-generate design. Both treat relevance as a property of the query and the passage alone. In "
    "regulation, relevance also depends on who is asking: the correct paragraph for a small finance bank may be the "
    "wrong one for an NBFC. Our class-aware retriever supplies this missing condition through metadata filtering.")
R.p("**Es et al. (2024), RAGAS** [@es2024ragas]. RAGAS defines reference-free metrics for faithfulness, answer "
    "relevance and context relevance. Keeping faithfulness and relevance apart turns out to matter for our T4 result, "
    "in which RePASs tracks human faithfulness ratings but not whether an answer addresses the question.")
R.p("**Liu et al. (2024), Lost in the Middle** [@liu2024lost]. Long-context models use information at the beginning "
    "and end of their input better than information in the middle. This motivated our long-context baseline, which "
    "reads every Direction of the compared classes up to a 100K-token cap, as a direct test of whether retrieval is "
    "needed at all.")
R.p("**Chalkidis et al. (2020, 2022), LEGAL-BERT and LexGLUE** [@legalbert, @chalkidis2022lexglue]. These studies "
    "show that legal language benefits from domain-specific models and that legal-understanding benchmarks remain "
    "difficult. Their tasks centre on court decisions and contracts; the obligations that a regulator places on "
    "supervised entities are not their focus.")
R.h2("2.3 Comparison of the surveyed work")
R.p("Table 2.1 places the surveyed work along the two dimensions that matter most for this project: whether it "
    "compares obligations across entity classes, and whether it examines the answer metric itself.")
R.table("Comparison of related benchmarks and methods with this project", [
    "Work", "Domain / data", "Task", "Cross-class comparison", "Metric audit"], [
    ["ObliQA, RIRAG [@gokhan2024regnlp]", "ADGM financial regulations", "Passage retrieval + answer generation",
     "No", "Introduces RePASs"],
    ["RIRAG-2025 [@gokhan2025riragtask]", "ADGM (ObliQA)", "Shared task on regulatory RAG", "No",
     "Uses RePASs"],
    ["AUEB-Archimedes [@aueb2025rirag]", "ADGM (ObliQA)", "RAG system", "No",
     "Shows concatenation games RePASs"],
    ["ObliQA-MP [@obliqamp]", "ADGM", "Multi-passage answers, learning-to-rank", "No", "No"],
    ["IndiaFinBench [@indiafinbench]", "SEBI and RBI text", "LLM QA, 4 question types", "No", "No"],
    ["LexGLUE [@chalkidis2022lexglue]", "EU/US legal text", "Legal classification", "No", "No"],
    ["RAGAS [@es2024ragas]", "General", "RAG evaluation framework", "No", "Reference-free metrics"],
    ["**RBI-ObliBench (this work)**", "381 RBI Master Directions", "Applicability, differential, retrieval, "
     "temporal", "**Yes (T1, T2)**", "**Audits RePASs (T4)**"],
], [1.6, 1.15, 1.35, 0.85, 0.95], font=9.5)
R.h2("2.4 Research gap and problem definition")
R.p("Taken together, the surveyed work leaves three questions open. First, regulatory QA datasets treat a regulation "
    "as one rulebook, so none of them tests whether a system can recognise that an obligation in one entity class "
    "has a counterpart in another class that says something different. Second, regulatory retrieval is evaluated "
    "without the asker's entity class, even though the correct paragraph depends on it. Third, the concatenation "
    "weakness of RePASs has been shown only on ObliQA, and whether it carries over to Indian regulatory text is "
    "unknown. These three gaps correspond, in order, to RQ2, RQ1 and RQ3 in Section 1.3.")
R.p('**Summary:** There is plenty of good work on retrieval and RAG for regulatory text, and ObliQA with RePASs '
    'has become the usual way to evaluate it. What we could not find was a test of differences between entity '
    "classes, retrieval that takes the asker's class into account, or an independent check of RePASs. "
    'RBI-ObliBench was designed to cover those three things.')

# ------------------------------------------------------------------------------------------------ Chapter 3
R.chapter_heading("Methodology and Implementation")
R.p('We describe the system roughly in the order it was built: corpus, extraction, matching and labelling, the '
    'systems under test, the comparator and scoring, and then the applications, standards and use of AI tools.')
R.h2("3.1 Block diagram")
R.p('Fig. 3.1 has three rows. Row one collects the data: download the Master Directions, convert them to text, '
    'split them into paragraphs with fixed ids, and tag each paragraph with its entity class and subject family. '
    'Row two builds the benchmark: extract obligation candidates, match them across classes, have an expert label '
    'them, and add FAQs, enforcement releases and Amendment Directions for the temporal and retrieval sets. Row '
    'three runs the systems and produces the paper, the data release and the applications.')
R.p('Phase 1 was divided among the three of us. Akash Goyal collected the corpus, extracted the text and '
    'segmented it into paragraphs. Karan Lokhande normalised the metadata and built the entity class × subject '
    'family matrix. Meer Magia ran the corpus quality checks, wrote the annotation protocol and organised the '
    'three-rater pilot.')
R.figure(FIG / "block_overall.png", "Overall block diagram of RBI-ObliBench, from corpus harvest to evaluation and "
         "applications", width=6.0)
R.p("Fig. 3.2, taken from the research paper, shows the benchmark-construction steps in more detail.")
R.figure(FIG / "fig1_benchmark_construction.png", "Benchmark construction: corpus, candidate extraction, cross-class "
         "matching, the T1 sample and expert labels, and T2 to T4", width=6.0)
R.h2("3.2 Hardware and software description")
R.p('No special hardware was needed. All development and CPU work ran on an Apple-silicon (arm64) laptop with '
    'macOS. The cross-class embeddings were computed on Kaggle Notebooks, where the code reads from the Kaggle '
    'inputs and writes only to the Kaggle working directory. LLM calls used the free tiers of the Google Gemini '
    'API and Groq. The demo website is an Azure Storage static website and its comparator API an Azure Function; '
    "the audit generator, in contrast, runs entirely on the user's machine with a local Ollama model. Tables 3.1 "
    'and 3.2 list the platforms and software versions.')
R.table("Hardware and computing platforms", ["Item", "Used for"], [
    ["Apple-silicon (arm64) laptop, macOS", "Development, corpus processing, retrieval, NLI, evaluation, tests"],
    ["Kaggle Notebooks", "Corpus harvest notebook and bge-base embedding of 28,694 candidates"],
    ["Google Gemini API (free tier)", "gemini-3.5-flash-lite for every T1 system and the comparator"],
    ["Groq API (free tier)", "gpt-oss-120b for T4 question drafting and an additional T1 run"],
    ["Microsoft Azure", "Static website (demo) and Azure Function (live comparator API)"],
    ["Local Ollama runtime", "On-device model for the audit generator's AI assistant"],
], [2.4, 3.4])
R.table("Main software stack", ["Layer", "Software (version)"], [
    ["Language and tests", "Python 3.14.3, pytest 9.1.1; TypeScript 5.9 with Vitest for the UI"],
    ["Harvest and parsing", "requests 2.33, BeautifulSoup 4.14, lxml 6.1, pdfplumber 0.11"],
    ["Data and statistics", "NumPy 2.4, pandas 3.0, SciPy 1.17, scikit-learn 1.6"],
    ["Retrieval", "bm25s 0.3.11; sentence-transformers 6.1 with bge-base-en-v1.5; RRF (k = 60)"],
    ["Models", "PyTorch 2.11, transformers 5.4; cross-encoder/nli-deberta-v3-xsmall (NLI verifier)"],
    ["Metric audit", "RePASs at a pinned commit, in a separate environment"],
    ["Backend", "FastAPI 0.135, uvicorn 0.44, pydantic 2.13 (audit generator, loopback only)"],
    ["Front end", "React 19, Vite 7, Tailwind CSS 4, Recharts, React Flow; Hono for the comparator API"],
], [1.7, 4.1])
R.h2("3.3 Corpus construction")
R.p("Our scraper downloaded all 381 Directions from the RBI's Master Directions listing; their PDFs were "
    'converted to text and split into 76,188 paragraphs, each carrying a stable id (md_NNNNN::pNNNNN) and a '
    'clause path. The first harvest had missed 81 Directions, and for a while our Kaggle notebook was silently '
    're-running stale code. Once the notebook was fixed, the P1-004 repair phase used retries, a manual import '
    'route and consistency checks to recover the missing Directions, so all later work rests on the full 381. '
    'FAQs, enforcement releases and Amendment Directions were also harvested for validation. Table 3.3 gives the '
    'main corpus statistics.')
R.table('Corpus statistics', ['Item', 'Value'], [
    ['Master Directions', '381'],
    ['Paragraphs', '76,188'],
    ['Listing headings', '19 (11 regulated-entity classes, 8 RBI function headings)'],
    ['Subject families (derived from titles)', '57'],
    ['Entity class × subject family cells', '1,083 (296 populated, 9 ambiguous)'],
    ['Titles with an “Updated as on” stamp', '162 (the corpus holds current text only)'],
    ['FAQ pages and items', '80 pages, 1,845 items'],
    ['Enforcement press releases', '463 (entity class resolved for 455)'],
    ['Amendment Directions', '333 pages'],
], [2.8, 3.0], font=10)
R.h2("3.4 Obligation candidate extraction")
R.p("The extractor is rule-based. It marks a paragraph as an obligation candidate when the paragraph contains a "
    "deontic cue such as “shall”, “must”, “is required to” or “should ensure”, and it "
    "excludes definitions, duties placed on customers and purely descriptive text. Of the 33,507 paragraphs that "
    "contain a deontic cue, the final rules (v4) keep 28,694 candidates. We refined the rules over four precision "
    "rounds, checking each version by hand on a fresh sample (Section 4.2).")
R.h2("3.5 Cross-class matching")
R.p("Each candidate obligation was matched to counterpart paragraphs in the Directions that the other entity classes "
    "receive on the same subject. The matcher combines bge-base-en-v1.5 cosine similarity with lexical overlap, and "
    "its threshold of 0.757567 was fixed on validation pairs before the matcher was used. The top two matches for each "
    "compared class later became the candidates shown to the annotator. Used directly as labels, the same matches form "
    "the “P2-002 candidates” baseline.")
R.h2("3.6 Benchmark tasks and annotation protocol")
R.p('**T1 (RQ1, RQ2).** We drew 123 candidates with a fixed seed, stratified by source class, with at most four '
    'compared classes per item. For each compared class the annotator picks one judgement from Table 3.4 and '
    'cites the counterpart paragraph; spans that place no duty on a regulated entity are rejected as not an '
    "obligation. Guideline rule v3.6 derives the item's flag: any ‘different’ gives ‘class-specific’, otherwise "
    'any ‘same’ gives ‘shared’, and all ‘none’ gives ‘absent’. Of the 123 items, 106 were validated and 17 '
    'rejected, leaving 412 class judgements.')
R.table('Annotation judgements for T1', ['Judgement', 'Meaning'], [
    ['same', 'The same obligation in substance'],
    ['different', 'Same topic, but a different threshold, timeline, scope, actor or carve-out'],
    ['none', 'No counterpart among the paragraphs checked'],
], [1.3, 4.5], font=10)
R.p("**Annotation workflow.** The gold labels come from one expert annotator who worked on blind sheets with written "
    "guidelines. Of the 106 gold items, 62 are single-pass, 6 were consistent across a blind retest, and 38 were "
    "adjudicated by the same annotator. Reliability was measured separately from the gold: three raters, all of them "
    "student authors, independently labelled thirty items drawn outside the T1 sample, and the annotator repeated a "
    "blind test–retest on 25 items. Fig. 3.3 shows this provenance.")
R.figure(FIG / "fig2_annotation_provenance.png", "Annotation and reliability: the single-expert gold and the "
         "separately measured reliability evidence", width=6.0)
R.p('**T2 (RQ1)** has three relevance sets for retrieving the target-class counterpart: one derived from the T1 '
    'labels (291 queries), one from the P2-002 validation pairs (53) and one from a hand alignment of FAQ and '
    'press release questions (25). **T3** asks for the status of a paragraph (in force, amended or deleted) on an '
    'as-of date; its 52 scored items come from a deterministic parser of Amendment Directions and update stamps. '
    '**T4 (RQ3)** has 30 questions. Each has a genuine RAG answer and three rule-built variants: a concatenation '
    'of the retrieved obligation sentences, a negated version of that concatenation, and an off-topic answer of '
    'matched length. Thirty answers also carry blind human ratings of faithfulness and of whether they answer the '
    'question. Table 3.5 summarises the benchmark.')
R.table("RBI-ObliBench at a glance", ["Component", "Size"], [
    ["Corpus", "381 Directions; 76,188 paragraphs; 11 regulated classes; 57 subject families"],
    ["T1 (RQ1, RQ2)", "106 validated of 123 sampled; 412 class units (same 213, different 78, none 121)"],
    ["T2 (RQ1)", "291 / 53 / 25 queries in three relevance sets"],
    ["T3", "52 scored items (of 60 built)"],
    ["T4 (RQ3)", "30 questions × 4 answer types; 30 human-rated answers"],
], [1.5, 4.3])
R.h2("3.7 Retrieval and judgement systems")
R.p("Fig. 3.4 shows the evaluation architecture. We compared five retrievers: BM25; dense retrieval with "
    "bge-base-en-v1.5; a hybrid that fuses the two with RRF (k = 60); a **class-aware hybrid** restricted to the "
    "Directions of the target class (and its function-heading Directions); and, as a diagnostic, the class-blind "
    "hybrid with every paragraph of the query's own source class removed. A **temporal filter** keeps only paragraphs "
    "in force on the as-of date, using the same amendment index that builds T3.")
R.figure(FIG / "fig3_evaluation_architecture.png", "Evaluation architecture: retrieval with optional class and "
         "temporal filters, LLM judgement, the NLI verifier, the long-context alternative and the structured "
         "comparator", width=6.0)
R.p('All T1 judgement systems use gemini-3.5-flash-lite at temperature zero, with minimal thinking, JSON output '
    'and frozen prompts whose SHA-256 hashes are stored in the configuration. Table 3.6 shows how they differ.')
R.table('T1 judgement systems', ['System', 'Evidence given to the model', 'Answer check'], [
    ['Class-blind LLM', 'Retrieved paragraphs, no class filter', 'None'],
    ['Class-aware LLM', 'Retrieved paragraphs from the target class', 'None'],
    ['Final agentic system', 'Retrieved paragraphs from the target class', 'NLI verifier (nli-deberta-v3-xsmall): retry, then abstain'],
    ['Class-blind LLM + verifier', 'Retrieved paragraphs, no class filter', 'NLI verifier'],
    ['Long-context system', 'Every Direction of the compared classes, up to a 100K-token cap', 'None'],
], [1.7, 2.6, 1.5], font=10)
R.p('The baselines are the majority class, computed in-sample from the gold (a reference point, not a deployable '
    'system), and the P2-002 candidate labels. Ablations A, B and C turn the class filter, the temporal filter '
    'and the verifier on or off. Orchestration is plain Python, and a later LangGraph port reproduced all four '
    'retrieval-based T1 systems exactly. The final agentic system works like this:')
R.bullets([
    "Input: source obligation *o*, compared class *c*, as-of date *t*.",
    "Retrieve the top-k paragraphs for *o* with the hybrid retriever, restricted to class *c* (class filter) and to "
    "paragraphs in force on *t* (temporal filter).",
    "Ask the LLM for a judgement in {same, different, none}, the matched paragraph id and a one-sentence rationale.",
    "Check the rationale against the cited paragraph with the NLI verifier; if it is not entailed, retry once with "
    "the verifier's feedback; if it still fails, abstain.",
    "Derive the item flag from the per-class judgements with rule v3.6.",
], numbered=True)
R.h2("3.8 Pairwise structured comparator")
R.p("The comparator is this project's targeted experiment, designed for the ‘different’ failure. For each item and "
    "compared class, the model receives the source obligation and the two candidate paragraphs that the annotator was "
    "shown. It extracts thirteen fields from both sides (actor, action, object, scope, condition, threshold, amount, "
    "percentage, frequency, deadline, exception, documentation and reporting) and marks each field as equal, "
    "different or present on one side only. The verdict is then decided by a **fixed rule, not by the model**, with "
    "the precedence same > different > none. We developed the prompt and the rule only on the separate 30-item set, "
    "revised them once to fix a field-extraction bug, and froze them by hash (system prompt 51f7ea78ed4b…, rule "
    "83664f8d9d8f…) before any run on the T1 gold. The comparisons against the class-aware LLM and against "
    "P2-002 were pre-registered.")
R.h2("3.9 Evaluation protocol")
R.p('Table 3.7 summarises how each task is scored, how abstentions are treated and how intervals are computed.')
R.table('Evaluation protocol', ['Item', 'Rule'], [
    ['T1', 'Three-way flag macro-F1 (shared, class-specific, absent); collapsed flag macro-F1 (absent versus present, the fair comparison with P2-002, which cannot express ‘different’); judgement macro-F1 over class units; ‘different’ F1; coverage'],
    ['T2', 'nDCG@10 [@jarvelin2002ndcg]'],
    ['T3', 'Status exact match'],
    ['T4', 'RePASs composite and its Spearman correlation with human ratings'],
    ['Abstentions', 'Kept in the denominator: an abstained class judgement counts as ‘unsure’ and matches no gold label; an item whose flag cannot be derived is scored as wrong'],
    ['Long-context system', 'Scored on the 102 items it answered; comparisons with it use the same items'],
    ['Confidence intervals', '95% percentile bootstrap over 2,000 item resamples [@efron1979]; differences paired on the same items, noting whether the interval excludes zero'],
    ['Proportions and agreement', "Wilson intervals [@wilson1927]; Cohen's and Fleiss' κ [@cohen1960, @fleiss1971]"],
], [1.6, 4.2], font=10)
R.h2("3.10 Applications built on the benchmark")
R.h3("3.10.1 Interactive inspection website and live comparator API")
R.p('The React and TypeScript website shows all 412 expert-labelled comparisons with every sealed system answer; '
    'its main pages are listed in Table 3.8. It is hosted as an Azure static website, and the comparator API runs '
    'as an Azure Function that loads the frozen prompt and rule and checks their hashes before use. Because RBI '
    "text is copyrighted, excerpts are capped at twelve words and always link to the RBI's PDF.")
R.table('Main pages of the inspection website', ['Page', 'Purpose'], [
    ['Microscope', "One case in full: both excerpts with RBI links, every system's answer and input, the 13-field table and the rule's decision trace"],
    ['Failure Map', 'The 78 real differences plotted against all systems'],
    ['Play', 'A spot-the-difference game'],
    ['Atlas', '11 institution types × 57 topics'],
    ['Lab', 'Live re-run of a benchmark pair, compared with the sealed answer'],
    ['Triage, Results, Method', 'Review triage view; results and method pages'],
    ['Presenter mode', 'Scripted demonstration for presentations'],
], [1.6, 4.2], font=10)
R.h3("3.10.2 Local compliance audit generator with an AI assistant")
R.p("The audit generator applies the pipeline to a compliance team's routine work (Fig. 3.5). The user enters an "
    'entity profile (class, as-of date, last review date and activities) and receives an audit pack in which '
    'every row cites its RBI paragraph. Table 3.9 lists the six parts of the pack.')
R.table('Contents of an audit pack', ['Part', 'What it contains'], [
    ['Applicability register', "Obligations that bind the entity's class"],
    ['Change-impact log', 'Changes since the last review date'],
    ['Compliance calendar', 'Deadlines and frequencies'],
    ['Cross-class differential', 'Differences across the entities of a group'],
    ['Enforcement-risk view', 'Related penalty press releases'],
    ['Policy gap analysis', 'Each applicable obligation marked covered, partial or missing in an uploaded policy'],
], [1.9, 3.9], font=10)
R.p('Reviewers confirm or dispute each row. Packs can be exported to Excel, DOCX, PDF, iCalendar and a JSON audit '
    'trail, and the FastAPI backend binds to 127.0.0.1 only.')
R.figure(FIG / "block_auditgen.png", "Block diagram of the local compliance audit generator", width=6.0)
R.p('Each pack also has an AI assistant for questions, explanations of obligations and changes, draft policy '
    'clauses and executive memos. It runs only on a local Ollama model and refuses non-loopback hosts. A sentence '
    'is shown only if it cites RBI text, passes the NLI cross-encoder check and uses no number that is missing '
    'from the source. The assistant cannot change a review status.')
R.h2("3.11 Standards and ethical considerations")
R.h3("3.11.1 Software engineering standards")
R.p('Table 3.10 lists the software standards and how we applied each.')
R.table('Software engineering standards and how they were applied', ['Standard', 'How it was applied'], [
    ['ISO/IEC/IEEE 12207:2017 (life-cycle processes)', 'Gated phases P0 to P5, each with a written plan, audit and acceptance checklist'],
    ['ISO/IEC/IEEE 29148:2018 (requirements)', 'Research questions, tasks and acceptance criteria written before coding; comparator analysis pre-registered'],
    ['IEEE 1016-2009 (design descriptions)', 'Module boundaries, data schemas and decision records (D-01 to D-28 for the demo) documented'],
    ['ISO/IEC/IEEE 29119 (testing)', 'Over 1,200 automated Python tests and 115 UI tests; release check for excluded paths, key-like strings, oversized files and long copied RBI text; data assertions in the UI build'],
    ['IEEE reference style, ISO 8601, RFC 5545', 'Citations, dates and the iCalendar export'],
], [2.2, 3.6], font=10)
R.h3("3.11.2 Ethical AI standards")
R.p('Table 3.11 maps four IEEE 7000-series standards, and the human-oversight principle, to the project. They '
    'guided the design; no formal conformity assessment has been carried out.')
R.table('Ethical AI standards and principles and how they were applied', ['Standard or principle', 'How it was applied'], [
    ['IEEE 7000-2021, ethical concerns in system design [@ieee7000]', 'Copyright, privacy and human oversight treated as requirements: pointer-only release, no personal data in prompts, AI use disclosed (Section 3.12), “decision support only, not legal advice” on every audit output'],
    ['IEEE 7001-2021, transparency [@ieee7001]', 'Sealed, inspectable system answers; comparator field table and rule trace; every audit row cites Direction, paragraph id and RBI link; prompts, rules and model versions frozen by hash'],
    ['IEEE 7002-2022, data privacy [@ieee7002]', 'Audit generator runs locally on 127.0.0.1 with a local model; uploaded policies kept in the audit trail only as hashes'],
    ['IEEE 7003-2024, algorithmic bias [@ieee7003]', 'Known biases documented: each T2 set favours one retriever; annotator and comparator saw the same P2-002 candidates; single-expert gold; 7 to 15 T1 items per class (Section 5.2)'],
    ['Human oversight (Ethically Aligned Design [@ead2019]; RBI FREE-AI [@freeai2025])', 'Every audit-pack row needs a human decision, and AI suggestions cannot override it'],
], [2.2, 3.6], font=10)
R.h2("3.12 Use of AI tools")
R.p('AI use, stated plainly: Claude Code (Anthropic) wrote the repository code to our instructions, covering the '
    'scraper, preprocessing, extraction, matching, benchmark tooling, evaluation and statistics scripts, the '
    'website and the audit generator, and it drafted our internal reports. Claude also helped draft and edit this '
    'report, and we checked all of its output. gemini-3.5-flash-lite and gpt-oss-120b are evaluated systems only '
    'and never produced labels; all human labels were assigned by hand. Prompts used public RBI text and no '
    'personal data.')
R.p('**Summary:** Chapter 3 covered the corpus, the four tasks and their labels, the systems and the comparator, '
    'the scoring rules, the two applications and the standards behind them.')

# ------------------------------------------------------------------------------------------------ Chapter 4
R.chapter_heading("Results and Analysis")
R.p('The chapter checks the benchmark inputs (Sections 4.2 and 4.3), answers RQ1 to RQ3 and covers T3 (Sections '
    '4.4 to 4.8), adds further experiments (Section 4.9) and discusses the results (Sections 4.10 and 4.11). '
    'Brackets give 95% confidence intervals.')
R.h2("4.1 Experimental setup")
R.p('All T1 systems used gemini-3.5-flash-lite at temperature zero with frozen prompts. Each ran once per item, '
    'and predictions were sealed before scoring. One command rebuilds any table from the stored predictions, and '
    "the paper's tables come from the same results file.")
R.h2("4.2 Intermediate-step validation")
R.p("**Candidate extraction.** Over four rounds of hand checks, the precision of the extraction rules rose from 0.675 "
    "to 0.929 (Table 4.1, Fig. 4.1).")
R.table("Precision of obligation candidate extraction by rule version (Wilson 95% CI)",
        ["Rules", "n", "True obligations", "Precision [95% CI]"], [
            ["v1", "40", "27", "0.675 [0.520, 0.799]"], ["v2", "40", "31", "0.775 [0.625, 0.877]"],
            ["v3", "40", "34", "0.850 [0.709, 0.929]"], ["v4 (final)", "28", "26", "0.929 [0.774, 0.980]"],
        ], [1.3, 0.8, 1.5, 2.2])
R.figure(FIG / "precision_rounds.png", "Precision of candidate extraction over four rule rounds", width=4.2)
R.p("**Cross-class matching.** On 60 validation pairs the matcher found a true counterpart in 53, a rate of 0.883 "
    "[0.778, 0.942]. **Supplementary sources.** FAQ alignment was clean in only 5 of 30 samples (0.167), and "
    "enforcement alignment in 16 of 30 (0.533). Under the locked decision rule, FAQ text is therefore used only for "
    "validation and motivation, and enforcement releases only as Direction-level weak labels. **T1 sampling.** 17 of "
    "the 123 sampled candidates were rejected as not an obligation (0.138 [0.088, 0.210]). The 106 validated items "
    "are flagged shared (52), class-specific (40) and absent (14).")
R.h2("4.3 Annotation reliability")
R.table("Reliability evidence, κ [95% bootstrap CI] (number of items); neither row is computed on the gold",
        ["Evidence", "Class judgement", "Flag", "Not-obligation"], [
            ["Separate 30-item set, 3 raters (Fleiss)", "0.774 [0.645, 0.886] (20)", "0.571 [0.289, 0.807] (20)",
             "0.392 [-0.015, 0.689] (30)"],
            ["Annotator blind retest, 11.7-18.6 h gap (Cohen)", "0.550 [0.333, 0.752] (20)",
             "0.426 [0.091, 0.730] (20)", "0.702 [0.000, 1.000] (25)"],
            ["Timed blind re-label of 20 single-pass items", "0.684 [0.506, 0.872] (19)", "0.409 [0.042, 0.759] (19)",
             "-"],
        ], [2.0, 1.3, 1.3, 1.2], font=9.5)
R.p("Agreement among the three raters on class judgements is substantial on the Landis and Koch scale "
    "[@landis1977]. On the derived flag it is only moderate, which is expected: a flag compounds the errors of up to "
    "four class judgements. The retest is supplementary evidence, because a gap of 11.7 to 18.6 hours is short enough "
    "for recall to inflate agreement. The gold itself remains single-expert, and we note this wherever T1 results are "
    "reported.")
R.h2("4.4 RQ1: applicability and counterpart retrieval (T2)")
R.table("T2 counterpart retrieval, nDCG@10 [95% CI]", ["System", "xclass_t1 (291)", "xclass_p2002 (53)",
                                                      "supp_p2003 (25)"], [
    ["BM25", "0.458 [0.424, 0.492]", "0.277 [0.194, 0.369]", "0.616 [0.462, 0.761]"],
    ["Dense (bge)", "0.421 [0.385, 0.455]", "0.334 [0.252, 0.428]", "0.362 [0.212, 0.528]"],
    ["Hybrid RRF", "0.443 [0.408, 0.478]", "0.319 [0.234, 0.414]", "0.504 [0.348, 0.673]"],
    ["Hybrid - source class", "0.464 [0.429, 0.497]", "0.337 [0.256, 0.429]", "0.504 [0.348, 0.673]"],
    ["**Class-aware hybrid**", "**0.894 [0.864, 0.922]**", "**0.741 [0.630, 0.844]**", "**0.675 [0.535, 0.811]**"],
], [1.75, 1.35, 1.35, 1.35], font=9.5)
R.figure(FIG / "t2_ndcg.png", "nDCG@10 of the five retrievers on the three T2 relevance sets", width=5.8)
R.p("The class filter raises nDCG@10 on t2_xclass_t1 by **+0.451 [+0.421, +0.481]** (excludes 0), and the gain "
    "appears on all three relevance sets: +0.423 [+0.336, +0.514] on t2_xclass_p2002 and +0.171 [+0.072, +0.273] on "
    "t2_supp_p2003, both excluding zero. Some of this gain is built in, because relevance was labelled only for the "
    "target-class counterpart. The third set, however, was constructed independently and still shows a clear gain. "
    "Removing only the source class is not enough (0.464), which suggests that the benefit comes from knowing the "
    "target class rather than merely from avoiding near-duplicates in the source Direction. The class-blind dense "
    "retriever reaches 0.421 against 0.894 for the class-aware hybrid; for the second half of RQ1, then, a class-blind "
    "retriever loses more than half of the achievable nDCG on this set.")
R.p("The picture changes on T1, where the class filter has no significant effect: class-aware minus class-blind "
    "three-way flag F1 is -0.050 [-0.133, +0.027] without the verifier and -0.049 [-0.133, +0.036] with it, and "
    "neither interval excludes zero. Finding the counterpart is not where T1 systems struggle.")
R.h2("4.5 RQ2: differential obligation (T1)")
R.table("T1 on the 106-item gold: flag and judgement macro-F1 [95% CI], different F1 and coverage",
        ["System", "n", "3-way F1", "Collapsed F1", "Judgement F1", "diff. F1", "Coverage"], [
            ["Majority (in-sample)", "106", "0.219", "0.465", "0.227", "0.000", "1.000"],
            ["P2-002 candidates", "106", "0.459", "0.784", "0.550", "0.000", "1.000"],
            ["Class-blind LLM", "106", "0.602", "0.766", "0.664", "0.321", "1.000"],
            ["Class-aware LLM", "106", "0.551", "0.808", "0.609", "0.154", "0.991"],
            ["Final agentic", "106", "0.483", "0.710", "0.521", "0.047", "0.774"],
            ["Class-blind + verifier", "106", "0.532", "0.695", "0.578", "0.176", "0.792"],
            ["Long-context (100K)", "102", "0.509", "0.819", "0.551", "0.074", "1.000"],
            ["**Structured comparator**", "106", "**0.616**", "**0.838**", "**0.680**", "**0.409**", "1.000"],
        ], [1.65, 0.4, 0.75, 0.85, 0.85, 0.65, 0.7], font=9.5)
R.p("Table 4.4 gives point estimates; Appendix B lists the confidence interval for every cell. No LLM system "
    "significantly beats the P2-002 candidate labels on collapsed flag F1: class-blind minus P2-002 is -0.019 "
    "[-0.114, +0.072] and class-aware minus P2-002 is +0.024 [-0.096, +0.135], and neither interval excludes zero. "
    "On three-way F1 the class-blind LLM does beat P2-002, by +0.143 [+0.054, +0.232], because P2-002 cannot express "
    "‘different’ at all.")
R.figure(FIG / "t1_systems.png", "Three-way flag macro-F1 and different F1 of every T1 system", width=6.0)
R.h3("4.5.1 The different failure")
R.p("The LLM systems fail most on the ‘different’ judgement. Of the 78 gold ‘different’ class units, **56 are missed by every "
    "LLM system** when all five answered, and 58 when only the systems that answered are counted. We classify an "
    "error as a retrieval failure if the gold matched paragraph was absent from the system's context, and as a "
    "reasoning failure if it was present. Across the five LLM systems, 262 of the 350 ‘different’ errors occurred "
    "with the gold counterpart in context (Table 4.5, Fig. 4.4), so most of these errors are reasoning failures rather "
    "than retrieval failures.")
R.table("Errors on the 78 gold different units: retrieval versus reasoning, and the wrong answer given",
        ["System", "Errors", "Retrieval", "Reasoning", "→ same", "→ none"], [
            ["Class-blind LLM", "60/78", "30", "30", "18", "42"],
            ["Class-aware LLM", "71/78", "12", "59", "32", "39"],
            ["Final agentic", "76/78", "12", "64", "13", "44"],
            ["Class-blind + verifier", "70/78", "30", "40", "8", "41"],
            ["Long-context (100K)", "73/78", "4", "69", "43", "30"],
            ["Structured comparator", "40/78", "0", "40", "6", "32"],
        ], [1.9, 0.8, 0.85, 0.85, 0.7, 0.7])
R.figure(FIG / "different_errors.png", "Retrieval and reasoning failures on the gold different units", width=5.8)
R.p("The systems also err in different directions. On gold ‘different’ units, the class-aware LLM answers ‘same’ 32 "
    "times and ‘none’ 39 times, while the long-context model answers ‘same’ 43 times. Either way, the difference that a "
    "compliance reviewer needs to see is lost.")
R.h3("4.5.2 Verifier and long-context")
R.p("Adding the NLI verifier lowers three-way flag F1 by **-0.068 [-0.132, -0.012]** and coverage by -0.217 [-0.292, "
    "-0.142], both excluding zero; on the class-blind side the loss is -0.069 [-0.129, -0.014]. The final agentic "
    "system abstained on 81 class judgements, 59 of which had been correct before the retry. Our reading is that a "
    "whole-paragraph entailment premise is a poor test for a one-sentence rationale. The long-context model answered "
    "102 items at the 100K cap. On those items it ties the retrieval systems on three-way F1 and beats the final "
    "agentic system on collapsed F1 by +0.126 [+0.016, +0.240]. When the relevant Directions fit in the context "
    "window, retrieval does not appear to be the bottleneck.")
R.h2("4.6 Targeted experiment: the structured comparator")
R.table("Pre-registered comparator comparisons on the gold (paired item bootstrap, 95% CI)",
        ["Comparator minus", "Class-aware LLM", "P2-002 candidates"], [
            ["Δ judgement macro-F1", "+0.071 [+0.001, +0.142]", "+0.130 [+0.067, +0.191]"],
            ["Δ different F1", "+0.255 [+0.094, +0.411]", "+0.409 [+0.282, +0.530]"],
            ["Δ different recall", "+0.397 [+0.250, +0.543]", "+0.487 [+0.338, +0.632]"],
            ["Δ collapsed flag F1", "+0.030 [-0.061, +0.128]", "+0.054 [-0.057, +0.168]"],
        ], [1.8, 2.0, 2.0])
R.p("Against the class-aware LLM, the comparator raises ‘different’ F1 by +0.255, ‘different’ recall by +0.397 and "
    "judgement macro-F1 by +0.071, and all three intervals exclude zero (Table 4.6). The gain does not extend to "
    "collapsed flag F1 (+0.030 [-0.061, +0.128]). The comparator recovers 26 of the 56 units that every LLM system "
    "missed, and on the gold its ‘different’ recall is 0.487 at a precision of 0.352. Its ‘different’ F1 on the "
    "development set had been 0.348, so the gold result does not come from tuning on test data. The remaining errors "
    "run ‘different’ → ‘none’ 32 times and ‘different’ → ‘same’ only 6 times: in most failures the model "
    "decides that the two paragraphs do not describe the same duty. This points to topic matching, rather than field "
    "extraction, as the next bottleneck.")
R.h2("4.7 RQ3: metric integrity (T4)")
R.table("RePASs composite by answer type (mean [95% CI]) and correlation with human ratings",
        ["Measure", "Value"], [
            ["Genuine answer", "0.371 [0.311, 0.431]"], ["Concatenated obligations", "0.746 [0.692, 0.796]"],
            ["Negated concatenation", "0.049 [0.022, 0.082]"], ["Off-topic answer", "0.229 [0.198, 0.257]"],
            ["Concatenated - genuine", "+0.375 [+0.325, +0.427] (reproduces)"],
            ["Spearman ρ with human faithfulness", "0.731 [0.535, 0.845]"],
            ["Spearman ρ with answers-the-question", "0.008 [-0.323, 0.339]"],
        ], [2.8, 3.0])
R.figure(FIG / "repass.png", "RePASs composite score of the four answer types on RBI text", width=4.6)
R.p('Table 4.7 shows that the gameability reproduces (pre-registered verdict: reproduces): concatenated answers '
    'score +0.375 above genuine ones, while negated and off-topic answers score lower. RePASs follows human '
    'faithfulness ratings but not answer relevance. An exploratory repair, an overlap penalty plus a relevance '
    'term, ranked genuine answers first (+0.208 over concatenated) but lost agreement with human faithfulness (ρ '
    '= -0.126 [-0.477, 0.216]), so we do not treat it as usable.')
R.h2("4.8 Temporal status (T3) and ablations")
R.p("With the temporal filter on, status exact match is 1.000, but this result is circular: the gold and the filter "
    "share one parser. Without the filter the score falls to 0.538 [0.404, 0.673], and the model answered “in "
    "force, original” on 48 of the 52 items. What T3 shows, then, is that a model uses the dates it is given but "
    "does not infer amendment status on its own. Table 4.8 summarises ablations A to C.")
R.table("Ablations A-C (ON minus OFF, 95% CI)", ["Ablation", "Measure", "n", "ON - OFF"], [
    ["A: class filter", "T2 nDCG@10, xclass_t1", "291", "+0.451 [+0.421, +0.481]"],
    ["A: class filter", "T1 3-way flag F1 (with verifier)", "106", "-0.049 [-0.133, +0.036]"],
    ["B: temporal filter", "T3 status exact match", "52", "+0.462 [+0.327, +0.596]"],
    ["C: verifier", "T1 3-way flag F1", "106", "-0.068 [-0.132, -0.012]"],
    ["C: verifier", "T1 coverage", "106", "-0.217 [-0.292, -0.142]"],
    ["C: verifier", "T4 unsupported-sentence rate", "28", "-0.382 [-0.552, -0.214]"],
    ["C: verifier", "T4 abstention rate", "28", "+0.393 [+0.214, +0.571]"],
], [1.3, 2.3, 0.5, 1.7], font=9.5)
R.h2("4.9 Additional experiments")
R.p('The extra experiments were pre-registered after the main runs and reuse the same prompts and intervals '
    '(Table 4.9).')
R.table('Additional experiments', ['Experiment', 'Result'], [
    ['Cross-encoder re-ranker (ms-marco-MiniLM-L6-v2, hybrid top 20)', 'No reliable T2 gain; T1 class-blind three-way F1 -0.064 [-0.115, -0.017]'],
    ['gpt-oss-120b, class-blind, 103 items (free-tier limit)', 'Tied gemini-3.5-flash-lite on three-way F1: -0.010 [-0.094, +0.084]'],
    ['ObliQA test set, BM25 retrieval', 'Recall@10 75.3 [73.9, 76.8] versus 76.1 published'],
    ['IndiaFinBench, stratified prefix of 268 of 406 items', 'Frozen answer prompt: 75.7% [70.3, 80.5]'],
], [2.8, 3.0], font=10)
R.h2("4.10 Discussion")
R.p('Putting it all together, six findings stand out. We see them as things the benchmark reveals, not as proof '
    'that our agent is better than the alternatives:')
R.bullets([
    "Class-aware filtering substantially improves counterpart retrieval.",
    "That improvement does not carry over to T1 judgement: locating the counterpart is easier than deciding what "
    "differs.",
    "The ‘different’ judgement is the core failure, and most ‘different’ errors are reasoning failures.",
    "The NLI verifier hurts T1, because it declines many correct answers.",
    "A long-context model without retrieval is competitive when the relevant Directions fit in its window.",
    "RePASs can be gamed by concatenation on RBI text, so a faithfulness score needs a relevance component that "
    "verbatim text cannot satisfy.",
], numbered=True)
R.p('The comparator is the one encouraging result. Once the model is made to compare the two paragraphs field by '
    'field and a fixed rule makes the call, some of the ‘different’ cases that free-form judgement misses are '
    'recovered. The problem is far from solved, though: the comparator still misses 40 of the 78 ‘different’ '
    'units.')
R.h2("4.11 Validity of the results")
R.p('Freezing and hashing prompts, rules and thresholds before testing, pre-registering the comparator '
    "comparisons, pairing every bootstrap comparison, counting abstentions as errors and generating the paper's "
    'numbers from the results file all guard against tuning on test data and against transcription mistakes; the '
    'software was tested along ISO/IEC/IEEE 29119 lines (Section 3.11). None of this removes the single-expert '
    'gold limitation discussed in Chapter 5.')
R.p('**Summary:** Class filtering helps retrieval, not judgement (RQ1); LLM systems miss most real differences, '
    'and the comparator recovers part of them (RQ2); RePASs can be gamed on RBI text (RQ3).')

# ------------------------------------------------------------------------------------------------ Chapter 5
R.chapter_heading("Advantages, Limitations and Applications")
R.p('Tables 5.1 to 5.3 summarise the strengths, limitations and likely users of the work, with the evidence for '
    'each.')
R.h2("5.1 Advantages")
R.table('Advantages and supporting evidence', ['Advantage', 'Evidence'], [
    ['A new evaluation target: counterparts that exist but differ', 'T1 results (Section 4.5)'],
    ['A complete, current corpus of 381 Master Directions with stable ids, matrix and amendment index', 'Section 3.3'],
    ['Fair evaluation: frozen prompts and rules, pre-registration, paired bootstrap, abstentions scored as errors', 'Sections 3.9 and 4.11'],
    ['An interpretable comparator: 13-field table and fixed rule', 'Section 3.8'],
    ['A copyright-safe release: pointers with SHA-256 hashes and a rehydration script', 'Appendix B'],
    ['Reproducible code: one command per table, over 1,200 automated tests, release safety check', 'Section 3.11'],
    ['Local, private applications: uploaded policies stored only as hashes', 'Section 3.10.2'],
], [4.3, 1.5], font=10)
R.h2("5.2 Limitations")
R.table('Limitations and their consequences', ['Limitation', 'Consequence'], [
    ['T1 has 106 items, 7 to 15 per source class', 'Per-class results are uncertain'],
    ['Gold labels from a single expert; agreement measured on a separate sample; short retest gap', 'Label reliability is established only indirectly'],
    ['At most four classes per item; annotator and comparator saw the same two candidates', 'Possible bias towards the P2-002 candidates'],
    ['Each T2 relevance set favours one retriever', 'Retrieval comparisons depend on the set used'],
    ['T3 gold and filter share one parser, which has a known defect on merged changes', 'T3 is circular'],
    ['The corpus holds only current, amended text', 'Earlier wording cannot be shown'],
    ['T4 is small, with LLM-drafted questions and one rater; the RePASs repair is exploratory', 'T4 findings are preliminary'],
    ['Main LLM results use a Flash-Lite-class model on free tiers', 'May not hold for stronger models'],
    ['The tools give decision support', 'They are not legal advice'],
], [3.6, 2.2], font=10)
R.h2("5.3 Applications")
R.table('Applications by user group', ['User', 'Use'], [
    ['Compliance teams of regulated entities', 'Applicability register, change log and compliance calendar, each row linked to the RBI paragraph'],
    ['Groups with several regulated entities', 'Cross-class differential, e.g. a bank versus its NBFC subsidiary'],
    ['Internal and statutory auditors', 'Reviewable pack with sign-off and a JSON audit trail'],
    ['Policy owners', 'Gap analysis of an internal policy against every applicable obligation'],
    ['RegTech vendors and researchers', 'A benchmark for RAG on Indian regulation; evidence on the limits of RePASs'],
    ['Teachers and trainers', 'The inspection website as a teaching aid on subtle regulatory differences'],
], [2.2, 3.6], font=10)
R.p("**Summary:** The work's main strengths are its new evaluation target and careful protocol; its main weakness "
    'is a small, single-expert gold set evaluated with small hosted models.')

# ------------------------------------------------------------------------------------------------ Chapter 6
R.chapter_heading("Conclusion and Future Scope")
R.p('This last chapter gives our answers and next steps.')
R.h2("6.1 Conclusion")
R.p('RBI-ObliBench was built to test whether systems can tell which RBI obligations apply to an entity class and '
    'where parallel Master Directions differ; Table 6.1 summarises our answers.')
R.table('Answers to the research questions', ['Question', 'Answer', 'Main evidence'], [
    ['RQ1 Applicability', 'Yes for retrieval; no for judgement', 'Class filter: nDCG@10 +0.451; no significant difference on T1'],
    ['RQ2 Differential obligation', 'Not with current free-form LLM systems', 'Most real differences missed, usually with the counterpart in context; structured comparator: ‘different’ F1 0.409, recovers 26 of 56, still misses 40 of 78'],
    ['RQ3 Metric integrity', 'Yes, RePASs is gameable', 'Verbatim concatenation rewarded, as on ObliQA; the repair loses agreement with human ratings'],
], [1.5, 1.6, 2.7], font=10)
R.p('The RQ3 result means a faithfulness metric needs a relevance term that copied text cannot satisfy. The '
    "project's outputs are a pointer-only data release, a tested code base, a public inspection website, a local "
    'compliance audit generator and a paper submitted to AISIGH-SD 2026.')
R.h2("6.2 Future scope")
R.p('Next steps, most urgent first: a retest after days rather than hours and independent second raters for every '
    'gold item; a frontier LLM on T1 and the comparator; the comparator on retrieved evidence with better topic '
    'matching, since most of its errors are ‘different’ answered as ‘none’; larger two-rater versions of T3 and '
    'T4 and a working RePASs repair; and the full IndiaFinBench run, full use of the FAQ and enforcement sources, '
    'and a pilot of the audit generator with a compliance team.')

# ------------------------------------------------------------------------------------------------ References
R.chapter_heading("References", numbered=False)
R.chapter = 0
missing = [k for k in R.cites if k not in REFS]
if missing:
    raise SystemExit(f"cited keys with no reference entry: {missing}")
unused = [k for k in REFS if k not in R.cites]
if unused:
    raise SystemExit(f"reference entries never cited: {unused}")
for key, n in sorted(R.cites.items(), key=lambda kv: kv[1]):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    para.paragraph_format.left_indent = Inches(0.45)
    para.paragraph_format.first_line_indent = Inches(-0.45)
    para.paragraph_format.line_spacing = 1.15
    para.paragraph_format.space_after = Pt(5)
    R.runs(para, f"[{n}]\t{REFS[key]}", size=11)

# ------------------------------------------------------------------------------------------------ Appendices
R.chapter_heading("Appendix A: Soft Code Flowcharts", numbered=False)
R.p("This appendix gives the flowcharts and algorithms of the main software components. The code is in the project "
    "repository; every stage runs with one command (Table A.1).")
R.table("Pipeline stages and commands", ["Stage", "Command"], [
    ["Harvest, text extraction, segmentation", "python3 scripts/run_harvest.py all"],
    ["Vocabularies and entity class × subject matrix", "python3 scripts/run_matrix.py all"],
    ["Obligation candidates (P2-001)", "python3 scripts/run_candidates.py extract"],
    ["Cross-class matching (P2-002)", "python3 scripts/run_matching.py units"],
    ["T1 candidate benchmark (P2-004)", "python3 scripts/run_t1.py candidates"],
    ["T2 retrieval baselines (P3-001)", "python3 scripts/run_p3001.py index | qrels | retrieve | score"],
    ["T3 temporal set", "python3 scripts/run_t3.py build"],
    ["T4 RePASs audit (P3-002)", "python3 scripts/run_t4.py questions ... analyze"],
    ["RAG systems and ablations (P4)", "python3 scripts/run_p4.py t1 --system <system>"],
    ["All tables and results file", "python3 scripts/build_tables.py"],
    ["Pointer-only release and safety check", "python3 scripts/build_release.py; scripts/release_check.py"],
    ["Audit generator", "python3 scripts/auditgen.py generate --profile <file>"],
], [2.6, 3.2], font=9.5, label_prefix="A.1")
R.figure(FIG / "block_overall.png", "Flow of the complete pipeline (as in Fig. 3.1)", width=5.6, label_prefix="A.1")
R.h3("Algorithm A.1: Structured comparator decision")
R.bullets([
    "For a source obligation *s* and candidate paragraphs *c1*, *c2* of a compared class:",
    "Ask the model to extract the 13 fields from *s* and from each candidate (JSON, frozen prompt).",
    "The model also marks each field equal, differs, only in the source, only in the target, or absent, and says "
    "whether the candidate addresses the same duty.",
    "Per candidate (fixed rule comparator-rule-v1): if it does not address the same duty, the verdict is **none**.",
    "Otherwise, if any of the 13 fields differs, or a material field (every field except action and object) is "
    "stated on one side only, the verdict is **different**; otherwise it is **same**.",
    "Class verdict: the strongest per-candidate verdict with precedence same > different > none; the matched "
    "paragraph is the first candidate with that verdict. An unreadable answer gives **unsure**.",
], numbered=True)
R.h3("Algorithm A.2: Bootstrap confidence interval of a paired difference")
R.bullets([
    "Input: per-item predictions of systems X and Y and the gold labels for n items.",
    "Repeat 2,000 times: draw n items with replacement; compute metric(X) - metric(Y) on the sample.",
    "Report the observed difference with the 2.5th and 97.5th percentiles of the resampled differences.",
    "State whether the interval excludes zero (above or below).",
], numbered=True)

R.chapter_heading("Appendix B: Data Sheets", numbered=False)
R.p("This project has no hardware components, so the data sheets are those of the dataset and of the models used, "
    "following the datasheets-for-datasets practice.")
R.table("Data sheet of the RBI-ObliBench release", ["Field", "Value"], [
    ["Name and version", "RBI-ObliBench v1.0"],
    ["Source", "RBI Master Directions (rbi.org.in), harvested 22 August to 25 September 2026"],
    ["Contents", "Pointers (Direction id, paragraph id, character offsets, URL, harvest date, SHA-256), labels"],
    ["Tasks", "T1 (106 items, 412 class units), T2 (291/53/25), T3 (52), T4 (30 × 4)"],
    ["Labels", "Manual, single expert for T1 gold; three-rater sample for reliability"],
    ["Licence", "Code MIT; annotations and derived metadata CC BY 4.0; RBI text not included"],
    ["Rehydration", "scripts/rehydrate.py rebuilds text from RBI URLs and checks hashes"],
    ["Intended use", "Research on regulatory retrieval and RAG; not legal or compliance advice"],
], [1.6, 4.2], label_prefix="B.1")
R.table("Data sheet of the models used", ["Model", "Role", "Licence / access"], [
    ["bge-base-en-v1.5", "Dense retrieval and cross-class matching", "MIT"],
    ["cross-encoder/nli-deberta-v3-xsmall", "NLI verifier; AI-assistant sentence check", "Apache-2.0"],
    ["gemini-3.5-flash-lite", "All T1 systems, long-context, comparator", "Gemini API free tier"],
    ["gpt-oss-120b (via Groq)", "T4 questions and genuine answers; additional T1 run", "Open weights"],
    ["RePASs (NLI + LEGAL-BERT classifier)", "Metric under audit (T4)", "Used unmodified"],
    ["ms-marco-MiniLM-L6-v2", "Cross-encoder re-ranker (additional experiment)", "Open weights"],
], [2.1, 2.3, 1.4], font=9.5, label_prefix="B.2")
R.table("T1 results with 95% bootstrap confidence intervals", ["System", "3-way F1", "Collapsed F1",
                                                               "Judgement F1", "Coverage"], [
    ["Majority (in-sample)", "0.219 [0.186, 0.246]", "0.465 [0.445, 0.483]", "0.227 [0.202, 0.248]",
     "1.000 [1.000, 1.000]"],
    ["P2-002 candidates", "0.459 [0.381, 0.520]", "0.784 [0.671, 0.877]", "0.550 [0.512, 0.583]",
     "1.000 [1.000, 1.000]"],
    ["Class-blind LLM", "0.602 [0.497, 0.700]", "0.766 [0.647, 0.873]", "0.664 [0.597, 0.726]",
     "1.000 [1.000, 1.000]"],
    ["Class-aware LLM", "0.551 [0.445, 0.639]", "0.808 [0.685, 0.908]", "0.609 [0.553, 0.667]",
     "0.991 [0.972, 1.000]"],
    ["Final agentic", "0.483 [0.385, 0.568]", "0.710 [0.590, 0.815]", "0.521 [0.470, 0.570]",
     "0.774 [0.689, 0.849]"],
    ["Class-blind + verifier", "0.532 [0.431, 0.625]", "0.695 [0.572, 0.802]", "0.578 [0.520, 0.639]",
     "0.792 [0.708, 0.868]"],
    ["Long-context (100K)", "0.509 [0.408, 0.600]", "0.819 [0.691, 0.917]", "0.551 [0.496, 0.604]",
     "1.000 [1.000, 1.000]"],
    ["Structured comparator", "0.616 [0.512, 0.702]", "0.838 [0.720, 0.926]", "0.680 [0.622, 0.732]",
     "1.000 [1.000, 1.000]"],
], [1.4, 1.1, 1.1, 1.1, 1.1], font=8, label_prefix="B.3")

R.chapter_heading("Appendix C: Software Component List", numbered=False)
R.p("The project uses software components only. Table C.1 lists the main ones with their versions and licences.")
R.table("Software components", ["Component", "Version", "Purpose", "Licence"], [
    ["Python", "3.14.3", "Language for the pipeline and backend", "PSF"],
    ["bm25s", "0.3.11", "BM25 lexical retrieval", "MIT"],
    ["sentence-transformers", "6.1.0", "Embeddings and cross-encoders", "Apache-2.0"],
    ["transformers / PyTorch", "5.4.0 / 2.11.0", "Model inference", "Apache-2.0 / BSD"],
    ["NumPy / pandas / SciPy", "2.4.3 / 3.0.1 / 1.17.1", "Data handling and statistics", "BSD"],
    ["scikit-learn", "1.6.1", "Metrics (F1, kappa)", "BSD"],
    ["pdfplumber", "0.11.10", "PDF text extraction", "MIT"],
    ["requests / BeautifulSoup / lxml", "2.33.0 / 4.14.3 / 6.1.1", "Harvesting and HTML parsing", "Apache / MIT / BSD"],
    ["FastAPI / uvicorn / pydantic", "0.135.3 / 0.44.0 / 2.13.0", "Audit generator backend", "MIT / BSD / MIT"],
    ["pytest", "9.1.1", "Python test suite", "MIT"],
    ["React / Vite / TypeScript", "19 / 7 / 5.9", "Inspection website", "MIT / MIT / Apache-2.0"],
    ["Tailwind CSS / Recharts / React Flow", "4 / 3 / 12", "Styling, charts, diagrams", "MIT"],
    ["Hono", "4", "Comparator API (Azure Function)", "MIT"],
    ["Ollama", "local", "On-device model for the AI assistant", "MIT"],
], [1.95, 1.35, 1.6, 0.9], font=9, label_prefix="C.1")

R.chapter_heading("Appendix D: List of Papers Presented and Published", numbered=False)
R.p("The following paper on the topic of this report has been submitted by the project team:")
R.table("Research paper", ["Field", "Details"], [
    ["Title", D["paper_title"]],
    ["Authors", D["paper_authors"]],
    ["Conference", "AISIGH-SD 2026: International Conference on AI-Enabled Smart Solutions for Industry, "
                   "Governance, Healthcare and Sustainable Development, CUTM Bhubaneswar, 28-30 December 2026, "
                   "technical co-sponsor IEEE Bhubaneswar Section (accepted and presented papers are submitted to "
                   "IEEE Xplore)"],
    ["Submission", f"Microsoft CMT, 10 October 2026; Paper ID {D['paper_id']}"],
    ["Status", f"{D['paper_status']}; notification of acceptance due 15 November 2026"],
], [1.3, 4.5], label_prefix="D.1")
R.p("The proof of submission is attached as Annexure III. A reprint of the submitted paper follows.")
for n, page in enumerate(sorted((ROOT / "figures" / "paper_pages").glob("page*.png"),
                                key=lambda f: int(f.stem[4:])), 1):
    para = doc.add_paragraph()
    para.alignment = C
    para.paragraph_format.page_break_before = True
    para.paragraph_format.space_after = Pt(2)
    para.add_run().add_picture(str(page), width=Inches(5.75))
    R.p(f"Reprint of the submitted paper, page {n}", align=C, size=9, space_after=0)

# ------------------------------------------------------------------------------------------------ Annexures
for title, scan_prefix, what in [
    ("Annexure I: Topic Approval Form", "topic_approval",
     "Insert the scanned, signed topic approval form (Annexure A.2 of the capstone guidelines) here, signed by the "
     "project guide, the review-1 panel members and the HoD."),
    ("Annexure II: Weekly Log Book", "logbook",
     "Insert the scanned pages of the capstone log book here: the cover page with student details and grades, and "
     "every weekly entry with the work carried out, the faculty remark and the faculty mentor's signature with date."),
    ("Annexure III: Proof of Research Paper Submission", "paper_submission_proof",
     "Insert the proof of the paper's status here: the CMT submission confirmation e-mail or a screenshot of the "
     "AISIGH-SD 2026 author console showing the paper ID, title and status (Submitted / Accepted)."),
]:
    R.chapter_heading(title, numbered=False)
    pages = sorted(SCANS.glob(f"{scan_prefix}_p*.jpg"))
    email = SCANS / "cmt_confirmation.txt"
    if not pages and scan_prefix == "paper_submission_proof" and email.exists():
        R.p(f"Submission confirmation e-mail from Microsoft CMT for AISIGH-SD 2026, Paper ID {D['paper_id']}. The "
            "text below is reproduced from the e-mail received on 10 October 2026.", align=L)
        box = doc.add_table(rows=1, cols=1)
        box.style = "Table Grid"
        cell = box.rows[0].cells[0]
        cell.width = Inches(5.77)
        first = True
        for line in email.read_text().splitlines():
            para = cell.paragraphs[0] if first else cell.add_paragraph()
            first = False
            para.paragraph_format.line_spacing = 1.0
            para.paragraph_format.space_after = Pt(2)
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if len(line) > 120 else L
            key, sep, rest = line.partition(": ")
            if sep and len(key) < 30 and not line.startswith(" "):
                R.runs(para, f"**{key}:** {rest}", size=9.5)
            else:
                R.runs(para, line, size=9.5)
    elif not pages:
        R.p(f"«{what}»", align=WD_ALIGN_PARAGRAPH.CENTER)
    for n, page in enumerate(pages, 1):
        para = doc.add_paragraph()
        para.alignment = C
        para.paragraph_format.space_after = Pt(0)
        para.paragraph_format.page_break_before = n > 1
        # the first page shares its page with the annexure heading, so it is drawn a little smaller
        para.add_run().add_picture(str(page), height=Inches(7.6 if n == 1 else 8.15))

out_dir = ROOT / "output"
out_dir.mkdir(exist_ok=True)
rolls = "_".join(s["roll"] for s in STUDENTS)
name = f"{D['group_no']}_{rolls}_{D['file_title']}.docx"
name = re.sub(r"[«»]", "", name).replace("Group No.", "GroupNo").replace("Roll No.", "RollNo")
path = out_dir / name
R.save(path, update_fields_on_open="--word" not in sys.argv)
print(path)
print(f"{len(R.cites)} references cited")
