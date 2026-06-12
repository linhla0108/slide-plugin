#!/usr/bin/env python3
"""Publish one explicitly approved extraction item into the shared library."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from _common import load_json, now_iso, write_json


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
ID_PATTERN = re.compile(r"^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+$")


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
    if mapping.get("approval", {}).get("status") != "approved":
        raise SystemExit("Publication requires approval.status=approved in mapping.json.")
    if not ID_PATTERN.match(mapping.get("candidate_stable_id", "")):
        raise SystemExit("Candidate stable ID does not follow the naming contract.")
    artifact_dir = item_dir / "artifact"
    artifacts = files_under(artifact_dir)
    if not artifacts:
        raise SystemExit("No artifacts found for publication.")
    preview_files = files_under(item_dir / "preview")
    evidence_files = files_under(item_dir / "evidence")
    if not preview_files:
        raise SystemExit("Publication requires at least one preview file.")
    if not evidence_files:
        raise SystemExit("Publication requires source-versus-reconstruction evidence.")
    if any(value == "untested" for value in mapping.get("compatibility", {}).values()):
        raise SystemExit("All compatibility targets must be tested before publication.")

    item_type = mapping["type"]
    folder = TYPE_FOLDERS.get(item_type, item_type)
    destination = Path(args.library_root) / folder / mapping["candidate_stable_id"]
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(artifact_dir, destination)
    for required in ("preview", "evidence"):
        shutil.copytree(item_dir / required, destination / required)

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
    stable_id = mapping["candidate_stable_id"]
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
        "compatibility": mapping["compatibility"],
        "limitations": mapping.get("limitations", []),
    }
    if existing:
        registry["items"][registry["items"].index(existing)] = item_record
    else:
        registry["items"].append(item_record)
    registry["updated_at"] = now_iso()
    write_json(args.registry, registry)

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
