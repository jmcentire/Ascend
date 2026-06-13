"""Within-cohort normalization primitives (ANALYSIS_STANDARD.md §3, §4).

"Normalize before you compare" (§0 first principle 3). These functions reduce a
cohort's raw values to the statistics the outlier engine thresholds against. No
function here ranks or orders members — they only describe a distribution and
place a single value within it.
"""

from __future__ import annotations

import math


def cohort_stats(values: list[float]) -> dict:
    """Compute n / mean / median / population-sd over a cohort's values.

    Population standard deviation (divide by n, not n-1) is used because we are
    describing the cohort itself, not estimating a wider population. sd is 0.0
    when n < 2 (a single point has no spread), which downstream zscore treats as
    "no discrimination possible" rather than dividing by zero.
    """
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "sd": 0.0}

    floats = [float(v) for v in values]
    mean = sum(floats) / n

    ordered = sorted(floats)
    mid = n // 2
    if n % 2 == 1:
        median = ordered[mid]
    else:
        median = (ordered[mid - 1] + ordered[mid]) / 2.0

    if n < 2:
        sd = 0.0
    else:
        variance = sum((v - mean) ** 2 for v in floats) / n
        sd = math.sqrt(variance)

    return {"n": n, "mean": mean, "median": median, "sd": sd}


def zscore(value: float, stats: dict) -> float:
    """Standard score of ``value`` within a cohort's ``stats``.

    Returns 0.0 when sd == 0 (no spread -> nobody is an outlier; never divide by
    zero). Positive means above the cohort mean, negative below.
    """
    sd = stats.get("sd", 0.0)
    if sd == 0.0:
        return 0.0
    return (float(value) - stats.get("mean", 0.0)) / sd


def ratio_to_median(value: float, stats: dict) -> float:
    """``value`` as a multiple of the cohort median (e.g. "3x cohort median").

    Returns 0.0 when the median is 0 (ratio undefined; avoids divide-by-zero).
    Useful for the §1.D "rate >Nx cohort median" phrasing alongside the z-score.
    """
    median = stats.get("median", 0.0)
    if median == 0:
        return 0.0
    return float(value) / median
