"""Tests for memory CRUD orchestration (memory.py)."""

from memento import memory, wiki, index


class TestStore:
    def test_store_creates_file_and_index(self):
        mem = memory.store("tattoo", "chest", "arch", "Use PostgreSQL", "DB")
        assert mem.path.exists()
        results = index.search("PostgreSQL")
        assert len(results) == 1

    def test_store_extracts_inline_tags(self):
        mem = memory.store("note", "hand", "todo", "Fix #auth before deploy")
        assert "auth" in mem.tags


class TestRecall:
    def test_recall_reads_file(self):
        mem = memory.store("note", "hand", "todo", "Buy milk")
        fetched = memory.recall(mem.id)
        assert fetched.content == "Buy milk"

    def test_recall_nonexistent(self):
        assert memory.recall("nonexistent") is None


class TestUpdate:
    def test_update_rewrites_file_and_index(self):
        mem = memory.store("note", "hand", "todo", "Old")
        updated = memory.update(mem.id, content="New")
        assert updated.content == "New"
        fetched = memory.recall(mem.id)
        assert fetched.content == "New"
        results = index.search("New")
        assert len(results) == 1


class TestBurn:
    def test_burn_note(self):
        mem = memory.store("note", "hand", "todo", "Burn me")
        assert memory.burn(mem.id) is True
        assert memory.recall(mem.id) is None

    def test_burn_tattoo_fails(self):
        mem = memory.store("tattoo", "chest", "core", "Permanent")
        assert memory.burn(mem.id) is False
        assert memory.recall(mem.id) is not None


class TestListAndQuery:
    def test_list_contexts(self):
        memory.store("tattoo", "chest", "a", "x")
        memory.store("note", "hand", "b", "y")
        assert "chest" in memory.list_contexts()
        assert "hand" in memory.list_contexts()

    def test_list_topics(self):
        memory.store("tattoo", "chest", "arch", "x")
        assert "arch" in memory.list_topics("chest")

    def test_get_topic(self):
        memory.store("note", "hand", "todo", "T1")
        memory.store("note", "hand", "todo", "T2")
        results = memory.get_topic("hand", "todo")
        assert len(results) == 2

    def test_examine_tattoos(self):
        memory.store("tattoo", "chest", "a", "x")
        memory.store("note", "hand", "b", "y")
        tattoos = memory.examine_tattoos()
        assert len(tattoos) == 1
        assert tattoos[0].kind == "tattoo"

    def test_summarize_topic(self):
        memory.store("tattoo", "chest", "core", "F1", tags=["a"])
        memory.store("note", "chest", "core", "N1", tags=["b"])
        summary = memory.summarize_topic("chest", "core")
        assert summary["memory_count"] == 2
        assert "a" in summary["tags"]
        assert "b" in summary["tags"]
