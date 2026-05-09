import pytest

from cc_janitor.core.safety import RunawayCapError, reset_run_counter, soft_delete
from cc_janitor.core.state import Paths


def test_hard_cap_when_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    monkeypatch.setenv("CC_JANITOR_SCHEDULED", "1")
    monkeypatch.setenv("CC_JANITOR_HARD_CAP", "3")
    reset_run_counter()
    paths = Paths(home=tmp_path / ".cc-janitor")
    paths.ensure_dirs()
    for i in range(3):
        f = tmp_path / f"v{i}.txt"
        f.write_text("x")
        soft_delete(f, paths=paths)
    f4 = tmp_path / "v3.txt"
    f4.write_text("x")
    with pytest.raises(RunawayCapError):
        soft_delete(f4, paths=paths)


def test_no_cap_when_not_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    monkeypatch.delenv("CC_JANITOR_SCHEDULED", raising=False)
    monkeypatch.setenv("CC_JANITOR_HARD_CAP", "1")
    reset_run_counter()
    paths = Paths(home=tmp_path / ".cc-janitor")
    paths.ensure_dirs()
    for i in range(5):
        f = tmp_path / f"v{i}.txt"
        f.write_text("x")
        soft_delete(f, paths=paths)  # no cap
