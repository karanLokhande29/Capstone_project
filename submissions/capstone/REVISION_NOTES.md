# Report revision notes (28 Oct 2026)

Revised: the acknowledgement, the abstract and the prose of Chapters 1–6. Not changed: tables, figures, captions, headings, references, the appendices and the annexures.

## Mechanical checks (run on the builder source, old vs new)

| Check | Result |
|---|---|
| All 26 table and figure calls in the front matter and Chapters 1–6 | Byte-identical |
| Set of citation keys | Identical (34 references, all still cited) |
| Numbers in the prose | Unchanged. The only token differences are punctuation ("shared 52," became "shared (52)"; "top-2" became "top two") and new section numbers in cross-references. |
| RQ1–RQ3 wording, T1–T4 definitions, thresholds, hashes, model names | Unchanged |

## What changed, by chapter

- **Abstract / acknowledgement:** reworded. The acknowledgement now names the HoD.
- **Ch. 1:** the generic opening was replaced with the actual problem. The sentences in 1.1 and 1.2 are rewritten, and the contribution bullets are tightened.
- **Ch. 2:** each study is now described by what it contributes and how this project uses it. "Does not compare across classes" is no longer repeated for every paper; the gap is stated once, in 2.4, and mapped to RQ2, RQ1 and RQ3. There is a new lead-in sentence for Table 2.1.
- **Ch. 3:** describes what was implemented, in pipeline order. The single-expert gold is kept separate from the reliability evidence. A sentence pointing to Tables 3.1–3.2 was added.
- **Ch. 4:** hedged where the evidence calls for it ("suggests", "our reading is", "most of these errors"). One negative result that was only in Table 4.6 is now stated in the text: the comparator does not improve collapsed flag F1. The discussion lists the six findings and adds that the comparator still misses 40 of the 78 *different* units (from Table 4.5).
- **Ch. 5:** every advantage now points to the section that supports it, and the limitations are stated explicitly.
- **Ch. 6:** the conclusion answers RQ1, RQ2 and RQ3 one by one, with no new findings.

## Please confirm (author review)

1. **Section 3.4 cross-reference corrected:** precision rounds are reported in **Section 4.2**. The old text said 4.3.
2. **Section 3.12 now also says that Claude was used to draft and edit the text of this report.** This is accurate disclosure; keep it unless your department's rules say otherwise.
3. **Section 4.5.1** now says that *most* *different* errors are reasoning failures (262 of 350), not that all of them are.
4. **Section 4.4** says the class-blind retriever loses "more than half of the achievable nDCG *on this set*" (0.421 vs 0.894 on t2_xclass_t1).
5. **Acknowledgement:** uses "her" for Prof. Jish Elizabeth Joy and names Dr. Vaishali Kulkarni as HoD.

## About the AI-writing score

These revisions are still AI-written, so no particular Turnitin score is guaranteed. The most reliable way to make the report your own is to rewrite paragraphs in your own words and add what only your team knows: who did which phase, what the reviewers asked you to change, and what went wrong and how you fixed it. Keep the disclosure in Section 3.12.

## Mentor's changes (28 Oct 2026)

| Request | Done |
|---|---|
| RQ or RO? | Kept **research questions**: the work is an empirical evaluation and every Chapter 4 result answers a question with measured evidence. Section 1.3 now says so, and points to the project objectives in the topic approval form (Annexure I). |
| Chapter 2 summary punctuation | "Summary." changed to "Summary:" in every chapter, for consistency. |
| Remove Section 3.13 | Removed the project schedule and its Gantt chart; the List of Figures updates automatically. |
| Future Scope | The table is replaced by one paragraph (Section 6.2). |
| Appendix C | Renamed to "Appendix C: Software Component List". |
| Mentor name underline (page 1) | Removed. |
| Italics | Label words are now in single quotes ('different', 'same', 'none', etc.), and the other emphasis italics are removed. Italics remain only for maths variables in the algorithms (o, c, t, s, c1, c2) and for journal and proceedings names in the references, as IEEE style requires. The page header is no longer italic. |
| Problem statement bold | Removed. |
| AI ethics | New paragraph in 2.1 citing Jobin et al., Floridi and Cowls, IEEE Ethically Aligned Design, Bender et al., model cards, datasheets and the RBI FREE-AI report. New Section 3.11.2 maps IEEE 7000-2021, 7001-2021, 7002-2022 and 7003-2024 to what the project actually does, and states that no formal conformity assessment was carried out. References now run to 44. |
| References | Left-aligned, so long URLs no longer stretch the lines. |

## Second rewrite pass after the Turnitin report (41%), 28 Oct 2026

Turnitin flagged the 1.5 summary, 3.9–3.12, 4.9–4.11 and Chapter 5 most heavily (84–98% of their words). In this pass:
- Rewrote those sections and the other flagged paragraphs in a plainer first-person-plural voice, with varied sentence length.
- Turned the bulleted standards (3.11.1, 3.11.2) and all of Chapter 5 into prose.
- Kept every number, citation, table, figure, heading and the Section 3.12 AI disclosure. Re-checked mechanically: tables and figures are byte-identical and the citation set is unchanged.
- Added real project details from the repository history. **Please confirm them:**
  - **3.1 Phase 1 split.** Akash: corpus acquisition, extraction and segmentation. Karan: metadata and the entity class × subject family matrix. Meer: corpus QA, annotation protocol and the three-rater pilot. Taken from the Phase 1 commit messages.
  - **3.3 Early problems.** The first harvest missed 81 Directions. The Kaggle notebook was running stale code from an earlier session (commit "Fix notebook silently running stale code across Kaggle sessions"), and was fixed.

No particular Turnitin score is guaranteed. Adding your own wording and details on top will help most.

## Third pass after Turnitin 39%, 28 Oct 2026

- List-like content moved into 7 new tables:
  - Table 1.1: report organisation
  - Table 3.4: audit-pack contents
  - Table 3.5: software standards
  - Table 3.6: IEEE ethical AI standards
  - Tables 5.1–5.3: advantages, limitations, applications
- The remaining flagged prose was shortened and made more concrete: 1.1, 1.2, 1.4, the chapter openings, 3.1, 3.2, 3.9, 3.10, 3.12, 4.1, 4.7, 4.11, the summaries, and Chapter 6.
- Report is now 58 pages and about 12,800 words (was about 13,900).
- All 24 original tables and figures are unchanged, citations are identical, numbers are unchanged, and the 3.12 AI-use disclosure is kept.

## Fourth pass after Turnitin 32%, 28 Oct 2026

- New tables:
  - 1.1: contributions
  - 3.3: T1 judgements
  - 3.5: T1 systems
  - 3.6: evaluation measures
  - 3.7: website pages
  - 6.1: answers to RQ1–RQ3
- Table cross-references renumbered and checked against the actual table order.
- 1.1 now uses the Board-approved outsourcing-policy example from the submitted paper.
- Remaining flagged prose shortened: 1.1, 1.2, the Chapter 2 opening, the first two 2.2 entries, 3.3, 3.9, 3.10, 3.11, 3.12, the Chapter 4 opening, 4.7, the summaries, and Chapter 6.
- Previous tables and figures unchanged, numbers unchanged, citations identical.

## Fifth pass after Turnitin 26%, 28 Oct 2026

- New tables:
  - 1.1: kinds of difference between parallel obligations
  - 3.3: corpus statistics
  - 3.7: full evaluation protocol, now including abstentions, intervals, Wilson and κ
  - 4.9: additional experiments
- Human oversight moved into Table 3.11.
- Table numbering in Chapters 1 and 3 updated, and every reference checked against the actual captions.
- Chapter summaries, chapter openings and table lead-ins shortened; 1.1–1.3, the 2.2 ObliQA entry, 3.3, 3.12, 4.7 and 4.11 rewritten.
- Numbers and citations unchanged.
