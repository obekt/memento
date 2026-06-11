"""Memento MCP Server — Leonard Shelby's memory system for LLMs."""

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool, Resource

from memento import wiki
from memento import index
from memento import memory
from memento import search
from memento import sync

MEMENTO_GUIDE = """# Memento Guide

> "Every 5 minutes, your coding agent forgets everything. It doesn't remember the
> architecture. It doesn't remember the bug from yesterday. It doesn't remember
> why that workaround exists.
>
> Your agent is Leonard Shelby. This is its tattoo parlor."

## The Three Memory Systems

Leonard Shelby (Memento, 2000) has anterograde amnesia. To function, he uses three
memory systems with different reliability levels:

### Tattoos — Permanent, Immutable
Burned into skin. Can never be lost, never be faked, never forgotten.
- Use `tattoo()` for architecture decisions, API contracts, critical bug fixes
- Stored in `context` = body part: `chest` (most vital), `left_arm`, `thigh`, etc.
- **Cannot be burned** — tattoos are forever

### Polaroids — Context-Rich Snapshots
Photos with handwritten captions on the back.
- Use `snap()` for error messages, terminal output, state captures
- Each polaroid has a `content` (what you see) and a `caption` (back-of-photo note)
- Can be burned if the context changes

### Notes — Temporary, Disposable
Scribbled on scraps of paper. "SHAVE". "DON'T ANSWER THE PHONE".
- Use `scribble()` for TODOs, temporary hypotheses, reminders
- Easy to write, easy to burn. Often wrong or outdated.

## Storage Format

Every memory is a **markdown file** with YAML frontmatter:

```markdown
---
id: 550e8400-e29b-41d4-a716-446655440000
kind: tattoo
context: chest
topic: architecture
slug: db-choice
title: Database Choice
tags: [scaling, sqlite]
certainty: 1.0
created_at: 2026-05-02T14:00:00+00:00
updated_at: 2026-05-02T14:00:00+00:00
---

Use SQLite with FTS5 for full-text search.
```

Files live in `~/.memento/wiki/{context}/{topic}/{slug}.md`.

## Context = Body Part (Namespaces)

To avoid topic collision ("setup" in Project A vs Project B), Memento uses body
parts as namespaces:

- `chest/` — Core facts. Always visible. Most important.
- `left_arm/`, `right_arm/` — Working context. Current project, current bug.
- `hand/` — Immediate reminders. "SHAVE." "Call Natalie."
- `thigh/` — Deep background. License plates, drug dealer facts.
- `back/` — Hidden assumptions. Things you can't see yourself.

Example: `chest/memento/architecture` vs `left_arm/client-x/architecture`

## When to Use What

| Situation | Tool | Why |
|-----------|------|-----|
| Architecture decision | `tattoo()` | Permanent, survives every session |
| Error message + fix | `snap()` | Visual context with caption |
| TODO / temporary idea | `scribble()` | Quick, disposable |
| Starting a new session | `wake_up()` | Reconstruct context from tattoos + polaroids |
| Searching past work | `search_memories()` | FTS5 full-text search |
| Checking for repeated mistakes | `sammy_jankis_test()` | "Am I repeating the same error?" |

## Available Tools

- `tattoo(context, topic, content, title, tags, source)` — Permanent fact.
- `snap(context, topic, content, caption, title, tags, source)` — Polaroid snapshot.
- `scribble(context, topic, content, title, tags, source)` — Temporary note.
- `recall(memory_id)` — Fetch a memory by UUID.
- `search_memories(query, kind, context, topic, tags, limit)` — Full-text search.
- `list_contexts()` — List body parts (namespaces).
- `list_topics(context)` — List topics, optionally filtered by context.
- `get_topic(context, topic, limit)` — Read all memories in a context+topic.
- `examine_tattoos(context)` — List permanent facts for a body part.
- `update_memory(memory_id, ...)` — Modify an existing memory.
- `burn_note(memory_id)` — Delete a note or polaroid. Tattoos are forever.
- `fact_or_fiction(memory_id, certainty)` — Rate reliability (0.0-1.0).
- `wake_up(context)` — Reconstruct context. "Where am I? What am I doing?"
- `reverse_timeline(context, limit)` — View memories backward (like the movie).
- `sammy_jankis_test(query, limit)` — "Am I repeating the same mistake?"
- `follow_link(link_target)` — Resolve a `[[wiki-link]]`.
- `get_backlinks(memory_id)` — Who references this memory?
- `get_linked_entries(memory_id)` — Memories this one links to.
- `export_vault(path)` — Backup the wiki to a `.zip` file.
- `import_vault(path, merge_strategy)` — Restore or merge from a `.zip` file.
- `merge_vaults(path_a, path_b, output_path, merge_strategy)` — Merge two exports.

## Merge Strategies

- `keep_both`: If files differ, keep both (duplicate with `.imported.md` suffix).
- `keep_newer`: Keep the file with the latest `updated_at` frontmatter.
- `keep_mine`: Never overwrite existing files.
- `keep_theirs`: Always overwrite with imported files.

## Data Location

```
~/.memento/wiki/     # Markdown files (source of truth)
~/.memento/.index.db # SQLite FTS5 index (rebuildable)
```

## Zero-Config Philosophy

Memento is designed so that any coding agent can use it immediately. The tool
names tell the story. You don't read docs — you wake up, check your tattoos,
and start working.
"""

app = Server("memento")


@app.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="memento://guide",
            name="Memento Usage Guide",
            mimeType="text/markdown",
            description="Complete guide on how to use Memento",
        ),
        Resource(
            uri="memento://contexts",
            name="All Contexts",
            mimeType="application/json",
            description="List of all body-part contexts in the wiki",
        ),
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "memento://guide":
        return MEMENTO_GUIDE
    if uri == "memento://contexts":
        index.sync_if_stale()
        contexts = memory.list_contexts()
        return json.dumps(contexts, indent=2)
    if uri.startswith("memento://context/"):
        context = uri[len("memento://context/"):]
        topics = memory.list_topics(context)
        return json.dumps(topics, indent=2)
    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_memento_guide",
            description="Returns the complete Memento usage guide. Call this first if you are unsure how Memento works.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="tattoo",
            description=(
                "Burn a permanent fact into memory — like a tattoo on Leonard Shelby's skin. "
                "Use this for architecture decisions, API contracts, critical bug fixes, and anything "
                "that must survive EVERY session. Tattoos cannot be deleted. "
                "Example: tattoo(context='chest', topic='architecture', content='Use PostgreSQL, not SQLite, for production.')"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Body part / namespace. 'chest' = most vital, 'left_arm' = working context, 'thigh' = background."},
                    "topic": {"type": "string", "description": "Topic path. Can be hierarchical: 'project/setup' or 'api-design/auth'."},
                    "content": {"type": "string", "description": "The permanent fact. Be specific and actionable."},
                    "title": {"type": "string", "description": "Optional title."},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                    "source": {"type": "string", "description": "Optional source reference."},
                },
                "required": ["context", "topic", "content"],
            },
        ),
        Tool(
            name="snap",
            description=(
                "Take a Polaroid — a context-rich snapshot with a handwritten caption on the back. "
                "Use this for error messages, terminal output, state captures, or any situation where "
                "you need to remember both WHAT you saw and WHAT IT MEANS. "
                "Example: snap(context='left_arm', topic='bugs', content='Traceback: ConnectionRefusedError', caption='Happens when Redis is down. Restart Docker container.')"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Body part / namespace."},
                    "topic": {"type": "string", "description": "Topic path."},
                    "content": {"type": "string", "description": "What you see — the snapshot content (error message, output, state)."},
                    "caption": {"type": "string", "description": "Back-of-photo caption — what it means, how to fix it, why it matters."},
                    "title": {"type": "string", "description": "Optional title."},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                    "source": {"type": "string", "description": "Optional source reference."},
                },
                "required": ["context", "topic", "content"],
            },
        ),
        Tool(
            name="scribble",
            description=(
                "Jot a temporary note on a scrap of paper. "
                "Use this for TODOs, temporary hypotheses, quick reminders. "
                "Notes are disposable — easy to write, easy to burn. They may be wrong or outdated. "
                "Example: scribble(context='hand', topic='todo', content='Refactor auth module before lunch.')"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Body part / namespace. 'hand' = immediate reminder."},
                    "topic": {"type": "string", "description": "Topic path."},
                    "content": {"type": "string", "description": "The temporary note."},
                    "title": {"type": "string", "description": "Optional title."},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                    "source": {"type": "string", "description": "Optional source reference."},
                },
                "required": ["context", "topic", "content"],
            },
        ),
        Tool(
            name="recall",
            description="Retrieve a single memory by its unique ID.",
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string", "description": "UUID of the memory."}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="search_memories",
            description=(
                "Search the memory wiki using full-text search (FTS5). "
                "This is the primary way to find knowledge. Filters by kind, context, topic, and tags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query. Supports phrases and keywords."},
                    "kind": {"type": "string", "enum": ["tattoo", "polaroid", "note"], "description": "Optional: filter by memory kind."},
                    "context": {"type": "string", "description": "Optional: filter by body part / namespace."},
                    "topic": {"type": "string", "description": "Optional: filter by topic."},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional: filter by tags (all must match)."},
                    "limit": {"type": "integer", "description": "Max results. Default 10."},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_contexts",
            description="List all body-part contexts (namespaces) in the wiki, ordered by most recently updated.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_topics",
            description="List all topics. Optionally filter by a specific context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Optional body part to filter by."},
                },
            },
        ),
        Tool(
            name="get_topic",
            description=(
                "Retrieve memories under a specific context+topic. "
                "Returns compact previews by default. Use detail='full' to load entire content. "
                "Call recall() on a specific ID if you need the full body after browsing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Body part / namespace."},
                    "topic": {"type": "string", "description": "Topic path."},
                    "limit": {"type": "integer", "description": "Max results. Default 50."},
                    "detail": {"type": "string", "enum": ["compact", "full"], "description": "Default 'compact'. Use 'full' to return complete content."},
                },
                "required": ["context", "topic"],
            },
        ),
        Tool(
            name="examine_tattoos",
            description="List permanent facts (tattoos) for a body part, or all tattoos if no context given.",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Optional body part to filter by."},
                    "limit": {"type": "integer", "description": "Max results. Default 100."},
                },
            },
        ),
        Tool(
            name="update_memory",
            description="Modify an existing memory. Tattoos cannot change their kind (they're permanent).",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "context": {"type": "string"},
                    "topic": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "caption": {"type": "string"},
                    "certainty": {"type": "number", "description": "0.0 to 1.0"},
                    "source": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="burn_note",
            description=(
                "Permanently destroy a note or polaroid. "
                "TATTOOS CANNOT BE BURNED — they are permanent. "
                "Use this to clean up outdated notes and polaroids."
            ),
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="fact_or_fiction",
            description=(
                "Rate a memory's reliability (0.0 to 1.0). "
                "Like Leonard questioning whether Teddy is lying. "
                "Use this when you discover a memory is wrong, outdated, or hallucinated."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "certainty": {"type": "number", "description": "0.0 = definitely false, 1.0 = definitely true"},
                },
                "required": ["memory_id", "certainty"],
            },
        ),
        Tool(
            name="wake_up",
            description=(
                "Reconstruct your context. Like Leonard Shelby waking up and checking his tattoos and polaroids. "
                "Returns recent tattoos (permanent facts), polaroids (context snapshots), and notes (immediate reminders). "
                "Call this at the start of every session."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Optional: restrict to a specific body part."},
                    "limit": {"type": "integer", "description": "How many of each kind to return. Default 10."},
                },
            },
        ),
        Tool(
            name="reverse_timeline",
            description=(
                "View memories in reverse chronological order, like the movie's color timeline. "
                "Returns compact previews by default. Use detail='full' for complete content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Optional body part filter."},
                    "limit": {"type": "integer", "description": "Max results. Default 20."},
                    "detail": {"type": "string", "enum": ["compact", "full"], "description": "Default 'compact'. Use 'full' to return complete content."},
                },
            },
        ),
        Tool(
            name="sammy_jankis_test",
            description=(
                "'Am I repeating the same mistake?' — Search for similar past errors or low-certainty memories. "
                "Named after Sammy Jankis, the man who accidentally killed his wife by giving her too much insulin "
                "because he couldn't remember he'd already given her a shot. Use this to detect repeated bugs, "
                "recurring anti-patterns, or déjà vu situations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Describe the current situation or error."},
                    "limit": {"type": "integer", "description": "Max results. Default 5."},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="follow_link",
            description="Resolve a [[wiki-link]] target to a memory.",
            inputSchema={
                "type": "object",
                "properties": {"link_target": {"type": "string"}},
                "required": ["link_target"],
            },
        ),
        Tool(
            name="get_backlinks",
            description="Find all memories that link TO this memory.",
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="get_linked_entries",
            description="Find all memories that this memory links out to.",
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="export_vault",
            description=(
                "Export the entire wiki to a portable .zip file containing all markdown files. "
                "Use this to create backups before major changes, or to migrate your wiki to another machine. "
                "If no path is given, a timestamped file is created in ~/.memento/."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional absolute path for the export zip. If omitted, auto-generated in ~/.memento/."},
                },
            },
        ),
        Tool(
            name="import_vault",
            description=(
                "Import a Memento wiki .zip file into the live wiki. "
                "Use this to restore from backup or merge a wiki from another machine. "
                "Choose a merge_strategy to handle conflicts. Default is 'keep_both' which preserves all information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the .zip export file to import."},
                    "merge_strategy": {"type": "string", "enum": ["keep_both", "keep_newer", "keep_mine", "keep_theirs"], "description": "How to resolve conflicts when a file already exists. Default: 'keep_both'."},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="merge_vaults",
            description=(
                "Merge two Memento wiki .zip files into a new .zip file WITHOUT modifying the live wiki. "
                "Use this when you have exports from two different machines and want to create a unified wiki. "
                "The result is a new .zip file that you can then import with import_vault."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path_a": {"type": "string", "description": "Absolute path to the first wiki export .zip."},
                    "path_b": {"type": "string", "description": "Absolute path to the second wiki export .zip."},
                    "output_path": {"type": "string", "description": "Absolute path for the merged output .zip."},
                    "merge_strategy": {"type": "string", "enum": ["keep_both", "keep_newer", "keep_mine", "keep_theirs"], "description": "Conflict resolution strategy. Default: 'keep_both'."},
                },
                "required": ["path_a", "path_b", "output_path"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_memento_guide":
        return [TextContent(type="text", text=MEMENTO_GUIDE)]

    # Pick up files edited outside Memento (vim, git pull, rsync) — the
    # markdown files are the source of truth, so resync before serving.
    index.sync_if_stale()

    if name == "tattoo":
        mem = memory.store(
            kind="tattoo",
            context=arguments["context"],
            topic=arguments["topic"],
            content=arguments["content"],
            title=arguments.get("title", ""),
            tags=arguments.get("tags"),
            source=arguments.get("source", ""),
        )
        return [TextContent(type="text", text=f"Tattooed on {mem.context}: '{mem.title or mem.slug}' (ID: {mem.id}, path: {mem.path})")]

    if name == "snap":
        mem = memory.store(
            kind="polaroid",
            context=arguments["context"],
            topic=arguments["topic"],
            content=arguments["content"],
            caption=arguments.get("caption", ""),
            title=arguments.get("title", ""),
            tags=arguments.get("tags"),
            source=arguments.get("source", ""),
        )
        return [TextContent(type="text", text=f"Polaroid taken in {mem.context}/{mem.topic}: '{mem.title or mem.slug}' (ID: {mem.id})")]

    if name == "scribble":
        mem = memory.store(
            kind="note",
            context=arguments["context"],
            topic=arguments["topic"],
            content=arguments["content"],
            title=arguments.get("title", ""),
            tags=arguments.get("tags"),
            source=arguments.get("source", ""),
        )
        return [TextContent(type="text", text=f"Scribbled on {mem.context}: '{mem.title or mem.slug}' (ID: {mem.id})")]

    if name == "recall":
        mem = memory.recall(arguments["memory_id"])
        if mem is None:
            return [TextContent(type="text", text=f"No memory found with ID {arguments['memory_id']}")]
        return [TextContent(type="text", text=json.dumps(mem.to_dict(), indent=2))]

    if name == "search_memories":
        results = search.search_memories(
            query=arguments["query"],
            kind=arguments.get("kind"),
            context=arguments.get("context"),
            topic=arguments.get("topic"),
            tags=arguments.get("tags"),
            limit=arguments.get("limit", 10),
        )
        if not results:
            return [TextContent(type="text", text="No matching memories found.")]
        lines = [f"Found {len(results)} memory/ies:"]
        for m in results:
            preview = m.content[:150].replace("\n", " ")
            lines.append(f"  [{m.kind}] {m.context}/{m.topic}/{m.slug} — {m.title or 'Untitled'} (certainty: {m.certainty}): {preview}...")
        return [TextContent(type="text", text="\n".join(lines))]

    if name == "list_contexts":
        contexts = memory.list_contexts()
        if not contexts:
            return [TextContent(type="text", text="No contexts yet. The wiki is empty.")]
        return [TextContent(type="text", text="Body parts (contexts):\n" + "\n".join(f"  - {c}" for c in contexts))]

    if name == "list_topics":
        topics = memory.list_topics(arguments.get("context"))
        if not topics:
            return [TextContent(type="text", text="No topics found.")]
        return [TextContent(type="text", text="Topics:\n" + "\n".join(f"  - {t}" for t in topics))]

    if name == "get_topic":
        results = memory.get_topic(
            context=arguments["context"],
            topic=arguments["topic"],
            limit=arguments.get("limit", 50),
        )
        if not results:
            return [TextContent(type="text", text=f"No memories in {arguments['context']}/{arguments['topic']}.")]
        detail = arguments.get("detail", "compact")
        if detail == "full":
            payload = [m.to_dict() for m in results]
        else:
            payload = [m.to_compact() for m in results]
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    if name == "examine_tattoos":
        results = memory.examine_tattoos(
            context=arguments.get("context"),
            limit=arguments.get("limit", 100),
        )
        if not results:
            return [TextContent(type="text", text="No tattoos found.")]
        lines = [f"Found {len(results)} tattoo(s):"]
        for m in results:
            preview = m.content[:150].replace("\n", " ")
            lines.append(f"  [{m.context}] {m.title or m.slug}: {preview}...")
        return [TextContent(type="text", text="\n".join(lines))]

    if name == "update_memory":
        try:
            mem = memory.update(
                memory_id=arguments["memory_id"],
                context=arguments.get("context"),
                topic=arguments.get("topic"),
                title=arguments.get("title"),
                content=arguments.get("content"),
                caption=arguments.get("caption"),
                certainty=arguments.get("certainty"),
                source=arguments.get("source"),
                tags=arguments.get("tags"),
            )
        except ValueError as e:
            return [TextContent(type="text", text=str(e))]
        if mem is None:
            return [TextContent(type="text", text=f"No memory found with ID {arguments['memory_id']}")]
        return [TextContent(type="text", text=f"Updated {mem.kind} {mem.id} in {mem.context}/{mem.topic}")]

    if name == "burn_note":
        ok = memory.burn(arguments["memory_id"])
        if ok:
            return [TextContent(type="text", text="Burned. Gone forever.")]
        return [TextContent(type="text", text="Cannot burn. Either it's a tattoo (permanent) or the ID doesn't exist.")]

    if name == "fact_or_fiction":
        mem = memory.update(
            memory_id=arguments["memory_id"],
            certainty=arguments["certainty"],
        )
        if mem is None:
            return [TextContent(type="text", text=f"No memory found with ID {arguments['memory_id']}")]
        label = "FACT" if mem.certainty >= 0.8 else "UNCERTAIN" if mem.certainty >= 0.4 else "FICTION"
        return [TextContent(type="text", text=f"Rated {label} (certainty: {mem.certainty}) for memory {mem.id}")]

    if name == "wake_up":
        report = search.wake_up(
            context=arguments.get("context"),
            limit=arguments.get("limit", 10),
        )
        # Compact all memory lists to avoid context blowup at session start
        compact_report = {
            "context": report["context"],
            "summary": report["summary"],
            "tattoos": [m.to_compact() for m in report["tattoos"]],
            "polaroids": [m.to_compact() for m in report["polaroids"]],
            "notes": [m.to_compact() for m in report["notes"]],
        }
        return [TextContent(type="text", text=json.dumps(compact_report, indent=2))]

    if name == "reverse_timeline":
        results = search.reverse_timeline(
            context=arguments.get("context"),
            limit=arguments.get("limit", 20),
        )
        if not results:
            return [TextContent(type="text", text="No memories found.")]
        detail = arguments.get("detail", "compact")
        if detail == "full":
            payload = [m.to_dict() for m in results]
        else:
            payload = [m.to_compact() for m in results]
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    if name == "sammy_jankis_test":
        results = search.sammy_jankis_test(
            query=arguments["query"],
            limit=arguments.get("limit", 5),
        )
        if not results:
            return [TextContent(type="text", text="No similar past memories found. This might be a new mistake.")]
        payload = [
            {
                "memory": r["memory"].to_compact(),
                "warning": r["warning"],
                "reliability": r["reliability"],
            }
            for r in results
        ]
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    if name == "follow_link":
        mem = search.resolve_link(arguments["link_target"])
        if mem is None:
            return [TextContent(type="text", text=f"No memory found for link '{arguments['link_target']}'.")]
        return [TextContent(type="text", text=json.dumps(mem.to_dict(), indent=2))]

    if name == "get_backlinks":
        links = search.get_backlinks(arguments["memory_id"])
        if not links:
            return [TextContent(type="text", text="No memories link to this one.")]
        return [TextContent(type="text", text=json.dumps(links, indent=2))]

    if name == "get_linked_entries":
        links = search.get_linked_entries(arguments["memory_id"])
        if not links:
            return [TextContent(type="text", text="This memory links to nothing.")]
        return [TextContent(type="text", text=json.dumps(links, indent=2))]

    if name == "export_vault":
        path = sync.export_vault(arguments.get("path"))
        return [TextContent(type="text", text=f"Wiki exported to: {path}")]

    if name == "import_vault":
        result = sync.import_vault(
            path=arguments["path"],
            merge_strategy=arguments.get("merge_strategy", "keep_both"),
        )
        # Rebuild index after import
        index.rebuild_index()
        return [TextContent(type="text", text=f"Import complete:\n{json.dumps(result, indent=2)}")]

    if name == "merge_vaults":
        result = sync.merge_vaults(
            path_a=arguments["path_a"],
            path_b=arguments["path_b"],
            output_path=arguments["output_path"],
            merge_strategy=arguments.get("merge_strategy", "keep_both"),
        )
        return [TextContent(type="text", text=f"Merge complete:\n{json.dumps(result, indent=2)}")]

    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    wiki.ensure_wiki()
    stats = index.rebuild_index()
    print(f"[memento] Leonard Shelby is awake. {stats['indexed_entries']} memories indexed.", flush=True)
    import asyncio
    asyncio.run(_run())


async def _run() -> None:
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())


if __name__ == "__main__":
    main()
