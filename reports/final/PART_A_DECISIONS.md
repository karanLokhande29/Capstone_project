# Command Center Part A: decisions log

Decisions taken without asking, as instructed: when something was ambiguous, the most conservative option was chosen. Dates are 2026-10-03, IST.

| # | Item | Decision | Why |
|---|---|---|---|
| D-A1 | A1 accent conversion | A small accent map in `scripts/build_master_document.py` (`tex_to_text`), not `pylatexenc`. | `pylatexenc` is not installed or in the lock, and adding a dependency is out of scope. |
| D-A2 | Master Document v1 | Kept unchanged in `reports/final/` and also zipped in `final_push_backups/command_center_partA_pre_20261003T104823Z.zip`; v2 is a new file. | "Archive, never overwrite": deleting v1 would lose the record the dossier history refers to. |
| D-A3 | main.tex | Regenerated rather than patched, both times. Before each run it was confirmed byte-identical to a fresh `build_paper_draft.py` output, so no hand edits existed. | The prompt allows regeneration when main.tex has not been hand-edited. After 2026-10-04 (manual prose rewrite), use `paper/aisigh/PATCHLIST_v1.md` instead. |
| D-A4 | A5 `different` F1 CIs | Not computed. A "CIs not computed" note was added, and the follow-up is listed. | No new statistics may go into frozen results. |
| D-A5 | A11 coverage value | Read from `phase4.t1_paired["Ablation C on T1: final agentic − class-aware"].coverage.diff` (−0.217) and printed in the document's own style (hyphen-minus in the Master Document, `$-$` in LaTeX). | Every number must come from `results_v2.json`. |
| D-A6 | A12 dossier regeneration | The pre-regeneration dossier was archived (byte copy in `final_push_backups/command_center_partA2_pre_20261003T110035Z.zip`), then `build_context_dossier.py` was rerun. The dossier's content was not read or displayed. | §2 privacy: nothing under `reports/private/` is read or displayed; only the generator touched it. |
| D-A7 | A14 prompt copy | `cp` of the single file the user named from `~/Downloads` into `docs/prompts/` (sha256 `73093ccb…`). No prompt index exists in `docs/prompts/`, so none was created. | The user asked for this copy explicitly; no other file outside the repo was read. Creating a new index file was not asked for. |
| D-A8 | A15 checklist source | `submission_checklist_v2.md` lives under `reports/private/final_push/p2/`. It was read once, only for the A15 comparison, and nothing from it is copied into `ui/`. | A15 names this file explicitly. It holds venue items, not rater identities. Its private status is respected by never surfacing it in the UI. |
| D-A9 | A15 CMT | No sign-in. Only the CMT login page was recorded. | Creating accounts and signing in are prohibited actions. |
| D-A10 | A15 page limit | The paper is treated as limited to **6 pages at submission**, because the CFP says 4–6. The 7–8 page charges are read as camera-ready only. | Most conservative reading of conflicting venue text. |
| D-A11 | A13 deliverables | Rebuilt `deliverables_2026-10-03/` in place after zipping its old contents to `final_push_backups/deliverables_2026-10-03_pre_20261003T110324Z.zip`. Today's date is still 2026-10-03, so the folder name follows its README convention. | Its README says to re-copy after a rebuild. |
| D-A12 | A16 placeholders | Left as `\placeholder{}`: 3 author emails and the Zenodo DOI. | Values must never be invented. |
