from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_scan_table_output(mock_claude_home):
    res = runner.invoke(app, ["monorepo", "scan",
                              "--root", str(mock_claude_home / "projects")])
    assert res.exit_code == 0
    assert ".claude" in res.stdout
    assert "real" in res.stdout


def test_scan_json_output(mock_claude_home):
    res = runner.invoke(app, ["monorepo", "scan", "--json",
                              "--root", str(mock_claude_home / "projects")])
    assert res.exit_code == 0
    import json
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert all("scope_kind" in item for item in data)


def test_scan_include_junk(mock_claude_home):
    res = runner.invoke(app, ["monorepo", "scan", "--include-junk",
                              "--root", str(mock_claude_home / "projects")])
    assert "junk" in res.stdout
