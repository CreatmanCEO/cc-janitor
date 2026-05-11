"""Tests for the 0.3.1 scope filter on discover_rules / discover_hooks /
discover_memory_files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cc_janitor.core.hooks import discover_hooks
from cc_janitor.core.memory import discover_memory_files
from cc_janitor.core.permissions import discover_rules


def _make_real_proj(root: Path) -> Path:
    """A real project: parent has pyproject.toml, .claude/settings.json present."""
    p = root / "real-app"
    p.mkdir()
    (p / "pyproject.toml").write_text("", encoding="utf-8")
    claude = p / ".claude"
    claude.mkdir()
    settings = {
        "permissions": {"allow": ["Bash(real-cmd *)"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo real"}]}
            ]
        },
    }
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    mem = claude / "memory"
    mem.mkdir()
    (mem / "project_real.md").write_text("# real project memory\n", encoding="utf-8")
    return p


def _make_nested_proj(root: Path) -> Path:
    """A nested project: inside node_modules with package.json marker."""
    p = root / "real-app" / "node_modules" / "vendor-pkg"
    p.mkdir(parents=True, exist_ok=True)
    (p / "package.json").write_text("{}", encoding="utf-8")
    claude = p / ".claude"
    claude.mkdir()
    settings = {
        "permissions": {"allow": ["Bash(nested-cmd *)"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo nested"}]}
            ]
        },
    }
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    mem = claude / "memory"
    mem.mkdir()
    (mem / "project_nested.md").write_text("# nested project memory\n", encoding="utf-8")
    return p


@pytest.fixture
def scope_workspace(tmp_path, monkeypatch):
    """Fixture: HOME has no .claude, cwd has a real-proj + nested-proj."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CC_JANITOR_HOME", str(home / ".cc-janitor"))

    cwd = tmp_path / "ws"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    _make_real_proj(cwd)
    _make_nested_proj(cwd)
    return cwd


def test_discover_rules_scope_real_excludes_nested(scope_workspace):
    rules = discover_rules(scope="real")
    patterns = {r.pattern for r in rules}
    assert "real-cmd *" in patterns
    assert "nested-cmd *" not in patterns


def test_discover_rules_scope_nested_excludes_real(scope_workspace):
    rules = discover_rules(scope="nested")
    patterns = {r.pattern for r in rules}
    assert "nested-cmd *" in patterns
    assert "real-cmd *" not in patterns


def test_discover_rules_scope_none_returns_both(scope_workspace):
    rules = discover_rules()  # no scope arg
    patterns = {r.pattern for r in rules}
    assert "real-cmd *" in patterns
    assert "nested-cmd *" in patterns


def test_discover_rules_scope_all_returns_both(scope_workspace):
    rules = discover_rules(scope="all")
    patterns = {r.pattern for r in rules}
    assert "real-cmd *" in patterns
    assert "nested-cmd *" in patterns


def test_discover_rules_scope_real_plus_nested(scope_workspace):
    rules = discover_rules(scope="real+nested")
    patterns = {r.pattern for r in rules}
    assert "real-cmd *" in patterns
    assert "nested-cmd *" in patterns


def test_discover_hooks_scope_real_excludes_nested(scope_workspace):
    hooks = discover_hooks(scope="real")
    cmds = {h.command for h in hooks}
    assert "echo real" in cmds
    assert "echo nested" not in cmds


def test_discover_hooks_scope_nested_excludes_real(scope_workspace):
    hooks = discover_hooks(scope="nested")
    cmds = {h.command for h in hooks}
    assert "echo nested" in cmds
    assert "echo real" not in cmds


def test_discover_hooks_scope_none_returns_both(scope_workspace):
    hooks = discover_hooks()
    cmds = {h.command for h in hooks}
    assert "echo real" in cmds
    assert "echo nested" in cmds


def test_discover_hooks_files_alias(scope_workspace):
    from cc_janitor.core.hooks import discover_hooks_files
    assert discover_hooks_files(scope="real") == discover_hooks(scope="real")


def test_discover_memory_scope_real_excludes_nested(scope_workspace):
    items = discover_memory_files(scope="real")
    names = {m.path.name for m in items}
    assert "project_real.md" in names
    assert "project_nested.md" not in names


def test_discover_memory_scope_nested_excludes_real(scope_workspace):
    items = discover_memory_files(scope="nested")
    names = {m.path.name for m in items}
    assert "project_nested.md" in names
    assert "project_real.md" not in names


def test_discover_memory_scope_none_returns_both(scope_workspace):
    items = discover_memory_files()
    names = {m.path.name for m in items}
    assert "project_real.md" in names
    assert "project_nested.md" in names
