#!/usr/bin/env python3
"""Replace embedded SVG data-image URIs with relative image files."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from pathlib import Path


BATCH = Path(__file__).resolve().parent
DATA_IMAGE = re.compile(
    r"data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>[^\"']+)"
)
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}


def externalize(svg_path: Path) -> list[dict[str, object]]:
    source = svg_path.read_text(encoding="utf-8")
    assets_dir = svg_path.parent / "assets"
    matches = list(DATA_IMAGE.finditer(source))
    if not matches:
        manifest_path = svg_path.parent.parent / "evidence" / "external-images.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))["images"]
        return []

    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir()

    records: list[dict[str, object]] = []
    by_digest: dict[str, str] = {}

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

        records.append(
            {
                "reference_index": len(records) + 1,
                "path": f"assets/{filename}",
                "mime_type": mime,
                "byte_size": len(data),
                "sha256": digest,
            }
        )
        return f"assets/{filename}"

    rewritten, replacement_count = DATA_IMAGE.subn(replace, source)
    if replacement_count:
        svg_path.write_text(rewritten, encoding="utf-8")
    return records


svg_paths = list((BATCH / "items").glob("*/artifact/source-page.svg"))
svg_paths += list((BATCH / "items").glob("*/artifact/visual.svg"))
svg_paths += list((BATCH / "items").glob("*/evidence/source-with-text.svg"))

for svg_path in sorted(svg_paths):
    records = externalize(svg_path)
    item_dir = svg_path.parent.parent
    if svg_path.parent.name == "evidence":
        item_dir = svg_path.parent.parent
    manifest_path = item_dir / "evidence" / "external-images.json"
    manifest_path.write_text(
        json.dumps(
            {
                "svg": str(svg_path.relative_to(BATCH)),
                "reference_count": len(records),
                "unique_file_count": len({record["sha256"] for record in records}),
                "images": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    mapping_path = item_dir / "mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    artifact_files = mapping.setdefault("paths", {}).setdefault("artifact_files", [])
    artifact_files = [
        path for path in artifact_files if not path.startswith("artifact/assets/")
    ]
    artifact_files.extend(
        f"artifact/{record['path']}"
        for record in records
        if f"artifact/{record['path']}" not in artifact_files
    )
    mapping["paths"]["artifact_files"] = artifact_files
    mapping["external_images"] = {
        "reference_count": len(records),
        "unique_file_count": len({record["sha256"] for record in records}),
        "manifest": "evidence/external-images.json",
    }
    mapping_path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    notes_path = item_dir / "evidence" / "notes.md"
    notes = notes_path.read_text(encoding="utf-8")
    if "## External image packaging" not in notes:
        notes += (
            "\n## External image packaging\n\n"
            f"- Base64 data-image references replaced: `{len(records)}`.\n"
            f"- Unique external image files: `{len({record['sha256'] for record in records})}`.\n"
            "- Files are stored under `artifact/assets/` and referenced relatively by "
            "the visual and source-evidence SVG files.\n"
            "- Geometry, clipping, masks, transforms, and SVG paint order were not changed.\n"
        )
        notes_path.write_text(notes, encoding="utf-8")
