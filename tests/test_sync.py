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
