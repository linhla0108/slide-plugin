#!/usr/bin/env python3
"""Update batch mappings after editable text-slot extraction."""

from __future__ import annotations

import json
from pathlib import Path


BATCH = Path(__file__).resolve().parent


for mapping_path in sorted((BATCH / "items").glob("*/mapping.json")):
    item_dir = mapping_path.parent
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    contract = json.loads(
        (item_dir / "artifact" / "text-slots.json").read_text(encoding="utf-8")
    )
    assets = sorted(
        f"artifact/{path.relative_to(item_dir / 'artifact')}"
        for path in (item_dir / "artifact" / "assets").glob("*")
        if path.is_file()
    ) if (item_dir / "artifact" / "assets").exists() else []
    existing = [
        path
        for path in mapping.get("paths", {}).get("artifact_files", [])
        if path.endswith((".css", ".html")) and "source-page.svg" not in path
    ]
    mapping["paths"] = {
        "artifact": "artifact/visual.svg",
        "visual": "artifact/visual.svg",
        "text_slots": "artifact/text-slots.json",
        "artifact_files": [
            "artifact/visual.svg",
            "artifact/text-slots.json",
            *existing,
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
    mapping["content_fields"]["text_slots"] = [
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
        external_manifest = json.loads(
            external_manifest_path.read_text(encoding="utf-8")
        )
        external_manifest["svg"] = f"items/{item_dir.name}/artifact/visual.svg"
        external_manifest_path.write_text(
            json.dumps(external_manifest, indent=2) + "\n", encoding="utf-8"
        )

    notes_path = item_dir / "evidence" / "notes.md"
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


report = [
    "# Extraction Batch - GUIDLINE_PRESENTATION_SUN",
    "",
    "Source: `input/GUIDLINE_PRESENTATION_SUN.pdf`",
    "",
    "All five full-page regions remain in staging. Nothing is published.",
    "",
    "Reusable SVG contract:",
    "",
    "- `evidence/source-with-text.svg`: source-faithful review evidence.",
    "- `artifact/visual.svg`: scalable visual without semantic text.",
    "- `artifact/text-slots.json`: normalized editable text contract.",
    "- `gallery.html`: visual plus editable source-content overlays.",
    "",
]
for mapping_path in sorted((BATCH / "items").glob("*/mapping.json")):
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    report.append(
        f"- Page {mapping['source']['slide_or_page']}: "
        f"`{mapping['candidate_stable_id']}` - "
        f"{mapping['text_contract']['slot_count']} slots, `staging`."
    )
(BATCH / "batch-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
