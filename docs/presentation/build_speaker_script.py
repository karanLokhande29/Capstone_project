"""Speaker script for the 16-slide final presentation: Markdown + Word (+ PDF via LibreOffice, run separately).

    python3 docs/presentation/build_speaker_script.py

Numbers come from the deck (build_deck_15.py) and its sources (reports/p4001_system_and_ablations.md, results_v2.json,
the sprint extension reports). Speaker split: Akash opens, Meer takes the method, Karan the product, results and demo.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).parent
MAROON, GREY = RGBColor(0x62, 0x24, 0x23), RGBColor(0x59, 0x59, 0x59)

PLAN = [("Akash", "Slides 1–2, role-play, slides 3–5", "about 4 min 45 s (role-play 2 min included)"),
        ("Meer", "Slides 6–8, then slides 14–16 (close)", "about 4 min"),
        ("Karan", "Slides 9–12, live demo, slide 13", "about 6 min 30 s (demo 3 min 30 s included)")]

# (slide, title, speaker, seconds, lines, cue)
SLIDES = [
    (1, "Title", "Akash", 15,
     ["Good morning, respected panel. We are Group 10 from the Department of Artificial Intelligence, MPSTME, presenting "
      "our capstone project: “Same Subject, Different Duties: RBI-ObliBench for Differential Obligations across Entity Classes”."],
     None),
    (2, "Team", "Akash", 15,
     ["I am Akash Goyal, with Karan Lokhande and Meer Magia. Our mentor is Prof. Jish Elizabeth Joy, and our paper's "
      "co-author is Dr. Hima Deepthi Vankayalapati.",
      "Before the slides, let us show you the problem the way a compliance team actually meets it."],
     "ROLE-PLAY “The ₹65 lakh Monday” (about 2 min): Karan and Meer start the scene, Akash walks in; his last line leads into slide 3."),
    (3, "Introduction: one subject, many Master Directions", "Akash", 40,
     ["The Reserve Bank of India writes a separate Master Direction for each kind of regulated entity: commercial banks, "
      "small finance banks, NBFCs, co-operative banks and others.",
      "So one subject, say a board-approved outsourcing policy, appears in several near-parallel Directions. Usually the "
      "duty is the same. Sometimes the approving body, the threshold, the scope or the deadline quietly changes, or there "
      "is no counterpart at all.",
      "We harvested 381 Master Directions, split them into 76,188 paragraphs with stable ids, and tagged them across 11 "
      "regulated-entity classes. Telling same from different, class by class, is exactly what our benchmark asks a system to do."],
     None),
    (4, "Literature review and problem statement", "Akash", 50,
     ["Regulatory question answering so far treats a regulation as one rulebook. ObliQA and RIRAG set up retrieve-then-answer "
      "on financial regulation and introduced the RePASs metric; AUEB-Archimedes showed that RePASs rewards simply "
      "concatenating obligations; IndiaFinBench is the closest Indian benchmark, but it tests single documents.",
      "None of them compares obligations across entity classes. That gap is our problem statement: for an obligation in one "
      "class's Master Direction, decide for every other class whether a counterpart exists and whether it is the same or a "
      "different duty; retrieve that counterpart; tell whether a paragraph is in force on a date; and test whether the "
      "faithfulness metric can be gamed on Indian regulatory text.",
      "That gives four tasks: T1 applicability and differential, with 106 expert-validated items and 412 class judgements; "
      "T2 counterpart retrieval; T3 temporal status; and T4, an audit of the RePASs metric."],
     None),
    (5, "Methodology: overall block diagram", "Akash", 40,
     ["We built the project in three stages, each validated before the next.",
      "One, data collection: harvest the Directions, extract text with pdfplumber, segment the paragraphs and tag each by "
      "entity class and subject family.",
      "Two, benchmark construction: extract 28,694 obligation candidates, match them across classes with bge embeddings "
      "plus lexical features, have experts label the 106-item T1 gold, and build the T2, T3 and T4 sets.",
      "Three, evaluation and outputs: run the retrieval and LLM systems, compare them with a paired bootstrap, and deliver the "
      "paper, a pointer-only data release, the website and the audit generator.",
      "Meer will take you through how we evaluate."],
     "HAND-OVER: Akash → Meer"),
    (6, "Methodology: evaluation flowchart", "Meer", 45,
     ["Every system shares one pipeline. The input is an obligation, a target class and a date. Hybrid retrieval combines "
      "BM25 and bge with reciprocal rank fusion. Two filters can switch on: A, keep only the target class; B, keep only "
      "paragraphs in force on the date. Then the LLM judge says same, different or none.",
      "In the final agentic system an NLI verifier checks the judge's rationale: if it is not entailed, the system retries "
      "once and then abstains. Rule v3.6 turns the per-class answers into an item flag.",
      "Two alternatives sit beside it: a long-context system that reads whole Directions with no retrieval, and our "
      "structured comparator. Everything runs on gemini-3.5-flash-lite at temperature 0, with frozen, hashed prompts, and "
      "every prediction was sealed before scoring."],
     None),
    (7, "Implementation algorithm: structured comparator", "Meer", 50,
     ["Our main algorithmic idea: let the model extract, and let a fixed rule decide.",
      "For the source obligation and each candidate, the model fills 13 fields: actor, action, object, scope, condition, "
      "threshold, amount, percentage, frequency, deadline, exception, documentation and reporting. If the candidate does "
      "not address the same duty, the answer is none. If it does, and any field differs, or a material field is present on "
      "one side only, the answer is different; otherwise same.",
      "Against the class-aware LLM, ‘different’ F1 rises from 0.154 to 0.409, and recall by 0.397. It recovers 26 of the "
      "56 differences that every LLM system missed. And honestly, it still misses 40 of 78. It was developed only on a "
      "separate 30-item set and frozen by hash before we touched the gold."],
     None),
    (8, "Implementation: LLM systems, tools and technology", "Meer", 45,
     ["These are the five LLM systems we compare, all on the same model and the same frozen prompts. Only what each system "
      "sees and checks changes.",
      "Class-blind retrieves across every class: 3-way F1 0.602. Class-aware adds the class filter: 0.551. Final agentic adds "
      "the temporal filter and the verifier, so it abstains more: 0.483. Long-context reads whole Directions: 0.509. The "
      "structured comparator scores best on both, 0.616, and 0.409 on ‘different’.",
      "Underneath is our stack: Python and pdfplumber for the corpus, BM25S plus bge for retrieval, NumPy and SciPy with a "
      "2,000-resample bootstrap for statistics, React and FastAPI for the apps, and Azure for the public demo.",
      "Karan will now show what this becomes for a real compliance team."],
     "HAND-OVER: Meer → Karan"),
    (9, "Use case diagram and deployment", "Karan", 40,
     ["We applied the pipeline to a compliance team's routine work: the audit generator. A compliance officer enters the "
      "entity's profile and gets an audit pack: an applicability register, a change log, a compliance calendar, a cross-class "
      "differential and the enforcement context, with every row citing its RBI paragraph. A reviewer confirms rows and signs "
      "off, and everything exports to Excel, Word, PDF, a calendar file and a JSON audit trail.",
      "On the right is the deployment you will see live: a static website on Azure, an Azure Function that generates packs, "
      "Gemini on the free tier writing AI drafts, and our ONNX bge and NLI models retrieving evidence and checking every "
      "sentence. The installed version runs the same code inside the bank's own network with a local Qwen model, so uploaded "
      "policies never leave it."],
     None),
    (10, "The product: key features", "Karan", 30,
     ["Here is what you will see in the demo, in six screenshots. The home page opens with a real case that none of the five "
      "AI systems got right. A case page shows every LLM saying same, the expert saying different, and only our comparator "
      "catching it.",
      "The audit generator builds a full audit pack in about thirty seconds, with past RBI penalties for context; the AI "
      "assistant cites every sentence and holds back what it cannot verify; and the board memo only states figures that "
      "are in the pack's own facts."],
     None),
    (11, "Result analysis: RQ1 and RQ2", "Karan", 50,
     ["RQ1: does knowing the entity class help? For retrieval, yes: the class filter lifts counterpart nDCG@10 by 0.451, "
      "from 0.443 to 0.894. But for the T1 judgement, it makes no significant difference: minus 0.050, with a confidence "
      "interval that includes zero.",
      "RQ2: can LLMs spot the differences? Not yet. 56 of the 78 gold ‘different’ units were missed by every LLM system, "
      "and 262 of the 350 ‘different’ errors happened with the counterpart already in the model's context. So the failure "
      "is reasoning, not retrieval. No LLM system significantly beats the embedding baseline on collapsed F1."],
     None),
    (12, "Result analysis: RQ3, RePASs rewards copying", "Karan", 40,
     ["RQ3: is the standard faithfulness metric trustworthy here? No. On 30 T4 questions, simply concatenating the "
      "retrieved obligation sentences scores 0.746 against 0.371 for a genuine answer: plus 0.375, and this was "
      "pre-registered.",
      "RePASs tracks human faithfulness ratings well, rho 0.731, but not whether the answer addresses the question, rho "
      "0.008. A faithfulness metric needs a relevance term that copied text cannot satisfy.",
      "Now let us show you the system live."],
     "LIVE DEMO (3 min 30 s): Karan drives, following the demo run-sheet. Suggested order: the Governance case → Generate "
     "(Shubh Small Finance Bank vs NBFCs) → Register / Differential / Enforcement → Review → Ask: KYC question, then the "
     "capital question (point out the held-back sentences). Then return to slide 13."),
    (13, "Result analysis: additional experiments", "Karan", 40,
     ["Back to the slides for four robustness checks, all pre-registered.",
      "A cross-encoder reranker made things worse: class-blind 3-way F1 down 0.064. A bigger open model, gpt-oss-120b, scored "
      "0.614 against Gemini's 0.624, no significant change, and did no better on ‘different’. So model scale alone does not "
      "fix the core failure.",
      "On the external IndiaFinBench benchmark our frozen answer step reached 0.757 overall, strongest on regulatory "
      "interpretation at 0.951 and weakest on numerical reasoning at 0.561. And a LangGraph port reproduced every prompt and "
      "output exactly across four systems.",
      "Meer will close."],
     "HAND-OVER: Karan → Meer"),
    (14, "Conclusion and future scope", "Meer", 45,
     ["To conclude: retrieval accuracy alone does not measure cross-class obligation reasoning.",
      "RQ1: the class filter helps retrieval, not judgement. RQ2: free-form LLMs miss most real differences; our structured "
      "comparator is a step forward, recovering 26 of 56. RQ3: RePASs is gameable by copying.",
      "Next, in order of urgency: independent second raters for stronger labels; frontier models rerun on T1 and the "
      "comparator; a comparator that uses retrieved evidence with better topic matching; larger T3 and T4 studies with a "
      "working RePASs repair; and a real pilot of the audit generator with a compliance team."],
     None),
    (15, "Paper status and SDG mapping", "Meer", 40,
     ["Our paper, with the same title, was submitted on 10 October 2026 through Microsoft CMT to AISIGH-SD 2026, IEEE "
      "Bhubaneswar Section, Paper ID 1954. It is under review; the decision is due on 15 November, and the CMT confirmation "
      "is in Annexure III of the report. Accepted papers go to IEEE Xplore.",
      "The project maps to three SDGs: 16, strong and transparent institutions, because every audit row cites its RBI "
      "source and a human signs off; 8, decent work and growth, by helping banks, NBFCs and co-operative banks see which "
      "duties bind them; and 9, innovation, through an open benchmark, tested code and a pointer-only data release."],
     None),
    (16, "References and thank you", "Meer", 10,
     ["These are our key references; the full list of 44 is in the report. Thank you. We are happy to take your questions, "
      "and the live site is open if you would like to see anything again."],
     "Q&A (5 min): all three answer; see the Q&A prep at the end."),
]

QA = [("Isn't the comparator just tuned to your test set?",
       "No. It was developed only on a separate 30-item set, had one bug-fix revision, and was frozen by hash before we "
       "touched the 106-item gold. The comparisons against it were pre-registered."),
      ("Why gemini-3.5-flash-lite and not a bigger model?",
       "One free-tier model for every system keeps the comparison fair. We also reran T1 with gpt-oss-120b, a much larger "
       "open model: no significant change, and no better on ‘different’."),
      ("Why only 106 items?",
       "Each item needs an expert to judge every compared class, which gave 412 class judgements. We report every result "
       "with a paired bootstrap confidence interval, so the uncertainty is visible, and stronger labels are first on our future-scope list."),
      ("Is this legal advice? Can a bank rely on it?",
       "No. It is decision support. Every row cites its RBI paragraph, rows that need judgement are flagged, and nothing is "
       "settled until a named reviewer confirms it and signs off."),
      ("What about confidential company documents?",
       "Policy uploads run only in the installed version, inside the bank's network. The public demo sends only RBI text and "
       "the user's question to Gemini, and says so on the page."),
      ("Why are RBI quotes cut to 12 words on the site?",
       "Redistribution of the RBI text is an open IPR question, so the public site shows short quotes and links every row to "
       "the official RBI PDF."),
      ("What are the main limitations?",
       "The comparator still misses 40 of 78 differences; the enforcement links are Direction-level weak labels (53.3% clean "
       "on a 30-item check); and the temporal set is small, 52 items."),
      ("What did this cost to run?",
       "Nothing beyond free tiers: Gemini and Groq free tiers for the experiments, Kaggle for embeddings, and a student Azure "
       "subscription for the public site, with daily caps so it cannot exceed the free allowance.")]


def markdown() -> str:
    out = ["# RBI-ObliBench: speaker script (15 minutes)", "",
           "Final presentation, Group 10. Total: about 15 minutes (slides about 9.5 min, role-play 2 min, live demo 3 min 30 s), "
           "then 5 minutes of Q&A. Speak at a calm pace; each slide's time is a target, not a limit.", "",
           "| Speaker | Takes | Time |", "|---|---|---|"]
    out += [f"| **{a}** | {b} | {c} |" for a, b, c in PLAN]
    for n, title, who, secs, lines, cue in SLIDES:
        out += ["", f"## Slide {n} · {title}", f"**{who}** · about {secs} s", ""]
        out += [line + "\n" for line in lines]
        if cue:
            out += [f"> **{cue}**", ""]
    out += ["", "## Q&A prep", ""]
    for q, a in QA:
        out += [f"**Q: {q}**", "", a, ""]
    return "\n".join(out).rstrip() + "\n"


def word(path: Path) -> None:
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(1.8)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(12)

    def para(text, *, size=12, color=None, bold=False, italic=False, after=6, indent=0.0):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.left_indent = Cm(indent)
        r = p.add_run(text)
        r.font.size, r.bold, r.italic = Pt(size), bold, italic
        if color:
            r.font.color.rgb = color
        return p

    p = para("RBI-ObliBench · Speaker script", size=22, color=MAROON, bold=True, after=2)
    p.runs[0].font.name = "Times New Roman"
    para("Final presentation, Group 10 · about 15 minutes (slides ~9.5 min, role-play 2 min, live demo 3 min 30 s) + 5 min Q&A",
         size=10.5, color=GREY, after=8)
    t = doc.add_table(rows=1, cols=3)
    t.style = "Light Grid Accent 2"
    for c, h in zip(t.rows[0].cells, ("Speaker", "Takes", "Time")):
        c.text = h
    for row in PLAN:
        cells = t.add_row().cells
        for c, v in zip(cells, row):
            c.text = v
    for n, title, who, secs, lines, cue in SLIDES:
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(14)
        h.paragraph_format.space_after = Pt(3)
        h.paragraph_format.keep_with_next = True
        r = h.add_run(f"Slide {n} · {title}")
        r.bold, r.font.size, r.font.color.rgb = True, Pt(14), MAROON
        r = h.add_run(f"     {who} · about {secs} s")
        r.italic, r.font.size, r.font.color.rgb = True, Pt(10.5), GREY
        for line in lines:
            para(line, after=5, indent=0.3)
        if cue:
            para(cue, size=10.5, color=MAROON, bold=True, after=4, indent=0.3)
    h = para("Q&A prep", size=14, color=MAROON, bold=True, after=4)
    h.paragraph_format.space_before = Pt(16)
    for q, a in QA:
        para("Q: " + q, bold=True, after=1, indent=0.3)
        para(a, size=11.5, after=7, indent=0.3)
    doc.save(str(path))


if __name__ == "__main__":
    (HERE / "SPEAKER_SCRIPT.md").write_text(markdown(), encoding="utf-8")
    word(HERE / "RBI-ObliBench_Speaker_Script.docx")
    words = sum(len(" ".join(lines).split()) for *_, lines, _ in [(s[0], s[1], s[2], s[3], s[4], s[5]) for s in SLIDES])
    secs = sum(s[3] for s in SLIDES)
    print(f"script: {words} spoken words over {secs} s of slides ({words / (secs / 60):.0f} words/min); files written")
