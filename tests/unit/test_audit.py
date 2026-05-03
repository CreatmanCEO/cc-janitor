import json
from pathlib import Path
from cc_janitor.core.audit import AuditLog, AuditEntry

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
