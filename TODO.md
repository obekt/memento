# TODO — Remaining fixes

Findings from an architectural review (2026-06-11). Already **fixed** in that pass:

- FTS5 search wrapped the whole query in one phrase — multi-keyword queries
  (`redis refused`) returned 0 hits. Now tokenized into AND-ed phrases, with
  explicit `"quoted phrases"` preserved (`index.py::_fts_query`).
- `import_vault keep_both` wrote conflict variants with the *same* frontmatter
  `id:` as the original; the duplicate PRIMARY KEY then crashed
  `rebuild_index()` at every server startup. Variants now get fresh IDs
  (`sync.py::_reassign_id`) and `rebuild_index` skips+reports duplicate/missing
  IDs instead of raising.
- Path traversal: `_safe_dir_name` kept `/`, so `context="/tmp/evil"` wrote
  outside the wiki (`WIKI_ROOT / "/tmp/evil"` == `/tmp/evil`). Now sanitized
  segment-by-segment. Zip-slip members (`../`, absolute) rejected in
  `import_vault` and `merge_vaults`.
- Data loss on move: `update_memory` unlinked the old file *before* writing the
  new one; now writes first, deletes after, and keeps `mem.slug` in sync with
  collision-renamed filenames. `_write_md` is atomic (tmp + rename).

Everything below is still open, ordered by severity.

## High

- [ ] **No SQLite concurrency safety.** `index.py::_connect` opens a fresh
  connection per call with no WAL, no `busy_timeout`, no `BEGIN IMMEDIATE`.
  MCP servers can receive concurrent tool calls; `index_memory` is a
  multi-statement read-modify-write (FTS delete by old rowid, then re-insert)
  that can interleave → `database is locked` errors or FTS desync. Fix:
  `PRAGMA journal_mode=WAL`, `busy_timeout`, and wrap mutations in
  `BEGIN IMMEDIATE`.

- [ ] **Rename/delete leaves wiki-links and backlinks stale.**
  - Renaming via `update_memory` doesn't rewrite other files' `[[old-slug]]`
    links, and their `index_links` rows are only recomputed when *those*
    sources are re-indexed.
  - Deleting a memory (`wiki.py::delete_memory` via `memory.py`) leaves all
    inbound `index_links.target_id` rows pointing at a dead ID.
  Fix: on rename/delete, update or invalidate inbound `index_links` rows
  (query `get_backlinks` first), and optionally rewrite link text in source
  files on rename.

- [ ] **No incremental file↔index sync.** README advertises editing memory
  files with `vim`, but nothing reindexes until full restart; `wiki.update_memory`
  / `wiki.delete_memory` are public and bypass the index entirely (only the
  `memory.py` wrappers sync). Fix: mtime-based incremental sync on each tool
  call (cheap: compare max mtime vs a stored watermark), or at least re-export
  only the `memory.py` wrappers.

## Medium

- [ ] **`merge_vaults` cleanup can delete user data.** `sync.py` (cleanup loop)
  `rmtree`s every subdirectory of `out_dir` — if `output_path` is e.g.
  `~/exports/merged.zip` and `~/exports` has other folders, they're destroyed.
  Fix: extract/merge in a `tempfile.TemporaryDirectory`, write only the final
  zip to `output_path`.

- [ ] **`keep_newer` naive/aware datetime comparison silently skips imports.**
  `sync.py` compares `fromisoformat("1970-01-01T00:00:00")` (naive) against
  stored timezone-aware timestamps → `TypeError`, swallowed as `skipped`.
  Fix: normalize both to aware UTC before comparing.

- [ ] **Link resolution ignores namespaces.** `index.py::_update_links` resolves
  `[[link]]` by `slug = ? OR title = ? ... LIMIT 1` with no context scoping —
  ambiguous slugs across contexts resolve to an arbitrary entry, defeating the
  "body parts avoid collision" premise. Fix: prefer same-context matches, then
  global; surface ambiguity.

- [ ] **Forward references never resolve.** Links to memories created *later*
  keep `target_id = NULL` until a full rebuild. Fix: on `index_memory`, also
  re-resolve `index_links` rows whose `link_text` matches the new entry's
  slug/title.

- [ ] **`read_resource` URI handling.** `server.py` compares the MCP `AnyUrl`
  against `str` (`uri == "memento://guide"`), and the `memento://context/...`
  route is never advertised by `list_resources`. Tests call the handler with
  plain strings, masking this. Fix: `str(uri)` normalization + advertise or
  remove the context route.

- [ ] **Tattoo immutability TOCTOU.** `memory.py::burn` does recall-then-delete
  non-atomically, and `update_memory(certainty=0)` can effectively neuter a
  tattoo. Decide and document what "permanent" guarantees actually are.

## Low

- [ ] **`_cleanup_empty_dirs` can rmdir the wiki root** when the wiki empties
  (loop reassigns `d = d.parent` after successful rmdir; guard checks stale `d`).
- [ ] **Tag merge is a one-way ratchet.** `wiki.py::update_memory` unions old
  tags + inline tags whenever content is updated — tags can never be removed
  together with a content change.
- [ ] **Search drops stale hits silently.** `search.py` re-reads each hit from
  disk and skips missing files — results shrink below `limit` with no warning
  (N+1 file reads, too).
- [ ] **`parse_inline_tags` hex-exclusion rejects real tags** like `#cafe`,
  `#added` (matches `[0-9a-fA-F]{3,8}`); the `startswith("http")` check is
  effectively dead code.
- [ ] **Fallback context/topic derivation in `_read_md`** breaks for files
  directly under a context dir or at wiki root.
- [ ] **`rebuild_index` uses `DELETE FROM fts_entries`** on an external-content
  FTS5 table; the canonical idiom is the `'delete-all'` command.
- [ ] **Test gaps:** no concurrency tests, no malformed-frontmatter tests, no
  rename-backlink tests; `test_server.py` calls handlers with `str` URIs
  instead of `AnyUrl`.
