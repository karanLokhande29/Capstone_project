# RBI-ObliBench — Annotation Instructions

**Guidelines version: v3.1** (2026-09-27). v1 and v2 below still hold unless the
v3 section at the end says otherwise. v3.1 changes one thing from v3 (2026-09-26):
there is **no minimum waiting period** between pass 1 and pass 2 (rule v3.10).
The label rules are unchanged.

**Read this once before starting.** It should take about 15 minutes.

> **Roster (v3, from 2026-09-26).** **rater_1 is the primary annotator.** **rater_2
> and rater_3 are independent second raters** on a 30-item subset of the P2-004
> sample. They start from **blank files** (v2.5), and nobody discusses
> individual items until their files have been returned.
>
> Reliability evidence comes from two places:
> - **test-retest:** rater_1 labels the same items twice, blind (v3.10: no
>   minimum interval between the passes). That is what the two passes below are for.
> - **inter-rater:** rater_1, rater_2 and rater_3 on the shared subset.

You have a CSV file named `annotation_<yourname>.csv`. Open it in a spreadsheet
(Excel, Numbers, Google Sheets) or a text editor. Fill in the four columns on
the right. Do not edit any other column, and do not reorder or delete rows —
`label_id` is what links your judgments back to the item.

---

## The two passes, and why blindness matters

| | What you do | Why |
|---|---|---|
| **Pass 1** | Label every item in `annotation_<you>.csv`. Time it. | The labels themselves. |
| **Between the passes** | **No minimum wait (v3.10).** Pass 2 can start once pass 1 is ingested and frozen. | What protects the retest is blindness (below), not the calendar. |
| **Pass 2** | Label the items in `annotation_<you>_pass2.csv`, which the tooling generates for you. | Items you label the same way twice are the ones that validate. |

The pass-2 file contains the pre-drawn **retest set** in a **shuffled** order,
with every judgment column blank. For the pilot the retest set is all 18 items.

**Pass 2 only means something if it is blind.** While doing it:

- **do not open your pass-1 file**, or any notes you made during pass 1;
- **do not look up an earlier answer by `label_id`** — the row order is
  deliberately shuffled so position cannot remind you either;
- do not compare the two files until both are ingested.

If you break blindness on some rows, say so in `notes` rather than quietly
continuing. A retest figure that is really a memory test is worse than no
figure, because it will be reported as evidence of stability.

Items where the two passes agree are promoted to `validated`. Items where they
differ go to **adjudication**: you get a file showing both of your answers side
by side and write down which one is right and why. That written reason is
mandatory — the tooling refuses a decision without one.

---

## What you are labelling

Each row is one **candidate obligation** — a span of text pulled out of an RBI
Master Direction because it contains a deontic cue ("shall", "must", "is
required to"). Some of these are genuine obligations. **Some are not** — the
extractor is a deliberately simple keyword search, so it also catches
definitional language ("X shall mean...") and commencement clauses ("...shall
come into force..."). Marking those as not-obligations is useful signal, not a
nuisance; see "If the span is not an obligation" below.

---

## The columns you fill in

### 1. `applies_to` — **the most important column**

**Which regulated entity classes does this obligation actually bind?**

Separate multiple classes with a semicolon:

```
Commercial Banks;Small Finance Banks
```

**Do not just copy `context_entity_class`.** That column tells you which
Direction the text came from, which is *not* the same question. A Direction
addressed to one class routinely extends obligations to others, or carves some
out. If you simply restate the source class every time, the resulting label
carries no information beyond "which file was this in" — and the whole
applicability research question collapses. The report measures how often you
did exactly that, per pass, and prints it.

Judge from the **text of the span itself**, plus the `context_*` columns for
orientation. If the span says "banks and NBFCs shall...", then it applies to
both, regardless of which Direction it appeared in.

#### The valid names — spelling must match exactly

These are the 19 canonical entity classes discovered from the corpus
(`data/metadata/entity_classes.json`). **A name not on this list is rejected on
ingestion**, naming your file and row, because a misspelled class cannot be
joined back to the Subject x Entity-Class matrix:

- `All India Financial Institutions`
- `Asset Reconstruction Companies`
- `Banker and Debt Manager to Government`
- `Banker to Governments and Banks`
- `Commercial Banks`
- `Consumer Education and Protection`
- `Credit Information Companies`
- `Financial Inclusion and Development`
- `Financial Market`
- `Foreign Exchange Management`
- `Issuer of Currency`
- `Local Area Banks`
- `Non-Banking Financial Companies`
- `Payment and Settlement System`
- `Payments Banks`
- `Regional Rural Banks`
- `Rural Co-operative Banks`
- `Small Finance Banks`
- `Urban Co-operative Banks`

### 2. `applies_to_rationale`

One sentence: **why** you chose those classes. This is what lets you adjudicate
your own disagreement later instead of just counting it.

> "Span names 'every bank and NBFC' explicitly, so both classes."

### 3. `differential_flag` — exactly one of these four values

| Value | Use when |
|---|---|
| `shared` | The same obligation, in substance, also binds other entity classes. |
| `class-specific` | The obligation differs meaningfully by entity class (different thresholds, timelines, or carve-outs). |
| `absent` | You checked, and no counterpart obligation exists for other classes. |
| `unlabelled` | You could not determine it. **Leave the cell blank instead** — see below. |

**Do not use `absent` as a default.** `absent` is a positive finding meaning "I
looked and there isn't one". If you didn't look, or couldn't tell, leave the row
blank rather than guessing — an unexamined item recorded as `absent` silently
becomes evidence for a claim nobody checked.

### 4. `notes`

Anything else: ambiguity, a span that looks mis-extracted, a case you want to
revisit. Free text.

---

## If the span is not an obligation

Leave `applies_to` and `differential_flag` blank, **and write why in `notes`**
(e.g. "definitional, not an obligation"). Do not invent an applicability for
text that does not impose one.

The `notes` field is what distinguishes the two blank cases, so it is not
optional here:

- **blank judgment + a note** = "I looked; this is not an obligation" -> the
  item is `rejected`;
- **blank judgment + no note** = "not yet done" -> the item stays where it is
  and is excluded from every statistic.

## If you are unsure

**Leave the row entirely blank and move on.** A blank row is read as "not yet
annotated". A guessed row is read as a judgment and silently corrupts the
retest figure — and because you will see the same item again in pass 2, a guess
is also the fastest way to manufacture a disagreement you then have to
adjudicate. Blank is always the safer choice.

---

## Saving the file

**Saving as "CSV UTF-8" is fine** — Excel's CSV UTF-8 export writes a byte-order
mark and Windows line endings, and the ingest accepts both. Keep the filename
unchanged.

## Please also record

**The total minutes each pass took you.** Pass it on the command line:

```bash
python scripts/run_annotation.py ingest --pass 1 --minutes rater_1=45
```

We need a real per-item annotation time to plan Phase 2's item target — a guess
here turns into a badly wrong schedule later. Without it the report prints
`NOT YET MEASURED` and the Phase 2 projection is simply not made.

---

## Rules the tooling enforces (so you don't have to worry about them)

- A row with a `differential_flag` but no `applies_to` is **rejected on
  ingestion** — an item cannot have a differential judgment without an
  applicability judgment.
- A `differential_flag` outside the four values above is rejected, naming your
  file and row number.
- An `applies_to` name that is not on the list above is rejected, naming your
  file and row number.
- The same `label_id` twice in one file is rejected.
- **Nothing you write is overwritten.** Every pass is stored as its own set of
  votes. The tooling refuses to regenerate a task file that already holds
  filled-in cells, and if forced it copies the old file to
  `data/benchmark/tasks/_overwritten/` first.
- An item is promoted to `validated` only via a recorded route: both passes
  agreed, or it sat outside the retest set, or you adjudicated it in writing.

---

# Guidelines v2 — mandatory from Phase 2

> **The pilot files were labelled under v1 and are not edited.** These four
> rules were written after the pilot, in response to what the pilot actually
> produced. They are not applied retroactively; where a pilot disagreement
> turns out to be v1 ambiguity rather than genuine disagreement, the audit
> says so.

## v2.1 Obligated party — label only duties on a REGULATED ENTITY

Label an obligation only when the duty falls on an entity RBI regulates. If the
sentence places the duty on a customer, an applicant, a borrower or any other
third party, it is **not** an RE obligation, however forcefully it is worded.

Leave `applies_to` and `differential_flag` blank and write in `notes`:

```
not an RE obligation — duty on <party>
```

The pilot's `t1_pilot_md_12927::p00046_00` is the worked example: *"they are
required to submit an OVD..."* places the duty on the customer. The bank's
obligation is to *collect* one, which is a different sentence.

## v2.2 Function headings — which of the 19 names may appear in `applies_to`

Not every entity-class name denotes a class of regulated entity. Some are RBI
*function* headings, and using one as an applicability answer says which
department published the Direction rather than who it binds.

**May stand in for a regulated party:**

- `Payment and Settlement System` — use for **authorised non-bank payment system operators**.
- `Foreign Exchange Management` — use for **authorised persons / AD entities**.

**Never use in `applies_to`.** Map to the regulated classes the text actually
binds, and if the text binds nobody identifiable, treat it under v2.1:

- `Issuer of Currency`
- `Financial Market`
- `Financial Inclusion and Development`
- `Consumer Education and Protection`
- `Banker and Debt Manager to Government`
- `Banker to Governments and Banks`

**Always available** (ordinary regulated classes):

- `All India Financial Institutions`
- `Asset Reconstruction Companies`
- `Commercial Banks`
- `Credit Information Companies`
- `Local Area Banks`
- `Non-Banking Financial Companies`
- `Payments Banks`
- `Regional Rural Banks`
- `Rural Co-operative Banks`
- `Small Finance Banks`
- `Urban Co-operative Banks`

This formalises what rater_1's pass 1 mostly did already: it used the two
stand-ins above as parties, while mapping "Financial Market" and "Issuer of
Currency" through to bank classes. v1 left that to each rater's judgment, so
some of the pilot's `applies_to` variation would have been guideline ambiguity
rather than disagreement.

## v2.3 Cite your counterparts

A `differential_flag` is a claim about other Directions, so name them.

| Flag | Required `notes` entry |
|---|---|
| `shared` | `counterparts: md_xxxxx; md_yyyyy` |
| `class-specific` | `counterparts: md_xxxxx; md_yyyyy` |
| `absent` | `checked: md_xxxxx; md_yyyyy` |

Cite **only** document ids listed in `reference_directions.csv`, which is the
corpus snapshot. A counterpart outside it cannot be checked by anyone reading
the benchmark, and `absent` in particular is a positive finding that has to be
falsifiable — "I checked these and found none" is a claim; "there isn't one" is
not.

The pilot hit this directly: several `shared` rows cited Commercial Banks and
Small Finance Banks counterparts that were among the 81 Directions missing from
the corpus, so nobody could verify them at labelling time.

## v2.4 As-of rule

Judge applicability **as of the corpus snapshot**, i.e. against the Directions
in `reference_directions.csv` as they stand there. If you know of a draft, a
recent amendment or a future-effective provision that would change the answer,
put it in `notes` — but do not let it change the label. A benchmark whose labels
track a moving regulatory frontier cannot be reproduced by anyone later.

## v2.5 Independence — the rule the pilot did not have

**Form every judgment yourself, before seeing anyone else's.**

- **No AI tools** — ChatGPT, Claude, Copilot or any other — for labels,
  rationales or notes. A file produced with AI assistance must be declared, and
  is then recorded as a human-AI diagnostic: it never enters kappa and can
  never promote an item.
- **`applies_to` included.** Do not start from a file where someone has already
  filled that column. The pilot ran partially anchored — one person's
  `applies_to` was copied into all three files — so the pilot has **no**
  applicability reliability figure at all, and the tooling now refuses to
  report one when it detects the pattern. That is the specific mistake this
  rule exists to prevent.
- Do not discuss individual items with the other annotators until all files are
  submitted.
- Do not open anyone else's file.

## v2.6 Time

Record the **total minutes** each pass took you and report it with the file. A
recalled estimate afterwards is recorded as `recalled_estimate` and cannot
support a Phase 2 schedule; a figure noted at the time is recorded as
`measured` and can.

---

# Guidelines v3 — the P2-004 sheet (from 2026-09-26)

> v3 adds the per-class sheet used for the Phase 2 benchmark. **Every v1 and v2
> rule still holds unless a rule below replaces it.** The pilot files, including
> the pilot retest `annotation_pilot_rater_1_pass2.csv`, keep the item-level
> columns described above (`applies_to`, `applies_to_rationale`,
> `differential_flag`, `notes`).

## v3.1 Layout: one item row, then one row per compared class

The P2-004 files are called `annotation_p2004_<name>.csv`. Each item takes
several consecutive rows, and `row_type` says which kind a row is.

| `row_type` | What it shows | What you fill in |
|---|---|---|
| `item` | `source_class`, `subject_family`, `source_paragraph_id`, and `source_span` (the obligation sentence(s), then the whole paragraph) | `applies_to`, `applies_to_rationale`, `not_obligation`, `note` |
| `class` | `target_class` and `target_candidates`: two paragraphs from that class's Directions in the same subject family, each with its id in `[brackets]`, in random order | `judgement`, `matched_paragraph_id`, `note` |

- An item has **up to 4** class rows.
- Leave the other cells of a row blank.
- **Don't edit any shown column, and don't reorder or delete rows.**
- The paragraphs shown are candidates, not answers. Nothing on the sheet tells
  you how they were found or how good a match they are.

## v3.2 `applies_to` (item row): unchanged meaning, never derived

Fill this in **exactly as in v1**: which regulated entity classes the obligation
binds, judged from **the span's own text**.
- Apply v2.1 (obligated party).
- Use the v2.2 names: the 11 regulated classes, plus the two stand-ins
  `Payment and Settlement System` and `Foreign Exchange Management`.
- Separate names with `;`.
- **Don't fill this in from the class rows.** A counterpart in another class's
  Directions doesn't mean *this* sentence binds that class.
- `applies_to_rationale`: one sentence, as in v1.

## v3.3 `not_obligation` (item row)

Use this if the span isn't an obligation, or if the duty falls on someone RBI
doesn't regulate (v2.1):
- Enter `yes` in `not_obligation`.
- Leave `applies_to` and `applies_to_rationale` blank.
- Write the reason in `note`. For v2.1, write exactly
  `not an RE obligation — duty on <party>`; otherwise, for example,
  `definitional, not an obligation`.
- The item's class rows may stay blank.

These items are **rejected**. They are left out of the benchmark size and
reported as the candidate rejection rate.

## v3.4 `judgement` (class row): one of four values

| Value | Use when |
|---|---|
| `same` | The target class has the **same obligation in substance**, in a shown paragraph or one you looked up. |
| `different` | **Same topic, but the requirement differs**: a different threshold, timeline, scope or carve-out. |
| `none` | **No counterpart among the shown paragraphs and anything you looked up.** This covers only what you checked, not every Direction of that class. |
| `unsure` | You can't tell. |

**"Leave it blank if unsure" (v1) does not apply to this sheet.** Use `unsure`
instead. Every class row of an obligation item needs a value, and a blank
stops ingest.

## v3.5 `matched_paragraph_id` (class row): the v2.3 citation for this sheet

| Judgement | `matched_paragraph_id` |
|---|---|
| `same` / `different` | **Required.** The id of the paragraph that carries the counterpart, in the form `md_NNNNN::pNNNNN`. It can be one of the two shown, or any paragraph from a Direction of that target class (see v3.9). Give one id; if several apply, give the best one and list the others in `note`. |
| `none` | Leave it blank. The shown ids are recorded automatically as `checked`. If you checked other paragraphs, add them to `note` as `checked: md_…::p…; md_…::p…`. |
| `unsure` | Leave it blank. |

For this sheet, corpus paragraph ids replace v2.3's restriction to
`reference_directions.csv`. Ingest checks the id format and that the paragraph
belongs to a Direction of the judged target class.

## v3.6 `differential_flag` is derived, not entered

The item's flag is computed from its class rows, in this order:

1. any `different` → **`class-specific`**
2. otherwise, any `same` → **`shared`** (the obligation also binds another class)
3. all `none` → **`absent`**
4. otherwise (only `none` and `unsure`) → **ambiguous**, sent to adjudication

Any item with an `unsure` is also listed for adjudication, even when rule 1 or
2 decides its flag.

`absent` is limited to what was checked: the shown and cited paragraphs of the
compared classes (at most 4 per item). If a class's Directions in this subject
family have no candidate paragraphs at all, that class isn't shown or compared,
and it never counts as `none`.

## v3.7 Classes

Compared classes, and every T1 metric, use the **11 regulated classes** only.
The two stand-ins can appear in `applies_to` (v3.2); the report counts them
separately.

## v3.8 Blocks and minutes

- Items come in **blocks of 20** (column `block`). Label them in order.
- Log each block in `p2004_minutes.csv` **at the time** (`measured`, v2.6):
  `rater, block, started_at, ended_at, minutes, note`.
- rater_1 stops after block 1 for the checkpoint, which re-sizes the benchmark
  from the measured minutes.

## v3.9 Looking up other paragraphs (rater_1, with the repo)

```bash
python scripts/run_t1.py lookup --paragraph md_13140::p00087
python scripts/run_t1.py lookup --class "Small Finance Banks" --family "Know Your Customer" --query "video KYC"
```

Second raters without the repo can cite the shown ids, or an id from a
Direction they have open.

## v3.10 Retest timing (from 2026-09-27)

The method is **blind test-retest with no enforced minimum inter-pass
interval.** This replaces the earlier "at least 5 days" gap.

Pass 2 can start as soon as:
1. pass 1 has been validated and ingested, and is frozen;
2. the retest items were fixed in advance, independently of your pass-1 answers;
3. the pass-2 sheet is shuffled and every judgement field is blank.

Pass 2 must be **blind**. Don't open pass 1, your notes, the IRR outputs, the
adjudication files or any earlier answer. If you break blindness on any row,
say so in `note`.

When the passes happened is recorded as provenance only, and only where it was
logged at the time; unknown timing stays unknown. Elapsed time never decides
whether pass 2 may be generated, done, ingested or reported.

Reports describe this as a **blind test-retest procedure** and claim **no
washout period**. A short interval between the passes may inflate agreement
through recall of pass-1 answers, and reports say so.

For P2-004, pass 2 is a single sheet, `annotation_p2004_rater_1_pass2.csv`. It
holds the retest items (v3 layout, `row_type` item/class) and the 18 pilot items
(`row_type` pilot_item, pilot layout with `differential_flag`), shuffled
together.

---

## For a second rater (rater_2, rater_3)

You are a genuine second opinion, and the protocol treats you as one, but only
if you are independent:

- **Label independently.** Don't look at rater_1's file or each other's, and
  don't discuss any item until all files are returned (v2.5).
- **Start from your own blank file.** For P2-004 that is
  `annotation_p2004_rater_2.csv` or `annotation_p2004_rater_3.csv`. It uses the v3
  sheet layout below; read v3 before starting.
- **No AI tools** (v2.5).
- **Keep the filename** and return the file as CSV (UTF-8 is fine).
- **Log your minutes** as you go, one line per sitting (v2.6), and send them
  with the file.

Your names are already in `config.benchmark.second_raters`. Any item where you
differ from rater_1 goes to adjudication rather than quietly validating.

---

## When you're done

Save the file **in place, as CSV**, keeping the same filename, then run:

```bash
python scripts/run_annotation.py ingest --pass 1 --minutes <you>=NN
```

Then, once pass 1 is ingested (no minimum wait, v3.10), label pass 2 blind:

```bash
python scripts/run_annotation.py retest        # writes the blind pass-2 file
# ... fill annotation_<you>_pass2.csv ...
python scripts/run_annotation.py ingest --pass 2 --minutes <you>=NN
python scripts/run_annotation.py adjudicate    # only if disagreements exist
python scripts/run_annotation.py ingest --adjudication
python scripts/run_annotation.py report
```
