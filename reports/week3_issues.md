# Week 3 Issues — Entity/subject title parsing

## Issue

An earlier parser split entity/subject on ASCII hyphen as well as en-dash, which
truncated names such as `Urban Co-operative Banks` → `Urban Co` and
`Non-Banking Financial Companies` → `Non`.

## Fix applied

`parse_entity_and_subject` now splits **only** on Unicode en/em dashes (`–`/`—`),
with a known-entity-prefix fallback. Catalog, Matrix v0/v1, processed paragraph
metadata, and T1 candidate entity/subject fields were rebuilt from titles.

Counts in `week3_metrics.json` / `weeks_1_to_5_summary.md` reflect the corrected
discovered axes (not the dossier ~11×~26 estimate).
