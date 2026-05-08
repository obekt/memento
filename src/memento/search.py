"""Search, backlinks, and timeline queries for Memento."""

from typing import Any

from memento import wiki
from memento import index


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


def _hydrate_entries(entries: list[wiki.Memory]) -> list[wiki.Memory]:
    """Read full memory from file and attach tags for a list of index entries."""
    result = []
    for e in entries:
        if e.path and e.path.exists():
            mem = wiki.read_memory(e.path)
            mem.tags = index.get_tags_for_entry(mem.id)
            result.append(mem)
    return result


def wake_up(context: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Reconstruct context: read recent tattoos, polaroids, and notes."""
    tattoos = _hydrate_entries(index.get_entries_by_kind("tattoo", context, limit))
    polaroids = _hydrate_entries(index.get_entries_by_kind("polaroid", context, limit))
    notes = _hydrate_entries(index.get_entries_by_kind("note", context, limit))

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
    """View memories in reverse chronological order (newest first, like the movie)."""
    entries = index.get_recent_entries(context, limit)
    return _hydrate_entries(entries)


def sammy_jankis_test(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search for similar past errors or low-certainty memories.

    Looks for:
    1. FTS matches for the query (potential repeated patterns)
    2. Flags low-certainty memories as unreliable
    3. Detects repeated patterns when multiple memories share the same topic
    """
    # Search for matches, cast a wider net then trim
    entries = index.search(query, limit=limit * 2)
    result = []
    topic_counts: dict[str, int] = {}

    for e in entries:
        if e.path and e.path.exists():
            mem = wiki.read_memory(e.path)
            mem.tags = index.get_tags_for_entry(mem.id)
            topic_key = f"{mem.context}/{mem.topic}"
            topic_counts[topic_key] = topic_counts.get(topic_key, 0) + 1

            # Build warning message based on actual signals
            warnings = []
            if mem.certainty < 0.8:
                warnings.append(f"Low certainty ({mem.certainty})")
            if topic_counts[topic_key] > 1:
                warnings.append(f"Repeated topic ({topic_key} appeared {topic_counts[topic_key]} times)")
            if mem.kind == "note":
                warnings.append("Temporary note — may be outdated")

            result.append({
                "memory": mem,
                "warning": "; ".join(warnings) if warnings else None,
                "reliability": mem.certainty,
            })

    # Sort by reliability ascending (least reliable first) and trim to limit
    result.sort(key=lambda r: r["reliability"])
    return result[:limit]
