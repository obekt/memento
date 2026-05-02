"""Export, import, and merge for the markdown wiki."""

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memento import wiki


def export_vault(path: str | None = None) -> str:
    """Export the entire wiki to a zip file. Returns the file path."""
    wiki.ensure_wiki()
    if path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = str(wiki.WIKI_ROOT.parent / f"memento_export_{ts}.zip")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for md_path in wiki.WIKI_ROOT.rglob("*.md"):
            arcname = md_path.relative_to(wiki.WIKI_ROOT)
            zf.write(md_path, arcname)
        # Add metadata manifest
        manifest = {
            "memento_version": "1.0.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format": "markdown-vault",
        }
        zf.writestr(".memento-manifest.json", json.dumps(manifest, indent=2))
    return str(target)


def _read_frontmatter(path: Path) -> dict[str, Any] | None:
    """Peek at a markdown file's frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None
        _, rest = text.split("---", 1)
        fm_text, _ = rest.split("---", 1)
        import yaml
        return yaml.safe_load(fm_text.strip()) or {}
    except Exception:
        return None


def import_vault(path: str, merge_strategy: str = "keep_both") -> dict[str, Any]:
    """
    Import a wiki zip file into the live wiki.
    Merge strategies: keep_both, keep_newer, keep_mine, keep_theirs.
    """
    wiki.ensure_wiki()
    target = Path(path)
    created = 0
    updated = 0
    skipped = 0
    conflicts = 0

    with zipfile.ZipFile(target, "r") as zf:
        for item in zf.namelist():
            if item.endswith("/") or not item.endswith(".md"):
                continue
            data = zf.read(item)
            dest = wiki.WIKI_ROOT / item
            dest.parent.mkdir(parents=True, exist_ok=True)

            if not dest.exists():
                dest.write_bytes(data)
                created += 1
                continue

            if merge_strategy == "keep_mine":
                skipped += 1
                continue

            if merge_strategy == "keep_theirs":
                dest.write_bytes(data)
                updated += 1
                continue

            existing_fm = _read_frontmatter(dest)
            imported_text = data.decode("utf-8")
            imported_fm = _read_frontmatter(dest.__class__("/dev/null"))
            try:
                if imported_text.startswith("---"):
                    _, rest = imported_text.split("---", 1)
                    fm_text, _ = rest.split("---", 1)
                    import yaml
                    imported_fm = yaml.safe_load(fm_text.strip()) or {}
            except Exception:
                imported_fm = {}

            if merge_strategy == "keep_newer":
                try:
                    existing_time = datetime.fromisoformat(existing_fm.get("updated_at", "1970-01-01T00:00:00"))
                    imported_time = datetime.fromisoformat(imported_fm.get("updated_at", "1970-01-01T00:00:00"))
                    if imported_time > existing_time:
                        dest.write_bytes(data)
                        updated += 1
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
                continue

            # keep_both
            existing_body = dest.read_text(encoding="utf-8").split("---", 2)[-1].strip()
            imported_body = imported_text.split("---", 2)[-1].strip()
            if existing_body == imported_body:
                skipped += 1
                continue

            variant = dest.with_name(dest.stem + ".imported" + dest.suffix)
            counter = 1
            orig = variant
            while variant.exists():
                variant = orig.with_name(dest.stem + f".imported-{counter}" + dest.suffix)
                counter += 1
            variant.write_bytes(data)
            conflicts += 1

    return {
        "imported_from": str(target),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "conflicts_resolved_by_duplication": conflicts,
    }


def merge_vaults(path_a: str, path_b: str, output_path: str, merge_strategy: str = "keep_both") -> dict[str, Any]:
    """Merge two wiki zip files into a new zip file without touching the live wiki."""
    out_dir = Path(output_path)
    if out_dir.suffix == ".zip":
        out_dir = out_dir.with_suffix("")
    out_dir.mkdir(parents=True, exist_ok=True)

    def extract_to(zip_path: str, dest_dir: Path) -> None:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)

    dir_a = out_dir / "._merge_a"
    dir_b = out_dir / "._merge_b"
    shutil.rmtree(dir_a, ignore_errors=True)
    shutil.rmtree(dir_b, ignore_errors=True)
    extract_to(path_a, dir_a)
    extract_to(path_b, dir_b)

    created = 0
    updated = 0
    skipped = 0
    conflicts = 0

    # Copy all from A as base
    for src in dir_a.rglob("*.md"):
        rel = src.relative_to(dir_a)
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        created += 1

    # Merge B on top
    for src in dir_b.rglob("*.md"):
        rel = src.relative_to(dir_b)
        dst = out_dir / rel

        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            created += 1
            continue

        if merge_strategy == "keep_mine":
            skipped += 1
            continue

        if merge_strategy == "keep_theirs":
            shutil.copy2(src, dst)
            updated += 1
            continue

        existing_fm = _read_frontmatter(dst)
        imported_fm = _read_frontmatter(src)

        if merge_strategy == "keep_newer":
            try:
                existing_time = datetime.fromisoformat(existing_fm.get("updated_at", "1970-01-01T00:00:00"))
                imported_time = datetime.fromisoformat(imported_fm.get("updated_at", "1970-01-01T00:00:00"))
                if imported_time > existing_time:
                    shutil.copy2(src, dst)
                    updated += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
            continue

        # keep_both
        existing_body = dst.read_text(encoding="utf-8").split("---", 2)[-1].strip()
        imported_body = src.read_text(encoding="utf-8").split("---", 2)[-1].strip()
        if existing_body == imported_body:
            skipped += 1
            continue

        variant = dst.with_name(dst.stem + ".merged-variant" + dst.suffix)
        counter = 1
        orig = variant
        while variant.exists():
            variant = orig.with_name(dst.stem + f".merged-variant-{counter}" + dst.suffix)
            counter += 1
        shutil.copy2(src, variant)
        conflicts += 1

    # Package into zip
    zip_out = Path(output_path)
    if zip_out.suffix != ".zip":
        zip_out = zip_out.with_suffix(".zip")
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.rglob("*"):
            if f.is_file() and not f.name.startswith("._merge_"):
                zf.write(f, f.relative_to(out_dir))

    # Cleanup temp dirs
    shutil.rmtree(dir_a, ignore_errors=True)
    shutil.rmtree(dir_b, ignore_errors=True)

    return {
        "output_path": str(zip_out),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "conflicts_resolved_by_duplication": conflicts,
    }
