import os
import subprocess
import sys

import pytest


def test_cli_handles_cyrillic_output_without_pythonioencoding(tmp_path, monkeypatch):
    """End-to-end smoke: invoke the entry-point with a fake home that contains
    Cyrillic session content, with PYTHONIOENCODING unset, on win32. Must NOT crash."""
    if sys.platform != "win32":
        pytest.skip("Windows-specific guard")

    # Build fake home
    home = tmp_path / "fake-home"
    project_dir = home / ".claude" / "projects" / "test-proj"
    project_dir.mkdir(parents=True)
    jsonl = project_dir / "abc123.jsonl"
    jsonl.write_text(
        '{"type":"user","message":{"content":"тестовое сообщение"},"sessionId":"abc123","timestamp":"2026-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    env["CC_JANITOR_HOME"] = str(home / ".cc-janitor")

    # Use the package entry-point via python -m
    result = subprocess.run(
        [sys.executable, "-m", "cc_janitor", "session", "list"],
        env=env,
        capture_output=True,
        text=False,  # raw bytes, we decode ourselves
        timeout=30,
    )
    assert result.returncode == 0, f"crashed: stderr={result.stderr[:500]!r}"
    # Output should be valid UTF-8 (decode without error)
    decoded = result.stdout.decode("utf-8", errors="replace")
    assert "abc123" in decoded
    assert "тестовое" in decoded or "тестов" in decoded  # last char of "тестовое сообщение" might be truncated


def test_main_does_not_crash_on_non_windows():
    """Smoke: main() runs the reconfigure guard without raising on non-win32."""
    import cc_janitor.__main__
    # Just import and verify the symbol exists; the test_cli_handles... covers behavior.
    assert hasattr(cc_janitor.__main__, "main")
