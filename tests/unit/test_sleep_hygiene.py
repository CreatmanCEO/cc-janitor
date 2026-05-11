from cc_janitor.core.sleep_hygiene import (
    _extract_contradiction_subjects,
    _scan_relative_dates,
)


def test_relative_date_density_finds_en_and_ru(tmp_path):
    f = tmp_path / "x.md"
    f.write_text(
        "yesterday we did X\nна прошлой неделе also Y\nstable text\n",  # noqa: RUF001
        encoding="utf-8",
    )
    matches = _scan_relative_dates([f], extra_terms=())
    terms = {m[2] for m in matches}
    assert "yesterday" in terms
    assert "на прошлой неделе" in terms


def test_contradiction_extraction(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("never use openai apis directly\n", encoding="utf-8")
    b.write_text("always use openai apis for embeddings\n", encoding="utf-8")
    pairs = _extract_contradiction_subjects([a, b], jaccard_threshold=0.5)
    assert pairs
    subj, files = pairs[0]
    assert "openai" in subj.lower()
    assert len(files) >= 2
