from __future__ import annotations

import hashlib
import json
import tarfile

from cc_janitor.core.bundle import export_bundle


def test_export_creates_tar_with_manifest(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    n = export_bundle(out, include_memory=False)
    assert out.exists() and n >= 1
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        m = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        assert m["version"] == 1
        assert all("sha256" in f for f in m["files"])


def test_export_excludes_settings_local(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=True)
    with tarfile.open(out, "r:gz") as tar:
        for name in tar.getnames():
            assert "settings.local.json" not in name


def test_export_sha256_matches(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    with tarfile.open(out, "r:gz") as tar:
        m = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        for entry in m["files"]:
            member = tar.extractfile(entry["arcname"])
            data = member.read()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_export_includes_claude_md(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    with tarfile.open(out, "r:gz") as tar:
        assert "claude/CLAUDE.md" in tar.getnames()


def test_export_include_memory_flag(mock_claude_home, tmp_path):
    out_no = tmp_path / "no.tar.gz"
    out_yes = tmp_path / "yes.tar.gz"
    export_bundle(out_no, include_memory=False)
    export_bundle(out_yes, include_memory=True)
    with tarfile.open(out_no, "r:gz") as tar:
        no_names = tar.getnames()
    with tarfile.open(out_yes, "r:gz") as tar:
        yes_names = tar.getnames()
    # memory files only show up when include_memory=True
    assert not any("/memory/" in n for n in no_names)
    assert any("/memory/" in n for n in yes_names)
