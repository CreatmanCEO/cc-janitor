from pathlib import Path
from cc_janitor.core.config import (
    Config, DreamDoctorConfig, SnapshotsConfig, HygieneConfig,
    load_config, DEFAULTS,
)


def test_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.dream_doctor.disk_warning_mb == 100
    assert cfg.dream_doctor.memory_file_count_threshold == 50
    assert cfg.dream_doctor.memory_md_line_threshold == 180
    assert cfg.snapshots.raw_retention_days == 7
    assert cfg.snapshots.tar_retention_days == 30


def test_partial_override(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[dream_doctor]\n'
        'disk_warning_mb = 500\n'
        '[snapshots]\n'
        'raw_retention_days = 14\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.dream_doctor.disk_warning_mb == 500
    assert cfg.dream_doctor.memory_md_line_threshold == 180  # default kept
    assert cfg.snapshots.raw_retention_days == 14
    assert cfg.snapshots.tar_retention_days == 30


def test_malformed_falls_back_to_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("this is not [valid toml", encoding="utf-8")
    cfg = load_config(p)
    assert cfg == DEFAULTS


def test_extra_relative_date_terms(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[hygiene]\n'
        'relative_date_terms_extra = ["позавчера", "tomorrow"]\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert "позавчера" in cfg.hygiene.relative_date_terms_extra
