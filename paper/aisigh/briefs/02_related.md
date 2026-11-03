# Brief: Related work

Word budget: **180 words** (6-page) / 350 (8-page, paid). Prose is written by the authors.

**Claims:**
- Regulatory QA and retrieval: ObliQA and RePASs \cite{gokhan2024regnlp} (paper); RePASs code at the pinned commit \cite{repass} (software citation only); ObliQA-MP \cite{obliqamp}; the RIRAG-2025 shared task \cite{gokhan2025riragtask}; AUEB-Archimedes on obligation concatenation \cite{aueb2025rirag}.
- Indian financial regulatory text: IndiaFinBench \cite{indiafinbench} (406 QA pairs from SEBI/RBI text; four task types).
- Retrieval: BM25S \cite{bm25s}, dense bge (C-Pack) \cite{bge} via Sentence-BERT \cite{sbert}, reciprocal rank fusion \cite{rrf}.
- Gap: no benchmark tests "same obligation vs different version across entity classes".

**References:** all verified on 2 Oct (`paper/aisigh/refs_verified.bib`). Cite RePASs-the-metric through `gokhan2024regnlp`, and use `repass` only as the code citation.

