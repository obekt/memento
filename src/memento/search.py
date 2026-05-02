"""Search, backlinks, and timeline queries for Memento."""

from typing import Any

from memento import wiki
from memento import index


def _ensure_index() -> None:
    index.init_index()


def search_memories(
    query: str,
    kind: str | None = None,
    context: str | None = None,
    topic: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[wiki.Memory]:
    """Full-text search using FTS5, with optional filters."""
    entries = index.search(query, kind, context, topic, tags, limit)
    result = []
    for e in entries:
        if e.path and e.path.exists():
            mem = wiki.read_memory(e.path)
            mem.tags = index.get_tags_for_entry(mem.id)
            result.append(mem)
    return result


def get_linked_entries(memory_id: str) -> list[dict[str, Any]]:
    """Return memories that the given memory links out to."""
    return index.get_linked_entries(memory_id)


def get_backlinks(memory_id: str) -> list[dict[str, Any]]:
    """Return memories that link TO the given memory."""
    return index.get_backlinks(memory_id)


def resolve_link(link_target: str) -> wiki.Memory | None:
    """Resolve a [[wiki-link]] target to a memory."""
    entry = index.resolve_link(link_target)
    if entry is None or not entry.path or not entry.path.exists():
        return None
    mem = wiki.read_memory(entry.path)
    mem.tags = index.get_tags_for_entry(mem.id)
    return mem


def wake_up(context: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Reconstruct context: read recent tattoos, polaroids, and notes."""
    tattoos: list[wiki.Memory] = []
    polaroids: list[wiki.Memory] = []
    notes: list[wiki.Memory] = []

    for e in index.get_tattoos(context, limit):
        if e.path and e.path.exists():
            mem = wiki.read_memory(e.path)
            mem.tags = index.get_tags_for_entry(mem.id)
            tattoos.append(mem)

    # Polaroids
    from memento.index import _connect, init_index
    init_index()
    with _connect() as conn:
        sql = "SELECT * FROM index_entries WHERE kind = 'polaroid'"
        params: list[Any] = []
        if context:
            sql += " AND context = ?"
            params.append(context)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        for r in conn.execute(sql, params):
            p = wiki.Memory(
                id=r["id"], kind=r["kind"], context=r["context"], topic=r["topic"],
                slug=r["slug"], title=r["title"] or "", content=r["content"],
                caption=r["caption"] or "", path=wiki.Path(r["path"]) if r["path"] else None,
                created_at=r["created_at"] or "", updated_at=r["updated_at"] or "",
            )
            if p.path and p.path.exists():
                mem = wiki.read_memory(p.path)
                mem.tags = index.get_tags_for_entry(mem.id)
                polaroids.append(mem)

        # Notes
        sql = "SELECT * FROM index_entries WHERE kind = 'note'"
        params = []
        if context:
            sql += " AND context = ?"
            params.append(context)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        for r in conn.execute(sql, params):
            p = wiki.Memory(
                id=r["id"], kind=r["kind"], context=r["context"], topic=r["topic"],
                slug=r["slug"], title=r["title"] or "", content=r["content"],
                caption=r["caption"] or "", path=wiki.Path(r["path"]) if r["path"] else None,
                created_at=r["created_at"] or "", updated_at=r["updated_at"] or "",
            )
            if p.path and p.path.exists():
                mem = wiki.read_memory(p.path)
                mem.tags = index.get_tags_for_entry(mem.id)
                notes.append(mem)

    return {
        "context": context or "all",
        "tattoos": tattoos,
        "polaroids": polaroids,
        "notes": notes,
        "summary": {
            "tattoo_count": len(tattoos),
            "polaroid_count": len(polaroids),
            "note_count": len(notes),
        },
    }


def reverse_timeline(context: str | None = None, limit: int = 20) -> list[wiki.Memory]:
    """View memories in reverse chronological order (oldest first)."""
    _ensure_index()
    from memento.index import _connect
    with _connect() as conn:
        sql = "SELECT * FROM index_entries WHERE 1=1"
        params: list[Any] = []
        if context:
            sql += " AND context = ?"
            params.append(context)
        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            p = wiki.Path(r["path"]) if r["path"] else None
            if p and p.exists():
                mem = wiki.read_memory(p)
                mem.tags = index.get_tags_for_entry(mem.id)
                result.append(mem)
        return result


def sammy_jankis_test(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search for similar past errors or low-certainty memories."""
    entries = index.search(query, limit=limit)
    result = []
    for e in entries:
        if e.path and e.path.exists():
            mem = wiki.read_memory(e.path)
            mem.tags = index.get_tags_for_entry(mem.id)
            result.append({
                "memory": mem,
                "warning": "Repeated pattern detected" if mem.kind == "note" else None,
                "reliability": mem.certainty,
            })
    return result
