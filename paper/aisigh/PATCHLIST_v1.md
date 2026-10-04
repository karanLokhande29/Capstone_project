# PATCHLIST v1: text edits for the authors to review (Demo Build Spec B5, 2026-10-04)

From 2026-10-04 `main.tex` is edited by hand and is **never regenerated**. Each patch below is an exact find → replace, so it can also be applied to an Overleaf copy. **No number changes.**

## Applied 2026-10-04

These patches were applied to:
- `paper/aisigh/main.tex`, by text replacement (not regenerated);
- the generator `scripts/build_paper_draft.py`, so any later generation stays consistent;
- the master-document generator `scripts/build_master_document.py`, after which `reports/final/RBI-ObliBench_Master_Document_v2.{md,docx}` were regenerated. The diff against the previous v2 is exactly patches P4–P6 plus the record date.

### Paper (`main.tex`)

The Overleaf zip and `RBI-ObliBench_paper_draft.docx` were **not** re-exported; re-export them after review.

**P1. Limitations, last sentence**

- Find: `reranking, IndiaFinBench transfer or an ObliQA baseline, and the release has no UI.`
- Replace: `reranking, IndiaFinBench transfer or an ObliQA baseline. A public inspection interface accompanies the release; it reads the sealed outputs and does not affect any reported result.`

**P2. Future Work: remove "a user interface"**

- Find: `a LangGraph port of the pipeline; full use of the FAQ and enforcement sources; and a user interface.`
- Replace: `a LangGraph port of the pipeline; and full use of the FAQ and enforcement sources.`

**P3. Acknowledgment / AI use**

- Find: `internal reports. gemini-3.5-flash-lite and gpt-oss-120b are systems under study;`
- Replace: `internal reports. Claude Code also wrote the inspection interface and its build scripts under the authors' direction. gemini-3.5-flash-lite and gpt-oss-120b are systems under study;`

**Page budget:** P1 + P3 add about 30 words and P2 removes 4. Check the 6-page limit after compiling.

### Master Document v2

**P4. §11 Scope Ladder, item 7**

- Before: `release limited to benchmark + code + dataset card, with no UI.`
- After: `release limited to benchmark + code + dataset card. An inspection UI was built after the scope ladder; it reads the sealed outputs only and changes no reported result.`

**P5. §12 Future Work, rank 11 ("A UI")**

- **What:** `Built after the scope ladder: a public inspection interface that reads the sealed outputs only.`
- **Why:** `… outside the research questions; it changes no reported result.`
- **Effort:** `Done (inspection UI).`

**P6. §14 AI-use statement:** added the bullet `**Inspection interface:** Claude Code also wrote the inspection interface and its build scripts under the authors' direction.`

## Optional: not applied (team decision)

### P7. Confidence subsection

Insert only if the team wants the confidence model in the paper. Otherwise the UI keeps labelling it *Post-paper*.

Every number was checked against `ui/src/data/confidence_model_v1.json` (`models.M2.eval`) on 2026-10-04:

> Confidence. A logistic model over eight comparator-intrinsic features was fitted on the separate 30-item set (92 units) and frozen before gold evaluation. On the 412 gold units (base accuracy 297/412 = 0.721 [0.676, 0.762]), the High band was correct on 156/162 (0.963 [0.922, 0.983]), Medium 95/123 (0.772 [0.691, 0.838]), Low 46/125 (0.368 [0.289, 0.455]); ECE 0.087, Brier 0.148. High is assigned almost only to same answers; all but two correct different answers fall in Low.

If inserted, the UI's *Post-paper* tag on the confidence elements should be removed (`ui/src/features/demo/badges.tsx`, `PostPaper` uses).

### P8. Candidate limitation line (A3: actor names)

Drafted from `ui/AUDIT.md` §A3. The analysis is a post-hoc sensitivity check; the reported result uses the frozen rule.

> The comparator's fixed rule treats any extracted `actor` difference as material; because institution names differ across classes by construction, 8 of its 70 false alarms and 1 of its 38 correct *different* calls rest on actor wording alone (post-hoc sensitivity analysis; the reported result uses the frozen rule).
