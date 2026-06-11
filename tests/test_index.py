"""Tests for the rebuildable search index (index.py)."""

from memento import wiki, index


class TestIndexLifecycle:
    def test_index_and_search(self):
        mem = wiki.write_memory("tattoo", "chest", "arch", "Use PostgreSQL for production")
        index.index_memory(mem, mem.path)
        results = index.search("PostgreSQL")
        assert len(results) == 1
        assert results[0].id == mem.id

    def test_deindex_removes_from_search(self):
        mem = wiki.write_memory("note", "hand", "todo", "Temporary task")
        index.index_memory(mem, mem.path)
        index.deindex_memory(mem.id)
        results = index.search("Temporary")
        assert len(results) == 0

    def test_rebuild_index(self):
        wiki.write_memory("tattoo", "chest", "a", "Fact A")
        wiki.write_memory("note", "hand", "b", "Note B")
        stats = index.rebuild_index()
        assert stats["indexed_entries"] == 2
        results = index.search("Fact")
        assert len(results) == 1

    def test_search_with_kind_filter(self):
        wiki.write_memory("tattoo", "chest", "a", "PostgreSQL")
        wiki.write_memory("note", "hand", "b", "PostgreSQL")
        index.rebuild_index()
        results = index.search("PostgreSQL", kind="tattoo")
        assert len(results) == 1
        assert results[0].kind == "tattoo"

    def test_search_with_context_filter(self):
        wiki.write_memory("tattoo", "chest", "a", "Content")
        wiki.write_memory("note", "hand", "b", "Content")
        index.rebuild_index()
        results = index.search("Content", context="chest")
        assert len(results) == 1
        assert results[0].context == "chest"

    def test_search_no_results(self):
        index.rebuild_index()
        results = index.search("xyznonexistent")
        assert results == []


class TestLinksAndBacklinks:
    def test_backlinks(self):
        target = wiki.write_memory("tattoo", "chest", "core", "Core API")
        source = wiki.write_memory("note", "hand", "todo", f"See [[{target.slug}]]")
        index.rebuild_index()
        backlinks = index.get_backlinks(target.id)
        assert len(backlinks) == 1
        assert backlinks[0]["memory_id"] == source.id

    def test_resolve_link_by_slug(self):
        mem = wiki.write_memory("tattoo", "chest", "core", "Important", title="Important")
        index.rebuild_index()
        resolved = index.resolve_link(mem.slug)
        assert resolved is not None
        assert resolved.id == mem.id

    def test_resolve_link_not_found(self):
        index.rebuild_index()
        assert index.resolve_link("nonexistent") is None


class TestTags:
    def test_tags_indexed(self):
        mem = wiki.write_memory("note", "hand", "todo", "Task", tags=["urgent", "bug"])
        index.index_memory(mem, mem.path)
        tags = index.get_tags_for_entry(mem.id)
        assert "urgent" in tags
        assert "bug" in tags

    def test_search_by_tags(self):
        mem = wiki.write_memory("note", "hand", "todo", "Task", tags=["urgent"])
        index.index_memory(mem, mem.path)
        results = index.search("Task", tags=["urgent"])
        assert len(results) == 1


class TestStats:
    def test_index_stats(self):
        wiki.write_memory("tattoo", "chest", "a", "x")
        index.rebuild_index()
        stats = index.index_stats()
        assert stats["entries"] == 1


class TestMultiKeywordSearch:
    """Multi-keyword queries must match non-adjacent, out-of-order words.

    Regression: queries used to be wrapped in ONE phrase, so
    'redis refused' returned 0 hits against 'Redis connection refused'.
    """

    def test_keywords_match_non_adjacent_words(self):
        mem = wiki.write_memory(
            "polaroid", "left_arm", "errors", "Redis connection refused on port 6379"
        )
        index.index_memory(mem, mem.path)
        assert len(index.search("redis refused")) == 1

    def test_keywords_match_out_of_order(self):
        mem = wiki.write_memory(
            "polaroid", "left_arm", "errors", "Redis connection refused on port 6379"
        )
        index.index_memory(mem, mem.path)
        assert len(index.search("refused redis")) == 1

    def test_keywords_are_anded(self):
        mem = wiki.write_memory("note", "hand", "todo", "Redis cache layer")
        index.index_memory(mem, mem.path)
        assert len(index.search("redis nonexistentword")) == 0

    def test_explicit_phrase_preserved(self):
        a = wiki.write_memory("note", "hand", "todo", "connection refused error")
        b = wiki.write_memory("note", "hand", "todo", "refused the connection politely")
        index.index_memory(a, a.path)
        index.index_memory(b, b.path)
        results = index.search('"connection refused"')
        assert len(results) == 1
        assert results[0].id == a.id

    def test_empty_query_returns_empty(self):
        assert index.search("") == []
        assert index.search("   ") == []

    def test_injection_chars_are_safe(self):
        mem = wiki.write_memory("note", "hand", "todo", "some content")
        index.index_memory(mem, mem.path)
        # None of these should raise a MATCH syntax error
        index.search("col:value")
        index.search("a AND b OR c NOT d")
        index.search("weird-chars *star (paren)")
        index.search('"unbalanced quote')


class TestRebuildResilience:
    def test_rebuild_skips_duplicate_ids(self):
        """Duplicate frontmatter ids must not crash the rebuild (server boot)."""
        mem = wiki.write_memory("tattoo", "chest", "core", "Original fact")
        dup = mem.path.with_name(mem.path.stem + ".imported.md")
        dup.write_text(mem.path.read_text(encoding="utf-8"), encoding="utf-8")

        stats = index.rebuild_index()  # must not raise IntegrityError
        assert stats["indexed_entries"] == 1
        assert len(stats.get("skipped_files", [])) == 1

    def test_rebuild_skips_missing_id(self):
        wiki.ensure_wiki()
        bad = wiki.WIKI_ROOT / "chest" / "core"
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "no-id.md").write_text(
            "---\nkind: note\n---\n\nbody without id\n", encoding="utf-8"
        )
        stats = index.rebuild_index()  # must not raise
        assert stats["indexed_entries"] == 0
