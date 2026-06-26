#!/usr/bin/env python3
"""split_icon_sheet.py — Decompose a brand ICON reference sheet into one
self-contained SVG per individual icon.

Why a dedicated splitter (not classify_page_components): an icon sheet is a
dense regular grid of hundreds of tiny, all-distinct glyphs. The generic
decomposer's area-floor drops every icon as "too small", its shape-class /
proximity-run logic is meant for repeated cards (not unique glyphs), and a
single proximity gap cannot both keep a big multi-stroke icon whole AND avoid
fusing two neighbours in a tight grid.

Approach — two regions, each with the right rule:
  * MAIN library grid: cluster strokes at a small gap (neighbours are ~3x
    farther apart than an icon is wide, so they never fuse), then SNAP each
    cluster to its (row, column) cell and merge co-cell fragments. This keeps
    every icon whole regardless of internal stroke gaps, and one icon == one
    occupied cell.
  * "Frequently used" box (top-right, labelled): a handful of large icons whose
    strokes sit far apart — coarse-merge with a bigger gap, and name each from
    the nearest extracted text-slot label.

Reuses the leaf/cluster/fragment primitives from classify_page_components so the
emitted per-icon SVGs are byte-identical in construction to the catalog's other
component fragments (defs copied, geometry translated to a 0-based viewport,
raster assets embedded).

Output (under <item>/artifact/icons/):
  icon-NNN.svg            one self-contained icon
  icons-manifest.json     [{index, region, row, col, x,y,w,h, name, label}]
  contact-sheet-NN.png    labelled montages for visual naming/QA
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from classify_page_components import (
    SVG_NS,
    _ancestor_transform,
    _bounds,
    _build_fragment,
    _cluster_spatial,
    _leaf_boxes,
    document_groups,
    measure,
)

RENDER_JS = Path(__file__).resolve().parent / "render_svg.js"


def _cluster_1d(values: list[float], tol: float) -> list[float]:
    """Group sorted scalars whose neighbour-gap <= tol; return cluster means
    (the grid lines)."""
    if not values:
        return []
    values = sorted(values)
    groups: list[list[float]] = [[values[0]]]
    for v in values[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _nearest(lines: list[float], v: float) -> int:
    return min(range(len(lines)), key=lambda i: abs(lines[i] - v))


def _merge_within(clusters: list[dict], gap: float) -> list[dict]:
    """Union-find merge of cluster bboxes whose gap on BOTH axes <= gap. Used
    for the sparse frequently-used icons whose strokes sit far apart."""
    n = len(clusters)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def axis_gap(a0, a1, b0, b1):
        if a1 < b0:
            return b0 - a1
        if b1 < a0:
            return a0 - b1
        return 0.0

    for i in range(n):
        a = clusters[i]
        for j in range(i + 1, n):
            b = clusters[j]
            gx = axis_gap(a["x"], a["x"] + a["w"], b["x"], b["x"] + b["w"])
            gy = axis_gap(a["y"], a["y"] + a["h"], b["y"], b["y"] + b["h"])
            if gx <= gap and gy <= gap:
                parent[find(i)] = find(j)

    by_root: dict[int, list[dict]] = {}
    for i in range(n):
        by_root.setdefault(find(i), []).append(clusters[i])
    out = []
    for members in by_root.values():
        merged = [m for c in members for m in c["members"]]
        x, y, w, h = _bounds(merged)
        out.append({"x": x, "y": y, "w": w, "h": h, "members": merged})
    return out


def _label_slots(item_dir: Path, canvas_w: float, canvas_h: float) -> list[dict]:
    """Text-slot labels as pixel-space centres, for naming the labelled icons."""
    p = item_dir / "artifact" / "text-slots.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for s in data.get("slots", []):
        if s.get("role") != "label":
            continue
        b = s["bounds"]
        out.append({
            "text": s.get("example_value", "").strip(),
            "cx": (b["x"] + b["width"] / 2) * canvas_w,
            "cy": (b["y"] + b["height"] / 2) * canvas_h,
        })
    return out


def split(item_dir: Path, gap: float, freq_x: float, freq_y: float,
          freq_gap: float, bg_frac: float, margin: float,
          row_tol: float, col_tol: float) -> dict:
    visual = item_dir / "artifact" / "visual.svg"
    if not visual.exists():
        raise SystemExit(f"no artifact/visual.svg in {item_dir}")

    measured = measure(visual)
    W, H = float(measured["width"]), float(measured["height"])
    root = ET.fromstring(visual.read_text(encoding="utf-8"))
    groups = document_groups(root)
    if len(groups) != len(measured["groups"]):
        raise SystemExit(
            f"group mismatch: parsed {len(groups)} vs measured "
            f"{len(measured['groups'])} — SVG structure not understood")
    all_defs = [copy.deepcopy(d) for d in root.iter(f"{{{SVG_NS}}}defs")]
    parent_map = {c: p for p in root.iter() for c in p}
    anc = _ancestor_transform(root, parent_map, groups[0]) if groups else ""

    leaves = _leaf_boxes(measured, window_pad=max(W, H) * 0.02)
    raw = _cluster_spatial(leaves, gap, W, H)
    cells: list[dict] = []
    for m in raw:
        x, y, w, h = _bounds(m)
        if (w * h) / (W * H) >= bg_frac:        # drop page background
            continue
        cells.append({"x": x, "y": y, "w": w, "h": h, "members": m})

    def in_freq(c: dict) -> bool:
        return c["x"] >= freq_x and (c["y"] + c["h"]) <= freq_y

    freq_cells = [c for c in cells if in_freq(c)]
    main_cells = [c for c in cells if not in_freq(c)]

    # MAIN grid: assign each stroke-cluster to a row (rows are ~100px apart and
    # well separated), then WITHIN each row merge consecutive cells whose
    # horizontal gap is below `col_tol`. The gap histogram is sharply bimodal —
    # intra-icon fragment gaps sit at 0-10px, inter-icon gutters at 50-80px, with
    # an empty valley between — so a threshold in that valley re-fuses an icon's
    # own split strokes without ever gluing two neighbouring icons together.
    # (A global column model is fragile here: rows are not perfectly
    # column-aligned, so shared column lines merge distinct adjacent icons.)
    rows = _cluster_1d([c["y"] + c["h"] / 2 for c in main_cells], row_tol)
    by_row: dict[int, list[dict]] = {}
    for c in main_cells:
        by_row.setdefault(_nearest(rows, c["y"] + c["h"] / 2), []).append(c)
    by_cell: dict[tuple[int, int], list[dict]] = {}
    for r, row_cells in by_row.items():
        row_cells.sort(key=lambda c: c["x"])
        col = 0
        right = None
        for c in row_cells:
            if right is not None and (c["x"] - right) >= col_tol:
                col += 1
            by_cell.setdefault((r, col), []).append(c)
            right = max(right if right is not None else c["x"] + c["w"],
                        c["x"] + c["w"])

    labels = _label_slots(item_dir, W, H)

    def name_from_labels(x, y, w, h) -> tuple[str, str]:
        # A labelled icon's caption sits directly BELOW it and is x-aligned, so
        # match on horizontal distance among labels in the band beneath the icon
        # (euclidean mixes up a row whose icons differ in height).
        if not labels:
            return "", ""
        cx, cy = x + w / 2, y + h / 2
        below = [L for L in labels if cy <= L["cy"] <= y + h + 2.2 * h]
        if not below:
            return "", ""
        best = min(below, key=lambda L: abs(L["cx"] - cx))
        if abs(best["cx"] - cx) <= max(w, 130):
            return best["text"], best["text"]
        return "", ""

    icons: list[dict] = []
    for (r, col), members_cells in sorted(by_cell.items()):
        merged = [m for c in members_cells for m in c["members"]]
        x, y, w, h = _bounds(merged)
        icons.append({"region": "grid", "row": r, "col": col,
                      "x": x, "y": y, "w": w, "h": h, "members": merged,
                      "name": "", "label": ""})

    for fc in _merge_within(freq_cells, freq_gap):
        name, label = name_from_labels(fc["x"], fc["y"], fc["w"], fc["h"])
        icons.append({"region": "frequently-used", "row": -1, "col": -1,
                      "x": fc["x"], "y": fc["y"], "w": fc["w"], "h": fc["h"],
                      "members": fc["members"], "name": name, "label": label})

    icons.sort(key=lambda i: (0 if i["region"] == "frequently-used" else 1,
                              round(i["y"] / 30), i["x"]))

    out_dir = item_dir / "artifact" / "icons"
    if out_dir.exists():
        for f in out_dir.glob("*"):
            if f.is_file():
                f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"canvas": {"w": W, "h": H},
                "params": {"gap": gap, "freq_x": freq_x, "freq_y": freq_y,
                           "freq_gap": freq_gap, "row_tol": row_tol,
                           "col_tol": col_tol, "margin": margin},
                "grid": {"rows": len(rows),
                         "cells": len(by_cell), "freq_used": len(icons) - len(by_cell)},
                "icons": []}
    for idx, ic in enumerate(icons):
        frag = _build_fragment(ic["members"], groups, all_defs, margin,
                               item_dir / "artifact", anc)
        (out_dir / f"icon-{idx:03d}.svg").write_text(
            ET.tostring(frag, encoding="unicode"), encoding="utf-8")
        manifest["icons"].append({
            "index": idx, "file": f"icon-{idx:03d}.svg", "region": ic["region"],
            "row": ic["row"], "col": ic["col"],
            "x": round(ic["x"], 1), "y": round(ic["y"], 1),
            "w": round(ic["w"], 1), "h": round(ic["h"], 1),
            "name": ic["name"], "label": ic["label"]})
    (out_dir / "icons-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"out_dir": out_dir, "count": len(icons), "manifest": manifest}


def render_contact_sheets(out_dir: Path, per_sheet: int = 60, cols: int = 12,
                          cell_px: int = 110) -> list[Path]:
    """Render each icon to PNG and tile labelled contact sheets for naming/QA."""
    manifest = json.loads((out_dir / "icons-manifest.json").read_text())
    icons = manifest["icons"]
    margin = manifest.get("params", {}).get("margin", 4.0)
    tmp = Path(tempfile.mkdtemp(prefix="iconpng_"))
    # Render each icon at its OWN native pixel size — render_svg.js clips to the
    # viewport, so a fixed small viewport would crop the larger icons. PIL then
    # scales each tight PNG to fit the cell, preserving aspect.
    jobs = [{"svg": str(out_dir / ic["file"]),
             "output": str(tmp / f"{ic['index']:03d}.png"),
             "width": int(ic["w"] + 2 * margin + 2),
             "height": int(ic["h"] + 2 * margin + 2)} for ic in icons]
    jobs_path = tmp / "jobs.json"
    jobs_path.write_text(json.dumps(jobs))
    proc = subprocess.run(["node", str(RENDER_JS), "--jobs", str(jobs_path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"render_svg.js failed:\n{proc.stderr}")

    from PIL import Image, ImageDraw
    sheets: list[Path] = []
    label_h = 16
    cw, ch = cell_px, cell_px + label_h
    for s, start in enumerate(range(0, len(icons), per_sheet)):
        chunk = icons[start:start + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw, rows * ch), "white")
        draw = ImageDraw.Draw(sheet)
        for k, ic in enumerate(chunk):
            r, c = divmod(k, cols)
            px, py = c * cw, r * ch
            p = tmp / f"{ic['index']:03d}.png"
            if p.exists():
                im = Image.open(p).convert("RGBA")
                bg = Image.new("RGBA", im.size, "white")
                bg.alpha_composite(im)
                glyph = bg.convert("RGB")
                fit = cell_px - 14
                glyph.thumbnail((fit, fit), Image.LANCZOS)
                ox = px + (cw - glyph.width) // 2
                oy = py + (cell_px - glyph.height) // 2
                sheet.paste(glyph, (ox, oy))
            draw.rectangle([px, py, px + cw - 1, py + ch - 1], outline="#ddd")
            draw.text((px + 3, py + cell_px), f"#{ic['index']}", fill="red")
        out = out_dir / f"contact-sheet-{s:02d}.png"
        sheet.save(out)
        sheets.append(out)
    return sheets


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--item-dir", required=True, type=Path)
    ap.add_argument("--gap", type=float, default=6.0)
    ap.add_argument("--freq-x", type=float, default=1580.0,
                    help="left edge (px) of the frequently-used box")
    ap.add_argument("--freq-y", type=float, default=770.0,
                    help="bottom edge (px) of the frequently-used box")
    ap.add_argument("--freq-gap", type=float, default=34.0)
    ap.add_argument("--bg-frac", type=float, default=0.5)
    ap.add_argument("--margin", type=float, default=4.0)
    ap.add_argument("--row-tol", type=float, default=45.0)
    ap.add_argument("--col-tol", type=float, default=35.0,
                    help="max intra-row gap (px) to fuse split strokes of one "
                         "icon; sits in the valley between fragment and "
                         "inter-icon gaps")
    ap.add_argument("--contact", action="store_true",
                    help="also render labelled contact sheets")
    args = ap.parse_args()

    res = split(args.item_dir, args.gap, args.freq_x, args.freq_y,
                args.freq_gap, args.bg_frac, args.margin,
                args.row_tol, args.col_tol)
    print(f"icons: {res['count']}  ->  {res['out_dir']}")
    g = res["manifest"]["grid"]
    print(f"grid: {g['rows']} rows, {g['cells']} cells + {g['freq_used']} freq-used")
    named = sum(1 for i in res["manifest"]["icons"] if i["name"])
    print(f"named (from labels): {named}")
    if args.contact:
        sheets = render_contact_sheets(res["out_dir"])
        for s in sheets:
            print(f"contact: {s}")


if __name__ == "__main__":
    main()
