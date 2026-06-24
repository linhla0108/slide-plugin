#!/usr/bin/env python3
"""Replace embedded SVG data-image URIs with relative image files.

Reusable batch post-step (was previously hand-written as a per-batch `_*.py`
helper inside the output folder). Run against any extraction batch:

    python3 slide-system/scripts/externalize_svg_images.py --batch <batch-dir>

All of an item's SVG files share ONE asset store: `artifact/assets/`.
`artifact/visual.svg` and `artifact/source-page.svg` reference it as
`assets/...`; `evidence/source-with-text.svg` references the same files as
`../artifact/assets/...` so evidence never carries a duplicate copy of every
image (publish_extraction.py rewrites that prefix to `../assets/` for the
published layout). Payloads are deduplicated by content hash across the whole
item and recorded in `evidence/external-images.json` plus the item
`mapping.json` and `evidence/notes.md`.

Re-running is safe: already-externalized SVGs are left alone, and legacy items
that still hold a duplicated `evidence/assets/` copy are repaired in place
(files merged into `artifact/assets/`, references rewritten, duplicate folder
removed).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
from pathlib import Path


DATA_IMAGE = re.compile(
    r"data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>[^\"']+)"
)
ASSET_REF = re.compile(r"href=\"(?:\.\./artifact/)?assets/(?P<name>[^\"]+)\"")
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
MIME_BY_EXTENSION = {ext: mime for mime, ext in EXTENSIONS.items()}
MIME_BY_EXTENSION[".jpeg"] = "image/jpeg"


def item_svg_specs(item_dir: Path) -> list[tuple[Path, str]]:
    """The item's SVG files and the relative prefix each uses for shared assets."""
    specs = [
        (item_dir / "artifact" / "source-page.svg", "assets/"),
        (item_dir / "artifact" / "visual.svg", "assets/"),
        (item_dir / "evidence" / "source-with-text.svg", "../artifact/assets/"),
    ]
    return [(path, prefix) for path, prefix in specs if path.exists()]


def seed_digests(assets_dir: Path) -> dict[str, str]:
    by_digest: dict[str, str] = {}
    if assets_dir.is_dir():
        for path in sorted(assets_dir.iterdir()):
            if path.is_file():
                by_digest[hashlib.sha256(path.read_bytes()).hexdigest()] = path.name
    return by_digest


def repair_legacy_evidence_assets(
    item_dir: Path, assets_dir: Path, by_digest: dict[str, str]
) -> bool:
    """Merge a duplicated evidence/assets/ copy into the shared artifact store."""
    legacy_dir = item_dir / "evidence" / "assets"
    if not legacy_dir.is_dir():
        return False
    assets_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(legacy_dir.iterdir()):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in by_digest:
            shutil.move(str(path), assets_dir / path.name)
            by_digest[digest] = path.name
    shutil.rmtree(legacy_dir)
    return True


def externalize(
    svg_path: Path, prefix: str, assets_dir: Path, by_digest: dict[str, str]
) -> bool:
    source = svg_path.read_text(encoding="utf-8")
    changed = False

    if DATA_IMAGE.search(source):
        assets_dir.mkdir(parents=True, exist_ok=True)

        def replace(match: re.Match[str]) -> str:
            mime = match.group("mime")
            payload = "".join(match.group("data").split())
            data = base64.b64decode(payload, validate=True)
            digest = hashlib.sha256(data).hexdigest()

            filename = by_digest.get(digest)
            if filename is None:
                extension = EXTENSIONS.get(mime, ".bin")
                filename = f"image-{len(by_digest) + 1:02d}-{digest[:12]}{extension}"
                (assets_dir / filename).write_bytes(data)
                by_digest[digest] = filename
            return f"{prefix}{filename}"

        source, replacement_count = DATA_IMAGE.subn(replace, source)
        changed = changed or bool(replacement_count)

    # Legacy repair: evidence SVGs used to reference their own assets/ copy.
    if prefix != "assets/" and '"assets/' in source:
        source = source.replace('"assets/', f'"{prefix}')
        changed = True

    if changed:
        svg_path.write_text(source, encoding="utf-8")
    return changed


def collect_records(svg_specs: list[tuple[Path, str]], assets_dir: Path) -> list[dict[str, object]]:
    """Manifest records for every shared-asset reference across the item's SVGs."""
    records: list[dict[str, object]] = []
    for svg_path, _prefix in svg_specs:
        source = svg_path.read_text(encoding="utf-8")
        for match in ASSET_REF.finditer(source):
            asset = assets_dir / match.group("name")
            if not asset.is_file():
                continue
            data = asset.read_bytes()
            records.append(
                {
                    "reference_index": len(records) + 1,
                    "svg": svg_path.name,
                    "path": f"assets/{asset.name}",
                    "mime_type": MIME_BY_EXTENSION.get(asset.suffix.lower(), "application/octet-stream"),
                    "byte_size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return records


def gc_unreferenced_assets(svg_specs: list[tuple[Path, str]], assets_dir: Path) -> int:
    """Delete files in ``assets_dir`` referenced by none of the item's SVGs.

    After a component crop drops off-canvas <image> elements (from both visual.svg
    and the evidence SVG), the underlying asset files become orphaned in the
    shared store; this reclaims them. Only ever removes files no SVG points at, so
    it cannot break a live reference.
    """
    if not assets_dir.is_dir():
        return 0
    referenced: set[str] = set()
    for svg_path, _prefix in svg_specs:
        for match in ASSET_REF.finditer(svg_path.read_text(encoding="utf-8")):
            referenced.add(match.group("name"))
    removed = 0
    for path in sorted(assets_dir.iterdir()):
        if path.is_file() and path.name not in referenced:
            path.unlink()
            removed += 1
    return removed


def process_item(item_dir: Path) -> bool:
    svg_specs = item_svg_specs(item_dir)
    if not svg_specs:
        return False

    assets_dir = item_dir / "artifact" / "assets"
    by_digest = seed_digests(assets_dir)

    touched = repair_legacy_evidence_assets(item_dir, assets_dir, by_digest)
    for svg_path, prefix in svg_specs:
        touched = externalize(svg_path, prefix, assets_dir, by_digest) or touched

    # Reclaim assets no SVG references anymore (e.g. off-canvas images dropped by
    # crop_svg_region.py from both visual.svg and the evidence SVG).
    touched = gc_unreferenced_assets(svg_specs, assets_dir) > 0 or touched

    if not by_digest:
        return touched

    records = collect_records(svg_specs, assets_dir)
    unique_count = len({record["sha256"] for record in records})

    manifest_path = item_dir / "evidence" / "external-images.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "svg": [str(path.relative_to(item_dir)) for path, _ in svg_specs],
                "assets_dir": "artifact/assets",
                "reference_count": len(records),
                "unique_file_count": unique_count,
                "images": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    mapping_path = item_dir / "mapping.json"
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        artifact_files = mapping.setdefault("paths", {}).setdefault("artifact_files", [])
        artifact_files = [
            path for path in artifact_files if not path.startswith("artifact/assets/")
        ]
        artifact_files.extend(
            sorted(
                f"artifact/assets/{name}"
                for name in {record["path"].split("/", 1)[1] for record in records}
            )
        )
        mapping["paths"]["artifact_files"] = artifact_files
        mapping["external_images"] = {
            "reference_count": len(records),
            "unique_file_count": unique_count,
            "manifest": "evidence/external-images.json",
        }
        mapping_path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    notes_path = item_dir / "evidence" / "notes.md"
    if notes_path.exists():
        notes = notes_path.read_text(encoding="utf-8")
        if records and "## External image packaging" not in notes:
            notes += (
                "\n## External image packaging\n\n"
                f"- Shared-asset references across the item's SVG files: `{len(records)}`.\n"
                f"- Unique external image files: `{unique_count}`.\n"
                "- Files are stored once under `artifact/assets/` and referenced "
                "relatively by both the visual and source-evidence SVG files.\n"
                "- Geometry, clipping, masks, transforms, and SVG paint order were not changed.\n"
            )
            notes_path.write_text(notes, encoding="utf-8")
    return True


def process_batch(batch: Path) -> int:
    touched = 0
    for item_dir in sorted((batch / "items").iterdir()):
        if item_dir.is_dir() and process_item(item_dir):
            touched += 1
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=Path, help="Extraction batch directory")
    args = parser.parse_args()
    batch = args.batch.resolve()
    if not (batch / "items").is_dir():
        parser.error(f"{batch} has no items/ — not an extraction batch")
    count = process_batch(batch)
    print(f"Externalized SVG images across {count} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
