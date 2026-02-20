"""Slack fetcher — channel activity, signal detection, notable messages.

Ported from daily-report, adapted for Ascend.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

_SIGNAL_PATTERNS = [
    re.compile(r"\bbug\b", re.IGNORECASE),
    re.compile(r"\bblocker\b", re.IGNORECASE),
    re.compile(r"\bblocked\b", re.IGNORECASE),
    re.compile(r"\bbroken\b", re.IGNORECASE),
    re.compile(r"\bregression\b", re.IGNORECASE),
    re.compile(r"\bincident\b", re.IGNORECASE),
    re.compile(r"\boutage\b", re.IGNORECASE),
    re.compile(r"\bdowntime\b", re.IGNORECASE),
    re.compile(r"\bfailing\b", re.IGNORECASE),
    re.compile(r"\bfailed\b", re.IGNORECASE),
    re.compile(r"\brollback\b", re.IGNORECASE),
    re.compile(r"\brevert\b", re.IGNORECASE),
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\b500\b"),
    re.compile(r"\btimeout\b", re.IGNORECASE),
    re.compile(r"\bcrash\b", re.IGNORECASE),
    re.compile(r"\bhotfix\b", re.IGNORECASE),
    re.compile(r"\bsev[- ]?[012]\b", re.IGNORECASE),
    re.compile(r"\burgent\b", re.IGNORECASE),
    re.compile(r"\bcritical\b", re.IGNORECASE),
    re.compile(r"\bdata.?loss\b", re.IGNORECASE),
    re.compile(r"\bbreaking\b", re.IGNORECASE),
    re.compile(r"\bworkaround\b", re.IGNORECASE),
    re.compile(r"\bescalat", re.IGNORECASE),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
    re.compile(r"\bslipping\b", re.IGNORECASE),
    re.compile(r"\bdelayed?\b", re.IGNORECASE),
    re.compile(r"\brisk\b", re.IGNORECASE),
    re.compile(r"\bconcern\b", re.IGNORECASE),
]


def _api(
    token: str, method: str, params: dict[str, Any] | None = None,
    *, max_retries: int = 2, timeout: int = 15,
) -> dict[str, Any] | None:
    """Call a Slack Web API method with retry."""
    url = f"https://slack.com/api/{method}"
    if params:
        parts = [f"{k}={quote(str(v), safe=',')}" for k, v in params.items()]
        url = f"{url}?{'&'.join(parts)}"

    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    })

    for attempt in range(max_retries + 1):
        try:
            response = urlopen(req, timeout=timeout)
            return json.loads(response.read().decode())
        except HTTPError as e:
            if e.code == 429:
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


def resolve_channel_id(token: str, channel_name: str) -> str | None:
    """Resolve a channel name to its ID."""
    clean = channel_name.lstrip("#")
    cursor = None

    while True:
        params: dict[str, Any] = {
            "types": "public_channel,private_channel",
            "limit": 200, "exclude_archived": "true",
        }
        if cursor:
            params["cursor"] = cursor
        result = _api(token, "users.conversations", params)
        if result is None or not result.get("ok"):
            return None
        for ch in result.get("channels", []):
            if ch.get("name") == clean:
                return ch["id"]
        next_cursor = result.get("response_metadata", {}).get("next_cursor", "")
        if next_cursor:
            cursor = next_cursor
        else:
            return None


def fetch_channel_activity(
    token: str, channel_name: str, since: datetime
) -> dict[str, Any]:
    """Fetch Slack activity for a channel."""
    if not token:
        return {"error": "SLACK_BOT_TOKEN not set", "channel": channel_name,
                "message_count": 0, "active_threads": 0, "notable": []}
    if not channel_name:
        return {"error": "no channel configured", "channel": "",
                "message_count": 0, "active_threads": 0, "notable": []}

    channel_id = resolve_channel_id(token, channel_name)
    if not channel_id:
        return {"error": f"channel not found: #{channel_name}", "channel": channel_name,
                "message_count": 0, "active_threads": 0, "notable": []}

    oldest = str(since.timestamp())
    all_messages: list[dict[str, Any]] = []
    cursor = None

    while True:
        params: dict[str, Any] = {
            "channel": channel_id, "oldest": oldest, "limit": 200, "inclusive": "true",
        }
        if cursor:
            params["cursor"] = cursor
        result = _api(token, "conversations.history", params)
        if result is None or not result.get("ok"):
            error = result.get("error", "unknown") if result else "no response"
            return {"error": error, "channel": channel_name,
                    "message_count": len(all_messages), "active_threads": 0, "notable": []}
        all_messages.extend(result.get("messages", []))
        next_cursor = result.get("response_metadata", {}).get("next_cursor", "")
        if next_cursor:
            cursor = next_cursor
        else:
            break

    # Filter bot/system messages
    real = [m for m in all_messages
            if m.get("subtype") not in ("channel_join", "channel_leave", "bot_message")]
    active_threads = sum(1 for m in real if m.get("reply_count", 0) > 2)
    notable = _extract_notable(real)

    return {
        "error": None, "channel": channel_name,
        "message_count": len(real), "active_threads": active_threads,
        "notable": notable,
    }


def detect_signals(text: str) -> list[str]:
    """Return signal keywords found in text."""
    return [
        pat.pattern.replace(r"\b", "").replace("\\b", "")
        for pat in _SIGNAL_PATTERNS if pat.search(text)
    ]


def _extract_notable(messages: list[dict[str, Any]], limit: int = 5) -> list[dict]:
    """Score and rank notable messages by signal density."""
    scored: list[tuple[int, dict]] = []
    for msg in messages:
        text = msg.get("text", "")
        if not text or len(text) < 10:
            continue
        signals = detect_signals(text)
        if not signals:
            continue
        score = len(signals)
        if msg.get("reply_count", 0) > 0:
            score += 1
        if any(r.search(text) for r in _SIGNAL_PATTERNS[:6]):
            score += 2
        preview = text.split("\n")[0][:120]
        if len(text.split("\n")[0]) > 120:
            preview += "..."
        scored.append((score, {
            "text": preview, "signals": signals[:4],
            "user": msg.get("user", ""),
            "reply_count": msg.get("reply_count", 0),
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]
