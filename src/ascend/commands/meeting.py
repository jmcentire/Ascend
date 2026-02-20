"""Meeting commands — ingest, list, show, search, items, item-close, prep."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ascend.audit import log_operation
from ascend.config import DB_PATH, TRANSCRIPTS_DIR, load_config
from ascend.db import get_connection
from ascend.output import format_table, render_output
from ascend.transcript import (
    ParsedTranscript,
    TranscriptError,
    check_duplicate,
    parse_transcript,
    resolve_member,
    scan_directory,
)


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def _resolve_member_arg(member: str, conn: sqlite3.Connection) -> Optional[int]:
    """Resolve a --member argument to a member_id."""
    if member.isdigit():
        return int(member)
    row = conn.execute(
        "SELECT id FROM members WHERE LOWER(name) = LOWER(?) OR github = ?",
        (member, member),
    ).fetchone()
    return row["id"] if row else None


def cmd_meeting_ingest(args: argparse.Namespace) -> None:
    """Ingest transcript file(s)."""
    path = Path(args.file)
    if not path.exists():
        render_output(f"Error: path '{path}' not found")
        return

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = scan_directory(path)
    else:
        render_output(f"Error: '{path}' is not a file or directory")
        return

    dry_run = getattr(args, "dry_run", False)
    no_llm = getattr(args, "no_llm", False)
    json_mode = getattr(args, "json", False)
    explicit_member = getattr(args, "member", None)

    if dry_run:
        results = [{"file": f.name, "action": "would ingest"} for f in files]
        if json_mode:
            render_output(results, json_mode=True)
        else:
            for r in results:
                render_output(f"  [dry-run] {r['file']}")
            render_output(f"\n{len(files)} file(s) would be ingested.")
        return

    conn = _get_conn()
    cfg = load_config()
    ingested = []
    skipped = []

    # Get LLM client if needed
    llm_client = None
    if not no_llm:
        from ascend.summarizer import get_client
        llm_client = get_client(cfg)

    for file_path in files:
        try:
            parsed = parse_transcript(file_path)
        except TranscriptError as e:
            skipped.append({"file": file_path.name, "reason": str(e)})
            continue

        # Resolve member
        member_id = None
        if explicit_member:
            member_id = _resolve_member_arg(explicit_member, conn)
        elif parsed.turns:
            speakers = list(dict.fromkeys(t.speaker for t in parsed.turns))
            member_id = resolve_member(speakers, cfg.manager_name, conn)

        # Date fallback to file mtime
        date = parsed.date
        if not date:
            mtime = file_path.stat().st_mtime
            date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

        # Duplicate check
        if check_duplicate(parsed.source_file, member_id, date, conn):
            skipped.append({"file": file_path.name, "reason": "already ingested"})
            continue

        # LLM processing
        summary = None
        sentiment = None
        items = []
        if llm_client and not no_llm:
            from ascend.summarizer import summarize_transcript, extract_items, analyze_sentiment
            summary = summarize_transcript(parsed.raw_text, cfg, llm_client)
            items = extract_items(parsed.raw_text, cfg, llm_client)
            sentiment = analyze_sentiment(parsed.raw_text, cfg, llm_client)

        # Store meeting
        conn.execute(
            """INSERT INTO meetings (member_id, date, source, source_file, raw_text, summary, sentiment_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (member_id, date, "transcript", parsed.source_file, parsed.raw_text, summary, sentiment),
        )
        meeting_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Store items
        for item in items:
            conn.execute(
                "INSERT INTO meeting_items (meeting_id, kind, content, status) VALUES (?, ?, ?, 'open')",
                (meeting_id, item["kind"], item["content"]),
            )

        conn.commit()

        # Copy transcript to ~/.ascend/transcripts/
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        dest = TRANSCRIPTS_DIR / parsed.source_file
        if not dest.exists():
            shutil.copy2(file_path, dest)

        ingested.append({
            "file": file_path.name,
            "meeting_id": meeting_id,
            "member_id": member_id,
            "date": date,
            "summary": summary[:80] if summary else None,
            "items": len(items),
        })

    conn.close()
    log_operation("meeting ingest", args={"ingested": len(ingested), "skipped": len(skipped)})

    if json_mode:
        render_output({"ingested": ingested, "skipped": skipped}, json_mode=True)
    else:
        for r in ingested:
            render_output(f"  Ingested: {r['file']} (id={r['meeting_id']}, {r['items']} items)")
        for s in skipped:
            render_output(f"  Skipped: {s['file']} ({s['reason']})")
        render_output(f"\n{len(ingested)} ingested, {len(skipped)} skipped.")


def cmd_meeting_list(args: argparse.Namespace) -> None:
    """List meetings."""
    conn = _get_conn()
    query = """SELECT m.id, m.date, m.source_file, m.summary, m.sentiment_score,
                      mem.name as member_name
               FROM meetings m
               LEFT JOIN members mem ON mem.id = m.member_id
               WHERE 1=1"""
    params: list = []

    if getattr(args, "member", None):
        mid = _resolve_member_arg(args.member, conn)
        if mid:
            query += " AND m.member_id = ?"
            params.append(mid)

    if getattr(args, "from_date", None):
        query += " AND m.date >= ?"
        params.append(args.from_date)

    if getattr(args, "to_date", None):
        query += " AND m.date <= ?"
        params.append(args.to_date)

    query += " ORDER BY m.date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    log_operation("meeting list", args={"count": len(rows)})

    if getattr(args, "json", False):
        render_output([dict(r) for r in rows], json_mode=True)
    else:
        if not rows:
            render_output("No meetings found.")
            return
        headers = ["ID", "Date", "Member", "Source", "Summary"]
        table_rows = [
            [str(r["id"]), r["date"], r["member_name"] or "", r["source_file"] or "",
             (r["summary"] or "")[:60]]
            for r in rows
        ]
        render_output(format_table(headers, table_rows))


def cmd_meeting_show(args: argparse.Namespace) -> None:
    """Show full meeting details."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT m.*, mem.name as member_name FROM meetings m
           LEFT JOIN members mem ON mem.id = m.member_id
           WHERE m.id = ?""",
        (args.id,),
    ).fetchone()

    if not row:
        conn.close()
        render_output(f"Error: meeting {args.id} not found")
        return

    items = conn.execute(
        "SELECT * FROM meeting_items WHERE meeting_id = ? ORDER BY kind, id",
        (args.id,),
    ).fetchall()
    conn.close()

    log_operation("meeting show", args={"id": args.id})

    if getattr(args, "json", False):
        data = dict(row)
        data["items"] = [dict(i) for i in items]
        render_output(data, json_mode=True)
    else:
        lines = [f"## Meeting {row['id']} — {row['date']}\n"]
        if row["member_name"]:
            lines.append(f"**Member:** {row['member_name']}")
        if row["summary"]:
            lines.append(f"\n### Summary\n\n{row['summary']}")
        if row["sentiment_score"] is not None:
            lines.append(f"\n**Sentiment:** {row['sentiment_score']:.2f}")
        if items:
            lines.append("\n### Items\n")
            for item in items:
                status = "x" if item["status"] == "closed" else " "
                lines.append(f"- [{status}] **{item['kind']}**: {item['content']}")
        if row["raw_text"]:
            lines.append(f"\n### Transcript\n\n{row['raw_text'][:2000]}")
            if len(row["raw_text"]) > 2000:
                lines.append(f"\n... ({len(row['raw_text'])} chars total)")
        render_output("\n".join(lines), copy=getattr(args, "copy", False))


def cmd_meeting_search(args: argparse.Namespace) -> None:
    """Full-text search across transcripts."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT m.id, m.date, m.member_id, mem.name as member_name,
                  snippet(meetings_fts, 0, '>>>', '<<<', '...', 40) as snippet
           FROM meetings_fts
           JOIN meetings m ON m.id = meetings_fts.rowid
           LEFT JOIN members mem ON mem.id = m.member_id
           WHERE meetings_fts MATCH ?
           ORDER BY rank
           LIMIT 20""",
        (args.query,),
    ).fetchall()
    conn.close()

    log_operation("meeting search", args={"query": args.query, "results": len(rows)})

    if getattr(args, "json", False):
        render_output([dict(r) for r in rows], json_mode=True)
    else:
        if not rows:
            render_output(f"No results for '{args.query}'")
            return
        for r in rows:
            render_output(f"**Meeting {r['id']}** ({r['date']}) — {r['member_name'] or 'unknown'}")
            render_output(f"  {r['snippet']}\n")


def cmd_meeting_items(args: argparse.Namespace) -> None:
    """List action items across meetings."""
    conn = _get_conn()
    status = getattr(args, "status", "open") or "open"
    query = """SELECT mi.id, mi.kind, mi.content, mi.status, mi.created_at,
                      m.date, mem.name as member_name
               FROM meeting_items mi
               JOIN meetings m ON m.id = mi.meeting_id
               LEFT JOIN members mem ON mem.id = m.member_id
               WHERE 1=1"""
    params: list = []

    if status != "all":
        query += " AND mi.status = ?"
        params.append(status)

    if getattr(args, "member", None):
        mid = _resolve_member_arg(args.member, conn)
        if mid:
            query += " AND m.member_id = ?"
            params.append(mid)

    query += " ORDER BY mi.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    log_operation("meeting items", args={"count": len(rows)})

    if getattr(args, "json", False):
        render_output([dict(r) for r in rows], json_mode=True)
    else:
        if not rows:
            render_output(f"No {status} items found.")
            return
        headers = ["ID", "Kind", "Content", "Status", "Member", "Date"]
        table_rows = [
            [str(r["id"]), r["kind"], r["content"][:60], r["status"],
             r["member_name"] or "", r["date"]]
            for r in rows
        ]
        render_output(format_table(headers, table_rows))


def cmd_meeting_item_close(args: argparse.Namespace) -> None:
    """Close an action item."""
    conn = _get_conn()
    row = conn.execute("SELECT id, content FROM meeting_items WHERE id = ?", (args.id,)).fetchone()
    if not row:
        conn.close()
        render_output(f"Error: item {args.id} not found")
        return

    conn.execute("UPDATE meeting_items SET status = 'closed' WHERE id = ?", (args.id,))
    conn.commit()
    conn.close()

    log_operation("meeting item-close", args={"id": args.id})

    if getattr(args, "json", False):
        render_output({"id": args.id, "status": "closed"}, json_mode=True)
    else:
        render_output(f"Closed item {args.id}: {row['content'][:60]}")


def cmd_meeting_prep(args: argparse.Namespace) -> None:
    """Generate AI conversation plan for next 1:1."""
    conn = _get_conn()
    member_id = _resolve_member_arg(args.member, conn)
    if not member_id:
        conn.close()
        render_output(f"Error: member '{args.member}' not found")
        return

    member_row = conn.execute("SELECT name FROM members WHERE id = ?", (member_id,)).fetchone()
    member_name = member_row["name"] if member_row else args.member

    # Fetch recent meetings (last 5)
    meetings = conn.execute(
        """SELECT m.date, m.summary FROM meetings m
           WHERE m.member_id = ? ORDER BY m.date DESC LIMIT 5""",
        (member_id,),
    ).fetchall()

    recent_meetings = []
    for m in meetings:
        items = conn.execute(
            """SELECT mi.kind, mi.content FROM meeting_items mi
               JOIN meetings mt ON mt.id = mi.meeting_id
               WHERE mt.member_id = ? AND mt.date = ?""",
            (member_id, m["date"]),
        ).fetchall()
        recent_meetings.append({
            "date": m["date"],
            "summary": m["summary"],
            "items": [{"kind": i["kind"], "content": i["content"]} for i in items],
        })

    # Fetch open items
    open_items = conn.execute(
        """SELECT mi.content, m.date FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'
           ORDER BY mi.created_at DESC""",
        (member_id,),
    ).fetchall()
    open_items_list = [{"content": i["content"], "date": i["date"]} for i in open_items]

    conn.close()

    cfg = load_config()
    from ascend.summarizer import generate_prep
    result = generate_prep(member_name, recent_meetings, open_items_list, config=cfg)

    log_operation("meeting prep", args={"member": args.member})

    if getattr(args, "json", False):
        render_output({"member": member_name, "prep": result}, json_mode=True)
    else:
        if result:
            render_output(f"## 1:1 Prep — {member_name}\n\n{result}")
        else:
            render_output(f"Could not generate prep for {member_name} (LLM unavailable or no data)")
