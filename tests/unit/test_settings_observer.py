from __future__ import annotations

import json
from pathlib import Path

from cc_janitor.core.audit import AuditLog
from cc_janitor.core.settings_observer import observe_autodream_change
from cc_janitor.core.state import get_paths


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()


def test_first_observation_no_change(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"autoDreamEnabled": false}'
    )
    assert observe_autodream_change() is None


def test_no_change_returns_none(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    s = tmp_path / ".claude" / "settings.json"
    s.write_text('{"autoDreamEnabled": true}')
    observe_autodream_change()
    assert observe_autodream_change() is None


def test_change_detected_writes_audit(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    s = tmp_path / ".claude" / "settings.json"
    s.write_text('{"autoDreamEnabled": false}')
    observe_autodream_change()
    s.write_text('{"autoDreamEnabled": true}')
    delta = observe_autodream_change()
    assert delta == (False, True)

    # Audit entry must have been recorded
    log = AuditLog(get_paths().audit_log)
    entries = list(log.read(cmd_glob="settings-observe"))
    assert len(entries) == 1
    assert entries[0].changed["old"] is False
    assert entries[0].changed["new"] is True
    assert entries[0].changed["key"] == "autoDreamEnabled"


def test_missing_settings_returns_none(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert observe_autodream_change() is None


def test_cache_file_at_expected_path(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"autoDreamEnabled": true}'
    )
    observe_autodream_change()
    cache = get_paths().home / "state" / "autodream-last-seen.json"
    assert cache.exists()
    assert json.loads(cache.read_text())["autoDreamEnabled"] is True
