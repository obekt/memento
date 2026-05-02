"""Tests for search and graph queries (search.py)."""

from memento import memory, search, index


class TestSearchMemories:
    def test_basic_search(self):
        memory.store("tattoo", "chest", "arch", "Use PostgreSQL")
        results = search.search_memories("PostgreSQL")
        assert len(results) >= 1

    def test_search_with_filters(self):
        memory.store("tattoo", "chest", "arch", "PostgreSQL")
        memory.store("note", "hand", "todo", "PostgreSQL")
        results = search.search_memories("PostgreSQL", kind="tattoo")
        assert len(results) == 1
        assert results[0].kind == "tattoo"

    def test_search_no_results(self):
        results = search.search_memories("xyznonexistent123")
        assert results == []


class TestWakeUp:
    def test_wake_up_returns_all_kinds(self):
        memory.store("tattoo", "chest", "core", "Fact")
        memory.store("polaroid", "left_arm", "bug", "Error", caption="Fix")
        memory.store("note", "hand", "todo", "Task")
        report = search.wake_up(limit=5)
        assert len(report["tattoos"]) == 1
        assert len(report["polaroids"]) == 1
        assert len(report["notes"]) == 1


class TestReverseTimeline:
    def test_order(self):
        m1 = memory.store("note", "hand", "todo", "First")
        m2 = memory.store("note", "hand", "todo", "Second")
        results = search.reverse_timeline(limit=2)
        assert results[0].id == m1.id
        assert results[1].id == m2.id


class TestSammyJankisTest:
    def test_finds_similar(self):
        memory.store("note", "hand", "bugs", "Redis connection failed")
        results = search.sammy_jankis_test("Redis")
        assert len(results) >= 1

    def test_no_results(self):
        results = search.sammy_jankis_test("xyzabc")
        assert results == []


class TestLinks:
    def test_follow_link(self):
        target = memory.store("tattoo", "chest", "core", "API", title="API")
        index.rebuild_index()
        resolved = search.resolve_link(target.slug)
        assert resolved is not None
        assert resolved.id == target.id

    def test_get_backlinks(self):
        target = memory.store("tattoo", "chest", "core", "Core")
        source = memory.store("note", "hand", "todo", f"See [[{target.slug}]]")
        index.rebuild_index()
        backlinks = search.get_backlinks(target.id)
        assert len(backlinks) == 1
