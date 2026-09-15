from agentproof.compare import exact_mcnemar_p_value, wilson_interval


def test_exact_mcnemar_is_small_for_one_sided_improvement():
    assert exact_mcnemar_p_value(12, 1) < 0.05


def test_wilson_interval_contains_observed_rate():
    lo, hi = wilson_interval(95, 100)
    assert lo < 0.95 < hi
