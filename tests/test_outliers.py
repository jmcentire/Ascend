"""Tests for the Mirror-correct outlier engine (ANALYSIS_STANDARD.md §0.5, §1.D)."""

from __future__ import annotations

import math

import pytest

from ascend.analysis.cohorts import (
    cohort_key,
    criticality_class,
    is_ramping,
    novelty_score,
)
from ascend.analysis.normalization import cohort_stats, ratio_to_median, zscore
from ascend.analysis.outliers import DimensionSpec, detect_outliers


# --- normalization math ----------------------------------------------------


def test_cohort_stats_basic():
    stats = cohort_stats([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert stats["n"] == 8
    assert stats["mean"] == pytest.approx(5.0)
    assert stats["median"] == pytest.approx(4.5)
    # population sd (divide by n) == 2.0 for this classic dataset
    assert stats["sd"] == pytest.approx(2.0)


def test_cohort_stats_odd_median():
    stats = cohort_stats([1.0, 3.0, 100.0])
    assert stats["median"] == pytest.approx(3.0)
    assert stats["mean"] == pytest.approx(34.6666667)


def test_cohort_stats_empty_and_single():
    empty = cohort_stats([])
    assert empty == {"n": 0, "mean": 0.0, "median": 0.0, "sd": 0.0}
    single = cohort_stats([42.0])
    assert single["n"] == 1
    assert single["sd"] == 0.0  # n<2 -> no spread


def test_zscore():
    stats = cohort_stats([2.0, 4.0, 6.0])  # mean 4, pop sd ~1.632993
    assert zscore(4.0, stats) == pytest.approx(0.0)
    assert zscore(6.0, stats) == pytest.approx((6.0 - 4.0) / math.sqrt(8.0 / 3.0))
    # sd == 0 guard
    assert zscore(99.0, {"sd": 0.0, "mean": 1.0}) == 0.0


def test_ratio_to_median():
    stats = cohort_stats([1.0, 2.0, 3.0])  # median 2
    assert ratio_to_median(6.0, stats) == pytest.approx(3.0)
    assert ratio_to_median(5.0, {"median": 0}) == 0.0


# --- cohort classification -------------------------------------------------


def test_criticality_class():
    assert criticality_class("payment-service") == "critical"
    assert criticality_class("availability") == "critical"
    assert criticality_class("pricing") == "high"
    assert criticality_class("marketing-website") == "low"
    assert criticality_class("some-random-tool") == "standard"
    # module name also matched
    assert criticality_class("wander", "pms/booking") == "critical"
    # overrides take precedence
    assert criticality_class("foo", overrides={"foo": "low"}) == "low"


def test_is_ramping_none_is_true():
    assert is_ramping(None) is True
    assert is_ramping(4.0) is True
    assert is_ramping(20.0) is False
    assert is_ramping(12.0) is False  # threshold is exclusive lower bound


def test_novelty_score():
    assert novelty_score(None, None) == 0.0
    assert novelty_score(10.0, None) == 1.0  # fresh repo -> max novelty
    assert novelty_score(1000.0, None) == 0.0  # mature repo
    assert novelty_score(None, 0.8) == pytest.approx(0.8)
    # max of the two axes
    assert novelty_score(1000.0, 0.9) == pytest.approx(0.9)


def test_cohort_key_stable_and_buckets():
    k1 = cohort_key("PE II", 30.0, "high")
    k2 = cohort_key("pe ii", 30.0, "HIGH")
    assert k1 == k2  # case-insensitive, stable
    assert "established" in k1
    assert "ramping" in cohort_key("PE II", 4.0, "high")
    assert "ramping" in cohort_key("PE II", None, "high")
    assert "unknown" in cohort_key(None, 30.0, None)


# --- detect_outliers: the §0.5 contract ------------------------------------


def _quality_cohort():
    """A cohort of PE II established engineers; one member is >2SD worse."""
    base = [
        {
            "name": f"peer{i}",
            "level": "PE II",
            "tenure_weeks": 50.0,
            "criticality": "standard",
            "novelty": 0.0,
            "repeated_failures": v,
        }
        for i, v in enumerate([1.0, 1.0, 2.0, 1.0, 2.0])
    ]
    outlier = {
        "name": "spike",
        "level": "PE II",
        "tenure_weeks": 50.0,
        "criticality": "standard",
        "novelty": 0.0,
        "repeated_failures": 25.0,  # far above cohort
    }
    return base + [outlier]


def test_detect_outliers_flags_high_bad_with_both_explanations():
    spec = DimensionSpec(
        name="repeated_failures",
        metric_key="repeated_failures",
        direction="high_bad",
        threshold_sd=2.0,
        min_cohort=4,
    )
    flags = detect_outliers(_quality_cohort(), [spec])

    assert len(flags) == 1
    flag = flags[0]
    assert flag["member"] == "spike"
    assert flag["dimension"] == "repeated_failures"
    assert flag["z_score"] > 2.0
    assert flag["severity"] in {"watch", "strong"}

    # BOTH sides must be present: at least one exonerating, at least one not.
    exonerating = [e for e in flag["explanations"] if e["exonerating"]]
    genuine = [e for e in flag["explanations"] if not e["exonerating"]]
    assert genuine, "flag must carry a non-exonerating candidate"
    assert any(
        "genuine performance gap" in e["rationale"] for e in genuine
    )


def test_detect_outliers_exonerating_controls_fire():
    """Novelty, high criticality, thin cohort, and ramping all annotate."""
    members = [
        {
            "name": "a",
            "level": "PE I",
            "tenure_weeks": 4.0,  # ramping
            "criticality": "critical",  # high blast radius
            "novelty": 0.9,  # greenfield
            "catchable_errors": 30.0,
        },
        {
            "name": "b",
            "level": "PE I",
            "tenure_weeks": 6.0,
            "criticality": "critical",
            "novelty": 0.9,
            "catchable_errors": 1.0,
        },
        {
            "name": "c",
            "level": "PE I",
            "tenure_weeks": 8.0,
            "criticality": "critical",
            "novelty": 0.9,
            "catchable_errors": 1.0,
        },
    ]
    spec = DimensionSpec(
        name="catchable_errors",
        metric_key="catchable_errors",
        direction="high_bad",
        threshold_sd=1.0,  # small cohort, loosen to trigger
        min_cohort=4,  # n=3 < 4 -> thin-cohort exoneration fires
    )
    flags = detect_outliers(members, [spec])
    assert len(flags) == 1
    labels = {e["label"] for e in flags[0]["explanations"]}
    assert "novel/greenfield work" in labels
    assert "high system-criticality" in labels
    assert "thin cohort" in labels
    assert "ramping" in labels
    assert "genuine performance gap" in labels


def test_uniform_cohort_yields_zero_flags():
    """No spread -> no outliers. No positional/bottom-N ranking exists."""
    members = [
        {
            "name": f"m{i}",
            "level": "PE II",
            "tenure_weeks": 60.0,
            "criticality": "standard",
            "novelty": 0.0,
            "repeated_failures": 3.0,  # everyone identical
        }
        for i in range(6)
    ]
    spec = DimensionSpec(name="repeated_failures", metric_key="repeated_failures")
    flags = detect_outliers(members, [spec])
    assert flags == []


def test_no_ranking_order_dependence():
    """Shuffling member order does not change which flags are produced."""
    cohort = _quality_cohort()
    spec = DimensionSpec(name="repeated_failures", metric_key="repeated_failures")

    flags_a = detect_outliers(cohort, [spec])
    flags_b = detect_outliers(list(reversed(cohort)), [spec])

    members_a = sorted(f["member"] for f in flags_a)
    members_b = sorted(f["member"] for f in flags_b)
    assert members_a == members_b == ["spike"]


def test_low_bad_direction():
    """low_bad flags a member far BELOW the cohort (e.g. landing rate)."""
    members = [
        {
            "name": f"m{i}",
            "level": "PE II",
            "tenure_weeks": 60.0,
            "criticality": "standard",
            "novelty": 0.0,
            "landing_rate": v,
        }
        for i, v in enumerate([0.9, 0.85, 0.9, 0.88, 0.92])
    ]
    members.append(
        {
            "name": "low",
            "level": "PE II",
            "tenure_weeks": 60.0,
            "criticality": "standard",
            "novelty": 0.0,
            "landing_rate": 0.1,
        }
    )
    spec = DimensionSpec(
        name="landing_rate", metric_key="landing_rate", direction="low_bad"
    )
    flags = detect_outliers(members, [spec])
    assert [f["member"] for f in flags] == ["low"]
    assert flags[0]["z_score"] < -2.0
