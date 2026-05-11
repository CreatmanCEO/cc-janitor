import json
from datetime import datetime, timezone
from pathlib import Path
from cc_janitor.core.dream_snapshot import (
    DreamSnapshotPair, LockState, observe_lock, snapshot_pre,
    snapshot_post, record_pair, history,
)


def _fake_memory(root: Path) -> Path:
    mem = root / ".claude" / "projects" / "-home-u-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\nb\nc\n")
    (mem / "x.md").write_text("x\n")
    return mem


def test_observe_lock_appearing(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = _fake_memory(tmp_path)
    lock = mem / ".consolidate-lock"
    state = LockState()
    transition = observe_lock(mem, state)
    assert transition.kind == "no_change"
    lock.write_text("38249")
    transition = observe_lock(mem, state)
    assert transition.kind == "lock_appeared"
    assert transition.pid == 38249


def test_snapshot_pre_writes_raw_mirror(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = _fake_memory(tmp_path)
    pair_id = "20260511T120000Z-proj"
    snapshot_pre(pair_id, mem)
    pre = tmp_path / "jhome" / "backups" / "dream" / f"{pair_id}-pre"
    assert (pre / "MEMORY.md").exists()
    assert (pre / "MEMORY.md").read_text() == "a\nb\nc\n"


def test_full_pair_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = _fake_memory(tmp_path)
    pair_id = "20260511T120000Z-proj"
    pre = snapshot_pre(pair_id, mem)
    # Auto Dream "ran" — mutate.
    (mem / "MEMORY.md").write_text("a\nb\n")
    (mem / "x.md").unlink()
    post = snapshot_post(pair_id, mem)
    pair = record_pair(pair_id, mem, project_slug="proj",
                       dream_pid_in_lock=38249,
                       ts_pre=datetime.now(timezone.utc),
                       ts_post=datetime.now(timezone.utc),
                       pre_dir=pre, post_dir=post)
    assert pair.file_count_delta == -1
    assert pair.line_count_delta < 0
    # Reload from jsonl.
    items = history()
    assert any(p.pair_id == pair_id for p in items)
