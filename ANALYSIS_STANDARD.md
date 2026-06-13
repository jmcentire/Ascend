# Ascend Analysis Standard

**Version:** 2.1 — 2026-06-12
**Owner:** Jeremy McEntire
**Applies to:** every deeper-analysis run — `coach-analyze`, `coach-risks`, `coach-suggest`,
and any cohort / outlier analysis built on Ascend data.

**Changelog:** v2.1 incorporates the Jeremy-simulacrum strategy critique (2026-06-12): the
*output shape* — not the metric weighting — is what makes a tool a Mirror or a Frame. A
ranked "bottom-N to manage out" list is a Frame regardless of how the inputs are weighted.
This version rewrites the output contract (§0.5) and adds the failure-mode controls (§1.D)
and the investigation + misfire-audit protocols (§8–9) the critique demanded.

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

## 0.5 Output contract — Mirror, not Frame  *(load-bearing; from the Sim critique)*

The **shape** of the output, not the sophistication of the weighting, is what makes Ascend a
Mirror or a Frame. Get this wrong and every metric below becomes a weapon.

- **A Mirror outputs anomalies-to-investigate.** "These engineers are >2 SD above their
  level/tenure cohort on catchable-error rate — investigate why." The output is a *question*;
  the required next action is *investigation*.
- **A Frame outputs verdicts.** "These are the bottom 10 — raise the bar / manage out." The
  output is a *judgment*; the next action is *execution*. **Ascend must never emit this.**

Hard rules that follow:
1. **No ranked manage-out lists.** Ascend surfaces outliers against an absolute,
   cohort-relative threshold (e.g. >2 SD, or rate >Nx cohort median) — never a positional
   "bottom N." Positional ranking is forced-ranking (Vitality Curve); it guarantees a bottom
   segment exists even when everyone is strong, and it misclassifies globally-strong
   engineers who sit on exceptional teams. (A one-off manual ranking a human explicitly
   requests and interprets is their call; the *tool* does not generate or persist one.)
2. **Every flag ships with its candidate explanations**, including the ones that exonerate
   (see §1.D controls). The flag is the start of an investigation, not its conclusion.
3. **Investigation precedes action** (§8). If a manager moves to PIP/manage-out on an Ascend
   flag with no logged investigation, Ascend records that as a *process violation*, not a
   validated decision.

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

## 8. Investigation protocol  *(the Mirror's teeth)*
A flag is a hypothesis. Before any consequential action (PIP, manage-out, formal rating) on
an Ascend signal, the manager records an investigation answering, at minimum:
1. **Why** is the rate/anomaly high — what does digging in actually show?
2. **Is the comparison valid** — same level, tenure, work-novelty, system-criticality?
3. **What would change it** — a context/tooling fix (inadequate tests, greenfield) vs. a
   genuine performance gap?
4. **Verdict** — performance issue, context issue, or metric misfire.

Ascend stores the investigation against the flag. A consequential action with **no logged
investigation** is recorded as a process violation. Skipping investigation is the exact
failure mode the Mirror exists to prevent (the tool becoming the justification rather than
the trigger).

## 9. Misfire audit  *(keeps the metric honest)*
Quarterly, re-examine the prior period's flags. For each: was the signal valid, or a misfire
(novel work, invalid cohort, inadequate tooling, illegible/prevention work)? If the misfire
rate exceeds **~30%**, the metric is not fit to inform consequential action — demote it to
investigation-only and fix the controls before it is trusted again. Track misfire rate per
dimension over time; a dimension that cannot get below the threshold does not belong in the
weighting.
