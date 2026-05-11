from __future__ import annotations

import pytest

from cc_janitor.core.bundle import export_bundle, import_bundle
from cc_janitor.core.safety import NotConfirmedError


def test_import_requires_confirmed(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    with pytest.raises(NotConfirmedError):
        import_bundle(out, dry_run=True, force=False)


def test_import_dry_run_does_not_write(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    target = mock_claude_home / ".claude" / "CLAUDE.md"
    target.write_text("DIFFERENT", encoding="utf-8")
    plan = import_bundle(out, dry_run=True, force=False)
    assert plan["would_write"] >= 1
    assert plan["written"] == 0
    assert target.read_text(encoding="utf-8") == "DIFFERENT"


def test_import_force_writes_and_backups(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    target = mock_claude_home / ".claude" / "CLAUDE.md"
    original = target.read_text(encoding="utf-8")
    target.write_text("DIFFERENT", encoding="utf-8")
    res = import_bundle(out, dry_run=False, force=True)
    assert res["written"] >= 1
    assert target.read_text(encoding="utf-8") == original
    assert any(res["backups"])
    # backup file should contain the pre-overwrite content
    from pathlib import Path
    bp = Path(res["backups"][0])
    assert bp.exists()
    assert bp.read_text(encoding="utf-8") == "DIFFERENT"


def test_import_skips_identical(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    # No tampering — destination matches bundle.
    res = import_bundle(out, dry_run=False, force=True)
    assert res["written"] == 0
    assert res["would_write"] == 0


def test_import_refuses_on_corrupt_archive(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bad.tar.gz"
    export_bundle(out, include_memory=False)
    raw = out.read_bytes()
    out2 = tmp_path / "tampered.tar.gz"
    # Corrupt the gzip stream in the middle.
    out2.write_bytes(raw[:100] + b"\x00" * 50 + raw[150:])
    with pytest.raises(Exception):  # noqa: B017 — corrupt bundle may raise various types
        import_bundle(out2, dry_run=False, force=True)


def test_import_refuses_on_sha_mismatch(mock_claude_home, tmp_path, monkeypatch):
    """Build a tar where manifest claims a sha but actual member differs."""
    import io
    import json
    import tarfile

    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "evil.tar.gz"
    # manifest references CLAUDE.md with a wrong sha
    manifest = {
        "version": 1,
        "exported_at": "2026-01-01T00:00:00+00:00",
        "host": "evil",
        "cc_janitor_version": "0.3.0.dev0",
        "files": [
            {
                "path": "/x",
                "arcname": "claude/CLAUDE.md",
                "sha256": "0" * 64,
                "kind": "claude_md",
                "size": 5,
            }
        ],
    }
    payload = b"hello"
    with tarfile.open(out, "w:gz") as tar:
        mb = json.dumps(manifest).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(mb)
        tar.addfile(info, io.BytesIO(mb))
        info = tarfile.TarInfo("claude/CLAUDE.md")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="SHA mismatch"):
        import_bundle(out, dry_run=False, force=True)


def test_import_rejects_unknown_version(mock_claude_home, tmp_path, monkeypatch):
    import io
    import json
    import tarfile

    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "v99.tar.gz"
    manifest = {"version": 99, "files": []}
    with tarfile.open(out, "w:gz") as tar:
        mb = json.dumps(manifest).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(mb)
        tar.addfile(info, io.BytesIO(mb))
    with pytest.raises(ValueError, match="Unsupported bundle version"):
        import_bundle(out, dry_run=False, force=True)
