from pathlib import Path

from cc_janitor.core.dream_doctor import run_checks


def test_doctor_runs_all_9_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"autoDreamEnabled": true}', encoding="utf-8")
    checks = run_checks()
    ids = {c.id for c in checks}
    expected = {"stale_lock", "autodream_enabled", "server_gate",
                "last_dream_ts", "backup_dir_health", "memory_md_cap",
                "disk_usage", "memory_file_count", "duplicate_summary"}
    assert expected.issubset(ids)


def test_stale_lock_with_dead_pid_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / ".consolidate-lock").write_text("999999")  # very unlikely-alive PID
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    checks = {c.id: c for c in run_checks()}
    assert checks["stale_lock"].severity == "FAIL"
