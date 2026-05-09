from cc_janitor.core.schedule import ScheduledJob, SchtasksScheduler


def test_schtasks_add_calls_create(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / ".cc-janitor"))
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    calls = []

    def fake_run(args, **kw):
        calls.append(args)

        class R:
            returncode = 0
            stdout = b""
            stderr = b""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    s = SchtasksScheduler()
    s.add_job(
        ScheduledJob(
            name="cc-janitor-perms-prune",
            template="perms-prune",
            cron_expr="0 3 * * 0",
            command="cc-janitor perms prune --older-than 90d --dry-run",
            next_run=None,
            last_run=None,
            last_status="never",
            dry_run_pending=True,
            backend="schtasks",
        )
    )
    assert any("/Create" in str(c) for c in calls)
