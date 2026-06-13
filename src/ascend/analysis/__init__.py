"""Ascend analysis package — Mirror-correct outlier engine.

Implements the cohort-relative, threshold-based outlier detection required by
ANALYSIS_STANDARD.md §0.5 (Output contract — Mirror, not Frame). This package
NEVER emits positional bottom-N rankings; it surfaces threshold-relative
anomalies-to-investigate, each shipped with candidate explanations (including
exonerating ones from the §1.D controls).

Public surface:
  - cohorts: criticality classification, novelty/ramp signals, cohort keys
  - normalization: within-cohort statistics (§3, §4)
  - outliers: DimensionSpec + detect_outliers (§0.5 output contract)
"""

from .cohorts import (
    DEFAULT_CRITICALITY,
    cohort_key,
    criticality_class,
    is_ramping,
    novelty_score,
)
from .normalization import cohort_stats, ratio_to_median, zscore
from .outliers import DimensionSpec, detect_outliers

__all__ = [
    "DEFAULT_CRITICALITY",
    "criticality_class",
    "novelty_score",
    "is_ramping",
    "cohort_key",
    "cohort_stats",
    "zscore",
    "ratio_to_median",
    "DimensionSpec",
    "detect_outliers",
]
