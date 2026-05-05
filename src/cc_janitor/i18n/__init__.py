from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).parent
_current_lang = "en"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    p = _HERE / f"{lang}.toml"
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text(encoding="utf-8"))


def set_lang(lang: str) -> None:
    global _current_lang
    _current_lang = lang


def detect_lang() -> str:
    explicit = os.environ.get("CC_JANITOR_LANG")
    if explicit:
        return "ru" if explicit.lower().startswith("ru") else "en"
    sys_lang = os.environ.get("LANG", "")
    return "ru" if sys_lang.lower().startswith("ru") else "en"


def t(key: str, *, lang: str | None = None, **fmt) -> str:
    lang = lang or _current_lang
    parts = key.split(".")
    for source in (lang, "en"):
        d = _load(source)
        ok = True
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                ok = False
                break
        if ok and isinstance(d, str):
            return d.format(**fmt) if fmt else d
    return key
