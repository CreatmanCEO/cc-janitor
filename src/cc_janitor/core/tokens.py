from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _enc():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc().encode(text))


def count_file_tokens(p: Path) -> int:
    if not p.exists():
        return 0
    return count_tokens(p.read_text(encoding="utf-8", errors="replace"))
