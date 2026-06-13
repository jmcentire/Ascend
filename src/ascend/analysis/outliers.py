"""Mirror-correct outlier engine (ANALYSIS_STANDARD.md §0.5).

§0.5 — Output contract — Mirror, not Frame:

    "A Mirror outputs anomalies-to-investigate. 'These engineers are >2 SD above
    their level/tenure cohort on catchable-error rate — investigate why.' The
    output is a *question*; the required next action is *investigation*.
    A Frame outputs verdicts. 'These are the bottom 10 — raise the bar / manage
    out.' ... Ascend must never emit this.

    Hard rules:
    1. No ranked manage-out lists. Ascend surfaces outliers against an absolute,
       cohort-relative threshold (e.g. >2 SD, or rate >Nx cohort median) — never
       a positional 'bottom N.'
    2. Every flag ships with its candidate explanations, including the ones that
       exonerate (see §1.D controls). The flag is the start of an investigation,
       not its conclusion.
    3. Investigation precedes action (§8)."

This module therefore produces ZERO positional/bottom-N output. Every flag is a
threshold-relative anomaly carrying candidate explanations on BOTH sides — the
exonerating §1.D controls when they apply, plus at least one non-exonerating
"genuine performance gap" candidate — so the reader investigates rather than
concludes. The order of the returned list is incidental (grouped by spec then
cohort) and carries no ranking meaning.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cohorts import cohort_key, is_ramping
from .normalization import cohort_stats, ratio_to_median, zscore


@dataclass
class DimensionSpec:
    """One quality/flow dimension to scan for cohort-relative outliers.

    Attributes:
      name: human-readable dimension label (e.g. "repeated_failures").
      metric_key: key into each member dict holding that member's metric value.
      direction: "high_bad" (a high value is the concern) or "low_bad" (a low
        value is the concern, e.g. landing rate).
      threshold_sd: how many SDs from the cohort mean (in the bad direction)
        triggers a flag. Default 2.0 per §0.5 example.
      min_cohort: below this cohort size the comparison is considered thin and
        the flag is annotated with the cohort-validity exoneration (§1.D). It
        does NOT suppress the flag — it weakens it explicitly.
    """

    name: str
    metric_key: str
    direction: str = "high_bad"
    threshold_sd: float = 2.0
    min_cohort: int = 4


# Dimensions where §1.D's system-criticality control applies: repeated failures
# and catchable-error / quality signals correlate with blast radius, so owning a
# critical/high system can inflate them without implying poor craft.
_QUALITY_DIMENSIONS = {
    "repeated_failures",
    "repeated_failure",
    "catchable_errors",
    "catchable_error",
    "quality",
    "reopened_issues",
    "regressions",
}


def _build_explanations(member: dict, spec: DimensionSpec, cohort_n: int) -> list[dict]:
    """Candidate explanations for a flag — exonerating (§1.D) plus a genuine one.

    Always emits at least one NON-exonerating candidate so the flag presents both
    sides, never a one-way verdict.
    """
    explanations: list[dict] = []

    novelty = member.get("novelty")
    if novelty is not None and novelty >= 0.5:
        explanations.append(
            {
                "label": "novel/greenfield work",
                "rationale": (
                    "novel/greenfield work — failures may not be catchable in "
                    "hindsight"
                ),
                "exonerating": True,
            }
        )

    criticality = (member.get("criticality") or "").strip().lower()
    if criticality in {"critical", "high"} and spec.name.lower() in _QUALITY_DIMENSIONS:
        explanations.append(
            {
                "label": "high system-criticality",
                "rationale": (
                    "owns high-blast-radius system; repeats correlate with "
                    "stakes, not craft"
                ),
                "exonerating": True,
            }
        )

    if cohort_n < spec.min_cohort:
        explanations.append(
            {
                "label": "thin cohort",
                "rationale": (
                    f"thin cohort (n={cohort_n}); comparison may be invalid"
                ),
                "exonerating": True,
            }
        )

    if is_ramping(member.get("tenure_weeks")):
        explanations.append(
            {
                "label": "ramping",
                "rationale": "ramping (<12wk); insufficient signal",
                "exonerating": True,
            }
        )

    # At least one non-exonerating candidate so BOTH sides are always presented.
    explanations.append(
        {
            "label": "genuine performance gap",
            "rationale": (
                "genuine performance gap at level — investigate whether the "
                "anomaly reflects craft rather than context"
            ),
            "exonerating": False,
        }
    )

    return explanations


def detect_outliers(members: list[dict], specs: list[DimensionSpec]) -> list[dict]:
    """Surface threshold-relative outliers per dimension (§0.5).

    For each spec: group members by cohort_key(level, tenure_weeks,
    criticality); within each cohort with n>=2 compute cohort_stats over the
    metric; flag a member whose z-score crosses ``threshold_sd`` in the BAD
    direction (high_bad: z > +t; low_bad: z < -t).

    Returns a list of flag dicts. ABSOLUTELY NO positional/bottom-N ranking is
    performed — the list order is grouping order only and carries no meaning.
    Each flag carries candidate explanations (§1.D controls + a genuine-gap
    candidate) so it reads as a question to investigate, not a verdict.
    """
    flags: list[dict] = []

    for spec in specs:
        # Group members by cohort.
        cohorts: dict[str, list[dict]] = {}
        for m in members:
            if spec.metric_key not in m:
                continue
            key = cohort_key(
                m.get("level"),
                m.get("tenure_weeks"),
                m.get("criticality"),
            )
            cohorts.setdefault(key, []).append(m)

        for key, group in cohorts.items():
            if len(group) < 2:
                # No spread can be established from a single point (§4).
                continue

            values = [float(m[spec.metric_key]) for m in group]
            stats = cohort_stats(values)
            if stats["sd"] == 0.0:
                # Uniform cohort -> nobody is an outlier. No flags. (Guards the
                # "uniform cohort yields zero flags" invariant.)
                continue

            for m in group:
                value = float(m[spec.metric_key])
                z = zscore(value, stats)

                if spec.direction == "high_bad":
                    triggered = z > spec.threshold_sd
                elif spec.direction == "low_bad":
                    triggered = z < -spec.threshold_sd
                else:
                    triggered = False

                if not triggered:
                    continue

                severity = "strong" if abs(z) > 3.0 else "watch"

                flags.append(
                    {
                        "member": m.get("name"),
                        "dimension": spec.name,
                        "metric_key": spec.metric_key,
                        "value": value,
                        "cohort_key": key,
                        "cohort_n": stats["n"],
                        "cohort_median": stats["median"],
                        "cohort_sd": stats["sd"],
                        "z_score": z,
                        "ratio_to_median": ratio_to_median(value, stats),
                        "direction": spec.direction,
                        "severity": severity,
                        "explanations": _build_explanations(m, spec, stats["n"]),
                    }
                )

    return flags
