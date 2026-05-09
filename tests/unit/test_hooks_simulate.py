import sys

from cc_janitor.core.hooks import build_stdin_payload, simulate_hook


def test_build_stdin_pretooluse():
    payload = build_stdin_payload("PreToolUse", tool_name="Bash")
    assert '"hook_event_name": "PreToolUse"' in payload
    assert '"tool_name": "Bash"' in payload


def test_simulate_runs_command(tmp_path, monkeypatch):
    # Use call operator on Windows to handle paths with spaces/unicode
    if sys.platform == "win32":
        cmd = (
            f'& "{sys.executable}" -c '
            f'"import sys; sys.stdout.write(sys.stdin.read())"'
        )
    else:
        cmd = (
            f'{sys.executable} -c '
            f'"import sys; sys.stdout.write(sys.stdin.read())"'
        )
    result = simulate_hook(cmd, event="PreToolUse", matcher="Bash", timeout=10)
    assert result.exit_code == 0, f"stderr={result.stderr}"
    assert "PreToolUse" in result.stdout
    assert result.duration_ms >= 0
