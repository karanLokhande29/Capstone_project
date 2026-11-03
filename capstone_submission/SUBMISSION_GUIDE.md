# Capstone report: submission guide

Built from *Guidelines_Capstone Project_BTech/MBA Tech 24-25* (Annexures A.2, A.7 and A.8) and the coordinator's note.

## What is in this folder

| File | What it is |
|---|---|
| `output/<Group>_<RollNos>_RBI-ObliBench ….docx` | The report (53 pages), in the A.8 format: title page and certificate with the NMIMS logo, acknowledgement with the team table, abstract, contents, list of figures, list of tables, abbreviations, Chapters 1–6, 34 references, Appendices A–D, and Annexures I–III where the scans go. Edit this file in Word. |
| `output/… .pdf` | The same report as a PDF, to check the layout. |
| `output/Topic_Approval_Form_prefilled.docx / .pdf` | A pre-filled copy of the A.2 topic approval form. Use it only if you need a fresh copy. If you already have the form signed at Review 1, scan that one instead. |
| `build/details.json` | Group number, roll numbers, SAP IDs, program, stream, mentor's designation, department, HoD name and paper ID. |
| `build/` | Scripts that rebuild everything from `details.json`. |
| `figures/` | The NMIMS logo and every figure in the report. |
| `paper/RBI-ObliBench_AISIGH-SD2026_submitted.pdf` | The paper as submitted on 10 Oct 2026. Appendix D reprints its six pages. |

Everything highlighted in **yellow** in the report is a placeholder that still needs a value.

## Step 1: fill in the missing details

Fill in `build/details.json`, then rebuild (Word fills in the page numbers in the table of contents automatically):

```bash
PY=python3 capstone_submission/build/render.sh
```

The render script needs `python-docx`, `matplotlib` and `pillow` (`python3 -m pip install python-docx matplotlib pillow`) and Microsoft Word. Alternatively, open the .docx in Word and replace the yellow text by hand, then right-click the table of contents → **Update Field → Update entire table**, and do the same for the List of Figures and the List of Tables.

Filled in from the official MPSTME website (engineering.nmims.edu, checked 28 Oct 2026):
- **Program:** Bachelor of Technology (B.Tech.) in Artificial Intelligence.
- **Mentor:** Prof. Jish Elizabeth Joy, Assistant Professor, Department of Artificial Intelligence. Her profile lists the Ph.D. as "pursuing", so the title is "Prof.", not "Dr."
- **HoD:** Dr. Vaishali Kulkarni, Professor and HOD, Department of Artificial Intelligence.
- **Co-author:** Dr. Hima Deepthi Vankayalapati, Professor, Department of Artificial Intelligence.

Left blank for you to fill in by hand: the SAP IDs (title-page team table, topic forms) and the CMT paper ID (Appendix D).

Check these before printing:
- **Academic year** is set to **2026-27** in the header and on the title page. Confirm it with your coordinator.
- **Minimum page count**: the guideline leaves this number blank (A.8, Chapter 1 note 3). Ask the coordinator. The report is currently 53 pages before the scans.

## Step 2: get the signatures (Jish Joy and others)

Get these signatures in person from **Jish Joy** at MPSTME. Email (Jish.Joy@nmims.edu) to book a slot, and take the printed pages with you.

| # | Where | Who signs | When |
|---|---|---|---|
| 1 | **Certificate page** of the report: the line "Project Mentor (Internal Guide)", with the date | **Jish Joy** | Before binding, on **both** copies. Guideline 16 says the report must be verified and signed by the mentor before the final presentation. Give the mentor the draft to review first. |
| 2 | **Log book**: every weekly page, in "Faculty Remark" and "Faculty Signature with date" | **Jish Joy** | Every week that is still unsigned. Get them all done before scanning. |
| 3 | **Log book cover page**: the "Grades (By Faculty Mentor)" column | **Jish Joy** | Before the final submission. |
| 4 | **Topic approval form**: "Name and Signature of the guide" | **Jish Joy** | Usually done at Review 1. If yours is missing, use the pre-filled form. |
| 5 | Certificate: "Head of Department (HoD)" | **HoD** | After the mentor signs, before binding. |
| 6 | Topic approval form: "Signature of HoD", and the Review-1 panel members | HoD, Review-1 panel | Usually already done at Review 1. |
| 7 | Certificate: "Examiner" | External examiner | **Leave blank.** The examiner signs at the final viva. |
| 8 | Acknowledgement page: the "Signature" column of the team table | Karan, Akash, Meer | Before binding. |

## Step 3: scan and insert the annexures

Replace each yellow placeholder page with the scans. In Word, use Insert → Pictures, one scan per page.

1. **Annexure I**: the signed topic approval form (both pages).
2. **Annexure II**: the log book. Include the cover page with student details and grades, and every weekly page.
3. **Annexure III**: proof of the paper's status. Today (28 Oct 2026) the status is *submitted*, so use one of:
   - a screenshot of the CMT author console (https://cmt3.research.microsoft.com/AISIGHSD2026) showing the paper ID, the title and the status; or
   - the CMT "submission received" confirmation email.

   AISIGH-SD 2026 sends acceptance notifications on **15 Nov 2026**. If yours arrives before you print, attach the acceptance email instead. Then set `paper_status` in `details.json` to "Accepted" and rebuild.

Scan at 300 dpi. A phone scanner app works if the pages are flat and the scans are straight.

## Step 4: final files

- **File name:** `GroupNumber_RollNos_ProjectTitle`. Yours is `10_I025_I039_I040_RBI-ObliBench Entity-Class Applicability and Differential Obligations.docx`.
- **Hard copies:** two copies, hard-bound in a black cover (the "black book").
- **Log book:** hand the original in at the final presentation as well.

### Binding order

1. Title page
2. Certificate (signed)
3. Acknowledgement (with student signatures)
4. Abstract
5. Table of Contents, List of Figures, List of Tables, Abbreviations
6. Chapters 1–6
7. References
8. Appendices A–D
9. Annexure I: Topic approval form
10. Annexure II: Weekly log book
11. Annexure III: Proof of paper submission

## Before you print: read these

- **Rewrite the text in your own words.** Claude drafted the report from the project's paper, master document and code, and says so in Section 3.12. NMIMS may run a similarity or AI-content check. AISIGH-SD's camera-ready rule (AI-generated content under 20%) applies to the paper. Read every chapter, change the wording, and add details that only your team knows: who did what, review feedback, problems you hit.
- **The numbers are traceable.** Every result in Chapters 3–4 and Appendix B is copied from `reports/final/RBI-ObliBench_Master_Document_v2.md` (`results_v2.json`). Do not change them by hand.
- **References:** entries [1]–[34] are in IEEE style. 20 of them come from the paper's verified bibliography. The 14 standard papers added for the survey chapter (BERT, RAG, DPR, LexGLUE, nDCG and others) are well known, but check them once.
