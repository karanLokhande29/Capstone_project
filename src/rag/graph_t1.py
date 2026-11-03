"""LangGraph port of the P4 T1 pipeline (extension #9, engineering only; Amendments 5 and 6).

The graph re-expresses `pipeline.run_t1_item` as explicit nodes and one conditional edge:

    evidence -> generate -> verify --(all supported / no verifier)--> finalize
                                  \\--(some unsupported)--> retry -> finalize

Every node calls the same functions as the original (t1_evidence, t1_messages, parse_t1, t1_check, derive), so prompts
and outputs are meant to be byte-identical; scripts/run_langgraph_equivalence.py checks that on all 106 items.
LangGraph supports Python 3.10-3.13, so this module runs in the separate environment external/.venv-langgraph313.
No reported number depends on it.
"""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

from src.rag import pipeline as PL


class T1State(TypedDict, total=False):
    item: Mapping[str, Any]
    classes: list[str]
    query: str
    log: dict[str, Any]
    shown: dict[str, list[str]]
    per: dict[str, dict]
    bad: list[str]


def build_t1_graph(res: PL.Resources, prompts: PL.Prompts, llm: Any, verifier: PL.NLIVerifier | None, cfg: PL.T1Config):
    from langgraph.graph import END, START, StateGraph

    def evidence(s: T1State) -> T1State:
        item = s["item"]
        query = " ".join(item["obligation_span"]["text"].split())
        log = {"item_id": item["item_id"], "class_filter": cfg.class_filter, "verifier": cfg.verifier,
               "temporal_filter": "inactive (T1 items carry no as-of date)", "steps": []}
        return {"classes": sorted(item["compared_classes"]), "query": query, "log": log}

    def generate(s: T1State) -> T1State:
        item, log = s["item"], s["log"]
        ev, shown = PL.t1_evidence(res, item, s["query"], cfg)
        c = llm.complete(PL.t1_messages(prompts, res, item, ev), max_output_tokens=cfg.max_output_tokens)
        per, problems = PL.parse_t1(c.text, s["classes"])
        log["steps"].append({"attempt": 1, "shown": shown, "cached": c.cached, "model": c.model, "model_version": c.model_version,
                             "raw": c.text, "parse_problems": problems, "per_class": per})
        return {"shown": shown, "per": per, "log": log}

    def verify(s: T1State) -> T1State:
        if not cfg.verifier:
            return {"bad": []}
        sup = PL.t1_check(res, s["per"], s["shown"], verifier)
        s["log"]["steps"][0]["supported"] = sup
        return {"bad": [k for k, ok in sup.items() if not ok], "log": s["log"]}

    def route(s: T1State) -> str:
        return "retry" if s.get("bad") else "finalize"

    def retry(s: T1State) -> T1State:
        item, per, bad, log = s["item"], s["per"], s["bad"], s["log"]
        query2 = s["query"] + " " + " ".join(per[k]["rationale"] for k in bad if per[k]["rationale"])
        ev2, shown2 = PL.t1_evidence(res, item, query2, cfg)
        c2 = llm.complete(PL.t1_messages(prompts, res, item, ev2), max_output_tokens=cfg.max_output_tokens)
        per2, problems2 = PL.parse_t1(c2.text, s["classes"])
        sup2 = PL.t1_check(res, per2, shown2, verifier)
        log["steps"].append({"attempt": 2, "unsupported_classes": bad, "shown": shown2, "cached": c2.cached, "model": c2.model,
                             "raw": c2.text, "parse_problems": problems2, "per_class": per2, "supported": sup2})
        for k, ok in sup2.items():
            if not ok:
                per2[k] = {**per2[k], "judgement": "unsure", "matched_paragraph_id": None, "abstained": True}
        return {"per": per2, "log": log}

    def finalize(s: T1State) -> T1State:
        log = s["log"]
        final = {k: {kk: vv for kk, vv in v.items() if kk != "valid"} for k, v in s["per"].items()}
        log["final"] = {"per_class": final, **PL.derive(final, s["item"]["entity_class"])}
        log["calls"] = sum(1 for st in log["steps"] if not st["cached"])
        log["retried"] = len(log["steps"]) > 1
        return {"log": log}

    g = StateGraph(T1State)
    for name, fn in (("evidence", evidence), ("generate", generate), ("verify", verify), ("retry", retry), ("finalize", finalize)):
        g.add_node(name, fn)
    g.add_edge(START, "evidence")
    g.add_edge("evidence", "generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges("verify", route, {"retry": "retry", "finalize": "finalize"})
    g.add_edge("retry", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def run_t1_item_graph(graph, item: Mapping[str, Any]) -> dict[str, Any]:
    return graph.invoke({"item": item})["log"]
