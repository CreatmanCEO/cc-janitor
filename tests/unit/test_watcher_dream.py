from datetime import datetime, timezone
from pathlib import Path
from cc_janitor.core.dream_snapshot import LockState, history
from cc_janitor.core.watcher import run_dream_once


def test_run_dream_once_appears_then_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\n")
    state = LockState()
    pending: dict = {}

    # No lock yet.
    run_dream_once([mem], state, pending)
    assert not pending

    # Lock appears.
    (mem / ".consolidate-lock").write_text("4711")
    run_dream_once([mem], state, pending)
    assert mem in pending
    pair_id = pending[mem]["pair_id"]
    assert (tmp_path / "jhome" / "backups" / "dream" / f"{pair_id}-pre").exists()

    # Lock disappears + content changed.
    (mem / "MEMORY.md").write_text("a\nb\n")
    (mem / ".consolidate-lock").unlink()
    run_dream_once([mem], state, pending)
    assert mem not in pending
    h = history()
    assert any(p.pair_id == pair_id for p in h)
