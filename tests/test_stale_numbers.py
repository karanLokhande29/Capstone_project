"""P1: stale-number scanner (fixtures)."""

from src.release import stale_numbers as S


def test_scan_maps_numbers_to_keys_and_flags_unsourced():
    idx = S.build_index({"r": {"t": {"kappa": 0.7738, "n": 106, "diff": -0.21698, "rate": 0.138, "big": 76188,
                                     "fmt": "-0.049 [-0.133, +0.036]"}}})
    text = ("# 8.1 Results\nκ = 0.774 (n = 106), coverage -0.217, lowers by 0.217; 13.8% rejected; 76,188 paragraphs.\n"
            "Ablation A -0.049 [-0.133, +0.036]. Unknown 0.123. Paragraph md_12925::p00044 on 2026-09-27, v3.1, Table 5, {{P.kappa}}.")
    res = S.scan_text(text, idx)
    by = {r["number"]: r["status"] for r in res["rows"]}
    assert by["0.774"] == by["106"] == by["-0.217"] == by["0.217"] == by["13.8%"] == by["76,188"] == "sourced"
    assert by["-0.049"] == by["+0.036"] == "sourced"
    assert by["0.123"] == "unsourced"
    assert not any(n in by for n in ("8.1", "12925", "2026", "3.1", "5"))
    assert all(not r["number"].endswith(",") for r in res["rows"])
