from cc_janitor.core.audit import AuditLog


def test_record_and_read(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.record(mode="cli", user_confirmed=True, cmd="session list", args=[], exit_code=0)
    entries = list(log.read())
    assert len(entries) == 1
    assert entries[0].cmd == "session list"
    assert entries[0].user_confirmed is True

def test_rotates_when_too_large(tmp_path):
    p = tmp_path / "audit.log"
    log = AuditLog(p, max_bytes=200)
    for i in range(50):
        log.record(mode="cli", user_confirmed=False, cmd=f"x{i}", args=[], exit_code=0)
    rotated = list(tmp_path.glob("audit.log.*"))
    assert len(rotated) >= 1, "Should have rotated at least once"

def test_read_filter_by_cmd(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.record(mode="cli", user_confirmed=True, cmd="session delete", args=["x"], exit_code=0)
    log.record(mode="cli", user_confirmed=True, cmd="perms prune", args=[], exit_code=0)
    rs = list(log.read(cmd_glob="session*"))
    assert len(rs) == 1 and rs[0].cmd == "session delete"


def test_record_and_read_roundtrip_unicode(tmp_path):
    """Cyrillic and emoji content survives JSON round-trip with ensure_ascii=False."""
    log = AuditLog(tmp_path / "audit.log")
    log.record(mode="cli", user_confirmed=True, cmd="перенос сессии",
               args=["—", "Сессия #1"], exit_code=0,
               changed={"删除": 5, "removed": "файлы"})
    [entry] = list(log.read())
    assert entry.cmd == "перенос сессии"
    assert entry.args == ["—", "Сессия #1"]
    assert entry.changed == {"删除": 5, "removed": "файлы"}
    # also verify stored file is utf-8 with literal cyrillic, no \uXXXX escapes
    raw = (tmp_path / "audit.log").read_text(encoding="utf-8")
    assert "перенос" in raw
    assert "\\u" not in raw  # no escape sequences


def test_read_skips_malformed_lines(tmp_path):
    """A truncated/corrupt line should be skipped, not raise."""
    p = tmp_path / "audit.log"
    log = AuditLog(p)
    log.record(mode="cli", user_confirmed=True, cmd="ok1", args=[], exit_code=0)
    # append a bad line manually
    with p.open("a", encoding="utf-8") as f:
        f.write('{"this is": "truncated", "cmd"\n')
    log.record(mode="cli", user_confirmed=True, cmd="ok2", args=[], exit_code=0)
    cmds = [e.cmd for e in log.read()]
    assert cmds == ["ok1", "ok2"]
