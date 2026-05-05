# tests/conftest.py
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data" / "mock-claude-home"


@pytest.fixture
def mock_claude_home(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "mock-claude-home"
    shutil.copytree(DATA, target)
    monkeypatch.setenv("HOME", str(target))
    monkeypatch.setenv("USERPROFILE", str(target))  # Windows
    monkeypatch.setenv("CC_JANITOR_HOME", str(target / ".cc-janitor"))
    return target
