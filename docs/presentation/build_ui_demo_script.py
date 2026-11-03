"""UI demonstration script: every feature of the live site, exact inputs, and what proves it works (Markdown + Word).

    python3 docs/presentation/build_ui_demo_script.py

Inputs and expected outputs were tested on the live site on 30 Oct 2026 (see DEMO_RUNSHEET.md). ★ marks the 4-minute
path for the exam; the rest is the full tour for a longer demo or for the panel's questions.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).parent
SITE = "https://rbioblibench5qbvp2.z29.web.core.windows.net"
MAROON, GREY, GREEN = RGBColor(0x62, 0x24, 0x23), RGBColor(0x59, 0x59, 0x59), RGBColor(0x2E, 0x6B, 0x4F)

BEFORE = [
    f"Open {SITE}/auditgen 10 minutes before you present and wait for the green badge “live · hosted service” (the first "
    "visit can take about a minute while the server wakes up).",
    "Open /auditgen/ai and check “assistant ready · gemini-3.5-flash-lite”.",
    "Generate the demo pack once (Part C, step C1) so it is already in the Pack list as “(yours)”.",
    "Daily free limit for the whole site: 30 AI answers and 40 generated packs. The full tour below uses about 11 AI answers; "
    "do not rehearse the AI steps more than once on the day.",
    "Keep this tab order ready: Home · Cases case · Audit generator. Zoom the browser to 110–125% so the panel can read it.",
]

# (part, [(step id, star, page, do, input, say, proof)])
PARTS = [
    ("Part A · The benchmark (research site)", [
        ("A1", True, "/ (Home)", "The quiz at the top shows two RBI rules side by side. Ask the panel to guess, then click the answer.",
         "Click “Different requirement”.",
         "“These two rules look the same. They aren't. None of the five AI systems we tested noticed. That is the problem.”",
         "The page shows the expert's answer and what the AI systems said."),
        ("A2", True, "/case/t1_md_13006::p00135%7CUrban%20Co-operative%20Banks", "Open the Governance case (Audit Committee of the Board, Rural vs Urban co-operative banks).",
         "Paste the URL, or Cases → filters: Gold = Different, Missed by every LLM = yes (56) → this case.",
         "“Every LLM system says same. The expert says different. Only our structured comparator catches it, and you can see the 13 fields it compared.”",
         "Each system's verdict, the comparator's field table, the RBI paragraph ids and links to the official PDFs."),
        ("A3", False, "/cases", "Filter the 412 expert-labelled comparisons.", "Gold label = Different; Missed by every LLM = yes (56); Topic = Fraud Risk Management.",
         "“Every comparison is browsable and every filter is live.”", "The count updates; each card opens its case page."),
        ("A4", False, "/cases/failures", "Failure map of the 78 real differences.", "Sort = Recovered → missed by all → others.",
         "“56 differences no LLM caught; the comparator recovered 26; in 262 of 350 errors the right paragraph was already in context.”",
         "The three headline numbers at the top match slide 10."),
        ("A5", False, "/cases/play", "Interactive game: spot the difference.", "Click “Curated hard cases”, then answer one case.",
         "“A panel member can try it: same, different, or no matching rule.”", "After answering, the expert label and all system answers are shown."),
        ("A6", False, "/cases/atlas", "Which entity types have a Direction on which topic.", "Pick two classes in the two lists, e.g. Commercial Banks and Small Finance Banks.",
         "“11 entity types × 57 topics: where Directions exist, and where one class has none.”", "Filled cells = at least one Direction."),
        ("A7", False, "/lab", "The frozen comparator on a chosen pair (recorded run on the public site).",
         "Choose a pair in the list, e.g. “Credit Information Companies → Commercial Banks · Managing Risks in Outsourcing”.",
         "“Same frozen prompt and fixed rule as the sealed benchmark; the public site replays the recorded run, the key stays on the server.”",
         "The comparator's extracted fields and its verdict for the pair; the banner says it is a cached replay (honest by design)."),
        ("A8", False, "/triage", "How much could a team let the system handle.", "Drag the slider; click “High (≥ 0.85)”.",
         "“When the comparator says high confidence it was right 96% of the time on the test set.”", "Coverage and accuracy update as the slider moves."),
        ("A9", True, "/results", "Six results in plain language, each with a chart.",
         "Toggle “Institution filter OFF/ON”; in the T4 list pick “T4Q01 · Does a CIC need to have a Board-approved IT outsourcing policy…”.",
         "“The comparator finds 2× more real differences; copying the regulation fools the popular answer-quality score.”",
         "Charts change with the toggle and the question picker; numbers match slides 10–11."),
        ("A10", False, "/method and /genai", "How the benchmark was built; the ten generative-AI components.", "Scroll.",
         "“Every number on these pages is read from the published results file.”", "Hashes of the frozen prompt and rule are printed on /method."),
    ]),
    ("Part B · Research workspace (for questions on the results)", [
        ("B1", False, "/rq", "Research questions → tasks → findings.", "Click “trace →” under RQ2.", "“Each answer traces back to its evidence.”",
         "The RQ text is verbatim; findings carry their caveats (e.g. single-expert gold)."),
        ("B2", False, "/workspace/results", "Every metric with its 95% bootstrap interval.", "Tabs: T1 → Paired differences → Ablations → T3 → T4.",
         "“Every cell is a key in results_v2.json.”", "Hovering a cell shows its results key."),
        ("B3", False, "/different", "The ‘different’ failure explorer.", "Tick “Only units missed by every LLM system”; click a row.",
         "“For each miss: the 13-field comparator diff and its rule path.”", "The field heatmap shows which fields decide ‘different’."),
        ("B4", False, "/construction and /reliability", "From 381 Directions to 106 validated items; annotation agreement.", "Scroll.",
         "“Agreement is measured on a separate 30-item set with three raters; the gold itself is single-expert, and the site says so.”", "Counts 381 → 76,188 → 28,694 → 106."),
        ("B5", False, "/atlas and /architecture", "Corpus atlas; system map.", "Click any filled cell; click “Structured comparator”.",
         "“Click any component to see which systems use it and its measured effect.”", "Component → ablation → effect size."),
        ("B6", False, "/explorer", "Obligation Explorer (product view).", "Your class = Commercial Banks; Topic = Fraud Risk Management; compare with = Small Finance Banks (or any class the list offers).",
         "“What must my class do here, and what differs for another class.”", "Matched obligations with the comparator's verdict and evidence link."),
    ]),
    ("Part C · Audit generator (the product)", [
        ("C1", True, "/auditgen", "Generate an audit pack.",
         "Name: Shubh Small Finance Bank · Entity class: Small Finance Banks · As of: today · Last review: 01/12/2025 · "
         "Activities: Deposits, Lending, KYC / AML, Outsourcing, IT / cyber · Group entities: click Non-Banking Financial Companies · "
         "click “Generate audit pack” (15–30 s).",
         "“This is what a compliance team does on a Monday morning.”",
         "About 4,400 applicable obligations, ~150 flagged for human review, ~770 changes since 1 Dec 2025, ~250 calendar "
         "entries, ~6,700 differential rows vs NBFCs, 3 penalty releases. (Numbers move slightly with the date.)"),
        ("C2", True, "Audit pack → Register", "Applicability register.", "Type “outsourcing” in the filter; tick “show hidden rows” once, then untick.",
         "“Every obligation that applies, each citing its RBI paragraph, with its as-of status and deadline.”",
         "Click a source link: the official RBI PDF opens. Hidden rows are kept with their reason, never deleted."),
        ("C3", False, "Changes · Calendar", "What changed since the last review; due dates.", "Calendar → Month view → use › to move a month.",
         "“Amended or withdrawn since our last review; and what is due when.”", "Each change links to its amendment notification; entries marked “verify” are low-confidence by design."),
        ("C4", True, "Differential · Enforcement", "Where we differ from the NBFC; past penalties.", "Open both tabs.",
         "“Where our duty differs from our NBFC sister company, and RBI penalties on banks like us: ₹65 lakh, ₹6.70 lakh and ₹1 crore.”",
         "Differential rows carry a caution note (the research result); enforcement rows link to the RBI press releases."),
        ("C5", False, "Gaps · About", "Policy gap analysis; provenance.", "Switch Pack to “Sample Small Finance Bank” to show its gap run, then About.",
         "“Gap analysis matches a policy against every obligation; on the public site it runs on a synthetic policy, uploads stay in the installed version.”",
         "About shows the corpus snapshot date and sha256 hash, tool and rules versions."),
        ("C6", True, "Review", "Human review and sign-off.", "Switch back to your pack · Reviewer name: Karan · set one row to “confirmed” · type a note · then “Sign off”.",
         "“Nothing is settled until a named person confirms it; sign-off writes a new pack and keeps the original.”",
         "The progress bar moves; after a page reload the row is still confirmed (it is stored); the signed-off pack appears in the Pack list."),
        ("C7", False, "Downloads", "Five export formats.", "Click “Compliance calendar (.ics)” (≈15 s). Excel (≈1 min), Word, PDF and JSON work the same way.",
         "“Excel with filters and review columns, a Word and PDF report, a calendar file for Outlook / Google Calendar, and a JSON audit trail.”",
         "Open the .ics in Calendar and the .xlsx in Excel: the corpus hash and disclaimer are in every file."),
        ("C8", False, "Corpus status", "Snapshot age and refresh.", "Open the page.", "“Shows how fresh the RBI corpus is; the installed version can check rbi.org.in for updates.”",
         "Snapshot date and sha256 match the About tab."),
    ]),
    ("Part D · AI assistant (✦ AI assistant tab)", [
        ("D1", True, "Ask · All RBI obligations", "Ask any RBI question.", "How often must KYC be updated for high-risk customers?",
         "“Gemini answers only from the RBI paragraphs it retrieves, cites every sentence, and our NLI verifier checks each one.”",
         "Answer: at least once every two years. Each sentence has a source chip → official RBI PDF. “Show the 6 evidence paragraphs” lists what it read."),
        ("D2", True, "Ask · Small Finance Banks", "Show the verifier holding sentences back.", "What is the minimum capital a small finance bank must maintain?",
         "“Look: it states 15% of risk-weighted assets, and the sentences it could not confirm are held back. That is the trust feature.”",
         "Verified and unverified sentences are labelled; unverified ones are hidden by default."),
        ("D3", False, "Ask · Non-Banking Financial Companies", "Meer's NBFC question.", "What must an NBFC disclose to a borrower about the interest rate?",
         "“Same assistant, scoped to one entity type.”", "The annualised rate, the risk gradation and the reasons, in the application and the sanction letter."),
        ("D4", False, "Ask · All RBI obligations (spare)", "Spare questions for the panel.",
         "When must a fraud be reported to the RBI? · Who must approve the outsourcing policy? (scope: Small Finance Banks) · "
         "What must a bank do before outsourcing a financial service?",
         "", "All tested: verified, cited answers in 4–18 s."),
        ("D5", False, "Obligation copilot", "Explain one obligation; draft a policy clause; suggest a review status.",
         "Search “outsourcing” → pick a row → Explain · Company name: Shubh Small Finance Bank → Draft clause · Suggest → Reviewer name: Karan → “I agree: mark …”.",
         "“A plain-English explanation, a draft clause for our policy, and a review suggestion that changes nothing until a person accepts it.”",
         "Each output shows its verified sentences, the quoted evidence and a “check before deciding” note."),
        ("D6", False, "Changes explained", "Explain one change since the last review.", "Pick the first change → Explain change.",
         "“What the amendment changed, before and after, in plain words.”", "Before / after excerpts and the amendment link."),
        ("D7", False, "Memo & action plan", "Board memo and action plan from the pack's facts.", "Draft memo → Download DOCX · Build action plan.",
         "“A memo to the audit committee: every figure must appear in the pack's facts, or the sentence is flagged.”",
         "Tested: 5 sections, 16 of 16 sentences checked; action plan 20 of 20. “Show the facts given to the model” lists them."),
        ("D8", False, "Calendar check · Differential 2nd opinion", "Second checks on deadlines and on a difference.",
         "Calendar check → “Check the N ‘verify’ entries” · Differential → pick a pair → Second opinion.",
         "“The model re-reads uncertain deadlines and must quote the words it used; a second opinion on a flagged difference.”",
         "Agreement with the rule-based extractor is shown; quotes are checked against the paragraph."),
        ("D9", False, "How it works & log", "Transparency panel.", "Open the tab.",
         "“Which model, what goes in, how sentences are verified, and where outputs are stored.”", "Model id and verifier id are shown."),
    ]),
]

PROOF = [
    ("Citations are real", "Click any source chip or source link: it opens the official RBI PDF on rbi.org.in / rbidocs.rbi.org.in."),
    ("The verifier works", "Ask D2 (minimum capital): some sentences are held back as unverified. Click “Show the evidence paragraphs”."),
    ("Answers are grounded, not memorised", "Invite the panel to type their own question. If the corpus does not cover it, the assistant abstains instead of guessing."),
    ("It is live, not a recording", "Generate with the panel's choice of entity class and date; the numbers change with the inputs."),
    ("State is saved", "Confirm a row in Review, reload the page: it is still confirmed. Sign-off creates a new, separate pack."),
    ("Exports are real files", "Download the .ics or .xlsx and open it on the laptop."),
    ("Provenance", "About tab and every export carry the corpus snapshot date and sha256, the tool and rules versions."),
    ("Research claims are checkable", "Every number on /results and /workspace/results is a key in reports/results_v2.json; /method prints the prompt and rule hashes."),
]

FALLBACK = [
    ("“connecting to the hosted service…” for over a minute", "Reload once. If it persists, switch the Pack list to a sample pack: everything except Generate and new AI answers keeps working."),
    ("“today's limit”", "The daily free quota is used up; show a sample pack's recorded AI answers (Pack → Sample Small Finance Bank → AI assistant)."),
    ("An answer says it cannot answer reliably", "That is the verifier doing its job; say so and ask the next question."),
    ("No internet", "Run locally: python3 scripts/auditgen.py serve and cd ui && npm run dev, then open localhost:5181/auditgen (local Qwen model)."),
]


def markdown() -> str:
    o = ["# RBI-ObliBench: UI demonstration script", "",
         f"Site: **{SITE}** · ★ = the 4-minute exam path (A1 → A2 → A9 → C1 → C2 → C4 → C6 → D1 → D2). "
         "Everything else is the full tour. Inputs were tested on the live site on 30 Oct 2026.", "", "## Before you start", ""]
    o += [f"- {b}" for b in BEFORE]
    for part, steps in PARTS:
        o += ["", f"## {part}", ""]
        for sid, star, page, do, inp, say, proof in steps:
            o += [f"### {'★ ' if star else ''}{sid} · {page}", "", f"- **Do:** {do}", f"- **Input:** {inp}"]
            if say:
                o.append(f"- **Say:** {say}")
            o += [f"- **Proof it works:** {proof}", ""]
    o += ["## How to prove to the panel that it works", ""] + [f"- **{a}:** {b}" for a, b in PROOF]
    o += ["", "## If something goes wrong", ""] + [f"- **{a}:** {b}" for a, b in FALLBACK]
    return "\n".join(o) + "\n"


def word(path: Path) -> None:
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2)
        s.top_margin = s.bottom_margin = Cm(1.7)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    def p(text="", *, size=11, color=None, bold=False, italic=False, after=4, indent=0.0, before=0):
        para = doc.add_paragraph()
        para.paragraph_format.space_after = Pt(after)
        para.paragraph_format.space_before = Pt(before)
        para.paragraph_format.left_indent = Cm(indent)
        if text:
            r = para.add_run(text)
            r.font.size, r.bold, r.italic = Pt(size), bold, italic
            if color:
                r.font.color.rgb = color
        return para

    def labelled(label, text, color=MAROON):
        para = p(after=2, indent=0.4)
        r = para.add_run(label + "  ")
        r.bold, r.font.color.rgb, r.font.size = True, color, Pt(10.5)
        r = para.add_run(text)
        r.font.size = Pt(10.5)

    h = p("RBI-ObliBench · UI demonstration script", size=21, color=MAROON, bold=True, after=2)
    h.runs[0].font.name = "Times New Roman"
    p(f"Site: {SITE}   ·   ★ = 4-minute exam path: A1 → A2 → A9 → C1 → C2 → C4 → C6 → D1 → D2   ·   tested live 30 Oct 2026",
      size=9.5, color=GREY, after=8)
    p("Before you start", size=14, color=MAROON, bold=True, after=3)
    for b in BEFORE:
        p("• " + b, size=10.5, after=2, indent=0.3)
    for part, steps in PARTS:
        hp = p(part, size=15, color=MAROON, bold=True, after=4, before=12)
        hp.paragraph_format.keep_with_next = True
        for sid, star, page, do, inp, say, proof in steps:
            sp = p(after=2, before=6)
            sp.paragraph_format.keep_with_next = True
            r = sp.add_run(("★ " if star else "") + f"{sid} · {page}")
            r.bold, r.font.size = True, Pt(12)
            r.font.color.rgb = MAROON if star else RGBColor(0x26, 0x26, 0x26)
            labelled("Do", do)
            labelled("Input", inp)
            if say:
                labelled("Say", say)
            labelled("Proof", proof, GREEN)
    p("How to prove to the panel that it works", size=15, color=MAROON, bold=True, after=4, before=14)
    for a, b in PROOF:
        labelled(a + ":", b, GREEN)
    p("If something goes wrong", size=15, color=MAROON, bold=True, after=4, before=14)
    for a, b in FALLBACK:
        labelled(a + ":", b)
    doc.save(str(path))


if __name__ == "__main__":
    (HERE / "UI_DEMO_SCRIPT.md").write_text(markdown(), encoding="utf-8")
    word(HERE / "RBI-ObliBench_UI_Demo_Script.docx")
    print("written:", sum(len(s) for _, s in PARTS), "steps,", sum(1 for _, s in PARTS for x in s if x[1]), "on the exam path")
