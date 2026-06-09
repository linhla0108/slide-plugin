#!/usr/bin/env python3
"""Update batch mappings after editable text-slot extraction.

Reusable batch post-step (was previously hand-written as a per-batch `_*.py`
helper inside the output folder). Run against any extraction batch:

    python3 slide-system/scripts/apply_text_contract.py --batch <batch-dir>

For every item it folds the extracted `artifact/text-slots.json` into
`mapping.json` (paths, text_contract, content_fields, limitations), refreshes
`evidence/notes.md`, and regenerates the batch-level `batch-report.md`. Title and
source are derived from the batch `manifest.json`, not hard-coded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def derive_title(batch: Path, manifest: dict) -> str:
    extraction_id = manifest.get("extraction_id") or batch.name
    return extraction_id.replace("-", "_").upper()


def apply_item(item_dir: Path) -> int:
    mapping_path = item_dir / "mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    contract = json.loads(
        (item_dir / "artifact" / "text-slots.json").read_text(encoding="utf-8")
    )
    assets = (
        sorted(
            f"artifact/{path.relative_to(item_dir / 'artifact')}"
            for path in (item_dir / "artifact" / "assets").glob("*")
            if path.is_file()
        )
        if (item_dir / "artifact" / "assets").exists()
        else []
    )
    # SVG visual + text-slots is the single source of truth. Parallel .html/.css
    # representations are intentionally not carried into the artifact manifest.
    mapping["paths"] = {
        "artifact": "artifact/visual.svg",
        "visual": "artifact/visual.svg",
        "text_slots": "artifact/text-slots.json",
        "artifact_files": [
            "artifact/visual.svg",
            "artifact/text-slots.json",
            *assets,
        ],
        "preview": None,
        "source_evidence": "evidence/source-with-text.svg",
    }
    mapping["text_contract"] = {
        "schema": "slide-system/schemas/text-slots.schema.json",
        "visual": "artifact/visual.svg",
        "slots": "artifact/text-slots.json",
        "source_evidence": "evidence/source-with-text.svg",
        "slot_count": len(contract["slots"]),
        "coordinate_space": "normalized",
        "example_content": "source",
        "semantic_text_in_visual": False,
        "artwork_text_exemptions": contract["artwork_text_exemptions"],
        "overflow_policy": "unmanaged",
        "editable": True,
        "allow_empty": True,
    }
    mapping.setdefault("content_fields", {})["text_slots"] = [
        {
            "id": slot["id"],
            "role": slot["role"],
            "html_tag": slot["html_tag"],
            "required": False,
        }
        for slot in contract["slots"]
    ]
    mapping["limitations"] = [
        limitation
        for limitation in mapping.get("limitations", [])
        if "overflow" not in limitation.lower()
        and "embeds raster image data" not in limitation.lower()
    ]
    mapping["limitations"].append(
        "Text overflow is intentionally unmanaged; callers may edit content, font size, and bounds."
    )
    mapping_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    external_manifest_path = item_dir / "evidence" / "external-images.json"
    if external_manifest_path.exists():
        external_manifest = json.loads(external_manifest_path.read_text(encoding="utf-8"))
        external_manifest["svg"] = f"items/{item_dir.name}/artifact/visual.svg"
        external_manifest_path.write_text(
            json.dumps(external_manifest, indent=2) + "\n", encoding="utf-8"
        )

    notes_path = item_dir / "evidence" / "notes.md"
    if notes_path.exists():
        notes = notes_path.read_text(encoding="utf-8")
        notes = notes.replace(
            "- Exact vector artifact: `../artifact/source-page.svg`.",
            "- Source-faithful vector evidence: `source-with-text.svg`.\n"
            "- Reusable visual-only vector: `../artifact/visual.svg`.\n"
            "- Editable text contract: `../artifact/text-slots.json`.",
        )
        notes = notes.replace(
            "`artifact/source-page.svg`",
            "`artifact/visual.svg` and `evidence/source-with-text.svg`",
        )
        if "## Editable text slots" not in notes:
            notes += (
                "\n## Editable text slots\n\n"
                f"- Semantic slots extracted: `{len(contract['slots'])}`.\n"
                "- Source wording is stored as `example_value` for review.\n"
                "- The reusable SVG contains no semantic text nodes.\n"
                "- Bounds use normalized 0-1 coordinates and may be edited by callers.\n"
                "- Overflow is intentionally unmanaged; content is never auto-fitted or truncated.\n"
            )
        notes_path.write_text(notes, encoding="utf-8")

    return len(contract["slots"])


def write_report(batch: Path, manifest: dict) -> None:
    title = derive_title(batch, manifest)
    source_path = manifest.get("source_path", "unknown")
    report = [
        f"# Extraction Batch - {title}",
        "",
        f"Source: `{source_path}`",
        "",
        "All regions remain in staging. Nothing is published.",
        "",
        "Reusable SVG contract:",
        "",
        "- `evidence/source-with-text.svg`: source-faithful review evidence.",
        "- `artifact/visual.svg`: scalable visual without semantic text.",
        "- `artifact/text-slots.json`: normalized editable text contract.",
        "- `gallery.html`: visual plus editable source-content overlays.",
        "",
    ]
    for mapping_path in sorted((batch / "items").glob("*/mapping.json")):
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        report.append(
            f"- Page {mapping['source']['slide_or_page']}: "
            f"`{mapping['candidate_stable_id']}` - "
            f"{mapping['text_contract']['slot_count']} slots, `{mapping.get('status', 'staging')}`."
        )
    (batch / "batch-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=Path, help="Extraction batch directory")
    args = parser.parse_args()
    batch = args.batch.resolve()
    if not (batch / "items").is_dir():
        parser.error(f"{batch} has no items/ — not an extraction batch")

    manifest_path = batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    count = 0
    for mapping_path in sorted((batch / "items").glob("*/mapping.json")):
        if (mapping_path.parent / "artifact" / "text-slots.json").exists():
            apply_item(mapping_path.parent)
            count += 1
    write_report(batch, manifest)
    print(f"Applied text contract to {count} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
