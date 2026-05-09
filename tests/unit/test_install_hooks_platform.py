from __future__ import annotations

from cc_janitor.cli.commands.install_hooks import _build_hook_command


def test_posix_hook_command():
    cmd = _build_hook_command("linux")
    assert "test -f" in cmd
    assert "rm" in cmd


def test_windows_hook_command():
    cmd = _build_hook_command("win32")
    assert "powershell" in cmd.lower()
    assert "Test-Path" in cmd
    assert "Remove-Item" in cmd
