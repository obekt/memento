# Memento

> *"Every 5 minutes, your coding agent forgets everything. It doesn't remember the architecture. It doesn't remember the bug from yesterday. It doesn't remember why that workaround exists."*
>
> *Your agent is Leonard Shelby. This is its tattoo parlor.*

[![Tests](https://github.com/obekt/memento/actions/workflows/test.yml/badge.svg)](https://github.com/obekt/memento/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A zero-config, self-documenting local MCP server that gives your coding agent persistent memory.**

Inspired by Christopher Nolan's *Memento* (2000).

---

## The Problem

You pay $20/month for an AI that writes code. Then you open a new chat, and:

- ❌ It forgot the architecture decisions from yesterday
- ❌ It re-introduces the bug you fixed last week
- ❌ It asks "what framework are we using?" for the 47th time
- ❌ Your carefully crafted system prompt is a band-aid, not a brain

**Your agent has anterograde amnesia.** Every session is a blank slate.

## The Solution

Memento stores knowledge as **markdown files** that survive across sessions. When connected to your MCP-aware IDE (Cursor, Claude Desktop, Windsurf, VS Code), your agent can:

- 🔥 **`tattoo()`** — Burn permanent facts into its skin (architecture, APIs, contracts)
- 📸 **`snap()`** — Take Polaroids of errors with captions (error + fix)
- 📝 **`scribble()`** — Jot temporary notes (TODOs, hypotheses)
- 🧠 **`wake_up()`** — Reconstruct context at the start of every session
- 🔍 **`sammy_jankis_test()`** — Detect repeated mistakes before you make them again

**No API keys. No ports. No cloud. No setup.** The agent reads the tool names and knows what to do.

---

## Quick Start (30 seconds)

```bash
# Install globally so your IDE can find it
pipx install memento-mcp
# or: uv tool install memento-mcp
```

Add to your MCP client:

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "memento": {
      "command": "memento"
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "memento": {
      "command": "memento"
    }
  }
}
```

**VS Code** (settings.json):
```json
{
  "mcp": {
    "servers": {
      "memento": {
        "command": "memento",
        "type": "stdio"
      }
    }
  }
}
```

Restart your IDE. Tell your agent: *"Wake up and check your tattoos."* It will.

---

## Storage: Markdown Files = Source of Truth

```
~/.memento/
  wiki/
    chest/
      architecture/
        db-choice.md
        api-design.md
    left_arm/
      bugs/
        redis-down.md
    hand/
      todo/
        refactor-auth.md
  .index.db   # SQLite FTS5 index (rebuildable, disposable)
```

Every memory is a **human-readable `.md` file** with YAML frontmatter. The SQLite database is just a search index — if it breaks, delete it and it regenerates. Your data is safe in the files.

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
---

Use SQLite with FTS5 for full-text search. Single file, millions of rows.

See also [[left_arm/bugs/redis-down]] for related issues.

#scaling #decision
```

- **Human-readable**: Open any file in your editor
- **Git-friendly**: `git diff` shows meaningful changes
- **Linkable**: `[[wiki-link]]` connects entries into a knowledge graph
- **Taggable**: `#hashtags` inline + frontmatter tags
- **No lock-in**: If Memento disappears, you still have your markdown files

---

## The Three Memory Systems

Leonard Shelby uses three systems with different reliability levels:

| Type | Movie | Reliability | Tool | Use For |
|------|-------|-------------|------|---------|
| **Tattoo** | Burned into skin | 🔒 Permanent, immutable | `tattoo()` | Architecture, APIs, critical bugs |
| **Polaroid** | Photo + back caption | 📸 Context-rich | `snap()` | Errors, terminal output, state |
| **Note** | Scribbled scrap | 📝 Temporary | `scribble()` | TODOs, hypotheses, quick thoughts |

> *"Tattoos are forever. Notes can be wrong. Natalie writes lies on Polaroids."*

---

## Context = Body Part (Namespaces)

Same topic name in different projects? No collision. Body parts are namespaces:

- **`chest/`** — Core facts. Always visible. Architecture, contracts.
- **`left_arm/`**, **`right_arm/`** — Working context. Current project, current bug.
- **`hand/`** — Immediate reminders. "SHAVE."
- **`thigh/`** — Deep background. Research, references.
- **`back/`** — Hidden assumptions. Things you can't see yourself.

Example: `chest/memento/architecture` vs `left_arm/client-x/architecture` — unambiguous.

---

## Real Workflow

### Start every session with context

```
Agent: wake_up(context="left_arm")
Memento: {
  "tattoos": [
    { "title": "Auth Flow", "preview": "JWT in httpOnly cookie, refresh token rotated..." },
    { "title": "DB Schema", "preview": "Users table has soft-delete via deleted_at..." }
  ],
  "polaroids": [
    { "title": "Redis Down", "preview": "Connection refused port 6379. Fix: docker-compose up redis" }
  ],
  "notes": [
    { "title": "TODO", "preview": "Refactor auth middleware before shipping v2" }
  ]
}
```

### When you make a decision that matters

```
Agent: tattoo(
  context="chest",
  topic="memento/architecture",
  content="Use SQLite with FTS5 for search. Markdown files are source of truth. Index is disposable.",
  title="Storage Design"
)
Memento: Tattooed on chest: 'Storage Design' (ID: ..., permanent)
```

### When you hit an error you'll hit again

```
Agent: snap(
  context="left_arm",
  topic="bugs/redis",
  content="ConnectionRefusedError: port 6379",
  caption="Redis is down. Run: docker-compose up redis",
  title="Redis Down"
)
```

### When you might be repeating yourself

```
Agent: sammy_jankis_test("Connection refused on port 6379")
Memento: [
  { "memory": { "title": "Redis Down", "preview": "Connection refused port 6379..." },
    "warning": "Repeated pattern detected",
    "reliability": 1.0 }
]
```

Named after Sammy Jankis — the man who accidentally killed his wife by giving her too much insulin because he couldn't remember he'd already given her a shot. **Don't be Sammy.**

---

## Complete Tool Reference

| Tool | Purpose |
|------|---------|
| `get_memento_guide` | Self-documentation. Read this first. |
| `tattoo` | Burn a permanent fact. |
| `snap` | Take a Polaroid (content + caption). |
| `scribble` | Jot a temporary note. |
| `recall` | Fetch a memory by ID (full content). |
| `search_memories` | FTS5 full-text search with filters. |
| `list_contexts` | List body parts (namespaces). |
| `list_topics` | List topics, filtered by context. |
| `get_topic` | Browse memories in a topic (compact previews). |
| `examine_tattoos` | List permanent facts. |
| `update_memory` | Modify an existing memory. |
| `burn_note` | Destroy a note or polaroid. Tattoos survive. |
| `fact_or_fiction` | Rate memory reliability (0.0–1.0). |
| `wake_up` | Reconstruct context. "Where am I?" |
| `reverse_timeline` | View memories backward (like the movie). |
| `sammy_jankis_test` | "Am I repeating the same mistake?" |
| `follow_link` | Resolve a `[[wiki-link]]`. |
| `get_backlinks` | Who references this memory? |
| `export_vault` | Backup the wiki to a `.zip` file. |
| `import_vault` | Import with merge strategies. |
| `merge_vaults` | Merge two exports offline. |

---

## Scale & Performance

```
~/.memento/wiki/     # Markdown files (source of truth)
~/.memento/.index.db # SQLite FTS5 index (rebuildable)
```

- **FTS5 search** in <1ms
- **10,000 entries** reindex in ~1 second
- **Millions of rows** possible
- **Zip export** — just markdown files, no giant JSON blobs

---

## Backup & Sync

```bash
# Quick backup — just copy the wiki directory
cp -r ~/.memento/wiki ~/memento-backup-$(date +%Y%m%d)

# Or export via tool
export_vault(path="~/backup.zip")

# Import on another machine
import_vault(path="~/backup.zip", merge_strategy="keep_both")
```

---

## Development

```bash
git clone https://github.com/obekt/memento
cd memento
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Why "Memento"?

Because your agent wakes up every session like Leonard Shelby — confused, contextless, and desperate for clues. It checks the mirror. It reads its tattoos. It looks at its Polaroids. And slowly, it remembers who it is and what it's doing.

**Give it tattoos.**

---

*"I have to believe in a world outside my own mind. I have to believe that my actions still have meaning, even if I can't remember them."* — Leonard Shelby
