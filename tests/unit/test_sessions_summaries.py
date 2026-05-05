def test_enrich_with_indexer_summaries(mock_claude_home):
    from cc_janitor.core.sessions import discover_sessions, enrich_with_indexer_summaries
    sessions = discover_sessions()
    enriched = enrich_with_indexer_summaries(
        sessions,
        indexer_root=mock_claude_home / "Conversations" / "claude-code",
    )
    target = next((s for s in enriched if s.id == "def456"), None)
    assert target is not None
    md_summaries = [x for x in target.summaries if x.source == "user_indexer_md"]
    assert len(md_summaries) == 1


def test_enrich_no_indexer_dir_is_noop(mock_claude_home, tmp_path):
    from cc_janitor.core.sessions import discover_sessions, enrich_with_indexer_summaries
    sessions = discover_sessions()
    before_summaries = [len(s.summaries) for s in sessions]
    enriched = enrich_with_indexer_summaries(
        sessions, indexer_root=tmp_path / "nonexistent",
    )
    after_summaries = [len(s.summaries) for s in enriched]
    assert before_summaries == after_summaries
