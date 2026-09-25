# RBI-ObliBench — Annotation Instructions (Single-Expert Protocol)

**Read this once before starting.** It should take about 10 minutes; the pilot
itself is ~18 items.

> **This project has one annotator.** From 2026-09-24 the three-person roster
> no longer exists, so there is no inter-annotator agreement to measure and the
> tooling will not produce one. Reliability evidence comes from **you labelling
> the same items twice, blind, at least five days apart** — plus a second rater
> if one can be found. That is what the two passes below are for, and it is the
> only reason the retest is worth the time.

You have a CSV file named `annotation_<yourname>.csv`. Open it in a spreadsheet
(Excel, Numbers, Google Sheets) or a text editor. Fill in the four columns on
the right. Do not edit any other column, and do not reorder or delete rows —
`label_id` is what links your judgments back to the item.

---

## The two passes, and why blindness matters

| | What you do | Why |
|---|---|---|
| **Pass 1** | Label every item in `annotation_<you>.csv`. Time it. | The labels themselves. |
| **Gap** | **At least 5 days.** | Sooner and you are remembering your answers, not re-forming a judgment. |
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
python scripts/run_annotation.py ingest --pass 1 --minutes karan=45
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

This formalises what Karan's pass 1 mostly did already: it used the two
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

## For a second rater

If someone else agrees to label a subset, they are a genuine second opinion and
the protocol treats them as one — but only if they are independent:

- label **independently**: do not look at Karan's file, and do not discuss
  specific items beforehand;
- use the same four columns, the same entity-class names, and the same
  "blank if unsure" rule;
- return the file named **`annotation_<yourname>.csv`** (e.g.
  `annotation_akash.csv`);
- tell Karan roughly how long it took.

Karan then adds that name to `config.benchmark.second_raters` and re-runs
`ingest`. Until that config entry exists the file is ignored — with a warning,
and it is never deleted. Any item where the second rater differs goes to
adjudication rather than quietly validating.

---

## When you're done

Save the file **in place, as CSV**, keeping the same filename, then run:

```bash
python scripts/run_annotation.py ingest --pass 1 --minutes <you>=NN
```

Five or more days later:

```bash
python scripts/run_annotation.py retest        # writes the blind pass-2 file
# ... fill annotation_<you>_pass2.csv ...
python scripts/run_annotation.py ingest --pass 2 --minutes <you>=NN
python scripts/run_annotation.py adjudicate    # only if disagreements exist
python scripts/run_annotation.py ingest --adjudication
python scripts/run_annotation.py report
```
