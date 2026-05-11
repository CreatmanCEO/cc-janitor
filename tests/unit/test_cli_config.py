from __future__ import annotations

from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.bundle import export_bundle

runner = CliRunner()


def test_cli_config_export_creates_bundle(mock_claude_home, tmp_path):
    out = tmp_path / "b.tar.gz"
    result = runner.invoke(app, ["config", "export", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "Exported" in result.output


def test_cli_config_import_dry_run_first(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "b.tar.gz"
    export_bundle(out, include_memory=False)
    target = mock_claude_home / ".claude" / "CLAUDE.md"
    target.write_text("DIFFERENT", encoding="utf-8")
    # No --apply: should dry-run only.
    result = runner.invoke(app, ["config", "import", str(out)])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert target.read_text(encoding="utf-8") == "DIFFERENT"


def test_cli_config_import_apply_writes(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "b.tar.gz"
    export_bundle(out, include_memory=False)
    target = mock_claude_home / ".claude" / "CLAUDE.md"
    original = target.read_text(encoding="utf-8")
    target.write_text("DIFFERENT", encoding="utf-8")
    result = runner.invoke(app, ["config", "import", str(out), "--apply"])
    assert result.exit_code == 0, result.output
    assert "Imported" in result.output
    assert target.read_text(encoding="utf-8") == original


def test_cli_config_import_requires_confirmed(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    out = tmp_path / "b.tar.gz"
    # Need confirmed to call export... actually export is read-only. Use direct.
    from cc_janitor.core.bundle import export_bundle as _e
    _e(out, include_memory=False)
    result = runner.invoke(app, ["config", "import", str(out), "--apply"])
    assert result.exit_code != 0
