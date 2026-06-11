"""Tests for zip-based export/import/merge (sync.py)."""

from pathlib import Path

from memento import memory, sync, wiki


class TestExportVault:
    def test_export_creates_zip(self, tmp_path):
        memory.store("tattoo", "chest", "core", "Fact")
        path = sync.export_vault(str(tmp_path / "out.zip"))
        assert Path(path).exists()
        assert Path(path).suffix == ".zip"

    def test_export_contains_markdown(self, tmp_path):
        mem = memory.store("tattoo", "chest", "core", "Fact", title="My Fact")
        path = sync.export_vault(str(tmp_path / "out.zip"))
        import zipfile
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            assert any(n.endswith(".md") for n in names)


class TestImportVault:
    def test_import_creates_files(self, tmp_path):
        memory.store("tattoo", "chest", "core", "Original")
        export_path = sync.export_vault(str(tmp_path / "export.zip"))

        # Clear wiki
        import shutil
        shutil.rmtree(wiki.WIKI_ROOT)
        wiki.ensure_wiki()

        result = sync.import_vault(export_path)
        assert result["created"] >= 1
        assert any(wiki.WIKI_ROOT.rglob("*.md"))

    def test_import_keep_mine(self, tmp_path):
        mem = memory.store("tattoo", "chest", "core", "Original")
        export_path = sync.export_vault(str(tmp_path / "export.zip"))
        result = sync.import_vault(export_path, merge_strategy="keep_mine")
        assert result["skipped"] >= 1


class TestImportKeepBoth:
    def test_keep_both_variant_gets_fresh_id(self, tmp_path):
        """keep_both duplicates must NOT share the original's id — duplicate
        ids used to crash rebuild_index (id is PRIMARY KEY) on next boot."""
        mem = memory.store("tattoo", "chest", "core", "Original body")
        export_path = sync.export_vault(str(tmp_path / "export.zip"))

        # Diverge the local copy so keep_both detects a conflict
        mem.path.write_text(
            mem.path.read_text(encoding="utf-8").replace(
                "Original body", "Locally changed body"
            ),
            encoding="utf-8",
        )

        result = sync.import_vault(export_path, merge_strategy="keep_both")
        assert result["conflicts_resolved_by_duplication"] == 1

        ids = set()
        for md in wiki.WIKI_ROOT.rglob("*.md"):
            ids.add(wiki.read_memory(md).id)
        assert len(ids) == 2  # original + variant with fresh id

        # And the rebuild must succeed without skipping anything
        from memento import index
        stats = index.rebuild_index()
        assert stats["indexed_entries"] == 2
        assert "skipped_files" not in stats

    def test_import_rejects_zip_slip_members(self, tmp_path):
        """Zip members with .. or absolute paths must not escape the wiki."""
        import zipfile

        evil_zip = tmp_path / "evil.zip"
        with zipfile.ZipFile(evil_zip, "w") as zf:
            zf.writestr("../../escaped.md", "---\nid: x\n---\n\nevil\n")
            zf.writestr("/abs/escaped.md", "---\nid: y\n---\n\nevil\n")
            zf.writestr("ok/fine.md", "---\nid: z\nkind: note\n---\n\nok\n")

        result = sync.import_vault(str(evil_zip))
        assert result["created"] == 1
        assert not (wiki.WIKI_ROOT.parent.parent / "escaped.md").exists()
        assert not Path("/abs/escaped.md").exists()


class TestMergeVaults:
    def test_merge_creates_output(self, tmp_path):
        memory.store("tattoo", "chest", "core", "Fact A")
        export_a = sync.export_vault(str(tmp_path / "a.zip"))

        import shutil
        shutil.rmtree(wiki.WIKI_ROOT)
        wiki.ensure_wiki()

        memory.store("note", "hand", "todo", "Task B")
        export_b = sync.export_vault(str(tmp_path / "b.zip"))

        output = str(tmp_path / "merged.zip")
        result = sync.merge_vaults(export_a, export_b, output)
        assert Path(result["output_path"]).exists()
