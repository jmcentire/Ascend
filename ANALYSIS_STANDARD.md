# Ascend Analysis Standard

**Version:** 2.1 — 2026-06-12
**Owner:** Jeremy McEntire
**Applies to:** every deeper-analysis run — `coach-analyze`, `coach-risks`, `coach-suggest`,
and any cohort / outlier analysis built on Ascend data.

**Changelog:**
- v2.2 (2026-06-12): corrected scope per Jeremy — the goal is **comprehensive analysis for
  every engineer**, and the tool is **agnostic about how the reader uses it**. Rewrote §0.5
  away from usage-governance (no "the tool must never rank / investigation-before-action /
  process-violation" enforcement) toward analysis-for-all + the analytical-correctness
  controls. Investigation logging (§8) and the misfire audit (§9) are now *optional* tooling
  (note-taking + tracking the tool's own accuracy), not gates on the manager. The genuine
  Sim insight is retained where it belongs: keep the analysis honest, don't fake signals,
  don't penalize illegible work — but don't police usage.
- v2.1 (2026-06-12): incorporated the Jeremy-simulacrum critique on metric-correctness
  failure modes (§1.D controls: novelty, system-criticality, cohort-validity).

This is the single source of truth for *what we measure and how we reason about it*. The
`coach-analyze` system prompt encodes this document; if the two disagree, this document wins
and the prompt is the bug.

---

## 0. First principles (read before using any number)

1. **An activity index is an indicator, never a verdict.** Commit/PR/issue counts are a
   weighted sum of *countable artifacts*. Prevention, multiplication, and craft leave no
   artifact and register as LOW. Every derived signal routes attention ("investigate why"),
   it does not conclude.
2. **Rank from the full eligible roster, never from a pre-filtered seed.** Enriching an
   already-short list can only re-order it — it can never surface someone the thin filter
   missed. Selection must use the same rich signals as the read. (See §5, De-anchoring.)
3. **Normalize before you compare.** Raw volume is meaningless across levels and tenures.
   Always reduce to within-band and per-active-week before drawing a line. (See §4.)
4. **Name the data you don't have.** If a dimension below is absent from the context you
   were given, say so explicitly and lower confidence — do not infer it from adjacent
   metrics or stay silent.

---

## 0.5 Output contract — analysis for all, honestly

The product is **comprehensive, multi-dimensional analysis for every engineer.** The tool's
job is to make that analysis *true and complete*; it is **agnostic about how the reader uses
it**. The tool does not decide, gate, or police usage — that is the manager's call. What the
tool owes is correctness, not governance.

What that means in practice:
1. **Analysis for all, not a hunt for the bad ones.** The primary surface (`report-analysis`)
   covers *every* engineer across every dimension — output, multiplication, flow, quality,
   and the industry frameworks — shown both absolute and cohort-relative. Anomaly/outlier
   views (`coach-outliers`) are *one optional lens*, not the product.
2. **Don't collapse to a single verdict score.** A one-number ranking hides exactly the
   illegible / multiplication / prevention work the controls below exist to surface. Present
   the dimensions; let the reader sort, weigh, and decide. The tool will happily sort by any
   dimension — sorting is a reader convenience and carries no judgment.
3. **The analytical-correctness controls are mandatory** — they keep the analysis honest, and
   that is the one thing the tool is opinionated about:
   - cohort normalization by level / tenure / criticality (§3–4),
   - crediting multiplication / review-load, not penalizing it (§1.B),
   - novelty / criticality / cohort-validity context on every comparison (§1.D),
   - data-gap honesty — name what isn't measured, never proxy it silently (§0.4),
   - CFR/reverts demoted as a dead discriminator on a fix-forward team (§1.D).

(The activity-index-is-an-indicator-not-a-verdict principle, §0.1, still holds: a number is a
starting point for understanding a person's work, never the whole of it.)

---

## 1. Dimensions (every deeper analysis must cover all of these)

### A. Output & throughput
- Commits, merged PRs, Linear issues completed.
- **Landing rate** — merged PRs vs commit volume. A large commits/merged gap = "work that
  isn't landing" (scoping, review-throughput, or abandonment). Flag it; it hides inside raw
  commit counts.

### B. Multiplication / review engagement  *(decisive — do not omit)*
- **Reviews given** and **co-authored commits**: value that lands in *someone else's* output.
- Read review *given* against review *consumed*. Heavy givers (carrying the team's review
  load) will show suppressed personal output — that explains a low index, it is **not**
  underperformance. Low givers who consume lots of review are the real flag.

### C. Flow & latency  *(languishing — Jeremy's stated focus)*
- **Stale-hours**: open-PR idle time summed per author.
- **Rotting PRs**: open and idle ≥ 7 days.
- **PR cycle-time p85**: time-to-land (open → merge).
- **Languishing tickets**: Linear issues with little/no action for days.
- Languishing work — "little to no action in hours and hours and days" — is a first-class
  signal, weighted with the quality block below, not an afterthought.

### D. Quality & reliability  *(heaviest block)*
- **Repeated failures — WEIGHT HEAVIEST.** The same class of issue recurring: reopened
  issues, the same bug/incident pattern landing more than once, regressions on previously
  "fixed" areas. A pattern of repeats outweighs any volume metric.
- **Catchable errors.** Defects that a competent review, an existing test, or CI *should*
  have caught before merge/prod — the avoidable miss, not the genuinely-hard bug. Weighted
  with repeated failures.
- **Bug-fix share** — % of completed work that is bug/firefighting vs. feature. High share
  is ambiguous (stuck-in-churn vs. carrying cleanup) — surface it, interpret with context.
- **Test presence** — do PRs ship with tests in areas that warrant them.
- **CFR / git reverts — DO NOT LEAN ON THIS.** On a fix-forward team reverts are near-zero
  (≈39 org-wide/quarter) and do not discriminate. Reopened/recurring issues (above) is the
  real quality signal; CFR is reported for completeness only.

**Controls — the quality block penalizes exactly the work we want unless these fire**
*(from the Sim critique — each is mandatory before any quality flag is surfaced):*
- **Novelty / greenfield control.** Catchable-error rate presupposes review/test/CI are
  *adequate to the work*. Greenfield or novel-infrastructure work has failure modes not yet
  in the suite, so "catchable" errors read high *because the work is uncharted*. Tag work
  context (new service/module, first-of-kind integration, migration) and either exclude it
  from the catchable-error signal or annotate the flag with "novel work — failures may not
  be catchable in hindsight."
- **System-criticality control.** Repeated failures correlate with *blast radius*, not just
  craft. The payments pipeline fails more visibly than the marketing site because the stakes
  are higher. Normalize repeated-failure rate *within system-criticality class*; never
  compare an owner of a hard, high-stakes system against an owner of a low-stakes one. Owning
  hard things must not mechanically lower standing.
- **Cohort-validity control.** Before a flag, confirm the peer cohort is doing comparable
  work. "3x peer catchable-error rate" is meaningless if the peers maintain mature systems
  with comprehensive CI and the flagged engineer is on greenfield infra. Invalid comparison
  → no flag; surface the comparison gap instead.

### E. Engagement (Slack)  *(caveated — see §6)*

---

## 2. Weighting

Heaviest → lightest, but **all subordinate to the §4 guardrails** (a high repeated-failure
count is only meaningful *after* tenure/level normalization and identity verification):

1. **Repeated failures** (recurring issues / reopened / regressions) — heaviest.
2. **Catchable errors** + **languishing flow** (stale/rotting/cycle).
3. **Quality mix** (bug share, test presence) + **landing rate**.
4. **Output volume** + **review engagement** (engagement *raises* standing; low output with
   heavy multiplication is neutral, not negative).
5. CFR/reverts, Slack — informational only.

---

## 3. Required normalizations
- **Per-level band.** Compare within ladder band (PE II vs PE II). Express as z-score within
  band before ranking across bands.
- **Tenure / ramp.** Use first-commit date; express output as **merges-per-active-week**,
  not raw volume. A new hire reads as "low output" identically to a coaster — the denominator
  is what tells them apart. Flag <~12 weeks tenure as "ramping; insufficient signal."

---

## 4. Identity resolution
- Resolve **Linear email → GitHub login → Slack ID** per person; apply the org email-alias
  map (`config/email_aliases.csv`) so personal-email commits attribute correctly.
- Known failure modes to handle explicitly, not silently drop:
  - GitHub accounts not indexed by author-search → enumerate commits via email/commit-PR linkage; note "reviews given" is then unmeasurable.
  - Authors with zero Linear activity → likely a tracking-process gap, not absence. Confirm before any read.

## 5. De-anchoring (selection integrity)
- Any bottom-N / cohort / bar-raise ranking must be computed over the **entire eligible
  roster** with the full §1 signal set — not by enriching a list pre-selected on a thinner
  metric. Document the eligible set and the exclusions.
- **Exclusions** (wrong ruler — never rank on IC output): Engineering Managers, PMs, QA,
  interns, and departed members. State them.

## 6. Slack engagement caveat
- Workspace-wide per-engineer Slack activity is **not reliably measurable** with the current
  bot token (no search scope, partial channel coverage, no DMs/most threads). Do not present
  it as a ranking signal. Use **reviews-given** as the engagement proxy. Only scan an
  explicitly-named channel set on request.

---

## 7. Data sources & wiring status

| Dimension | Source | In Ascend now? |
|-----------|--------|----------------|
| Commits, merged/open PRs | `integrations/github.py` | ✅ collected |
| Reviews given, co-authored | `integrations/github.py` | ✅ collected; surfaced in `coach-analyze` context (fixed 2026-06-12) |
| Issues completed/in-progress | `integrations/linear.py` | ✅ collected |
| Bug-fix share | `linear.bug_share()` | ✅ collected into snapshot (2026-06-12) |
| Stale-hours, rotting PRs, PR cycle p85 | `github.compute_flow_metrics()` | ✅ wired into snapshot (2026-06-12) |
| **Repeated failures / reopened issues** | `linear.count_reopened()` (issue state-history) | ✅ collected into snapshot (2026-06-12) — heaviest-weighted |
| DORA / SPACE / DX Core 4 | `integrations/frameworks.py` | ✅ computed (proxies, provenance-tagged) |
| Outlier detection (cohort z-score) | `analysis/outliers.py` + `coach-outliers` | ✅ Mirror-correct; no positional bottom-N |
| Investigation + misfire audit (§8/§9) | `analysis/investigation.py` + `coach-investigate`/`coach-audit` | ✅ implemented |
| Per-level band + tenure/ramp | `coach._parse_level` + `github.first_commit_date`/`tenure_weeks` | ✅ at analysis time |
| System-criticality class | `analysis/cohorts.py` + `criticality:<class>` member flag | ◐ default map + opt-in flag; **auto-detection per repo TODO** |
| Reverts / CFR | `tools/scripts/.../dora-attribution` | ⛔ external — informational only (§1.D), intentionally not leaned on |
| **Catchable errors** | review-comment / CI-failure / test-gap signals | ⛔ **not yet collected** — `coach-outliers` reports this as a data gap (§0.4), does not proxy it |
| Work-novelty tag | repo-age / new-file-ratio heuristic | ◐ `cohorts.novelty_score()` exists; **not yet fed from a collector** (defaults to 0.0 with caveat) |

**Remaining collector work:** catchable-error signal; per-repo auto-detection of
system-criticality and work-novelty (today: criticality via opt-in member flag, novelty
inactive). Until a row is wired, deeper analyses flag that dimension as "not in context"
per §0.4 rather than infer it — `coach-outliers` does exactly this for catchable-errors,
tenure-unknown, and criticality-unknown.

---

## 8. Investigation log  *(optional)*
When someone *does* dig into a finding, they can record what they found — why the anomaly is
there, whether the comparison was valid, what would change it, and a verdict
(performance / context / misfire). This is **optional note-taking**, not a gate: the tool
does not require it and does not police whether anyone acts before logging. Its one real
payoff is §9 — recorded verdicts are what let the tool measure its own accuracy.

## 9. Misfire audit  *(keeps the analysis honest about itself)*
Periodically, re-examine prior flags that were investigated: was the signal valid, or a
misfire (novel work, invalid cohort, inadequate tooling, illegible/prevention work)? If a
dimension misfires more than **~30%** of the time, that's the *tool* telling you the
dimension isn't earning its keep — fix the controls or stop foregrounding it. This audits the
analysis, not the analyst.
