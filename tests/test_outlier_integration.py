"""Integration tests for the coach-outliers / investigate / audit wiring.

Exercises the helpers in commands/coach.py against a real (temp) SQLite DB plus the
analysis modules, with no network or git access. Verifies the Mirror contract end to end:
snapshots -> aggregated metrics -> cohort outliers -> persisted flag -> investigation ->
misfire audit.
"""

from __future__ import annotations

import json

import pytest

from ascend.db import init_db
from ascend.commands.coach import (
    _parse_level,
    _aggregate_member_metrics,
    _member_criticality,
    _dimension_specs,
)
from ascend.analysis.outliers import detect_outliers
from ascend.analysis import investigation as inv


@pytest.fixture()
def conn(tmp_path):
    c = init_db(tmp_path / "ascend.db")
    yield c
    c.close()


def _add_member(conn, name, title, github="gh"):
    cur = conn.execute(
        "INSERT INTO members (name, title, github, status) VALUES (?, ?, ?, 'active')",
        (name, title, github + name),
    )
    conn.commit()
    return cur.lastrowid


def _add_snapshot(conn, member_id, date, metrics):
    conn.execute(
        "INSERT INTO performance_snapshots (member_id, date, source, metrics, score) "
        "VALUES (?, ?, 'sync', ?, 0)",
        (member_id, date, json.dumps(metrics)),
    )
    conn.commit()


# ---- _parse_level ----

@pytest.mark.parametrize("title,expected_contains", [
    ("Product Engineer II", "ii"),
    ("Staff Product Engineer", "staff"),
    ("Senior Product Engineer", "senior"),
    ("Principal Engineer", "principal"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_parse_level(title, expected_contains):
    assert expected_contains in _parse_level(title)


# ---- _member_criticality ----

def test_member_criticality_flag(conn):
    mid = _add_member(conn, "Alice", "Product Engineer II")
    assert _member_criticality(conn, mid) is None
    conn.execute(
        "INSERT INTO member_flags (member_id, flag) VALUES (?, 'criticality:critical')",
        (mid,),
    )
    conn.commit()
    assert _member_criticality(conn, mid) == "critical"


# ---- _aggregate_member_metrics ----

def test_aggregate_sums_and_averages(conn):
    mid = _add_member(conn, "Bob", "Product Engineer II")
    _add_snapshot(conn, mid, "2099-01-01", {
        "prs_merged": 2, "commits_count": 10, "reviews_given": 3,
        "reopened": 1, "pr_cycle_p85_hours": 100.0, "stale_hours": 50.0, "bug_share": 0.2,
    })
    _add_snapshot(conn, mid, "2099-01-02", {
        "prs_merged": 4, "commits_count": 5, "reviews_given": 1,
        "reopened": 2, "pr_cycle_p85_hours": 200.0, "stale_hours": 150.0, "bug_share": 0.4,
    })
    # huge window so the inserted future dates fall inside it
    agg = _aggregate_member_metrics(conn, mid, days=100000)
    assert agg["reopened"] == 3          # summed
    assert agg["prs_merged"] == 6        # summed
    assert agg["pr_cycle_p85_hours"] == pytest.approx(150.0)   # averaged
    assert agg["stale_hours"] == pytest.approx(100.0)
    assert agg["bug_share"] == pytest.approx(0.3)
    assert agg["snapshots"] == 2
    assert agg["merges_per_week"] > 0


def test_aggregate_empty(conn):
    mid = _add_member(conn, "Carol", "Product Engineer II")
    agg = _aggregate_member_metrics(conn, mid, days=90)
    assert agg["snapshots"] == 0
    assert agg["reopened"] == 0


# ---- end-to-end: detect -> persist -> investigate -> audit ----

def test_outlier_flag_investigate_audit_flow(conn):
    inv.ensure_tables(conn)
    mid = _add_member(conn, "Dave", "Product Engineer II")

    # Cohort: 9 peers at baseline, one (Dave) a clear high-reopened outlier (z=3).
    reopened_series = [0, 0, 0, 0, 0, 0, 0, 0, 0, 30]
    last = len(reopened_series) - 1
    members = []
    for i, reopened in enumerate(reopened_series):
        members.append({
            "member_id": mid if i == last else 1000 + i,
            "name": "Dave" if i == last else f"peer{i}",
            "level": "ii", "tenure_weeks": 52.0, "criticality": "standard", "novelty": 0.0,
            "reopened": reopened, "stale_hours": 0.0, "pr_cycle_p85_hours": 0.0,
            "merges_per_week": 3.0, "bug_share": 0.1,
        })

    specs = _dimension_specs()
    flags = detect_outliers(members, specs)
    rf = [f for f in flags if f["dimension"] == "repeated_failures"]
    assert rf, "expected a repeated_failures flag for the 12-reopened outlier"
    flag = rf[0]
    assert flag["member"] == "Dave"
    # Mirror contract: explanations present, with both sides represented.
    labels = flag["explanations"]
    assert any(not e["exonerating"] for e in labels)

    # Persist the flag (as cmd_coach_outliers does) and run the §8/§9 loop.
    fid = inv.record_flag(
        conn, member_id=mid, dimension=flag["dimension"], period="last_90d",
        cohort_key=flag.get("cohort_key"), value=flag.get("value"),
        cohort_median=flag.get("cohort_median"), cohort_sd=flag.get("cohort_sd"),
        z_score=flag.get("z_score"), explanations=flag.get("explanations"),
    )
    assert fid

    # Acting WITHOUT investigation is a process violation (§8).
    res = inv.record_action(conn, member_id=mid, action="pip", flag_id=fid)
    assert res["is_process_violation"] is True

    # Investigate, then audit.
    iid = inv.record_investigation(
        conn, flag_id=fid, why="dug in", comparison_valid=True,
        what_would_change="more tests", verdict="misfire", investigated_by="jmc",
    )
    assert iid
    audit = inv.misfire_audit(conn)
    assert isinstance(audit, dict)
