"""Industry engineering-framework indicators (DORA, SPACE, DX Core 4).

This module computes the three best-known industry frameworks — DORA, SPACE,
and the DX Core 4 — from the same VCS/issue-derived metrics dict Ascend already
collects (see `integrations/snapshot.py`). It exists so deeper analyses can
speak in the vocabulary leadership recognizes, *without* pretending we have data
we do not.

Read this against ANALYSIS_STANDARD.md:

- **§0.4 — name the data you don't have.** None of the canonical frameworks were
  designed to be reconstructed from git/Linear alone. Real DORA wants deploy
  pipelines and incident timelines; real SPACE wants survey instruments; DX Core
  4 wants developer-experience surveys. We have artifacts, not pipelines or
  surveys. So *every* value this module emits carries an explicit `status`:
    - ``"measured"`` — taken directly from a collected metric.
    - ``"proxy"``    — derived from an adjacent artifact; the ``note`` names the
                       proxy and its limits.
    - ``"not_measured"`` — we cannot honestly derive it; ``value`` is ``None``.
  We never fabricate a number to fill a slot.

- **§0 / Mirror doctrine (§0.5).** These outputs are *indicators that route
  attention*, never verdicts. A "low" DORA or DX number here means "the artifacts
  we can see look like X — investigate why," not "this team/person is bad."

- **§1.D — CFR/reverts are dead on a fix-forward team.** So `change_failure_rate`
  here is proxied from *reopened* issues, which §1.D names as the real recurring-
  failure signal, not from reverts. The ``note`` says so.

All functions are pure: a metrics dict in, a plain dict out. Missing keys are
handled honestly (status ``not_measured``); no division by zero; no bare except.

Metrics dict keys consumed (all optional): commits_count, prs_opened,
prs_merged, issues_completed, issues_in_progress, reviews_given,
coauthored_commits, reopened, bug_share, stale_hours, rotting_prs,
pr_cycle_p85_hours, open_prs, period_days, sentiment_score.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

__all__ = [
    "compute_dora",
    "compute_space",
    "compute_dx_core4",
    "frameworks_report",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# The metric names that, if present, are genuinely *measured* artifacts rather
# than proxies. Used by the provenance summary.
_KNOWN_INPUTS = (
    "commits_count",
    "prs_opened",
    "prs_merged",
    "issues_completed",
    "issues_in_progress",
    "reviews_given",
    "coauthored_commits",
    "reopened",
    "bug_share",
    "stale_hours",
    "rotting_prs",
    "pr_cycle_p85_hours",
    "open_prs",
    "period_days",
    "sentiment_score",
)


def _num(metrics: Mapping[str, Any], key: str) -> Optional[float]:
    """Return metrics[key] as a float if it is a real, finite number, else None.

    Booleans are rejected (a bool is an int in Python but never a metric here),
    as are NaN/inf and anything non-numeric. Honesty over coercion: a value we
    cannot trust is treated as absent.
    """
    if key not in metrics:
        return None
    value = metrics[key]
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    # Reject NaN and infinities (NaN != NaN).
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _cell(
    value: Optional[float],
    status: str,
    note: str,
    *,
    unit: Optional[str] = None,
) -> dict:
    """Build a result cell with provenance.

    Every emitted value is one of measured / proxy / not_measured. When the
    value is None we force status to not_measured so the contract can never lie.
    """
    if value is None:
        status = "not_measured"
    cell: dict = {"value": value, "status": status, "note": note}
    if unit is not None:
        cell["unit"] = unit
    return cell


def _not_measured(note: str, *, unit: Optional[str] = None) -> dict:
    return _cell(None, "not_measured", note, unit=unit)


# --------------------------------------------------------------------------- #
# DORA
# --------------------------------------------------------------------------- #


def compute_dora(
    metrics: Mapping[str, Any],
    *,
    period_days: Optional[float] = None,
) -> dict:
    """Compute proxy DORA four-key metrics from artifact data.

    Returns a dict with keys deployment_frequency, lead_time,
    change_failure_rate, mttr — each a ``{value, unit, status, note}`` cell.

    None of these are true DORA measurements: we have no deploy pipeline,
    incident timeline, or revert-grade failure signal. They are proxies over
    VCS/issue artifacts, to be read as indicators per the Mirror doctrine.
    """
    if metrics is None:
        metrics = {}

    # period_days: explicit kwarg wins, else the metrics value, else absent.
    days = period_days if period_days is not None else _num(metrics, "period_days")

    # --- Deployment frequency: merged PRs per day (proxy: merged PR == deploy)
    prs_merged = _num(metrics, "prs_merged")
    if prs_merged is None:
        deployment_frequency = _not_measured(
            "no prs_merged collected; deployment frequency underivable",
            unit="deploys/day",
        )
    elif days is None or days <= 0:
        deployment_frequency = _not_measured(
            "prs_merged present but period_days missing or non-positive; "
            "cannot compute a per-day rate",
            unit="deploys/day",
        )
    else:
        deployment_frequency = _cell(
            prs_merged / days,
            "proxy",
            "proxy: merged PRs treated as deploys, divided by period_days. "
            "Not a real deploy count — no deploy pipeline is wired.",
            unit="deploys/day",
        )

    # --- Lead time: PR cycle-time p85 (proxy: open->merge, not commit->prod)
    cycle_p85 = _num(metrics, "pr_cycle_p85_hours")
    if cycle_p85 is None:
        lead_time = _not_measured(
            "no pr_cycle_p85_hours collected; lead time underivable",
            unit="hours",
        )
    else:
        lead_time = _cell(
            cycle_p85,
            "proxy",
            "proxy: PR cycle-time p85 (open->merge). True DORA lead time is "
            "commit->production; we measure review latency, not deploy latency.",
            unit="hours",
        )

    # --- Change failure rate: reopened / prs_merged (proxy per §1.D)
    reopened = _num(metrics, "reopened")
    if reopened is None or prs_merged is None:
        change_failure_rate = _not_measured(
            "needs both reopened and prs_merged; "
            f"{'reopened ' if reopened is None else ''}"
            f"{'prs_merged ' if prs_merged is None else ''}absent",
            unit="ratio",
        )
    elif prs_merged <= 0:
        change_failure_rate = _not_measured(
            "prs_merged is non-positive; cannot form a failure ratio",
            unit="ratio",
        )
    else:
        change_failure_rate = _cell(
            reopened / prs_merged,
            "proxy",
            "proxy: reopened issues / merged PRs. Per ANALYSIS_STANDARD §1.D, "
            "CFR-via-reverts is dead on a fix-forward team (~near-zero, no "
            "discrimination); reopened/recurring failures is the real quality "
            "signal, so we proxy CFR from reopened instead.",
            unit="ratio",
        )

    # --- MTTR: genuinely not measurable without an incident metric.
    incident_keys = ("mttr_hours", "incident_recovery_hours", "incidents")
    has_incident = any(_num(metrics, k) is not None for k in incident_keys)
    if has_incident:
        # We accept a directly-provided MTTR-like value if one ever exists.
        mttr_value = _num(metrics, "mttr_hours") or _num(
            metrics, "incident_recovery_hours"
        )
        mttr = _cell(
            mttr_value,
            "measured" if mttr_value is not None else "not_measured",
            "incident-recovery metric present in context",
            unit="hours",
        )
    else:
        mttr = _not_measured(
            "no incident/recovery metric in context; MTTR requires an incident "
            "timeline Ascend does not collect (§0.4, §7).",
            unit="hours",
        )

    return {
        "deployment_frequency": deployment_frequency,
        "lead_time": lead_time,
        "change_failure_rate": change_failure_rate,
        "mttr": mttr,
    }


# --------------------------------------------------------------------------- #
# SPACE
# --------------------------------------------------------------------------- #


def compute_space(metrics: Mapping[str, Any]) -> dict:
    """Compute proxy SPACE dimensions from artifact data.

    Returns Satisfaction, Performance, Activity, Communication, Efficiency —
    each a ``{value, status, note}`` cell. SPACE was designed around developer
    *surveys*; with only artifacts we can proxy four of five and must mark
    Satisfaction not_measured unless a sentiment_score is supplied.
    """
    if metrics is None:
        metrics = {}

    # --- Satisfaction & well-being: only from an explicit sentiment signal.
    sentiment = _num(metrics, "sentiment_score")
    if sentiment is None:
        satisfaction = _not_measured(
            "Satisfaction is survey-grade; no sentiment_score in context. "
            "Artifacts cannot proxy how developers feel (§0.4)."
        )
    else:
        satisfaction = _cell(
            sentiment,
            "proxy",
            "proxy: supplied sentiment_score stands in for survey-based "
            "satisfaction; it is not a SPACE survey instrument.",
        )

    # --- Performance: landing rate + (1 - bug_share). Quality of outcomes.
    prs_merged = _num(metrics, "prs_merged")
    commits = _num(metrics, "commits_count")
    bug_share = _num(metrics, "bug_share")

    perf_parts = []
    landing_rate: Optional[float] = None
    if prs_merged is not None and commits is not None:
        # max(1, commits) guards div-by-zero and tiny denominators.
        landing_rate = prs_merged / max(1.0, commits)
        perf_parts.append(landing_rate)
    feature_share: Optional[float] = None
    if bug_share is not None:
        feature_share = 1.0 - bug_share
        perf_parts.append(feature_share)

    if not perf_parts:
        performance = _not_measured(
            "Performance needs landing rate (prs_merged + commits_count) "
            "and/or bug_share; none present."
        )
    else:
        performance = _cell(
            sum(perf_parts) / len(perf_parts),
            "proxy",
            "proxy: mean of available outcome signals — landing rate "
            f"(prs_merged/max(1,commits)={_fmt(landing_rate)}) and feature "
            f"share (1-bug_share={_fmt(feature_share)}). Proxies for outcome "
            "quality, not a performance verdict (§0).",
        )

    # --- Activity: countable artifact volume. The honest, shallow dimension.
    activity_keys = ("commits_count", "prs_opened", "issues_completed")
    activity_vals = [
        v for v in (_num(metrics, k) for k in activity_keys) if v is not None
    ]
    if not activity_vals:
        activity = _not_measured(
            "Activity needs at least one of commits_count, prs_opened, "
            "issues_completed; none present."
        )
    else:
        activity = _cell(
            sum(activity_vals),
            "proxy" if len(activity_vals) < len(activity_keys) else "measured",
            "sum of countable artifacts (commits + PRs opened + issues "
            "completed). Volume indicator only; prevention/craft leave no "
            "artifact and read LOW here (§0.1).",
        )

    # --- Communication & collaboration: review + co-authoring.
    reviews = _num(metrics, "reviews_given")
    coauthored = _num(metrics, "coauthored_commits")
    comm_vals = [v for v in (reviews, coauthored) if v is not None]
    if not comm_vals:
        communication = _not_measured(
            "Communication needs reviews_given and/or coauthored_commits; "
            "neither present."
        )
    else:
        communication = _cell(
            sum(comm_vals),
            "proxy" if len(comm_vals) < 2 else "measured",
            "reviews_given + coauthored_commits — multiplication work that "
            "lands in others' output (§1.B). Higher is engagement, not noise.",
        )

    # --- Efficiency & flow: latency, lower is better.
    cycle_p85 = _num(metrics, "pr_cycle_p85_hours")
    stale = _num(metrics, "stale_hours")
    eff_vals = [v for v in (cycle_p85, stale) if v is not None]
    if not eff_vals:
        efficiency = _not_measured(
            "Efficiency needs pr_cycle_p85_hours and/or stale_hours; "
            "neither present.",
        )
    else:
        efficiency = _cell(
            sum(eff_vals),
            "proxy",
            "proxy: pr_cycle_p85_hours + stale_hours (total latency in hours). "
            "LOWER is better — this is friction/languishing (§1.C), not a "
            "score where high wins.",
        )

    return {
        "Satisfaction": satisfaction,
        "Performance": performance,
        "Activity": activity,
        "Communication": communication,
        "Efficiency": efficiency,
    }


def _fmt(value: Optional[float]) -> str:
    """Compact, honest rendering for embedding in notes."""
    if value is None:
        return "n/a"
    return f"{value:.3f}"


# --------------------------------------------------------------------------- #
# DX Core 4
# --------------------------------------------------------------------------- #


def compute_dx_core4(metrics: Mapping[str, Any]) -> dict:
    """Compute proxy DX Core 4 dimensions from artifact data.

    Returns Speed, Effectiveness, Quality, Impact — each a
    ``{value, status, note}`` cell. DX Core 4 was built on developer-experience
    surveys plus delivery data; we proxy from the delivery/artifact half only.
    """
    if metrics is None:
        metrics = {}

    days = _num(metrics, "period_days")
    prs_merged = _num(metrics, "prs_merged")
    cycle_p85 = _num(metrics, "pr_cycle_p85_hours")

    # --- Speed: lead time and deploy frequency.
    deploy_freq: Optional[float] = None
    if prs_merged is not None and days is not None and days > 0:
        deploy_freq = prs_merged / days
    speed_parts = []
    if cycle_p85 is not None:
        speed_parts.append(("lead_time_hours", cycle_p85))
    if deploy_freq is not None:
        speed_parts.append(("deploys_per_day", deploy_freq))
    if not speed_parts:
        speed = _not_measured(
            "Speed needs pr_cycle_p85_hours (lead time) and/or "
            "prs_merged+period_days (deploy frequency); insufficient inputs."
        )
    else:
        speed = _cell(
            {k: v for k, v in speed_parts},
            "proxy",
            "proxy: lead time (PR cycle p85, lower better) and deploy frequency "
            "(merged PRs/day). Two-part — they trade off, so we keep them "
            "separate rather than fuse into a fake single number.",
        )

    # --- Effectiveness: collaboration leverage (reviews x co-authoring proxy).
    reviews = _num(metrics, "reviews_given")
    coauthored = _num(metrics, "coauthored_commits")
    if reviews is None and coauthored is None:
        effectiveness = _not_measured(
            "Effectiveness needs reviews_given and/or coauthored_commits; "
            "neither present. (DX Core 4 Effectiveness is really a DX survey; "
            "this is a leverage proxy only.)"
        )
    else:
        # Multiplicative leverage proxy: (1+reviews)*(1+coauthored)-1, so either
        # signal alone still contributes and both together compound. The +1
        # offsets keep a zero in one factor from nuking the other.
        r = reviews if reviews is not None else 0.0
        c = coauthored if coauthored is not None else 0.0
        effectiveness = _cell(
            (1.0 + r) * (1.0 + c) - 1.0,
            "proxy",
            "proxy: (1+reviews_given)*(1+coauthored_commits)-1 — multiplicative "
            "leverage of review + co-authoring (§1.B). A leverage indicator, "
            "NOT the DX Core 4 developer-experience survey it nominally names.",
        )

    # --- Quality: reopened / change-failure / bug share. Heaviest block (§1.D).
    reopened = _num(metrics, "reopened")
    bug_share = _num(metrics, "bug_share")
    q_parts = []
    cfr: Optional[float] = None
    if reopened is not None and prs_merged is not None and prs_merged > 0:
        cfr = reopened / prs_merged
        q_parts.append(("change_failure_rate", cfr))
    elif reopened is not None:
        q_parts.append(("reopened", reopened))
    if bug_share is not None:
        q_parts.append(("bug_share", bug_share))
    if not q_parts:
        quality = _not_measured(
            "Quality needs reopened (with prs_merged for a rate) and/or "
            "bug_share; none present. Per §1.D this is the heaviest block — "
            "absence lowers confidence, do not infer it."
        )
    else:
        quality = _cell(
            {k: v for k, v in q_parts},
            "proxy",
            "proxy: reopened-derived change-failure rate and/or bug_share "
            "(§1.D — reopened/recurring failures over reverts). LOWER is "
            "better; this is the heaviest-weighted block, surfaced as an "
            "investigation trigger, never a verdict.",
        )

    # --- Impact: shipped outcomes (issues completed).
    issues_completed = _num(metrics, "issues_completed")
    if issues_completed is None:
        impact = _not_measured(
            "Impact needs issues_completed; absent. (True impact is business "
            "outcome, which no artifact captures — this is a delivery proxy.)"
        )
    else:
        impact = _cell(
            issues_completed,
            "proxy",
            "proxy: issues_completed as a delivery-volume stand-in. Real impact "
            "is business outcome and is not in any artifact (§0.4).",
        )

    return {
        "Speed": speed,
        "Effectiveness": effectiveness,
        "Quality": quality,
        "Impact": impact,
    }


# --------------------------------------------------------------------------- #
# Combined report
# --------------------------------------------------------------------------- #


def frameworks_report(
    metrics: Mapping[str, Any],
    *,
    period_days: Optional[float] = None,
) -> dict:
    """Combine DORA, SPACE, and DX Core 4 into one report with provenance.

    Returns ``{"dora": ..., "space": ..., "dx_core4": ..., "provenance": ...}``.
    The provenance summary lists which known inputs were actually present vs.
    absent, so a reader can see at a glance how much of this is real measurement
    versus proxy versus gap — honoring §0.4 (name the data you don't have).
    """
    if metrics is None:
        metrics = {}

    dora = compute_dora(metrics, period_days=period_days)
    space = compute_space(metrics)
    dx_core4 = compute_dx_core4(metrics)

    measured_inputs = sorted(
        k for k in _KNOWN_INPUTS if _num(metrics, k) is not None
    )
    absent_inputs = sorted(
        k for k in _KNOWN_INPUTS if _num(metrics, k) is None
    )

    # Tally cell statuses across every framework so the summary is self-checking.
    status_counts = {"measured": 0, "proxy": 0, "not_measured": 0}
    for framework in (dora, space, dx_core4):
        for cell in framework.values():
            status = cell.get("status")
            if status in status_counts:
                status_counts[status] += 1

    provenance = {
        "measured_inputs": measured_inputs,
        "absent_inputs": absent_inputs,
        "input_coverage": f"{len(measured_inputs)}/{len(_KNOWN_INPUTS)}",
        "cell_status_counts": status_counts,
        "doctrine": (
            "These frameworks are proxies computed over VCS/issue artifacts, "
            "not pipeline/survey/incident data. Read every cell by its `status` "
            "(measured/proxy/not_measured) and treat the whole report as an "
            "indicator that routes attention, per the Mirror doctrine "
            "(ANALYSIS_STANDARD §0, §0.4, §0.5) — never as a verdict."
        ),
    }

    return {
        "dora": dora,
        "space": space,
        "dx_core4": dx_core4,
        "provenance": provenance,
    }
