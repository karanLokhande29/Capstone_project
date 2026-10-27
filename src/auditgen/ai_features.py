"""Generative-AI features of the audit generator (local LLM only; see src/auditgen/genai.py for the rules).

1. ``ask``: question answering over the pack's applicable obligations (bge + BM25 retrieval, cited answer, NLI check,
   one retry, abstain).
2. ``explain_obligation``: plain-language summary, who must act, the actions and the deadline of one register row.
3. ``explain_change``: what an amendment changed in one paragraph, and its impact.
4. ``memo``: an executive memo drafted from the pack's own numbers (every number must come from the facts).
5. ``action_plan``: prioritised actions, each tied to a calendar entry, a change or a gap row of the pack.
6. ``draft_clause``: a policy clause for an obligation, scored by the gap analyser's own covered/partial/missing rule.
7. ``calendar_check``: LLM extraction of the deadline or frequency, compared with the rule-based extraction.
8. ``diff_second_opinion``: field-level comparison of a differential pair, decided by the frozen comparator rule.
9. ``review_suggestion``: a suggested review status with a verified reason; it never changes the row.

Inputs are RBI text from the local corpus and the pack's own rows. No feature reads uploaded company documents.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np

from src.auditgen import genai as G
from src.auditgen.corpus import ROOT, CorpusStore

_TOK = re.compile(r"[a-z0-9]+")
STOP = set("the a an of to and or in on for by with is are be shall should must may any all such as at from that this "
           "which it its their they than other under within into not no if per each every".split())


class FeatureError(ValueError):
    pass


# -- shared helpers -----------------------------------------------------------------------------------------------------

def para_text(store: CorpusStore, pid: str | None) -> str:
    return " ".join(((store.paragraphs.get(pid or "") or {}).get("text") or "").split())


def row_by_id(pack: Mapping[str, Any], section: str, row_id: str) -> dict[str, Any]:
    rows = pack.get(section)
    if isinstance(rows, dict):
        rows = rows.get("rows")
    for r in rows or []:
        if r.get("row_id") == row_id:
            return r
    raise FeatureError(f"no {section} row {row_id}")


def cite(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in ("row_id", "md_id", "paragraph_id", "direction_title", "source_url")}


def _sys(text: str) -> dict[str, str]:
    return {"role": "system", "content": text}


def _user(text: str) -> dict[str, str]:
    return {"role": "user", "content": text}


GROUND = ("You help an Indian regulated entity's compliance team read Reserve Bank of India (RBI) Master Directions. "
          "Use ONLY the text you are given. Do not use outside knowledge. Stay close to the wording of the source so that "
          "every sentence can be checked against it. Never invent numbers, dates, section numbers or names. "
          "Reply with one JSON object only.")


# -- 1. ask the pack ----------------------------------------------------------------------------------------------------

def _tokens(s: str) -> list[str]:
    return [t for t in _TOK.findall((s or "").lower()) if t not in STOP and len(t) > 1]


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.2, b: float = 0.75):
        self.tf = [Counter(_tokens(d)) for d in docs]
        self.len = np.array([sum(t.values()) for t in self.tf], dtype=np.float32)
        self.avg = float(self.len.mean()) if len(docs) else 1.0
        df: Counter = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, q: str) -> np.ndarray:
        out = np.zeros(len(self.tf), dtype=np.float32)
        for w in set(_tokens(q)):
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(w)
                if f:
                    out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return out


class Retriever:
    """bge + BM25 over the pack's visible register rows, fused by reciprocal rank. bge vectors of RBI paragraphs are
    cached on disk per corpus snapshot (RBI text only; never company text)."""

    _cache: dict[tuple[str, ...], "Retriever"] = {}

    def __init__(self, store: CorpusStore, gcfg: Mapping[str, Any], models, pack: Mapping[str, Any]):
        a = gcfg["ask"]
        self.rows = [r for r in pack["register"] if not r["hidden"] and r.get("paragraph_id")]
        seen, rows = set(), []
        for r in self.rows:
            if r["paragraph_id"] not in seen:
                seen.add(r["paragraph_id"])
                rows.append(r)
        self.rows = rows
        self.texts = [G.words(para_text(store, r["paragraph_id"]) or r.get("excerpt") or "", int(a["passage_max_words"])) for r in rows]
        self.docs = [f"{r['direction_title']}. {t}" for r, t in zip(rows, self.texts)]
        self.bm25 = BM25(self.docs)
        self.models = models
        self.vecs = self._vectors(store, gcfg)
        self.k = int(a["rrf_k"])

    def _vectors(self, store: CorpusStore, gcfg: Mapping[str, Any]) -> np.ndarray:
        ids = [r["paragraph_id"] for r in self.rows]
        if not ids:
            return np.zeros((0, 1), dtype=np.float32)
        tag = getattr(self.models, "ids", {}).get("embedding", "model")
        path = ROOT / gcfg["storage"]["ai_cache"] / f"emb_{store.snapshot.sha256[:12]}_{G.sha(tag)[:8]}.npz"
        known: dict[str, np.ndarray] = {}
        if path.exists():
            z = np.load(path, allow_pickle=False)
            known = dict(zip(z["ids"].tolist(), z["vecs"]))
        missing = [i for i, pid in enumerate(ids) if pid not in known]
        if missing:
            v = self.models.embed([self.docs[i] for i in missing])
            for i, row in zip(missing, v):
                known[ids[i]] = row
            path.parent.mkdir(parents=True, exist_ok=True)
            keys = sorted(known)
            np.savez(path, ids=np.array(keys), vecs=np.stack([known[k] for k in keys]).astype(np.float32))
        return np.stack([known[pid] for pid in ids]).astype(np.float32)

    @classmethod
    def get(cls, store, gcfg, models, pack) -> "Retriever":
        key = (pack["pack_id"], pack.get("created_utc", ""), str(gcfg["storage"]["ai_cache"]),
               getattr(models, "ids", {}).get("embedding", type(models).__name__))
        if key not in cls._cache:
            cls._cache.clear()
            cls._cache[key] = cls(store, gcfg, models, pack)
        return cls._cache[key]

    def search(self, query: str, depth: int) -> list[tuple[int, float]]:
        if not self.rows:
            return []
        q = self.models.embed([query])[0]
        dense = self.vecs @ q
        lex = self.bm25.scores(query)
        fused = np.zeros(len(self.rows), dtype=np.float64)
        for arr in (dense, lex):
            order = np.argsort(-arr)[:depth]
            for rank, i in enumerate(order):
                fused[i] += 1.0 / (self.k + rank + 1)
        top = np.argsort(-fused)[:depth]
        return [(int(i), float(fused[i])) for i in top if fused[i] > 0]


ASK_FORMAT = ('{"can_answer": true, "sentences": [{"text": "one short sentence", "citations": ["E1"]}]}  '
              'or {"can_answer": false, "sentences": []}')


def _ask_messages(question: str, history: Sequence[Mapping[str, str]], evidence: Sequence[Mapping[str, Any]], strict: bool) -> list[dict]:
    ev = "\n\n".join(f"[{e['label']}] {e['direction_title']} | status: {e['status']}"
                     f"{' | deadline/frequency: ' + e['deadline'] if e.get('deadline') else ''}\n{e['text']}" for e in evidence)
    hist = "".join(f"Earlier question: {h.get('question', '')}\n" for h in history)
    rule = ("Every sentence must restate what its cited evidence paragraph says, using the paragraph's own words where "
            "possible. Cite each sentence with the evidence label(s) it rests on, e.g. [\"E2\"]. "
            "If the evidence answers the question only in part, answer that part (can_answer true). Reply can_answer "
            "false only when no evidence paragraph is about the question.")
    if strict:
        rule += (" Your previous answer had sentences the evidence does not support. Answer again with fewer, simpler "
                 "sentences that copy the evidence wording closely.")
    return [_sys(GROUND), _user(f"{hist}QUESTION: {question}\n\nEVIDENCE:\n{ev}\n\n{rule}\n\nReply in this JSON shape: {ASK_FORMAT}")]


def ask(store: CorpusStore, cfg: Mapping[str, Any], gcfg: Mapping[str, Any], pack: Mapping[str, Any], question: str, *,
        llm: G.LocalLLM, models, history: Sequence[Mapping[str, str]] = (), model: str | None = None) -> dict[str, Any]:
    a = gcfg["ask"]
    question = " ".join((question or "").split())
    if not question:
        raise FeatureError("empty question")
    if len(question) > int(a["max_question_chars"]):
        raise FeatureError(f"question longer than {a['max_question_chars']} characters")
    t0 = time.monotonic()
    history = list(history)[-int(a["history_turns"]):]
    # A short follow-up ("and for NBFCs?") borrows the previous question for retrieval; a full question stands alone.
    follow_up = bool(history) and len(question.split()) <= 6
    query = f"{history[-1].get('question', '')} {question}" if follow_up else question
    ret = Retriever.get(store, gcfg, models, pack)
    hits = ret.search(query, int(a["retrieve_depth"]))[: int(a["evidence"])]
    evidence = []
    for n, (i, score) in enumerate(hits, 1):
        r = ret.rows[i]
        evidence.append({"label": f"E{n}", **cite(r), "status": r.get("status"), "deadline": r.get("deadline_frequency") or "",
                         "subject_family": r.get("subject_family"), "text": ret.texts[i], "excerpt": r.get("excerpt"),
                         "score": round(score, 5)})
    by_label = {e["label"]: e for e in evidence}
    model_used, attempts, sents = None, 0, []
    if evidence:
        for strict in (False, True):
            attempts += 1
            out = llm.chat(_ask_messages(question, history, evidence, strict), model=model)
            model_used = out["model"]
            j = out["json"] or {}
            raw = j.get("sentences") if j.get("can_answer", True) else []
            items = []
            for s in raw or []:
                if not isinstance(s, dict) or not str(s.get("text") or "").strip():
                    continue
                labels = [str(c).strip().strip("[]") for c in (s.get("citations") or []) if isinstance(c, (str, int))]
                labels = [lb if lb.startswith("E") else f"E{lb}" for lb in labels]
                valid = [lb for lb in labels if lb in by_label]
                items.append({"text": str(s["text"]).strip(), "citations": valid,
                              "premises": [by_label[lb]["text"] for lb in valid]})
            sents = G.verify(models, items, premise_max_words=int(gcfg["verifier"]["premise_max_words"]))
            if sents and all(s["verified"] for s in sents):
                break
            if not sents and not (j.get("can_answer", True)):
                break
    kept = [s for s in sents if s["verified"]]
    for s in sents:
        s["sources"] = [{k: by_label[lb][k] for k in ("label", "row_id", "paragraph_id", "direction_title", "source_url")}
                        for lb in s["citations"]]
    res = G.envelope(gcfg, cfg, model_used, time.monotonic() - t0, question, question=question, attempts=attempts,
                     sentences=sents, abstained=not kept,
                     answer=" ".join(s["text"] for s in kept) if kept else "I cannot answer this reliably from this pack's obligations. "
                     "The closest evidence is listed below.",
                     evidence=[{k: v for k, v in e.items() if k != "text"} for e in evidence])
    return res


# -- 2. explain one obligation ------------------------------------------------------------------------------------------

def explain_obligation(store, cfg, gcfg, pack, row_id: str, *, llm: G.LocalLLM, models, model: str | None = None) -> dict[str, Any]:
    r = row_by_id(pack, "register", row_id)
    text = para_text(store, r["paragraph_id"])
    if not text:
        raise FeatureError("no corpus text for this row")
    t0 = time.monotonic()
    prompt = (f"ENTITY: a {pack['profile']['entity_class']} entity.\nDIRECTION: {r['direction_title']}\n"
              f"PARAGRAPH {r['paragraph_id']} (status as of {pack['profile']['as_of']}: {r['status']}):\n{text}\n\n"
              "Explain this paragraph for a compliance officer. Reply in this JSON shape:\n"
              '{"plain_summary": ["one or two short sentences saying what the paragraph requires"], '
              '"who_must_act": "who the paragraph puts the duty on, in its own words", '
              '"actions": ["each concrete thing the entity must do, one per item"], '
              '"deadline_or_frequency": "the deadline or frequency the paragraph states, or null", '
              '"evidence_quote": "an exact quote of 5 to 20 words from the paragraph that carries the main duty"}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    summary = j.get("plain_summary") or []
    if isinstance(summary, str):
        summary = G.sentences(summary)
    items = [{"part": "summary", "text": str(s)} for s in summary if str(s).strip()]
    items += [{"part": "action", "text": str(s)} for s in (j.get("actions") or []) if str(s).strip()]
    if j.get("who_must_act"):
        items.append({"part": "who", "text": str(j["who_must_act"])})
    dl = j.get("deadline_or_frequency")
    if dl and str(dl).lower() not in ("null", "none", "n/a", ""):
        items.append({"part": "deadline", "text": str(dl)})
    for it in items:
        it["premise"] = text
    checked = G.verify(models, items, premise_max_words=int(gcfg["verifier"]["premise_max_words"]))
    # "who" and "deadline" are short phrases, not claims; a phrase passes when it is quoted from the paragraph.
    for it in checked:
        if it["part"] in ("who", "deadline") and not it["verified"] and G.quote_in(it["text"], text):
            it["verified"], it["reason"] = True, "phrase found in the paragraph"
    quote = str(j.get("evidence_quote") or "")
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, text, row=cite(r), sentences=checked,
                      evidence_quote=quote, evidence_quote_found=G.quote_in(quote, text),
                      rule_deadline=r.get("deadline_frequency") or "", status=r.get("status"))


# -- 3. explain a change ------------------------------------------------------------------------------------------------

def explain_change(store, cfg, gcfg, pack, row_id: str, *, llm: G.LocalLLM, models, model: str | None = None) -> dict[str, Any]:
    r = row_by_id(pack, "changes", row_id)
    pid = r.get("paragraph_id")
    if not pid:
        return G.envelope(gcfg, cfg, None, 0.0, row_id, row=cite(r), sentences=[], abstained=True,
                          note="This is a Direction-level change (the consolidated 'Updated as on' date moved). The changed "
                               "paragraphs are not identified, so there is nothing to compare. Read the updated Direction.")
    old = para_text(store, pid)
    events = [e for e in store.temporal().events.get(pid, []) if e.item_id == r.get("governing_instrument")]
    ev = events[0] if events else None
    new = (ev.new_text if ev else None) or ""
    amd = (getattr(store, "amendments", {}) or {}).get(r.get("governing_instrument"), {})
    premise = f"{old} Amendment ({(ev.title if ev else r.get('governing_title')) or ''}): action {ev.action if ev else r['change']}. {new}"
    t0 = time.monotonic()
    prompt = (f"PARAGRAPH {pid} BEFORE THE AMENDMENT:\n{old}\n\nAMENDMENT: {r.get('governing_title')} "
              f"(effective {r.get('effective') or 'date unknown'}). Action: {ev.action if ev else r['change']}"
              f" ({ev.scope if ev else 'scope unknown'}).\nNEW TEXT FROM THE AMENDMENT: {new or '(none: the paragraph is deleted or the new text is not available)'}\n\n"
              "Say what changed. Reply in this JSON shape:\n"
              '{"what_changed": ["short sentences on what the amendment does to this paragraph"], '
              '"impact": ["short sentences on what the entity must now do differently, only if the texts say so"]}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    items = [{"part": "what_changed", "text": str(s), "premise": premise} for s in (j.get("what_changed") or []) if str(s).strip()]
    items += [{"part": "impact", "text": str(s), "premise": premise} for s in (j.get("impact") or []) if str(s).strip()]
    checked = G.verify(models, items, premise_max_words=int(gcfg["verifier"]["premise_max_words"]))
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, premise, row=cite(r), sentences=checked,
                      change=r["change"], amendment={"id": r.get("governing_instrument"), "title": r.get("governing_title"),
                                                     "url": r.get("governing_url"), "effective": r.get("effective"),
                                                     "published": amd.get("published_date")},
                      before_excerpt=G.words(old, 25), after_excerpt=G.words(new, 25) if new else None)


# -- 4 / 5. memo and action plan ----------------------------------------------------------------------------------------

def facts(pack: Mapping[str, Any], gcfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Numbered facts taken from the pack; the memo and the plan may only use these."""
    m, s, p = gcfg["memo"], pack["summary"], pack["profile"]
    out: list[dict[str, Any]] = []

    def add(text: str, ref: str | None = None, **kw: Any) -> None:
        out.append({"id": f"F{len(out) + 1}", "text": text, "ref": ref, **kw})

    add(f"Entity profile: {p['name']}, a {p['entity_class']} entity; as-of date {p['as_of']}; last review {p['last_review']}.")
    add(f"The applicability register has {s['register_visible']} applicable obligations shown and {s['register_hidden']} hidden.")
    add(f"{s['needs_review']} applicable obligations need human review.")
    for st, n in sorted(s.get("by_status", {}).items(), key=lambda x: -x[1]):
        add(f"{n} obligations have status '{st}'.")
    add(f"The change-impact log has {s['changes']} changes since {p['last_review']}.")
    add(f"The compliance calendar has {s['calendar_entries']} entries, of which {s['calendar_verify']} are marked verify.")
    if s.get("differential_rows"):
        add(f"The cross-class differential has {s['differential_rows']} rows, {s['differential_needs_review']} of which need review.")
    add(f"Enforcement view: {s['enforcement_releases']} RBI penalty press releases across {s['enforcement_directions']} Directions for this class.")
    for d in (s.get("by_direction") or [])[: int(m["top_directions"])]:
        add(f"Direction '{d['direction_title']}' contributes {d['obligations']} obligations.", None, md_id=d["md_id"], url=d["source_url"])
    changes = sorted(pack.get("changes") or [], key=lambda c: c.get("effective") or "", reverse=True)
    for c in changes[: int(m["top_changes"])]:
        add(f"Change ({c['change']}) to {c.get('paragraph_id') or c['md_id']} in '{c['direction_title']}', effective {c.get('effective') or 'unknown'}.",
            c["row_id"], url=c.get("governing_url") or c["source_url"])
    # One fact per calendar entry (a weekly entry has many dates in 90 days; listing each would repeat the same duty).
    cal = {e["entry_id"]: e for e in pack.get("calendar") or []}
    due: dict[str, dict[str, Any]] = {}
    for d in s.get("next_90_days") or []:
        due.setdefault(d["entry_id"], {**d, "dates": []})["dates"].append(d["date"])
    for d in list(due.values())[: int(m["next_deadlines"])]:
        when = d["dates"][0] if len(d["dates"]) == 1 else f"{d['dates'][0]} (then {len(d['dates']) - 1} more dates in the next 90 days)"
        e = cal.get(d["entry_id"]) or {}
        add(f"Deadline on {when}{' (verify)' if d['verify'] else ''}: {e.get('frequency') or e.get('kind') or ''} duty in "
            f"'{e.get('direction_title', '')}' ({d['paragraph_id']}): \"{e.get('excerpt', '')}\"", d["entry_id"], url=d["source_url"])
    g = pack.get("gaps") or {}
    if g:
        c = g.get("counts") or {}
        add(f"Policy gap analysis: {c.get('covered', 0)} covered, {c.get('partial', 0)} partial, {c.get('missing', 0)} missing.")
        for r in [x for x in g.get("rows", []) if x["coverage"] == "missing"][: int(m["top_gaps"])]:
            add(f"Missing in policy: {r['paragraph_id']} of '{r['direction_title']}' (enforcement releases {r.get('enforcement_risk', 0)}).",
                r["row_id"], url=r["source_url"])
    return out


def memo(store, cfg, gcfg, pack, *, llm: G.LocalLLM, models, model: str | None = None) -> dict[str, Any]:
    fs = facts(pack, gcfg)
    fact_text = "\n".join(f"{f['id']}: {f['text']}" for f in fs)
    by_id = {f["id"]: f for f in fs}
    t0 = time.monotonic()
    prompt = ("FACTS FROM THE AUDIT PACK:\n" + fact_text + "\n\nDraft a short executive memo to the board's audit "
              "committee about this compliance audit pack. Use only these facts; cite the fact ids each sentence uses. "
              "Do not compute new totals or percentages. Reply in this JSON shape:\n"
              '{"subject": "memo subject line", "sections": [{"heading": "Overview", "sentences": [{"text": "…", "facts": ["F2"]}]}, '
              '{"heading": "What changed", "sentences": []}, {"heading": "Upcoming deadlines", "sentences": []}, '
              '{"heading": "Risks and gaps", "sentences": []}, {"heading": "Recommended next steps", "sentences": []}]}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    sections = []
    for sec in j.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        items = []
        for s in sec.get("sentences") or []:
            if isinstance(s, str):
                s = {"text": s, "facts": []}
            if not isinstance(s, dict) or not str(s.get("text") or "").strip():
                continue
            ids = [str(x).strip("[] ") for x in (s.get("facts") or []) if str(x).strip("[] ") in by_id]
            items.append({"text": str(s["text"]).strip(), "facts": ids})
        sections.append({"heading": str(sec.get("heading") or ""), "sentences": check_facts(items, fs)})
    allsent = [s for sec in sections for s in sec["sentences"]]
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, fact_text, subject=str(j.get("subject") or "Compliance audit pack"),
                      sections=sections, sentences=allsent, facts=fs, profile=pack["profile"], pack_id=pack["pack_id"])


def check_facts(items: list[dict[str, Any]], fs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Memo sentences are checked against the pack's facts, not by NLI (the facts are numbers, not prose):

    - every number the sentence states must occur in the facts it cites (or, when it cites none, in some fact,
      which then becomes its citation);
    - a sentence with no number must cite at least one fact, and is labelled a recommendation or summary.
    """
    by_id = {f["id"]: f for f in fs}
    out = []
    for it in items:
        nums = G.numbers(it["text"])
        ids = list(it.get("facts") or [])
        if nums and not ids:
            ids = [f["id"] for f in fs if nums & G.numbers(f["text"])]
        have = set().union(*[G.numbers(by_id[i]["text"]) for i in ids]) if ids else set()
        stray = sorted(nums - have)
        if stray:
            ok, why = False, f"states a number not in the pack's facts ({', '.join(stray)})"
        elif not ids:
            ok, why = False, "cites no fact"
        else:
            ok, why = True, ("figures match " if nums else "no figures; grounded in ") + ", ".join(ids)
        out.append({"text": it["text"], "facts": ids, "verified": ok, "reason": why if not ok else "",
                    "check": why, "kind": "figures" if nums else "summary or recommendation"})
    return out


def action_plan(store, cfg, gcfg, pack, *, llm: G.LocalLLM, models, model: str | None = None) -> dict[str, Any]:
    fs = [f for f in facts(pack, gcfg) if f.get("ref")]
    if not fs:
        return G.envelope(gcfg, cfg, None, 0.0, pack["pack_id"], items=[], sentences=[], abstained=True,
                          note="This pack has no dated deadlines, changes or gaps to plan from.")
    by_id = {f["id"]: f for f in fs}
    fact_text = "\n".join(f"{f['id']}: {f['text']}" for f in fs)
    t0 = time.monotonic()
    prompt = ("ITEMS FROM THE AUDIT PACK (deadlines, changes, policy gaps):\n" + fact_text + "\n\nWrite a prioritised "
              "action plan: one action per item that needs work, most urgent first. Each action names exactly one item id. "
              "Do not add dates or numbers that are not in the item. Reply in this JSON shape:\n"
              '{"actions": [{"item": "F3", "priority": "high|medium|low", "action": "what to do", "why": "why, from the item"}]}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    items, seen = [], set()
    for a in j.get("actions") or []:
        if not isinstance(a, dict):
            continue
        fid = str(a.get("item") or "").strip("[] ")
        f = by_id.get(fid)
        text = str(a.get("action") or "").strip()
        why = str(a.get("why") or "").strip()
        if not text:
            continue
        stray = (G.numbers(text) | G.numbers(why)) - G.numbers(f["text"] if f else "")
        repeated = fid in seen or G.norm(text) in seen
        ok = f is not None and not repeated and not stray
        seen.update({fid, G.norm(text)})
        items.append({"item": fid, "ref": f["ref"] if f else None, "fact": f["text"] if f else None, "url": f.get("url") if f else None,
                      "priority": a.get("priority") if a.get("priority") in ("high", "medium", "low") else "medium",
                      "text": text, "why": why, "verified": ok,
                      "reason": "" if ok else ("unknown item id" if f is None else "repeated item" if repeated else
                                               f"states a number not in the item ({', '.join(sorted(stray))})")})
    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (not x["verified"], order[x["priority"]]))
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, fact_text, items=items, sentences=items, pack_id=pack["pack_id"])


# -- 6. draft a policy clause -------------------------------------------------------------------------------------------

def draft_clause(store, cfg, gcfg, pack, row_id: str, *, llm: G.LocalLLM, models, section: str = "register",
                 company: str = "the Company", model: str | None = None) -> dict[str, Any]:
    r = row_by_id(pack, section, row_id)
    pid = r["paragraph_id"]
    text = para_text(store, pid)
    if not text:
        raise FeatureError("no corpus text for this row")
    company = " ".join((company or "the Company").split())[:80] or "the Company"
    t0 = time.monotonic()
    prompt = (f"RBI OBLIGATION ({r['direction_title']}, {pid}):\n{text}\n\nDraft one clause for {company}'s internal "
              f"policy that would satisfy this obligation. Keep every duty, condition, number and deadline of the "
              f"obligation; add nothing it does not require. At most {gcfg['draft_clause']['max_words']} words. "
              'Reply in this JSON shape: {"title": "short clause title", "clause": "the clause text", '
              '"owner": "the function that should own it (e.g. Compliance, Operations)", "notes": "what a reviewer should check"}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    clause = G.words(str(j.get("clause") or ""), int(gcfg["draft_clause"]["max_words"]))
    score = _coverage(models, cfg, clause, store, r) if clause else {"coverage": "missing", "entailment": 0.0, "cosine": 0.0}
    stray = G.numbers(clause) - G.numbers(text)
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, text, row=cite(r), title=str(j.get("title") or ""),
                      clause=clause, owner=str(j.get("owner") or ""), notes=str(j.get("notes") or ""), check=score,
                      stray_numbers=sorted(stray), sentences=[{"text": clause, "verified": score["coverage"] == "covered" and not stray}],
                      company=company)


def _coverage(models, cfg, clause: str, store, r) -> dict[str, Any]:
    """The gap analyser's rule, applied to (draft clause → obligation sentence)."""
    g = cfg["gap_analysis"]
    cand = next((c for c in store.candidates() if c["candidate_id"] == r.get("obligation_id")), None)
    obl = store.obligation_sentence(cand) if cand else para_text(store, r["paragraph_id"])
    p, ok = models.nli_scores([(clause, obl)])
    v = models.embed([clause, obl])
    cos = float(np.dot(v[0], v[1]))
    pe = float(p[0])
    if bool(ok[0]) and pe >= float(g["covered_entailment"]):
        cov = "covered"
    elif pe >= float(g["partial_entailment"]) or cos >= float(g["partial_cosine"]):
        cov = "partial"
    else:
        cov = "missing"
    return {"coverage": cov, "entailment": round(pe, 4), "cosine": round(cos, 4), "obligation_sentence": G.words(obl, 25),
            "rule": "gap analyser: covered = NLI entailment ≥ %s; partial = entailment ≥ %s or cosine ≥ %s" %
                    (g["covered_entailment"], g["partial_entailment"], g["partial_cosine"])}


# -- 7. calendar check --------------------------------------------------------------------------------------------------

CAL_KINDS = ("recurring", "fixed", "event", "none")


def _cal_prompt(text: str) -> str:
    return (f"PARAGRAPH:\n{text}\n\nDoes this paragraph set a deadline or a frequency for the entity? Reply in this JSON "
            'shape: {"kind": "recurring|fixed|event|none", "frequency": "daily|weekly|fortnightly|monthly|quarterly|'
            'half-yearly|annually|null", "offset_days": null or a number of days, "trigger": "what starts the clock, or null", '
            '"due_date": "YYYY-MM-DD or null", "what": "what must be done or submitted", '
            '"quote": "the exact words of the paragraph that state the deadline or frequency"}. '
            "recurring = repeats on a frequency; fixed = a calendar date; event = within some time of an event; none = no deadline.")


def calendar_one(store, cfg, gcfg, text: str, rule: Mapping[str, Any] | None, *, llm: G.LocalLLM, model: str | None = None) -> dict[str, Any]:
    out = llm.chat([_sys(GROUND), _user(_cal_prompt(text))], model=model)
    j = out["json"] or {}
    kind = j.get("kind") if j.get("kind") in CAL_KINDS else "none"
    quote = str(j.get("quote") or "")
    found = G.quote_in(quote, text)
    freq = j.get("frequency") if isinstance(j.get("frequency"), str) and j.get("frequency") not in ("null", "") else None
    off = j.get("offset_days") if isinstance(j.get("offset_days"), (int, float)) else None
    ai = {"kind": kind, "frequency": freq, "offset_days": off, "trigger": j.get("trigger") or None, "due_date": j.get("due_date") or None,
          "what": str(j.get("what") or ""), "quote": quote, "quote_found": found}
    agree = None
    if rule:
        agree = (rule.get("kind") == kind) and (rule.get("kind") != "recurring" or (rule.get("frequency") or "") == (freq or "")) \
            and (rule.get("kind") != "event" or off is None or rule.get("offset_days") in (None, off))
    return {"ai": ai, "rule": dict(rule) if rule else None, "agrees_with_rule": agree, "verified": found and kind != "none",
            "model": out["model"], "seconds": out["seconds"]}


def calendar_check(store, cfg, gcfg, pack, entry_ids: Sequence[str] | None = None, *, llm: G.LocalLLM, model: str | None = None) -> dict[str, Any]:
    cal = pack.get("calendar") or []
    if entry_ids:
        rows = [row_by_id(pack, "calendar", e) for e in entry_ids]
    else:
        rows = [e for e in cal if e.get("verify")][: int(gcfg["calendar"]["batch_limit"])]
    t0 = time.monotonic()
    results, model_used = [], None
    for e in rows:
        text = para_text(store, e["paragraph_id"])
        if not text:
            continue
        rule = {k: e.get(k) for k in ("kind", "frequency", "offset_days", "phrase", "confidence")}
        res = calendar_one(store, cfg, gcfg, text, rule, llm=llm, model=model)
        model_used = res["model"]
        results.append({"entry_id": e["entry_id"], **cite(e), "summary": e.get("summary"), **res})
    agree = [r["agrees_with_rule"] for r in results if r["agrees_with_rule"] is not None]
    return G.envelope(gcfg, cfg, model_used, time.monotonic() - t0, json.dumps([r["entry_id"] for r in results]),
                      results=results, sentences=[{"verified": r["verified"]} for r in results],
                      agreement={"n": len(agree), "agree": sum(agree), "rate": round(sum(agree) / len(agree), 3) if agree else None},
                      note="Agreement with the rule-based extraction is not accuracy: neither is checked until the "
                           "calendar check sheet is labelled.")


# -- 8. differential second opinion -------------------------------------------------------------------------------------

def diff_second_opinion(store, cfg, gcfg, pack, row_id: str, *, llm: G.LocalLLM, model: str | None = None) -> dict[str, Any]:
    from src.rag import comparator_rule as CR

    r = row_by_id(pack, "differential", row_id)
    src_t, tgt_t = para_text(store, r["paragraph_id"]), para_text(store, r.get("counterpart_paragraph_id"))
    if not src_t or not tgt_t:
        return G.envelope(gcfg, cfg, None, 0.0, row_id, row=cite(r), sentences=[], abstained=True, judgement="none",
                          note="No counterpart paragraph in the target class, so there is nothing to compare.")
    t0 = time.monotonic()
    fields = ", ".join(CR.FIELDS)
    prompt = (f"SOURCE ({r['source_class']}, {r['paragraph_id']}):\n{src_t}\n\nTARGET ({r['target_class']}, "
              f"{r['counterpart_paragraph_id']}):\n{tgt_t}\n\nDo the two paragraphs state the same duty? For each field "
              f"({fields}) compare the two sides: equal, differs, only_source, only_target or absent. Reply in this JSON "
              'shape: {"addresses_same_duty": true, "field_comparison": {"actor": "equal", ...}, '
              '"differences": [{"field": "deadline", "source": "words from source", "target": "words from target"}]}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    fc = {f: (j.get("field_comparison") or {}).get(f) for f in CR.FIELDS}
    complete = isinstance(j.get("addresses_same_duty"), bool) and all(v in CR.COMPARISONS for v in fc.values())
    verdict = CR.candidate_verdict({"addresses_same_duty": j["addresses_same_duty"], "field_comparison": fc}) if complete else "unsure"
    diffs = []
    for d in j.get("differences") or []:
        if isinstance(d, dict) and d.get("field"):
            diffs.append({"field": str(d["field"]), "source": str(d.get("source") or ""), "target": str(d.get("target") or ""),
                          "source_found": G.quote_in(str(d.get("source") or ""), src_t),
                          "target_found": G.quote_in(str(d.get("target") or ""), tgt_t)})
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, src_t + tgt_t, row=cite(r), judgement=verdict,
                      rule=CR.RULE_VERSION, field_comparison=fc, differences=diffs, pack_label=r["differential"],
                      sentences=[{"verified": verdict != "unsure"}],
                      caution="Second opinion only. In RBI-ObliBench, LLM systems missed most 'different' cases "
                              "(56 of 78 gold units were missed by every LLM system). Review every call.")


# -- 9. review suggestion -----------------------------------------------------------------------------------------------

SUGGESTIONS = ("confirm", "dispute", "not applicable", "unsure")


def review_suggestion(store, cfg, gcfg, pack, section: str, row_id: str, *, llm: G.LocalLLM, models, model: str | None = None) -> dict[str, Any]:
    r = row_by_id(pack, section, row_id)
    text = para_text(store, r.get("paragraph_id")) or r.get("excerpt") or ""
    p = pack["profile"]
    profile_line = (f"The entity is a {p['entity_class']} entity. Its activities are: {', '.join(p['activities']) or 'none listed'}.")
    row_line = {k: r.get(k) for k in ("applies_to", "applicability_basis", "scope_note", "status", "coverage", "change",
                                      "differential", "deadline_frequency") if r.get(k)}
    t0 = time.monotonic()
    prompt = (f"{profile_line}\nROW ({section}) FROM THE AUDIT PACK: {json.dumps(row_line)}\nRBI PARAGRAPH "
              f"{r.get('paragraph_id')} ({r['direction_title']}):\n{text}\n\nShould a reviewer confirm this row, dispute it, "
              "or mark it not applicable to this entity? Reply in this JSON shape: "
              '{"suggestion": "confirm|dispute|not applicable|unsure", "reason": "one or two sentences quoting the paragraph", '
              '"check": "what the reviewer should check before deciding"}')
    out = llm.chat([_sys(GROUND), _user(prompt)], model=model)
    j = out["json"] or {}
    sug = j.get("suggestion") if j.get("suggestion") in SUGGESTIONS else "unsure"
    reasons = [{"text": s, "premise": f"{profile_line} {text}"} for s in G.sentences(str(j.get("reason") or ""))]
    checked = G.verify(models, reasons, premise_max_words=int(gcfg["verifier"]["premise_max_words"]))
    if not any(s["verified"] for s in checked):
        sug_shown = "unsure"
    else:
        sug_shown = sug
    return G.envelope(gcfg, cfg, out["model"], time.monotonic() - t0, text, row=cite(r), section=section,
                      suggestion=sug_shown, raw_suggestion=sug, sentences=checked, check=str(j.get("check") or ""),
                      current_review_status=r.get("review_status"),
                      note="A suggestion only: the row's review status is unchanged until a person applies it.")


def memo_docx(res: Mapping[str, Any]) -> bytes:
    """The memo as a DOCX: verified sentences only, each with its fact ids, plus the label and disclaimer."""
    import io

    import docx

    d = docx.Document()
    d.add_heading(res.get("subject") or "Compliance audit pack memo", level=1)
    p = res.get("profile") or {}
    d.add_paragraph(f"{p.get('name', '')} · {p.get('entity_class', '')} · as of {p.get('as_of', '')} · pack {res.get('pack_id', '')}")
    d.add_paragraph(f"{res.get('label')} Model: {res.get('model')}. Verifier: {res.get('verifier')}.").italic = True
    for sec in res.get("sections") or []:
        kept = [s for s in sec["sentences"] if s.get("verified")]
        if not kept:
            continue
        d.add_heading(sec["heading"] or "Notes", level=2)
        d.add_paragraph(" ".join(f"{s['text']} [{', '.join(s.get('facts') or [])}]" for s in kept))
    d.add_heading("Facts used", level=2)
    for f in res.get("facts") or []:
        d.add_paragraph(f"{f['id']}: {f['text']}" + (f" ({f['url']})" if f.get("url") else ""), style="List Bullet")
    d.add_paragraph(res.get("disclaimer") or "")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()

