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
    region_identity_hash,
    resolve_repo_path,
    semantic_signature_hash,
    sha256_file,
    write_json,
)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


# Reject positional/placeholder ids: numeric-suffixed (page-01, slide-3,
# slide-3-full, item-5), purely numeric (42), and positional-only names built
# from direction words (top-left, center). Semantic names that merely start with
# a direction word (e.g. left-rail, top-banner) are allowed.
_POS = "top|bottom|left|right|center|centre|middle|upper|lower"
_BANNED_ID = re.compile(
    rf"^(?:(?:page|slide|item)-\d+(?:-full)?|\d+|(?:{_POS})(?:-(?:{_POS}))*)$"
)
# Docling draft placeholders minted by analyze_with_docling.py:
# "<label>-p<page>-<n>" (e.g. picture-p1-1, figure-p2-3, table-p10-1,
# chart-px-1, form-p3-2). These are candidate ids that REQUIRE a human rename
# before scaffolding — never let them become a stable identity.
_DOCLING_DRAFT_ID = re.compile(
    r"^(?:picture|figure|table|chart|form)-p[a-z0-9]+-\d+$"
)
_GENERIC_INTENT = {"full-page extraction", "full-slide", "page"}


def validate_request_item(item: dict) -> None:
    for key in ("item_id", "slide_or_page", "region", "requested_type", "semantic_intent"):
        if key not in item or item[key] in (None, "", []):
            raise SystemExit(f"Item {item.get('item_id', '<unknown>')} is missing {key}")
    if _BANNED_ID.match(item["item_id"]):
        raise SystemExit(
            f"Item ID '{item['item_id']}' is a positional placeholder. "
            f"Use a semantic name describing the visual content "
            f"(e.g., 'metric-card', 'timeline-horizontal', 'org-chart')."
        )
    if _DOCLING_DRAFT_ID.match(item["item_id"]):
        raise SystemExit(
            f"Item ID '{item['item_id']}' is a Docling draft placeholder. "
            f"Rename it to a semantic ID describing the visual content "
            f"(e.g., 'metric-card', 'salary-table', 'org-chart') before "
            f"scaffolding."
        )
    intent_set = {v.lower().strip() for v in item["semantic_intent"]}
    if not intent_set or intent_set <= _GENERIC_INTENT:
        raise SystemExit(
            f"Item '{item['item_id']}' has only generic semantic_intent "
            f"{item['semantic_intent']}. Add descriptive intent values "
            f"(e.g., 'cover', 'salary-table', 'org-chart')."
        )
    normalized_bounds(item["region"])


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

    # The extraction-request JSON is a TEMPORARY input artifact. `input/` is a
    # tracked directory (only source decks belong there), so a request file
    # dropped in it pollutes the repo. Every extraction passes through here, so
    # this is the one place that can guarantee it never happens again. The
    # scaffold persists its own copy at <output>/request.json regardless, so the
    # request is never lost. Keep loose requests under the gitignored
    # outputs/extraction-requests/ (or a scratchpad) instead.
    repo_root = Path(__file__).resolve().parents[2]
    request_path = Path(args.request).resolve()
    try:
        rel = request_path.relative_to(repo_root / "input")
    except ValueError:
        rel = None
    if rel is not None:
        raise SystemExit(
            "Request file must not live in the tracked input/ directory "
            f"(got {request_path}). input/ is for source decks only. "
            "Write extraction-request JSON to outputs/extraction-requests/ "
            "(gitignored) and re-run."
        )

    request = load_json(args.request)
    for key in ("extraction_id", "source_path", "items"):
        if not request.get(key):
            raise SystemExit(f"Missing required request value: {key}")
    source_path = resolve_repo_path(request["source_path"])
    if not source_path.exists():
        raise SystemExit(f"Source path does not exist: {source_path}")
    if not request["items"]:
        raise SystemExit("At least one explicit extraction region is required.")
    for item in request["items"]:
        validate_request_item(item)

    output_dir = Path(args.output_root) / request["extraction_id"]
    if output_dir.exists():
        # An analysis pre-step (analyze_with_docling.py) writes only `analysis/`
        # under this same id. That must not block a later scaffold for the same
        # extraction. Allow the dir through ONLY when it is an analysis-only
        # shell — it carries `analysis/` and none of the real extraction outputs
        # (request.json, manifest.json, items/). Anything else is a genuine prior
        # extraction and is still rejected. The `analysis/` dir is preserved.
        real_outputs = [
            name for name in ("request.json", "manifest.json", "items")
            if (output_dir / name).exists()
        ]
        analysis_only = (output_dir / "analysis").is_dir() and not real_outputs
        if not analysis_only:
            raise SystemExit(f"Extraction output already exists: {output_dir}")
    else:
        output_dir.mkdir(parents=True)
    write_json(output_dir / "request.json", request)

    history = load_json(args.history)
    registry = load_json(args.registry)
    source_hash = sha256_file(source_path)
    batch_items = []

    for item in request["items"]:
        region = normalized_bounds(item["region"])
        region_hash = region_identity_hash(
            source_hash, item["slide_or_page"], region,
            item.get("object_ids", []),
        )
        semantic_hash = semantic_signature_hash(item["semantic_intent"])
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
        # "duplicate" means the region already exists as a PUBLISHED library
        # item — the registry is the only authority for that. A prior history
        # attempt (`exact`) is NOT proof of publication: it may have stalled in
        # staging or been abandoned. We still reuse its stable_id above so a
        # re-scaffold keeps a stable identity (and matches the registry if it
        # truly published), but it must not by itself force "duplicate" — doing
        # so leaves the item with no artifact folder and hides it from the
        # catalog, which only surfaces staging/qa items.
        if registry_match:
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
            "name": item_slug.replace("-", " ").title(),
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
            "limitations": [],
            "approval": {"status": "pending", "approved_by": None, "approved_at": None},
            "duplicate_of": candidate_id if registry_match else None,
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
