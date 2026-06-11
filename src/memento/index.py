"""Rebuildable SQLite search index for the markdown wiki."""

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from memento.wiki import WIKI_ROOT, Memory, scan_wiki, parse_links

INDEX_PATH = Path.home() / ".memento" / ".index.db"


def _connect() -> sqlite3.Connection:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    # autocommit mode (isolation_level=None): we control transactions
    # explicitly via _write_txn for multi-statement mutations.
    conn = sqlite3.connect(str(INDEX_PATH), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # MCP servers can receive concurrent tool calls; WAL allows readers
    # alongside a writer, busy_timeout makes writers wait instead of
    # failing with 'database is locked'.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def _write_txn(conn: sqlite3.Connection):
    """Run a multi-statement mutation atomically.

    BEGIN IMMEDIATE takes the write lock up front so read-modify-write
    sequences (e.g. FTS delete by old rowid, then re-insert) can't
    interleave with another writer and desync the FTS index.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def init_index() -> None:
    """Initialize the index schema. No triggers — we sync explicitly from files."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_entries (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                context TEXT NOT NULL,
                topic TEXT NOT NULL,
                slug TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                caption TEXT,
                certainty REAL DEFAULT 1.0,
                source TEXT DEFAULT '',
                image_path TEXT DEFAULT '',
                path TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_entries USING fts5(
                title, content, caption,
                content='index_entries', content_rowid='rowid'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_entry_tags (
                entry_id TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (entry_id, tag_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_links (
                source_id TEXT NOT NULL,
                target_id TEXT,
                link_text TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_ie_kind ON index_entries(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ie_context ON index_entries(context)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ie_topic ON index_entries(topic)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ie_updated ON index_entries(updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_il_source ON index_links(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_il_target ON index_links(target_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_iet_entry ON index_entry_tags(entry_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_iet_tag ON index_entry_tags(tag_id)")

        conn.commit()


def _row_to_memory(row: sqlite3.Row) -> Memory:
    from memento.wiki import Memory
    return Memory(
        id=row["id"],
        kind=row["kind"],
        context=row["context"],
        topic=row["topic"],
        slug=row["slug"],
        title=row["title"] or "",
        content=row["content"],
        caption=row["caption"] or "",
        certainty=row["certainty"] if row["certainty"] is not None else 1.0,
        source=row["source"] or "",
        image_path=row["image_path"] or "",
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
        path=Path(row["path"]) if row["path"] else None,
    )


def _set_tags(conn: sqlite3.Connection, entry_id: str, tags: list[str]) -> None:
    conn.execute("DELETE FROM index_entry_tags WHERE entry_id = ?", (entry_id,))
    for tag in set(tags):
        conn.execute("INSERT OR IGNORE INTO index_tags (name) VALUES (?)", (tag,))
        row = conn.execute("SELECT id FROM index_tags WHERE name = ?", (tag,)).fetchone()
        if row:
            conn.execute(
                "INSERT OR IGNORE INTO index_entry_tags (entry_id, tag_id) VALUES (?, ?)",
                (entry_id, row["id"]),
            )


def _update_links(conn: sqlite3.Connection, memory: Memory) -> None:
    conn.execute("DELETE FROM index_links WHERE source_id = ?", (memory.id,))
    for link_text in parse_links(memory.content):
        target = conn.execute(
            "SELECT id FROM index_entries WHERE slug = ? OR topic || '/' || slug = ? OR title = ? LIMIT 1",
            (link_text, link_text, link_text),
        ).fetchone()
        target_id = target["id"] if target else None
        conn.execute(
            "INSERT INTO index_links (source_id, target_id, link_text) VALUES (?, ?, ?)",
            (memory.id, target_id, link_text),
        )


def index_memory(memory: Memory, path: Path) -> None:
    """Add or update a single memory in the index."""
    init_index()
    with _connect() as conn, _write_txn(conn):
        # Get old rowid + content for FTS delete if updating
        old = conn.execute(
            "SELECT rowid, title, content, caption FROM index_entries WHERE id = ?",
            (memory.id,),
        ).fetchone()
        if old:
            conn.execute(
                "INSERT INTO fts_entries(fts_entries, rowid, title, content, caption) VALUES ('delete', ?, ?, ?, ?)",
                (old["rowid"], old["title"], old["content"], old["caption"]),
            )

        conn.execute("DELETE FROM index_entries WHERE id = ?", (memory.id,))
        conn.execute("DELETE FROM index_links WHERE source_id = ?", (memory.id,))
        conn.execute("DELETE FROM index_entry_tags WHERE entry_id = ?", (memory.id,))

        cur = conn.execute(
            """
            INSERT INTO index_entries (id, kind, context, topic, slug, title, content, caption,
                                      certainty, source, image_path, path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id, memory.kind, memory.context, memory.topic, memory.slug,
                memory.title, memory.content, memory.caption,
                memory.certainty, memory.source, memory.image_path, str(path),
                memory.created_at, memory.updated_at,
            ),
        )
        # Sync FTS5
        conn.execute(
            "INSERT INTO fts_entries(rowid, title, content, caption) VALUES (?, ?, ?, ?)",
            (cur.lastrowid, memory.title, memory.content, memory.caption),
        )
        _set_tags(conn, memory.id, memory.tags)
        _update_links(conn, memory)
        # Retro-resolve dangling links that point at this (possibly new)
        # memory by slug, topic/slug, or title — forward references and
        # renames would otherwise stay unresolved until a full rebuild.
        conn.execute(
            """
            UPDATE index_links SET target_id = ?
            WHERE target_id IS NULL
              AND (link_text = ? OR link_text = ? OR (? != '' AND link_text = ?))
            """,
            (
                memory.id,
                memory.slug,
                f"{memory.topic}/{memory.slug}",
                memory.title,
                memory.title,
            ),
        )
        _store_signature(conn)


def deindex_memory(memory_id: str) -> None:
    """Remove a memory from the index."""
    init_index()
    with _connect() as conn, _write_txn(conn):
        old = conn.execute("SELECT rowid, title, content, caption FROM index_entries WHERE id = ?", (memory_id,)).fetchone()
        if old:
            conn.execute(
                "INSERT INTO fts_entries(fts_entries, rowid, title, content, caption) VALUES ('delete', ?, ?, ?, ?)",
                (old["rowid"], old["title"], old["content"], old["caption"]),
            )
        conn.execute("DELETE FROM index_entries WHERE id = ?", (memory_id,))
        conn.execute("DELETE FROM index_links WHERE source_id = ?", (memory_id,))
        conn.execute("DELETE FROM index_entry_tags WHERE entry_id = ?", (memory_id,))
        # Inbound links now dangle: mark them unresolved instead of
        # leaving target_id pointing at a dead memory (get_backlinks of
        # the deleted id would otherwise still return "live" results).
        conn.execute(
            "UPDATE index_links SET target_id = NULL WHERE target_id = ?",
            (memory_id,),
        )
        _store_signature(conn)


def rebuild_index() -> dict[str, Any]:
    """Full rebuild of the index from the wiki directory.

    Tolerant of bad data: files with a missing or duplicate frontmatter
    `id:` are skipped (and reported) instead of crashing the server at
    startup with an IntegrityError.
    """
    init_index()
    memories = scan_wiki()
    skipped: list[str] = []
    seen_ids: set[str] = set()
    indexed: list[Memory] = []
    for memory in memories:
        if not memory.id or memory.id in seen_ids:
            skipped.append(str(memory.path) if memory.path else memory.slug)
            continue
        seen_ids.add(memory.id)
        indexed.append(memory)
    memories = indexed
    with _connect() as conn, _write_txn(conn):
        conn.execute("DELETE FROM index_entries")
        # External-content FTS5 tables must be cleared with the special
        # 'delete-all' command — a plain DELETE leaves stale tokens in the
        # inverted index that then match against reused rowids.
        conn.execute("INSERT INTO fts_entries(fts_entries) VALUES ('delete-all')")
        conn.execute("DELETE FROM index_links")
        conn.execute("DELETE FROM index_entry_tags")
        conn.execute("DELETE FROM index_tags")
        for memory in memories:
            cur = conn.execute(
                """
                INSERT INTO index_entries (id, kind, context, topic, slug, title, content, caption,
                                          certainty, source, image_path, path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id, memory.kind, memory.context, memory.topic, memory.slug,
                    memory.title, memory.content, memory.caption,
                    memory.certainty, memory.source, memory.image_path,
                    str(memory.path) if memory.path else "",
                    memory.created_at, memory.updated_at,
                ),
            )
            conn.execute(
                "INSERT INTO fts_entries(rowid, title, content, caption) VALUES (?, ?, ?, ?)",
                (cur.lastrowid, memory.title, memory.content, memory.caption),
            )
            _set_tags(conn, memory.id, memory.tags)
        # Now resolve links (second pass so all entries exist)
        for memory in memories:
            _update_links(conn, memory)
        _store_signature(conn)
    result: dict[str, Any] = {
        "indexed_entries": len(memories),
        "links": sum(len(parse_links(m.content)) for m in memories),
    }
    if skipped:
        result["skipped_files"] = skipped
    return result


def _wiki_signature() -> str:
    """Cheap fingerprint of the wiki's on-disk state: file count + newest mtime.

    Used to detect external edits (vim, git pull, rsync) so the index can
    resync without a server restart. Note: mtime granularity is filesystem
    dependent (~1s worst case), so a same-second in-place edit with an
    unchanged file count may be missed — acceptable for the vim use case.
    """
    latest = 0.0
    count = 0
    if WIKI_ROOT.exists():
        for p in WIKI_ROOT.rglob("*.md"):
            count += 1
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > latest:
                latest = m
    return f"{count}:{latest}"


def _store_signature(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('wiki_signature', ?)",
        (_wiki_signature(),),
    )


def sync_if_stale() -> bool:
    """Rebuild the index if wiki files changed outside Memento.

    The README advertises editing memory files directly with vim; without
    this, such edits were invisible until a full server restart. Called
    before serving tool requests. Returns True if a rebuild happened.
    """
    init_index()
    sig = _wiki_signature()
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM index_meta WHERE key = 'wiki_signature'"
        ).fetchone()
    if row and row["value"] == sig:
        return False
    rebuild_index()
    return True


def index_stats() -> dict[str, Any]:
    init_index()
    with _connect() as conn:
        entries = conn.execute("SELECT COUNT(*) as c FROM index_entries").fetchone()["c"]
        links = conn.execute("SELECT COUNT(*) as c FROM index_links").fetchone()["c"]
        tags = conn.execute("SELECT COUNT(*) as c FROM index_tags").fetchone()["c"]
        return {"entries": entries, "links": links, "tags": tags}


def _fts_query(query: str) -> str:
    """Turn free-text user input into a safe FTS5 MATCH expression.

    Each whitespace-separated token becomes its own quoted phrase; phrases
    are joined by implicit AND. User-supplied double quotes are preserved
    as explicit phrases ("redis error" docker → "redis error" AND "docker").

    The previous implementation wrapped the ENTIRE query in one phrase,
    which made multi-keyword search return zero results unless the words
    were adjacent and in order.
    """
    tokens: list[str] = []
    # re.split with one capture group alternates outside/inside quotes:
    # pieces[0::2] are outside quotes, pieces[1::2] are inside quotes.
    pieces = re.split(r'"([^"]*)"', query)
    for i, piece in enumerate(pieces):
        piece = piece.strip()
        if not piece:
            continue
        if i % 2 == 1:
            # Inside quotes — keep as a single phrase
            tokens.append('"' + piece.replace('"', '""') + '"')
        else:
            for word in piece.split():
                tokens.append('"' + word.replace('"', '""') + '"')

    return " ".join(tokens)


def search(
    query: str,
    kind: str | None = None,
    context: str | None = None,
    topic: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[Memory]:
    """Full-text search using FTS5, with optional filters."""
    init_index()
    safe_query = _fts_query(query)
    if not safe_query:
        return []
    with _connect() as conn:
        sql = """
            SELECT e.* FROM index_entries e
            JOIN fts_entries fts ON e.rowid = fts.rowid
            WHERE fts_entries MATCH ?
        """
        params: list[Any] = [safe_query]

        if kind:
            sql += " AND e.kind = ?"
            params.append(kind)
        if context:
            sql += " AND e.context = ?"
            params.append(context)
        if topic:
            sql += " AND e.topic = ?"
            params.append(topic)

        if tags:
            placeholders = ",".join("?" * len(tags))
            sql += f"""
                AND e.id IN (
                    SELECT entry_id FROM index_entry_tags
                    JOIN index_tags ON index_entry_tags.tag_id = index_tags.id
                    WHERE index_tags.name IN ({placeholders})
                    GROUP BY entry_id
                    HAVING COUNT(DISTINCT index_tags.name) = ?
                )
            """
            params.extend(tags)
            params.append(len(tags))

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_memory(r) for r in rows]


def get_linked_entries(memory_id: str) -> list[dict[str, Any]]:
    """Return memories that the given memory links out to."""
    init_index()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT e.*, l.link_text
            FROM index_links l
            LEFT JOIN index_entries e ON l.target_id = e.id
            WHERE l.source_id = ?
            """,
            (memory_id,),
        ).fetchall()
        return [
            {
                "link_text": r["link_text"],
                "resolved": r["id"] is not None,
                "memory_id": r["id"],
                "context": r["context"],
                "topic": r["topic"],
                "slug": r["slug"],
                "title": r["title"],
            }
            for r in rows
        ]


def get_backlinks(memory_id: str) -> list[dict[str, Any]]:
    """Return memories that link TO the given memory."""
    init_index()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT e.id, e.context, e.topic, e.slug, e.title, e.kind
            FROM index_links l
            JOIN index_entries e ON l.source_id = e.id
            WHERE l.target_id = ?
            """,
            (memory_id,),
        ).fetchall()
        return [
            {
                "memory_id": r["id"],
                "context": r["context"],
                "topic": r["topic"],
                "slug": r["slug"],
                "title": r["title"],
                "kind": r["kind"],
            }
            for r in rows
        ]


def resolve_link(link_target: str) -> Memory | None:
    """Resolve a [[wiki-link]] target to a memory."""
    init_index()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM index_entries WHERE slug = ?", (link_target,)
        ).fetchone()
        if row:
            return _row_to_memory(row)
        if "/" in link_target:
            topic, slug = link_target.rsplit("/", 1)
            row = conn.execute(
                "SELECT * FROM index_entries WHERE topic = ? AND slug = ?",
                (topic, slug),
            ).fetchone()
            if row:
                return _row_to_memory(row)
        row = conn.execute(
            "SELECT * FROM index_entries WHERE title = ?", (link_target,)
        ).fetchone()
        if row:
            return _row_to_memory(row)
    return None


def get_tags_for_entry(memory_id: str) -> list[str]:
    init_index()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT t.name FROM index_tags t
            JOIN index_entry_tags et ON t.id = et.tag_id
            WHERE et.entry_id = ?
            ORDER BY t.name
            """,
            (memory_id,),
        ).fetchall()
        return [r["name"] for r in rows]


def list_all_contexts() -> list[str]:
    init_index()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT context, MAX(updated_at) as last_update
            FROM index_entries
            GROUP BY context
            ORDER BY last_update DESC
            """
        ).fetchall()
        return [r["context"] for r in rows]


def list_all_topics(context: str | None = None) -> list[str]:
    init_index()
    with _connect() as conn:
        if context:
            rows = conn.execute(
                """
                SELECT topic, MAX(updated_at) as last_update
                FROM index_entries
                WHERE context = ?
                GROUP BY topic
                ORDER BY last_update DESC
                """,
                (context,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT topic, MAX(updated_at) as last_update
                FROM index_entries
                GROUP BY topic
                ORDER BY last_update DESC
                """
            ).fetchall()
        return [r["topic"] for r in rows]


def get_entries_by_topic(context: str, topic: str, limit: int = 50) -> list[Memory]:
    init_index()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM index_entries
            WHERE context = ? AND topic = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (context, topic, limit),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]


def get_tattoos(context: str | None = None, limit: int = 100) -> list[Memory]:
    init_index()
    with _connect() as conn:
        if context:
            rows = conn.execute(
                """
                SELECT * FROM index_entries
                WHERE kind = 'tattoo' AND context = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (context, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM index_entries
                WHERE kind = 'tattoo'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_memory(r) for r in rows]


def summarize(context: str, topic: str) -> dict[str, Any]:
    init_index()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) as count, MAX(updated_at) as last_update, MIN(created_at) as first_created
            FROM index_entries
            WHERE context = ? AND topic = ?
            """,
            (context, topic),
        ).fetchone()
        kind_rows = conn.execute(
            "SELECT kind, COUNT(*) as c FROM index_entries WHERE context = ? AND topic = ? GROUP BY kind",
            (context, topic),
        ).fetchall()
        tag_rows = conn.execute(
            """
            SELECT DISTINCT t.name
            FROM index_tags t
            JOIN index_entry_tags et ON t.id = et.tag_id
            JOIN index_entries e ON et.entry_id = e.id
            WHERE e.context = ? AND e.topic = ?
            ORDER BY t.name
            """,
            (context, topic),
        ).fetchall()
        return {
            "context": context,
            "topic": topic,
            "memory_count": row["count"] if row else 0,
            "first_created": row["first_created"] if row else None,
            "last_update": row["last_update"] if row else None,
            "by_kind": {r["kind"]: r["c"] for r in kind_rows},
            "tags": [r["name"] for r in tag_rows],
        }


def get_entries_by_kind(kind: str, context: str | None = None, limit: int = 50) -> list[Memory]:
    """Return entries of a specific kind, optionally filtered by context."""
    init_index()
    with _connect() as conn:
        sql = "SELECT * FROM index_entries WHERE kind = ?"
        params: list[Any] = [kind]
        if context:
            sql += " AND context = ?"
            params.append(context)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_memory(r) for r in rows]


def get_recent_entries(context: str | None = None, limit: int = 20) -> list[Memory]:
    """Return entries in reverse chronological order (newest first)."""
    init_index()
    with _connect() as conn:
        sql = "SELECT * FROM index_entries WHERE 1=1"
        params: list[Any] = []
        if context:
            sql += " AND context = ?"
            params.append(context)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_memory(r) for r in rows]


def find_memory_path(memory_id: str) -> str | None:
    """Look up a memory's file path by ID using the index (O(1) instead of O(n) scan)."""
    init_index()
    with _connect() as conn:
        row = conn.execute(
            "SELECT path FROM index_entries WHERE id = ?", (memory_id,)
        ).fetchone()
        if row and row["path"]:
            return row["path"]
    return None
