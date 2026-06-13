"""Cohort classification and control signals (ANALYSIS_STANDARD.md §1.D, §3).

These functions produce the cohort grouping and the exonerating-control inputs
the outlier engine needs so it can compare like-with-like (§1.D cohort-validity)
and annotate flags with novelty/greenfield and ramp context. None of this ranks
anyone — it only decides *who is comparable to whom* and *what context might
exonerate an anomaly*.
"""

from __future__ import annotations

# DEFAULT_CRITICALITY maps a name-substring (matched case-insensitively against
# repo and module names) to a system-criticality class. Reasoning (§1.D
# system-criticality control): repeated failures correlate with blast radius,
# not craft, so we must normalize within criticality class. We seed the map from
# the blast radius of the Wander domains:
#   - payment/auth/availability/booking/pricing/sync are money-movement,
#     access-control, or system-of-record paths — a failure is customer- or
#     revenue-visible, so they are "critical" (or "high" for the slightly less
#     immediate ones).
#   - website/docs/marketing/sites are low-blast-radius surfaces; a defect is
#     embarrassing, rarely load-bearing, so "low".
#   - everything unmatched defaults to "standard" — most product/platform code.
# Order does not matter for lookup, but longer/more-specific substrings are not
# privileged; first match wins in iteration order, so keep entries unambiguous.
DEFAULT_CRITICALITY: dict[str, str] = {
    # critical — money movement, access control, system-of-record
    "payment": "critical",
    "payout": "critical",
    "billing": "critical",
    "invoic": "critical",
    "auth": "critical",
    "availability": "critical",
    "booking": "critical",
    # high — revenue-shaping or cross-system integrity, slightly less immediate
    "pricing": "high",
    "sync": "high",
    "property": "high",
    "pms": "high",
    "channex": "high",
    # low — low-blast-radius public surfaces
    "website": "low",
    "marketing": "low",
    "docs": "low",
    "sites": "low",
    "blog": "low",
}

_VALID_CLASSES = {"critical", "high", "standard", "low"}


def criticality_class(
    repo: str,
    module: str | None = None,
    *,
    overrides: dict | None = None,
) -> str:
    """Classify the system-criticality of a repo/module (§1.D).

    Matches name-substrings against ``overrides`` (if given) then
    ``DEFAULT_CRITICALITY``, case-insensitively, across both the repo name and
    the optional module name. Returns one of {critical, high, standard, low};
    unmatched work is "standard".
    """
    haystacks = [h.lower() for h in (repo, module) if h]
    table = overrides if overrides is not None else DEFAULT_CRITICALITY
    for substr, klass in table.items():
        s = substr.lower()
        if any(s in hay for hay in haystacks):
            if klass in _VALID_CLASSES:
                return klass
    return "standard"


def novelty_score(
    repo_age_days: float | None,
    new_file_ratio: float | None,
) -> float:
    """Estimate how novel/greenfield the work is, in [0.0, 1.0] (§1.D novelty).

    Higher = more novel = more likely that "catchable" errors are actually
    failure modes not yet in the suite (so a high catchable-error rate may not
    be catchable in hindsight).

    Inputs:
      - repo_age_days: age of the codebase; younger -> more novel. We treat
        anything <= 90 days as maximally novel (1.0 on this axis) decaying
        linearly to 0.0 at ~2 years (730 days).
      - new_file_ratio: fraction of touched files that are brand new; already in
        [0,1] and used directly as the novelty contribution of this axis.

    Documented default: a None input contributes 0.0 to its axis (no novelty
    signal -> assume mature/established, the conservative read that does NOT
    hand out a free exoneration). If BOTH are None the score is 0.0.
    The two axes are combined by taking the max, so strong evidence of novelty
    on either axis carries.
    """
    age_axis = 0.0
    if repo_age_days is not None:
        if repo_age_days <= 90.0:
            age_axis = 1.0
        elif repo_age_days >= 730.0:
            age_axis = 0.0
        else:
            # linear decay between 90 and 730 days
            age_axis = (730.0 - repo_age_days) / (730.0 - 90.0)

    file_axis = 0.0
    if new_file_ratio is not None:
        file_axis = max(0.0, min(1.0, float(new_file_ratio)))

    return max(age_axis, file_axis)


def is_ramping(tenure_weeks: float | None, threshold: float = 12.0) -> bool:
    """True if the engineer is still ramping (§3 tenure/ramp).

    Tenure below ``threshold`` weeks is "ramping; insufficient signal". Unknown
    tenure (None) is treated as ramping: absence of evidence is not evidence of
    establishment, and the conservative move is to withhold judgement.
    """
    if tenure_weeks is None:
        return True
    return tenure_weeks < threshold


def cohort_key(
    level: str | None,
    tenure_weeks: float | None,
    criticality: str | None,
) -> str:
    """Build a stable cohort key combining level, ramp bucket, criticality (§3, §1.D).

    Tenure is bucketed into "ramping" / "established" (not raw weeks) so the
    cohort is coarse enough to populate. Missing facets normalize to "unknown"
    so members with the same gaps still group together (a stable, deterministic
    key — not a positional one).
    """
    level_part = (level or "unknown").strip().lower()
    ramp_part = "ramping" if is_ramping(tenure_weeks) else "established"
    crit_part = (criticality or "unknown").strip().lower()
    return f"level={level_part}|ramp={ramp_part}|crit={crit_part}"
