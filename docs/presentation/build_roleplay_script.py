"""Role-play opening scene (about 2 minutes): Markdown + Word. PDF via LibreOffice, run separately.

    python3 docs/presentation/build_roleplay_script.py

Cast: Akash = RBI-ObliBench, Karan = compliance head of a small finance bank, Meer = compliance officer of the group's
NBFC. The companies are fictional. The ₹65 lakh figure is a real RBI penalty on a small finance bank (Jan 2025, in our
enforcement data); the scene does not name the bank or claim a reason for it. Every project number is from our results.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).parent
MAROON, GREY = RGBColor(0x62, 0x24, 0x23), RGBColor(0x59, 0x59, 0x59)

CAST = [("Akash", "RBI-ObliBench (opens the presentation, walks in mid-scene)"),
        ("Karan", "Compliance head, Shubh Small Finance Bank"),
        ("Meer", "Compliance officer, Sahyog Finance (an NBFC in the same group)")]

STAGE = "Monday, 9:30 in the morning. Karan is staring at his phone. Meer walks in with two cups of chai."

LINES = [
    ("MEER", "", "Good morning! Why that face? Your chai's getting cold."),
    ("KARAN", "turns the phone towards her", "RBI press release. Monetary penalty on a small finance bank. Sixty-five lakh rupees."),
    ("MEER", "", "Not us, I hope?"),
    ("KARAN", "", "Not this time. But it got me thinking… last year we copied our outsourcing policy straight from your NBFC."),
    ("MEER", "shrugs", "Same group, same topic. The rules must be the same, no?"),
    ("KARAN", "", "That's what I thought. So yesterday I opened both Master Directions side by side. Same headings… but the details? "
              "Who approves it, what you report, by when. Not the same everywhere. And RBI has three hundred and eighty-one of these."),
    ("MEER", "", "Okay, so what do we do? Hire five more people just to read PDFs?"),
    ("KARAN", "half joking", "Or just ask ChatGPT?"),
    ("AKASH", "walking in", "Please don't. We actually tested that."),
    ("KARAN", "", "Akash! Perfect timing. Go on."),
    ("AKASH", "", "We took a hundred and six real cases and had an expert check each one. Seventy-eight of them had genuinely different "
              "rules. The AI systems missed fifty-six. And most of the time the right paragraph was sitting right there in front of them."),
    ("MEER", "", "Fifty-six out of seventy-eight? That's… worrying."),
    ("AKASH", "", "Exactly why we built RBI-ObliBench. Instead of letting the model just chat, our comparator pulls out thirteen specific "
              "things from each rule: who has to do it, what, how much, by when. Then a fixed rule decides if they really match. "
              "It caught twenty-six of those misses."),
    ("KARAN", "", "Fine, but I need something my team can open on a Monday morning. Like today."),
    ("AKASH", "", "That's the audit generator. You select ‘Small Finance Bank’, put in your last review date, compare with Meer's NBFC. "
              "In about thirty seconds you get every rule that applies to you, what's changed since your last review, your "
              "deadlines, where you're different from her, and past RBI penalties on banks like yours. Every line links back to the "
              "RBI document."),
    ("MEER", "", "And if I just have a quick question?"),
    ("AKASH", "", "Ask it. It only answers from RBI's own text, it shows you the source for every sentence, and if it can't back "
              "something up, it simply won't say it."),
    ("KARAN", "", "And who signs off at the end?"),
    ("AKASH", "", "You do. It's your assistant, not your lawyer."),
    ("MEER", "raising her chai", "So next Monday, we read our audit pack… not somebody else's penalty."),
    ("AKASH", "turns to the panel", "That's RBI-ObliBench. Let us show you how we built it."),
]

NOTES = [
    "When: right after the team slide (slide 2), as the opening scene. Akash's last line leads into slide 3 (Introduction).",
    "Timing: about 2 minutes at a normal talking pace. Speak like you normally talk; small pauses are fine. If short of time, "
    "skip Meer's “Okay, so what do we do? Hire five more people…” (Karan goes straight to “Or just ask ChatGPT?”) and "
    "Meer's “Fifty-six out of seventy-eight?”.",
    "Props (optional): a phone for Karan, cups for Meer. Keep the phone screen away from the panel.",
    "Facts: the ₹65 lakh figure is a real RBI penalty on a small finance bank (January 2025); do not name the bank or guess why "
    "it was fined. Every project number in the scene is from our results.",
    "In the live demo, Karan's question “how often do we update KYC for high-risk customers?” is a good first question to type.",
]


def markdown() -> str:
    o = ["# Role-play: “The ₹65 lakh Monday” (about 2 minutes)", "",
         "| Who | Plays |", "|---|---|"] + [f"| **{a}** | {b} |" for a, b in CAST] + ["", f"*{STAGE}*", ""]
    for who, how, line in LINES:
        o += [f"**{who.title()}**{f' *({how})*' if how else ''}: {line}", ""]
    o += ["---", ""] + [f"- {n}" for n in NOTES]
    return "\n".join(o) + "\n"


def word(path: Path) -> None:
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(1.8)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(12)
    p = doc.add_paragraph()
    r = p.add_run("RBI-ObliBench · Role-play: “The ₹65 lakh Monday”")
    r.bold, r.font.size, r.font.color.rgb, r.font.name = True, Pt(20), MAROON, "Times New Roman"
    p = doc.add_paragraph()
    r = p.add_run("Opening scene · about 2 minutes · Group 10")
    r.font.size, r.font.color.rgb = Pt(11), GREY
    t = doc.add_table(rows=1, cols=2)
    t.style = "Light Grid Accent 2"
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Who", "Plays"
    for a, b in CAST:
        c = t.add_row().cells
        c[0].text, c[1].text = a, b
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    r = p.add_run(STAGE)
    r.italic, r.font.color.rgb = True, GREY
    for who, how, line in LINES:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(7)
        r = p.add_run(who.title())
        r.bold, r.font.color.rgb, r.font.size = True, MAROON, Pt(12.5)
        if how:
            r = p.add_run(f"  ({how})")
            r.italic, r.font.color.rgb, r.font.size = True, GREY, Pt(10.5)
        p.add_run("\n" + line)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    r = p.add_run("Notes for the three of you")
    r.bold, r.font.color.rgb = True, MAROON
    for n in NOTES:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run("• " + n)
        r.font.size, r.font.color.rgb = Pt(10.5), GREY
    doc.save(str(path))


if __name__ == "__main__":
    (HERE / "ROLEPLAY_SCRIPT.md").write_text(markdown(), encoding="utf-8")
    word(HERE / "RBI-ObliBench_Roleplay_Script.docx")
    words = sum(len(re.findall(r"\S+", l)) for *_, l in LINES)
    print(f"role-play: {words} words, about {words / 150:.1f} min at 150 words/min")
