"""P4-001 pipeline, plain Python (no LangGraph).

Steps for a query (``entity_class``, ``as_of`` and three flags, all on by default):

1. **Retrieve**: P3-001 hybrid RRF (BM25 + bge, k = 60), top ``depth`` (20). The query's own
   source paragraph is always excluded. When the class filter is on, the fusion is ranked inside
   the kept set (as P3-001's ``class_aware``), so a filter never leaves an empty top 20.
2. **Class filter**: keep paragraphs whose Direction's entity class equals ``entity_class``, plus
   function-heading Directions (the stand-ins included) whose subject family matches the query's.
3. **Temporal filter** (needs ``as_of``): drop paragraphs deleted as of ``as_of``; attach the
   amendment action, text and effective date to paragraphs amended as of ``as_of``; mark
   paragraphs whose amendment takes effect later "original in force; amended from <date>".
   The events come from the T3 parser (``src/t3/parser.py``), the same rules that build the T3 gold.
4. **Answer**: the LLM answers from the top ``answer_top`` (5) kept paragraphs, citing ids.
5. **Verifier**: ``cross-encoder/nli-deberta-v3-xsmall`` at a pinned revision. A sentence is
   supported iff the argmax label (read from ``id2label``) is entailment, with the cited
   paragraph(s) as premise. Any unsupported sentence -> one deterministic retry (re-retrieve with
   the query plus the unsupported sentences, same filters, top 5; one answer call); still
   unsupported -> abstain ("cannot answer reliably") with the evidence.

T1 uses one call per item (all compared classes at once) with an equal evidence budget: class-aware
= top 5 per compared class retrieved inside that class; class-blind = top 5 x K class-blind.
The verifier checks each same/different rationale against its matched paragraph; a ``none``
cannot be checked by entailment. Still unsupported after the retry -> ``unsure``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from src.benchmark.t1 import derive_flag
from src.retrieval import systems as S

JUDGEMENTS = ("same", "different", "none", "unsure")
PID_RE = re.compile(r"md_\d+::p\d+")
ABSTAIN = "cannot answer reliably"


class PipelineError(RuntimeError):
    pass


class PromptFreezeError(PipelineError):
    pass


# -- prompts (frozen) -----------------------------------------------------------------

PROMPT_FILES = ("t1_system.txt", "t1_user.txt", "answer_system.txt", "answer_user.txt", "t3_system.txt",
                "t3_user.txt", "long_context_system.txt", "long_context_user.txt")


def prompt_hashes(directory: Path | str) -> dict[str, str]:
    d = Path(directory)
    return {f: hashlib.sha256((d / f).read_bytes()).hexdigest() for f in PROMPT_FILES}


class Prompts:
    """Loads the prompt files and refuses to run if any differs from the hashes frozen in config."""

    def __init__(self, directory: Path | str, frozen: Mapping[str, str] | None, *, require_frozen: bool = True):
        self.dir = Path(directory)
        current = prompt_hashes(self.dir)
        if require_frozen:
            if not frozen:
                raise PromptFreezeError("prompts are not frozen (p4.prompt_sha256 is empty); run `freeze` first")
            changed = sorted(f for f in PROMPT_FILES if frozen.get(f) != current[f])
            if changed:
                raise PromptFreezeError(f"frozen prompt(s) changed: {changed}. Stop and ask Karan before changing a prompt.")
        self.hashes = current
        self.text = {f: (self.dir / f).read_text(encoding="utf-8") for f in PROMPT_FILES}

    def messages(self, kind: str, **fields: Any) -> list[dict[str, str]]:
        user = self.text[f"{kind}_user.txt"]
        for k, v in fields.items():
            user = user.replace("{" + k + "}", str(v))
        return [{"role": "system", "content": self.text[f"{kind}_system.txt"].strip()},
                {"role": "user", "content": user.strip()}]


# -- temporal index ------------------------------------------------------------------------


@dataclass
class Event:
    item_id: str
    action: str
    scope: str
    date: str | None
    window: list[str] | None
    title: str
    new_text: str | None


class TemporalIndex:
    """paragraph_id -> amendment events, from the T3 parser's actions (all scopes except new paragraphs)."""

    def __init__(self, events: Mapping[str, Sequence[Event]]):
        self.events = {k: sorted(v, key=lambda e: (e.date or (e.window or ["9999"])[-1])) for k, v in events.items()}

    @classmethod
    def build(cls, actions: Sequence[Any], amendments: Mapping[str, Mapping[str, Any]],
              paras_by_md: Mapping[str, Sequence[Mapping[str, Any]]]) -> "TemporalIndex":
        from src.t3.parser import effective_date

        out: dict[str, list[Event]] = {}
        for a in actions:
            if not a.md_id or a.scope == "new_paragraph":
                continue
            eff = effective_date(amendments[a.item_id], a.start)
            if eff["date"] is None and eff["window"] is None:
                continue
            for p in paras_by_md.get(a.md_id, []):
                cp = (p.get("clause_path") or "").lower().replace(" ", "")
                for t in a.targets:
                    exact = cp == t
                    below = a.scope == "paragraph_whole" and (cp.startswith(t + "(") or cp.startswith(t + "."))
                    if exact or below:
                        new = a.new_text or ("; ".join(a.new_words) if a.new_words else None)
                        out.setdefault(p["paragraph_id"], []).append(Event(
                            a.item_id, a.action, a.scope, eff["date"], eff["window"],
                            amendments[a.item_id].get("title") or "", new))
                        break
        return cls(out)

    def status(self, pid: str, as_of: str) -> dict[str, Any]:
        """``state``: in_force | deleted | amended | original_amended_later | uncertain, with a note."""
        state, notes, governing = "in_force", [], None
        for e in self.events.get(pid, []):
            what = "deletion" if e.action == "delete" and e.scope == "paragraph_whole" else f"{e.action} ({e.scope.replace('_', ' ')})"
            if e.date:
                started, ended = e.date <= as_of, False
            else:
                lo, hi = e.window
                started, ended = as_of >= hi, as_of < lo
                if not started and not ended:
                    state = "uncertain"
                    notes.append(f"amendment {e.item_id} ({what}) takes effect between {lo} and {hi}")
                    continue
            eff = e.date or e.window[-1]
            if started:
                if e.action == "delete" and e.scope == "paragraph_whole":
                    state, governing = "deleted", e.item_id
                    notes.append(f"DELETED from {eff} by amendment {e.item_id} ({e.title})")
                else:
                    state, governing = ("amended" if state != "deleted" else state), e.item_id
                    new = f" New text: {e.new_text[:600]}" if e.new_text else ""
                    notes.append(f"AMENDED from {eff} by amendment {e.item_id} ({e.title}): {what}.{new}")
            else:
                if state == "in_force":
                    state = "original_amended_later"
                notes.append(f"original in force; amended from {eff} by amendment {e.item_id} ({what})")
        return {"state": state, "notes": notes, "governing": governing}


# -- NLI verifier ------------------------------------------------------------------------------


class NLIVerifier:
    """Supported iff argmax(NLI(premise, hypothesis)) is the model's entailment label (id2label, not assumed)."""

    def __init__(self, model_id: str, revision: str, *, device: str = "cpu"):
        import torch
        from huggingface_hub import model_info
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        resolved = model_info(model_id, revision=revision).sha
        if resolved != revision:
            raise PipelineError(f"STOP: {model_id} revision resolved to {resolved}, pinned {revision}")
        self.tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_id, revision=revision).eval().to(device)
        labels = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        ent = [k for k, v in labels.items() if v.startswith("entail")]
        if len(ent) != 1:
            raise PipelineError(f"cannot find the entailment label in id2label {labels}")
        self.entail, self.labels, self.device, self._torch = ent[0], labels, device, torch
        self.model_id, self.revision = model_id, revision

    def probs(self, pairs: Sequence[tuple[str, str]]) -> tuple[np.ndarray, np.ndarray]:
        """(entailment probability, argmax label id) per pair. For post hoc diagnostics; the rule is ``supported``."""
        if not pairs:
            return np.zeros(0), np.zeros(0, dtype=int)
        f = self.tok([p for p, _ in pairs], [h for _, h in pairs], padding=True, truncation="only_first",
                     max_length=512, return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            logits = self.model(**f).logits
        pr = logits.softmax(-1).cpu().numpy()
        return pr[:, self.entail], logits.argmax(-1).cpu().numpy()

    def premise_truncated(self, premise: str, hypothesis: str) -> bool:
        return len(self.tok(premise, hypothesis, truncation=False)["input_ids"]) > 512

    def supported(self, pairs: Sequence[tuple[str, str]]) -> list[bool]:
        if not pairs:
            return []
        f = self.tok([p for p, _ in pairs], [h for _, h in pairs], padding=True, truncation="only_first",
                     max_length=512, return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            arg = self.model(**f).logits.argmax(-1).cpu().tolist()
        return [a == self.entail for a in arg]


# -- resources ---------------------------------------------------------------------------------


@dataclass
class Resources:
    corpus: Any
    bm25: Any
    emb: np.ndarray
    encoder: Callable[[str], np.ndarray]
    doc: Mapping[str, Mapping[str, Any]]  # md_id -> {title, entity_class, subject_family}
    function_headings: frozenset
    temporal: TemporalIndex
    paragraph_max_chars: int = 1500
    family_of: np.ndarray = field(default=None)  # type: ignore[assignment]
    heading_mask: np.ndarray = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        mds = self.corpus.md_id
        self.family_of = np.array([self.doc.get(m, {}).get("subject_family") for m in mds], dtype=object)
        self.heading_mask = np.array([c in self.function_headings for c in self.corpus.entity_class])

    def text(self, pid: str) -> str:
        return self.corpus.texts[self.corpus.index_of[pid]]


def class_mask(res: Resources, entity_class: str | None, subject_family: str | None) -> np.ndarray | None:
    if entity_class is None:
        return None
    mask = res.corpus.entity_class == entity_class
    if subject_family:
        mask = mask | (res.heading_mask & (res.family_of == subject_family))
    return mask


def retrieve(res: Resources, query: str, *, exclude_pid: str | None, entity_class: str | None,
             subject_family: str | None, class_filter: bool, depth: int, rrf_k: int = 60) -> list[str]:
    n = len(res.corpus)
    mask = np.ones(n, dtype=bool)
    if exclude_pid is not None and exclude_pid in res.corpus.index_of:
        mask[res.corpus.index_of[exclude_pid]] = False
    if class_filter and entity_class is not None:
        mask &= class_mask(res, entity_class, subject_family)
    bm = res.bm25.scores(query)
    dn = res.emb @ res.encoder(query)
    ranked = S.rrf(bm, dn, mask, k=rrf_k, depth=depth)
    return [res.corpus.ids[i] for i in ranked.indices]


def apply_temporal(res: Resources, pids: Sequence[str], as_of: str | None, *, keep: Sequence[str] = ()) -> tuple[list[str], dict[str, dict]]:
    """Drop paragraphs deleted as of ``as_of`` (except ``keep``); return the survivors and their statuses."""
    if not as_of:
        return list(pids), {}
    out, status = [], {}
    for p in pids:
        st = res.temporal.status(p, as_of)
        if st["state"] == "deleted" and p not in keep:
            continue
        out.append(p)
        if st["notes"]:
            status[p] = st
    return out, status


def format_paragraph(res: Resources, pid: str, status: Mapping[str, Any] | None = None, *, max_chars: int | None = None) -> str:
    md = res.corpus.md_id[res.corpus.index_of[pid]]
    d = res.doc.get(md, {})
    text = " ".join(res.text(pid).split())
    cap = max_chars or res.paragraph_max_chars
    if len(text) > cap:
        text = text[:cap] + " [...]"
    head = f"[{pid}] (Direction {md}: {d.get('title', '')}; entity class: {d.get('entity_class', '')})"
    notes = "".join(f"\n  STATUS: {n}" for n in (status or {}).get("notes", []))
    return f"{head}{notes}\n{text}"


def parse_json(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return v if isinstance(v, dict) else None


# -- T1 -------------------------------------------------------------------------------------------


@dataclass
class T1Config:
    class_filter: bool
    verifier: bool
    per_class: int = 5
    depth: int = 20
    max_output_tokens: int = 4096


def t1_evidence(res: Resources, item: Mapping[str, Any], query: str, cfg: T1Config) -> tuple[str, dict[str, list[str]]]:
    """Evidence text and the ids shown per compared class (class-blind: one shared pool under key '*')."""
    classes = sorted(item["compared_classes"])
    if cfg.class_filter:
        shown = {c: retrieve(res, query, exclude_pid=item["paragraph_id"], entity_class=c,
                             subject_family=item.get("subject_family"), class_filter=True,
                             depth=cfg.depth)[:cfg.per_class] for c in classes}
        blocks = [f"=== Compared class: {c} ===\n" + "\n\n".join(format_paragraph(res, p) for p in shown[c]) for c in classes]
    else:
        pool = retrieve(res, query, exclude_pid=item["paragraph_id"], entity_class=None, subject_family=None,
                        class_filter=False, depth=max(cfg.depth, cfg.per_class * len(classes)))[:cfg.per_class * len(classes)]
        shown = {"*": pool}
        blocks = ["=== Evidence paragraphs (any class; each shows its Direction's entity class) ===\n"
                  + "\n\n".join(format_paragraph(res, p) for p in pool)]
    return "\n\n".join(blocks), shown


def t1_messages(prompts: Prompts, res: Resources, item: Mapping[str, Any], evidence: str) -> list[dict[str, str]]:
    md = item["md_id"]
    return prompts.messages("t1", source_class=item["entity_class"], source_title=res.doc.get(md, {}).get("title", ""),
                            source_paragraph_id=item["paragraph_id"], source_text=" ".join(item["obligation_span"]["text"].split()),
                            compared_classes="; ".join(sorted(item["compared_classes"])), evidence=evidence)


def parse_t1(raw: str, classes: Sequence[str]) -> tuple[dict[str, dict], list[str]]:
    """Per-class judgements; anything missing or malformed becomes ``unsure`` (and is reported)."""
    problems = []
    data = parse_json(raw)
    per = (data or {}).get("per_class") if data else None
    if not isinstance(per, dict):
        problems.append("unparseable JSON")
        per = {}
    out = {}
    for c in classes:
        v = per.get(c)
        if not isinstance(v, dict):
            problems.append(f"missing class {c}")
            out[c] = {"judgement": "unsure", "matched_paragraph_id": None, "rationale": "", "valid": False}
            continue
        j = str(v.get("judgement") or "").strip().lower()
        if j not in JUDGEMENTS:
            problems.append(f"{c}: judgement {j!r}")
            j = "unsure"
        mid = v.get("matched_paragraph_id")
        mid = mid.strip() if isinstance(mid, str) and PID_RE.fullmatch(mid.strip()) else None
        out[c] = {"judgement": j, "matched_paragraph_id": mid if j in ("same", "different") else None,
                  "rationale": " ".join(str(v.get("rationale") or "").split()), "valid": True}
    return out, problems


def t1_check(res: Resources, per: Mapping[str, dict], shown: Mapping[str, list[str]],
             verifier: NLIVerifier | None) -> dict[str, bool]:
    """same/different -> supported? (the matched id must be shown, from that class's Direction, and entail the rationale)."""
    todo, keys = [], []
    result: dict[str, bool] = {}
    for c, v in per.items():
        if v["judgement"] not in ("same", "different"):
            continue
        mid = v["matched_paragraph_id"]
        pool = shown.get(c, shown.get("*", []))
        ok_id = bool(mid) and mid in pool and res.corpus.entity_class[res.corpus.index_of[mid]] == c
        if not ok_id or not v["rationale"]:
            result[c] = False
            continue
        if verifier is None:
            result[c] = True
            continue
        todo.append((res.text(mid), v["rationale"]))
        keys.append(c)
    if verifier is not None:
        for c, ok in zip(keys, verifier.supported(todo)):
            result[c] = ok
    return result


def derive(per: Mapping[str, dict], source_class: str) -> dict[str, Any]:
    j = {c: v["judgement"] for c, v in per.items()}
    flag = derive_flag(j)
    applies = sorted({source_class, *(c for c, v in j.items() if v in ("same", "different"))})
    return {"flag": flag["flag"] or "ambiguous", "ambiguous": flag["ambiguous"], "applies_to": applies}


def run_t1_item(res: Resources, prompts: Prompts, llm: Any, verifier: NLIVerifier | None, item: Mapping[str, Any],
                cfg: T1Config) -> dict[str, Any]:
    classes = sorted(item["compared_classes"])
    query = " ".join(item["obligation_span"]["text"].split())
    log: dict[str, Any] = {"item_id": item["item_id"], "class_filter": cfg.class_filter, "verifier": cfg.verifier,
                           "temporal_filter": "inactive (T1 items carry no as-of date)", "steps": []}
    evidence, shown = t1_evidence(res, item, query, cfg)
    msgs = t1_messages(prompts, res, item, evidence)
    c = llm.complete(msgs, max_output_tokens=cfg.max_output_tokens)
    per, problems = parse_t1(c.text, classes)
    step = {"attempt": 1, "shown": shown, "cached": c.cached, "model": c.model, "model_version": c.model_version,
            "raw": c.text, "parse_problems": problems, "per_class": per}
    log["steps"].append(step)
    if cfg.verifier:
        sup = t1_check(res, per, shown, verifier)
        step["supported"] = sup
        bad = [k for k, ok in sup.items() if not ok]
        if bad:
            query2 = query + " " + " ".join(per[k]["rationale"] for k in bad if per[k]["rationale"])
            evidence2, shown2 = t1_evidence(res, item, query2, cfg)
            c2 = llm.complete(t1_messages(prompts, res, item, evidence2), max_output_tokens=cfg.max_output_tokens)
            per, problems2 = parse_t1(c2.text, classes)
            sup2 = t1_check(res, per, shown2, verifier)
            log["steps"].append({"attempt": 2, "unsupported_classes": bad, "shown": shown2,
                                 "cached": c2.cached, "model": c2.model, "raw": c2.text,
                                 "parse_problems": problems2, "per_class": per, "supported": sup2})
            for k, ok in sup2.items():
                if not ok:
                    per[k] = {**per[k], "judgement": "unsure", "matched_paragraph_id": None, "abstained": True}
    final = {k: {kk: vv for kk, vv in v.items() if kk != "valid"} for k, v in per.items()}
    log["final"] = {"per_class": final, **derive(final, item["entity_class"])}
    log["calls"] = sum(1 for s in log["steps"] if not s["cached"])
    log["retried"] = len(log["steps"]) > 1
    return log


# -- general answer (T4, demo) ---------------------------------------------------------------------


@dataclass
class AnswerConfig:
    class_filter: bool = True
    temporal_filter: bool = True
    verifier: bool = True
    depth: int = 20
    answer_top: int = 5
    max_output_tokens: int = 4096


def _answer_evidence(res: Resources, query: str, *, entity_class: str | None, subject_family: str | None,
                     as_of: str | None, cfg: AnswerConfig, exclude_pid: str | None = None,
                     pin: Sequence[str] = ()) -> tuple[list[str], dict[str, dict], list[str]]:
    ranked = retrieve(res, query, exclude_pid=exclude_pid, entity_class=entity_class, subject_family=subject_family,
                      class_filter=cfg.class_filter, depth=cfg.depth)
    ranked = list(pin) + [p for p in ranked if p not in pin]
    kept, status = apply_temporal(res, ranked, as_of if cfg.temporal_filter else None, keep=pin)
    dropped = [p for p in ranked if p not in kept]
    return kept[:cfg.answer_top], status, dropped


def split_answer(data: Mapping[str, Any] | None) -> tuple[bool, list[dict]]:
    if not data:
        return False, []
    sents = []
    for s in data.get("sentences") or []:
        if isinstance(s, dict) and str(s.get("text") or "").strip():
            cites = [c for c in (s.get("citations") or []) if isinstance(c, str) and PID_RE.fullmatch(c.strip())]
            sents.append({"text": " ".join(str(s["text"]).split()), "citations": [c.strip() for c in cites]})
    return bool(data.get("can_answer")) and bool(sents), sents


def verify_sentences(res: Resources, sents: Sequence[Mapping[str, Any]], shown: Sequence[str],
                     verifier: NLIVerifier) -> list[bool]:
    """Premise = the cited paragraph(s) (only ids actually shown count); an uncited sentence is unsupported."""
    pairs, idx, out = [], [], [False] * len(sents)
    for i, s in enumerate(sents):
        cites = [c for c in s["citations"] if c in shown]
        if cites:
            pairs.append((" ".join(" ".join(res.text(c).split()) for c in cites), s["text"]))
            idx.append(i)
    for i, ok in zip(idx, verifier.supported(pairs)):
        out[i] = ok
    return out


def answer(res: Resources, prompts: Prompts, llm: Any, verifier: NLIVerifier | None, query: str, *,
           entity_class: str | None = None, subject_family: str | None = None, as_of: str | None = None,
           cfg: AnswerConfig | None = None, exclude_pid: str | None = None) -> dict[str, Any]:
    cfg = cfg or AnswerConfig()
    log: dict[str, Any] = {"query": query, "entity_class": entity_class, "as_of": as_of,
                           "flags": {"class_filter": cfg.class_filter, "temporal_filter": cfg.temporal_filter,
                                     "verifier": cfg.verifier}, "steps": []}

    def one(q: str) -> dict[str, Any]:
        shown, status, dropped = _answer_evidence(res, q, entity_class=entity_class, subject_family=subject_family,
                                                  as_of=as_of, cfg=cfg, exclude_pid=exclude_pid)
        ev = "\n\n".join(format_paragraph(res, p, status.get(p)) for p in shown)
        c = llm.complete(prompts.messages("answer", query=query, entity_class=entity_class or "(not given)",
                                          as_of=as_of or "(not given)", evidence=ev), max_output_tokens=cfg.max_output_tokens)
        can, sents = split_answer(parse_json(c.text))
        return {"query_used": q, "shown": shown, "status": status, "dropped_by_temporal": dropped,
                "cached": c.cached, "model": c.model, "raw": c.text, "can_answer": can, "sentences": sents}

    s1 = one(query)
    log["steps"].append(s1)
    final = s1
    if cfg.verifier and s1["can_answer"]:
        sup = verify_sentences(res, s1["sentences"], s1["shown"], verifier)
        s1["supported"] = sup
        if not all(sup):
            s2 = one(query + " " + " ".join(s["text"] for s, ok in zip(s1["sentences"], sup) if not ok))
            log["steps"].append(s2)
            final = s2
            if s2["can_answer"]:
                s2["supported"] = verify_sentences(res, s2["sentences"], s2["shown"], verifier)
    abstained = bool(cfg.verifier and final["can_answer"] and not all(final.get("supported", [True])))
    log["result"] = {
        "can_answer": final["can_answer"] and not abstained,
        "abstained_by_verifier": abstained,
        "answer": ABSTAIN if abstained else (" ".join(s["text"] for s in final["sentences"]) if final["can_answer"] else "cannot answer"),
        "sentences": final["sentences"], "supported": final.get("supported"), "evidence": final["shown"],
    }
    log["calls"] = sum(1 for s in log["steps"] if not s["cached"])
    return log


# -- T3 -------------------------------------------------------------------------------------------------


def t3_query(item: Mapping[str, Any], title: str) -> str:
    return (f"As of {item['as_of']}, what is the status of paragraph {item['paragraph_id']} of {title}, "
            "and which instrument governs it?")


def run_t3_item(res: Resources, prompts: Prompts, llm: Any, item: Mapping[str, Any], *, temporal_filter: bool,
                cfg: AnswerConfig) -> dict[str, Any]:
    """The target paragraph is pinned into the evidence (a deleted one stays, marked); the verifier does not
    apply (the output is a status, not sentences)."""
    md = item["md_id"]
    title = res.doc.get(md, {}).get("title", "")
    q = t3_query(item, title)
    c2 = AnswerConfig(class_filter=cfg.class_filter, temporal_filter=temporal_filter, verifier=False,
                      depth=cfg.depth, answer_top=cfg.answer_top, max_output_tokens=cfg.max_output_tokens)
    shown, status, dropped = _answer_evidence(res, q, entity_class=res.doc.get(md, {}).get("entity_class"),
                                              subject_family=None, as_of=item["as_of"], cfg=c2,
                                              pin=[item["paragraph_id"]])
    ev = "\n\n".join(format_paragraph(res, p, status.get(p)) for p in shown)
    c = llm.complete(prompts.messages("t3", query=q, evidence=ev), max_output_tokens=cfg.max_output_tokens)
    data = parse_json(c.text) or {}
    st = str(data.get("status") or "").strip()
    gov = str(data.get("governing_instrument") or "").strip()
    return {"t3_id": item["t3_id"], "temporal_filter": temporal_filter, "query": q, "shown": shown,
            "status_notes": status, "dropped_by_temporal": dropped, "cached": c.cached, "model": c.model,
            "raw": c.text, "pred_status": st, "pred_governing_instrument": gov, "calls": 0 if c.cached else 1}


# -- long-context T1 -----------------------------------------------------------------------------------


def long_context_messages(prompts: Prompts, res: Resources, item: Mapping[str, Any], *, max_input_tokens: int,
                          paras_by_md: Mapping[str, Sequence[Mapping[str, Any]]]) -> tuple[list[dict], dict[str, Any]]:
    """Source paragraph + the full text of the compared classes' Directions in the item's subject family.
    Over the cap, each class's text is cut proportionally (whole paragraphs kept from the start)."""
    fam = item.get("subject_family")
    per_class: dict[str, list[str]] = {}
    for c in sorted(item["compared_classes"]):
        lines = []
        for md, d in sorted(res.doc.items()):
            if d.get("entity_class") == c and d.get("subject_family") == fam:
                lines.append(f"### Direction {md}: {d.get('title', '')} (entity class: {c})")
                lines += [f"[{p['paragraph_id']}] " + " ".join(res.text(p["paragraph_id"]).split()) for p in paras_by_md.get(md, [])]
        per_class[c] = lines
    base = prompts.messages("long_context", source_class=item["entity_class"], source_title=res.doc.get(item["md_id"], {}).get("title", ""),
                            source_paragraph_id=item["paragraph_id"], source_text=" ".join(item["obligation_span"]["text"].split()),
                            compared_classes="; ".join(sorted(item["compared_classes"])), directions="")
    budget_chars = max_input_tokens * 4 - sum(len(m["content"]) for m in base)
    total = sum(len(l) + 1 for ls in per_class.values() for l in ls)
    trunc: dict[str, Any] = {"total_chars": total, "budget_chars": budget_chars, "classes": {}}
    scale = min(1.0, budget_chars / total) if total else 1.0
    blocks = []
    for c, ls in per_class.items():
        cap = int(sum(len(l) + 1 for l in ls) * scale)
        kept, used = [], 0
        for l in ls:
            if used + len(l) + 1 > cap:
                break
            kept.append(l)
            used += len(l) + 1
        trunc["classes"][c] = {"lines": len(ls), "kept_lines": len(kept), "truncated": len(kept) < len(ls)}
        blocks.append(f"=== Compared class: {c} ===\n" + "\n".join(kept))
    trunc["truncated"] = any(v["truncated"] for v in trunc["classes"].values())
    msgs = prompts.messages("long_context", source_class=item["entity_class"], source_title=res.doc.get(item["md_id"], {}).get("title", ""),
                            source_paragraph_id=item["paragraph_id"], source_text=" ".join(item["obligation_span"]["text"].split()),
                            compared_classes="; ".join(sorted(item["compared_classes"])), directions="\n\n".join(blocks))
    trunc["input_chars"] = sum(len(m["content"]) for m in msgs)
    return msgs, trunc


def run_long_context_item(res: Resources, prompts: Prompts, llm: Any, item: Mapping[str, Any], *, max_input_tokens: int,
                          paras_by_md: Mapping[str, Sequence[Mapping[str, Any]]], max_output_tokens: int = 4096) -> dict[str, Any]:
    msgs, trunc = long_context_messages(prompts, res, item, max_input_tokens=max_input_tokens, paras_by_md=paras_by_md)
    c = llm.complete(msgs, role="long_context", max_output_tokens=max_output_tokens)
    per, problems = parse_t1(c.text, sorted(item["compared_classes"]))
    final = {k: {kk: vv for kk, vv in v.items() if kk != "valid"} for k, v in per.items()}
    return {"item_id": item["item_id"], "system": "long_context", "truncation": trunc, "cached": c.cached,
            "model": c.model, "model_version": c.model_version, "raw": c.text, "parse_problems": problems,
            "final": {"per_class": final, **derive(final, item["entity_class"])},
            "calls": 0 if c.cached else 1, "input_tokens": c.input_tokens}


# -- run bookkeeping ------------------------------------------------------------------------------------


def today_iso() -> str:
    return _dt.date.today().isoformat()
