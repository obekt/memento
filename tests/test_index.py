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
