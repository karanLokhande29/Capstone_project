# P2-004-SPRINT — overrides to P2-004 for the 30 Sep deadline

Run **together with** `docs/prompts/P2-004.md`. Where this file differs, **this file wins**. Everything else in P2-004 stands (blind sheets, D11 guard, provenance routes, no AI labels, candidate vs validated separation).

## 1. Clock
- Deadline 2026-09-30.
- Karan: 8+ h/day.
- Akash and Meer each label ~30 items by **29 Sep 12:00 IST**.

## 2. Size (keeps P2-004's full plan wherever the deadline allows)
- **N_target = 123 items across all 11 core classes**, exactly as P2-004 §K: floor 6 per class, K = 4 compared classes, blocks of 20.
- Karan labels pass 1 on **Sun 27 and Mon 28** (8+ h/day, about 7.5 h at 3.61 min/item).
- **Checkpoint after block 1.** Re-derive N from the measured minutes. Drop whole blocks from the end only if the measured pace can't finish by Mon 28, 23:59.
- If the re-derived N < 100, then (master prompt rule) concentrate on the core classes with the most Directions sharing subject families (measured from the matrix), and report the list.
- **Retest subset:** draw the stratified 20% hidden subset now, exactly as P2-004 A5.
  - The only part the deadline makes impossible is the 5-day gap: pass 1 ends 28 Sep, so the retest can't happen before 3 Oct.
  - The report therefore records Phase-2 test-retest as **NOT YET MEASURED (deadline 30 Sep; 5-day rule)**.
  - The retest sheet is still generated and date-locked, so it can be run after the deadline and added as an update.

## 3. Sheet change (adds to P2-004 A6)
- Add a column `matched_paragraph_id` beside `judgement`.
- For `same` or `different`, Karan enters the paragraph id that carries the corresponding obligation: one of the two shown, or any id from `lookup`. Leave it blank for `none` or `unsure`.
- These ids become T2 relevance judgements in P3-001/P4-001. Ingest validates the id format and that the id belongs to the judged target class.

## 4. Second raters (replaces P2-004 A5/A6 subset rules)
- **30 items**, all from blocks 1–3, stratified. The same 30 go to Akash and Meer, as blank files.
- Write both files in Part A so Karan can send them **tonight**.
- Both also fill in `matched_paragraph_id`.

## 5. Pilot retest (replaces P2-004 C2 timing)
- The 18 pilot items go in their own pass-2 sheet `annotation_pilot_karan_pass2.csv`. Write it in Part A.
- It is locked by date: ingest refuses it before **2026-09-30**. The sheet header says so.

## 6. Parts (replaces P2-004 §X order)
- **Part A (tonight):** preflight, rules check (A2 stop point still applies), candidate benchmark, sprint size, concentrated sample, all sheets (Karan pass 1, Akash, Meer, pilot pass 2), key, minutes log. Print a short send-list for Karan.
- **Checkpoint (Sun, after block 1).**
- **Part C (Mon):** ingest Karan pass 1 → validate. Build per-class judgement tables and the `matched_paragraph_id` qrels file `data/benchmark/t1/t1_pairs_qrels_v1.jsonl` for P3-001/P4-001.
- **Part D (Tue):** ingest Akash and Meer; inter-rater κ (pairwise Cohen's; Fleiss' over complete items); disagreement list → Karan adjudicates → validated set with provenance routes. Phase-2 test-retest: NOT YET MEASURED.
- **Part E (Wed 30 Sep):** ingest the pilot retest → pilot test-retest κ (18 items, bootstrap CI); final `reports/p2004_t1_benchmark.md` with the Phase 2 gate checklist. Gate items that can't be met by 30 Sep are listed as not met, with the reason.

## 7. Provenance routes (adds to P2-004 D3)
Items outside the second-rater subset, labelled once by Karan: `annotator:karan:single-pass`.
Items in the subset: `...:second-rater-consistent` if all agree, else `...:adjudicated`.
The report gives counts per route and says plainly that most items are single-pass.
