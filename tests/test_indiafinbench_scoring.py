from src.eval import indiafinbench as F


def test_token_set_ratio_matches_rapidfuzz_definition():
    assert F.token_set_ratio("fuzzy was a bear", "fuzzy fuzzy was a bear") == 100.0
    # intersection "a"; diffs "b" vs "c": sect 1, sect_ab = sect_ba = 3; result = 100 - 100*2/6; sect ratios 100 - 100*2/4
    assert round(F.token_set_ratio("a b", "a c"), 4) == round(100 - 100 * 2 / 6, 4)
    assert F.token_set_ratio("", "x") == 0.0
    assert F.indel_distance("abc", "abd") == 2


def test_stages():
    assert F.score("Twenty one days", "twenty-one days.", "regulatory_interpretation")["correct"]
    assert F.score("Regulation 47", "Regulation 47 required this.", "temporal_reasoning")["stage"] == 2
    assert F.score("₹5,500 crore", "The amount is Rs 5500 crores after the cap of the limit applies", "numerical_reasoning")["correct"]
    assert F.score("No", "No. The passages differ.", "contradiction_detection")["stage"] == 4
    # a contradiction answer that merely contains the reference word elsewhere is not accepted
    assert not F.score("Yes", "No, although yes appears later.", "contradiction_detection")["correct"]
    assert not F.score("11.5%", "", "numerical_reasoning")["correct"]
    assert F.numbers("1,00,000 and 2.50") == {100000.0, 2.5}


def test_wilson():
    lo, hi = F.wilson(50, 100)
    assert round(lo, 3) == 0.404 and round(hi, 3) == 0.596
    assert F.wilson(0, 0) is None
