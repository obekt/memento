"""Pytest configuration and shared fixtures for Memento tests."""

import pytest
from pathlib import Path

import memento.wiki as wiki_module
import memento.index as index_module


@pytest.fixture(autouse=True)
def temp_wiki(tmp_path, monkeypatch):
    """Use a temporary wiki directory and index for every test."""
    wiki_dir = tmp_path / "wiki"
    index_db = tmp_path / "index.db"
    monkeypatch.setattr(wiki_module, "WIKI_ROOT", wiki_dir)
    monkeypatch.setattr(index_module, "WIKI_ROOT", wiki_dir)
    monkeypatch.setattr(index_module, "INDEX_PATH", index_db)
    wiki_module.ensure_wiki()
    yield
    # Cleanup
    import shutil
    if wiki_dir.exists():
        shutil.rmtree(wiki_dir)
    if index_db.exists():
        index_db.unlink()
