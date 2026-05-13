import json
from pathlib import Path

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_stats_sleep_hygiene_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert "projects" in data
    assert data["totals"]["projects"] == 0


def test_stats_sleep_hygiene_with_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text(
        "yesterday we did x\nrecently changed y\n", encoding="utf-8")
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    data = json.loads(res.stdout)
    assert data["totals"]["total_relative_date_matches"] >= 2


def _seed_contradictions(tmp_path):
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "feedback_a.md").write_text(
        "Never use openai api in this project\n", encoding="utf-8")
    (mem / "feedback_b.md").write_text(
        "Always use openai api for embeddings\n", encoding="utf-8")
    return mem


def test_stats_sleep_hygiene_json_contains_pairs(tmp_path, monkeypatch):
    """C5: JSON output exposes contradicting_pairs content (not just count)."""
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    _seed_contradictions(tmp_path)
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    proj = next(p for p in data["projects"] if p["project_slug"] == "-proj")
    assert proj["contradicting_pair_count"] >= 1
    assert "contradicting_pairs" in proj
    assert proj["contradicting_pairs"], "JSON must include pair content, not only count"
    pair = proj["contradicting_pairs"][0]
    assert "subject" in pair and "files" in pair
    assert len(pair["files"]) == 2


def test_stats_sleep_hygiene_text_lists_pairs(tmp_path, monkeypatch):
    """C5: text output shows one line per contradicting pair under header."""
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    _seed_contradictions(tmp_path)
    res = runner.invoke(app, ["stats", "sleep-hygiene"])
    assert res.exit_code == 0
    assert "Contradictions:" in res.stdout
    assert "—" in res.stdout
    assert "feedback_a.md" in res.stdout or "feedback_b.md" in res.stdout
