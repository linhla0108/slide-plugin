#!/usr/bin/env python3
"""Publish one explicitly approved extraction item into the shared library."""

from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path

from _common import (
    library_mutation_lock,
    library_mutation_unlock,
    load_json,
    mutex_dir,
    now_iso,
    quarantine_path,
    replace_dir_atomically,
    restore_dir_from_backup,
    restore_path,
    snapshot_path,
    write_json,
    write_json_atomic,
    write_jsonl_atomic,
)
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
        _brand, set_slug, slide_slug = stable_id.split(".")
        destination = Path(args.library_root) / folder / set_slug / slide_slug
    else:
        destination = Path(args.library_root) / folder / stable_id

    # ── Phase 0: acquire mutation lock ──────────────────────────────────
    lock_dir = mutex_dir()
    lock_token = library_mutation_lock(lock_dir)
    if lock_token is None:
        raise SystemExit(
            "Another library mutation is in progress; try again later."
        )

    # ── Snapshot every surface we may mutate ────────────────────────────
    registry_path = Path(args.registry)
    compact_path = registry_path.with_name("visual-library-compact.json")
    retrieval_path = registry_path.with_name("component-retrieval-index.jsonl")
    history_path = Path(args.history)

    registry_snap = snapshot_path(registry_path)
    compact_snap = snapshot_path(compact_path)
    retrieval_snap = snapshot_path(retrieval_path)
    mapping_snap = snapshot_path(mapping_path)
    history_snap = snapshot_path(history_path)

    destination_existed = destination.exists()
    artifact_backup: Path | None = None
    tmp_dest = destination.parent / f"{destination.name}.tmp.{os.getpid()}"

    try:
        if tmp_dest.exists():
            shutil.rmtree(tmp_dest)

        # ── Phase 1: prepare everything in a temporary directory ────────
        shutil.copytree(artifact_dir, tmp_dest)
        shutil.copytree(item_dir / "preview", tmp_dest / "preview")
        if not files_under(tmp_dest):
            raise SystemExit(
                f"Publish aborted: no files were copied to {tmp_dest}; refusing "
                "to write a registry entry with no backing folder."
            )
        shutil.copytree(
            item_dir / "evidence",
            tmp_dest / "evidence",
            ignore=shutil.ignore_patterns("reference.png"),
        )
        published_evidence_svg = tmp_dest / "evidence" / "source-with-text.svg"
        if published_evidence_svg.exists():
            svg_text = published_evidence_svg.read_text(encoding="utf-8")
            if '"../artifact/assets/' in svg_text:
                published_evidence_svg.write_text(
                    svg_text.replace('"../artifact/assets/', '"../assets/'),
                    encoding="utf-8",
                )

        # ── Phase 2: swap temp → destination (retains backup) ──────────
        artifact_backup = replace_dir_atomically(tmp_dest, destination)

        # ── Phase 3: registry + derived projections ─────────────────────
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
        write_json_atomic(registry_path, registry)
        write_json_atomic(compact_path, build_registry.project_compact(registry["items"]))
        write_jsonl_atomic(retrieval_path, retrieval.build_records(registry))

        # ── Phase 4: staging mapping + history (audit trail) ────────────
        mapping["status"] = "published"
        mapping["published_at"] = now_iso()
        mapping["published_path"] = str(relative_destination)
        write_json_atomic(mapping_path, mapping)
        history = load_json(args.history)
        history.setdefault("attempts", []).append({
            "attempted_at": now_iso(),
            "extraction_id": mapping["extraction_id"],
            "item_id": args.item_id,
            "stable_id": stable_id,
            "status": "published",
            "source_sha256": mapping["source"]["sha256"],
            "region_identity_sha256": mapping["fingerprints"]["region_identity_sha256"],
            "semantic_signature_sha256": mapping["fingerprints"]["semantic_signature_sha256"],
        })
        history["updated_at"] = now_iso()
        write_json_atomic(history_path, history)

    except BaseException:
        # ── Rollback: restore every surface to its pre-operation state ──
        if artifact_backup and artifact_backup.exists():
            restore_dir_from_backup(destination, artifact_backup)
        elif not destination_existed and destination.exists():
            shutil.rmtree(destination)
        restore_path(registry_path, registry_snap)
        restore_path(compact_path, compact_snap)
        restore_path(retrieval_path, retrieval_snap)
        restore_path(mapping_path, mapping_snap)
        restore_path(history_path, history_snap)
        if tmp_dest.exists():
            shutil.rmtree(tmp_dest)
        # Never prune Draft staging on failure.
        library_mutation_unlock(lock_dir, lock_token)
        raise

    # ── Cleanup on success ──────────────────────────────────────────────
    if artifact_backup and artifact_backup.exists():
        shutil.rmtree(artifact_backup)
    if tmp_dest.exists():
        shutil.rmtree(tmp_dest)
    library_mutation_unlock(lock_dir, lock_token)
    print(f"Published {stable_id} {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
