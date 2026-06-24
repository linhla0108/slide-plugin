#!/usr/bin/env python3
"""crop_svg_region.py — Crop a full-page extraction visual down to the single
selected component region.

Why this exists: the extraction pipeline
(convert_pdf_source.py -> extract_editable_text_slots.py) emits a visual.svg
whose viewBox is the ENTIRE source page. The component's region — recorded in
mapping.json as normalized 0-1 `source.region` — was metadata only and never
applied geometrically, so every "component" was really the whole slide with its
text stripped. This step closes that gap.

Per item it:
  1. reads `source.region` (0-1) from mapping.json and the visual.svg viewBox;
  2. maps the region into source units and rewrites the viewBox to that window,
     wrapping all drawable content in a translate(-x -y) group so the viewport
     origin stays at 0 (PowerPoint/LibreOffice misrender svgBlips whose viewBox
     does not start at 0 — the same constraint decompose_svg_objects.py handles);
  3. re-normalizes every text-slot bound into the cropped coordinate space and
     drops slots whose center falls outside the region.

The crop is idempotent: a `region_crop` marker is written into text-slots.json's
`source` block; a second run on an already-cropped item is a no-op. A region
covering the whole page (x=0,y=0,w=1,h=1) is also a no-op.

    python3 slide-system/scripts/crop_svg_region.py --item-dir outputs/.../items/<item> [--item-dir ...]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from _common import load_json

SVG_NS = "http://www.w3.org/2000/svg"
SVG = f"{{{SVG_NS}}}"
NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def numbers(value: str | None) -> list[float]:
    return [float(item) for item in NUMBER.findall(value or "")]


def region_fraction(region: dict) -> tuple[float, float, float, float]:
    """Return (x, y, w, h) as 0-1 fractions, tolerating percent-encoded units."""
    unit = str(region.get("unit", "normalized")).lower()
    scale = 100.0 if unit in ("percent", "percentage", "%") else 1.0
    return (
        region["x"] / scale,
        region["y"] / scale,
        region["width"] / scale,
        region["height"] / scale,
    )


def is_full_page(fx: float, fy: float, fw: float, fh: float) -> bool:
    return (
        abs(fx) < 1e-4 and abs(fy) < 1e-4
        and abs(fw - 1.0) < 1e-4 and abs(fh - 1.0) < 1e-4
    )


def crop_item(item_dir: Path) -> dict:
    artifact_dir = item_dir / "artifact"
    visual_path = artifact_dir / "visual.svg"
    slots_path = artifact_dir / "text-slots.json"
    mapping_path = item_dir / "mapping.json"
    for required in (visual_path, slots_path, mapping_path):
        if not required.exists():
            raise SystemExit(f"Missing {required}")

    mapping = load_json(mapping_path)
    region = (mapping.get("source") or {}).get("region")
    if not region:
        raise SystemExit(f"{mapping_path} has no source.region to crop to")
    fx, fy, fw, fh = region_fraction(region)
    if fw <= 0 or fh <= 0:
        raise SystemExit(f"Region has non-positive size: {region}")

    contract = load_json(slots_path)
    if (contract.get("source") or {}).get("region_crop"):
        return {"status": "already-cropped", "slot_count": len(contract.get("slots", []))}
    if is_full_page(fx, fy, fw, fh):
        return {"status": "full-page-noop", "slot_count": len(contract.get("slots", []))}

    tree = ET.parse(visual_path)
    root = tree.getroot()
    view_box = numbers(root.attrib.get("viewBox"))
    if len(view_box) != 4 or not view_box[2] or not view_box[3]:
        raise SystemExit(f"visual.svg requires a valid viewBox: {visual_path}")
    min_x, min_y, page_w, page_h = view_box

    # Region (0-1 of the page) -> source units -> crop window.
    crop_x = min_x + fx * page_w
    crop_y = min_y + fy * page_h
    crop_w = fw * page_w
    crop_h = fh * page_h

    # Move every drawable child (everything except <defs>) into a translate group
    # so the new viewport origin is 0,0. clip-path / fill="url(#id)" references
    # still resolve — defs stay at the root and ids are unchanged.
    defs = [child for child in list(root) if child.tag == f"{SVG}defs"]
    drawables = [child for child in list(root) if child.tag != f"{SVG}defs"]
    for child in drawables:
        root.remove(child)
    group = ET.SubElement(root, f"{SVG}g", {"transform": f"translate({-crop_x} {-crop_y})"})
    for child in drawables:
        group.append(child)
    # Keep defs ahead of the drawable group in document order.
    for offset, node in enumerate(defs):
        root.remove(node)
        root.insert(offset, node)

    root.set("viewBox", f"0 0 {crop_w:g} {crop_h:g}")
    root.set("width", f"{crop_w:g}")
    root.set("height", f"{crop_h:g}")
    tree.write(visual_path, encoding="unicode", xml_declaration=True)

    # Re-normalize text slots into the cropped space; drop slots centered outside.
    kept = []
    dropped = 0
    for slot in contract.get("slots", []):
        bounds = slot["bounds"]
        # slot bounds were normalized against the full page.
        sx = bounds["x"] * page_w + min_x
        sy = bounds["y"] * page_h + min_y
        sw = bounds["width"] * page_w
        sh = bounds["height"] * page_h
        center_x = sx + sw / 2
        center_y = sy + sh / 2
        inside = (crop_x <= center_x <= crop_x + crop_w
                  and crop_y <= center_y <= crop_y + crop_h)
        if not inside:
            dropped += 1
            continue
        nx = (sx - crop_x) / crop_w
        ny = (sy - crop_y) / crop_h
        bounds["x"] = round(max(0.0, min(1.0, nx)), 7)
        bounds["y"] = round(max(0.0, min(1.0, ny)), 7)
        bounds["width"] = round(max(0.0001, min(1.0 - bounds["x"], sw / crop_w)), 7)
        bounds["height"] = round(max(0.0001, min(1.0 - bounds["y"], sh / crop_h)), 7)
        slot["z_order"] = len(kept) + 1
        kept.append(slot)
    contract["slots"] = kept

    source = contract.setdefault("source", {})
    source["view_box"] = [0, 0, round(crop_w, 4), round(crop_h, 4)]
    source["canvas_width"] = round(crop_w, 4)
    source["canvas_height"] = round(crop_h, 4)
    source["region_crop"] = {
        "region": {"x": round(fx, 6), "y": round(fy, 6),
                   "width": round(fw, 6), "height": round(fh, 6)},
        "page_view_box": [min_x, min_y, page_w, page_h],
        "crop_window": [round(crop_x, 4), round(crop_y, 4),
                        round(crop_w, 4), round(crop_h, 4)],
    }
    slots_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "status": "cropped",
        "crop_window": source["region_crop"]["crop_window"],
        "slots_kept": len(kept),
        "slots_dropped": dropped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", action="append", type=Path, required=True)
    args = parser.parse_args()
    results = {item_dir.name: crop_item(item_dir) for item_dir in args.item_dir}
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
