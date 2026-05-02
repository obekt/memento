"""CRUD operations for memories: orchestrates wiki files + search index."""

from typing import Any

from memento import wiki
from memento import index


def store(
    kind: str,
    context: str,
    topic: str,
    content: str,
    title: str = "",
    caption: str = "",
    certainty: float = 1.0,
    image_path: str = "",
    source: str = "",
    tags: list[str] | None = None,
    slug: str | None = None,
) -> wiki.Memory:
    """Create a new memory: write .md file, index it."""
    memory = wiki.write_memory(
        kind=kind,
        context=context,
        topic=topic,
        content=content,
        title=title,
        caption=caption,
        certainty=certainty,
        image_path=image_path,
        source=source,
        tags=tags,
        slug=slug,
    )
    index.index_memory(memory, memory.path)
    return memory


def recall(memory_id: str) -> wiki.Memory | None:
    """Fetch a memory by ID: find .md file, read it."""
    path = wiki.find_memory(memory_id)
    if path is None:
        return None
    return wiki.read_memory(path)


def update(
    memory_id: str,
    context: str | None = None,
    topic: str | None = None,
    title: str | None = None,
    content: str | None = None,
    caption: str | None = None,
    certainty: float | None = None,
    image_path: str | None = None,
    source: str | None = None,
    tags: list[str] | None = None,
) -> wiki.Memory | None:
    """Update an existing memory: rewrite .md file, re-index."""
    memory = wiki.update_memory(
        memory_id=memory_id,
        context=context,
        topic=topic,
        title=title,
        content=content,
        caption=caption,
        certainty=certainty,
        image_path=image_path,
        source=source,
        tags=tags,
    )
    if memory is None:
        return None
    index.index_memory(memory, memory.path)
    return memory


def burn(memory_id: str) -> bool:
    """Delete a memory. Tattoos cannot be burned."""
    mem = recall(memory_id)
    if mem is None:
        return False
    if mem.kind == "tattoo":
        return False
    ok = wiki.delete_memory(memory_id)
    if ok:
        index.deindex_memory(memory_id)
    return ok


def list_contexts() -> list[str]:
    return index.list_all_contexts()


def list_topics(context: str | None = None) -> list[str]:
    return index.list_all_topics(context)


def get_topic(context: str, topic: str, limit: int = 50) -> list[wiki.Memory]:
    # Read from index for speed, but return actual files
    entries = index.get_entries_by_topic(context, topic, limit)
    result = []
    for e in entries:
        if e.path and e.path.exists():
            result.append(wiki.read_memory(e.path))
    return result


def examine_tattoos(context: str | None = None, limit: int = 100) -> list[wiki.Memory]:
    entries = index.get_tattoos(context, limit)
    result = []
    for e in entries:
        if e.path and e.path.exists():
            result.append(wiki.read_memory(e.path))
    return result


def summarize_topic(context: str, topic: str) -> dict[str, Any]:
    return index.summarize(context, topic)
