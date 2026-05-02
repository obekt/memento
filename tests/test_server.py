"""Tests for the MCP server (server.py)."""

import asyncio
import json

import pytest

from memento.server import list_tools, call_tool, read_resource
from memento import memory


@pytest.mark.asyncio
async def test_list_tools():
    tools = await list_tools()
    names = {t.name for t in tools}
    assert "tattoo" in names
    assert "snap" in names
    assert "scribble" in names
    assert "wake_up" in names
    assert "export_vault" in names
    assert len(tools) >= 20


@pytest.mark.asyncio
async def test_tattoo():
    result = await call_tool("tattoo", {"context": "chest", "topic": "test", "content": "Test fact", "title": "Test"})
    assert "Tattooed on chest" in result[0].text


@pytest.mark.asyncio
async def test_snap():
    result = await call_tool("snap", {"context": "left_arm", "topic": "bug", "content": "Error", "caption": "Fix", "title": "Err"})
    assert "Polaroid" in result[0].text


@pytest.mark.asyncio
async def test_scribble():
    result = await call_tool("scribble", {"context": "hand", "topic": "todo", "content": "Buy milk"})
    assert "Scribbled" in result[0].text


@pytest.mark.asyncio
async def test_recall():
    mem = memory.store("note", "hand", "todo", "Recall me")
    result = await call_tool("recall", {"memory_id": mem.id})
    data = json.loads(result[0].text)
    assert data["id"] == mem.id


@pytest.mark.asyncio
async def test_search_memories():
    memory.store("note", "hand", "todo", "Searchable xyz")
    result = await call_tool("search_memories", {"query": "xyz"})
    assert "Found" in result[0].text


@pytest.mark.asyncio
async def test_wake_up():
    memory.store("tattoo", "chest", "core", "Fact")
    result = await call_tool("wake_up", {})
    data = json.loads(result[0].text)
    assert data["summary"]["tattoo_count"] >= 1


@pytest.mark.asyncio
async def test_burn_note():
    mem = memory.store("note", "hand", "todo", "Burn")
    result = await call_tool("burn_note", {"memory_id": mem.id})
    assert "Burned" in result[0].text


@pytest.mark.asyncio
async def test_burn_tattoo_fails():
    mem = memory.store("tattoo", "chest", "core", "Permanent")
    result = await call_tool("burn_note", {"memory_id": mem.id})
    assert "Cannot burn" in result[0].text


@pytest.mark.asyncio
async def test_export_vault():
    result = await call_tool("export_vault", {})
    assert ".zip" in result[0].text


@pytest.mark.asyncio
async def test_read_resource_guide():
    text = await read_resource("memento://guide")
    assert "Leonard Shelby" in text


@pytest.mark.asyncio
async def test_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        await call_tool("nonexistent", {})
