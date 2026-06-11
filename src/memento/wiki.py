"""Markdown-native wiki: source of truth for Memento memories."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

WIKI_ROOT = Path.home() / ".memento" / "wiki"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "-", s)
    return s[:64] or "untitled"


def _safe_dir_name(text: str) -> str:
    """Convert text to a filesystem-safe directory name.

    Path separators are normalized away segment-by-segment so the result
    can never be absolute or contain `..` — `Path.home() / "/tmp/evil"`
    silently resolves to /tmp/evil, so this must be airtight.
    """
    s = text.lower().strip()
    segments = []
    for seg in s.split("/"):
        seg = re.sub(r"[^\w\s-]", "", seg)
        seg = re.sub(r"[-\s]+", "-", seg).strip("-")
        # Drop empty segments (from leading/double slashes) and any
        # dot-only segments that survived sanitization.
        if seg and seg.strip(".") and seg not in (".", ".."):
            segments.append(seg)
    return "/".join(segments) or "default"


@dataclass
class Memory:
    id: str
    kind: str
    context: str
    topic: str
    slug: str
    title: str
    content: str
    caption: str = ""
    certainty: float = 1.0
    image_path: str = ""
    source: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "context": self.context,
            "topic": self.topic,
            "slug": self.slug,
            "title": self.title,
            "content": self.content,
            "caption": self.caption,
            "certainty": self.certainty,
            "image_path": self.image_path,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "path": str(self.path) if self.path else None,
        }

    def to_compact(self) -> dict[str, Any]:
        """Compact view for listings — prevents context blowup."""
        text = self.content or self.caption or ""
        preview = text[:200].replace("\n", " ") if text else ""
        if len(text) > 200:
            preview += "..."
        return {
            "id": self.id,
            "kind": self.kind,
            "context": self.context,
            "topic": self.topic,
            "slug": self.slug,
            "title": self.title,
            "preview": preview,
            "tags": self.tags,
            "certainty": self.certainty,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _memory_path(context: str, topic: str, slug: str) -> Path:
    """Build the file path for a memory."""
    parts = [_safe_dir_name(p) for p in topic.split("/")]
    d = WIKI_ROOT / _safe_dir_name(context)
    for p in parts:
        d = d / p
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_slugify(slug)}.md"


def _write_md(path: Path, memory: Memory) -> None:
    """Serialize a memory to a markdown file with YAML frontmatter."""
    frontmatter = {
        "id": memory.id,
        "kind": memory.kind,
        "context": memory.context,
        "topic": memory.topic,
        "slug": memory.slug,
        "title": memory.title,
        "tags": memory.tags,
        "certainty": memory.certainty,
        "source": memory.source,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }
    if memory.caption:
        frontmatter["caption"] = memory.caption
    if memory.image_path:
        frontmatter["image_path"] = memory.image_path
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    body = memory.content.strip()
    text = f"---\n{fm_yaml}---\n\n{body}\n"
    # Atomic write: tmp file + rename, so a crash mid-write can never
    # truncate or corrupt the markdown source of truth.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_md(path: Path) -> Memory:
    """Parse a markdown file into a Memory."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"Missing frontmatter in {path}")

    _, rest = text.split("---", 1)
    fm_text, body = rest.split("---", 1)
    fm = yaml.safe_load(fm_text.strip()) or {}

    return Memory(
        id=fm.get("id", ""),
        kind=fm.get("kind", "note"),
        context=fm.get("context", path.parent.parent.name if path.parent.parent != WIKI_ROOT else ""),
        topic=fm.get("topic", "/".join(path.parent.relative_to(WIKI_ROOT).parts[1:])),
        slug=fm.get("slug", path.stem),
        title=fm.get("title", ""),
        content=body.strip(),
        caption=fm.get("caption", ""),
        certainty=fm.get("certainty", 1.0),
        image_path=fm.get("image_path", ""),
        source=fm.get("source", ""),
        tags=fm.get("tags", []),
        created_at=fm.get("created_at", ""),
        updated_at=fm.get("updated_at", ""),
        path=path,
    )


def parse_links(content: str) -> list[str]:
    """Extract all [[wiki-link]] targets from markdown content."""
    return re.findall(r"\[\[(.*?)\]\]", content)


def parse_inline_tags(content: str) -> list[str]:
    """Extract #hashtags from content, excluding hex colors."""
    tags = re.findall(r"#([a-zA-Z_][\w/-]*)", content)
    return [t for t in tags if not t.startswith("http") and not re.fullmatch(r"[0-9a-fA-F]{3,8}", t)]


def ensure_wiki() -> None:
    WIKI_ROOT.mkdir(parents=True, exist_ok=True)


def _clamp_certainty(value: float) -> float:
    """Clamp certainty to [0.0, 1.0]."""
    return max(0.0, min(1.0, float(value)))


def write_memory(
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
    memory_id: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> Memory:
    """Write a new memory to the wiki. Returns the Memory with its path."""
    ensure_wiki()
    mem_id = memory_id or str(uuid.uuid4())
    now = created_at or _now()
    updated = updated_at or now
    s = slug or _slugify(title or content[:40])
    tags = list(set((tags or []) + parse_inline_tags(content)))
    certainty = _clamp_certainty(certainty)

    path = _memory_path(context, topic, s)
    # Handle duplicate slugs
    counter = 1
    original = path
    while path.exists():
        path = original.with_name(f"{_slugify(s)}-{counter}.md")
        counter += 1

    memory = Memory(
        id=mem_id,
        kind=kind,
        context=context,
        topic=topic,
        slug=path.stem,
        title=title,
        content=content,
        caption=caption,
        certainty=certainty,
        image_path=image_path,
        source=source,
        tags=tags,
        created_at=now,
        updated_at=updated,
        path=path,
    )
    _write_md(path, memory)
    return memory


def read_memory(path: Path) -> Memory:
    """Read a memory from its file path."""
    return _read_md(path)


def find_memory(memory_id: str) -> Path | None:
    """Find a memory's file path by its UUID.

    Tries the index first (O(1)), falls back to full wiki scan if the index
    is empty or the entry is missing from the index.
    """
    # Fast path: ask the index
    from memento import index
    indexed_path = index.find_memory_path(memory_id)
    if indexed_path:
        p = Path(indexed_path)
        if p.exists():
            return p

    # Slow fallback: full scan (needed when index is empty or stale)
    for path in WIKI_ROOT.rglob("*.md"):
        try:
            mem = _read_md(path)
            if mem.id == memory_id:
                return path
        except Exception:
            continue
    return None


def update_memory(
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
) -> Memory | None:
    """Update an existing memory and rewrite its markdown file.

    Tattoos are permanent: their content, context, and topic cannot be changed.
    Only title, tags, caption, source, and certainty can be updated on tattoos.
    """
    path = find_memory(memory_id)
    if path is None:
        return None

    mem = _read_md(path)
    now = _now()

    # Tattoo immutability guard: content, context, and topic cannot change
    if mem.kind == "tattoo":
        if content is not None and content != mem.content:
            raise ValueError("Tattoos are permanent — content cannot be changed.")
        if context is not None and context != mem.context:
            raise ValueError("Tattoos are permanent — context cannot be changed.")
        if topic is not None and topic != mem.topic:
            raise ValueError("Tattoos are permanent — topic cannot be changed.")

    if context is not None:
        mem.context = context
    if topic is not None:
        mem.topic = topic
    if title is not None:
        mem.title = title
    if content is not None:
        mem.content = content
        mem.tags = list(set((tags or mem.tags) + parse_inline_tags(content)))
    if tags is not None and content is None:
        mem.tags = tags
    if caption is not None:
        mem.caption = caption
    if certainty is not None:
        mem.certainty = _clamp_certainty(certainty)
    if image_path is not None:
        mem.image_path = image_path
    if source is not None:
        mem.source = source
    mem.updated_at = now

    # If context or topic changed, move the file.
    # Write the new file BEFORE unlinking the old one — the previous
    # order (unlink, then write) lost the memory entirely if anything
    # failed between the two steps.
    if context is not None or topic is not None:
        new_path = _memory_path(mem.context, mem.topic, mem.slug)
        if new_path != path:
            # Handle collision at new location
            counter = 1
            original = new_path
            while new_path.exists():
                new_path = original.with_name(f"{_slugify(mem.slug)}-{counter}.md")
                counter += 1
            mem.slug = new_path.stem
            mem.path = new_path
            _write_md(new_path, mem)
            path.unlink()
            _cleanup_empty_dirs(path.parent)
            return mem

    mem.path = path
    _write_md(path, mem)
    return mem


def delete_memory(memory_id: str) -> bool:
    """Delete a memory's markdown file by ID."""
    path = find_memory(memory_id)
    if path is None:
        return False
    path.unlink()
    _cleanup_empty_dirs(path.parent)
    return True


def _cleanup_empty_dirs(start: Path) -> None:
    """Remove empty topic/context directories."""
    d = start
    while d != WIKI_ROOT and d != WIKI_ROOT.parent:
        try:
            d.rmdir()
            d = d.parent
        except OSError:
            break


def list_contexts() -> list[str]:
    """Return all context directory names."""
    ensure_wiki()
    contexts: list[tuple[str, float]] = []
    for d in WIKI_ROOT.iterdir():
        if d.is_dir():
            mtime = max((f.stat().st_mtime for f in d.rglob("*.md")), default=0)
            contexts.append((d.name, mtime))
    contexts.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in contexts]


def list_topics(context: str) -> list[str]:
    """Return all topic paths under a context."""
    ctx_dir = WIKI_ROOT / _safe_dir_name(context)
    if not ctx_dir.exists():
        return []
    topics: set[str] = set()
    for md in ctx_dir.rglob("*.md"):
        rel = md.parent.relative_to(ctx_dir)
        topic = "/".join(rel.parts)
        if topic:
            topics.add(topic)
    return sorted(topics)


def get_memories(context: str, topic: str) -> list[Memory]:
    """Return all memories under a context+topic."""
    d = WIKI_ROOT / _safe_dir_name(context)
    parts = [_safe_dir_name(p) for p in topic.split("/")]
    for p in parts:
        d = d / p
    if not d.exists():
        return []
    memories: list[tuple[Memory, float]] = []
    for path in d.glob("*.md"):
        try:
            mem = _read_md(path)
            mtime = path.stat().st_mtime
            memories.append((mem, mtime))
        except Exception:
            continue
    memories.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in memories]


def scan_wiki() -> list[Memory]:
    """Scan the entire wiki and return all memories."""
    ensure_wiki()
    memories: list[Memory] = []
    for path in WIKI_ROOT.rglob("*.md"):
        try:
            memories.append(_read_md(path))
        except Exception:
            continue
    return memories
