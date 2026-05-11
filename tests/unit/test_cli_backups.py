"""Tests for ``cc-janitor backups`` (0.3.2 — C5)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.state import get_paths


def _seed_bucket(home: Path, name: str, *, age_days: float) -> Path:
    """Create a backup bucket with one file, mtime set to N days ago."""
    bucket = home / ".cc-janitor" / "backups" / name
    bucket.mkdir(parents=True, exist_ok=True)
    f = bucket / "settings.json.bak"
    f.write_text("{}", encoding="utf-8")
    mtime = time.time() - age_days * 86400
    os.utime(f, (mtime, mtime))
    return bucket


def test_backups_list_empty(mock_claude_home):
    r = CliRunner().invoke(app, ["backups", "list"])
    assert r.exit_code == 0


def test_backups_list_shows_seeded(mock_claude_home):
    _seed_bucket(mock_claude_home, "aaa111", age_days=5)
    r = CliRunner().invoke(app, ["backups", "list"])
    assert r.exit_code == 0
    assert "aaa111" in r.stdout


def test_backups_prune_dry_run(mock_claude_home):
    _seed_bucket(mock_claude_home, "old", age_days=60)
    _seed_bucket(mock_claude_home, "young", age_days=2)
    r = CliRunner().invoke(app, ["backups", "prune", "--dry-run"])
    assert r.exit_code == 0
    assert "old" in r.stdout
    assert "young" not in r.stdout
    # nothing actually deleted
    paths = get_paths()
    assert (paths.backups / "old").exists()
    assert (paths.backups / "young").exists()


def test_backups_prune_requires_confirm(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    _seed_bucket(mock_claude_home, "old", age_days=60)
    r = CliRunner().invoke(app, ["backups", "prune"])
    assert r.exit_code != 0
    # still there
    paths = get_paths()
    assert (paths.backups / "old").exists()


def test_backups_prune_deletes_only_old(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    _seed_bucket(mock_claude_home, "old", age_days=60)
    _seed_bucket(mock_claude_home, "young", age_days=2)
    r = CliRunner().invoke(app, ["backups", "prune", "--older-than-days", "30"])
    assert r.exit_code == 0
    paths = get_paths()
    assert not (paths.backups / "old").exists()
    assert (paths.backups / "young").exists()


def test_backup_rotate_template_emits_valid_command():
    """Regression: 0.3.1's template emitted an unknown --backups flag."""
    from cc_janitor.core.schedule import TEMPLATES

    cmd = TEMPLATES["backup-rotate"]["command"]
    assert "backups prune" in cmd
    assert "--older-than-days" in cmd
    assert "--backups" not in cmd  # the broken flag must be gone
