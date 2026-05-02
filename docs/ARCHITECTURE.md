# Memento Architecture

## Overview

Memento is a **markdown-native** local MCP server. Every memory is a `.md` file with YAML frontmatter. SQLite is used only as a **rebuildable search index**.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   MCP Client    │────▶│  Memento Server  │────▶│   Markdown Wiki │
│  (Cursor, etc)  │◀────│   (server.py)    │◀────│   (source of    │
└─────────────────┘     └──────────────────┘     │    truth)       │
                               │                  └─────────────────┘
                               ▼                           ▲
                        ┌──────────────────┐              │
                        │  SQLite FTS5     │──────────────┘
                        │  Search Index    │   (rebuildable)
                        └──────────────────┘
```

## Source of Truth: Markdown Files

The wiki lives at `~/.memento/wiki/{context}/{topic}/{slug}.md`.

Each file has YAML frontmatter + markdown body:

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

**Key rule**: Content is always read from the markdown file, never from the index.

## Search Index: SQLite FTS5

The index at `~/.memento/.index.db` is **disposable**. If it corrupts or gets out of sync:

```python
from memento import index
index.rebuild_index()  # Re-scan all markdown files
```

### Schema

```sql
-- Cached metadata + text for FTS5
CREATE TABLE index_entries (
    id TEXT PRIMARY KEY,
    kind TEXT,
    context TEXT,
    topic TEXT,
    slug TEXT,
    title TEXT,
    content TEXT,
    caption TEXT,
    path TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);

-- FTS5 virtual table (external content, manually synced)
CREATE VIRTUAL TABLE fts_entries USING fts5(
    title, content, caption,
    content='index_entries', content_rowid='rowid'
);

-- Tags
CREATE TABLE index_tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE index_entry_tags (entry_id TEXT, tag_id INTEGER);

-- Wiki-link graph
CREATE TABLE index_links (source_id TEXT, target_id TEXT, link_text TEXT);
```

**No triggers** — the index is kept in sync explicitly by `wiki.py` / `memory.py` on every write.

## Modules

| Module | Responsibility |
|--------|---------------|
| `wiki.py` | Read/write `.md` files, parse frontmatter, manage directory structure |
| `index.py` | SQLite FTS5 index, tags, links, search queries |
| `memory.py` | Orchestration — write `.md` then update index |
| `search.py` | High-level search, backlinks, wake_up, timeline |
| `sync.py` | Zip export/import/merge (no JSON!) |
| `server.py` | MCP protocol, 20+ movie-themed tools |

## Memory Types

### Tattoo (`kind='tattoo'`)
- Written to `.md` file like any other memory
- `burn_note()` refuses to delete it
- Use for architecture decisions, API contracts, critical facts

### Polaroid (`kind='polaroid'`)
- Has `content` (what you see) and `caption` (back-of-photo meaning)
- Can be deleted
- Use for errors, terminal output, state snapshots

### Note (`kind='note'`)
- Simplest type
- Easy to create, easy to burn
- Use for TODOs, temporary hypotheses

## Context = Body Part = Namespace

Contexts are directory names under `wiki/`. Topics are subdirectories.

```
wiki/
  chest/
    architecture/
      db-choice.md
  left_arm/
    project-x/
      setup.md
      auth.md
```

This solves topic disambiguation naturally — `chest/architecture` and `left_arm/architecture` are different files.

## Export / Import

### Export

`export_vault()` creates a `.zip` of the entire `wiki/` directory. No JSON serialization. Just the markdown files.

### Import

`import_vault()` unpacks a `.zip` and applies merge strategies at the file level:

| Strategy | Behavior |
|----------|----------|
| `keep_both` | `entry.md` + `entry.imported.md` |
| `keep_newer` | Compare `updated_at` in frontmatter |
| `keep_mine` | Skip existing files |
| `keep_theirs` | Overwrite existing files |

### Merge

`merge_vaults()` merges two `.zip` exports into a new `.zip` without touching the live wiki.

## Scalability

- **Markdown files**: Limited by filesystem (thousands of files per directory is fine)
- **FTS5 index**: Handles millions of rows, sub-second search
- **Rebuild**: Full reindex of 10,000 files takes ~1 second

## MCP Protocol

Memento speaks the [Model Context Protocol](https://modelcontextprotocol.io/) over stdio.

### Resources

- `memento://guide` — usage guide
- `memento://contexts` — list of body parts
- `memento://context/{name}` — topics in a context

### Tools

20+ tools. Each has an exhaustive description — they are their own documentation.
