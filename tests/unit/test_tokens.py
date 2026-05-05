from cc_janitor.core.tokens import count_file_tokens, count_tokens


def test_count_tokens_basic():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0


def test_count_file_tokens(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\n\nSome words here.\n", encoding="utf-8")
    assert count_file_tokens(f) > 0
