"""Tests for ``cc-janitor backups tar-compact`` + ``dream-tar-compact`` template."""
from __future__ import annotations

import os
import tarfile
import time

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_tar_compact_archives_old_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    dream = tmp_path / "jhome" / "backups" / "dream"
    pre = dream / "20260401T000000Z-old-pre"
    post = dream / "20260401T000000Z-old-post"
    pre.mkdir(parents=True)
    post.mkdir(parents=True)
    (pre / "MEMORY.md").write_text("a\n", encoding="utf-8")
    (post / "MEMORY.md").write_text("b\n", encoding="utf-8")
    old = time.time() - 30 * 86400
    for d in (pre, post):
        for f in d.rglob("*"):
            os.utime(f, (old, old))
        os.utime(d, (old, old))

    res = runner.invoke(
        app,
        ["backups", "tar-compact", "--kind", "dream",
         "--older-than-days", "7", "--apply"],
    )
    assert res.exit_code == 0, res.output
    tars = list(dream.glob("*.tar.gz"))
    assert len(tars) == 1
    with tarfile.open(tars[0]) as tf:
        names = tf.getnames()
        assert any("pre/MEMORY.md" in n for n in names)
        assert any("post/MEMORY.md" in n for n in names)
    # Raw mirrors removed.
    assert not pre.exists()
    assert not post.exists()


def test_tar_compact_skips_recent_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    dream = tmp_path / "jhome" / "backups" / "dream"
    pre = dream / "20260510T000000Z-new-pre"
    post = dream / "20260510T000000Z-new-post"
    pre.mkdir(parents=True)
    post.mkdir(parents=True)
    (pre / "MEMORY.md").write_text("a\n", encoding="utf-8")
    (post / "MEMORY.md").write_text("b\n", encoding="utf-8")

    res = runner.invoke(
        app,
        ["backups", "tar-compact", "--kind", "dream",
         "--older-than-days", "7", "--apply"],
    )
    assert res.exit_code == 0, res.output
    assert list(dream.glob("*.tar.gz")) == []
    assert pre.exists() and post.exists()


def test_tar_compact_dry_run_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    dream = tmp_path / "jhome" / "backups" / "dream"
    pre = dream / "20260401T000000Z-old-pre"
    post = dream / "20260401T000000Z-old-post"
    pre.mkdir(parents=True)
    post.mkdir(parents=True)
    (pre / "MEMORY.md").write_text("a\n", encoding="utf-8")
    (post / "MEMORY.md").write_text("b\n", encoding="utf-8")
    old = time.time() - 30 * 86400
    for d in (pre, post):
        for f in d.rglob("*"):
            os.utime(f, (old, old))
        os.utime(d, (old, old))

    res = runner.invoke(
        app,
        ["backups", "tar-compact", "--kind", "dream",
         "--older-than-days", "7"],
    )
    assert res.exit_code == 0, res.output
    assert "dry-run" in res.output.lower()
    assert pre.exists()
    assert list(dream.glob("*.tar.gz")) == []


def test_dream_tar_compact_template_registered():
    from cc_janitor.core.schedule import TEMPLATES

    assert "dream-tar-compact" in TEMPLATES
    tpl = TEMPLATES["dream-tar-compact"]
    assert "command" in tpl
    assert "default_cron" in tpl
    assert "tar-compact" in tpl["command"]
    assert "--kind" in tpl["command"]
    assert "--apply" in tpl["command"]
