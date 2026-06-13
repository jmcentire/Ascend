"""Tests for ascend.integrations.frameworks.

Covers a fully-populated metrics dict (statuses + values), a sparse dict
(honest not_measured, no exceptions, no division by zero), and the provenance
summary — the §0.4 honesty contract every cell must satisfy.
"""

from __future__ import annotations

import math

import pytest

from ascend.integrations.frameworks import (
    compute_dora,
    compute_dx_core4,
    compute_space,
    frameworks_report,
)

VALID_STATUSES = {"measured", "proxy", "not_measured"}


@pytest.fixture
def full_metrics() -> dict:
    return {
        "commits_count": 100,
        "prs_opened": 40,
        "prs_merged": 30,
        "issues_completed": 25,
        "issues_in_progress": 5,
        "reviews_given": 20,
        "coauthored_commits": 8,
        "reopened": 3,
        "bug_share": 0.2,
        "stale_hours": 50.0,
        "rotting_prs": 2,
        "pr_cycle_p85_hours": 36.0,
        "open_prs": 6,
        "period_days": 14.0,
        "sentiment_score": 0.7,
    }


def _assert_cell_valid(cell: dict) -> None:
    """Every cell must carry a valid status and never lie: None <=> not_measured."""
    assert set(["value", "status", "note"]).issubset(cell.keys())
    assert cell["status"] in VALID_STATUSES
    assert isinstance(cell["note"], str) and cell["note"]
    if cell["value"] is None:
        assert cell["status"] == "not_measured"
    else:
        assert cell["status"] in {"measured", "proxy"}


# --------------------------------------------------------------------------- #
# Fully-populated metrics
# --------------------------------------------------------------------------- #


def test_dora_full(full_metrics):
    dora = compute_dora(full_metrics)
    assert set(dora.keys()) == {
        "deployment_frequency",
        "lead_time",
        "change_failure_rate",
        "mttr",
    }
    for cell in dora.values():
        _assert_cell_valid(cell)

    # deployment_frequency = 30 / 14
    assert dora["deployment_frequency"]["status"] == "proxy"
    assert dora["deployment_frequency"]["value"] == pytest.approx(30 / 14)
    assert dora["deployment_frequency"]["unit"] == "deploys/day"

    # lead_time = pr_cycle_p85_hours
    assert dora["lead_time"]["status"] == "proxy"
    assert dora["lead_time"]["value"] == pytest.approx(36.0)

    # change_failure_rate = reopened / prs_merged = 3 / 30
    assert dora["change_failure_rate"]["status"] == "proxy"
    assert dora["change_failure_rate"]["value"] == pytest.approx(3 / 30)
    # §1.D note must explain the reopened-over-reverts choice.
    assert "reopened" in dora["change_failure_rate"]["note"].lower()

    # mttr stays not_measured even with full artifact data — no incident metric.
    assert dora["mttr"]["status"] == "not_measured"
    assert dora["mttr"]["value"] is None


def test_dora_mttr_measured_when_incident_present(full_metrics):
    full_metrics["mttr_hours"] = 4.5
    dora = compute_dora(full_metrics)
    assert dora["mttr"]["status"] == "measured"
    assert dora["mttr"]["value"] == pytest.approx(4.5)


def test_space_full(full_metrics):
    space = compute_space(full_metrics)
    assert set(space.keys()) == {
        "Satisfaction",
        "Performance",
        "Activity",
        "Communication",
        "Efficiency",
    }
    for cell in space.values():
        _assert_cell_valid(cell)

    # Satisfaction from sentiment_score.
    assert space["Satisfaction"]["status"] == "proxy"
    assert space["Satisfaction"]["value"] == pytest.approx(0.7)

    # Performance = mean(landing rate 30/100, feature share 1-0.2).
    assert space["Performance"]["status"] == "proxy"
    expected_perf = ((30 / 100) + (1 - 0.2)) / 2
    assert space["Performance"]["value"] == pytest.approx(expected_perf)

    # Activity = commits + prs_opened + issues_completed = 100+40+25.
    assert space["Activity"]["value"] == pytest.approx(165)
    assert space["Activity"]["status"] == "measured"

    # Communication = reviews + coauthored = 20 + 8.
    assert space["Communication"]["value"] == pytest.approx(28)
    assert space["Communication"]["status"] == "measured"

    # Efficiency = cycle p85 + stale = 36 + 50; lower-is-better noted.
    assert space["Efficiency"]["value"] == pytest.approx(86.0)
    assert "lower" in space["Efficiency"]["note"].lower()


def test_dx_core4_full(full_metrics):
    dx = compute_dx_core4(full_metrics)
    assert set(dx.keys()) == {"Speed", "Effectiveness", "Quality", "Impact"}
    for cell in dx.values():
        _assert_cell_valid(cell)

    # Speed is a two-part dict.
    assert dx["Speed"]["status"] == "proxy"
    assert dx["Speed"]["value"]["lead_time_hours"] == pytest.approx(36.0)
    assert dx["Speed"]["value"]["deploys_per_day"] == pytest.approx(30 / 14)

    # Effectiveness = (1+20)*(1+8)-1 = 188.
    assert dx["Effectiveness"]["value"] == pytest.approx((1 + 20) * (1 + 8) - 1)

    # Quality includes the reopened-derived change_failure_rate and bug_share.
    assert dx["Quality"]["status"] == "proxy"
    assert dx["Quality"]["value"]["change_failure_rate"] == pytest.approx(3 / 30)
    assert dx["Quality"]["value"]["bug_share"] == pytest.approx(0.2)

    # Impact = issues_completed.
    assert dx["Impact"]["value"] == pytest.approx(25)


# --------------------------------------------------------------------------- #
# Sparse metrics — honesty + no crashes / no div-by-zero
# --------------------------------------------------------------------------- #


def test_empty_metrics_no_exceptions():
    """Empty dict must produce all not_measured cells, never raise."""
    for fn in (compute_dora, compute_space, compute_dx_core4):
        result = fn({})
        for cell in result.values():
            _assert_cell_valid(cell)
            assert cell["status"] == "not_measured"
            assert cell["value"] is None


def test_none_metrics_handled():
    # Defensive: None in should be treated as empty, not crash.
    assert compute_dora(None)["mttr"]["status"] == "not_measured"
    assert compute_space(None)["Activity"]["status"] == "not_measured"
    assert compute_dx_core4(None)["Impact"]["status"] == "not_measured"


def test_sparse_no_division_by_zero():
    """Zero/absent denominators must yield not_measured, not a crash."""
    metrics = {
        "prs_merged": 5,
        "commits_count": 0,  # would div-by-zero in a naive landing rate
        "reopened": 2,
        "period_days": 0,  # would div-by-zero in deployment frequency
    }
    dora = compute_dora(metrics)
    # period_days <= 0 -> not_measured, no ZeroDivisionError.
    assert dora["deployment_frequency"]["status"] == "not_measured"

    space = compute_space(metrics)
    # landing rate uses max(1, commits) so commits=0 is safe and contributes.
    assert space["Performance"]["status"] == "proxy"
    assert space["Performance"]["value"] == pytest.approx(5 / 1)


def test_cfr_requires_positive_prs_merged():
    metrics = {"reopened": 2, "prs_merged": 0}
    dora = compute_dora(metrics)
    assert dora["change_failure_rate"]["status"] == "not_measured"
    assert dora["change_failure_rate"]["value"] is None


def test_non_numeric_and_nan_treated_as_absent():
    metrics = {
        "prs_merged": "lots",  # non-numeric
        "pr_cycle_p85_hours": float("nan"),  # NaN
        "issues_completed": True,  # bool is not a metric
    }
    dora = compute_dora(metrics)
    assert dora["deployment_frequency"]["status"] == "not_measured"
    assert dora["lead_time"]["status"] == "not_measured"
    dx = compute_dx_core4(metrics)
    assert dx["Impact"]["status"] == "not_measured"


def test_partial_space_dimensions():
    """Only some inputs present: derivable dims compute, the rest not_measured."""
    metrics = {"reviews_given": 4}
    space = compute_space(metrics)
    assert space["Communication"]["status"] == "proxy"  # one of two inputs
    assert space["Communication"]["value"] == pytest.approx(4)
    assert space["Satisfaction"]["status"] == "not_measured"
    assert space["Performance"]["status"] == "not_measured"
    assert space["Efficiency"]["status"] == "not_measured"


# --------------------------------------------------------------------------- #
# Provenance summary
# --------------------------------------------------------------------------- #


def test_frameworks_report_structure(full_metrics):
    report = frameworks_report(full_metrics)
    assert set(report.keys()) == {"dora", "space", "dx_core4", "provenance"}
    prov = report["provenance"]
    assert set(["measured_inputs", "absent_inputs", "input_coverage",
                "cell_status_counts", "doctrine"]).issubset(prov.keys())

    # All 15 known inputs are present in the full fixture.
    assert prov["input_coverage"] == "15/15"
    assert prov["absent_inputs"] == []
    assert "sentiment_score" in prov["measured_inputs"]
    assert isinstance(prov["doctrine"], str)
    assert "indicator" in prov["doctrine"].lower()

    # Status tally should sum to the number of cells (4 + 5 + 4 = 13).
    counts = prov["cell_status_counts"]
    assert sum(counts.values()) == 13
    # mttr is the one not_measured cell in the full case.
    assert counts["not_measured"] >= 1


def test_frameworks_report_sparse_provenance():
    report = frameworks_report({"prs_merged": 10, "period_days": 7})
    prov = report["provenance"]
    assert prov["measured_inputs"] == ["period_days", "prs_merged"]
    assert "commits_count" in prov["absent_inputs"]
    assert prov["input_coverage"] == "2/15"
    # Most cells should be not_measured given so little input.
    counts = prov["cell_status_counts"]
    assert counts["not_measured"] >= 1
    assert sum(counts.values()) == 13


def test_frameworks_report_period_days_kwarg_overrides():
    # period_days kwarg should drive deployment frequency even if absent in dict.
    report = frameworks_report({"prs_merged": 14}, period_days=7)
    df = report["dora"]["deployment_frequency"]
    assert df["status"] == "proxy"
    assert df["value"] == pytest.approx(2.0)


def test_all_values_finite_when_present(full_metrics):
    """No emitted scalar value should ever be NaN/inf."""
    report = frameworks_report(full_metrics)
    for framework in ("dora", "space", "dx_core4"):
        for cell in report[framework].values():
            value = cell["value"]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert math.isfinite(value)
