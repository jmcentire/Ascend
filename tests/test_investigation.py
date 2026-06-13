"""Tests for the §8/§9 investigation-logging + misfire-audit layer."""

from __future__ import annotations

import pytest

from ascend.db import get_connection
from ascend.analysis import investigation as inv


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "ascend_test.db"
    connection = get_connection(db_path)
    inv.ensure_tables(connection)
    try:
        yield connection
    finally:
        connection.close()


def test_ensure_tables_is_idempotent(conn):
    # Calling twice must not raise.
    inv.ensure_tables(conn)
    inv.ensure_tables(conn)


def test_record_flag_stores_explanations_as_json(conn):
    flag_id = inv.record_flag(
        conn,
        member_id=7,
        dimension="catchable_errors",
        explanations=["greenfield work", "small cohort"],
    )
    assert isinstance(flag_id, int)
    flags = inv.open_flags(conn, member_id=7)
    assert len(flags) == 1
    assert flags[0]["status"] == "open"
    assert flags[0]["explanations"] == ["greenfield work", "small cohort"]


def test_record_investigation_sets_flag_status(conn):
    flag_id = inv.record_flag(conn, member_id=1, dimension="repeated_failures")
    inv_id = inv.record_investigation(
        conn,
        flag_id=flag_id,
        why="cohort too small to be significant",
        comparison_valid=False,
        what_would_change="larger cohort window",
        verdict="context",
        investigated_by="manager-a",
    )
    assert isinstance(inv_id, int)
    # Flag is no longer open.
    assert inv.open_flags(conn, member_id=1) == []
    row = conn.execute(
        "SELECT status FROM flags WHERE id = ?", (flag_id,)
    ).fetchone()
    assert row["status"] == "investigated"


def test_record_investigation_rejects_bad_verdict(conn):
    flag_id = inv.record_flag(conn, member_id=1, dimension="catchable_errors")
    with pytest.raises(ValueError):
        inv.record_investigation(
            conn,
            flag_id=flag_id,
            why="x",
            comparison_valid=True,
            what_would_change="y",
            verdict="manage_out",  # invalid
            investigated_by="manager-a",
        )


def test_action_without_investigation_is_process_violation(conn):
    flag_id = inv.record_flag(conn, member_id=42, dimension="repeated_failures")
    result = inv.record_action(
        conn, member_id=42, action="pip", flag_id=flag_id
    )
    assert result["is_process_violation"] is True
    assert result["warning"] is not None
    assert "§8" in result["warning"]

    violations = inv.list_violations(conn)
    assert len(violations) == 1
    assert violations[0]["member_id"] == 42


def test_action_with_no_flag_is_process_violation(conn):
    result = inv.record_action(conn, member_id=5, action="rating")
    assert result["is_process_violation"] is True


def test_action_with_investigation_id_is_not_violation(conn):
    flag_id = inv.record_flag(conn, member_id=9, dimension="catchable_errors")
    inv_id = inv.record_investigation(
        conn,
        flag_id=flag_id,
        why="genuine gap",
        comparison_valid=True,
        what_would_change="coaching",
        verdict="performance",
        investigated_by="manager-b",
    )
    result = inv.record_action(
        conn,
        member_id=9,
        action="manage_out",
        flag_id=flag_id,
        investigation_id=inv_id,
    )
    assert result["is_process_violation"] is False
    assert result["warning"] is None
    assert inv.list_violations(conn) == []


def test_action_with_investigated_flag_is_not_violation(conn):
    # Even without passing investigation_id, an investigated flag backs the action.
    flag_id = inv.record_flag(conn, member_id=11, dimension="catchable_errors")
    inv.record_investigation(
        conn,
        flag_id=flag_id,
        why="genuine gap",
        comparison_valid=True,
        what_would_change="coaching",
        verdict="performance",
        investigated_by="manager-b",
    )
    result = inv.record_action(
        conn, member_id=11, action="pip", flag_id=flag_id
    )
    assert result["is_process_violation"] is False


def test_record_action_rejects_bad_action(conn):
    with pytest.raises(ValueError):
        inv.record_action(conn, member_id=1, action="promote")


def test_misfire_audit_thirty_percent_rule(conn):
    # 4 flags in one dimension, all investigated; 2 are misfires => 50% => demote.
    dim = "catchable_errors"
    verdicts = ["misfire", "misfire", "performance", "context"]
    for v in verdicts:
        fid = inv.record_flag(conn, member_id=100, dimension=dim)
        inv.record_investigation(
            conn,
            flag_id=fid,
            why="w",
            comparison_valid=True,
            what_would_change="c",
            verdict=v,
            investigated_by="auditor",
        )

    audit = inv.misfire_audit(conn)
    assert dim in audit["dimensions"]
    d = audit["dimensions"][dim]
    assert d["investigated"] == 4
    assert d["misfires"] == 2
    assert d["misfire_rate"] == pytest.approx(0.5)
    assert d["exceeds_threshold"] is True
    assert d["recommendation"] == "demote_to_investigation_only"
    assert dim in audit["overall"]["dimensions_to_demote"]
    assert audit["threshold"] == pytest.approx(0.30)


def test_misfire_audit_below_threshold_keeps_dimension(conn):
    # 4 investigated, 1 misfire => 25% => keep.
    dim = "languishing"
    verdicts = ["misfire", "performance", "performance", "context"]
    for v in verdicts:
        fid = inv.record_flag(conn, member_id=200, dimension=dim)
        inv.record_investigation(
            conn,
            flag_id=fid,
            why="w",
            comparison_valid=True,
            what_would_change="c",
            verdict=v,
            investigated_by="auditor",
        )
    audit = inv.misfire_audit(conn)
    d = audit["dimensions"][dim]
    assert d["misfire_rate"] == pytest.approx(0.25)
    assert d["recommendation"] == "keep"
    assert dim not in audit["overall"]["dimensions_to_demote"]
