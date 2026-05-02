# Contributing to Memento

Thanks for your interest! Memento is designed to be small, focused, and hackable.

## Development Setup

```bash
git clone <repo-url>
cd memento
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Project Structure

```
src/memento/
  db.py       — SQLite schema and FTS5 setup
  memory.py   — CRUD for tattoos, polaroids, notes
  search.py   — Full-text search, backlinks, timeline
  sync.py     — Export/import/merge (JSON Lines, markdown)
  server.py   — MCP server with all tools
tests/
  conftest.py — Shared fixtures (temp DB per test)
  test_*.py   — One test file per module
```

## Adding a New Tool

1. Add the tool logic to the appropriate module (`memory.py`, `search.py`, etc.)
2. Register it in `server.py`:
   - Add a `Tool(...)` to `list_tools()`
   - Add a handler to `call_tool()`
3. Add tests in `tests/test_server.py` and the relevant module test file
4. Update the README if it's a user-facing feature

## Adding a Memory Type

The three types (`tattoo`, `polaroid`, `note`) are hardcoded in the schema:

```sql
kind TEXT NOT NULL CHECK(kind IN ('tattoo', 'polaroid', 'note'))
```

To add a new type (e.g. `recording`):

1. Update the `CHECK` constraint in `db.py`
2. Add a convenience function in `memory.py`
3. Add a server tool in `server.py`
4. Update `wake_up()` in `search.py` to include the new kind

## Code Style

- Keep it simple. Memento is intentionally small.
- Add tests for every new feature.
- Tool descriptions should be exhaustive — they are the documentation.

## Testing

```bash
pytest                    # Run all tests
pytest -v                 # Verbose
pytest tests/test_memory.py -v   # Single file
pytest -k test_burn       # Filter by name
```

Tests use temporary databases (see `tests/conftest.py`), so they won't touch your real `~/.memento/memento.db`.

## Pull Request Checklist

- [ ] Tests pass (`pytest`)
- [ ] New features have tests
- [ ] Tool descriptions are clear and exhaustive
- [ ] README updated if user-facing
