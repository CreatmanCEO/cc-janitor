from cc_janitor.core.config import (
    DEFAULTS,
    load_config,
)


def test_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.dream_doctor.disk_warning_mb == 100
    assert cfg.dream_doctor.memory_file_count_threshold == 50
    assert cfg.dream_doctor.memory_md_line_threshold == 180
    assert cfg.snapshots.raw_retention_days == 7
    assert cfg.snapshots.tar_retention_days == 30


def test_partial_override(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[dream_doctor]\n'
        'disk_warning_mb = 500\n'
        '[snapshots]\n'
        'raw_retention_days = 14\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.dream_doctor.disk_warning_mb == 500
    assert cfg.dream_doctor.memory_md_line_threshold == 180  # default kept
    assert cfg.snapshots.raw_retention_days == 14
    assert cfg.snapshots.tar_retention_days == 30


def test_malformed_falls_back_to_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("this is not [valid toml", encoding="utf-8")
    cfg = load_config(p)
    assert cfg == DEFAULTS


def test_extra_relative_date_terms(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[hygiene]\n'
        'relative_date_terms_extra = ["позавчера", "tomorrow"]\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert "позавчера" in cfg.hygiene.relative_date_terms_extra


def test_malformed_toml_warns_to_stderr(tmp_path, capsys):
    """0.4.2: malformed config.toml emits a clear stderr warning."""
    from cc_janitor.core import config as cfg_mod

    # Clear warned cache for isolation
    cfg_mod._WARNED_PATHS.clear()

    p = tmp_path / "config.toml"
    p.write_text("[dream_doctor\nbroken =\n", encoding="utf-8")
    cfg = load_config(p)
    captured = capsys.readouterr()
    assert "failed to parse" in captured.err
    assert str(p) in captured.err
    assert cfg == DEFAULTS


def test_malformed_toml_warning_emitted_once(tmp_path, capsys):
    """Repeated load_config() with the same broken file emits one warning."""
    from cc_janitor.core import config as cfg_mod

    cfg_mod._WARNED_PATHS.clear()
    p = tmp_path / "config.toml"
    p.write_text("[bad", encoding="utf-8")
    load_config(p)
    load_config(p)
    load_config(p)
    captured = capsys.readouterr()
    assert captured.err.count("failed to parse") == 1


def test_config_init_creates_file(tmp_path, monkeypatch):
    """0.4.2: cc-janitor config init scaffolds the file with defaults."""
    from pathlib import Path

    from typer.testing import CliRunner

    from cc_janitor.cli import app

    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)

    r = CliRunner().invoke(app, ["config", "init"])
    assert r.exit_code == 0, r.stdout
    target = tmp_path / "jhome" / "config.toml"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "[dream_doctor]" in content
    assert "[snapshots]" in content
    assert "[hygiene]" in content


def test_config_init_refuses_overwrite_without_force(tmp_path, monkeypatch):
    from pathlib import Path

    from typer.testing import CliRunner

    from cc_janitor.cli import app

    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / "jhome").mkdir()
    (tmp_path / "jhome" / "config.toml").write_text("custom = 1\n")

    r = CliRunner().invoke(app, ["config", "init"])
    assert r.exit_code != 0
    assert (tmp_path / "jhome" / "config.toml").read_text() == "custom = 1\n"

    # With --force, overwrite
    r2 = CliRunner().invoke(app, ["config", "init", "--force"])
    assert r2.exit_code == 0
    assert "[dream_doctor]" in (tmp_path / "jhome" / "config.toml").read_text()
