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


class TestConcurrency:
    def test_concurrent_index_writes(self):
        """Concurrent index mutations must not raise 'database is locked'
        or desync the FTS index (WAL + busy_timeout + BEGIN IMMEDIATE)."""
        import threading

        mems = [
            wiki.write_memory("note", "hand", "todo", f"unique{i} concurrent body")
            for i in range(8)
        ]
        errors: list[Exception] = []

        def work(m):
            try:
                for _ in range(5):
                    index.index_memory(m, m.path)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=work, args=(m,)) for m in mems]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # FTS must be in sync: every memory findable, exactly once
        for i in range(8):
            assert len(index.search(f"unique{i}")) == 1

    def test_wal_mode_enabled(self):
        index.init_index()
        conn = index._connect()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode.lower() == "wal"


class TestLinkLifecycle:
    def test_delete_invalidates_inbound_backlinks(self):
        """Deleting a memory must not leave inbound links 'resolved' to a dead id."""
        from memento import memory as memory_mod

        target = memory_mod.store("note", "chest", "core", "Core API doc")
        source = memory_mod.store("note", "hand", "todo", f"See [[{target.slug}]]")

        memory_mod.burn(target.id)

        assert index.get_backlinks(target.id) == []
        links = index.get_linked_entries(source.id)
        assert len(links) == 1
        assert links[0]["resolved"] is False

    def test_forward_reference_resolves_when_target_created(self):
        """A [[link]] to a memory created LATER must resolve without a rebuild."""
        from memento import memory as memory_mod

        source = memory_mod.store("note", "hand", "todo", "See [[future-doc]]")
        links = index.get_linked_entries(source.id)
        assert links[0]["resolved"] is False

        target = memory_mod.store(
            "note", "chest", "core", "the future doc", slug="future-doc"
        )
        links = index.get_linked_entries(source.id)
        assert links[0]["resolved"] is True
        assert links[0]["memory_id"] == target.id


class TestExternalEditSync:
    def test_sync_if_stale_picks_up_vim_edit(self):
        """Editing a file outside Memento must be searchable after sync_if_stale."""
        import os
        from memento import memory as memory_mod

        mem = memory_mod.store("note", "hand", "todo", "original searchable body")
        index.sync_if_stale()  # settle the signature

        # Simulate a vim edit: change content directly on disk
        text = mem.path.read_text(encoding="utf-8").replace(
            "original searchable body", "externally edited zanzibar"
        )
        mem.path.write_text(text, encoding="utf-8")
        # Bump mtime well past filesystem granularity
        st = mem.path.stat()
        os.utime(mem.path, (st.st_atime, st.st_mtime + 10))

        assert index.sync_if_stale() is True
        assert len(index.search("zanzibar")) == 1
        assert len(index.search("original searchable")) == 0

    def test_sync_if_stale_noop_when_unchanged(self):
        from memento import memory as memory_mod

        memory_mod.store("note", "hand", "todo", "stable content")
        index.sync_if_stale()
        assert index.sync_if_stale() is False

    def test_sync_if_stale_picks_up_new_file(self):
        index.sync_if_stale()
        d = wiki.WIKI_ROOT / "chest" / "core"
        d.mkdir(parents=True, exist_ok=True)
        (d / "manual.md").write_text(
            "---\nid: manual-id-1\nkind: note\ncontext: chest\ntopic: core\n---\n\nmanually created xylophone\n",
            encoding="utf-8",
        )
        assert index.sync_if_stale() is True
        assert len(index.search("xylophone")) == 1
