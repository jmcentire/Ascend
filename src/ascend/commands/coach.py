"""Coach commands — analyze, risks, STAR assessments, suggestions."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional

from ascend.audit import log_operation
from ascend.config import DB_PATH, load_config
from ascend.db import get_connection
from ascend.output import format_table, render_output


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def _resolve_member(identifier: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Resolve member by name, github, email, or ID."""
    if identifier.isdigit():
        row = conn.execute("SELECT * FROM members WHERE id = ?", (int(identifier),)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM members WHERE LOWER(name) = LOWER(?) OR github = ? OR email = ?",
            (identifier, identifier, identifier),
        ).fetchone()
    return dict(row) if row else None


# ---- Coach: Analyze ----

def cmd_coach_analyze(args: argparse.Namespace) -> None:
    """Comprehensive member analysis (LLM-powered)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    config = load_config()

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    context = _gather_full_context(m, conn)
    conn.close()

    from ascend.summarizer import get_client
    client = get_client(config)

    if not client:
        if json_mode:
            render_output({"error": "LLM API key not configured", "context": context}, json_mode=True, copy=copy)
        else:
            render_output(f"Error: LLM API key not configured.\n\nContext data:\n{context}", copy=copy)
        log_operation("coach analyze", args={"member": args.member}, error="no API key")
        return

    # This rubric encodes ANALYSIS_STANDARD.md (repo root). Keep them in sync; the doc wins.
    system_prompt = (
        "You are a coaching advisor for engineering managers. You apply the Ascend Analysis "
        "Standard v2. Given comprehensive data about a team member, produce a detailed "
        "analysis.\n\n"
        "FIRST PRINCIPLES (do not violate):\n"
        "- An activity index (commit/PR/issue counts) is an indicator to investigate, NEVER a "
        "verdict. Prevention, multiplication, and craft leave no countable artifact and read "
        "as LOW — say so rather than concluding underperformance.\n"
        "- Name the data you do NOT have. If a dimension below is absent from the context, "
        "state that explicitly and lower confidence — never infer it from adjacent metrics.\n"
        "- Normalize before comparing: by ladder level (within-band) and by tenure "
        "(merges-per-active-week, not raw volume; <~12 weeks tenure = ramping, insufficient "
        "signal).\n\n"
        "COVER EVERY DIMENSION (flag any with no data):\n"
        "A. Output & throughput — commits, merged PRs, issues; and LANDING RATE (a large "
        "commits-vs-merged gap = work that isn't landing).\n"
        "B. Multiplication / review engagement — reviews GIVEN and co-authored commits. Heavy "
        "review-givers carry the team and will show suppressed personal output; that EXPLAINS "
        "a low index, it is not a deficit. Low givers who consume lots of review are the flag.\n"
        "C. Flow & latency (LANGUISHING) — stale open-PR hours, rotting PRs (idle >=7d), PR "
        "cycle-time p85 (time-to-land), and languishing tickets (little/no action for days).\n"
        "D. Quality & reliability (HEAVIEST BLOCK):\n"
        "   - REPEATED FAILURES — weight this most heavily of anything. The same class of "
        "issue recurring: reopened issues, the same bug/incident pattern more than once, "
        "regressions on previously-'fixed' areas. A pattern of repeats outweighs any volume "
        "metric.\n"
        "   - CATCHABLE ERRORS — defects a competent review, an existing test, or CI SHOULD "
        "have caught before merge/prod (the avoidable miss, not the genuinely-hard bug). "
        "Weighted with repeated failures.\n"
        "   - Bug-fix share (firefighting vs feature) and test presence.\n"
        "   - CFR / git reverts: DO NOT lean on this — on a fix-forward team reverts are "
        "near-zero and do not discriminate. Reopened/recurring issues is the real quality "
        "signal.\n\n"
        "WEIGHTING (heaviest -> lightest, all subordinate to normalization): repeated "
        "failures; then catchable errors + languishing flow; then quality mix + landing rate; "
        "then output volume + review engagement (engagement RAISES standing); CFR/reverts and "
        "Slack are informational only.\n\n"
        "OUTPUT SECTIONS:\n"
        "1. **Executive Summary** — current standing, key observations, confidence given data coverage\n"
        "2. **Performance Assessment** — across dimensions A-D, normalized for level and tenure\n"
        "3. **Attention Required** — lead with repeated failures and catchable errors; then languishing flow\n"
        "4. **Strengths & Wins** — include multiplication/review load explicitly\n"
        "5. **Growth Areas**\n"
        "6. **Recommended Actions** — specific next steps for the manager\n"
        "7. **Data Gaps** — dimensions not present in the provided context\n\n"
        "Be data-driven but empathetic. Use markdown formatting."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Analyze this team member:\n\n{context}"}],
        )
        analysis = response.content[0].text
    except Exception as e:
        if json_mode:
            render_output({"error": str(e)}, json_mode=True, copy=copy)
        else:
            render_output(f"LLM error: {e}", copy=copy)
        log_operation("coach analyze", args={"member": args.member}, error=str(e))
        return

    log_operation("coach analyze", args={"member": args.member}, result="success")

    if json_mode:
        render_output({"member": m["name"], "analysis": analysis}, json_mode=True, copy=copy)
    else:
        render_output(analysis, copy=copy)


# ---- Coach: Risks ----

def cmd_coach_risks(args: argparse.Namespace) -> None:
    """Risk dashboard — algorithmic detection of flight, burnout, bus factor, underperformance."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)

    members = [dict(r) for r in conn.execute(
        "SELECT * FROM members WHERE status = 'active'"
    ).fetchall()]

    risk_reports = []
    for m in members:
        risks = _compute_risks(m, conn)
        if risks["signals"]:
            risk_reports.append(risks)

    conn.close()
    log_operation("coach risks")

    # Sort by total risk score descending
    risk_reports.sort(key=lambda r: r["risk_score"], reverse=True)

    if json_mode:
        render_output(risk_reports, json_mode=True, copy=copy)
    else:
        if not risk_reports:
            render_output("# Risk Dashboard\n\nNo risk signals detected.")
            return

        parts = [f"# Risk Dashboard\n"]
        parts.append(f"**Members with risk signals:** {len(risk_reports)}\n")

        headers = ["Member", "Risk Score", "Signals"]
        rows_data = []
        for r in risk_reports:
            signals_str = ", ".join(r["signals"])
            rows_data.append([r["member"], str(r["risk_score"]), signals_str])
        parts.append(format_table(headers, rows_data))

        parts.append("")
        for r in risk_reports:
            parts.append(f"\n## {r['member']} (risk score: {r['risk_score']})")
            for signal in r["signals"]:
                parts.append(f"- {signal}")
            if r.get("details"):
                for k, v in r["details"].items():
                    parts.append(f"  {k}: {v}")

        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Coach: STAR ----

def cmd_coach_star(args: argparse.Namespace) -> None:
    """Record a STAR behavioral assessment."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    star = {
        "situation": args.situation,
        "task": args.task,
        "action": args.action,
        "result": args.result,
    }
    content = json.dumps(star)

    cursor = conn.execute(
        "INSERT INTO coaching_entries (member_id, kind, content) VALUES (?, 'star_assessment', ?)",
        (m["id"], content),
    )
    conn.commit()
    entry_id = cursor.lastrowid

    result = {
        "id": entry_id,
        "member": m["name"],
        "member_id": m["id"],
        "kind": "star_assessment",
        "star": star,
    }

    conn.close()
    log_operation("coach star", args={"member": args.member})

    if json_mode:
        render_output(result, json_mode=True)
    else:
        parts = [f"STAR assessment recorded for {m['name']} (#{entry_id})"]
        parts.append(f"  Situation: {args.situation}")
        parts.append(f"  Task: {args.task}")
        parts.append(f"  Action: {args.action}")
        parts.append(f"  Result: {args.result}")
        render_output("\n".join(parts))


# ---- Coach: Suggest ----

def cmd_coach_suggest(args: argparse.Namespace) -> None:
    """Coaching suggestions for next 1:1 (LLM-powered)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    config = load_config()

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    context = _gather_full_context(m, conn)

    # Also include coaching history
    entries = conn.execute(
        "SELECT kind, content, created_at FROM coaching_entries WHERE member_id = ? ORDER BY created_at DESC LIMIT 10",
        (m["id"],),
    ).fetchall()
    if entries:
        context += "\n\nCoaching history:"
        for e in entries:
            context += f"\n  [{e['kind']}] {e['created_at']}: {e['content'][:200]}"

    # Include risk signals
    risks = _compute_risks(m, conn)
    if risks["signals"]:
        context += f"\n\nRisk signals: {', '.join(risks['signals'])}"

    conn.close()

    from ascend.summarizer import get_client
    client = get_client(config)

    if not client:
        if json_mode:
            render_output({"error": "LLM API key not configured", "context": context}, json_mode=True, copy=copy)
        else:
            render_output(f"Error: LLM API key not configured.\n\nContext data:\n{context}", copy=copy)
        log_operation("coach suggest", args={"member": args.member}, error="no API key")
        return

    system_prompt = (
        "You are a coaching advisor for engineering managers preparing for a 1:1 meeting. "
        "Given data about a team member, generate specific coaching suggestions:\n\n"
        "1. **Topics to discuss** — prioritized by importance\n"
        "2. **Questions to ask** — open-ended, growth-oriented\n"
        "3. **Feedback to give** — specific, behavioral (STAR format when applicable)\n"
        "4. **Watch for** — signals to observe during the conversation\n"
        "5. **Follow-up actions** — what to do after the meeting\n\n"
        "Be specific and actionable. Use markdown."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Coaching suggestions for {m['name']}:\n\n{context}"}],
        )
        suggestions = response.content[0].text
    except Exception as e:
        if json_mode:
            render_output({"error": str(e)}, json_mode=True, copy=copy)
        else:
            render_output(f"LLM error: {e}", copy=copy)
        log_operation("coach suggest", args={"member": args.member}, error=str(e))
        return

    log_operation("coach suggest", args={"member": args.member}, result="success")

    if json_mode:
        render_output({"member": m["name"], "suggestions": suggestions}, json_mode=True, copy=copy)
    else:
        render_output(suggestions, copy=copy)


# ---- Risk Algorithm ----

def _compute_risks(member: dict, conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute risk signals for a member. Returns dict with signals list and score."""
    signals: list[str] = []
    details: dict[str, Any] = {}
    risk_score = 0

    member_id = member["id"]
    now = datetime.now()
    thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    # Get flags
    flags = [r["flag"] for r in conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member_id,)
    ).fetchall()]

    # Explicit flags
    if "flight_risk" in flags:
        signals.append("flight_risk flag set")
        risk_score += 30
    if "pip" in flags:
        signals.append("on PIP")
        risk_score += 20

    # Performance data (last 30 days)
    snapshots = conn.execute(
        """SELECT date, metrics, score FROM performance_snapshots
           WHERE member_id = ? AND date >= ? ORDER BY date""",
        (member_id, thirty_days_ago),
    ).fetchall()

    # The snapshot "score" is a visible-activity index (a weighted sum of
    # commits/PRs/issues), NOT a performance verdict. Prevention, multiplication,
    # and craft leave no countable artifact, so they register as LOW here. Every
    # signal derived from it is therefore an indicator that should route attention
    # ("investigate why"), never a conclusion. Risk weights are deliberately small.
    if snapshots:
        scores = [s["score"] or 0 for s in snapshots]
        avg_score = sum(scores) / len(scores)
        details["avg_activity_30d"] = round(avg_score, 1)

        # Multiplication: reviewing others' PRs and helping land others' commits
        # (co-authorship). Activity metrics tend to miss this kind of work — its
        # value lands in someone else's output, not in this member's own
        # commit/PR counts — so we surface it explicitly and let it explain a low
        # activity index rather than reading as underperformance.
        total_reviews = 0
        total_coauthored = 0
        for s in snapshots:
            m = json.loads(s["metrics"]) if s["metrics"] else {}
            total_reviews += m.get("reviews_given", 0)
            total_coauthored += m.get("coauthored_commits", 0)
        total_multiplication = total_reviews + total_coauthored
        details["reviews_given_30d"] = total_reviews
        details["coauthored_commits_30d"] = total_coauthored
        details["multiplication_30d"] = total_multiplication

        # Low visible output — an indicator, not a verdict. If the person is doing
        # heavy multiplication, that explains the low index; surface it as
        # multiplication instead of flagging it as a risk.
        if avg_score < 3 and len(snapshots) >= 3:
            if total_multiplication >= 5:
                signals.append(
                    f"multiplication: {total_reviews} reviews + {total_coauthored} co-authored "
                    "commits on others' work in 30d — value lands in others' output, not this "
                    "member's activity index"
                )
            else:
                signals.append(
                    "low visible output: activity index avg < 3 over 30d — "
                    "investigate why (may be prevention/multiplication/illegible work)"
                )
                risk_score += 15

        # Declining trend
        if len(scores) >= 3:
            first_half = sum(scores[:len(scores) // 2]) / max(1, len(scores) // 2)
            second_half = sum(scores[len(scores) // 2:]) / max(1, len(scores) - len(scores) // 2)
            if first_half > 0 and second_half < first_half * 0.5:
                signals.append("declining visible activity: second half < 50% of first half — investigate why")
                risk_score += 10

        # Sustained high output — high activity is not burnout by itself; the real
        # signal is load vs. recharge, which lives in the 1:1, not the commit count.
        if avg_score > 40:
            signals.append(
                "sustained high visible output (avg > 40) — check load vs. recharge in 1:1; "
                "high output is not burnout by itself"
            )
            risk_score += 5

        # Overwork: high issues_in_progress
        total_in_progress = 0
        for s in snapshots:
            m_data = json.loads(s["metrics"]) if s["metrics"] else {}
            total_in_progress += m_data.get("issues_in_progress", 0)
        avg_wip = total_in_progress / len(snapshots)
        if avg_wip > 5:
            signals.append(f"high WIP: avg {avg_wip:.1f} issues in progress")
            risk_score += 10
            details["avg_wip"] = round(avg_wip, 1)
    else:
        # No countable activity. This is an indicator to look closer, not a
        # deficit — it is exactly what illegible/prevention work, or a data gap,
        # produces. Small weight; the answer is "investigate," not "underperformer."
        signals.append("no visible activity data in last 30 days — investigate why (illegible/prevention work, or a data gap)")
        risk_score += 5

    # Meeting freshness — INFORMATIONAL ONLY, never risk. At any real team size
    # the baseline 1:1 cadence may be monthly or longer, gaps are often
    # deliberate, and not every 1:1 is recorded here (recorded != occurred).
    # Treating a gap as risk manufactures false signal, so it lives in details
    # and adds zero risk_score.
    last_meeting = conn.execute(
        "SELECT date FROM meetings WHERE member_id = ? ORDER BY date DESC LIMIT 1",
        (member_id,),
    ).fetchone()
    if last_meeting:
        details["last_recorded_1on1"] = last_meeting["date"]
    else:
        details["last_recorded_1on1"] = "none on record (note: not all 1:1s are uploaded)"

    # Sentiment trend
    recent_meetings = conn.execute(
        """SELECT sentiment_score FROM meetings
           WHERE member_id = ? AND date >= ? AND sentiment_score IS NOT NULL
           ORDER BY date""",
        (member_id, thirty_days_ago),
    ).fetchall()
    if len(recent_meetings) >= 2:
        sentiments = [r["sentiment_score"] for r in recent_meetings]
        avg_sentiment = sum(sentiments) / len(sentiments)
        details["avg_sentiment_30d"] = round(avg_sentiment, 2)
        if avg_sentiment < 0.4:
            signals.append(f"low meeting sentiment: avg {avg_sentiment:.2f}")
            risk_score += 15
        if len(sentiments) >= 3 and sentiments[-1] < sentiments[0] - 0.2:
            signals.append("declining sentiment trend")
            risk_score += 10

    # Open items overload
    open_items_count = conn.execute(
        """SELECT COUNT(*) FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'""",
        (member_id,),
    ).fetchone()[0]
    if open_items_count > 10:
        signals.append(f"action item overload: {open_items_count} open items")
        risk_score += 10
        details["open_items"] = open_items_count

    # Bus factor: sole contributor (only person with snapshots in their team)
    if member.get("team_id"):
        team_members_with_data = conn.execute(
            """SELECT COUNT(DISTINCT ps.member_id)
               FROM performance_snapshots ps
               JOIN team_members tm ON tm.member_id = ps.member_id
               WHERE tm.team_id = ? AND ps.date >= ?""",
            (member["team_id"], thirty_days_ago),
        ).fetchone()[0]
        if team_members_with_data == 1:
            signals.append("bus factor: sole contributor with data on team")
            risk_score += 15

    # Cap at 100
    risk_score = min(risk_score, 100)

    return {
        "member": member["name"],
        "member_id": member_id,
        "risk_score": risk_score,
        "signals": signals,
        "details": details,
    }


# ---- Context Gathering ----

def _gather_full_context(member: dict, conn: sqlite3.Connection) -> str:
    """Gather comprehensive context about a member for LLM prompts."""
    parts = [f"Member: {member['name']}"]
    if member.get("title"):
        parts.append(f"Title: {member['title']}")
    if member.get("github"):
        parts.append(f"GitHub: {member['github']}")
    if member.get("email"):
        parts.append(f"Email: {member['email']}")

    # Flags
    flags = [r["flag"] for r in conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member["id"],)
    ).fetchall()]
    if flags:
        parts.append(f"Flags: {', '.join(flags)}")

    # Performance snapshots
    snapshots = conn.execute(
        """SELECT date, metrics, score FROM performance_snapshots
           WHERE member_id = ? ORDER BY date DESC LIMIT 10""",
        (member["id"],),
    ).fetchall()
    if snapshots:
        parts.append("\nPerformance snapshots:")
        for s in snapshots:
            metrics = json.loads(s["metrics"]) if s["metrics"] else {}
            # Surface multiplication (reviews given / co-authored) — it is collected but was
            # previously dropped here, so the analysis never saw the work that lands in
            # others' output. Per ANALYSIS_STANDARD.md §1.B this is a decisive dimension.
            parts.append(
                f"  {s['date']}: score={s['score']}, "
                f"commits={metrics.get('commits_count', 0)}, "
                f"prs_merged={metrics.get('prs_merged', 0)}, "
                f"prs_opened={metrics.get('prs_opened', 0)}, "
                f"reviews_given={metrics.get('reviews_given', 0)}, "
                f"coauthored={metrics.get('coauthored_commits', 0)}, "
                f"issues_done={metrics.get('issues_completed', 0)}, "
                f"issues_wip={metrics.get('issues_in_progress', 0)}, "
                # Flow & quality (§1.C/§1.D). reopened = REPEATED FAILURES (heaviest).
                f"reopened={metrics.get('reopened', 0)}, "
                f"bug_share={metrics.get('bug_share', 0)}, "
                f"stale_hours={metrics.get('stale_hours', 0)}, "
                f"rotting_prs={metrics.get('rotting_prs', 0)}, "
                f"pr_cycle_p85h={metrics.get('pr_cycle_p85_hours', 0)}"
            )

    # Meetings
    meetings = conn.execute(
        """SELECT date, summary, sentiment_score FROM meetings
           WHERE member_id = ? ORDER BY date DESC LIMIT 5""",
        (member["id"],),
    ).fetchall()
    if meetings:
        parts.append("\nRecent meetings:")
        for mtg in meetings:
            parts.append(f"  {mtg['date']} (sentiment: {mtg['sentiment_score'] or '?'})")
            if mtg["summary"]:
                parts.append(f"    {mtg['summary'][:300]}")

    # Open items
    items = conn.execute(
        """SELECT mi.kind, mi.content FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'
           ORDER BY mi.created_at DESC LIMIT 10""",
        (member["id"],),
    ).fetchall()
    if items:
        parts.append("\nOpen action items:")
        for item in items:
            parts.append(f"  - [{item['kind']}] {item['content']}")

    # Goals
    goals = conn.execute(
        "SELECT type, title, current_value, target_value, status FROM goals WHERE member_id = ? ORDER BY id",
        (member["id"],),
    ).fetchall()
    if goals:
        parts.append("\nGoals:")
        for g in goals:
            progress = ""
            if g["target_value"]:
                progress = f" ({g['current_value'] or 0}/{g['target_value']})"
            parts.append(f"  - [{g['type']}] {g['title']}{progress} [{g['status']}]")

    # Coaching entries
    entries = conn.execute(
        "SELECT kind, content, created_at FROM coaching_entries WHERE member_id = ? ORDER BY created_at DESC LIMIT 5",
        (member["id"],),
    ).fetchall()
    if entries:
        parts.append("\nCoaching history:")
        for e in entries:
            parts.append(f"  [{e['kind']}] {e['created_at']}: {e['content'][:200]}")

    return "\n".join(parts)


# ---- Coach: Outliers (ANALYSIS_STANDARD.md §0.5 — Mirror, not Frame) ----
#
# This command surfaces cohort-relative ANOMALIES-TO-INVESTIGATE. It deliberately does
# NOT produce a ranked / positional "bottom-N" list (forbidden by §0.5). Every flag ships
# with candidate explanations — including the exonerating §1.D controls — and a pointer to
# the investigation that must precede any consequential action (§8).

# Compiled once at import (not per call). Roman-numeral product-engineer levels (PE II).
_ROMAN_RE = re.compile(r"\b([ivx]{1,4})\b", re.IGNORECASE)
_LADDER_BANDS = ("principal", "staff", "senior", "junior", "intern", "lead")


def _parse_level(title: Optional[str]) -> str:
    """Best-effort ladder-band extraction from a free-text title.

    Returns a normalized band string for cohorting, or 'unknown'. Unknown level means
    the member is compared only within tenure/criticality — never silently mis-banded.
    """
    if not title:
        return "unknown"
    t = title.lower()
    band = []
    for kw in _LADDER_BANDS:
        if kw in t:
            band.append(kw)
            break
    m = _ROMAN_RE.search(t)
    if m and ("engineer" in t or "pe" in t):
        band.append(m.group(1))
    return "-".join(band) if band else "unknown"


def _member_criticality(conn: sqlite3.Connection, member_id: int) -> Optional[str]:
    """Read an explicit 'criticality:<class>' member flag if present.

    Returns the class (critical/high/standard/low) or None. None is honest 'unknown'
    per §0.4 — the §1.D blast-radius control then degrades to a caveat rather than a
    fabricated value.
    """
    rows = conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member_id,)
    ).fetchall()
    for r in rows:
        flag = (r["flag"] or "").lower()
        if flag.startswith("criticality:"):
            return flag.split(":", 1)[1].strip() or None
    return None


def _aggregate_member_metrics(conn: sqlite3.Connection, member_id: int, days: int) -> dict:
    """Aggregate a member's snapshots over the window into one metrics dict.

    Sums event-style signals (reopened, merges, commits, reviews); averages rate/latency
    signals (stale_hours, cycle p85, bug_share) over snapshots that carry them.
    """
    from datetime import datetime, timedelta

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT metrics FROM performance_snapshots
           WHERE member_id = ? AND date >= ?""",
        (member_id, since),
    ).fetchall()

    agg = {
        "reopened": 0, "prs_merged": 0, "commits": 0, "reviews_given": 0,
        "coauthored_commits": 0, "issues_completed": 0,
    }
    cycle_vals: list[float] = []
    stale_vals: list[float] = []
    bug_vals: list[float] = []
    for row in rows:
        m = json.loads(row["metrics"]) if row["metrics"] else {}
        agg["reopened"] += m.get("reopened", 0) or 0
        agg["prs_merged"] += m.get("prs_merged", 0) or 0
        agg["commits"] += m.get("commits_count", 0) or 0
        agg["reviews_given"] += m.get("reviews_given", 0) or 0
        agg["coauthored_commits"] += m.get("coauthored_commits", 0) or 0
        agg["issues_completed"] += m.get("issues_completed", 0) or 0
        if m.get("pr_cycle_p85_hours"):
            cycle_vals.append(float(m["pr_cycle_p85_hours"]))
        if m.get("stale_hours"):
            stale_vals.append(float(m["stale_hours"]))
        if m.get("bug_share"):
            bug_vals.append(float(m["bug_share"]))

    weeks = max(days / 7.0, 1e-9)
    agg["merges_per_week"] = agg["prs_merged"] / weeks
    agg["pr_cycle_p85_hours"] = (sum(cycle_vals) / len(cycle_vals)) if cycle_vals else 0.0
    agg["stale_hours"] = (sum(stale_vals) / len(stale_vals)) if stale_vals else 0.0
    agg["bug_share"] = (sum(bug_vals) / len(bug_vals)) if bug_vals else 0.0
    agg["snapshots"] = len(rows)
    return agg


# Dimension specs per ANALYSIS_STANDARD §1/§2. repeated_failures is the heaviest-weighted
# signal; catchable_errors is intentionally ABSENT (not yet collected) and is reported as a
# data gap by the command rather than proxied (§0.4).
def _dimension_specs():
    from ascend.analysis.outliers import DimensionSpec
    return [
        DimensionSpec("repeated_failures", "reopened", "high_bad", threshold_sd=2.0),
        DimensionSpec("languishing_prs", "stale_hours", "high_bad", threshold_sd=2.0),
        DimensionSpec("slow_cycle", "pr_cycle_p85_hours", "high_bad", threshold_sd=2.0),
        DimensionSpec("low_output", "merges_per_week", "low_bad", threshold_sd=2.0),
        DimensionSpec("bug_heavy", "bug_share", "high_bad", threshold_sd=2.0),
    ]


def cmd_coach_outliers(args: argparse.Namespace) -> None:
    """Surface cohort-relative anomalies-to-investigate (§0.5). NOT a ranking."""
    from ascend.analysis.cohorts import criticality_class  # noqa: F401 (future use)
    from ascend.analysis.outliers import detect_outliers
    from ascend.analysis import investigation as inv
    from ascend.integrations.github import first_commit_date, tenure_weeks

    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    days = getattr(args, "days", None) or 90
    config = load_config()

    inv.ensure_tables(conn)

    members = [dict(r) for r in conn.execute(
        "SELECT * FROM members WHERE status = 'active'"
    ).fetchall()]

    member_metrics: list[dict] = []
    data_gaps = {"tenure_unknown": 0, "criticality_unknown": 0}
    for m in members:
        agg = _aggregate_member_metrics(conn, m["id"], days)
        if agg["snapshots"] == 0:
            continue  # no data — cannot compare; excluded, not flagged (§0.4)
        tw = None
        try:
            fcd = first_commit_date(
                m.get("github") or "", str(config.repos_dir),
                email=m.get("email"), personal_email=m.get("personal_email"),
            )
            tw = tenure_weeks(fcd)
        except Exception:
            tw = None
        if tw is None:
            data_gaps["tenure_unknown"] += 1
        crit = _member_criticality(conn, m["id"])
        if crit is None:
            data_gaps["criticality_unknown"] += 1
        member_metrics.append({
            "member_id": m["id"],
            "name": m["name"],
            "level": _parse_level(m.get("title")),
            "tenure_weeks": tw,
            "criticality": crit,
            "novelty": 0.0,  # not yet collected — §1.D novelty control reads as inactive
            **{k: agg[k] for k in (
                "reopened", "stale_hours", "pr_cycle_p85_hours",
                "merges_per_week", "bug_share",
            )},
        })

    specs = _dimension_specs()
    flags = detect_outliers(member_metrics, specs)

    # Persist each flag as an open hypothesis (§8) so it can be investigated.
    period = f"last_{days}d"
    name_to_id = {mm["name"]: mm["member_id"] for mm in member_metrics}
    for f in flags:
        try:
            fid = inv.record_flag(
                conn,
                member_id=name_to_id.get(f["member"]),
                dimension=f["dimension"], period=period, cohort_key=f.get("cohort_key"),
                value=f.get("value"), cohort_median=f.get("cohort_median"),
                cohort_sd=f.get("cohort_sd"), z_score=f.get("z_score"),
                explanations=f.get("explanations"),
            )
            f["flag_id"] = fid
        except Exception:
            f["flag_id"] = None

    conn.close()
    log_operation("coach outliers", args={"days": days, "flags": len(flags)})

    result = {
        "period": period,
        "members_analyzed": len(member_metrics),
        "anomalies": flags,
        "data_gaps": data_gaps,
        "catchable_errors": "not collected — data gap per §0.4/§7; not proxied.",
        "note": "One optional lens: engineers >2 SD from their cohort norm, with context "
                "(incl. reasons the gap may be benign). Full picture: `report-analysis`.",
    }

    if json_mode:
        render_output(result, json_mode=True, copy=copy)
        return

    if not flags:
        render_output(
            f"# Cohort outliers — {period}\n\nNo engineers cross the 2 SD bar "
            f"({len(member_metrics)} analyzed) — not that everyone is 'fine'; this is just "
            f"one lens. For the full per-engineer picture, use `report-analysis`.", copy=copy
        )
        return

    parts = [f"# Cohort outliers — {period}"]
    parts.append(
        "An optional lens: engineers >2 SD from their level/tenure/criticality cohort on a "
        "dimension, each with context (including reasons the gap may be benign). For the full "
        "per-engineer picture, use `report-analysis`.\n"
    )
    parts.append(f"Members analyzed: {len(member_metrics)}  |  Flags: {len(flags)}")
    parts.append(
        f"Data gaps: tenure unknown for {data_gaps['tenure_unknown']}, "
        f"criticality unknown for {data_gaps['criticality_unknown']}. "
        "Catchable-errors dimension: NOT collected (not proxied, per §0.4).\n"
    )
    # Group by dimension; within, order is incidental (no positional meaning).
    by_dim: dict[str, list] = {}
    for f in flags:
        by_dim.setdefault(f["dimension"], []).append(f)
    # repeated_failures first only because it is the heaviest-weighted DIMENSION, not a rank.
    dim_order = ["repeated_failures", "bug_heavy", "languishing_prs", "slow_cycle", "low_output"]
    for dim in sorted(by_dim, key=lambda d: dim_order.index(d) if d in dim_order else 99):
        parts.append(f"\n## {dim} ({len(by_dim[dim])})")
        for f in by_dim[dim]:
            fid = f.get("flag_id")
            parts.append(
                f"\n**{f['member']}** — value {f['value']:.2f} vs cohort median "
                f"{f.get('cohort_median', 0):.2f} (z={f.get('z_score', 0):+.1f}, "
                f"{f.get('severity', 'watch')}; cohort `{f.get('cohort_key')}`, "
                f"n={f.get('cohort_n')}){f' — flag #{fid}' if fid else ''}"
            )
            for ex in f.get("explanations", []):
                tag = "EXONERATES" if ex.get("exonerating") else "concern"
                parts.append(f"  - [{tag}] {ex.get('label')}: {ex.get('rationale')}")
            if fid:
                parts.append(
                    f"  (optional — log what you find: "
                    f"`ascend coach-investigate {fid} --why ... --verdict ...`)"
                )
    render_output("\n".join(parts), copy=copy)


def cmd_coach_investigate(args: argparse.Namespace) -> None:
    """Record an investigation against a flag (§8 — the Mirror's teeth)."""
    from ascend.analysis import investigation as inv

    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    inv.ensure_tables(conn)

    valid = (getattr(args, "valid", "yes") or "yes").lower() in ("yes", "y", "true", "1")
    try:
        iid = inv.record_investigation(
            conn,
            flag_id=args.flag_id,
            why=args.why,
            comparison_valid=valid,
            what_would_change=getattr(args, "what_would_change", None),
            verdict=args.verdict,
            investigated_by=getattr(args, "by", None) or "manager",
        )
    except ValueError as e:
        conn.close()
        render_output({"error": str(e)}, json_mode=True)
        return

    conn.close()
    log_operation("coach investigate", args={"flag_id": args.flag_id, "verdict": args.verdict})
    result = {"investigation_id": iid, "flag_id": args.flag_id, "verdict": args.verdict}
    if json_mode:
        render_output(result, json_mode=True)
    else:
        render_output(
            f"Investigation #{iid} recorded for flag #{args.flag_id} "
            f"(verdict: {args.verdict}). Flag status -> investigated."
        )


def cmd_coach_audit(args: argparse.Namespace) -> None:
    """Misfire audit (§9) — keep the metric honest; demote dimensions >30% misfire."""
    from ascend.analysis import investigation as inv

    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    inv.ensure_tables(conn)

    audit = inv.misfire_audit(conn, since=getattr(args, "since", None))
    conn.close()
    log_operation("coach audit")

    result = {"misfire_audit": audit}
    if json_mode:
        render_output(result, json_mode=True, copy=copy)
        return

    parts = ["# Analysis self-accuracy audit (§9)"]
    parts.append(
        "How often did flagged anomalies turn out to be noise (per logged investigations)? "
        "This audits the analysis itself — a dimension that misfires too often isn't earning "
        f"its keep. Threshold: misfire rate > {audit.get('threshold', 0.30)}.\n"
    )
    per_dim = audit.get("dimensions", audit) if isinstance(audit, dict) else {}
    if isinstance(per_dim, dict) and per_dim:
        for dim, stats in per_dim.items():
            if not isinstance(stats, dict):
                continue
            rec = stats.get("recommendation", "")
            parts.append(
                f"- **{dim}**: {stats.get('misfires', 0)}/{stats.get('investigated', 0)} "
                f"misfires (rate {stats.get('misfire_rate', 0):.0%}) {('-> ' + rec) if rec else ''}"
            )
    else:
        parts.append("_No investigated flags yet — nothing to audit._")
    render_output("\n".join(parts), copy=copy)


# ---- Analysis for all (ANALYSIS_STANDARD.md §0.5) ----
#
# The primary surface: comprehensive, honest analysis for EVERY engineer — output,
# multiplication, flow, quality, and the industry frameworks — each shown both in absolute
# terms and relative to the member's level/tenure/criticality cohort. It presents the full
# multi-dimensional picture and is agnostic about how the reader uses it. The analytical
# controls (cohort normalization, surfacing illegible/multiplication work, data-gap honesty,
# CFR-demotion) are here to keep the analysis TRUE, not to police usage.

# Dimensions shown per engineer with cohort-relative standing. (name, metric_key, lower_is_better)
_ANALYSIS_DIMENSIONS = [
    ("merges_per_week", "merges_per_week", False),
    ("reviews_given", "reviews_given", False),
    ("reopened", "reopened", True),
    ("bug_share", "bug_share", True),
    ("stale_hours", "stale_hours", True),
    ("pr_cycle_p85_hours", "pr_cycle_p85_hours", True),
]


def _fw_metrics(agg: dict, days: int) -> dict:
    """Map an aggregate into the metrics dict the frameworks module expects."""
    return {
        "commits_count": agg.get("commits", 0),
        "prs_merged": agg.get("prs_merged", 0),
        "issues_completed": agg.get("issues_completed", 0),
        "reviews_given": agg.get("reviews_given", 0),
        "coauthored_commits": agg.get("coauthored_commits", 0),
        "reopened": agg.get("reopened", 0),
        "bug_share": agg.get("bug_share", 0.0),
        "stale_hours": agg.get("stale_hours", 0.0),
        "pr_cycle_p85_hours": agg.get("pr_cycle_p85_hours", 0.0),
        "period_days": days,
    }


def cmd_report_analysis(args: argparse.Namespace) -> None:
    """Comprehensive analysis for every engineer, with cohort-relative standing (§0.5)."""
    from ascend.integrations.frameworks import frameworks_report
    from ascend.integrations.github import first_commit_date, tenure_weeks
    from ascend.analysis.normalization import cohort_stats, zscore
    from ascend.analysis.cohorts import cohort_key

    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    days = getattr(args, "days", None) or 90
    sort_key = getattr(args, "sort", None) or "name"
    only_member = getattr(args, "member", None)
    only_team = getattr(args, "team", None)
    config = load_config()

    query = "SELECT * FROM members WHERE status = 'active'"
    members = [dict(r) for r in conn.execute(query).fetchall()]
    if only_member:
        ml = only_member.lower()
        members = [m for m in members if ml in (m.get("name", "") or "").lower()
                   or ml == str(m.get("id")) or ml == (m.get("github") or "").lower()]
    if only_team and "team_id" in (members[0] if members else {}):
        members = [m for m in members if str(m.get("team_id")) == str(only_team)]

    profiles = []
    for m in members:
        agg = _aggregate_member_metrics(conn, m["id"], days)
        tw = None
        try:
            fcd = first_commit_date(
                m.get("github") or "", str(config.repos_dir),
                email=m.get("email"), personal_email=m.get("personal_email"),
            )
            tw = tenure_weeks(fcd)
        except Exception:
            tw = None
        crit = _member_criticality(conn, m["id"])
        level = _parse_level(m.get("title"))
        profiles.append({
            "member": m["name"],
            "level": level,
            "title": m.get("title"),
            "tenure_weeks": tw,
            "criticality": crit,
            "has_data": agg["snapshots"] > 0,
            "cohort": cohort_key(level, tw, crit),
            "metrics": {
                "merges_per_week": agg.get("merges_per_week", 0.0),
                "reviews_given": agg.get("reviews_given", 0),
                "reopened": agg.get("reopened", 0),
                "bug_share": agg.get("bug_share", 0.0),
                "stale_hours": agg.get("stale_hours", 0.0),
                "pr_cycle_p85_hours": agg.get("pr_cycle_p85_hours", 0.0),
                "commits": agg.get("commits", 0),
                "prs_merged": agg.get("prs_merged", 0),
            },
            "frameworks": frameworks_report(_fw_metrics(agg, days), period_days=days),
        })

    # Cohort-relative standing: for each dimension, z-score within the member's cohort.
    with_data = [p for p in profiles if p["has_data"]]
    by_cohort: dict[str, list] = {}
    for p in with_data:
        by_cohort.setdefault(p["cohort"], []).append(p)
    for _, group in by_cohort.items():
        for dim, key, lower_bad in _ANALYSIS_DIMENSIONS:
            stats = cohort_stats([g["metrics"].get(key, 0.0) for g in group])
            for g in group:
                z = zscore(g["metrics"].get(key, 0.0), stats)
                g.setdefault("standing", {})[dim] = round(z, 2)

    # Sorting is a convenience for the reader; it carries no verdict.
    def _sort_val(p):
        if sort_key in ("name",):
            return (p["member"] or "").lower()
        if sort_key in p["metrics"]:
            return -float(p["metrics"][sort_key])
        return (p["member"] or "").lower()
    profiles.sort(key=_sort_val)

    conn.close()
    log_operation("report analysis", args={"days": days, "members": len(profiles)})

    result = {
        "period": f"last_{days}d",
        "engineers": profiles,
        "note": "Comprehensive analysis for every engineer. Metrics shown absolute and "
                "cohort-relative (z within level/tenure/criticality). catchable-errors is "
                "not collected (data gap, not proxied).",
    }
    if json_mode:
        render_output(result, json_mode=True, copy=copy)
        return

    parts = [f"# Engineering analysis — every engineer · last {days}d (sorted by {sort_key})"]
    parts.append(
        "Per-engineer, all dimensions, absolute + cohort-relative (z within "
        "level/tenure/criticality). `*`=|z|>2 vs cohort. catchable-errors: not collected.\n"
    )
    header = (f"{'Engineer':<22}{'Level':<10}{'Ten':>4}{'Mrg/wk':>7}{'Rev':>5}"
              f"{'Reopen':>7}{'Bug%':>6}{'Stale':>7}{'Cyc85':>7}")
    parts.append(header)
    parts.append("-" * len(header))
    for p in profiles:
        if not p["has_data"]:
            parts.append(f"{p['member'][:21]:<22}{p['level'][:9]:<10}  — no snapshot data in window")
            continue
        mk = p["metrics"]
        st = p.get("standing", {})

        def mark(dim, val, fmt):
            s = "*" if abs(st.get(dim, 0)) > 2 else " "
            return f"{fmt.format(val)}{s}"
        tw = f"{p['tenure_weeks']:.0f}" if p["tenure_weeks"] is not None else "?"
        parts.append(
            f"{p['member'][:21]:<22}{p['level'][:9]:<10}{tw:>4}"
            f"{mark('merges_per_week', mk['merges_per_week'], '{:.1f}'):>7}"
            f"{mark('reviews_given', mk['reviews_given'], '{:.0f}'):>5}"
            f"{mark('reopened', mk['reopened'], '{:.0f}'):>7}"
            f"{mark('bug_share', mk['bug_share']*100, '{:.0f}'):>6}"
            f"{mark('stale_hours', mk['stale_hours'], '{:.0f}'):>7}"
            f"{mark('pr_cycle_p85_hours', mk['pr_cycle_p85_hours'], '{:.0f}'):>7}"
        )
    parts.append(
        f"\n{len(with_data)}/{len(profiles)} engineers with data. "
        "DORA/SPACE/DX Core 4 per engineer available via --json. "
        "Read it however you like — this is analysis, not a verdict."
    )
    render_output("\n".join(parts), copy=copy)
