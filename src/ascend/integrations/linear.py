"""Linear fetcher — GraphQL via urllib with pagination.

Ported from daily-report, adapted for member-centric queries.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_GRAPHQL_URL = "https://api.linear.app/graphql"

_RECENT_ISSUES_QUERY = """
query($teamId: ID!, $after: DateTimeOrDuration!, $first: Int!, $cursor: String) {
  issues(
    filter: {
      team: { id: { eq: $teamId } }
      updatedAt: { gte: $after }
    }
    first: $first
    after: $cursor
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      state { name }
      priority
      assignee { name displayName }
      labels { nodes { name } }
      updatedAt
      url
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_FULL_ISSUES_QUERY = """
query($teamId: ID!, $first: Int!, $cursor: String) {
  issues(
    filter: {
      team: { id: { eq: $teamId } }
    }
    first: $first
    after: $cursor
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      state { name }
      priority
      assignee { name displayName }
      labels { nodes { name } }
      estimate
      dueDate
      project { name }
      completedAt
      createdAt
      updatedAt
      url
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def _graphql(
    api_key: str, query: str, variables: dict[str, Any] | None = None,
    *, max_retries: int = 2, timeout: int = 15,
) -> dict[str, Any] | None:
    """Execute a GraphQL query against the Linear API."""
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()

    for attempt in range(max_retries + 1):
        req = Request(
            _GRAPHQL_URL, data=payload,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urlopen(req, timeout=timeout)
            body = json.loads(response.read().decode())

            if "errors" in body:
                err_msg = str(body["errors"][:1])
                is_transient = any(
                    s in err_msg.lower()
                    for s in ("ratelimit", "rate_limit", "too many", "timeout")
                )
                if is_transient and attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None
            return body.get("data")

        except HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                retry_after = int(e.headers.get("Retry-After", 2 ** attempt))
                time.sleep(retry_after)
                continue
            return None
        except (URLError, json.JSONDecodeError, OSError):
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return None
    return None


def fetch_recent_issues(
    api_key: str, team_id: str, since: datetime
) -> list[dict[str, Any]]:
    """Fetch issues updated since a timestamp with cursor pagination."""
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    all_issues: list[dict[str, Any]] = []
    cursor = None

    while True:
        variables: dict[str, Any] = {"teamId": team_id, "after": since_str, "first": 50}
        if cursor:
            variables["cursor"] = cursor
        result = _graphql(api_key, _RECENT_ISSUES_QUERY, variables)
        if result is None:
            break
        issues_data = result.get("issues", {})
        all_issues.extend(issues_data.get("nodes", []))
        page_info = issues_data.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            cursor = page_info["endCursor"]
        else:
            break
    return all_issues


def fetch_all_issues(api_key: str, team_id: str) -> list[dict[str, Any]]:
    """Fetch all team issues (no date filter, expanded fields)."""
    all_issues: list[dict[str, Any]] = []
    cursor = None

    while True:
        variables: dict[str, Any] = {"teamId": team_id, "first": 50}
        if cursor:
            variables["cursor"] = cursor
        result = _graphql(api_key, _FULL_ISSUES_QUERY, variables)
        if result is None:
            break
        issues_data = result.get("issues", {})
        all_issues.extend(issues_data.get("nodes", []))
        page_info = issues_data.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            cursor = page_info["endCursor"]
        else:
            break
    return all_issues


def fetch_member_issues(
    api_key: str, team_id: str, member_name: str, since: datetime
) -> list[dict[str, Any]]:
    """Fetch issues assigned to a specific member."""
    all_issues = fetch_recent_issues(api_key, team_id, since)
    member_lower = member_name.lower()
    return [
        i for i in all_issues
        if _assignee_matches(i, member_lower)
    ]


def match_issues(
    issues: list[dict[str, Any]],
    labels: list[str],
    assignees: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter issues by label, assignee, or title keyword match."""
    matched = []
    for issue in issues:
        issue_labels = [
            n.get("name", "").lower()
            for n in issue.get("labels", {}).get("nodes", [])
        ]
        # Label match (strongest)
        if any(l.lower() in issue_labels for l in labels):
            matched.append(issue)
            continue

        assignee = issue.get("assignee") or {}
        display = (assignee.get("displayName") or "").lower()
        name = (assignee.get("name") or "").lower()
        has_assignee = bool(display or name)

        # Assignee match
        is_our_assignee = False
        if assignees:
            for a in assignees:
                if a.lower() in (display, name):
                    is_our_assignee = True
                    break
        if is_our_assignee:
            matched.append(issue)
            continue

        # Title keyword (weak, gated)
        if has_assignee and assignees and not is_our_assignee:
            continue
        title = issue.get("title", "").lower()
        if any(l.lower() in title for l in labels):
            matched.append(issue)

    return matched


def get_effective_team_ids(config: Any) -> list[str]:
    """Merge linear_team_id and linear_team_ids into a single list."""
    ids = list(getattr(config, "linear_team_ids", []) or [])
    singular = getattr(config, "linear_team_id", "") or ""
    if singular and singular not in ids:
        ids.insert(0, singular)
    return ids


_STALE_PRIORITY_QUERY = """
query($teamId: ID!, $first: Int!, $cursor: String) {
  issues(
    filter: {
      team: { id: { eq: $teamId } }
      state: { type: { nin: ["completed", "canceled", "triage"] } }
      or: [
        { priority: { in: [1, 2] } }
        { labels: { name: { in: ["high-impact", "High Impact", "urgent", "Urgent"] } } }
      ]
    }
    first: $first
    after: $cursor
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      state { name type }
      priority
      assignee { name displayName }
      labels { nodes { name } }
      updatedAt
      createdAt
      url
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


_PRIORITY_NAMES = {0: "None", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}


def fetch_stale_priority_issues(
    api_key: str,
    team_ids: list[str],
    stale_hours: int = 48,
) -> list[dict[str, Any]]:
    """Fetch high-priority/urgent active issues that have gone stale.

    An issue is stale if updatedAt is older than stale_hours ago.
    """
    from datetime import timedelta as _td, timezone

    cutoff = datetime.now(timezone.utc) - _td(hours=stale_hours)
    all_stale: list[dict[str, Any]] = []

    for team_id in team_ids:
        cursor = None
        while True:
            variables: dict[str, Any] = {"teamId": team_id, "first": 50}
            if cursor:
                variables["cursor"] = cursor
            result = _graphql(api_key, _STALE_PRIORITY_QUERY, variables)
            if result is None:
                break
            issues_data = result.get("issues", {})
            for issue in issues_data.get("nodes", []):
                updated = issue.get("updatedAt", "")
                if not updated:
                    continue
                try:
                    updated_dt = datetime.fromisoformat(
                        updated.replace("Z", "+00:00")
                    )
                    if updated_dt < cutoff:
                        hours_stale = (
                            datetime.now(timezone.utc) - updated_dt
                        ).total_seconds() / 3600
                        assignee = issue.get("assignee") or {}
                        all_stale.append({
                            "identifier": issue.get("identifier", ""),
                            "title": issue.get("title", ""),
                            "priority": issue.get("priority", 0),
                            "priority_name": _PRIORITY_NAMES.get(
                                issue.get("priority", 0), "Unknown"
                            ),
                            "state": (issue.get("state") or {}).get("name", ""),
                            "assignee_name": (
                                assignee.get("displayName")
                                or assignee.get("name")
                                or None
                            ),
                            "labels": [
                                n.get("name", "")
                                for n in issue.get("labels", {}).get("nodes", [])
                            ],
                            "updated_at": updated,
                            "hours_stale": round(hours_stale, 1),
                            "url": issue.get("url", ""),
                        })
                except (ValueError, TypeError):
                    continue
            page_info = issues_data.get("pageInfo", {})
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

    # Deduplicate by identifier (same issue may appear from multiple teams)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in all_stale:
        ident = item["identifier"]
        if ident not in seen:
            seen.add(ident)
            deduped.append(item)

    # Sort by staleness descending
    deduped.sort(key=lambda x: x["hours_stale"], reverse=True)
    return deduped


def _assignee_matches(issue: dict[str, Any], name_lower: str) -> bool:
    """Check if issue assignee matches a member name (case-insensitive)."""
    assignee = issue.get("assignee") or {}
    display = (assignee.get("displayName") or "").lower()
    name = (assignee.get("name") or "").lower()
    return name_lower in (display, name) or name_lower in display or name_lower in name
