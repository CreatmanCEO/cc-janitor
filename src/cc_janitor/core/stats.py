from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from .state import get_paths

SPARKLINE_CHARS = " ▁▂▃▄▅▆▇█"


@dataclass
class StatsSnapshot:
    date: date
    sessions_count: int
    perm_rules_count: int
    context_tokens: int
    trash_bytes: int
    audit_entries_since_last: int


def _history_dir() -> Path:
    p = get_paths().history
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_snapshot(s: StatsSnapshot) -> Path:
    p = _history_dir() / f"{s.date.isoformat()}.json"
    d = asdict(s)
    d["date"] = s.date.isoformat()
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return p


def load_snapshots(*, since: timedelta = timedelta(days=30)) -> list[StatsSnapshot]:
    cutoff = date.today() - since
    out: list[StatsSnapshot] = []
    for f in sorted(_history_dir().glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        try:
            snap_date = date.fromisoformat(d["date"])
        except (KeyError, ValueError):
            continue
        if snap_date < cutoff:
            continue
        out.append(StatsSnapshot(
            date=snap_date,
            sessions_count=int(d.get("sessions_count", 0)),
            perm_rules_count=int(d.get("perm_rules_count", 0)),
            context_tokens=int(d.get("context_tokens", 0)),
            trash_bytes=int(d.get("trash_bytes", 0)),
            audit_entries_since_last=int(d.get("audit_entries_since_last", 0)),
        ))
    out.sort(key=lambda s: s.date)
    return out


def take_snapshot() -> StatsSnapshot:
    """Compute today's snapshot from the live cc-janitor state."""
    from .permissions import discover_rules
    from .sessions import discover_sessions
    paths = get_paths()
    sessions = discover_sessions()
    rules = discover_rules()
    tokens = 0
    try:
        from .context import context_cost
        ctx = context_cost(starting_from=Path.cwd())
        tokens = ctx.total_tokens
    except Exception:
        tokens = 0
    trash_bytes = (
        sum(p.stat().st_size for p in paths.trash.rglob("*") if p.is_file())
        if paths.trash.exists() else 0
    )
    audit_entries = 0
    if paths.audit_log.exists():
        prev = sorted(_history_dir().glob("*.json"))
        previous_count = 0
        if prev:
            try:
                previous_count = int(
                    json.loads(prev[-1].read_text(encoding="utf-8"))
                    .get("_audit_total_lines", 0)
                )
            except Exception:
                previous_count = 0
        with paths.audit_log.open("r", encoding="utf-8") as f:
            current_total = sum(1 for _ in f)
        audit_entries = max(0, current_total - previous_count)
    return StatsSnapshot(
        date=date.today(),
        sessions_count=len(sessions),
        perm_rules_count=len(rules),
        context_tokens=tokens,
        trash_bytes=trash_bytes,
        audit_entries_since_last=audit_entries,
    )


def render_sparkline(values: list[float], *, width: int = 30) -> str:
    if not values:
        return " " * width
    if len(values) > width:
        bucket = len(values) / width
        values = [
            sum(values[int(i*bucket):int((i+1)*bucket)]) / max(1, int((i+1)*bucket) - int(i*bucket))
            for i in range(width)
        ]
    elif len(values) < width:
        pad = [values[0]] * (width - len(values))
        values = pad + list(values)
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARKLINE_CHARS[len(SPARKLINE_CHARS) // 2] * width
    span = hi - lo
    bins = len(SPARKLINE_CHARS) - 1
    out = []
    for v in values:
        idx = int((v - lo) / span * bins)
        out.append(SPARKLINE_CHARS[max(1, min(bins, idx))])
    return "".join(out)
