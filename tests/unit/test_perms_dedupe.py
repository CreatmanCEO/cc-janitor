from pathlib import Path
from cc_janitor.core.permissions import (
    PermRule, PermSource, find_duplicates,
)


def _src(scope="user-local", path="/x"):
    return PermSource(path=Path(path), scope=scope)


def test_find_subsumed():
    rs = [
        PermRule(tool="Bash", pattern="git *", decision="allow", source=_src(), raw="Bash(git *)"),
        PermRule(tool="Bash", pattern="git status", decision="allow", source=_src(), raw="Bash(git status)"),
    ]
    dups = find_duplicates(rs)
    assert any(d.kind == "subsumed" for d in dups)


def test_find_exact_duplicate():
    rs = [
        PermRule(tool="Bash", pattern="npm *", decision="allow",
                 source=_src(scope="user-local", path="/a"), raw="Bash(npm *)"),
        PermRule(tool="Bash", pattern="npm *", decision="allow",
                 source=_src(scope="project-local", path="/b"), raw="Bash(npm *)"),
    ]
    dups = find_duplicates(rs)
    assert any(d.kind == "exact" for d in dups)


def test_empty_pattern_flagged():
    rs = [PermRule(tool="Bash", pattern="", decision="allow", source=_src(), raw="Bash()")]
    dups = find_duplicates(rs)
    assert any(d.kind == "empty" for d in dups)


def test_conflict_allow_vs_deny():
    rs = [
        PermRule(tool="Bash", pattern="git *", decision="allow", source=_src(), raw="Bash(git *)"),
        PermRule(tool="Bash", pattern="git push *", decision="deny", source=_src(), raw="Bash(git push *)"),
    ]
    dups = find_duplicates(rs)
    assert any(d.kind == "conflict" for d in dups)


def test_no_duplicates_in_clean_set():
    rs = [
        PermRule(tool="Bash", pattern="git status", decision="allow", source=_src(), raw="Bash(git status)"),
        PermRule(tool="Edit", pattern="./src/**", decision="allow", source=_src(), raw="Edit(./src/**)"),
    ]
    dups = find_duplicates(rs)
    assert dups == []
