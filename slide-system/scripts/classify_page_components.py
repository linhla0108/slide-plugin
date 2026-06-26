#!/usr/bin/env python3
"""classify_page_components.py — Decompose one extracted region/page SVG into
its DISTINCT visual components, then classify + deduplicate them.

Why this exists: a component-level extraction crops a page down to a region
(e.g. the Level 1-5 card strip), but the cropped ``visual.svg`` is still ONE
glued artwork. Reviewers (and the catalog Draft) want to see *each separate
component* the region contains — and a page often repeats the same component
in different colors (5 Level cards, identical shape, different palette). The
desired review surface is: one preview per DISTINCT component + the source
image for comparison, NOT five near-identical tiles and not the whole slide.

Pipeline (no new dependencies — reuses measure_svg_groups.js + Chromium, the
same renderer the decomposer already uses):

  1. measure every top-level group AND its children in real Chromium layout
     (matrix transforms / clipPaths resolved), via measure_svg_groups.js.
  2. flatten to leaf bboxes and DROP everything outside the viewBox — a crop
     leaves off-canvas vector junk behind (vector pruning is out of scope for
     crop_svg_region.py), which would otherwise pollute the decomposition.
  3. spatially cluster the on-canvas leaves (2D bbox-overlap union-find, NOT
     document order) into component INSTANCES. A layer-organized SVG keeps a
     card's gradient/shadow/face in different top-level groups, so document
     order cannot recover objects — spatial proximity can.
  4. classify instances into shape-CLASSES (congruent w x h within tolerance),
     then split each shape-class into proximity RUNS (group same-shape instances
     that sit near each other on both axes). A row of 5 Level cards (same shape,
     different color) sitting adjacent is ONE group; same-shape instances far
     apart fall into separate groups.
  5. emit one fragment SVG per GROUP — rendered as the whole run with every
     member's real color/icon preserved (the deliberate pattern, NOT a deduped
     single card) — plus a manifest recording the groups.

Usage:
    classify_page_components.py --item-dir <staging-item> [--item-dir ...]
        [--min-area-frac 0.015] [--shape-tol 0.14] [--merge-gap 6]
        [--group-gap-frac 0.6]

Writes per item:
    artifact/components/<prefix>-group-NN.svg   (one per proximity run)
    artifact/components/components-manifest.json
Idempotent: regenerates the components/ dir from scratch each run.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from _common import (
    load_json,
    normalized_bounds,
    now_iso,
    region_identity_hash,
    semantic_signature_hash,
    sha256_file,
    write_json,
)
from decompose_svg_objects import (
    SVG_NS,
    document_groups,
    embed_external_images,
    measure,
)

SCRIPT_DIR = Path(__file__).resolve().parent
RENDER_JS = SCRIPT_DIR / "render_svg.js"
CROP_SCRIPT = SCRIPT_DIR / "crop_svg_region.py"
VALIDATE_SCRIPT = SCRIPT_DIR / "validate_text_slots.py"
EXTERNALIZE_SCRIPT = SCRIPT_DIR / "externalize_svg_images.py"
OPTIMIZE_SCRIPT = SCRIPT_DIR / "optimize_svg.py"
TEXT_CONTRACT_SCRIPT = SCRIPT_DIR / "apply_text_contract.py"


_PERCEPT_GRID = 32   # signature resolution for the perceptual dedup


def _percept_signature(png_path: Path, grid: int = _PERCEPT_GRID):
    """A small, alpha-flattened, down-scaled RGB thumbnail of a rendered card —
    the perceptual signature used to decide "same component".

    Why not a byte/pixel hash: per-card fragments sit at fractional source
    coordinates, so the outer integer translate leaves each card at a slightly
    different sub-pixel phase — identical vector cards then rasterize to
    *different* bytes and an exact hash never matches (the dedup-miss root
    cause). Down-scaling to a 32×32 box averages that sub-pixel noise away while
    staying colour-sensitive (orange vs blue stay far apart). Alpha is flattened
    onto white so a card with/without a background fill compares the same."""
    from PIL import Image
    im = Image.open(png_path).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((grid, grid), Image.LANCZOS)


def _signature_distance(a, b) -> float:
    """Mean absolute per-channel error (0–255) between two signatures — the same
    metric `compare_renders.py` uses for render parity."""
    from PIL import ImageChops, ImageStat
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def _render_signatures(jobs: list[dict]) -> dict:
    """Render each job SVG to PNG via render_svg.js and return
    {output_path: perceptual-signature}. A signature is None when the render is
    missing — the dedup then keeps that card on its own (never silently merged).
    """
    if not jobs:
        return {}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(jobs, handle)
        jobs_path = handle.name
    try:
        proc = subprocess.run(["node", str(RENDER_JS), "--jobs", jobs_path],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"render_svg.js failed:\n{proc.stderr}")
    finally:
        Path(jobs_path).unlink(missing_ok=True)
    out: dict = {}
    for j in jobs:
        p = Path(j["output"])
        out[j["output"]] = _percept_signature(p) if p.exists() else None
    return out


def _leaf_boxes(measured: dict, window_pad: float) -> list[dict]:
    """All on-canvas leaf bboxes, tagged with (group, child) provenance.

    A group with measured children contributes one leaf per child; a childless
    group contributes itself. Leaves whose bbox falls outside the viewBox (plus
    a small pad) are off-canvas crop residue and are dropped.
    """
    W, H = float(measured["width"]), float(measured["height"])
    leaves: list[dict] = []
    for g in measured["groups"]:
        gi = g["index"]
        kids = [c for c in g.get("children", []) if c["w"] > 0 and c["h"] > 0]
        candidates = (
            [{"x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"],
              "group": gi, "child": c["index"]} for c in kids]
            if kids else
            ([{"x": g["x"], "y": g["y"], "w": g["w"], "h": g["h"],
               "group": gi, "child": None}] if g["w"] > 0 and g["h"] > 0 else [])
        )
        for leaf in candidates:
            x0, y0 = leaf["x"], leaf["y"]
            x1, y1 = x0 + leaf["w"], y0 + leaf["h"]
            on_canvas = (x1 > -window_pad and x0 < W + window_pad
                         and y1 > -window_pad and y0 < H + window_pad)
            if on_canvas:
                leaves.append(leaf)
    return leaves


def _cluster_spatial(leaves: list[dict], merge_gap: float,
                     canvas_w: float, canvas_h: float) -> list[list[dict]]:
    """Union-find over 2D bbox overlap. A few leaf shapes are barred from
    bridging because they would glue otherwise-disjoint objects into one blob:
    a near-full-bleed background, and full-width/full-height THIN bars
    (dividers/rules). A tall-but-narrow object (e.g. a portrait card that fills
    96% of the canvas height but only 19% of its width) is NOT barred — it is a
    real object that must still absorb its own icon/label children."""
    n = len(leaves)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    def wide(b: dict) -> bool:
        area_frac = (b["w"] * b["h"]) / (canvas_w * canvas_h)
        if area_frac >= 0.7:  # near full-bleed background
            return True
        # A divider/rule spans almost a whole axis AND is extremely elongated
        # (thin). A portrait card also spans a whole axis but is not elongated
        # (aspect ~1.3), so the aspect gate keeps it as a real object.
        long_side, short_side = max(b["w"], b["h"]), min(b["w"], b["h"])
        aspect = (long_side / short_side) if short_side else 999.0
        spans_axis = b["w"] >= 0.85 * canvas_w or b["h"] >= 0.85 * canvas_h
        if spans_axis and aspect >= 8.0:
            return True
        return False

    def overlaps(a: dict, b: dict) -> bool:
        return (a["x"] <= b["x"] + b["w"] + merge_gap
                and a["x"] + a["w"] >= b["x"] - merge_gap
                and a["y"] <= b["y"] + b["h"] + merge_gap
                and a["y"] + a["h"] >= b["y"] - merge_gap)

    for i in range(n):
        if wide(leaves[i]):
            continue
        for j in range(i + 1, n):
            if wide(leaves[j]):
                continue
            if overlaps(leaves[i], leaves[j]):
                union(i, j)

    by_root: dict[int, list[dict]] = {}
    for i in range(n):
        by_root.setdefault(find(i), []).append(leaves[i])
    return list(by_root.values())


def _split_on_gutter(members: list[dict], min_gutter_px: float,
                     ignore_area_frac: float = 0.01) -> list[list[dict]]:
    """Split one spatial cluster when a clean empty band (a "gutter") divides its
    LARGE leaves into two sides — separating distinct components that small
    bridging leaves (an icon, a dot, a stray fragment sitting in the gap) glued
    into one cluster during `_cluster_spatial`.

    Why this is needed: union-find bridges any two leaves within `merge_gap`, so
    a card next to a photo merges when a tiny fragment straddles the gutter
    between them (measured: a 21px card↔photo gutter bridged by 20–69px icon
    bits). The gutter is computed from the 1-D projection of the *large* leaves
    only (a gap there = a full-height/full-width empty band); small leaves do not
    block it but are assigned to whichever side their centre falls on. A genuine
    single component usually has a background/container leaf spanning it, so it
    has no internal gutter and is left intact. Recurses so a 3-up row splits
    fully."""
    if len(members) < 2:
        return [members]
    bx, by, bw, bh = _bounds(members)
    area = bw * bh
    big = [m for m in members if m["w"] * m["h"] >= ignore_area_frac * area]
    if len(big) < 2:
        return [members]

    best = None  # (gap, pos_key, size_key, cut)
    for pos, size in (("x", "w"), ("y", "h")):
        ordered = sorted(big, key=lambda m: m[pos])
        right = ordered[0][pos] + ordered[0][size]
        for m in ordered[1:]:
            gap = m[pos] - right
            if gap > 0 and (best is None or gap > best[0]):
                best = (gap, pos, size, (right + m[pos]) / 2)
            right = max(right, m[pos] + m[size])
    if best is None or best[0] < min_gutter_px:
        return [members]

    _, pos, size, cut = best
    left = [m for m in members if (m[pos] + m[size] / 2) < cut]
    right_side = [m for m in members if (m[pos] + m[size] / 2) >= cut]
    if not left or not right_side:
        return [members]
    return (_split_on_gutter(left, min_gutter_px, ignore_area_frac)
            + _split_on_gutter(right_side, min_gutter_px, ignore_area_frac))


def _bounds(members: list[dict]) -> tuple[float, float, float, float]:
    x0 = min(m["x"] for m in members)
    y0 = min(m["y"] for m in members)
    x1 = max(m["x"] + m["w"] for m in members)
    y1 = max(m["y"] + m["h"] for m in members)
    return x0, y0, x1 - x0, y1 - y0


def _shape_classes(instances: list[dict], tol: float) -> list[list[int]]:
    """Greedily group instance indices whose w and h match within ``tol``.

    Same shape => same class, regardless of color/fill — this is the merge
    rule (identical AND same-shape-different-color both collapse to one)."""
    classes: list[list[int]] = []
    reps: list[dict] = []
    for idx, inst in enumerate(instances):
        placed = False
        for ci, rep in enumerate(reps):
            dw = abs(inst["w"] - rep["w"]) / max(inst["w"], rep["w"])
            dh = abs(inst["h"] - rep["h"]) / max(inst["h"], rep["h"])
            if dw <= tol and dh <= tol:
                classes[ci].append(idx)
                placed = True
                break
        if not placed:
            classes.append([idx])
            reps.append(inst)
    return classes


import re

# Generic words that carry no signal as a title/tag (EN + common VN function words).
_STOP = {"the", "and", "for", "with", "này", "các", "cho", "là", "của", "một",
         "và", "có", "không", "như", "khi", "đã", "được", "that", "this", "you",
         "your", "từ", "đến", "ra", "vào", "theo"}


def _load_text_slots(item_dir: Path) -> list[dict]:
    """Read text-slots.json into lightweight records: text + normalized bbox +
    font size. Empty list when there is no text layer."""
    p = item_dir / "artifact" / "text-slots.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[dict] = []
    for s in data.get("slots", []):
        b = s.get("bounds") or {}
        text = (s.get("example_value") or "").strip()
        if not text:
            continue
        typo = s.get("typography") or {}
        try:
            size = float(typo.get("font_size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        out.append({"text": text, "x": b.get("x", 0.0), "y": b.get("y", 0.0),
                    "w": b.get("width", 0.0), "h": b.get("height", 0.0), "size": size})
    return out


def _slots_in(slots: list[dict], bx: float, by: float, bw: float, bh: float,
              canvas_w: float, canvas_h: float) -> list[dict]:
    """Slots whose center (normalized → px) falls inside the px bbox."""
    res = []
    for s in slots:
        cx = (s["x"] + s["w"] / 2) * canvas_w
        cy = (s["y"] + s["h"] / 2) * canvas_h
        if bx <= cx <= bx + bw and by <= cy <= by + bh:
            res.append(s)
    return res


def _heading(slots: list[dict]) -> str:
    """Title from a region's heading text: the two largest font-size tiers
    (heading + subtitle, e.g. 'Level 1 Spicy Autocomplete' / 'Revenue +30%'),
    read top-to-bottom/left-to-right.

    Long body-copy slots (a sentence, not a heading) are dropped, and repeated
    identical fragments are de-duplicated — source text extraction sometimes
    emits a heading twice or merges a description into the same tier."""
    if not slots:
        return ""
    short = [s for s in slots if len(s["text"]) <= 24] or slots
    by_size = sorted({round(s["size"], 1) for s in short}, reverse=True)
    if not by_size:
        return ""
    pick = [s for s in short if round(s["size"], 1) == by_size[0]]
    if len(by_size) > 1:
        tier2 = [s for s in short if round(s["size"], 1) == by_size[1]]
        if len(tier2) <= 3:        # a subtitle, not a body-copy paragraph
            pick += tier2
    pick.sort(key=lambda s: (round(s["y"] * 200), s["x"]))
    words: list[str] = []
    seen: set[str] = set()
    for s in pick:
        t = s["text"].strip()
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        words.append(t)
    return re.sub(r"\s+", " ", " ".join(words)).strip()[:42]


def _tags_from(titles: list[str], limit: int = 8) -> list[str]:
    """Distinctive words drawn from a set of card headings, deduped case-
    insensitively, original casing kept (so TRANSLATOR / Level survive)."""
    seen: list[str] = []
    lower_seen: set[str] = set()
    for t in titles:
        for w in re.findall(r"[A-Za-zÀ-ỹ0-9]+", t):
            if (len(w) < 3 and not w.isdigit()) or w.lower() in _STOP:
                continue
            if w.lower() not in lower_seen:
                lower_seen.add(w.lower())
                seen.append(w)
            if len(seen) >= limit:
                return seen
    return seen


def _group_title(card_titles: list[str]) -> str:
    """A group's name from its card headings: a shared leading word collapses to
    '<word> cards'; otherwise the distinct headings are joined."""
    heads = [t for t in card_titles if t]
    if not heads:
        return ""
    firsts = [h.split()[0] for h in heads if h.split()]
    if len(firsts) == len(heads) and len(set(w.lower() for w in firsts)) == 1:
        return f"{firsts[0]} cards"
    # Join only heading-like titles (short, capitalized) so a card that fell back
    # to body copy doesn't pollute the group name.
    concise = [h for h in heads if len(h.split()) <= 3 and h[:1].isupper()]
    return re.sub(r"\s+", " ", " / ".join(concise or heads)).strip()[:60]


def _collapse_duplicates(items: list, distance, threshold: float
                         ) -> tuple[list[int], list[int]]:
    """Given per-card items in reading order, keep the FIRST occurrence and
    collapse a later item into a kept one when ``distance(item, kept) <=
    threshold``.

    ``distance`` is injected so the rule is testable without rendering: the real
    call passes perceptual signatures + `_signature_distance` (mean abs error),
    which collapses identical *and* near-identical cards ("giống/tương tự → bỏ
    qua") while keeping clearly different colours/icons apart.

    Returns ``(kept_indices, counts)`` where ``counts[j]`` is how many cards
    collapsed into the j-th kept card (1 = no duplicate). A ``None`` item (render
    failed) is never merged — always kept on its own, so a missing render
    degrades to "show it" rather than silently dropping a distinct card.
    """
    kept: list[int] = []
    counts: list[int] = []
    reps: list = []
    for idx, it in enumerate(items):
        if it is not None:
            match = None
            for k, rep in enumerate(reps):
                if rep is not None and distance(it, rep) <= threshold:
                    match = k
                    break
            if match is not None:
                counts[match] += 1
                continue
        kept.append(idx)
        counts.append(1)
        reps.append(it)
    return kept, counts


def _child_count_mismatch(groups: list, measured_groups: list) -> list[tuple[int, int, int]]:
    """Groups whose ElementTree element-child count differs from the child count
    reported by measure_svg_groups.js, as (group_index, parsed, measured).

    _build_fragment copies a group's children by the MEASURED child index
    (``kids = list(source); kids[ci]``). If the two enumerations disagree, those
    indices point at different nodes and the fragment lifts the WRONG children —
    silently scrambling content (the same failure class as the icon paint-order
    bug). The caller fails loud on any mismatch, mirroring the top-level guard."""
    out: list[tuple[int, int, int]] = []
    for gi, (g, mg) in enumerate(zip(groups, measured_groups)):
        parsed = len(list(g))
        meas = len(mg.get("children", []))
        if parsed != meas:
            out.append((gi, parsed, meas))
    return out


def _axis_gap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Separation between two 1-D intervals; 0 when they overlap or touch."""
    return max(0.0, max(a0, b0) - min(a1, b1))


def _proximity_groups(instances: list[dict], class_idxs: list[int],
                      gap_frac: float) -> list[list[int]]:
    """Union-find within ONE shape-class: two instances join when the gap
    between their bboxes on EACH axis is <= ``gap_frac`` times the smaller
    extent on that axis (overlap => gap 0).

    This is the proximity-run rule: a row of cards has gap_y ~ 0 (aligned) and a
    small inter-card gutter on x; a grid has both gaps small; same-shape
    instances sitting far apart stay in separate groups. Alignment is NOT
    required — only nearness on both axes."""
    n = len(class_idxs)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    def near(a: dict, b: dict) -> bool:
        gx = _axis_gap(a["x"], a["x"] + a["w"], b["x"], b["x"] + b["w"])
        gy = _axis_gap(a["y"], a["y"] + a["h"], b["y"], b["y"] + b["h"])
        return (gx <= gap_frac * min(a["w"], b["w"])
                and gy <= gap_frac * min(a["h"], b["h"]))

    for i in range(n):
        for j in range(i + 1, n):
            if near(instances[class_idxs[i]], instances[class_idxs[j]]):
                union(i, j)

    by_root: dict[int, list[int]] = {}
    for i in range(n):
        by_root.setdefault(find(i), []).append(class_idxs[i])
    return list(by_root.values())


def _ancestor_transform(root: ET.Element, parent_map: dict, group_el: ET.Element) -> str:
    """Concatenated transform chain from the SVG root down to ``group_el``'s
    parent, outermost first. Empty transforms are skipped. This is the chain a
    fragment must re-apply because the measured bboxes already include it (e.g.
    a crop's ``translate(-crop_x -crop_y)`` wrapper)."""
    chain: list[str] = []
    node = parent_map.get(group_el)
    while node is not None and node is not root:
        t = (node.get("transform") or "").strip()
        if t:
            chain.append(t)
        node = parent_map.get(node)
    return " ".join(reversed(chain))


def _build_fragment(members: list[dict], groups: list[ET.Element],
                    all_defs: list[ET.Element], margin: float,
                    source_dir: Path, ancestor_transform: str) -> ET.Element:
    """Self-contained fragment SVG for one instance (mirrors the decomposer's
    fragment builder: defs copied, geometry translated into a 0-based viewport,
    raster assets embedded).

    ``ancestor_transform`` is the concatenated transform chain from the SVG root
    down to the measured groups' parent (e.g. a crop's ``translate(-440 -440)``).
    The measured bboxes are in final rendered space, but each copied element's
    own coordinates are in pre-ancestor-transform space, so the fragment must
    re-apply that chain before the viewport translate — otherwise the geometry
    lands off-canvas and the fragment renders blank."""
    x0, y0, w, h = _bounds(members)
    x0, y0 = math.floor(x0 - margin), math.floor(y0 - margin)
    w, h = math.ceil(w + 2 * margin), math.ceil(h + 2 * margin)
    frag = ET.Element(f"{{{SVG_NS}}}svg",
                      {"viewBox": f"0 0 {w} {h}", "width": str(w), "height": str(h)})
    for d in all_defs:
        frag.append(copy.deepcopy(d))
    content = ET.SubElement(frag, f"{{{SVG_NS}}}g",
                            {"transform": f"translate({-x0} {-y0})"})
    if ancestor_transform:
        content = ET.SubElement(content, f"{{{SVG_NS}}}g",
                                {"transform": ancestor_transform})
    # Members of the same source group: copy the whole group if any childless
    # leaf used it, else copy the group shell + just the referenced children.
    # Iterate groups in DOCUMENT order (ascending index), NOT member-traversal
    # order — paint order is document order, so a shared top layer (e.g. an icon
    # layer drawn last over all card backgrounds) must be copied last. Iterating
    # by traversal order would let a later card's background paint over an
    # earlier-inserted shared icon layer, hiding every icon but the first card's.
    by_group: dict[int, set] = {}
    for m in members:
        by_group.setdefault(m["group"], set()).add(m["child"])
    for gi in sorted(by_group):
        child_ids = by_group[gi]
        source = groups[gi]
        if None in child_ids:
            content.append(copy.deepcopy(source))
        else:
            shell = ET.Element(source.tag, dict(source.attrib))
            kids = list(source)
            for ci in sorted(child_ids):
                if 0 <= ci < len(kids):
                    shell.append(copy.deepcopy(kids[ci]))
            content.append(shell)
    embed_external_images(frag, source_dir)
    return frag


def process_item(item_dir: Path, min_area_frac: float, shape_tol: float,
                 merge_gap: float, margin: float, bg_coverage: float = 0.7,
                 group_gap_frac: float = 0.6, dedup_mae: float = 3.0,
                 split_gutter_px: float = 16.0) -> dict:
    visual = item_dir / "artifact" / "visual.svg"
    if not visual.exists():
        raise SystemExit(f"no artifact/visual.svg in {item_dir}")

    measured = measure(visual)
    canvas_w, canvas_h = float(measured["width"]), float(measured["height"])
    canvas_area = canvas_w * canvas_h

    root = ET.fromstring(visual.read_text(encoding="utf-8"))
    groups = document_groups(root)
    if len(groups) != len(measured["groups"]):
        raise SystemExit(
            f"group mismatch in {item_dir}: parsed {len(groups)} vs measured "
            f"{len(measured['groups'])} — SVG structure not understood")
    child_mismatch = _child_count_mismatch(groups, measured["groups"])
    if child_mismatch:
        detail = ", ".join(f"group {gi}: parsed {p} vs measured {m}"
                           for gi, p, m in child_mismatch)
        raise SystemExit(
            f"child-count mismatch in {item_dir} ({detail}) — measured child "
            f"indices would copy the wrong nodes; refusing to build fragments")
    all_defs = [copy.deepcopy(d) for d in root.iter(f"{{{SVG_NS}}}defs")]

    # The groups' bboxes were measured in final rendered space; capture the
    # transform chain from root down to their parent so fragments can re-apply
    # it (a crop wraps everything in translate(-crop_x -crop_y)).
    parent_map = {child: parent for parent in root.iter() for child in parent}
    ancestor_transform = _ancestor_transform(root, parent_map, groups[0]) if groups else ""

    leaves = _leaf_boxes(measured, window_pad=max(canvas_w, canvas_h) * 0.02)
    clusters = _cluster_spatial(leaves, merge_gap, canvas_w, canvas_h)
    # RC-1: un-glue distinct components that a small bridging leaf merged across
    # a clean gutter (e.g. a card sitting next to a photo).
    clusters = [sub for c in clusters
                for sub in _split_on_gutter(c, split_gutter_px)]

    instances: list[dict] = []
    background: list[dict] = []
    dropped_small: list[dict] = []
    for members in clusters:
        x0, y0, w, h = _bounds(members)
        area = w * h
        if area < min_area_frac * canvas_area:
            # Below the area floor — but record WHERE, so a genuine small
            # component (a lone icon/badge/logo) is inspectable instead of
            # vanishing behind a bare count.
            dropped_small.append({"x": round(x0, 1), "y": round(y0, 1),
                                  "w": round(w, 1), "h": round(h, 1),
                                  "area_frac": round(area / canvas_area, 4)})
            continue
        # A near-full-bleed cluster is the page background, not a component:
        # exclude it from the class list (mirrors how decompose_svg_objects.py
        # flags base-candidates). Otherwise a full-page extraction would emit
        # the background as a bogus "component".
        if area >= bg_coverage * canvas_area:
            background.append({"x": round(x0, 1), "y": round(y0, 1),
                               "w": round(w, 1), "h": round(h, 1),
                               "coverage": round(area / canvas_area, 4)})
            continue
        instances.append({"x": x0, "y": y0, "w": w, "h": h, "members": members})
    instances.sort(key=lambda i: (round(i["y"] / 20), i["x"]))

    # Classify by shape, then split each shape-class into proximity RUNS. A run
    # of same-shape instances sitting near each other (a row/grid) is ONE group
    # rendered as the whole strip with every member's real color/icon preserved
    # — the deliberate pattern, not a deduped single card. Same-shape instances
    # that sit far apart fall into separate groups (standalone items).
    shape_classes = _shape_classes(instances, shape_tol)
    comp_groups: list[dict] = []
    for ci, class_idxs in enumerate(shape_classes, start=1):
        for run in _proximity_groups(instances, class_idxs, group_gap_frac):
            comp_groups.append({"shape_class": ci, "members": run})

    def _group_bbox(member_idxs: list[int]) -> tuple[float, float, float, float]:
        return _bounds([instances[i] for i in member_idxs])

    comp_groups.sort(key=lambda g: (round(_group_bbox(g["members"])[1] / 20),
                                    _group_bbox(g["members"])[0]))

    out_dir = item_dir / "artifact" / "components"
    if out_dir.exists():
        for f in out_dir.iterdir():
            if f.is_file():
                f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = item_dir.name
    text_slots = _load_text_slots(item_dir)

    # Pass 1: build the whole-run fragment for each group, and a per-card
    # fragment for every member instance (written to a temp dir for the dedup
    # render). Each member is also a candidate distinct variable.
    render_tmp = Path(tempfile.mkdtemp(prefix="classify-cards-"))
    pending: list[dict] = []          # one entry per per-card render job
    group_plan: list[dict] = []
    try:
        for n, grp in enumerate(comp_groups, start=1):
            member_idxs = sorted(grp["members"], key=lambda i: instances[i]["x"])
            # Whole run: union of every member's leaf-members, so each variant
            # card (different color/icon) is reproduced as in the original.
            leaf_members = [m for i in member_idxs for m in instances[i]["members"]]
            whole = _build_fragment(leaf_members, groups, all_defs, margin,
                                    visual.parent, ancestor_transform)
            (out_dir / f"{prefix}-group-{n:02d}.svg").write_bytes(ET.tostring(whole))

            # One normalized render size per group so identical cards hash equal.
            ws = sorted(instances[i]["w"] for i in member_idxs)
            hs = sorted(instances[i]["h"] for i in member_idxs)
            mw, mh = ws[len(ws) // 2], hs[len(hs) // 2]
            tw = 160
            th = max(1, round(tw * mh / mw)) if mw else 160

            cards = []
            for k, i in enumerate(member_idxs, start=1):
                cfrag = _build_fragment(instances[i]["members"], groups, all_defs,
                                        margin, visual.parent, ancestor_transform)
                tmp_svg = render_tmp / f"g{n:02d}-c{k:02d}.svg"
                tmp_png = render_tmp / f"g{n:02d}-c{k:02d}.png"
                tmp_svg.write_bytes(ET.tostring(cfrag))
                pending.append({"svg": str(tmp_svg), "output": str(tmp_png),
                                "width": tw, "height": th})
                cards.append({"inst": i, "frag": cfrag, "png": str(tmp_png)})
            group_plan.append({"n": n, "grp": grp, "member_idxs": member_idxs,
                               "cards": cards})

        # Render every per-card fragment once, take its perceptual signature.
        sigs = _render_signatures([{"svg": p["svg"], "output": p["output"],
                                    "width": p["width"], "height": p["height"]}
                                   for p in pending])

        # Pass 2: within each group keep one card per distinct LOOK (collapse
        # identical AND near-identical color/icon/shape via signature distance),
        # write the kept per-card fragments, record.
        group_records: list[dict] = []
        for plan in group_plan:
            n, grp, member_idxs = plan["n"], plan["grp"], plan["member_idxs"]
            kept, counts = _collapse_duplicates(
                [sigs.get(c["png"]) for c in plan["cards"]],
                _signature_distance, dedup_mae)
            # RC-3: a single-member group's whole-run fragment IS the card —
            # the per-card SVG would be byte-identical to <prefix>-group-NN.svg,
            # producing a redundant duplicate tile in the catalog. Reuse the
            # group fragment as the card file instead of writing a twin.
            single_member = len(member_idxs) == 1
            card_records: list[dict] = []
            for m, (ci, dup) in enumerate(zip(kept, counts), start=1):
                card = plan["cards"][ci]
                inst = instances[card["inst"]]
                if single_member:
                    cfile = f"{prefix}-group-{n:02d}.svg"
                    card_id = f"{prefix}-group-{n:02d}"
                else:
                    cfile = f"{prefix}-group-{n:02d}-card-{m:02d}.svg"
                    card_id = f"{prefix}-group-{n:02d}-card-{m:02d}"
                    (out_dir / cfile).write_bytes(ET.tostring(card["frag"]))
                title = _heading(_slots_in(text_slots, inst["x"], inst["y"],
                                           inst["w"], inst["h"], canvas_w, canvas_h))
                card_records.append({
                    "card_id": card_id,
                    "file": f"components/{cfile}",
                    "title": title,
                    "bounds": {"x": round(inst["x"], 1), "y": round(inst["y"], 1),
                               "w": round(inst["w"], 1), "h": round(inst["h"], 1)},
                    "duplicate_count": dup,
                })
            gx, gy, gw, gh = _group_bbox(member_idxs)
            card_titles = [c["title"] for c in card_records]
            group_records.append({
                "group_id": f"{prefix}-group-{n:02d}",
                "file": f"components/{prefix}-group-{n:02d}.svg",
                "shape_class": grp["shape_class"],
                "title": _group_title(card_titles),
                "tags": _tags_from(card_titles),
                "member_count": len(member_idxs),
                "distinct_card_count": len(card_records),
                "group_bounds": {"x": round(gx, 1), "y": round(gy, 1),
                                 "w": round(gw, 1), "h": round(gh, 1)},
                "member_bounds": [
                    {"x": round(instances[i]["x"], 1), "y": round(instances[i]["y"], 1),
                     "w": round(instances[i]["w"], 1), "h": round(instances[i]["h"], 1)}
                    for i in member_idxs],
                "cards": card_records,
            })
    finally:
        shutil.rmtree(render_tmp, ignore_errors=True)

    manifest = {
        "source_visual": "artifact/visual.svg",
        "canvas": {"w": canvas_w, "h": canvas_h},
        "instance_count": len(instances),
        "shape_class_count": len(shape_classes),
        "group_count": len(group_records),
        "dropped_small_clusters": len(dropped_small),
        "dropped_small": dropped_small,
        "background_candidates": background,
        "params": {"min_area_frac": min_area_frac, "shape_tol": shape_tol,
                   "merge_gap": merge_gap, "margin": margin, "bg_coverage": bg_coverage,
                   "group_gap_frac": group_gap_frac, "dedup_mae": dedup_mae},
        "groups": group_records,
    }
    (out_dir / "components-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _run_script(script: Path, args: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"{script.name} failed (exit {proc.returncode}):\n"
            f"{(proc.stderr or proc.stdout or '').strip()}"
        )


def materialize_groups(item_dir: Path, manifest: dict) -> list[Path]:
    """Create a real staging item for each group in the manifest.

    Returns the list of newly created item directories.
    """
    groups = manifest.get("groups") or []
    canvas = manifest["canvas"]
    if not groups:
        return []

    base_mapping_path = item_dir / "mapping.json"
    if not base_mapping_path.exists():
        return []
    base_mapping = load_json(base_mapping_path)

    # Deduplicate groups by shape_class: keep only the first representative
    # of each shape class. Multiple proximity runs of the same shape are the
    # same component at different positions — only one needs to be staged.
    seen_shapes: set[int] = set()
    deduped = []
    for rec in groups:
        sc = rec.get("shape_class")
        if sc in seen_shapes:
            continue
        seen_shapes.add(sc)
        deduped.append(rec)
    groups = deduped
    base_source = base_mapping.get("source", {})
    source_path = base_source.get("path", "")
    source_sha = base_source.get("sha256", "")
    slide_or_page = base_source.get("slide_or_page", "1")
    base_intent = base_mapping.get("semantic_intent", [])
    base_slug = item_dir.name
    items_dir = item_dir.parent

    base_visual = item_dir / "artifact" / "visual.svg"
    base_slots = item_dir / "artifact" / "text-slots.json"
    if not base_visual.exists():
        return []

    created: list[Path] = []
    for n, rec in enumerate(groups, start=1):
        nn = f"{n:02d}"
        group_item_id = f"{base_slug}-g{nn}"
        candidate_id = f"sun.component.{base_slug}.g{nn}"
        group_dir = items_dir / group_item_id

        gb = rec["group_bounds"]
        region = normalized_bounds({
            "x": gb["x"] / canvas["w"],
            "y": gb["y"] / canvas["h"],
            "width": gb["w"] / canvas["w"],
            "height": gb["h"] / canvas["h"],
            "unit": "normalized",
        })

        intent = list(base_intent) + (rec.get("tags") or [])
        region_hash = region_identity_hash(
            source_sha, slide_or_page, region,
            base_source.get("object_ids", []),
        )
        semantic_hash = semantic_signature_hash(intent)

        artifact_dir = group_dir / "artifact"
        evidence_dir = group_dir / "evidence"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(base_visual, artifact_dir / "visual.svg")
        if base_slots.exists():
            shutil.copy2(base_slots, artifact_dir / "text-slots.json")
            # The parent's text-slots.json carries a region_crop marker from its
            # own crop pass. crop_svg_region.py is idempotent: it sees that marker
            # and returns "already-cropped" without re-cropping. But the group has
            # its OWN sub-region, so we must clear the marker so the crop script
            # actually crops the copied visual to the group's bounds.
            group_slots_path = artifact_dir / "text-slots.json"
            group_contract = load_json(group_slots_path)
            if (group_contract.get("source") or {}).get("region_crop"):
                del group_contract["source"]["region_crop"]
                group_slots_path.write_text(
                    json.dumps(group_contract, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

        base_assets = item_dir / "artifact" / "assets"
        if base_assets.is_dir():
            shutil.copytree(base_assets, artifact_dir / "assets", dirs_exist_ok=True)

        # Copy this group's fragment SVG + per-card variant SVGs into the
        # materialized item so collect_images() builds the full carousel
        # (whole row → per-card variants → source).
        base_comps = item_dir / "artifact" / "components"
        group_id = rec.get("group_id", f"{base_slug}-group-{nn}")
        if base_comps.is_dir():
            comp_dir = artifact_dir / "components"
            comp_dir.mkdir(exist_ok=True)
            group_file = f"{group_id}.svg"
            src_frag = base_comps / group_file
            if src_frag.exists():
                shutil.copy2(src_frag, comp_dir / group_file)
            for card in rec.get("cards", []):
                card_file = card.get("file", "")
                if card_file:
                    src_card = item_dir / "artifact" / card_file
                    if src_card.exists():
                        shutil.copy2(src_card, comp_dir / src_card.name)
            scoped_manifest = {
                "groups": [{
                    **rec,
                    "file": f"components/{group_file}",
                    "cards": [{**c, "file": f"components/{Path(c['file']).name}"}
                              for c in rec.get("cards", [])
                              if c.get("file")],
                }],
            }
            write_json(comp_dir / "components-manifest.json", scoped_manifest)

        base_evidence_svg = item_dir / "evidence" / "source-with-text.svg"
        if base_evidence_svg.exists():
            shutil.copy2(base_evidence_svg, evidence_dir / "source-with-text.svg")

        evidence_dir.joinpath("notes.md").write_text(
            f"# Evidence — {group_item_id}\n\n"
            f"Materialized from group {rec.get('group_id', nn)} "
            f"of base item `{base_slug}`.\n",
            encoding="utf-8",
        )

        group_title = rec.get("title", "")
        group_tags = rec.get("tags") or []
        base_title = base_slug.replace("-", " ").title()
        display_name = f"{base_title} — {group_title}" if group_title else base_title

        mapping = {
            "extraction_id": base_mapping.get("extraction_id", ""),
            "item_id": group_item_id,
            "candidate_stable_id": candidate_id,
            "name": display_name,
            "status": "staging",
            "type": "component",
            "category": base_mapping.get("category", "component"),
            "brand": base_mapping.get("brand", "sun-studio"),
            "source": {
                "path": source_path,
                "sha256": source_sha,
                "slide_or_page": slide_or_page,
                "region": region,
                "object_ids": base_source.get("object_ids", []),
            },
            "fingerprints": {
                "region_identity_sha256": region_hash,
                "semantic_signature_sha256": semantic_hash,
                "perceptual_hash": None,
            },
            "semantic_intent": intent,
            "tags": group_tags,
            "content_fields": {"required": [], "optional": []},
            "variables": [],
            "variants": [],
            "limitations": [],
            "approval": {"status": "pending", "approved_by": None, "approved_at": None},
            "duplicate_of": None,
        }
        write_json(group_dir / "mapping.json", mapping)

        _run_script(CROP_SCRIPT, ["--item-dir", str(group_dir)])
        # Skip validate on materialized groups: the evidence SVG carries the
        # parent's full text content, but slots cover only this sub-region —
        # unmapped source text warnings are expected, not a real coverage gap.
        created.append(group_dir)
        print(f"  materialized {group_item_id} (region {region['x']:.4f},{region['y']:.4f} "
              f"{region['width']:.4f}×{region['height']:.4f})")

    if created:
        batch_dir = items_dir.parent
        _run_script(EXTERNALIZE_SCRIPT, ["--batch", str(batch_dir)])
        _run_script(OPTIMIZE_SCRIPT, ["--batch", str(batch_dir)])
        _run_script(TEXT_CONTRACT_SCRIPT, ["--batch", str(batch_dir)])

        base_mapping["decomposed_into"] = [d.name for d in created]
        write_json(base_mapping_path, base_mapping)

    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", action="append", required=True, type=Path)
    parser.add_argument("--min-area-frac", type=float, default=0.015,
                        help="Drop clusters smaller than this fraction of canvas area")
    parser.add_argument("--shape-tol", type=float, default=0.14,
                        help="Relative w/h tolerance for 'same shape'")
    parser.add_argument("--merge-gap", type=float, default=6.0,
                        help="Treat bboxes within this many px as overlapping")
    parser.add_argument("--margin", type=float, default=3.0,
                        help="Padding around each representative bbox in px")
    parser.add_argument("--bg-coverage", type=float, default=0.7,
                        help="Clusters covering >= this fraction of the canvas are "
                             "treated as background, not components")
    parser.add_argument("--group-gap-frac", type=float, default=0.6,
                        help="Same-shape instances within this fraction of their "
                             "size (per axis) are grouped into one proximity run")
    parser.add_argument("--dedup-mae", type=float, default=3.0,
                        help="Cards whose rendered signatures differ by <= this "
                             "mean-absolute-error (0-255) are treated as the same "
                             "and collapsed (color/icon-sensitive perceptual dedup)")
    parser.add_argument("--split-gutter-px", type=float, default=16.0,
                        help="Split a clustered instance into separate components "
                             "when a clean empty band wider than this (px) divides "
                             "its large leaves (un-glues e.g. a card next to a photo)")
    parser.add_argument("--materialize-groups", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Create real staging items for each detected group "
                             "(default: on)")
    args = parser.parse_args()

    for item_dir in args.item_dir:
        resolved = item_dir.resolve()
        m = process_item(resolved, args.min_area_frac, args.shape_tol,
                         args.merge_gap, args.margin, args.bg_coverage,
                         args.group_gap_frac, args.dedup_mae, args.split_gutter_px)
        print(f"{item_dir.name}: {m['instance_count']} instance(s) -> "
              f"{m['shape_class_count']} shape-class(es) -> "
              f"{m['group_count']} group(s) (dropped {m['dropped_small_clusters']} small)")
        for rec in m["groups"]:
            print(f"  {rec['group_id']}: {rec['member_count']} member(s) "
                  f"[shape-class {rec['shape_class']}] @ {rec['group_bounds']}")
        if m.get("dropped_small"):
            print(f"  WARNING: dropped {len(m['dropped_small'])} small cluster(s) "
                  f"below min-area-frac (may be real small components): "
                  f"{m['dropped_small']}")
        if args.materialize_groups and m.get("groups"):
            created = materialize_groups(resolved, m)
            print(f"  -> materialized {len(created)} group item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
