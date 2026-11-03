# NOTICE — third-party components

RBI-ObliBench does not vendor any third-party component. The code downloads or expects them locally. Licences were read
from the local checkout or the local Hugging Face cache on 2026-09-29; where no licence file or model card was present
locally, the entry says `licence: [verify]` rather than guessing.

| Component | Used for | Identifier | Pinned version | Licence |
|---|---|---|---|---|
| RePASs | T4 metric audit (P3-002), T4 ablation C (P4) | https://github.com/RegNLP/RePASs (checked out under `external/RePASs/`, gitignored) | commit `821d438d07cfc6747bd657965188d9dde85dcb71` | licence: [verify] (no licence file in the local checkout) |
| bge-base-en-v1.5 | dense retrieval, P2-002 matching, P3/P4 indexes | Hugging Face `BAAI/bge-base-en-v1.5` | revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` | MIT (local model card) |
| nli-deberta-v3-xsmall | P4 verifier; RePASs entailment / contradiction | Hugging Face `cross-encoder/nli-deberta-v3-xsmall` | revision `a150876415327c80daeff35ca6f68f5ed8cf5c24` | licence: [verify] (no model card in the local cache) |
| deberta-large-mnli | RePASs obligation coverage | Hugging Face `microsoft/deberta-large-mnli` | revision `7296194b9009373def4f7c5dad292651e4b5cf4e` (local cache) | licence: [verify] (no model card in the local cache) |
| legal-bert-base-uncased | RePASs obligation classifier (fine-tuned locally with RePASs' script; the fine-tuned weights are not released) | Hugging Face `nlpaueb/legal-bert-base-uncased` | revision `15b570cbf88259610b082a167dacc190124f60f6` (local cache) | licence: [verify] (no model card in the local cache) |

Python packages are listed with exact versions in `requirements-lock.txt` (main pipeline) and
`requirements-repass-lock.txt` (RePASs environment); each keeps its own licence.

**Hosted LLMs (not components, used through their APIs).** `gemini-3.5-flash-lite` (Google Gemini API; P4) and
`openai/gpt-oss-120b` (Groq API; P3-002 questions and genuine answers). Their outputs appear in the release only as
T4 questions and genuine answers (`release/data/t4/`); provider terms: [verify].

**RBI documents.** Not included and not licensed by this project; see `release/LICENSE-DATA` and `scripts/rehydrate.py`.
