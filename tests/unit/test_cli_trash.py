from typer.testing import CliRunner

from cc_janitor.cli import app


def test_trash_list_empty(mock_claude_home):
    r = CliRunner().invoke(app, ["trash", "list"])
    assert r.exit_code == 0
    assert "empty" in r.stdout.lower()


def test_trash_round_trip(mock_claude_home, monkeypatch):
    """delete → list → restore → original path back."""
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    # Soft-delete abc123
    r1 = CliRunner().invoke(app, ["session", "delete", "abc123"])
    assert r1.exit_code == 0

    # List shows the item
    r2 = CliRunner().invoke(app, ["trash", "list"])
    assert r2.exit_code == 0
    assert "abc123" in r2.stdout or any(c.isdigit() for c in r2.stdout)
    # Extract trash_id (first column)
    line = next((ln for ln in r2.stdout.splitlines() if ln.strip()), "")
    trash_id = line.split()[0]

    # Restore
    r3 = CliRunner().invoke(app, ["trash", "restore", trash_id])
    assert r3.exit_code == 0
    assert "restored" in r3.stdout.lower()
    # After restore, list should be empty
    r4 = CliRunner().invoke(app, ["trash", "list"])
    assert "empty" in r4.stdout.lower()


def test_trash_restore_requires_confirm(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = CliRunner().invoke(app, ["trash", "restore", "anything"])
    assert r.exit_code != 0


def test_trash_empty_with_all_flag(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    # Soft-delete to populate trash
    CliRunner().invoke(app, ["session", "delete", "abc123"])
    # Empty all
    r = CliRunner().invoke(app, ["trash", "empty", "--all"])
    assert r.exit_code == 0
    # List should be empty now
    r2 = CliRunner().invoke(app, ["trash", "list"])
    assert "empty" in r2.stdout.lower()
