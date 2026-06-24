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
  3. prunes body <image> elements whose page-space bbox lies wholly outside the
     crop window, so externalize_svg_images.py does not bundle off-canvas raster
     into artifact/assets/ (fail-safe: keeps on any uncertain geometry/transform;
     leaves <defs> images and off-canvas vector content alone);
  4. re-normalizes every text-slot bound into the cropped coordinate space and
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


# --- off-canvas <image> pruning -------------------------------------------
# After the crop, the wrapper group clips everything to the new viewBox but
# elements wholly outside the window remain in the document — and
# externalize_svg_images.py then harvests every <image>, including the dead
# ones, into artifact/assets/. We drop body <image> elements whose page-space
# bbox lies entirely outside the crop window. Fail-safe throughout: any
# uncertainty (missing geometry, a <defs> ancestor, an unparseable/unsupported
# transform) keeps the element. A few extra KB beats a missing visible image.

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)  # affine matrix (a, b, c, d, e, f)
_XFORM_FN = re.compile(r"(\w+)\s*\(([^)]*)\)")


def _mat_mul(m1: tuple, m2: tuple) -> tuple:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(m: tuple, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(value: str | None):
    """Parse an SVG ``transform`` attribute into a single affine matrix.

    Supports only ``translate`` / ``scale`` / ``matrix`` (the forms PyMuPDF
    emits). Returns ``None`` for anything else — a non-affine/unknown token
    (``rotate``, ``skewX``, …), a wrong argument count, or leftover junk that is
    not a clean sequence of ``fn(args)`` calls. Callers treat ``None`` as
    "cannot reason about → keep the element".
    """
    if value is None:
        return IDENTITY
    s = value.strip()
    if not s:
        return IDENTITY
    # The whole string must be a clean sequence of fn(args) calls.
    leftover = re.sub(r"[\s,]+", "", _XFORM_FN.sub("", s))
    if leftover:
        return None
    matrix = IDENTITY
    for name, raw in _XFORM_FN.findall(s):
        nums = numbers(raw)
        if name == "translate":
            if len(nums) == 1:
                m = (1.0, 0.0, 0.0, 1.0, nums[0], 0.0)
            elif len(nums) == 2:
                m = (1.0, 0.0, 0.0, 1.0, nums[0], nums[1])
            else:
                return None
        elif name == "scale":
            if len(nums) == 1:
                m = (nums[0], 0.0, 0.0, nums[0], 0.0, 0.0)
            elif len(nums) == 2:
                m = (nums[0], 0.0, 0.0, nums[1], 0.0, 0.0)
            else:
                return None
        elif name == "matrix":
            if len(nums) == 6:
                m = tuple(nums)
            else:
                return None
        else:
            return None  # rotate/skew/unknown -> not supported, fail safe
        matrix = _mat_mul(matrix, m)
    return matrix


def _prune_offcanvas_images(group: ET.Element, defs_images: set, window: tuple) -> int:
    """Remove ``<image>`` elements inside ``group`` whose transformed page-space
    bbox lies wholly outside ``window`` = (x0, y0, x1, y1).

    Works in page space: the wrapper group's own ``translate(-crop_x, -crop_y)``
    is a uniform shift applied to everything, so it is excluded from the
    accumulated transform and the window is given in page units. Returns the
    number of images removed.
    """
    x0, y0, x1, y1 = window
    eps = 1e-6
    parent = {c: p for p in group.iter() for c in p}

    def ancestor_matrix(el):
        # Accumulate transforms from the outermost child-of-group down to el,
        # excluding group's own transform.
        chain = []
        cur = el
        while cur is not group and cur in parent:
            chain.append(cur)
            cur = parent[cur]
        matrix = IDENTITY
        for node in reversed(chain):  # outermost first
            m = parse_transform(node.get("transform"))
            if m is None:
                return None
            matrix = _mat_mul(matrix, m)
        return matrix

    removed = []
    for img in list(group.iter(f"{SVG}image")):
        if img in defs_images:
            continue  # indirect paint; position not locally decidable -> keep
        try:
            x = float(img.get("x"))
            y = float(img.get("y"))
            w = float(img.get("width"))
            h = float(img.get("height"))
        except (TypeError, ValueError):
            continue  # missing geometry -> keep
        matrix = ancestor_matrix(img)
        if matrix is None:
            continue  # unparseable transform -> keep
        corners = [
            _apply(matrix, cx, cy)
            for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))
        ]
        bx0 = min(c[0] for c in corners)
        bx1 = max(c[0] for c in corners)
        by0 = min(c[1] for c in corners)
        by1 = max(c[1] for c in corners)
        # Drop only if wholly outside; edge-touch / partial overlap is kept.
        outside = (bx1 < x0 - eps or bx0 > x1 + eps
                   or by1 < y0 - eps or by0 > y1 + eps)
        if outside:
            removed.append(img)

    for img in removed:
        parent[img].remove(img)

    # Sweep <g> left with no element children (bottom-up), but never the wrapper
    # group itself and never an id-bearing group (could be a <use> target).
    parent2 = {c: p for p in group.iter() for c in p}
    for node in reversed(list(group.iter(f"{SVG}g"))):
        if node is group or node not in parent2:
            continue
        if len(list(node)) == 0 and node.get("id") is None:
            parent2[node].remove(node)

    return len(removed)


def region_fraction(
    region: dict, page_w: float, page_h: float
) -> tuple[float, float, float, float]:
    """Return (x, y, w, h) as 0-1 fractions of the page, honoring ``region['unit']``.

    The visual.svg viewBox spans ``page_w`` x ``page_h`` in source units (pt for
    the PDF->SVG path). Units map to fractions as:

    - ``normalized`` / ``fraction`` (default): values are already 0-1.
    - ``percent`` / ``percentage`` / ``%``: divide by 100.
    - ``pt`` / ``px``: absolute coordinates in the viewBox grid -> divide by the
      page extent (the PyMuPDF source SVG is in pt; px is taken 1:1 with it).
    - ``in``: inches -> pt (x72), then divide by the page extent.

    Any other unit fails loud — a silently mis-scaled crop (the whole bug this
    guards against) is worse than a hard stop.
    """
    unit = str(region.get("unit", "normalized")).lower()
    x, y, w, h = region["x"], region["y"], region["width"], region["height"]
    if unit in ("normalized", "fraction"):
        return x, y, w, h
    if unit in ("percent", "percentage", "%"):
        return x / 100.0, y / 100.0, w / 100.0, h / 100.0
    if unit in ("pt", "px", "in"):
        factor = 72.0 if unit == "in" else 1.0
        return (
            x * factor / page_w,
            y * factor / page_h,
            w * factor / page_w,
            h * factor / page_h,
        )
    raise SystemExit(
        f"Unsupported region unit {unit!r}; expected one of: "
        "normalized, percent, pt, px, in."
    )


def is_full_page(fx: float, fy: float, fw: float, fh: float) -> bool:
    return (
        abs(fx) < 1e-4 and abs(fy) < 1e-4
        and abs(fw - 1.0) < 1e-4 and abs(fh - 1.0) < 1e-4
    )


def _apply_geometry_crop(
    root: ET.Element, crop_x: float, crop_y: float, crop_w: float, crop_h: float
) -> int:
    """Crop an SVG tree's geometry to the window: move every drawable child
    (everything except <defs>) into a ``translate(-crop_x -crop_y)`` group so the
    new viewport origin is 0,0 (clip-path / ``fill="url(#id)"`` references still
    resolve — defs stay at the root and ids are unchanged), prune body <image>
    elements wholly outside the window, then rewrite viewBox/width/height.

    Text nodes are preserved and never reordered, so the evidence SVG's
    ``<text>`` enumeration that validate_text_slots.py relies on is unaffected.
    Returns the number of images pruned.
    """
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

    defs_images = {img for node in defs for img in node.iter(f"{SVG}image")}
    window = (crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)
    images_pruned = _prune_offcanvas_images(group, defs_images, window)

    root.set("viewBox", f"0 0 {crop_w:g} {crop_h:g}")
    root.set("width", f"{crop_w:g}")
    root.set("height", f"{crop_h:g}")
    return images_pruned


def _crop_evidence_svg(
    evidence_path: Path, page_box: tuple, crop_x: float, crop_y: float,
    crop_w: float, crop_h: float,
) -> int:
    """Crop evidence/source-with-text.svg to the same window as visual.svg so it
    stops referencing off-canvas images (which would otherwise pin them in the
    shared artifact/assets/ store via externalize). Text is retained — this is
    the WITH-text provenance SVG.

    Fail-safe: if the evidence viewBox does not match the page extent the crop
    window was computed against (different scale/origin), skip rather than risk a
    mis-scaled crop. Returns images pruned (0 if skipped/absent).
    """
    if not evidence_path.exists():
        return 0
    tree = ET.parse(evidence_path)
    root = tree.getroot()
    vb = numbers(root.attrib.get("viewBox"))
    min_x, min_y, page_w, page_h = page_box
    if (len(vb) != 4 or abs(vb[0] - min_x) > 1e-3 or abs(vb[1] - min_y) > 1e-3
            or abs(vb[2] - page_w) > 1e-3 or abs(vb[3] - page_h) > 1e-3):
        return 0  # extent mismatch -> leave evidence untouched
    pruned = _apply_geometry_crop(root, crop_x, crop_y, crop_w, crop_h)
    tree.write(evidence_path, encoding="unicode", xml_declaration=True)
    return pruned


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

    contract = load_json(slots_path)
    if (contract.get("source") or {}).get("region_crop"):
        return {"status": "already-cropped", "slot_count": len(contract.get("slots", []))}

    tree = ET.parse(visual_path)
    root = tree.getroot()
    view_box = numbers(root.attrib.get("viewBox"))
    if len(view_box) != 4 or not view_box[2] or not view_box[3]:
        raise SystemExit(f"visual.svg requires a valid viewBox: {visual_path}")
    min_x, min_y, page_w, page_h = view_box

    # Resolve the region to 0-1 fractions only after the page extent is known,
    # so absolute units (pt/px/in) can be divided by it.
    fx, fy, fw, fh = region_fraction(region, page_w, page_h)
    if fw <= 0 or fh <= 0:
        raise SystemExit(f"Region has non-positive size: {region}")
    if is_full_page(fx, fy, fw, fh):
        return {"status": "full-page-noop", "slot_count": len(contract.get("slots", []))}

    # Region (0-1 of the page) -> source units -> crop window.
    crop_x = min_x + fx * page_w
    crop_y = min_y + fy * page_h
    crop_w = fw * page_w
    crop_h = fh * page_h

    # Crop visual.svg geometry (wrap + prune off-canvas <image> + rewrite viewBox).
    images_pruned = _apply_geometry_crop(root, crop_x, crop_y, crop_w, crop_h)
    tree.write(visual_path, encoding="unicode", xml_declaration=True)

    # Crop the full-page evidence SVG to the same window so it no longer
    # references off-canvas images — otherwise it pins them in the shared
    # artifact/assets/ store even after visual.svg drops them.
    evidence_pruned = _crop_evidence_svg(
        item_dir / "evidence" / "source-with-text.svg",
        (min_x, min_y, page_w, page_h), crop_x, crop_y, crop_w, crop_h,
    )

    # Re-normalize text slots into the cropped space; drop slots centered outside.
    # Record the source-text refs of dropped slots so validate_text_slots.py can
    # tell "intentionally cropped out" from "missing coverage" — without this the
    # full-page source SVG would always report out-of-region text as unmapped.
    kept = []
    dropped = 0
    dropped_source_refs: list[dict] = []
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
            for ref in slot.get("source_refs", []):
                dropped_source_refs.append({
                    "text_index": ref["text_index"],
                    "tspan_index": ref["tspan_index"],
                    "character_range": list(ref["character_range"]),
                })
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
        "dropped_source_refs": dropped_source_refs,
        "images_pruned": images_pruned,
        "evidence_images_pruned": evidence_pruned,
    }
    slots_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "status": "cropped",
        "crop_window": source["region_crop"]["crop_window"],
        "slots_kept": len(kept),
        "slots_dropped": dropped,
        "images_pruned": images_pruned,
        "evidence_images_pruned": evidence_pruned,
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
