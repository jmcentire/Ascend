"""Investigation logging + misfire-audit layer for Ascend.

This module implements the persistence layer for the two protocols in the
Ascend Analysis Standard that give the Mirror its *teeth*:

- **§8 Investigation protocol.** A flag is a hypothesis, never a verdict.
  Before any consequential action (PIP, manage-out, formal rating) on an
  Ascend signal, a manager must record an investigation answering: *why* the
  anomaly is high, whether the *comparison is valid*, *what would change it*,
  and a *verdict* (performance / context / misfire). A consequential action
  taken with **no logged investigation** is recorded here as a *process
  violation* — the exact failure mode the Mirror exists to prevent (the tool
  becoming the justification rather than the trigger).

- **§9 Misfire audit.** Quarterly, the prior period's investigated flags are
  re-examined per dimension. If the misfire rate exceeds ~30%, the dimension is
  not fit to inform consequential action and is demoted to investigation-only
  until its controls are fixed.

The module is self-sufficient about its own tables via the idempotent
:func:`ensure_tables`. Connections are expected to come from
``ascend.db.get_connection`` (``row_factory=sqlite3.Row``).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

__all__ = [
    "ensure_tables",
    "record_flag",
    "record_investigation",
    "record_action",
    "open_flags",
    "list_violations",
    "misfire_audit",
]

# §8 valid verdicts for an investigation.
VALID_VERDICTS = frozenset({"performance", "context", "misfire"})

# Consequential actions that require a prior investigation (§8).
CONSEQUENTIAL_ACTIONS = frozenset({"pip", "manage_out", "rating"})

# §9 threshold: above this per-dimension misfire rate, demote to
# investigation-only.
MISFIRE_THRESHOLD = 0.30


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the investigation-layer tables if they do not already exist.

    Idempotent (``CREATE TABLE IF NOT EXISTS``). Safe to call on every use so
    the module never assumes a separately-run migration. Supports §8/§9 by
    persisting flags, their investigations, and consequential actions
    (including process violations).
    """
    if conn is None:
        raise ValueError("conn must be a live sqlite3.Connection")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            dimension TEXT NOT NULL,
            period TEXT,
            cohort_key TEXT,
            value REAL,
            cohort_median REAL,
            cohort_sd REAL,
            z_score REAL,
            explanations TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flag_id INTEGER NOT NULL REFERENCES flags(id),
            why TEXT,
            comparison_valid INTEGER,
            what_would_change TEXT,
            verdict TEXT NOT NULL,
            investigated_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS consequential_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            flag_id INTEGER,
            investigation_id INTEGER,
            is_process_violation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()


def record_flag(
    conn: sqlite3.Connection,
    *,
    member_id: int,
    dimension: str,
    period: Optional[str] = None,
    cohort_key: Optional[str] = None,
    value: Optional[float] = None,
    cohort_median: Optional[float] = None,
    cohort_sd: Optional[float] = None,
    z_score: Optional[float] = None,
    explanations: Any = None,
) -> int:
    """Persist an anomaly-to-investigate flag and return its id (§0.5, §8).

    A flag is the *start* of an investigation, not its conclusion. ``status``
    defaults to ``'open'``. ``explanations`` — the candidate explanations that
    ship with every flag, including the ones that exonerate (§0.5/§1.D) — may be
    a list or dict and is stored as JSON text.
    """
    if member_id is None:
        raise ValueError("member_id is required")
    if not dimension or not isinstance(dimension, str):
        raise ValueError("dimension must be a non-empty string")

    explanations_json: Optional[str]
    if explanations is None:
        explanations_json = None
    elif isinstance(explanations, str):
        explanations_json = explanations
    else:
        try:
            explanations_json = json.dumps(explanations)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"explanations is not JSON-serializable: {exc}") from exc

    cur = conn.execute(
        """
        INSERT INTO flags (
            member_id, dimension, period, cohort_key, value,
            cohort_median, cohort_sd, z_score, explanations
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            member_id,
            dimension,
            period,
            cohort_key,
            value,
            cohort_median,
            cohort_sd,
            z_score,
            explanations_json,
        ),
    )
    conn.commit()
    flag_id = cur.lastrowid
    if flag_id is None:  # pragma: no cover - defensive
        raise RuntimeError("failed to obtain flag id after insert")
    return int(flag_id)


def record_investigation(
    conn: sqlite3.Connection,
    *,
    flag_id: int,
    why: Optional[str],
    comparison_valid: bool,
    what_would_change: Optional[str],
    verdict: str,
    investigated_by: Optional[str],
) -> int:
    """Record the §8 investigation answering the four mandatory questions.

    ``verdict`` MUST be one of ``{"performance", "context", "misfire"}`` (§8.4);
    any other value raises :class:`ValueError`. On success the parent flag's
    ``status`` is advanced to ``'investigated'``. Returns the investigation id.
    """
    if verdict not in VALID_VERDICTS:
        raise ValueError(
            f"verdict must be one of {sorted(VALID_VERDICTS)}, got {verdict!r}"
        )

    row = conn.execute("SELECT id FROM flags WHERE id = ?", (flag_id,)).fetchone()
    if row is None:
        raise ValueError(f"no flag with id {flag_id}")

    cur = conn.execute(
        """
        INSERT INTO investigations (
            flag_id, why, comparison_valid, what_would_change,
            verdict, investigated_by
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            flag_id,
            why,
            1 if comparison_valid else 0,
            what_would_change,
            verdict,
            investigated_by,
        ),
    )
    conn.execute(
        "UPDATE flags SET status = 'investigated' WHERE id = ?", (flag_id,)
    )
    conn.commit()
    investigation_id = cur.lastrowid
    if investigation_id is None:  # pragma: no cover - defensive
        raise RuntimeError("failed to obtain investigation id after insert")
    return int(investigation_id)


def _flag_has_investigation(conn: sqlite3.Connection, flag_id: int) -> bool:
    """True if the given flag has at least one logged investigation."""
    row = conn.execute(
        "SELECT 1 FROM investigations WHERE flag_id = ? LIMIT 1", (flag_id,)
    ).fetchone()
    return row is not None


def record_action(
    conn: sqlite3.Connection,
    *,
    member_id: int,
    action: str,
    flag_id: Optional[int] = None,
    investigation_id: Optional[int] = None,
) -> dict:
    """Record a consequential action, flagging process violations (§8).

    ``action`` must be one of ``{"pip", "manage_out", "rating"}`` else
    :class:`ValueError`.

    Per §8, a consequential action is a **process violation** when no
    investigation backs it: if ``investigation_id`` is ``None`` AND
    (``flag_id`` is ``None`` OR the referenced flag has no investigation row),
    ``is_process_violation`` is set to 1.

    Returns ``{"action_id": int, "is_process_violation": bool,
    "warning": str | None}``.
    """
    if action not in CONSEQUENTIAL_ACTIONS:
        raise ValueError(
            f"action must be one of {sorted(CONSEQUENTIAL_ACTIONS)}, got {action!r}"
        )
    if member_id is None:
        raise ValueError("member_id is required")

    has_investigation = False
    if investigation_id is not None:
        has_investigation = True
    elif flag_id is not None:
        has_investigation = _flag_has_investigation(conn, flag_id)

    is_violation = not has_investigation

    cur = conn.execute(
        """
        INSERT INTO consequential_actions (
            member_id, action, flag_id, investigation_id, is_process_violation
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (member_id, action, flag_id, investigation_id, 1 if is_violation else 0),
    )
    conn.commit()
    action_id = cur.lastrowid
    if action_id is None:  # pragma: no cover - defensive
        raise RuntimeError("failed to obtain action id after insert")

    warning: Optional[str] = None
    if is_violation:
        warning = (
            f"PROCESS VIOLATION (§8): consequential action {action!r} on member "
            f"{member_id} has no logged investigation. A flag is a hypothesis; "
            "investigation must precede action. This is recorded, not validated."
        )

    return {
        "action_id": int(action_id),
        "is_process_violation": is_violation,
        "warning": warning,
    }


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row into a plain dict, decoding JSON explanations."""
    d = dict(row)
    if "explanations" in d and isinstance(d["explanations"], str):
        try:
            d["explanations"] = json.loads(d["explanations"])
        except (ValueError, TypeError):
            # Leave the raw string if it was not stored as JSON.
            pass
    return d


def open_flags(
    conn: sqlite3.Connection, *, member_id: Optional[int] = None
) -> list[dict]:
    """Return flags still awaiting investigation (status ``'open'``).

    Optionally scoped to a single ``member_id``. Decodes the JSON
    ``explanations`` column back into a list/dict.
    """
    if member_id is None:
        rows = conn.execute(
            "SELECT * FROM flags WHERE status = 'open' ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM flags WHERE status = 'open' AND member_id = ? ORDER BY id",
            (member_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_violations(conn: sqlite3.Connection) -> list[dict]:
    """Return every consequential action recorded as a process violation (§8)."""
    rows = conn.execute(
        """
        SELECT * FROM consequential_actions
        WHERE is_process_violation = 1
        ORDER BY id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def misfire_audit(
    conn: sqlite3.Connection, *, since: Optional[str] = None
) -> dict:
    """Compute the §9 misfire audit over investigated flags.

    For each dimension, count the investigated flags whose verdict was
    ``'misfire'`` against the total investigated, derive the ``misfire_rate``,
    and recommend ``'demote_to_investigation_only'`` when the rate exceeds the
    ~30% threshold (§9). A dimension that cannot get below the threshold does
    not belong in the weighting.

    ``since`` optionally restricts the audit to flags created on/after the given
    ISO timestamp (``flags.created_at >= since``).

    Returns a dict with ``threshold``, per-``dimensions`` breakdown, and an
    ``overall`` summary.
    """
    params: list[Any] = []
    where = "WHERE i.verdict IS NOT NULL"
    if since is not None:
        where += " AND f.created_at >= ?"
        params.append(since)

    rows = conn.execute(
        f"""
        SELECT f.dimension AS dimension, i.verdict AS verdict
        FROM investigations i
        JOIN flags f ON f.id = i.flag_id
        {where}
        """,
        params,
    ).fetchall()

    per_dim: dict[str, dict[str, int]] = {}
    total_investigated = 0
    total_misfires = 0
    for r in rows:
        dim = r["dimension"]
        verdict = r["verdict"]
        bucket = per_dim.setdefault(dim, {"investigated": 0, "misfires": 0})
        bucket["investigated"] += 1
        total_investigated += 1
        if verdict == "misfire":
            bucket["misfires"] += 1
            total_misfires += 1

    dimensions: dict[str, dict[str, Any]] = {}
    for dim, bucket in sorted(per_dim.items()):
        investigated = bucket["investigated"]
        misfires = bucket["misfires"]
        rate = (misfires / investigated) if investigated else 0.0
        recommendation = (
            "demote_to_investigation_only" if rate > MISFIRE_THRESHOLD else "keep"
        )
        dimensions[dim] = {
            "investigated": investigated,
            "misfires": misfires,
            "misfire_rate": rate,
            "exceeds_threshold": rate > MISFIRE_THRESHOLD,
            "recommendation": recommendation,
        }

    overall_rate = (
        (total_misfires / total_investigated) if total_investigated else 0.0
    )
    demote = [
        d for d, v in dimensions.items() if v["recommendation"] == "demote_to_investigation_only"
    ]

    return {
        "since": since,
        "threshold": MISFIRE_THRESHOLD,
        "dimensions": dimensions,
        "overall": {
            "investigated": total_investigated,
            "misfires": total_misfires,
            "misfire_rate": overall_rate,
            "dimensions_to_demote": demote,
        },
    }
