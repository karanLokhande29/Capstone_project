# Week 1/2 Issues — PDF download bot challenge

## Conflict discovered

Direct GETs to `rbidocs.rbi.org.in` PDF URLs with a non-browser `User-Agent`
(`RBI-ObliBench-AcademicScraper/...`) returned an Imperva/TSPD JavaScript
challenge HTML page (~45KB) instead of a PDF. Files were cached with `.pdf`
extensions but were not valid PDFs (`No /Root object`).

## Resolution applied (not a methodology change)

1. Use a standard browser User-Agent + `Referer: https://www.rbi.org.in/`.
2. Validate downloaded content (`%PDF` magic / content-type) before accepting cache.
3. Invalidate and re-download challenge-HTML false positives.

Discovery of Master Direction **counts and URLs** from the listing page was
unaffected and remains the source of truth (381 discovered in this run).
