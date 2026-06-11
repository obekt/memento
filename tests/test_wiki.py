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
        assert "new-topic" in str(updated.path)

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


class TestPathSafety:
    """context/topic must never escape the wiki root.

    Path.home() / "/tmp/evil" silently resolves to /tmp/evil, so
    _safe_dir_name must strip absolute paths and `..` segments.
    """

    def test_absolute_context_stays_in_wiki(self):
        mem = wiki.write_memory("note", "/tmp/evil", "topic", "content")
        assert wiki.WIKI_ROOT in mem.path.parents

    def test_dotdot_context_stays_in_wiki(self):
        mem = wiki.write_memory("note", "../escape", "topic", "content")
        assert wiki.WIKI_ROOT in mem.path.parents
        assert ".." not in mem.path.parts

    def test_dotdot_topic_stays_in_wiki(self):
        mem = wiki.write_memory("note", "ctx", "../../escape", "content")
        assert wiki.WIKI_ROOT in mem.path.parents
        assert ".." not in mem.path.parts

    def test_empty_context_gets_default(self):
        assert wiki._safe_dir_name("///") == "default"
        assert wiki._safe_dir_name("..") == "default"

    def test_normal_names_unchanged(self):
        assert wiki._safe_dir_name("chest") == "chest"
        assert wiki._safe_dir_name("left arm") == "left-arm"
        assert wiki._safe_dir_name("a/b/c") == "a/b/c"


class TestMoveDoesNotLoseData:
    def test_move_writes_new_before_deleting_old(self, monkeypatch):
        """If the write to the new location fails, the old file must survive."""
        mem = wiki.write_memory("note", "hand", "old-topic", "Precious content")
        old_path = mem.path

        original_write = wiki._write_md

        def failing_write(path, memory):
            raise OSError("disk full")

        monkeypatch.setattr(wiki, "_write_md", failing_write)
        try:
            wiki.update_memory(mem.id, topic="new-topic")
        except OSError:
            pass
        monkeypatch.setattr(wiki, "_write_md", original_write)

        # The memory must still exist somewhere on disk
        assert old_path.exists()
        assert "Precious content" in old_path.read_text(encoding="utf-8")

    def test_rename_rewrites_inbound_links(self):
        """Renaming (moving) a memory must rewrite other files' [[links]]
        and keep backlinks resolving."""
        from memento import memory as memory_mod, index, search

        target = memory_mod.store("note", "chest", "core", "API contract doc")
        source = memory_mod.store(
            "note", "hand", "todo", f"Check [[{target.slug}]] before deploy"
        )

        moved = memory_mod.update(target.id, topic="archived")
        # Slug may stay the same on a topic-only move; force the full case
        assert moved is not None

        # Backlink must still resolve to the moved memory
        backlinks = search.get_backlinks(target.id)
        assert len(backlinks) == 1
        assert backlinks[0]["memory_id"] == source.id

        links = index.get_linked_entries(source.id)
        assert len(links) == 1
        assert links[0]["resolved"] is True
        assert links[0]["memory_id"] == target.id

    def test_rename_with_slug_change_rewrites_link_text(self):
        """When a move forces a slug rename (collision), the source file's
        [[old-slug]] text must be rewritten to the new slug."""
        from memento import memory as memory_mod

        # Occupy the destination slug to force a collision rename
        memory_mod.store("note", "hand", "new-topic", "blocker", slug="shared")
        target = memory_mod.store("note", "hand", "old-topic", "mover", slug="shared")
        source = memory_mod.store("note", "chest", "core", "See [[shared]] for info")

        # Linking by slug 'shared' is ambiguous (blocker vs target) — make
        # sure the source resolved to target before the move for this test
        from memento import index
        with index._connect() as conn:
            conn.execute(
                "UPDATE index_links SET target_id = ? WHERE source_id = ?",
                (target.id, source.id),
            )

        moved = memory_mod.update(target.id, topic="new-topic")
        assert moved.slug == "shared-1"

        refreshed = memory_mod.recall(source.id)
        assert "[[shared-1]]" in refreshed.content
        assert "[[shared]]" not in refreshed.content

    def test_move_collision_updates_slug(self):
        """After a collision rename, frontmatter slug must match the filename."""
        blocker = wiki.write_memory("note", "hand", "new-topic", "blocker", slug="content")
        mem = wiki.write_memory("note", "hand", "old-topic", "mover", slug="content")
        updated = wiki.update_memory(mem.id, topic="new-topic")
        assert updated.path.stem == updated.slug
        reread = wiki.read_memory(updated.path)
        assert reread.slug == updated.path.stem
