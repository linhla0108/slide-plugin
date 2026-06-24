#!/usr/bin/env python3
"""Validate a visual.svg + text-slots.json editable-text contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


SVG = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def validate(item_dir: Path) -> list[str]:
    errors: list[str] = []
    visual_path = item_dir / "artifact" / "visual.svg"
    slots_path = item_dir / "artifact" / "text-slots.json"
    source_path = item_dir / "evidence" / "source-with-text.svg"
    for path in (visual_path, slots_path, source_path):
        if not path.exists():
            errors.append(f"Missing required file: {path}")
    if errors:
        return errors

    visual_root = ET.parse(visual_path).getroot()
    if list(visual_root.iter(f"{SVG}text")) or list(visual_root.iter(f"{SVG}tspan")):
        errors.append("visual.svg contains semantic text nodes.")

    for element in visual_root.iter():
        href = element.attrib.get("href") or element.attrib.get(XLINK_HREF)
        if href and not href.startswith(("#", "data:", "http://", "https://")):
            if not (visual_path.parent / href).resolve().exists():
                errors.append(f"Missing visual asset reference: {href}")

    contract = json.loads(slots_path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != 1:
        errors.append("Unsupported text-slot schema version.")
    slots = contract.get("slots", [])
    ids = [slot.get("id") for slot in slots]
    if len(ids) != len(set(ids)):
        errors.append("Text slot IDs are not unique.")

    coverage: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for slot in slots:
        if slot.get("editable") is not True or slot.get("allow_empty") is not True:
            errors.append(f"Slot {slot.get('id')} is not editable/optional.")
        bounds = slot.get("bounds", {})
        for name in ("x", "y", "width", "height"):
            value = bounds.get(name)
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                errors.append(f"Slot {slot.get('id')} has invalid {name}.")
        if bounds.get("x", 0) + bounds.get("width", 0) > 1.000001:
            errors.append(f"Slot {slot.get('id')} exceeds horizontal bounds.")
        if bounds.get("y", 0) + bounds.get("height", 0) > 1.000001:
            errors.append(f"Slot {slot.get('id')} exceeds vertical bounds.")
        for ref in slot.get("source_refs", []):
            key = (ref["text_index"], ref["tspan_index"])
            coverage.setdefault(key, []).append(tuple(ref["character_range"]))

    # source-with-text.svg is the WHOLE page. When the item has been cropped to a
    # component region, crop_svg_region.py records the source-text refs it dropped
    # (text outside the region); those characters are intentionally not part of the
    # component, so exclude them from the coverage requirement.
    excluded: dict[tuple[int, int], set[int]] = {}
    region_crop = (contract.get("source") or {}).get("region_crop") or {}
    for ref in region_crop.get("dropped_source_refs", []):
        key = (ref["text_index"], ref["tspan_index"])
        start, end = ref["character_range"]
        excluded.setdefault(key, set()).update(range(start, end))

    source_root = ET.parse(source_path).getroot()
    source_texts = list(source_root.iter(f"{SVG}text"))
    for text_index, text_element in enumerate(source_texts):
        tspans = list(text_element.findall(f"{SVG}tspan")) or [text_element]
        for tspan_index, tspan in enumerate(tspans):
            text = "".join(tspan.itertext())
            if not text.strip():
                continue
            ranges = coverage.get((text_index, tspan_index), [])
            covered = set()
            for start, end in ranges:
                covered.update(range(start, end))
            excluded_chars = excluded.get((text_index, tspan_index), set())
            missing = [
                index
                for index, character in enumerate(text)
                if not character.isspace()
                and index not in covered
                and index not in excluded_chars
            ]
            if missing:
                errors.append(
                    f"Unmapped source text characters: text={text_index} "
                    f"tspan={tspan_index} count={len(missing)}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", action="append", required=True, type=Path)
    args = parser.parse_args()
    failed = False
    for item_dir in args.item_dir:
        errors = validate(item_dir)
        if errors:
            failed = True
            print(f"{item_dir}:")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{item_dir}: valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
