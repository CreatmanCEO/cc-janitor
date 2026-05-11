from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config
from .memory import find_duplicate_lines

DEFAULT_RELATIVE_TERMS = (
    "yesterday", "today", "recently", "now", "last week",
    "вчера", "сегодня", "недавно", "на прошлой неделе",
    "в прошлый раз", "в этот раз", "на днях",
)

NEG_PATTERN = re.compile(r"(?i)\b(never|don'?t|stop|avoid)\b\s+(.+)")
POS_PATTERN = re.compile(r"(?i)\b(always|prefer|use)\b\s+(.+)")


@dataclass
class ProjectHygiene:
    project_slug: str
    memory_md_size_lines: int
    memory_md_cap: int
    relative_date_density: float
    relative_date_matches: list[tuple[Path, int, str]]
    cross_file_dup_count: int
    contradicting_pairs: list[tuple[str, list[Path]]]


@dataclass
class HygieneReport:
    generated_at: datetime
    projects: list[ProjectHygiene]
    totals: dict


def _scan_relative_dates(
    paths: list[Path],
    *,
    extra_terms: tuple[str, ...],
) -> list[tuple[Path, int, str]]:
    terms = tuple(DEFAULT_RELATIVE_TERMS) + tuple(extra_terms)
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(t) for t in terms) + r")(?!\w)",
        re.IGNORECASE,
    )
    out: list[tuple[Path, int, str]] = []
    for f in paths:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                out.append((f, i, m.group(1).lower()))
    return out


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\w+", s) if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_contradiction_subjects(
    paths: list[Path],
    *,
    jaccard_threshold: float,
) -> list[tuple[str, list[Path]]]:
    neg: list[tuple[str, Path]] = []
    pos: list[tuple[str, Path]] = []
    for f in paths:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            mn = NEG_PATTERN.search(line)
            if mn:
                neg.append((mn.group(2).strip(), f))
            mp = POS_PATTERN.search(line)
            if mp:
                pos.append((mp.group(2).strip(), f))
    pairs: list[tuple[str, list[Path]]] = []
    for ns, nf in neg:
        nt = _tokens(ns)
        for ps, pf in pos:
            if _jaccard(nt, _tokens(ps)) >= jaccard_threshold:
                pairs.append((ns, [nf, pf]))
                break
    return pairs


def compute_project_hygiene(memory_dir: Path) -> ProjectHygiene:
    cfg = load_config()
    md_files = sorted(memory_dir.rglob("*.md"))
    memory_md = memory_dir / "MEMORY.md"
    total_lines = sum(
        sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
        for f in md_files
    ) or 1
    rel_matches = _scan_relative_dates(
        md_files, extra_terms=cfg.hygiene.relative_date_terms_extra,
    )
    dups = find_duplicate_lines(md_files, min_length=8)
    contradictions = _extract_contradiction_subjects(
        md_files,
        jaccard_threshold=cfg.hygiene.contradiction_jaccard_threshold,
    )
    memory_md_lines = (
        sum(1 for _ in memory_md.open("r", encoding="utf-8", errors="ignore"))
        if memory_md.exists() else 0
    )
    return ProjectHygiene(
        project_slug=memory_dir.parent.name,
        memory_md_size_lines=memory_md_lines,
        memory_md_cap=cfg.dream_doctor.memory_md_line_threshold,
        relative_date_density=len(rel_matches) / total_lines,
        relative_date_matches=rel_matches,
        cross_file_dup_count=len(dups),
        contradicting_pairs=contradictions,
    )


def compute_report() -> HygieneReport:
    projects_root = Path.home() / ".claude" / "projects"
    projects: list[ProjectHygiene] = []
    if projects_root.exists():
        for p in projects_root.iterdir():
            mem = p / "memory"
            if mem.is_dir():
                projects.append(compute_project_hygiene(mem))
    totals = {
        "projects": len(projects),
        "total_relative_date_matches": sum(
            len(p.relative_date_matches) for p in projects),
        "total_cross_file_dups": sum(
            p.cross_file_dup_count for p in projects),
        "total_contradiction_pairs": sum(
            len(p.contradicting_pairs) for p in projects),
    }
    return HygieneReport(datetime.now(UTC), projects, totals)
