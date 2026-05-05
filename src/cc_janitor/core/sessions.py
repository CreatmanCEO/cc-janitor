from __future__ import annotations
import json
import os
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
    # errors="replace" so a partial UTF-8 codepoint at end of file (truncated
    # mid-write) corrupts at most one line instead of killing the iterator.
    with p.open("r", encoding="utf-8", errors="replace") as f:
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

    # Per-session related directory only. subagents/ and tool-results/ live
    # INSIDE the session dir (<sid>/subagents/, <sid>/tool-results/) — never
    # as siblings of the jsonl. Including siblings here would cause
    # delete_session to wipe project-wide artifacts of OTHER sessions.
    related = []
    session_dir = jsonl_path.parent / sid
    if session_dir.is_dir():
        related.append(session_dir)

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


from .state import get_paths


def _claude_projects_root() -> Path:
    """Locate ``~/.claude/projects`` (the user-home, NOT cc-janitor home)."""
    return Path.home() / ".claude" / "projects"


def _cache_path() -> Path:
    return get_paths().cache / "sessions.json"


def _serialize(s: Session) -> dict:
    return {
        "id": s.id,
        "project": s.project,
        "jsonl_path": str(s.jsonl_path),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "last_activity": s.last_activity.isoformat(),
        "size_bytes": s.size_bytes,
        "message_count": s.message_count,
        "first_user_msg": s.first_user_msg,
        "last_user_msg": s.last_user_msg,
        "compactions": s.compactions,
        "tokens_estimate": s.tokens_estimate,
        "related_dirs": [str(p) for p in s.related_dirs],
        "summaries": [
            {
                "source": x.source,
                "text": x.text,
                "timestamp": x.timestamp.isoformat() if x.timestamp else None,
                "md_path": str(x.md_path) if x.md_path else None,
            }
            for x in s.summaries
        ],
        "mtime_ns": s.jsonl_path.stat().st_mtime_ns if s.jsonl_path.exists() else 0,
    }


def _deserialize(d: dict) -> Session | None:
    p = Path(d["jsonl_path"])
    if not p.exists():
        return None
    st = p.stat()
    if st.st_mtime_ns != d.get("mtime_ns") or st.st_size != d.get("size_bytes"):
        return None  # cache invalid: file changed
    return Session(
        id=d["id"],
        project=d["project"],
        jsonl_path=p,
        started_at=datetime.fromisoformat(d["started_at"]) if d["started_at"] else None,
        last_activity=datetime.fromisoformat(d["last_activity"]),
        size_bytes=d["size_bytes"],
        message_count=d["message_count"],
        first_user_msg=d["first_user_msg"],
        last_user_msg=d["last_user_msg"],
        compactions=d["compactions"],
        tokens_estimate=d.get("tokens_estimate", 0),
        related_dirs=[Path(p) for p in d.get("related_dirs", [])],
        summaries=[
            SessionSummary(
                source=x["source"],
                text=x["text"],
                timestamp=datetime.fromisoformat(x["timestamp"]) if x.get("timestamp") else None,
                md_path=Path(x["md_path"]) if x.get("md_path") else None,
            )
            for x in d.get("summaries", [])
        ],
    )


def discover_sessions(*, project: str | None = None, refresh: bool = False) -> list[Session]:
    paths = get_paths()
    paths.ensure_dirs()
    cache_p = _cache_path()
    cache: dict[str, dict] = {}
    if cache_p.exists() and not refresh:
        try:
            cache = {e["id"]: e for e in json.loads(cache_p.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, KeyError):
            cache = {}

    out: list[Session] = []
    root = _claude_projects_root()
    if not root.exists():
        return out
    for proj_dir in root.iterdir():
        if not proj_dir.is_dir():
            continue
        if project and proj_dir.name != project:
            continue
        for jsonl_p in proj_dir.glob("*.jsonl"):
            sid = jsonl_p.stem
            cached_entry = cache.get(sid)
            session = None
            if cached_entry:
                session = _deserialize(cached_entry)
            if session is None:
                session = parse_session(jsonl_p, project=proj_dir.name)
            out.append(session)

    tmp = cache_p.with_suffix(cache_p.suffix + ".tmp")
    tmp.write_text(
        json.dumps([_serialize(s) for s in out], ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, cache_p)
    return out


def enrich_with_indexer_summaries(sessions: list[Session], *, indexer_root: Path) -> list[Session]:
    """Attach user-side markdown summaries (e.g. from index-session.sh) to sessions.

    Looks in ``indexer_root`` for ``*.md`` files whose stem contains the session
    id (full or 8-char prefix). Adds one ``SessionSummary(source="user_indexer_md")``
    per match. Mutates and returns the same list for convenience.
    """
    if not indexer_root.exists():
        return sessions
    md_files = list(indexer_root.glob("*.md"))
    for s in sessions:
        for md in md_files:
            if s.id in md.stem or s.id[:8] in md.stem:
                s.summaries.append(SessionSummary(
                    source="user_indexer_md",
                    text=md.read_text(encoding="utf-8", errors="replace")[:1000],
                    md_path=md,
                ))
                break  # one .md per session is sufficient
    return sessions


def delete_session(s: Session) -> str:
    """Move a session JSONL plus its per-session subdirectory to trash.

    Both the .jsonl file and any per-session related directory are bundled
    into a single trash bucket so they can be restored together.

    Raises:
        NotConfirmedError: when CC_JANITOR_USER_CONFIRMED != "1".
        FileNotFoundError: when the JSONL no longer exists on disk.
    """
    from .safety import require_confirmed, soft_delete
    require_confirmed()
    if not s.jsonl_path.exists():
        raise FileNotFoundError(s.jsonl_path)

    paths = get_paths()
    paths.ensure_dirs()

    import tempfile, shutil
    # Build a single bundle directory containing jsonl + related_dirs,
    # then soft_delete the bundle as one unit.
    with tempfile.TemporaryDirectory(prefix="ccj-bundle-", dir=paths.home) as td:
        bundle = Path(td) / s.id
        bundle.mkdir()
        shutil.move(str(s.jsonl_path), str(bundle / s.jsonl_path.name))
        for d in s.related_dirs:
            if d.exists():
                shutil.move(str(d), str(bundle / d.name))
        return soft_delete(bundle, paths=paths)
