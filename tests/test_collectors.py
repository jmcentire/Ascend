"""Tests for additive analysis collectors (ANALYSIS_STANDARD §1.C/§1.D/§3).

Covers flow metrics, tenure, bug share, and reopen detection. All network and
subprocess access is mocked — these tests never hit real APIs or git.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from ascend.integrations.github import (
    compute_flow_metrics,
    first_commit_date,
    tenure_weeks,
    _parse_iso,
    _percentile,
)
from ascend.integrations.linear import (
    bug_share,
    count_reopened,
    _is_reopen,
)

NOW = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime, *, z: bool = False) -> str:
    s = dt.isoformat()
    if z and s.endswith("+00:00"):
        s = s[:-6] + "Z"
    return s


# --------------------------------------------------------------------------- #
# compute_flow_metrics
# --------------------------------------------------------------------------- #


def test_flow_metrics_empty():
    out = compute_flow_metrics({"open": [], "merged": []}, now=NOW)
    assert out == {
        "stale_hours": 0.0,
        "rotting_prs": 0,
        "pr_cycle_p85_hours": 0.0,
        "open_prs": 0,
    }


def test_flow_metrics_missing_keys():
    # Entirely absent keys should be treated as empty, not crash.
    out = compute_flow_metrics({}, now=NOW)
    assert out["open_prs"] == 0
    assert out["pr_cycle_p85_hours"] == 0.0


def test_flow_stale_hours_summed():
    open_prs = [
        {"updatedAt": _iso(NOW - timedelta(hours=10))},
        {"updatedAt": _iso(NOW - timedelta(hours=5), z=True)},  # trailing Z
    ]
    out = compute_flow_metrics({"open": open_prs, "merged": []}, now=NOW)
    assert out["stale_hours"] == pytest.approx(15.0)
    assert out["open_prs"] == 2


def test_flow_rotting_boundary_exactly_7_days():
    # Exactly 7 days idle counts as rotting (>= 7d).
    open_prs = [{"updatedAt": _iso(NOW - timedelta(days=7))}]
    out = compute_flow_metrics({"open": open_prs, "merged": []}, now=NOW)
    assert out["rotting_prs"] == 1


def test_flow_rotting_just_under_7_days_excluded():
    open_prs = [{"updatedAt": _iso(NOW - timedelta(days=7) + timedelta(seconds=1))}]
    out = compute_flow_metrics({"open": open_prs, "merged": []}, now=NOW)
    assert out["rotting_prs"] == 0


def test_flow_rotting_mixed():
    open_prs = [
        {"updatedAt": _iso(NOW - timedelta(days=10))},  # rotting
        {"updatedAt": _iso(NOW - timedelta(days=8))},   # rotting
        {"updatedAt": _iso(NOW - timedelta(days=2))},   # fresh
    ]
    out = compute_flow_metrics({"open": open_prs, "merged": []}, now=NOW)
    assert out["rotting_prs"] == 2


def test_flow_cycle_p85_math():
    # Cycle hours: 1, 2, ..., 10. p85 via linear interpolation:
    # rank = 0.85 * 9 = 7.65 -> between idx7 (8) and idx8 (9): 8 + 0.65 = 8.65
    merged = [
        {"createdAt": _iso(NOW - timedelta(hours=h)), "mergedAt": _iso(NOW)}
        for h in range(1, 11)
    ]
    out = compute_flow_metrics({"open": [], "merged": merged}, now=NOW)
    assert out["pr_cycle_p85_hours"] == pytest.approx(8.65)


def test_flow_cycle_p85_single():
    merged = [{"createdAt": _iso(NOW - timedelta(hours=4)), "mergedAt": _iso(NOW)}]
    out = compute_flow_metrics({"open": [], "merged": merged}, now=NOW)
    assert out["pr_cycle_p85_hours"] == pytest.approx(4.0)


def test_flow_cycle_p85_none_merged():
    out = compute_flow_metrics({"open": [], "merged": []}, now=NOW)
    assert out["pr_cycle_p85_hours"] == 0.0


def test_flow_skips_unparseable_timestamps():
    open_prs = [
        {"updatedAt": "not-a-date"},
        {"updatedAt": None},
        {},  # no key at all
        {"updatedAt": _iso(NOW - timedelta(hours=3))},
    ]
    merged = [
        {"createdAt": "garbage", "mergedAt": _iso(NOW)},
        {"createdAt": _iso(NOW - timedelta(hours=2)), "mergedAt": _iso(NOW)},
    ]
    out = compute_flow_metrics({"open": open_prs, "merged": merged}, now=NOW)
    assert out["stale_hours"] == pytest.approx(3.0)
    assert out["open_prs"] == 4  # count is of supplied open PRs, parseable or not
    assert out["pr_cycle_p85_hours"] == pytest.approx(2.0)


def test_flow_non_dict_pr_entries_skipped():
    out = compute_flow_metrics({"open": [None, "x", 5], "merged": [None]}, now=NOW)
    assert out["stale_hours"] == 0.0
    assert out["pr_cycle_p85_hours"] == 0.0
    assert out["open_prs"] == 3


def test_flow_now_defaults(monkeypatch):
    out = compute_flow_metrics({"open": [], "merged": []})
    assert out["open_prs"] == 0  # no crash with default now


def test_flow_naive_now_treated_as_utc():
    naive = datetime(2026, 6, 12, 12, 0, 0)
    open_prs = [{"updatedAt": _iso(NOW - timedelta(hours=4))}]
    out = compute_flow_metrics({"open": open_prs, "merged": []}, now=naive)
    assert out["stale_hours"] == pytest.approx(4.0)


# --------------------------------------------------------------------------- #
# _parse_iso / _percentile helpers
# --------------------------------------------------------------------------- #


def test_parse_iso_trailing_z():
    dt = _parse_iso("2026-06-12T12:00:00Z")
    assert dt == NOW


def test_parse_iso_bad_input():
    assert _parse_iso("nonsense") is None
    assert _parse_iso(None) is None
    assert _parse_iso("") is None
    assert _parse_iso(123) is None


def test_percentile_empty():
    assert _percentile([], 85) == 0.0


# --------------------------------------------------------------------------- #
# tenure_weeks
# --------------------------------------------------------------------------- #


def test_tenure_weeks_none_input():
    assert tenure_weeks(None) is None


def test_tenure_weeks_from_date():
    # Bare date parses to midnight; NOW is noon Jun 12 -> 14.5 days = ~2.07 wk.
    assert tenure_weeks("2026-05-29", now=NOW) == pytest.approx(14.5 / 7)


def test_tenure_weeks_from_full_timestamp():
    assert tenure_weeks(_iso(NOW - timedelta(weeks=10)), now=NOW) == pytest.approx(10.0)


def test_tenure_weeks_bad_input():
    assert tenure_weeks("not-a-date", now=NOW) is None


def test_tenure_weeks_default_now():
    # Just verify it returns a float and doesn't crash with default now.
    val = tenure_weeks(_iso(datetime.now(timezone.utc) - timedelta(weeks=3)))
    assert isinstance(val, float)
    assert val == pytest.approx(3.0, abs=0.1)


# --------------------------------------------------------------------------- #
# first_commit_date (subprocess mocked)
# --------------------------------------------------------------------------- #


def test_first_commit_date_missing_dir():
    assert first_commit_date("alice", "/nonexistent/path/xyz") is None


def test_first_commit_date_picks_earliest(tmp_path):
    # Two repos, each a git repo.
    for name in ("repoA", "repoB"):
        d = tmp_path / name
        (d / ".git").mkdir(parents=True)

    # repoA -> 2025-01-01, repoB -> 2024-06-15 (earlier)
    def fake_run(cmd, **kwargs):
        repo = cmd[2]
        if repo.endswith("repoA"):
            return ("2025-01-01T10:00:00+00:00\n2025-02-01T10:00:00+00:00\n", "", 0)
        if repo.endswith("repoB"):
            return ("2024-06-15T08:00:00+00:00\n", "", 0)
        return ("", "", 1)

    with patch("ascend.integrations.github._run_cmd", side_effect=fake_run):
        result = first_commit_date("alice", str(tmp_path), email="alice@x.com")
    assert result == "2024-06-15"


def test_first_commit_date_no_patterns(tmp_path):
    (tmp_path / "repoA" / ".git").mkdir(parents=True)
    # Empty handle and no emails -> no patterns -> None.
    assert first_commit_date("", str(tmp_path)) is None


def test_first_commit_date_no_matches(tmp_path):
    (tmp_path / "repoA" / ".git").mkdir(parents=True)
    with patch("ascend.integrations.github._run_cmd", return_value=("", "", 0)):
        assert first_commit_date("alice", str(tmp_path)) is None


# --------------------------------------------------------------------------- #
# bug_share
# --------------------------------------------------------------------------- #


def _issue(*label_names):
    return {"labels": {"nodes": [{"name": n} for n in label_names]}}


def test_bug_share_empty():
    assert bug_share([]) == 0.0


def test_bug_share_half():
    issues = [_issue("Bug"), _issue("feature")]
    assert bug_share(issues) == pytest.approx(0.5)


def test_bug_share_case_insensitive_and_substring():
    issues = [_issue("BUG"), _issue("regression-bugfix"), _issue("feature")]
    assert bug_share(issues) == pytest.approx(2 / 3)


def test_bug_share_no_labels_key():
    issues = [{}, {"labels": {"nodes": []}}]
    assert bug_share(issues) == 0.0


def test_bug_share_counts_issue_once():
    # Two bug labels on one issue still counts as a single bug issue.
    issues = [_issue("bug", "bug-critical"), _issue("feature")]
    assert bug_share(issues) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# _is_reopen
# --------------------------------------------------------------------------- #

SINCE = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


def _hist(from_type, to_type, when, *, to_present=True):
    node = {
        "createdAt": _iso(when),
        "fromState": {"name": from_type, "type": from_type},
    }
    if to_present:
        node["toState"] = {"name": to_type, "type": to_type}
    else:
        node["toState"] = None
    return node


def test_is_reopen_true_completed_to_started():
    nodes = [_hist("completed", "started", SINCE + timedelta(days=2))]
    assert _is_reopen(nodes, SINCE) is True


def test_is_reopen_false_completed_to_completed():
    nodes = [_hist("completed", "completed", SINCE + timedelta(days=2))]
    assert _is_reopen(nodes, SINCE) is False


def test_is_reopen_false_started_to_completed():
    # Normal completion, not a reopen.
    nodes = [_hist("started", "completed", SINCE + timedelta(days=2))]
    assert _is_reopen(nodes, SINCE) is False


def test_is_reopen_false_before_since():
    nodes = [_hist("completed", "started", SINCE - timedelta(days=1))]
    assert _is_reopen(nodes, SINCE) is False


def test_is_reopen_at_since_boundary():
    nodes = [_hist("completed", "started", SINCE)]
    assert _is_reopen(nodes, SINCE) is True


def test_is_reopen_empty_history():
    assert _is_reopen([], SINCE) is False


def test_is_reopen_handles_missing_states():
    nodes = [
        {"createdAt": _iso(SINCE + timedelta(days=1))},  # no states at all
        {"fromState": {"type": "completed"}, "toState": None,
         "createdAt": _iso(SINCE + timedelta(days=1))},
    ]
    assert _is_reopen(nodes, SINCE) is False


def test_is_reopen_multiple_one_valid():
    nodes = [
        _hist("started", "completed", SINCE + timedelta(days=1)),
        _hist("completed", "unstarted", SINCE + timedelta(days=3)),  # reopen
    ]
    assert _is_reopen(nodes, SINCE) is True


# --------------------------------------------------------------------------- #
# count_reopened (network mocked)
# --------------------------------------------------------------------------- #


def _issue_node(name, history_nodes):
    return {
        "identifier": "ENG-1",
        "assignee": {"name": name, "displayName": name},
        "history": {"nodes": history_nodes},
    }


def test_count_reopened_counts_matching():
    page = {
        "issues": {
            "nodes": [
                _issue_node("Alice", [_hist("completed", "started", SINCE + timedelta(days=2))]),
                _issue_node("Alice", [_hist("started", "completed", SINCE + timedelta(days=2))]),
                _issue_node("Bob", [_hist("completed", "started", SINCE + timedelta(days=2))]),
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }
    with patch("ascend.integrations.linear._graphql", return_value=page):
        n = count_reopened("key", "team", "Alice", SINCE)
    assert n == 1


def test_count_reopened_api_error_returns_zero():
    with patch("ascend.integrations.linear._graphql", return_value=None):
        assert count_reopened("key", "team", "Alice", SINCE) == 0


def test_count_reopened_pagination():
    page1 = {
        "issues": {
            "nodes": [
                _issue_node("Alice", [_hist("completed", "started", SINCE + timedelta(days=1))]),
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
        }
    }
    page2 = {
        "issues": {
            "nodes": [
                _issue_node("Alice", [_hist("completed", "unstarted", SINCE + timedelta(days=2))]),
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }
    with patch("ascend.integrations.linear._graphql", side_effect=[page1, page2]):
        n = count_reopened("key", "team", "Alice", SINCE)
    assert n == 2
