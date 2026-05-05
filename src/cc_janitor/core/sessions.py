from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal


@dataclass
class SessionSummary:
    source: Literal["jsonl_compact", "user_indexer_md", "first_msg"]
    text: str
    timestamp: datetime | None = None
    md_path: Path | None = None


@dataclass
class Session:
    id: str
    project: str
    jsonl_path: Path
    started_at: datetime | None
    last_activity: datetime
    size_bytes: int
    message_count: int
    first_user_msg: str
    last_user_msg: str
    compactions: int
    related_dirs: list[Path] = field(default_factory=list)
    summaries: list[SessionSummary] = field(default_factory=list)
    tokens_estimate: int = 0  # filled in later by token_count module


def _iter_jsonl(p: Path) -> Iterator[dict]:
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                return blk.get("text", "")
        return ""
    return ""


def parse_session(jsonl_path: Path, *, project: str) -> Session:
    sid = jsonl_path.stem
    msgs = list(_iter_jsonl(jsonl_path))
    user_msgs = [m for m in msgs if m.get("type") == "user"]
    compact_summaries = [m for m in msgs if m.get("type") == "summary" and "summary" in m]

    def _ts(m):
        ts = m.get("timestamp")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    started_at = _ts(user_msgs[0]) if user_msgs else None
    last_activity = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)

    first_user = ""
    last_user = ""
    if user_msgs:
        first_user = _extract_text(user_msgs[0].get("message", {}).get("content", ""))[:200]
        last_user = _extract_text(user_msgs[-1].get("message", {}).get("content", ""))[:200]

    summaries = [
        SessionSummary(source="jsonl_compact", text=m["summary"], timestamp=_ts(m))
        for m in compact_summaries
    ]
    if first_user:
        summaries.append(SessionSummary(source="first_msg", text=first_user))

    related = []
    for d in (
        jsonl_path.parent / sid,
        jsonl_path.parent / "subagents",
        jsonl_path.parent / "tool-results",
    ):
        if d.is_dir():
            related.append(d)

    return Session(
        id=sid,
        project=project,
        jsonl_path=jsonl_path,
        started_at=started_at,
        last_activity=last_activity,
        size_bytes=jsonl_path.stat().st_size,
        message_count=len(msgs),
        first_user_msg=first_user,
        last_user_msg=last_user,
        compactions=len(compact_summaries),
        related_dirs=related,
        summaries=summaries,
    )
