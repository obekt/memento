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

Fixed in a second pass (all High items):

- **SQLite concurrency safety** — `index.py::_connect` now enables WAL,
  `busy_timeout=10s`, and all multi-statement mutations (`index_memory`,
  `deindex_memory`, `rebuild_index`) run inside `BEGIN IMMEDIATE`
  transactions (`index.py::_write_txn`). Verified with a concurrent-writes
  test.
- **Stale links on rename/delete** — `deindex_memory` now nulls inbound
  `index_links.target_id` (backlinks of a deleted memory disappear instead
  of resolving to a dead ID); `memory.update` rewrites `[[old-slug]]` link
  text in source files and re-indexes them when a rename/move changes
  slug/topic (`memory.py::_rewrite_inbound_links`); `index_memory`
  retro-resolves dangling links, so forward references resolve as soon as
  the target is created.
- **External edit sync** — `index.py::sync_if_stale()` fingerprints the wiki
  (file count + newest mtime, stored in new `index_meta` table) and rebuilds
  the index when files were edited outside Memento (vim, git pull). Called
  at the top of every `call_tool` dispatch and the `memento://contexts`
  resource. Fixing this also surfaced that `rebuild_index`'s
  `DELETE FROM fts_entries` left stale tokens in the external-content FTS
  index — now uses the canonical `'delete-all'` command.

Everything below is still open, ordered by severity.

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
- [ ] **Test gaps:** no malformed-frontmatter tests; `test_server.py` calls
  handlers with `str` URIs instead of `AnyUrl`.
