#!/usr/bin/env python3
"""Generate catalog data from published/QA registry items and staging outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import load_json, now_iso, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}


def rel(path: Path | str) -> str:
    p = Path(path) if isinstance(path, str) else path
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def collect_images(item_dir: Path) -> list[dict]:
    images: list[dict] = []

    artifact_dir = item_dir / "artifact"
    bg = artifact_dir / "background.png"
    if bg.exists():
        images.append({"label": "Preview", "path": rel(bg)})

    # A component-level item is cropped to its region (crop_svg_region.py records
    # source.region_crop and crops source-with-text.svg too). reference.png is the
    # WHOLE-page QA raster and is NOT cropped, so surfacing it would make the draft
    # preview show the full slide instead of the extracted component. Skip it for
    # cropped items — the cropped source-with-text.svg is the faithful preview.
    slots_path = artifact_dir / "text-slots.json"
    is_cropped = False
    if slots_path.exists():
        try:
            is_cropped = bool((load_json(slots_path).get("source") or {}).get("region_crop"))
        except Exception:
            is_cropped = False

    evidence_dir = item_dir / "evidence"
    src_text = evidence_dir / "source-with-text.svg"
    if src_text.exists():
        images.append({"label": "Source with text", "path": rel(src_text)})

    ref = evidence_dir / "reference.png"
    if ref.exists() and not is_cropped:
        images.append({"label": "Reference", "path": rel(ref)})

    for f in sorted(evidence_dir.glob("*")) if evidence_dir.exists() else []:
        if f.suffix.lower() in IMAGE_EXTS and f.name not in {"source-with-text.svg", "reference.png"}:
            images.append({"label": f.stem.replace("-", " ").replace("_", " ").title(), "path": rel(f)})

    # Fallback: when no raster/evidence preview exists, surface a text-free
    # reusable artifact SVG (e.g. standalone icons) so it still gets a preview.
    if not images and artifact_dir.exists():
        for f in sorted(artifact_dir.glob("*.svg")):
            images.append({"label": f.stem.replace("-", " ").replace("_", " ").title(), "path": rel(f)})

    return images


def publish_readiness(item_dir: Path, mapping: dict) -> dict:
    """Hard gates that block publishing and that the user cannot fix by clicking.

    Excluded on purpose:
      - approval  -> clicking Publish IS the approval (granted server-side).
      - preview   -> authored automatically at publish time.
    These remaining blockers indicate a genuinely incomplete extraction.
    """
    blockers: list[str] = []
    artifact_dir = item_dir / "artifact"
    if not artifact_dir.is_dir() or not any(f.is_file() for f in artifact_dir.rglob("*")):
        blockers.append("No artifacts in this extraction")
    evidence_dir = item_dir / "evidence"
    if not evidence_dir.is_dir() or not any(f.is_file() for f in evidence_dir.rglob("*")):
        blockers.append("No source evidence in this extraction")
    return {"ready": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
    )
    parser.add_argument(
        "--extractions",
        default=str(PROJECT_ROOT / "outputs/component-extractions"),
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "catalog/catalog-data.json"),
    )
    args = parser.parse_args()

    registry = load_json(args.registry)
    items: list[dict] = []

    for pub_item in registry.get("items", []):
        item = dict(pub_item)
        art_path_str = item.get("paths", {}).get("artifact")
        art_path = Path(PROJECT_ROOT / art_path_str) if art_path_str else None
        variants = item.get("variants", [])

        item_images: list[dict] = []
        if art_path and art_path.is_dir() and variants:
            for f in sorted(art_path.iterdir()):
                if f.suffix.lower() in IMAGE_EXTS:
                    label = f.stem
                    for v in variants:
                        if v.lower().replace("-", "").replace("_", "") in label.lower().replace("-", "").replace("_", ""):
                            label = v.replace("-", " ").title()
                            break
                    item_images.append({"label": label, "path": rel(f)})
        elif art_path and art_path.is_file() and art_path.suffix.lower() in IMAGE_EXTS:
            item_images = [{"label": "Preview", "path": art_path_str}]

        # Fallback for dir-based published items without variant images
        # (e.g. full-slide templates): surface the standard preview assets so
        # the catalog tile/modal still renders a visual.
        if not item_images and art_path and art_path.is_dir():
            preview_candidates = [
                ("Preview", art_path / "preview" / "thumbnail.png"),
                ("Reference", art_path / "evidence" / "reference.png"),
                ("Visual", art_path / "visual.svg"),
                ("Source with text", art_path / "evidence" / "source-with-text.svg"),
            ]
            for label, candidate in preview_candidates:
                if candidate.exists() and candidate.suffix.lower() in IMAGE_EXTS:
                    item_images.append({"label": label, "path": rel(candidate)})

        item["images"] = item_images
        # Only library-owned items may be deleted from the catalog. Canonical
        # assets (logo, Dio) live under .agents/ and must never be removed here.
        item["deletable"] = bool(art_path_str and art_path_str.startswith("slide-system/library/"))
        items.append(item)

    extraction_root = Path(args.extractions)
    if extraction_root.exists():
        for mapping_path in extraction_root.glob("*/items/*/mapping.json"):
            mapping = load_json(mapping_path)
            status = mapping.get("status", "")
            if status not in {"staging", "qa"}:
                continue
            item_dir = mapping_path.parent
            artifact_dir = item_dir / "artifact"

            # Handle two mapping schemas:
            # v1: has item_id, candidate_stable_id, type, category, semantic_intent, text_contract, etc.
            # v2: has id, source, page, region, artifact{visual, text_slots}, evidence{reference}
            is_v2 = "page" in mapping and "artifact" in mapping and isinstance(mapping.get("artifact"), dict)

            if is_v2:
                art_info = mapping.get("artifact", {})
                ev_info = mapping.get("evidence", {})
                text_contract = None
                slot_count = mapping.get("slot_count", 0)
                if art_info.get("visual") and art_info.get("text_slots"):
                    text_contract = {
                        "visual": art_info["visual"],
                        "slots": art_info["text_slots"],
                        "slot_count": slot_count,
                    }

                source_str = mapping.get("source", "")
                batch_name = mapping_path.parent.parent.parent.name

                items.append({
                    "id": mapping.get("id", mapping_path.parent.name),
                    "version": "0.0.0",
                    "name": mapping_path.parent.name.replace("-", " ").title(),
                    "type": "template",
                    "category": mapping.get("region", "full-page"),
                    "status": "staging",
                    "brand": batch_name.split("-")[0] if batch_name else None,
                    "intent": [],
                    "tags": [mapping.get("region", "full-page")],
                    "source": source_str,
                    "paths": {
                        "artifact": rel(artifact_dir),
                        "visual": rel(item_dir / art_info["visual"]) if art_info.get("visual") else None,
                        "text_slots": rel(item_dir / art_info["text_slots"]) if art_info.get("text_slots") else None,
                        "preview": rel(item_dir / "preview"),
                        "detail": rel(item_dir / "README.md"),
                        "evidence": rel(item_dir / "evidence"),
                    },
                    "images": collect_images(item_dir),
                    "content_fields": {},
                    "text_contract": text_contract,
                    "variants": [],
                    "limitations": [],
                    "deletable": True,
                    "staging_dir": rel(item_dir),
                    "publish_readiness": publish_readiness(item_dir, mapping),
                })
            else:
                variants = mapping.get("variants", [])
                tc = mapping.get("text_contract")
                items.append({
                    "id": mapping.get("candidate_stable_id", mapping.get("item_id", mapping_path.parent.name)),
                    "version": mapping.get("version", "0.0.0"),
                    "name": mapping.get("name", mapping.get("item_id", mapping_path.parent.name)),
                    "type": mapping.get("type", "unknown"),
                    "category": mapping.get("category", mapping.get("type", "unknown")),
                    "status": "staging",
                    "brand": mapping.get("brand"),
                    "intent": mapping.get("semantic_intent", []),
                    "tags": mapping.get("tags", []),
                    "source": mapping.get("source", ""),
                    "paths": {
                        "artifact": rel(artifact_dir),
                        "visual": rel(item_dir / tc["visual"]) if tc and tc.get("visual") else None,
                        "text_slots": rel(item_dir / tc["slots"]) if tc and tc.get("slots") else None,
                        "preview": rel(item_dir / "preview"),
                        "detail": rel(item_dir / "README.md"),
                        "evidence": rel(item_dir / "evidence"),
                    },
                    "images": collect_images(item_dir),
                    "content_fields": mapping.get("content_fields", {}),
                    "text_contract": tc,
                    "variants": variants,
                    "limitations": mapping.get("limitations", []),
                    "deletable": True,
                    "staging_dir": rel(item_dir),
                    "publish_readiness": publish_readiness(item_dir, mapping),
                })

    data = {
        "generated_at": now_iso(),
        "counts": {
            "published": sum(item.get("status") == "published" for item in items),
            "staging": sum(item.get("status") in {"staging", "qa"} for item in items),
        },
        "items": items,
    }
    write_json(args.output, data)
    print(f"Catalog data: {len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
