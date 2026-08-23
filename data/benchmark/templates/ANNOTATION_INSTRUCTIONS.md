# RBI-ObliBench — Annotation Instructions (Pilot)

**Read this once before starting. It should take about 10 minutes; the pilot
itself is ~18 items.**

You have been given a CSV file named `annotation_<yourname>.csv`. Open it in
a spreadsheet (Excel, Numbers, Google Sheets) or a text editor. Fill in the
four columns on the right. Do not edit any other column, and do not reorder
or delete rows — `label_id` is what links your file back to everyone else's.

---

## What you are labelling

Each row is one **candidate obligation** — a span of text pulled out of an RBI
Master Direction because it contains a deontic cue ("shall", "must", "is
required to"). Some of these are genuine obligations. **Some are not** — the
extractor is a deliberately simple keyword search, so it also catches
definitional language ("X shall mean...") and commencement clauses ("...shall
come into force..."). Marking those as not-obligations is useful signal, not
a nuisance; see "If the span is not an obligation" below.

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
addressed to one class routinely extends obligations to others, or carves
some out. If you simply restate the source class every time, the resulting
label carries no information beyond "which file was this in" — and the whole
applicability research question collapses.

Judge from the **text of the span itself**, plus the `context_*` columns for
orientation. If the span says "banks and NBFCs shall...", then it applies to
both, regardless of which Direction it appeared in.

Use the entity-class names as they appear in `context_entity_class` across the
file (e.g. `Commercial Banks`, `Non-Banking Financial Companies`,
`Urban Co-operative Banks`) so everyone's spelling matches.

### 2. `applies_to_rationale`

One sentence: **why** you chose those classes. This is what lets us adjudicate
disagreements later instead of just counting them.

> "Span names 'every bank and NBFC' explicitly, so both classes."

### 3. `differential_flag` — exactly one of these four values

| Value | Use when |
|---|---|
| `shared` | The same obligation, in substance, also binds other entity classes. |
| `class-specific` | The obligation differs meaningfully by entity class (different thresholds, timelines, or carve-outs). |
| `absent` | You checked, and no counterpart obligation exists for other classes. |
| `unlabelled` | You could not determine it. **Leave the cell blank instead** — see below. |

**Do not use `absent` as a default.** `absent` is a positive finding meaning
"I looked and there isn't one". If you didn't look, or couldn't tell, leave
the row blank rather than guessing — an unexamined item recorded as `absent`
silently becomes evidence for a claim nobody checked.

### 4. `notes`

Anything else: ambiguity, a span that looks mis-extracted, a case you want to
discuss. Free text.

---

## If the span is not an obligation

Leave `applies_to` and `differential_flag` blank, and write why in `notes`
(e.g. "definitional, not an obligation"). Do not invent an applicability for
text that does not impose one.

---

## If you are unsure

**Leave the row blank and note why.** A blank row is read as "not yet
annotated" and is excluded from the agreement statistic. A guessed row is
read as a judgment and silently corrupts it. Blank is always the safer
choice.

---

## Rules the tooling enforces (so you don't have to worry about them)

- A row with a `differential_flag` but no `applies_to` is **rejected on
  ingestion** — an item cannot have a differential judgment without an
  applicability judgment.
- A `differential_flag` outside the four values above is rejected, naming your
  file and row number.
- An item is only promoted to `validated` once **at least two** of you have
  independently annotated it.
- Nothing you write is averaged or overwritten silently. Disagreements are
  preserved and measured.

---

## Please also record

**Roughly how long the whole file took you.** We need a real per-item
annotation time to plan Phase 2's ~350–400 item target — a guess here turns
into a badly wrong schedule later.

---

## When you're done

Save the file **in place, as CSV**, keeping the same filename, and tell Meer.
Ingestion runs `python scripts/run_annotation.py ingest`.
