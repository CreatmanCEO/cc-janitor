from cc_janitor.core.schedule import TEMPLATES, CronScheduler, ScheduledJob


def test_template_registry_complete():
    assert {
        "perms-prune",
        "trash-cleanup",
        "session-prune",
        "context-audit",
        "backup-rotate",
    } <= set(TEMPLATES.keys())


def test_cron_add_then_list_then_remove(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / ".cc-janitor"))
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    captured = {"crontab_in": "", "stdin": ""}

    def fake_run(args, input=None, capture_output=False, **kw):
        class R:
            returncode = 0
            stdout = captured["crontab_in"].encode() if "-l" in args else b""
            stderr = b""

        if input is not None:
            captured["stdin"] = input.decode() if isinstance(input, bytes) else input
            captured["crontab_in"] = captured["stdin"]
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    sched = CronScheduler()
    sched.add_job(
        ScheduledJob(
            name="cc-janitor-perms-prune",
            template="perms-prune",
            cron_expr="0 3 * * 0",
            command="cc-janitor perms prune --older-than 90d --dry-run",
            next_run=None,
            last_run=None,
            last_status="never",
            dry_run_pending=True,
            backend="cron",
        )
    )
    assert "cc-janitor-perms-prune" in captured["stdin"]

    jobs = sched.list_jobs()
    assert any(j.name == "cc-janitor-perms-prune" for j in jobs)

    sched.remove_job("cc-janitor-perms-prune")
    assert "cc-janitor-perms-prune" not in captured["stdin"]
