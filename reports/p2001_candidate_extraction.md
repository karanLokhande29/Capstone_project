# P2-001 — Deontic obligation-span candidate extraction

_Current rules: **v4**. Candidate file: `data/benchmark/candidates/t1_candidates_v4.jsonl` (gitignored, not committed). Earlier rule versions' files and results are kept, not overwritten._

This stage **proposes** candidates only. Nothing here is a label or a validation.

## Precision rounds (P2-001-CLOSE)

**Verdict: P2-001's precision gate passes, reported in two parts that are never merged:**

- **v3 kept set** (unchanged in v4): round 3 scores 34/40 = 85.0% (Wilson 70.9%–92.9%). The P2-001 §F stop condition did not fire.
- **v4 re-admitted set**: 26/28 = 92.9% per row (Wilson 77.4%–98.0%) and 17/18 = 94.4% per distinct text, with manual labels. Every group is at or above 70%, so no v3 exclusion is restored.

v4 is the current rule set.

| Round | Labelled file | Rules in force | n | True obligations | Precision | Wilson 95% interval |
|---|---|---|---|---|---|---|
| 1 | `t1_precision_sample_v1_completed_corrected_v2.csv` | P2-001 original (v1) | 40 | 27 | 67.5% | 52.0%–79.9% |
| 2 | `t1_precision_sample_v2_labeled.csv` (re-sent, with Karan's reasons) | v1 + `redirect_reference`, `classification_deeming` (v2) | 40 | 31 | 77.5% | 62.5%–87.7% |
| 2 (alt) | `t1_precision_sample_v2_labeled_adjudicated.csv` | same (v2) | 40 | 27 | 67.5% | 52.0%–79.9% |
| 3 | `t1_precision_sample_v3_labeled.csv` | `non_action_effect` (v3, P2-001-CORRECTIVE-v2) | 40 | 34 | **85.0%** | **70.9%–92.9%** |

Provenance of the figures:

- Rounds 1, 2 and 3 were each re-scored on 2026-09-25 from the labelled file with `run_candidates.py score --rules <v> --sample-file <file>`. Each labelled file holds exactly the candidates of the sample the pipeline drew for that rule set (checked by the score command), and only the `is_obligation` and `reviewer_note` columns differ from the blank sample the pipeline wrote.
- **Round 2 (alt) is not in `data/benchmark/candidates/`**, so its 27/40 is taken from P2-001-CLOSE §A and has not been re-scored. It is round 2's labels with the stricter reading of rows 42, 60, 61 and 73 applied.
- An earlier, uncorrected round-1 file, `t1_precision_sample_v1_completed.csv`, scores 32/40. It is superseded by the corrected file above and is kept only for the record.
- Round 3's sample was drawn in the same run that wrote `t1_candidates_v3.jsonl` (`rules = v3`, seed 20260927, rows 81–120, with all 80 earlier sample rows removed from the pool). All 40 rows are kept candidates under v3.

### Round-3 sensitivity

Claude's independent reading of round 3 changes two rows from `y` to `n`:

- **#83**: a paraphrase of Section 18 of CICRA whose subject is "disputes" ("such disputes shall be settled by conciliation or arbitration").
- **#94**: a clause that only classifies the balances ("balances outstanding in the RTGS Settlement Account ... shall be distinct and separate from the loans").

That reading gives **32/40 = 80.0%**. The point estimate stays above the 70% floor, but the Wilson 95% interval (65.2%–89.5%) reaches below it. Round 2's two readings (77.5% as marked, 67.5% under the stricter one) straddle the floor, and that disagreement is why round 3 was run. On Karan's labels, round 3's interval (70.9%–92.9%) sits entirely above 70%.

### False positives by round, grouped by pattern

**Round 1 (v1 rules): 13 false positives**

- Cross-reference or redirect ("shall be governed by / subject to / guided by"): #9, #30, #36, #40
- Classification or deeming ("shall be treated as", "shall be standardized at"): #20, #37
- Definitional ("shall bear the meanings", "shall be as defined in"): #6, #23
- Interpretation clause ("shall be final and binding"): #3, #4
- Permission or option ("shall also be in order for", "shall have the option to"): #25, #34
- Penalty or consequence ("shall attract penal provisions"): #29

**Round 2 (v2 rules): 9 false positives as marked, 13 under the stricter reading**

- Signpost to conditions stated elsewhere ("shall be subject to the following conditions"): #44
- Definitional ("shall mean", "shall refer to", "shall have the meaning assigned"): #46, #69
- Savings, repeal or continuity ("shall continue to apply / be valid", repealed instructions remaining repealed): #54, #55, #64, #66
- Classification or deeming ("shall not be an event of default", "shall be categorised"): #65, #70
- Stricter reading only: disclosure-scope exclusion #42, non-diminishment #60, scope-extension signpost #61, access scope #73

**Round 3 (v3 rules): 6 false positives**

- Eligibility or status rule ("shall remain ineligible for restructuring"): #84
- Savings or continuity clause, only partly excluded by v3: #98
- RBI or a government body as the subject: #103, #119
- Entitlement granted to a third party ("the surviving nominee ... shall be entitled to"): #104
- Definitional proviso ("shall not qualify under this definition"): #111

## Labelling rules applied (for Week 5 annotation)

These are the rules Karan applied across the three rounds, as updated by P2-001-V4 (Karan decided on 2026-09-26 that the labelling line governs the extraction rules). Week 5 annotation should use the same line.

**Counts as an obligation:**

- an action or restriction on a regulated entity;
- **an access restriction** ("shall have access to ... only those borrowers which ...", "shall be restricted to ...");
- **a disclosure-scope or reporting-scope rule** ("this disclosure shall exclude ...", "the report shall include ...");
- a computation-method rule;
- **a risk-weight, provisioning or capital-charge rule** ("claims on the Central Government shall attract zero risk weight", "shall be risk weighted at 150 per cent", "shall attract provisioning requirement as applicable to ..."). These are among the rules most likely to differ between entity classes (RQ2);
- "shall comply with / adhere to [another document]", since that is an action verb;
- a conditional requirement, for example the criteria a bank must meet before it may use internal models;
- a span with several "shall" sentences where at least one is a genuine duty.

**Does not count:**

- definitions;
- classification or deeming ("shall be treated as ...", "shall be reckoned as Tier 1 capital");
- savings and continuity clauses ("shall continue to ...");
- signposts to conditions stated elsewhere;
- "shall be governed by / subject to / guided by", a status statement with no action verb;
- genuine permissions and options ("shall have the option to", "shall be allowed/permitted to <verb>", "shall have the right/discretion to", "it shall also be in order for");
- eligibility status ("shall be eligible for", "shall remain ineligible");
- spans where RBI, a government body or a third party is the subject;
- "shall be entitled to", an entitlement granted to someone else;
- interpretation clauses ("final and binding");
- penalty or consequence clauses.

## v4 rules: aligned with the labelling line (P2-001-V4)

**Step 1: counted before any rule changed** (read-only, on the v3 output):

| v3 exclusion group | Cues | Paragraphs excluded only by this group | Paragraphs v4 actually re-admits |
|---|---|---|---|
| `non_action_effect:access_scope`, all forms | 658 | 198 | — |
| &nbsp;&nbsp;of which "shall have access" (a restriction) | 20 | — | 9 |
| `non_action_effect:disclosure_scope` | 58 | 14 | 15 |
| Risk weight / provisioning / capital charge inside `non_action_effect:definitional` (283 / 30 / 9) | 322 | 115 | 142 |

The two paragraph columns differ because a paragraph becomes a candidate again as soon as any one of its cues is re-admitted, even if other cues stay excluded. The "only by this group" column counts just the paragraphs where every excluded cue is in the group.

The 658 `access_scope` cues break down by form:

| Form | Cues |
|---|---|
| "eligible to/for" | 179 |
| "permitted/allowed to <verb>" | 174 |
| "option" | 153 |
| "right/discretion/freedom/flexibility/liberty/choice" | 83 |
| "entitled/free/at liberty to" | 45 |
| "**have access**" | **20** |
| "in order for/to" | 4 |

Only "have access" is a restriction. The rest are permissions, options or eligibility status, which the labelling line does not count, so v4 keeps them excluded. "Shall be restricted to" was never excluded by any rule set.

Another 124 classification/deeming cues mention risk weight, provision, capital or tier (for example "shall be reckoned as Tier 1 Capital"). They classify an item rather than state a measurement rate, so they stay `non_action_effect:definitional`.

**The three v4 changes, and nothing else:**

1. `non_action_effect:disclosure_scope` is removed.
2. `non_action_effect:access_scope` no longer covers "shall have access". Every permission and option form stays excluded.
3. Risk-weight, provisioning and capital-charge measurement clauses leave `non_action_effect:definitional`. Real definitions and classification/deeming stay excluded.

v1, v2 and v3 still reproduce their candidate files byte for byte, and a regression test checks this against the real corpus.

**v4 counts:** 28,694 kept candidates (v3: 28,528), 4,813 fully excluded paragraphs, and 9,490 of 63,002 cue matches excluded (15.1%). 166 paragraphs are re-admitted: 9 access restriction, 15 disclosure scope, 142 risk weight / provisioning, and none by more than one change.

**Re-admitted-set check (P2-001-V4 §B.3, scored under P2-001-V4-FINISH).**

*Why 28 rows, not 30.* v4 re-admitted 166 paragraphs: 9 access restrictions, 15 disclosure scope and 142 risk weight / provisioning, with none re-admitted by more than one change. P2-001-V4 asked for 10 per group, so the access group falls short.

- Only 20 cues in the whole corpus have the "shall have access" form, and they sit in just 9 paragraphs.
- One of those 9 is round-2 row #73, already labelled and so removed from the pool.
- That left 8, all of which were drawn. The group was not topped up from other groups, because that would have diluted its per-group gate.

The sample was drawn stratified by entity class with seed 20260928, numbered 121–148, and written blank. Row groups are kept in a separate provenance file (`t1_precision_sample_v4_groups.json`), and there is no prediction file. The groups the prompt assigned from span text match the pipeline's own group tags exactly, row for row.

*Label source: `manual`* (declared by Karan, 2026-09-26). The labelled file is `t1_precision_sample_v4_labeled.csv`. Karan's TRUE/FALSE labels were converted to y/n with no other change, and every content cell matches the blank sample.

*Result (Karan's labels):*

| Re-admitted group | Rows | Per row | Wilson 95% | Distinct texts | Per distinct text | Wilson 95% |
|---|---|---|---|---|---|---|
| Access restriction (#122, 125, 133–135, 142–144) | 8 | 8/8 = 100% | 67.6%–100% | 2 | 2/2 = 100% | 34.2%–100% |
| Disclosure scope (#121, 127, 128, 130, 137, 138, 140, 141, 146, 147) | 10 | 8/10 = 80.0% | 49.0%–94.3% | 6 | 5/6 = 83.3% | 43.6%–97.0% |
| Risk weight / provisioning (#123, 124, 126, 129, 131, 132, 136, 139, 145, 148) | 10 | 10/10 = 100% | 72.2%–100% | 10 | 10/10 = 100% | 72.2%–100% |
| **All re-admitted** | 28 | **26/28 = 92.9%** | 77.4%–98.0% | 18 | **17/18 = 94.4%** | 74.2%–99.0% |

**Gate: every group's point estimate is at or above 70% (per row), so no v3 exclusion is restored.** The disclosure group's interval reaches well below 70% (49.0%), because 10 rows cannot pin precision down.

*Sensitivity (Claude's independent reading).* This reading changes two rows to `n`:

- **#125**: the grammatical subject is RBI ("RBI shall have access to all information resources ... consumed by PPI provider").
- **#145**: the risk weight is only "as prescribed in paragraph 19(4)", a pointer to text stated elsewhere.

That gives 24/28 = 85.7% (Wilson 68.5%–94.3%). Per row, every group stays at or above 70%: access 7/8 = 87.5%, disclosure 8/10 = 80.0%, risk weight 9/10 = 90.0%. Per distinct text it gives 15/18 = 83.3% (60.8%–94.2%), and the **access group falls to 1/2 = 50%**. It has only two distinct texts, and #125 is one of them. The §B.3 gate is defined per row, so this does not change the gate result. It does mean the access group's 8/8 rests on two sentences.

*Duplicate text.* The 28 rows hold only 18 distinct texts. Rows count as the same text when their re-admitted sentence is a prefix of another, or at least 90% similar. The repeats are:

- "Such a CI shall have access to Credit Information Reports ... only": 7 rows, #122, 133, 134, 135, 142, 143, 144. #135 and #143 read "CoR" where the others read "license".
- The Annual Report BC-model sentence: 3 rows, #128, 138, 140. #128 is cut at a page break.
- The Level 3 disclosure note: 2 rows, #137, 141.
- "Banking system shall comprise": 2 rows, #121, 127.

No repeated text was labelled differently in different copies.

*New false positives:*

- **#121 and #127**: definitions phrased "the expression 'Banking system' shall comprise the following banks and financial institutions". No v4 rule catches "shall comprise" outside a disclosure context. They were re-admitted as disclosure scope because the clause subject contains "return".

## Known limitations (recorded, not fixed)

Changing the rules now would bias the round-3 result, so these are candidates for the next rule version only. v4 deliberately fixes none of them.

The `non_action_effect` rule missed two spans it should have excluded:

- **#98.** v3 excluded two of its three cues: "shall continue to be governed by the provisions thereof" (`non_action_effect:cross_reference`) and "shall be deemed as governed" (`definitional`). It missed "shall not in any way prejudicially affect", because an adverb between "not" and the verb breaks the `legal_effect` pattern. One cue survived, so the paragraph stayed a candidate.
- **#111.** "shall not qualify under this definition", a definitional proviso that no pattern covers.

Patterns the rules do not cover at all:

- RBI or a government body as the subject: #103, #119;
- "shall be entitled to": #104;
- eligibility or status ("shall remain ineligible"): #84.

Also found while closing P2-001, and also left unfixed. These are round-2 false positives (as marked) that v3 still keeps:

- #44 "shall be subject to the following conditions". v2 and v3 deliberately keep this form, reading the conditions as the duty. Karan's line treats it as a signpost.
- #46 "shall refer to" (definitional);
- #65 "shall not be an event of default" (deeming);
- #69 "It shall also include ..." inside a definitions block;
- #70 "shall be categorised '...'", with no "as".

Found in the v4 re-admitted sample (P2-001-V4-FINISH), recorded and not fixed:

- **Definitions phrased "shall comprise"** (#121, #127): "the expression 'Banking system' shall comprise ...". No rule covers this definitional form.
- **Segmentation artifacts.** #121 and #127 each splice an unrelated item ("(vi) In the case of any Co-operative Bank which has granted an advance ...") into the definition. #132 is extracted from a table and mixes fragments of adjacent rows (items 13 and 14 and a stray "%" header) around the one risk-weight sentence. This is a segmenter issue, not an exclusion-rule issue.
- **Pointer-only measurement clauses** (#145, Claude's reading only): "shall attract risk weight ... as prescribed in paragraph 19(4)" states no rate itself. Karan labelled it an obligation.
- **Regulator as the subject of an access clause** (#125, Claude's reading only): "RBI shall have access ...". This is the existing RBI-as-subject limitation, now inside a re-admitted group.
- **Every precision sample so far (rounds 1–3 and v4) was drawn per row.** The consolidated Directions repeat identical sentences across entity classes, so repeated text inflates the effective n. The v4 sample has 28 rows but only 18 distinct texts, and the access group has 8 rows but 2 texts. The per-row figures overstate how much independent evidence each sample carries.

**Note for P2-002 and the Week 5 sampling:** deduplicate or cluster identical span text before sampling for annotation. `near_duplicate_clusters()` in `src/benchmark/candidates.py` is one way to do it (prefix match or at least 90% similar). Otherwise annotation time goes on labelling the same sentence repeatedly, and agreement statistics are inflated in the same way. Identical text across entity classes is also direct evidence of **shared** obligations, which is exactly what RQ2 and P2-002's cross-class matching look for. P2-002 should use these clusters, not discard them.

**Resolved in v4:** the tension between the labelling line and the v3 rules. v3 excluded disclosure-scope rules (58 cues), the "shall have access" restriction (20 of the 658 `access_scope` cues) and risk-weight / provisioning measurement clauses (322 cues), all of which the labelling line counts as obligations. Karan decided that the labelling line governs, and v4 re-admits those cues.

## 0b. Correction note, round 2 (P2-001-CORRECTIVE-v2)

- v2 rules result as marked: **31/40 = 77.5%** (meets the 70% floor, Wilson 95% 62.5%–87.7%). Under the stricter reading of rows 42, 60, 61 and 73 it is 27/40 = 67.5%, the figure P2-001-CORRECTIVE-v2 acted on (see Precision rounds).
- The v2 fix worked on its own targets: neither redirect nor classification clauses appear among the round-2 false positives. The misses were four new shapes: a disclosure-scope exclusion ("this disclosure shall exclude ..."), a non-diminishment clause ("outsourcing ... shall not diminish its obligations"), a scope-extension signpost ("Instruction at (4) above shall also apply to ..."), and an access-scope clause ("shall have access to ... only those borrowers").
- v3 **replaces** v2's two narrow subtypes with one general exclusion, `non_action_effect`, for a cue that states a fact about legal position, another rule, a definition, or a permission/scope boundary, not an action the entity must take. The subtype is kept in `exclusion_reason` (`non_action_effect:legal_effect`, `:cross_reference`, `:definitional`, `:access_scope`, `:disclosure_scope`). P2-001's own checks (heading, definitional, procedural, quoted statute) run first and are unchanged. Mixed paragraphs stay candidates through the existing per-cue logic.
- All 10 hand-identified false positives from both rounds are unit-test fixtures and classify as `non_action_effect`. v1 and v2 remain selectable, and their reruns reproduce `t1_candidates_v1.jsonl` and `t1_candidates_v2.jsonl` byte for byte.
- The v3 sample is a fresh draw (new seed, all 80 earlier sample rows removed from the pool, numbered 81–120) and is written **blank**: no pre-filled `is_obligation` or `reviewer_note`, and no separate prediction file, so the review starts unanchored.
- If v3 also comes back below 70%, P2-001-CORRECTIVE-v2 §D applies: stop. Revisit paragraph-level cue matching itself rather than extending the exclusion list again.

## 0. Correction note, round 1 (P2-001-CORRECTIVE)

- v1 rules result: **27/40 = 67.5%** (**below 70%: stop condition fired**, Wilson 95% 52.0%–79.9%). P2-001 §F required a fix before Week 4 continues. Basis: scored from the hand-filled sample CSV.
- Root cause from the reviewed v1 sample: 13 of 40 were not obligations. Six fall into two unhandled patterns: **cross-reference redirects** ("shall be governed by / subject to / guided by [another instrument]", 4 rows) and **classification/deeming** clauses ("shall be treated as", "shall be standardized at", 2 rows).
- v2 adds two `excluded_boilerplate` subtypes, `redirect_reference` and `classification_deeming`. It also extends `definitional` to "shall bear the meaning(s)" and "shall be as defined in/under". The v2 checks run after every v1 check, so no cue v1 excluded changes subtype. v1 is still selectable (`--rules v1`), and re-running it reproduces `t1_candidates_v1.jsonl` byte for byte.
- The v2 precision sample is a **fresh** draw: new seed, and the 40 v1 rows are removed from the pool. It is numbered 41–80, so no v2 row shares a number with a v1 row. The reviewed v1 rows served only as unit-test fixtures, never as validation.
- Still open after v1 and **deliberately not changed** (outside P2-001-CORRECTIVE's scope): "interpretation ... shall be final and binding" closing clauses, "shall also be in order for" and "shall have the option to" permissive clauses, and "shall attract penal provisions". The corrective prompt describes these v1 rows as already handled. They were not: all were kept candidates under v1, and no permissive-option rule exists.

## 1. Rule versions side by side

| | v1 rules | v2 rules | v3 rules | v4 rules |
|---|---|---|---|---|
| Paragraphs with a cue | 33,507 | 33,507 | 33,507 | 33,507 |
| Kept as candidates | 31,096 | 30,019 | 28,528 | 28,694 |
| Fully excluded paragraphs (any reason) | 2,411 | 3,488 | 4,979 | 4,813 |
| &nbsp;&nbsp;of which `excluded_boilerplate` only | 2,411 | 3,488 | 2,411 | 2,411 |
| Cue matches excluded | 4,510 of 63,002 | 7,152 of 63,002 | 9,890 of 63,002 | 9,490 of 63,002 |
| **Rejection rate (cue level)** | **7.2%** | **11.4%** | **15.7%** | **15.1%** |
| &nbsp;&nbsp;`definitional` cues | 2,644 | 2,942 | 2,644 | 2,644 |
| &nbsp;&nbsp;`procedural` cues | 1,737 | 1,737 | 1,737 | 1,737 |
| &nbsp;&nbsp;`procedural_header` cues | 7 | 7 | 7 | 7 |
| &nbsp;&nbsp;`quoted_statute` cues | 122 | 122 | 122 | 122 |
| &nbsp;&nbsp;`redirect_reference` cues | 0 | 1,139 | 0 | 0 |
| &nbsp;&nbsp;`classification_deeming` cues | 0 | 1,205 | 0 | 0 |
| &nbsp;&nbsp;`non_action_effect:legal_effect` cues | 0 | 0 | 876 | 876 |
| &nbsp;&nbsp;`non_action_effect:cross_reference` cues | 0 | 0 | 1,963 | 1,963 |
| &nbsp;&nbsp;`non_action_effect:definitional` cues | 0 | 0 | 1,825 | 1,503 |
| &nbsp;&nbsp;`non_action_effect:access_scope` cues | 0 | 0 | 658 | 638 |
| &nbsp;&nbsp;`non_action_effect:disclosure_scope` cues | 0 | 0 | 58 | 0 |
| **Precision spot-check** | **27/40 = 67.5%** (**below 70%: stop condition fired**, Wilson 95% 52.0%–79.9%) | **31/40 = 77.5%** (meets the 70% floor, Wilson 95% 62.5%–87.7%) | **34/40 = 85.0%** (meets the 70% floor, Wilson 95% 70.9%–92.9%) | v3 kept set **34/40 = 85.0%** (meets the 70% floor, Wilson 95% 70.9%–92.9%) + re-admitted set **26/28 = 92.9%** (meets the 70% floor, Wilson 95% 77.4%–98.0%) (reported separately, not merged) |

## 2. Corpus scanned (v4 run)

- Documents in manifest: 381
- Documents scanned: 381
- Documents with no paragraph file: 0
- Paragraphs scanned: 76,188 (expected 76,188 from P1-004)
- Metrics generated 2026-09-25T18:52:46+00:00

## 3. Candidates (v4 rules)

- Paragraphs with at least one cue: **33,507** (44.0% of paragraphs)
- Kept as candidates: **28,694**
- Fully excluded (every cue excluded): **4,813**. By `exclusion_reason`: `excluded_boilerplate` 2,411, `non_action_effect:legal_effect` 715, `non_action_effect:cross_reference` 707, `non_action_effect:definitional` 571, `non_action_effect:access_scope` 189, `excluded_boilerplate+non_action_effect:definitional` 108, `excluded_boilerplate+non_action_effect:cross_reference` 44, `non_action_effect:cross_reference+definitional` 27, `excluded_boilerplate+non_action_effect:legal_effect` 14, `non_action_effect:access_scope+definitional` 12, `excluded_boilerplate+non_action_effect:cross_reference+definitional` 4, `non_action_effect:cross_reference+legal_effect` 3, `non_action_effect:access_scope+cross_reference+definitional` 2, `non_action_effect:access_scope+cross_reference` 2, `excluded_boilerplate+non_action_effect:access_scope+cross_reference` 1, `non_action_effect:access_scope+legal_effect` 1, `excluded_boilerplate+non_action_effect:cross_reference+legal_effect` 1, `non_action_effect:definitional+legal_effect` 1
- Mixed paragraphs (some cues excluded, at least one kept): 2,646
- Kept candidates with a matrix cell: 25,993, across 296 distinct cells. Kept candidates without one (document has no derived subject family): 2,701

### Cue distribution (every match / kept matches only)

| Cue | All matches | Kept |
|---|---|---|
| `shall` | 55,985 | 47,152 |
| `shall not` | 5,090 | 4,452 |
| `must` | 1,054 | 1,043 |
| `is required to` | 366 | 363 |
| `are required to` | 325 | 321 |
| `must not` | 48 | 48 |
| `is mandatory` | 42 | 41 |
| `is not permitted to` | 32 | 32 |
| `is prohibited from` | 29 | 29 |
| `are not permitted to` | 15 | 15 |
| `is obligated to` | 7 | 7 |
| `are mandatory` | 6 | 6 |
| `are prohibited from` | 3 | 3 |

### By entity class (raw, from the manifest)

| Entity class | Paragraphs | Kept | Excluded |
|---|---|---|---|
| All India Financial Institutions | 5,952 | 2,423 | 369 |
| Asset Reconstruction Companies | 1,219 | 504 | 65 |
| Banker and Debt Manager to Government | 239 | 23 | 3 |
| Banker to Governments and Banks | 254 | 48 | 18 |
| Commercial Banks | 13,728 | 5,465 | 754 |
| Consumer Education and Protection | 462 | 154 | 31 |
| Credit Information Companies | 920 | 416 | 40 |
| Financial Inclusion and Development | 908 | 201 | 76 |
| Financial Market | 1,687 | 477 | 204 |
| Foreign Exchange Management | 2,610 | 496 | 64 |
| Issuer of Currency | 206 | 59 | 4 |
| Local Area Banks | 6,388 | 2,334 | 433 |
| Non-Banking Financial Companies | 7,769 | 3,135 | 639 |
| Payment and Settlement System | 837 | 297 | 43 |
| Payments Banks | 5,866 | 2,339 | 307 |
| Regional Rural Banks | 4,867 | 1,842 | 335 |
| Rural Co-operative Banks | 4,088 | 1,503 | 325 |
| Small Finance Banks | 11,237 | 4,358 | 619 |
| Urban Co-operative Banks | 6,951 | 2,620 | 484 |

## 4. Gate item 2: candidate rejection rate

- v4 rules: 9,490 of 63,002 cue matches excluded = **15.1%** (paragraph level: 14.4%). The per-subtype and per-version counts are in section 1.

## 5. Gate item 1: precision spot-check

### v1 rules

- Sample: 40 kept candidates across 19 entity classes, stratified, seed 20260925, `sample_index` 1–40, in `data/benchmark/candidates/t1_precision_sample_v1.csv`
- By entity class: All India Financial Institutions 2, Asset Reconstruction Companies 2, Banker and Debt Manager to Government 2, Banker to Governments and Banks 2, Commercial Banks 3, Consumer Education and Protection 2, Credit Information Companies 2, Financial Inclusion and Development 2, Financial Market 2, Foreign Exchange Management 2, Issuer of Currency 2, Local Area Banks 2, Non-Banking Financial Companies 2, Payment and Settlement System 2, Payments Banks 2, Regional Rural Banks 2, Rural Co-operative Banks 2, Small Finance Banks 3, Urban Co-operative Banks 2
- Precision: **27/40 = 67.5%** (**below 70%: stop condition fired**, Wilson 95% 52.0%–79.9%)

### v2 rules

- Sample: 40 kept candidates across 19 entity classes, stratified, seed 20260926, `sample_index` 41–80, in `data/benchmark/candidates/t1_precision_sample_v2.csv`
- Fresh draw: 40 earlier-sample rows removed from the pool; overlap with earlier samples: 0
- By entity class: All India Financial Institutions 2, Asset Reconstruction Companies 2, Banker and Debt Manager to Government 2, Banker to Governments and Banks 2, Commercial Banks 3, Consumer Education and Protection 2, Credit Information Companies 2, Financial Inclusion and Development 2, Financial Market 2, Foreign Exchange Management 2, Issuer of Currency 2, Local Area Banks 2, Non-Banking Financial Companies 2, Payment and Settlement System 2, Payments Banks 2, Regional Rural Banks 2, Rural Co-operative Banks 2, Small Finance Banks 3, Urban Co-operative Banks 2
- Precision: **31/40 = 77.5%** (meets the 70% floor, Wilson 95% 62.5%–87.7%)

### v3 rules

- Sample: 40 kept candidates across 19 entity classes, stratified, seed 20260927, `sample_index` 81–120, in `data/benchmark/candidates/t1_precision_sample_v3.csv`
- Fresh draw: 80 earlier-sample rows removed from the pool; overlap with earlier samples: 0
- By entity class: All India Financial Institutions 2, Asset Reconstruction Companies 2, Banker and Debt Manager to Government 2, Banker to Governments and Banks 2, Commercial Banks 3, Consumer Education and Protection 2, Credit Information Companies 2, Financial Inclusion and Development 2, Financial Market 2, Foreign Exchange Management 2, Issuer of Currency 2, Local Area Banks 2, Non-Banking Financial Companies 2, Payment and Settlement System 2, Payments Banks 2, Regional Rural Banks 2, Rural Co-operative Banks 2, Small Finance Banks 3, Urban Co-operative Banks 2
- Precision: **34/40 = 85.0%** (meets the 70% floor, Wilson 95% 70.9%–92.9%)

### v4 rules

v4 changes only which v3-excluded paragraphs come back, so its precision is reported in two parts that are never merged into one number:

- **v3 kept set** (unchanged in v4): round 3, **34/40 = 85.0%** (meets the 70% floor, Wilson 95% 70.9%–92.9%).
- **Re-admitted set** (kept by v4, excluded by v3): **26/28 = 92.9%** (meets the 70% floor, Wilson 95% 77.4%–98.0%).
- Re-admitted pool: 166 paragraphs. By group: Access restrictions ("shall have access to ... only") 9, Disclosure / reporting scope 15, Risk weight / provisioning / capital charge 142. Re-admitted by more than one change (left out of the per-group sample): 0.
- Sample: 28 rows, 10 per group, stratified by entity class, seed 20260928, `sample_index` 121–148, written blank to `data/benchmark/candidates/t1_precision_sample_v4.csv`. The group of each row is kept out of that file, in `t1_precision_sample_v4_groups.json`, and there is no prediction file. 2 pool rows that earlier samples had already shown the reviewer were removed; overlap with earlier samples: 0.

| Re-admitted group | Judged | True obligations | Precision | Wilson 95% | Gate (≥ 70%) |
|---|---|---|---|---|---|
| Access restrictions ("shall have access to ... only") | 8 | 8 | 100.0% | 67.6%–100.0% | passes |
| Disclosure / reporting scope | 10 | 8 | 80.0% | 49.0%–94.3% | passes |
| Risk weight / provisioning / capital charge | 10 | 10 | 100.0% | 72.2%–100.0% | passes |
| **All re-admitted** | 28 | 26 | 92.9% | 77.4%–98.0% | — |

- Label source (declared by the reviewer): **manual**. Counts toward the gate.
- Gate: no group below 70%, so no v3 exclusion is restored.

Per **distinct text**. A near-identical sentence repeated across Directions counts once (prefix or ≥ 90% similar), and a text counts as an obligation only if every copy is `y`:

| Re-admitted group | Rows | Distinct texts | True obligations | Precision | Wilson 95% |
|---|---|---|---|---|---|
| Access restrictions ("shall have access to ... only") | 8 | 2 | 2 | 100.0% | 34.2%–100.0% |
| Disclosure / reporting scope | 10 | 6 | 5 | 83.3% | 43.6%–97.0% |
| Risk weight / provisioning / capital charge | 10 | 10 | 10 | 100.0% | 72.2%–100.0% |
| **All re-admitted** | 28 | 18 | 17 | 94.4% | 74.2%–99.0% |

- Repeated texts (rows): #121, #127; #122, #133, #134, #135, #142, #143, #144; #128, #138, #140; #137, #141. Clusters whose copies were labelled differently: 0.

## 6. Known limits

- `should` is not a cue. Paragraphs containing `should` and no cue: 3,303. That count is the upper bound of the recall gap this choice creates.
- Exemptions (`shall not be required to`) match `shall not` and are kept. They are not boilerplate under step C.3, so Week 5 rejects them.
- Reproduced statute is detected only when quoted (60+ characters inside quote marks) or introduced by "reads as under/follows"-type phrasing in the same or the preceding paragraph. Unquoted reproductions pass through.
- `redirect_reference` needs the redirect's object (up to the end of its clause) to name an instrument (Direction, Act, guidelines, instructions, norms, paragraph, …). A duty named before that reference (validation, approval, audit, review, …) keeps the cue. "Subject to a ceiling of 10 per cent" and "subject to the following conditions" stay candidates.
- `classification_deeming` (v2) and `non_action_effect:definitional` (v3) keep "shall be treated as confidential"-type clauses, which impose a duty.
- v3 excluded risk-weight and provisioning measurement clauses ("claims on the Central Government shall attract zero risk weight", "shall be risk weighted at 150 per cent") as `non_action_effect:definitional`. **v4 re-admits them**, because the labelling line counts them as obligations and they are prime RQ2 differential content. Classification such as "shall be reckoned as Tier 1 capital" stays excluded.
- `access_scope` (v3 and v4) treats "shall be allowed/permitted to <verb>" as a permission, but not "shall be allowed to the <recipient>", which obliges the entity to grant something. Negated forms ("shall not be permitted to") are prohibitions and stay candidates. **v4** also re-admits "shall have access" as a restriction, and keeps eligibility ("shall be eligible for") excluded as a status, not a duty.
- v3's `disclosure_scope` needed a reporting noun within six words before the cue. **v4 removes the subtype entirely**, because the labelling line counts disclosure and reporting scope as an obligation.
- `cue_exclusions` is one field beyond the P2-001 section D schema. It holds the per-cue subtype that the cue-level rejection rate needs.
