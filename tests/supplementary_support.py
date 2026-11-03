"""Shared helpers for the P2-003 tests: fixtures, a fake HTTP session, a tiny corpus. No network anywhere."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

from src.common.io_helpers import write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.supplementary.common import HarvestContext, SupplementaryConfig, supp_resolver
from tests.conftest import make_config

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "supplementary"

CB, UCB, FID, FEM = ("Commercial Banks", "Urban Co-operative Banks", "Financial Inclusion and Development",
                     "Foreign Exchange Management")


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


def repo_blocks() -> dict[str, Any]:
    return yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))


def supp_config(**alignment_over) -> dict[str, Any]:
    """make_config() plus the real `supplementary` and `matching` blocks, sized for the fixture corpus."""
    blocks = repo_blocks()
    supp = copy.deepcopy(blocks["supplementary"])
    supp["expected_corpus"] = {"directions": len(MANIFEST), "paragraphs": sum(len(v) for v in PARAGRAPHS.values()),
                               "raw_entity_classes": len({m["entity_class_raw"] for m in MANIFEST}),
                               "empty_title_directions": []}
    supp["enforcement"]["years"] = [2026]
    supp["amendments"]["years"] = [2026]
    supp["alignment"].update({"faq_items": 4, "enforcement_items": 3, "min_faq_items": 2, **alignment_over})
    cfg = make_config()
    cfg["supplementary"] = supp
    cfg["matching"] = copy.deepcopy(blocks["matching"])
    return cfg


class Response:
    def __init__(self, status: int, content: bytes):
        self.status_code, self.content = status, content


class FakeSession:
    """Serves the fixtures by URL. ``prid=804`` answers with the CAPTCHA page. Records every request."""

    def __init__(self, overrides: dict[str, tuple[int, bytes]] | None = None):
        self.requests: list[tuple[str, str, dict | None]] = []
        self.overrides = overrides or {}

    def _route(self, url: str) -> tuple[int, bytes]:
        for pattern, answer in self.overrides.items():
            if pattern in url:
                return answer
        m = re.search(r"FAQDisplay\.aspx\?Id=(\d+)", url)
        if m:
            name = f"faq_{m.group(1)}.html"
        elif url.endswith("FAQDisplay.aspx"):
            name = "faq_index.html"
        elif "prid=804" in url:
            name = "captcha.html"
        elif "prid=" in url:
            name = f"pen_{url.split('prid=')[1]}.html"
        elif url.endswith("BS_PressReleaseDisplay.aspx"):
            name = "pr_listing.html"
        elif "NotificationUser.aspx?Id=" in url:
            name = f"amd_{re.search(r'Id=(\d+)', url).group(1)}.html"
        elif url.endswith("NotificationUser.aspx"):
            name = "notif_listing.html"
        elif "WithdrawnCircular" in url:
            name = "withdrawn_list.html"
        else:
            return 404, b""
        return (200, fixture(name)) if (FIX / name).is_file() else (404, b"<html>not found</html>")

    def get(self, url, timeout=None):
        self.requests.append(("GET", url, None))
        return Response(*self._route(url))

    def post(self, url, data=None, timeout=None):
        self.requests.append(("POST", url, dict(data or {})))
        name = "pr_2026.html" if "PressRelease" in url else "notif_2026.html"
        return Response(200, fixture(name))


def resolver_for(cfg: dict, root: Path) -> PathResolver:
    sc = SupplementaryConfig.from_cfg(cfg)
    return supp_resolver(PathResolver.from_config(cfg, repo_root=root), sc)


def make_ctx(cfg: dict, root: Path, session: Any = None) -> HarvestContext:
    sc = SupplementaryConfig.from_cfg(cfg)
    return HarvestContext(cfg=cfg, sc=sc, resolver=resolver_for(cfg, root), session=session or FakeSession(),
                          logger=get_logger("test.supplementary", cfg), sleep_fn=lambda s: None)


# ---------------------------------------------------------------------------
# A tiny corpus: six Directions, with a repeal annex and a repeal statement
# ---------------------------------------------------------------------------

MANIFEST = [
    {"document_id": "md_90001", "entity_class_raw": CB,
     "title": "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025 "
              "(Updated as on December 29, 2025)"},
    {"document_id": "md_90002", "entity_class_raw": FID,
     "title": "Master Directions - Reserve Bank of India (Priority Lending – Targets and Classification) "
              "Directions, 2025 ( Updated as on August 07, 2026 )"},
    {"document_id": "md_90003", "entity_class_raw": UCB,
     "title": "Reserve Bank of India (Urban Co-operative Banks – Know Your Customer) Directions, 2025"},
    {"document_id": "md_90004", "entity_class_raw": UCB,
     "title": "Reserve Bank of India (Urban Co-operative Banks – Interest Rate on Deposits) Directions, 2025"},
    {"document_id": "md_90005", "entity_class_raw": FEM,
     "title": "Master Direction - Gadget Remittances ( Updated as on March 05, 2024 )"},
    {"document_id": "md_90006", "entity_class_raw": UCB,
     "title": "Reserve Bank of India (Urban Co-operative Banks – Credit Risk Management) Directions, 2025"},
]


def _paras(doc: str, texts: list[str]) -> list[dict[str, Any]]:
    return [{"paragraph_id": f"{doc}::p{i:05d}", "document_id": doc, "text": t} for i, t in enumerate(texts)]


PARAGRAPHS = {
    "md_90001": _paras("md_90001", [
        "RBI/DOR/2025-26/100 DOR.AML.REC.100/14.01.001/2025-26 November 28, 2025",
        "5. (1) (v) Certified copy: a bank shall compare the copy of the officially valid document with the original.",
        "12. A bank shall carry out periodic updation of KYC of customers at least once in two years.",
        "14. A bank shall report suspicious transactions to FIU-IND within seven days.",
        "20. A bank shall undertake enhanced due diligence for high risk customers.",
        "Chapter II",
    ]),
    "md_90002": _paras("md_90002", [
        "FIDD.CO.PSD.BC.No.5/04.09.001/2025-26 November 28, 2025",
        "6. Adjusted credit: the net certificate outstanding shall be added to net credit by banks.",
        "8. Gadget loans shall be classified under priority lending by banks subject to the limits.",
    ]),
    "md_90003": _paras("md_90003", [
        "DOR.AML.REC.101/14.01.001/2025-26 November 28, 2025",
        "12. A UCB shall carry out periodic updation of KYC of its customers at least once in two years.",
        "15. A UCB shall upload KYC records to the central registry within ten days.",
    ]),
    "md_90004": _paras("md_90004", [
        "DOR.RET.REC.200/12.01.001/2025-26 November 28, 2025",
        "6.1 A UCB shall not pay interest on current accounts held by its customers.",
    ]),
    "md_90005": _paras("md_90005", [
        "A.P. (DIR Series) Circular No. 1 November 28, 2025",
        "3. AD banks are required to allow remittances for gadgets up to the limit set out here.",
        "APPENDIX\nList of notifications/ circulars which have been consolidated in this Master Direction\n"
        "1 A.P. (DIR Series) Circular No. 64/2015-16 April 28, 2016\n"
        "2 Notification No. FEMA 5(R)/2015-RB April 1, 2016",
    ]),
    "md_90006": _paras("md_90006", [
        "DOR.CRE.REC.300/07.01.001/2025-26 November 28, 2025",
        "9. A UCB shall not sanction loans to relatives of its directors without Board approval.",
        "73. With the issue of these Directions, the existing Directions, instructions, and guidelines relating to "
        "Management of Advances as applicable to Urban Co-operative Banks stand repealed, as communicated vide "
        "circular DOR.RRC.REC.302/33-01-010/2025-26 dated November 28, 2025.",
    ]),
}


def write_corpus(root: Path) -> None:
    write_jsonl(root / "data" / "metadata" / "document_manifest.jsonl", MANIFEST)
    for doc, rows in PARAGRAPHS.items():
        write_jsonl(root / "data" / "processed" / f"{doc}.jsonl", rows)


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)
