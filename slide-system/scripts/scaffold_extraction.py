#!/usr/bin/env python3
"""Create a manual extraction staging package and record each attempt."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import (
    load_json,
    normalized_bounds,
    now_iso,
    resolve_repo_path,
    sha256_file,
    sha256_text,
    write_json,
)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parents[2] / "outputs/component-extractions"),
    )
    parser.add_argument(
        "--history",
        default=str(Path(__file__).resolve().parents[1] / "registries/extraction-history.json"),
    )
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
    )
    args = parser.parse_args()

    request = load_json(args.request)
    for key in ("extraction_id", "source_path", "items"):
        if not request.get(key):
            raise SystemExit(f"Missing required request value: {key}")
    source_path = resolve_repo_path(request["source_path"])
    if not source_path.exists():
        raise SystemExit(f"Source path does not exist: {source_path}")
    if not request["items"]:
        raise SystemExit("At least one explicit extraction region is required.")

    output_dir = Path(args.output_root) / request["extraction_id"]
    if output_dir.exists():
        raise SystemExit(f"Extraction output already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    write_json(output_dir / "request.json", request)

    history = load_json(args.history)
    registry = load_json(args.registry)
    source_hash = sha256_file(source_path)
    batch_items = []

    _BANNED_ID = re.compile(r"^(page-\d+|slide-\d+-full|item-\d+)$")
    _GENERIC_INTENT = {"full-page extraction", "full-slide", "page"}

    for item in request["items"]:
        for key in ("item_id", "slide_or_page", "region", "requested_type", "semantic_intent"):
            if key not in item or item[key] in (None, "", []):
                raise SystemExit(f"Item {item.get('item_id', '<unknown>')} is missing {key}")
        if _BANNED_ID.match(item["item_id"]):
            raise SystemExit(
                f"Item ID '{item['item_id']}' is a positional placeholder. "
                f"Use a semantic name describing the visual content "
                f"(e.g., 'metric-card', 'timeline-horizontal', 'org-chart')."
            )
        intent_set = {v.lower().strip() for v in item["semantic_intent"]}
        if not intent_set or intent_set <= _GENERIC_INTENT:
            raise SystemExit(
                f"Item '{item['item_id']}' has only generic semantic_intent "
                f"{item['semantic_intent']}. Add descriptive intent values "
                f"(e.g., 'cover', 'salary-table', 'org-chart')."
            )
        region = normalized_bounds(item["region"])
        identity = {
            "source_sha256": source_hash,
            "slide_or_page": str(item["slide_or_page"]),
            "region": region,
            "object_ids": sorted(item.get("object_ids", [])),
        }
        region_hash = sha256_text(json.dumps(identity, sort_keys=True))
        semantic_hash = sha256_text(
            "|".join(sorted(value.lower() for value in item["semantic_intent"]))
        )
        exact = next(
            (
                attempt
                for attempt in history.get("attempts", [])
                if attempt.get("region_identity_sha256") == region_hash
            ),
            None,
        )
        item_slug = slug(item["item_id"])
        candidate_id = (
            exact.get("stable_id")
            if exact and exact.get("stable_id")
            else f"sun.{slug(item['requested_type'])}.{item_slug}"
        )
        registry_match = next(
            (entry for entry in registry.get("items", []) if entry["id"] == candidate_id),
            None,
        )
        if exact or registry_match:
            status = "duplicate"
        elif item["requested_type"] == "template":
            status = "published"
        else:
            status = "staging"
        item_dir = output_dir / "items" / item["item_id"]
        # Lean staging: create only the folders a staged item needs. Evidence
        # holds a lightweight note that references (never copies) the source
        # raster. The artifact folder is created only for new items — a duplicate
        # resolves to an existing library item and produces no new artifact, so
        # it would otherwise leave an empty artifact/ folder behind. A per-item
        # preview/ is authored later, only for items advancing to publish (see
        # publish_extraction.py, which requires preview + evidence at that point).
        (item_dir / "evidence").mkdir(parents=True)
        if status != "duplicate":
            (item_dir / "artifact").mkdir(parents=True)

        mapping = {
            "extraction_id": request["extraction_id"],
            "item_id": item["item_id"],
            "candidate_stable_id": candidate_id,
            "status": status,
            "type": item["requested_type"],
            "category": item.get("category", item["requested_type"]),
            "brand": item.get("brand", "sun-studio"),
            "source": {
                "path": str(source_path),
                "sha256": source_hash,
                "slide_or_page": item["slide_or_page"],
                "region": region,
                "object_ids": item.get("object_ids", []),
            },
            "fingerprints": {
                "region_identity_sha256": region_hash,
                "semantic_signature_sha256": semantic_hash,
                "perceptual_hash": null_value(),
            },
            "semantic_intent": item["semantic_intent"],
            "content_fields": {"required": [], "optional": []},
            "variables": [],
            "variants": [],
            "compatibility": {
                "html": "supported",
                "pptx": "supported",
                "pdf": "untested",
                "canva": "untested",
            },
            "limitations": [],
            "approval": {"status": "pending", "approved_by": None, "approved_at": None},
            "duplicate_of": exact.get("stable_id") if exact else candidate_id if registry_match else None,
        }
        write_json(item_dir / "mapping.json", mapping)
        # Single lightweight evidence note. It references the source raster by
        # path instead of copying it, and satisfies publish_extraction's
        # "at least one evidence file" requirement. mapping.json is the canonical
        # machine record; the per-item README/report are intentionally omitted —
        # the batch-level batch-report.md is the staging summary and a full report
        # is authored only when an approved item is prepared for publish.
        (item_dir / "evidence" / "notes.md").write_text(
            f"# Evidence — {item['item_id']}\n\n"
            f"- Candidate ID: `{candidate_id}`\n"
            f"- Status: `{status}`\n"
            f"- Source: `{source_path}` (sha256 `{source_hash[:16]}...`)\n"
            f"- Slide or page: `{item['slide_or_page']}`\n"
            f"- Region (normalized 0-1): x={region['x']} y={region['y']} "
            f"w={region['width']} h={region['height']}\n"
            f"- Object handles: {item.get('object_ids') or 'none'}\n\n"
            "Source raster is referenced by path above, not copied. Add a per-item "
            "preview under `preview/` and tighten the region against the source "
            "geometry only when advancing this item to publish.\n",
            encoding="utf-8",
        )
        attempt = {
            "attempted_at": now_iso(),
            "extraction_id": request["extraction_id"],
            "item_id": item["item_id"],
            "stable_id": candidate_id,
            "status": status,
            "source_sha256": source_hash,
            "region_identity_sha256": region_hash,
            "semantic_signature_sha256": semantic_hash,
        }
        history.setdefault("attempts", []).append(attempt)
        batch_items.append({"item_id": item["item_id"], "status": status, "candidate_id": candidate_id})

    history["updated_at"] = now_iso()
    write_json(args.history, history)
    write_json(
        output_dir / "manifest.json",
        {
            "extraction_id": request["extraction_id"],
            "created_at": now_iso(),
            "source_path": str(source_path),
            "items": batch_items,
        },
    )
    (output_dir / "batch-report.md").write_text(
        "# Extraction Batch\n\n"
        + "\n".join(
            f"- `{item['item_id']}`: `{item['status']}` as `{item['candidate_id']}`"
            for item in batch_items
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_dir)
    return 0


def null_value():
    return None


if __name__ == "__main__":
    raise SystemExit(main())
