#!/usr/bin/env python3
"""decompose_svg_objects.py — Split a full-page artwork SVG into per-object
fragment SVGs plus a ready-to-paste tagged HTML snippet for deck building.

Why this exists (BUG B11): wrapping a whole-page visual.svg in one
data-export-layer tag passes the untagged gate but glues every card/arrow/icon
into a single PPTX picture. The layered export needs ONE TAG PER MOVABLE
OBJECT, and extraction SVGs cannot be split statically (matrix transforms,
full-page clipPaths). This script does it mechanically:

  1. measure_svg_groups.js measures every top-level group's bbox in Chromium;
  2. consecutive groups whose bboxes overlap are clustered into one object
     (painter's order: a card = gradient image + shadow paths + face paths);
  3. each cluster becomes assets/<prefix>-obj-NN.svg (viewBox = cluster bbox
     + margin, defs copied) plus a tagged absolutely-positioned <div> in
     snippet.html;
  4. clusters covering >= overlay_coverage.max_ratio of the canvas (the
     validator's full-bleed threshold) are reported as base-candidates and
     left OUT of the snippet — they belong in the slide's CSS background.

Usage:
    decompose_svg_objects.py --svg <visual.svg> --out-dir <run>/assets/page-NN \
        [--prefix page-NN] [--href-base assets/page-NN] [--margin 3]
        [--merge-gap 0] [--report <path.json>]

Outputs in --out-dir: fragment SVGs, snippet.html, decompose-manifest.json.
Exit 0 even when only base-candidates are found (the manifest records it);
exit 2 on operational errors.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import math
import mimetypes
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from _common import SCRIPT_DIR, SYSTEM_ROOT, load_json, sha256_file, write_json

MEASURE_JS = SCRIPT_DIR / "measure_svg_groups.js"
THRESHOLDS = SYSTEM_ROOT / "registries" / "export-qa-thresholds.json"
SVG_NS = "http://www.w3.org/2000/svg"
INK_NS = "http://www.inkscape.org/namespaces/inkscape"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INK_NS)
ET.register_namespace("xlink", XLINK_NS)


def embed_external_images(root: ET.Element, source_dir: Path) -> int:
    """Make fragment SVGs self-contained for file:// and Office rendering."""
    count = 0
    source_root = source_dir.resolve()
    for element in root.iter(f"{{{SVG_NS}}}image"):
        href_key = (
            f"{{{XLINK_NS}}}href"
            if f"{{{XLINK_NS}}}href" in element.attrib else "href"
        )
        href = element.get(href_key)
        if not href or href.startswith(("data:", "#", "http://", "https://")):
            continue
        asset = (source_dir / href).resolve()
        if not asset.is_relative_to(source_root) or not asset.is_file():
            continue
        mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(asset.read_bytes()).decode("ascii")
        element.set(href_key, f"data:{mime};base64,{encoded}")
        count += 1
    return count


def measure(svg_path: Path) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        out_path = Path(handle.name)
    try:
        proc = subprocess.run(
            ["node", str(MEASURE_JS), "--svg", str(svg_path), "--out", str(out_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise SystemExit(f"measure_svg_groups.js failed:\n{proc.stderr}")
        return load_json(out_path)
    finally:
        out_path.unlink(missing_ok=True)


def document_groups(root: ET.Element) -> list[ET.Element]:
    """The same groups, in the same order, that measure_svg_groups.js measured."""
    layers = [g for g in root.iter(f"{{{SVG_NS}}}g")
              if g.get(f"{{{INK_NS}}}groupmode") == "layer"]
    parents = layers or [root]
    groups: list[ET.Element] = []
    for parent in parents:
        groups.extend(ch for ch in parent if ch.tag != f"{{{SVG_NS}}}defs")
    return groups


def ancestor_transform(root: ET.Element, parent_map: dict, group_el: ET.Element) -> str:
    """Transform chain from the SVG root down to ``group_el``'s parent.

    The browser measures a group WITH these ancestor transforms applied, so a
    fragment that copies the group alone paints its geometry somewhere else
    entirely: a cropped component whose layer sits under
    ``translate(-499 -1859)`` renders completely blank inside a viewBox that
    starts at the origin. Re-applying the chain keeps the measured bounds and
    the painted geometry in one space.
    """
    chain: list[str] = []
    node = parent_map.get(group_el)
    while node is not None and node is not root:
        transform = (node.get("transform") or "").strip()
        if transform:
            chain.append(transform)
        node = parent_map.get(node)
    return " ".join(reversed(chain))


def viewbox(root: ET.Element) -> tuple[float, float, float, float] | None:
    """Parse the root viewBox as (min_x, min_y, width, height)."""
    raw = (root.get("viewBox") or "").replace(",", " ").split()
    if len(raw) != 4:
        return None
    try:
        min_x, min_y, width, height = (float(v) for v in raw)
    except ValueError:
        return None
    return (min_x, min_y, width, height) if width > 0 and height > 0 else None


def intersects_canvas(bounds: dict, canvas_w: float, canvas_h: float,
                      min_x: float = 0.0, min_y: float = 0.0) -> bool:
    """True when any part of an object's bbox falls inside the visible canvas."""
    return (bounds["x"] + bounds["w"] > min_x and bounds["x"] < min_x + canvas_w
            and bounds["y"] + bounds["h"] > min_y and bounds["y"] < min_y + canvas_h)


def cluster_consecutive(boxes: list[dict], merge_gap: float) -> list[list[dict]]:
    """Group consecutive document-order boxes whose bboxes overlap.

    Painter's order keeps an object's parts adjacent (image, then shadows,
    then face), while unrelated neighbors (the next card, an arrow between
    cards) do not overlap the running cluster bbox. Bbox-overlap across ALL
    pairs would over-merge: a card's diagonal-shadow bbox spans empty space
    that neighboring arrows sit in.
    """
    clusters: list[list[dict]] = []
    union: list[float] | None = None  # x0, y0, x1, y1
    for box in boxes:
        if box["w"] <= 0 or box["h"] <= 0:
            continue
        x0, y0 = box["x"], box["y"]
        x1, y1 = x0 + box["w"], y0 + box["h"]
        overlaps = (union is not None
                    and x0 <= union[2] + merge_gap and x1 >= union[0] - merge_gap
                    and y0 <= union[3] + merge_gap and y1 >= union[1] - merge_gap)
        if overlaps:
            clusters[-1].append(box)
            union = [min(union[0], x0), min(union[1], y0),
                     max(union[2], x1), max(union[3], y1)]
        else:
            clusters.append([box])
            union = [x0, y0, x1, y1]
    return clusters


# A source group spanning at least this fraction of the canvas (either axis)
# packs unrelated objects more often than it draws one big one — e.g. every
# timeline arrow in a single <g> stretching across all cards.
SPLIT_SPAN_RATIO = 0.5
# ...but a wide group shattering into this many pieces is a texture/pattern;
# keep it whole rather than emit confetti.
SPLIT_MAX_PIECES = 16


def explode_units(boxes: list[dict], canvas_w: float, canvas_h: float,
                  merge_gap: float, notes: list[str]) -> list[dict]:
    """Turn measured groups into cluster units, splitting wide multi-object
    groups by their children's disjoint bboxes. Each unit: {x,y,w,h, group,
    children: None | [child indices]}."""
    units: list[dict] = []
    for box in boxes:
        if box["w"] <= 0 or box["h"] <= 0:
            continue
        wide = (box["w"] >= SPLIT_SPAN_RATIO * canvas_w
                or box["h"] >= SPLIT_SPAN_RATIO * canvas_h)
        kids = [c for c in box.get("children", []) if c["w"] > 0 and c["h"] > 0]
        if wide and len(kids) >= 2:
            sub = cluster_consecutive(kids, merge_gap)
            if 2 <= len(sub) <= SPLIT_MAX_PIECES:
                notes.append(f"group {box['index']} spans "
                             f"{box['w']:.0f}x{box['h']:.0f} and was split into "
                             f"{len(sub)} disjoint sub-objects")
                for child_cluster in sub:
                    units.append({
                        "x": min(c["x"] for c in child_cluster),
                        "y": min(c["y"] for c in child_cluster),
                        "w": (max(c["x"] + c["w"] for c in child_cluster)
                              - min(c["x"] for c in child_cluster)),
                        "h": (max(c["y"] + c["h"] for c in child_cluster)
                              - min(c["y"] for c in child_cluster)),
                        "group": box["index"],
                        "children": [c["index"] for c in child_cluster],
                    })
                continue
        units.append({"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"],
                      "group": box["index"], "children": None})
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--prefix", default=None,
                        help="Object id prefix (default: parent item folder name "
                             "or the svg file stem)")
    parser.add_argument("--href-base", default=None,
                        help="Path prefix used in snippet.html src/vector-source "
                             "attributes (default: --out-dir as given)")
    parser.add_argument("--margin", type=float, default=3.0,
                        help="Padding around each cluster bbox in px (covers "
                             "strokes/antialiasing)")
    parser.add_argument("--merge-gap", type=float, default=0.0,
                        help="Treat bboxes closer than this many px as overlapping")
    parser.add_argument("--report", help="Optional extra path for the manifest JSON")
    args = parser.parse_args()

    svg_path = Path(args.svg).resolve()
    if not svg_path.exists():
        raise SystemExit(f"SVG not found: {svg_path}")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or (svg_path.parent.parent.name
                             if svg_path.parent.name == "artifact" else svg_path.stem)
    href_base = (args.href_base or args.out_dir).rstrip("/")

    measured = measure(svg_path)
    canvas_w, canvas_h = float(measured["width"]), float(measured["height"])
    boxes = measured["groups"]

    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    view_box = viewbox(root)
    # The measurement is in CSS px of the rendered viewport; the document is in
    # user units. They coincide only when the viewBox matches the rendered size
    # and starts at the origin. Derive the mapping from the SVG's own metadata
    # so cropped/scaled components land in the right space.
    origin_x, origin_y = (view_box[0], view_box[1]) if view_box else (0.0, 0.0)
    groups = document_groups(root)
    parent_map = {c: p for p in root.iter() for c in p}
    group_chain = [ancestor_transform(root, parent_map, g) for g in groups]
    if len(groups) != len(boxes):
        raise SystemExit(f"group mismatch: parsed {len(groups)} vs measured "
                         f"{len(boxes)} — SVG structure not understood")
    all_defs = [copy.deepcopy(d) for d in root.iter(f"{{{SVG_NS}}}defs")]

    max_ratio = load_json(THRESHOLDS).get("overlay_coverage", {}).get("max_ratio", 0.85)
    notes: list[str] = []
    units = explode_units(boxes, canvas_w, canvas_h, args.merge_gap, notes)
    # A full-bleed unit (typically the page background image) must not seed
    # the cluster union — it overlaps everything and would swallow every
    # object into one cluster. Pull each out as its own base-candidate.
    full_bleed = [u for u in units
                  if (u["w"] * u["h"]) / (canvas_w * canvas_h) >= max_ratio]
    clusters = [[u] for u in full_bleed] + cluster_consecutive(
        [u for u in units if u not in full_bleed], args.merge_gap)

    objects, base_candidates, warnings, snippet_divs = [], [], [], []
    off_canvas: list[dict] = []
    for n, members in enumerate(clusters, start=1):
        x0 = min(u["x"] for u in members) - args.margin + origin_x
        y0 = min(u["y"] for u in members) - args.margin + origin_y
        x1 = max(u["x"] + u["w"] for u in members) + args.margin + origin_x
        y1 = max(u["y"] + u["h"] for u in members) + args.margin + origin_y
        x0, y0 = math.floor(x0), math.floor(y0)
        w, h = math.ceil(x1) - x0, math.ceil(y1) - y0
        coverage = (w * h) / (canvas_w * canvas_h)
        obj_id = f"{prefix}-obj-{n:02d}"
        file_name = f"{obj_id}.svg"

        bounds = {"x": x0, "y": y0, "w": w, "h": h}
        if not intersects_canvas(bounds, canvas_w, canvas_h, origin_x, origin_y):
            # Geometry the crop threw away. Emitting it produces an overlay the
            # deck positions off-slide (or an empty PNG); it is not artwork.
            off_canvas.append({"id": obj_id, "bounds": bounds,
                               "groups": sorted({u["group"] for u in members})})
            warnings.append(
                f"{obj_id}: bounds {x0},{y0} {w}x{h} fall entirely outside the "
                f"source viewBox ({canvas_w:.0f}x{canvas_h:.0f}) — dropped as "
                f"cropped-away geometry, not emitted as an object")
            continue

        frag = ET.Element(f"{{{SVG_NS}}}svg", {
            "viewBox": f"0 0 {w} {h}", "width": str(w), "height": str(h)})
        for d in all_defs:
            frag.append(copy.deepcopy(d))
        # Keep the SVG viewport origin at zero. PowerPoint and LibreOffice can
        # misrender an svgBlip whose viewBox starts at the source-page x/y,
        # even though browsers display it correctly. Translate source geometry
        # into the normalized fragment viewport instead.
        normalized = ET.SubElement(
            frag, f"{{{SVG_NS}}}g",
            {"transform": f"translate({-x0} {-y0})"},
        )
        chain_hosts: dict[str, ET.Element] = {}

        def host_for(chain: str, _under=normalized) -> ET.Element:
            """Re-create the group's ancestor transform chain inside the fragment."""
            if chain not in chain_hosts:
                chain_hosts[chain] = (
                    ET.SubElement(_under, f"{{{SVG_NS}}}g", {"transform": chain})
                    if chain else _under)
            return chain_hosts[chain]

        for unit in members:
            source = groups[unit["group"]]
            content = host_for(group_chain[unit["group"]])
            if unit["children"] is None:
                content.append(copy.deepcopy(source))
            else:
                # Keep the group shell (clip-path/transform context), copy
                # only the chosen children.
                shell = ET.Element(source.tag, dict(source.attrib))
                kids = list(source)
                for ci in unit["children"]:
                    shell.append(copy.deepcopy(kids[ci]))
                content.append(shell)
        embed_external_images(frag, svg_path.parent)
        (out_dir / file_name).write_bytes(ET.tostring(frag))

        parts = [{"group": u["group"], **({"children": u["children"]}
                                          if u["children"] is not None else {})}
                 for u in members]
        record = {"id": obj_id, "file": file_name,
                  "groups": sorted({u["group"] for u in members}),
                  "parts": parts,
                  "bounds": {"x": x0, "y": y0, "w": w, "h": h},
                  "coverage": round(coverage, 4)}
        if coverage >= max_ratio:
            base_candidates.append(record)
            warnings.append(
                f"{obj_id}: covers {coverage:.0%} of the canvas (>= {max_ratio:.0%}) "
                f"— use it as the slide's CSS background (base layer), NOT as a "
                f"tagged overlay; the export gate rejects full-bleed overlays")
            continue
        objects.append(record)
        # Percentages of the SOURCE canvas, not raw px: a component cropped to
        # its own viewBox (e.g. 1999x620) is not in slide coordinates, and
        # pasting its px offsets into a 1920x1080 stage puts the artwork in the
        # wrong place at the wrong size. Percent maps onto whatever box the
        # snippet is dropped into, and is identity for a full-canvas source.
        def pct(value: float, span: float) -> str:
            return f"{value / span * 100:.4f}%"

        snippet_divs.append(
            f'<div data-export-layer="overlay" data-export-id="{obj_id}"\n'
            f'     data-export-vector-source="{href_base}/{file_name}"\n'
            f'     style="position:absolute;'
            f'left:{pct(x0 - origin_x, canvas_w)};top:{pct(y0 - origin_y, canvas_h)};'
            f'width:{pct(w, canvas_w)};height:{pct(h, canvas_h)};z-index:{n}">\n'
            f'  <img src="{href_base}/{file_name}" '
            f'style="width:100%;height:100%" alt=""></div>')

    snippet = ("<!-- Generated by decompose_svg_objects.py from "
               f"{svg_path.name}. Review ids/order, rename semantically if "
               "helpful, then paste inside the slide div. -->\n"
               + "\n".join(snippet_divs) + "\n")
    (out_dir / "snippet.html").write_text(snippet, encoding="utf-8")

    manifest = {
        "source": str(svg_path), "source_sha256": sha256_file(svg_path),
        "canvas": {"w": canvas_w, "h": canvas_h},
        # Snippet geometry is relative to this box, so a consumer never has to
        # guess whether the numbers are slide px or source-page px.
        "coordinate_space": {"origin_x": origin_x, "origin_y": origin_y,
                             "w": canvas_w, "h": canvas_h, "units": "percent-of-canvas"},
        "prefix": prefix, "max_coverage_ratio": max_ratio,
        "objects": objects, "base_candidates": base_candidates,
        "off_canvas": off_canvas,
        "buildable": bool(objects or base_candidates),
        "split_notes": notes, "warnings": warnings,
    }
    write_json(out_dir / "decompose-manifest.json", manifest)
    if args.report:
        write_json(args.report, manifest)

    for line in warnings:
        print(f"WARN {line}", file=sys.stderr)
    print(f"{prefix}: {len(objects)} object(s), {len(base_candidates)} "
          f"base-candidate(s), {len(off_canvas)} off-canvas -> {out_dir}/snippet.html")
    for record in objects:
        b = record["bounds"]
        print(f"  {record['id']}: groups {record['groups']} "
              f"@ {b['x']},{b['y']} {b['w']}x{b['h']}")
    if not manifest["buildable"]:
        # Every measured object was cropped away. The component cannot be
        # rendered at all, so the pipeline must reject it rather than build a
        # slide of empty overlays and call it a faithful reuse.
        print(f"ERROR: {prefix} is NOT BUILDABLE — all {len(off_canvas)} measured "
              f"object(s) fall outside the source viewBox "
              f"({canvas_w:.0f}x{canvas_h:.0f}); pick another component.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
