from cc_janitor.core.state import get_paths


def test_get_paths_uses_default_home(monkeypatch, tmp_path):
    monkeypatch.delenv("CC_JANITOR_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    p = get_paths()
    assert p.home == tmp_path / ".cc-janitor"
    assert p.cache == tmp_path / ".cc-janitor" / "cache"
    assert p.trash == tmp_path / ".cc-janitor" / ".trash"
    assert p.backups == tmp_path / ".cc-janitor" / "backups"
    assert p.audit_log == tmp_path / ".cc-janitor" / "audit.log"


def test_get_paths_respects_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom"
    monkeypatch.setenv("CC_JANITOR_HOME", str(custom))
    p = get_paths()
    assert p.home == custom


def test_ensure_dirs_creates_them(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "x"))
    p = get_paths()
    p.ensure_dirs()
    for d in (p.cache, p.trash, p.backups, p.hooks_log, p.history):
        assert d.is_dir()


def test_get_paths_empty_override_falls_back(monkeypatch, tmp_path):
    """Empty-string CC_JANITOR_HOME should fall through to default home."""
    monkeypatch.setenv("CC_JANITOR_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert get_paths().home == tmp_path / ".cc-janitor"


def test_get_paths_expands_tilde(monkeypatch, tmp_path):
    """A ~ in CC_JANITOR_HOME should expand to the user home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CC_JANITOR_HOME", "~/janitor-data")
    assert get_paths().home == tmp_path / "janitor-data"


def test_ensure_dirs_does_not_touch_files(monkeypatch, tmp_path):
    """ensure_dirs creates only directories — never the audit_log or config file."""
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "x"))
    p = get_paths()
    p.ensure_dirs()
    assert not p.audit_log.exists()
    assert not p.config.exists()
