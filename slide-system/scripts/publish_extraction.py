#!/usr/bin/env python3
"""Publish one explicitly approved extraction item into the shared library."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from _common import load_json, now_iso, write_json
import build_registry
import build_component_retrieval_index as retrieval
from validate_component_metadata import metadata_from_mapping, validate_item


TYPE_FOLDERS = {
    "card": "components/cards",
    "component": "components/diagrams",
    "data-display": "components/data-display",
    "action": "components/action",
    "section": "sections",
    "template": "templates",
    "style": "styles",
    "icon": "icons",
    "background": "backgrounds",
    "character": "characters/dio",
    "asset": "assets",
}
ID_PATTERN = re.compile(r"^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+(\.g\d+)?$")


def files_under(path: Path) -> list[Path]:
    return sorted(item for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction-dir", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
    )
    parser.add_argument(
        "--history",
        default=str(Path(__file__).resolve().parents[1] / "registries/extraction-history.json"),
    )
    parser.add_argument(
        "--library-root",
        default=str(Path(__file__).resolve().parents[1] / "library"),
    )
    args = parser.parse_args()

    item_dir = Path(args.extraction_dir) / "items" / args.item_id
    mapping_path = item_dir / "mapping.json"
    if not mapping_path.exists():
        raise SystemExit(f"Missing mapping: {mapping_path}")
    mapping = load_json(mapping_path)
    if mapping.get("status") == "duplicate":
        raise SystemExit(f"Duplicate already resolves to {mapping.get('duplicate_of')}")
    artifact_status = mapping.get("artifact_status")
    if artifact_status and artifact_status != "ready":
        raise SystemExit(
            f"Artifact build status is {artifact_status}; rerun artifact generation "
            "before publishing."
        )
    if mapping.get("approval", {}).get("status") != "approved":
        raise SystemExit("Publication requires approval.status=approved in mapping.json.")
    if not ID_PATTERN.match(mapping.get("candidate_stable_id", "")):
        raise SystemExit("Candidate stable ID does not follow the naming contract.")
    artifact_dir = item_dir / "artifact"
    artifacts = files_under(artifact_dir)
    if not artifacts:
        raise SystemExit("No artifacts found for publication.")

    # A component-level SVG item must have been cropped to its region. The
    # PDF->SVG path emits the whole page, so an uncropped visual.svg is the
    # entire slide with text stripped, not a single component. crop_svg_region.py
    # stamps source.region_crop into text-slots.json — its absence means the crop
    # was skipped. Templates legitimately reuse the full-page artifact, and a
    # region that covers the whole page is intentionally uncropped.
    item_type = mapping["type"]
    visual_svg = artifact_dir / "visual.svg"
    slots_json = artifact_dir / "text-slots.json"
    region = mapping.get("source", {}).get("region") or {}
    scale = 100.0 if str(region.get("unit", "")).lower() in ("percent", "percentage", "%") else 1.0
    is_full_page = (
        abs(float(region.get("x", 0)) / scale) < 1e-4
        and abs(float(region.get("y", 0)) / scale) < 1e-4
        and abs(float(region.get("width", 1)) / scale - 1.0) < 1e-4
        and abs(float(region.get("height", 1)) / scale - 1.0) < 1e-4
    ) if region else False
    if item_type != "template" and visual_svg.exists() and slots_json.exists() and region and not is_full_page:
        if not (load_json(slots_json).get("source") or {}).get("region_crop"):
            raise SystemExit(
                "Component-level item was not cropped to its region. Run "
                "`python3 slide-system/scripts/crop_svg_region.py --item-dir "
                f"{item_dir}` before publishing (text-slots.json has no "
                "source.region_crop marker — the artifact is still the full page)."
            )
    preview_files = files_under(item_dir / "preview")
    evidence_files = files_under(item_dir / "evidence")
    if not preview_files:
        raise SystemExit("Publication requires at least one preview file.")
    if not evidence_files:
        raise SystemExit("Publication requires source-versus-reconstruction evidence.")

    # Metadata quality gate (pre-mutation): a reusable component must carry
    # retrieval-ready metadata before it can enter the shared library. This runs
    # BEFORE any copytree/registry write below, so a failure leaves the library,
    # registry, compact projection, and retrieval index completely untouched.
    metadata_errors = validate_item(
        metadata_from_mapping(mapping, stable_id=mapping.get("candidate_stable_id"))
    )
    if metadata_errors:
        raise SystemExit(
            "Component metadata gate failed — author real retrieval metadata "
            "before publishing (nothing was mutated):\n  - "
            + "\n  - ".join(metadata_errors)
        )

    folder = TYPE_FOLDERS.get(item_type, item_type)
    stable_id = mapping["candidate_stable_id"]
    if item_type == "template":
        # Templates are grouped by set on disk: an id shaped `sun.<set>.<slide>`
        # publishes into templates/<set>/<slide>/ so one source deck stays one
        # tidy, reusable folder instead of many flat siblings.
        _brand, set_slug, slide_slug = stable_id.split(".")
        destination = Path(args.library_root) / folder / set_slug / slide_slug
    else:
        destination = Path(args.library_root) / folder / stable_id
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(artifact_dir, destination)
    shutil.copytree(item_dir / "preview", destination / "preview")
    # Defense in depth against "ghost published" zombies: only write the
    # registry/history below once the physical library folder actually holds
    # files. A registry entry without a real folder is exactly what
    # build_registry's dangling-drop later removes, leaving history claiming a
    # publication that never landed on disk. Fail loudly here instead.
    if not files_under(destination):
        raise SystemExit(
            f"Publish aborted: no files were copied to {destination}; refusing "
            "to write a registry entry with no backing folder."
        )
    # evidence/reference.png is a staging-only render-parity QA raster
    # (convert_pdf_source.py, page.get_pixmap) that is pixel-identical to
    # preview/thumbnail.png. The published library only needs the picker
    # thumbnail, so drop the duplicate raster from the published evidence.
    shutil.copytree(
        item_dir / "evidence",
        destination / "evidence",
        ignore=shutil.ignore_patterns("reference.png"),
    )

    # Staging keeps one shared asset store at artifact/assets/; evidence SVGs
    # reference it as ../artifact/assets/. The published layout flattens
    # artifact/ into the destination root, so the shared store lives at
    # assets/ and the evidence-relative prefix becomes ../assets/.
    published_evidence_svg = destination / "evidence" / "source-with-text.svg"
    if published_evidence_svg.exists():
        svg_text = published_evidence_svg.read_text(encoding="utf-8")
        if '"../artifact/assets/' in svg_text:
            published_evidence_svg.write_text(
                svg_text.replace('"../artifact/assets/', '"../assets/'),
                encoding="utf-8",
            )

    registry = load_json(args.registry)
    existing = next((item for item in registry["items"] if item["id"] == stable_id), None)
    repo_root = Path(__file__).resolve().parents[2]
    try:
        relative_destination = destination.resolve().relative_to(repo_root)
    except ValueError:
        relative_destination = destination.resolve()
    preview_path = relative_destination / "preview" / preview_files[0].relative_to(item_dir / "preview")
    evidence_path = relative_destination / "evidence" / evidence_files[0].relative_to(item_dir / "evidence")
    text_contract = dict(mapping.get("text_contract") or {})
    if text_contract:
        text_contract["visual"] = str(relative_destination / "visual.svg")
        text_contract["slots"] = str(relative_destination / "text-slots.json")
        text_contract["source_evidence"] = str(relative_destination / "evidence" / "source-with-text.svg")
    item_record = {
        "id": stable_id,
        "version": args.version,
        "name": mapping.get("name", stable_id.split(".")[-1].replace("-", " ").title()),
        "type": item_type,
        "category": mapping.get("category", folder.split("/")[-1]),
        "status": "published",
        "brand": mapping.get("brand"),
        "intent": mapping["semantic_intent"],
        "tags": mapping.get("tags", []),
        "content_structure": mapping.get("content_structure", []),
        "content_fields": mapping.get("content_fields", {}),
        "component_type": mapping.get("component_type"),
        "layout_role": mapping.get("layout_role"),
        "visual_summary": mapping.get("visual_summary"),
        "keywords": mapping.get("keywords", []),
        "use_cases": mapping.get("use_cases", []),
        "anti_use_cases": mapping.get("anti_use_cases", []),
        "quality_notes": mapping.get("quality_notes"),
        "retrieval_notes": mapping.get("retrieval_notes"),
        "text_contract": text_contract or None,
        "density": mapping.get("density", "any"),
        "source": {
            "kind": "extraction",
            "path": mapping["source"]["path"],
            "slide": mapping["source"]["slide_or_page"],
            "region": mapping["source"]["region"],
        },
        "paths": {
            "artifact": str(relative_destination),
            "visual": text_contract.get("visual") if text_contract else None,
            "text_slots": text_contract.get("slots") if text_contract else None,
            "preview": str(preview_path),
            "evidence": str(evidence_path),
        },
        "variants": mapping.get("variants", []),
        "limitations": mapping.get("limitations", []),
        "approval": mapping.get("approval", {}),
    }
    if existing:
        registry["items"][registry["items"].index(existing)] = item_record
    else:
        registry["items"].append(item_record)
    registry["updated_at"] = now_iso()
    write_json(args.registry, registry)
    # Keep the compact projection (what score_visual_items.py reads) in lockstep with
    # the full registry so it never drifts. Use build_registry's projection rather than
    # re-deriving it here: it applies the immutable-text audit gate, so a newly
    # published item projects as `unresolved` until it has actually been audited
    # instead of becoming automatically reusable the moment it lands.
    compact_path = Path(args.registry).with_name("visual-library-compact.json")
    write_json(str(compact_path), build_registry.project_compact(registry["items"]))
    retrieval_path = Path(args.registry).with_name("component-retrieval-index.jsonl")
    retrieval.write_jsonl(retrieval_path, retrieval.build_records(registry))

    mapping["status"] = "published"
    mapping["published_at"] = now_iso()
    mapping["published_path"] = str(relative_destination)
    write_json(mapping_path, mapping)
    history = load_json(args.history)
    history.setdefault("attempts", []).append(
        {
            "attempted_at": now_iso(),
            "extraction_id": mapping["extraction_id"],
            "item_id": args.item_id,
            "stable_id": stable_id,
            "status": "published",
            "source_sha256": mapping["source"]["sha256"],
            "region_identity_sha256": mapping["fingerprints"]["region_identity_sha256"],
            "semantic_signature_sha256": mapping["fingerprints"]["semantic_signature_sha256"],
        }
    )
    history["updated_at"] = now_iso()
    write_json(args.history, history)
    print(f"Published {stable_id} {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
