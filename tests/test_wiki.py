"""Tests for the markdown wiki layer (wiki.py)."""

from pathlib import Path

import pytest

from memento import wiki


class TestWriteAndRead:
    def test_write_tattoo(self):
        mem = wiki.write_memory("tattoo", "chest", "architecture", "Use PostgreSQL", "DB Choice")
        assert mem.path.exists()
        assert mem.path.suffix == ".md"
        text = mem.path.read_text()
        assert "---" in text
        assert "Use PostgreSQL" in text
        assert "tattoo" in text

    def test_read_memory_roundtrip(self):
        mem = wiki.write_memory("note", "hand", "todo", "Buy milk", title="Shopping")
        read = wiki.read_memory(mem.path)
        assert read.id == mem.id
        assert read.kind == "note"
        assert read.content == "Buy milk"
        assert read.title == "Shopping"

    def test_frontmatter_parsing(self):
        mem = wiki.write_memory(
            "polaroid", "left_arm", "bugs", "Error 500",
            caption="Server crashed", title="500 Error", tags=["critical"],
            certainty=0.8,
        )
        read = wiki.read_memory(mem.path)
        assert read.caption == "Server crashed"
        assert read.certainty == 0.8
        assert "critical" in read.tags

    def test_nested_topic_directory(self):
        mem = wiki.write_memory("tattoo", "chest", "project/setup", "Use Docker")
        assert "project" in str(mem.path)
        assert "setup" in str(mem.path)
        assert mem.path.exists()

    def test_duplicate_slug_auto_increments(self):
        m1 = wiki.write_memory("note", "hand", "todo", "First note", title="Note")
        m2 = wiki.write_memory("note", "hand", "todo", "Second note", title="Note")
        assert m1.slug == "note"
        assert m2.slug == "note-1"
        assert m1.path != m2.path


class TestFindAndList:
    def test_find_memory_by_id(self):
        mem = wiki.write_memory("note", "hand", "todo", "Find me")
        found = wiki.find_memory(mem.id)
        assert found == mem.path

    def test_find_nonexistent(self):
        assert wiki.find_memory("nonexistent") is None

    def test_list_contexts(self):
        wiki.write_memory("tattoo", "chest", "a", "x")
        wiki.write_memory("note", "hand", "b", "y")
        contexts = wiki.list_contexts()
        assert "chest" in contexts
        assert "hand" in contexts

    def test_list_topics(self):
        wiki.write_memory("tattoo", "chest", "architecture", "x")
        wiki.write_memory("note", "chest", "setup", "y")
        topics = wiki.list_topics("chest")
        assert "architecture" in topics
        assert "setup" in topics

    def test_get_memories(self):
        wiki.write_memory("note", "hand", "todo", "Task 1")
        wiki.write_memory("note", "hand", "todo", "Task 2")
        results = wiki.get_memories("hand", "todo")
        assert len(results) == 2

    def test_scan_wiki(self):
        wiki.write_memory("note", "hand", "todo", "A")
        wiki.write_memory("tattoo", "chest", "core", "B")
        all_mems = wiki.scan_wiki()
        assert len(all_mems) == 2


class TestDelete:
    def test_delete_memory(self):
        mem = wiki.write_memory("note", "hand", "todo", "Burn me")
        assert mem.path.exists()
        wiki.delete_memory(mem.id)
        assert not mem.path.exists()

    def test_delete_cleans_empty_dirs(self):
        mem = wiki.write_memory("note", "hand", "deep/nested", "Content")
        path = mem.path
        wiki.delete_memory(mem.id)
        # Parent dirs should be cleaned up
        assert not path.parent.exists()


class TestUpdate:
    def test_update_content(self):
        mem = wiki.write_memory("note", "hand", "todo", "Old")
        updated = wiki.update_memory(mem.id, content="New")
        assert updated.content == "New"
        assert updated.path is not None
        read = wiki.read_memory(updated.path)
        assert read.content == "New"

    def test_update_moves_file_when_topic_changes(self):
        mem = wiki.write_memory("note", "hand", "old-topic", "Content")
        old_path = mem.path
        updated = wiki.update_memory(mem.id, topic="new-topic")
        assert not old_path.exists()
        assert updated.path.exists()
        assert "newtopic" in str(updated.path)

    def test_update_sets_path_even_without_move(self):
        mem = wiki.write_memory("note", "hand", "todo", "Content")
        updated = wiki.update_memory(mem.id, title="New Title")
        assert updated.path is not None
        assert updated.path.exists()

    def test_tattoo_content_immutable(self):
        mem = wiki.write_memory("tattoo", "chest", "core", "Original fact")
        with pytest.raises(ValueError, match="content cannot be changed"):
            wiki.update_memory(mem.id, content="Changed fact")

    def test_tattoo_context_immutable(self):
        mem = wiki.write_memory("tattoo", "chest", "core", "Fact")
        with pytest.raises(ValueError, match="context cannot be changed"):
            wiki.update_memory(mem.id, context="hand")

    def test_tattoo_topic_immutable(self):
        mem = wiki.write_memory("tattoo", "chest", "core", "Fact")
        with pytest.raises(ValueError, match="topic cannot be changed"):
            wiki.update_memory(mem.id, topic="new-topic")

    def test_tattoo_title_can_update(self):
        mem = wiki.write_memory("tattoo", "chest", "core", "Fact", title="Old")
        updated = wiki.update_memory(mem.id, title="New Title")
        assert updated.title == "New Title"

    def test_tattoo_tags_can_update(self):
        mem = wiki.write_memory("tattoo", "chest", "core", "Fact", tags=["a"])
        updated = wiki.update_memory(mem.id, tags=["a", "b"])
        assert "b" in updated.tags


class TestCertainty:
    def test_certainty_clamped_on_write(self):
        mem = wiki.write_memory("note", "hand", "todo", "X", certainty=5.0)
        assert mem.certainty == 1.0

    def test_certainty_clamped_negative(self):
        mem = wiki.write_memory("note", "hand", "todo", "X", certainty=-1.0)
        assert mem.certainty == 0.0

    def test_certainty_clamped_on_update(self):
        mem = wiki.write_memory("note", "hand", "todo", "X")
        updated = wiki.update_memory(mem.id, certainty=2.5)
        assert updated.certainty == 1.0


class TestHelpers:
    def test_parse_links(self):
        assert wiki.parse_links("See [[a/b]] and [[c]]") == ["a/b", "c"]

    def test_parse_inline_tags(self):
        assert wiki.parse_inline_tags("Fix #auth and #deploy") == ["auth", "deploy"]
        assert wiki.parse_inline_tags("Color #ff0000") == []  # hex excluded

    def test_slugify(self):
        assert wiki._slugify("Hello World!") == "hello-world"
