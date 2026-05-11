from pathlib import Path
from cc_janitor.core.monorepo import (
    MonorepoLocation, discover_locations, classify_location, SKIP_DIRS,
)


def test_discover_finds_three(mock_claude_home, monkeypatch):
    root = mock_claude_home / "projects"
    monkeypatch.setenv("CC_JANITOR_HOME", str(mock_claude_home / ".cc-janitor"))
    locs = discover_locations(root, include_junk=True)
    paths = {l.path.relative_to(root) for l in locs}
    assert Path("real-proj/.claude") in paths
    assert Path("real-proj/node_modules/es-abstract/.claude") in paths
    assert Path("scratch/.claude") in paths


def test_classify_real_when_parent_has_pyproject(tmp_path):
    parent = tmp_path / "p"
    parent.mkdir()
    (parent / "pyproject.toml").write_text("")
    claude = parent / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}")
    loc = classify_location(claude)
    assert loc.scope_kind == "real"
    assert loc.has_settings is True
    assert loc.project_marker == "pyproject.toml"


def test_classify_nested_when_inside_node_modules(tmp_path):
    p = tmp_path / "node_modules" / "x"
    p.mkdir(parents=True)
    (p / "package.json").write_text("{}")
    claude = p / ".claude"
    claude.mkdir()
    loc = classify_location(claude)
    assert loc.scope_kind == "nested"


def test_classify_junk_when_no_marker(tmp_path):
    p = tmp_path / "scratch"
    p.mkdir()
    claude = p / ".claude"
    claude.mkdir()
    loc = classify_location(claude)
    assert loc.scope_kind == "junk"


def test_skip_dirs_default_includes_node_modules():
    assert "node_modules" in SKIP_DIRS
    assert ".venv" in SKIP_DIRS
    assert ".git" in SKIP_DIRS


def test_default_excludes_junk(mock_claude_home):
    root = mock_claude_home / "projects"
    locs = discover_locations(root, include_junk=False)
    kinds = {l.scope_kind for l in locs}
    assert "junk" not in kinds
