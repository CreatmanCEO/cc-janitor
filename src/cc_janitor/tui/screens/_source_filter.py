"""Shared options helper for the Source filter dropdown on Permissions,
Hooks, and Memory tabs."""
from __future__ import annotations

from collections.abc import Iterator

from ...core.monorepo import discover_locations


def source_filter_options() -> Iterator[tuple[str, str]]:
    """Yield ``(label, value)`` pairs for the Select widget.

    The first three entries are static scope filters; everything after is a
    concrete monorepo location discovered under the user's CWD.
    """
    yield ("<real only>", "real")
    yield ("<real + nested>", "real+nested")
    yield ("<all incl. junk>", "all")
    try:
        locs = discover_locations(scope_filter=("real", "nested"))
    except Exception:
        locs = []
    for loc in locs:
        path_str = str(loc.path)
        yield (path_str, path_str)
