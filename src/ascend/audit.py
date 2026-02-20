"""Append-only JSONL audit log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ascend.config import HISTORY_DIR


def _audit_path() -> Path:
    return HISTORY_DIR / "audit.jsonl"


def log_operation(
    command: str,
    *,
    args: Optional[dict] = None,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Append an operation to the audit log."""
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command,
    }
    if args:
        entry["args"] = args
    if result:
        entry["result"] = result
    if error:
        entry["error"] = error

    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_audit(last_n: int = 50) -> list[dict[str, Any]]:
    """Read recent audit entries."""
    path = _audit_path()
    if not path.exists():
        return []

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    return entries[-last_n:]
