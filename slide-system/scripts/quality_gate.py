#!/usr/bin/env python3
"""Post-stage quality gate for component Draft artifacts.

The default pass is structural and fast. A caller can opt into a scoped render
check for freshly staged items, which catches SVGs that contain XML but render
blank because the visible content is off-canvas, masked, or cropped away.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from _common import load_json, write_json

SCRIPT_DIR = Path(__file__).resolve().parent
RENDER_SVG = SCRIPT_DIR / "render_svg.js"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
VISIBLE_TAGS = {
    "circle", "ellipse", "image", "line", "path", "polygon", "polyline",
    "rect", "text", "use",
}
NON_RENDERING_TAGS = {
    "clipPath", "defs", "filter", "linearGradient", "mask", "metadata",
    "pattern", "radialGradient", "style", "symbol",
}
VISIBLE_COLOR_RE = re.compile(r"#(?!fff(?:fff)?\b)[0-9a-f]{3,8}|rgb\(|hsl\(", re.I)
DEFAULT_RENDER_BLANK_RATIO = 0.003


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _style_value(style: str, key: str) -> str | None:
    for part in style.split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        if name.strip().lower() == key:
            return value.strip()
    return None


def _attr(el: ET.Element, name: str) -> str | None:
    value = el.get(name)
    if value is not None:
        return value
    return _style_value(el.get("style", ""), name)


def _visible_paint(value: str | None) -> bool:
    if not value:
        return False
    normalized = re.sub(r"\s+", "", value.strip().lower())
    if normalized in {
        "none", "transparent", "white", "#fff", "#ffffff", "#ffffffff",
        "rgb(255,255,255)", "rgba(255,255,255,1)",
        "rgba(255,255,255,0)", "rgba(255,255,255,0.0)",
    }:
        return False
    return True


def _element_has_visible_content(el: ET.Element) -> bool:
    tag = _local_name(el.tag)
    if tag not in VISIBLE_TAGS:
        return False
    if _attr(el, "display") == "none" or _attr(el, "visibility") == "hidden":
        return False
    opacity = _attr(el, "opacity")
    if opacity is not None:
        try:
            if float(opacity) <= 0:
                return False
        except ValueError:
            pass
    if tag in {"image", "text", "use"}:
        return True
    if _visible_paint(_attr(el, "fill")) or _visible_paint(_attr(el, "stroke")):
        return True
    style = el.get("style", "")
    return bool(VISIBLE_COLOR_RE.search(style) and "255,255,255" not in re.sub(r"\s+", "", style))


def _walk_rendering_elements(el: ET.Element, *, in_non_rendering: bool = False):
    tag = _local_name(el.tag)
    hidden = in_non_rendering or tag in NON_RENDERING_TAGS
    if not hidden:
        yield el
    for child in list(el):
        yield from _walk_rendering_elements(child, in_non_rendering=hidden)


def svg_has_visible_content(path: Path) -> bool:
    """Best-effort structural blank detector.

    It deliberately errs on the side of keeping uncertain SVGs: gradients,
    images, text, and symbol uses count as visible. Empty SVGs, transparent
    elements, and white-only placeholder shapes are pruned.
    """
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return True
    for el in _walk_rendering_elements(root):
        if _element_has_visible_content(el):
            return True
    return False


def _parse_svg_length(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value)
    if not match:
        return None
    return max(1, int(round(float(match.group(1)))))


def _svg_dimensions(path: Path) -> tuple[int, int]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return 800, 600
    width = _parse_svg_length(root.get("width"))
    height = _parse_svg_length(root.get("height"))
    view_box = root.get("viewBox") or root.get("viewbox")
    if (not width or not height) and view_box:
        parts = [p for p in re.split(r"[\s,]+", view_box.strip()) if p]
        if len(parts) == 4:
            try:
                vb_w = int(round(float(parts[2])))
                vb_h = int(round(float(parts[3])))
                width = width or vb_w
                height = height or vb_h
            except ValueError:
                pass
    width = min(max(width or 800, 16), 4096)
    height = min(max(height or 600, 16), 4096)
    return width, height


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _png_nonwhite_ratio(path: Path) -> float:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    width = height = bit_depth = color_type = None
    idat: list[bytes] = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            idat.append(payload)
        elif kind == b"IEND":
            break
    if not width or not height or bit_depth != 8 or color_type not in {0, 2, 4, 6}:
        raise ValueError("unsupported PNG format")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    stride = width * channels
    raw = zlib.decompress(b"".join(idat))
    prev = bytearray(stride)
    offset = 0
    nonwhite = 0
    for _y in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[i] = (row[i] + _paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError("unsupported PNG filter")
        for x in range(width):
            p = x * channels
            if color_type == 0:
                r = g = b = row[p]
                alpha = 255
            elif color_type == 2:
                r, g, b = row[p], row[p + 1], row[p + 2]
                alpha = 255
            elif color_type == 4:
                r = g = b = row[p]
                alpha = row[p + 1]
            else:
                r, g, b, alpha = row[p], row[p + 1], row[p + 2], row[p + 3]
            if alpha > 8 and (r < 245 or g < 245 or b < 245):
                nonwhite += 1
        prev = row
    return nonwhite / float(width * height)


def _path_key(path: Path) -> str:
    return str(path.resolve()).lower()


def _copy_render_context(src: Path, item_dir: Path, dest_root: Path) -> Path:
    artifact_dir = item_dir / "artifact"
    try:
        rel = src.relative_to(artifact_dir)
        context_src = artifact_dir
    except ValueError:
        rel = src.relative_to(item_dir)
        context_src = item_dir
    dest = dest_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    for assets_rel in ("assets", "artifact/assets"):
        assets_src = context_src / assets_rel
        if assets_src.is_dir():
            shutil.copytree(assets_src, dest_root / assets_rel, dirs_exist_ok=True)
    return dest


def _render_svg_paths(paths_by_item: dict[Path, set[Path]]) -> dict[str, dict]:
    paths = sorted({p.resolve() for refs in paths_by_item.values() for p in refs})
    if not paths:
        return {}
    if not RENDER_SVG.exists():
        return {_path_key(p): {"error": "render_svg.js is missing"} for p in paths}
    with tempfile.TemporaryDirectory(prefix="component-render-gate-") as tmp:
        tmp_root = Path(tmp)
        jobs = []
        output_by_original: dict[str, Path] = {}
        item_for_path: dict[Path, Path] = {
            path.resolve(): item.resolve()
            for item, refs in paths_by_item.items()
            for path in refs
        }
        for idx, original in enumerate(paths):
            item_dir = item_for_path[original]
            mirror_dir = tmp_root / f"job-{idx:04d}"
            try:
                mirrored = _copy_render_context(original, item_dir, mirror_dir)
                width, height = _svg_dimensions(mirrored)
            except Exception as exc:
                output_by_original[_path_key(original)] = Path(f"ERROR:{exc}")
                continue
            output = tmp_root / "renders" / f"{idx:04d}.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            jobs.append({
                "svg": str(mirrored),
                "output": str(output),
                "width": width,
                "height": height,
            })
            output_by_original[_path_key(original)] = output
        jobs_path = tmp_root / "jobs.json"
        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        if jobs:
            try:
                proc = subprocess.run(
                    ["node", str(RENDER_SVG), "--jobs", str(jobs_path)],
                    cwd=str(SCRIPT_DIR.parents[1]),
                    capture_output=True,
                    text=True,
                )
            except OSError as exc:
                return {_path_key(p): {"error": str(exc)} for p in paths}
            if proc.returncode != 0:
                error = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
                return {_path_key(p): {"error": error[:1000] or "render failed"} for p in paths}
        results: dict[str, dict] = {}
        for original in paths:
            key = _path_key(original)
            output = output_by_original.get(key)
            if output is None:
                results[key] = {"error": "render output missing"}
            elif str(output).startswith("ERROR:"):
                results[key] = {"error": str(output)[6:]}
            elif not output.exists():
                results[key] = {"error": "render output missing"}
            else:
                try:
                    ratio = _png_nonwhite_ratio(output)
                    results[key] = {"nonwhite_ratio": ratio}
                except Exception as exc:
                    results[key] = {"error": str(exc)}
        return results


def _artifact_ref(item_dir: Path, value: object) -> Path | None:
    if not value:
        return None
    rel = Path(str(value))
    if rel.is_absolute() or ".." in rel.parts:
        return None
    return item_dir / "artifact" / rel


def _valid_ref(item_dir: Path, value: object) -> bool:
    path = _artifact_ref(item_dir, value)
    if path is None or not path.exists():
        return False
    if path.suffix.lower() == ".svg":
        return svg_has_visible_content(path)
    return path.stat().st_size > 0


def _render_blank(path: Path, render_results: dict[str, dict] | None, threshold: float) -> bool:
    if not render_results or path.suffix.lower() != ".svg":
        return False
    result = render_results.get(_path_key(path))
    if not result or result.get("error"):
        return False
    return float(result.get("nonwhite_ratio", 1.0)) < threshold


def _candidate_render_paths(item_dir: Path) -> set[Path]:
    refs: set[Path] = set()
    visual = item_dir / "artifact" / "visual.svg"
    if visual.exists():
        refs.add(visual)
    manifest_path = item_dir / "artifact" / "components" / "components-manifest.json"
    if not manifest_path.exists():
        return refs
    try:
        manifest = load_json(manifest_path)
    except Exception:
        return refs
    for group in manifest.get("groups") or []:
        for value in [group.get("file")]:
            path = _artifact_ref(item_dir, value)
            if path and path.exists() and path.suffix.lower() == ".svg":
                refs.add(path)
        for card in group.get("cards") or []:
            for key in ("file", "source_file"):
                path = _artifact_ref(item_dir, card.get(key))
                if path and path.exists() and path.suffix.lower() == ".svg":
                    refs.add(path)
    return refs


def _clean_group(
    item_dir: Path,
    group: dict,
    render_results: dict[str, dict] | None,
    render_threshold: float,
) -> tuple[dict | None, int, int]:
    pruned = 0
    render_pruned = 0
    out = dict(group)
    file_value = out.get("file")
    if file_value:
        file_path = _artifact_ref(item_dir, file_value)
        if not _valid_ref(item_dir, file_value):
            out.pop("file", None)
            pruned += 1
        elif file_path and _render_blank(file_path, render_results, render_threshold):
            out.pop("file", None)
            render_pruned += 1
    cards = []
    for card in out.get("cards") or []:
        clean = dict(card)
        has_visual_ref = False
        for key in ("file", "source_file"):
            if clean.get(key):
                ref_path = _artifact_ref(item_dir, clean[key])
                if _valid_ref(item_dir, clean[key]) and not (
                    ref_path and _render_blank(ref_path, render_results, render_threshold)
                ):
                    has_visual_ref = True
                else:
                    clean.pop(key, None)
                    if ref_path and _render_blank(ref_path, render_results, render_threshold):
                        render_pruned += 1
                    else:
                        pruned += 1
        if has_visual_ref:
            cards.append(clean)
    out["cards"] = cards
    if not out.get("file") and not cards:
        return None, pruned, render_pruned
    return out, pruned, render_pruned


def sanitize_item(
    item_dir: Path,
    *,
    render_results: dict[str, dict] | None = None,
    render_threshold: float = DEFAULT_RENDER_BLANK_RATIO,
) -> dict:
    item_dir = item_dir.resolve()
    manifest_path = item_dir / "artifact" / "components" / "components-manifest.json"
    mapping_path = item_dir / "mapping.json"
    summary = {
        "item_dir": str(item_dir),
        "blank_refs_pruned": 0,
        "render_blank_refs_pruned": 0,
        "empty_manifests_removed": 0,
        "blank_item_visual": False,
        "item_visual_nonwhite_ratio": None,
        "render_errors": 0,
        "render_checked_refs": 0,
        "status": "reviewable",
    }
    visual_path = item_dir / "artifact" / "visual.svg"
    if render_results:
        for ref in _candidate_render_paths(item_dir):
            result = render_results.get(_path_key(ref))
            if not result:
                continue
            if result.get("error"):
                summary["render_errors"] += 1
            else:
                summary["render_checked_refs"] += 1
        result = render_results.get(_path_key(visual_path))
        if result and not result.get("error"):
            ratio = float(result.get("nonwhite_ratio", 1.0))
            summary["item_visual_nonwhite_ratio"] = ratio
            if ratio < render_threshold:
                summary["blank_item_visual"] = True
                summary["status"] = "needs_review"
    if not manifest_path.exists():
        _write_mapping_quality(mapping_path, summary)
        return summary
    try:
        manifest = load_json(manifest_path)
    except Exception:
        summary["status"] = "needs_review"
        _write_mapping_quality(mapping_path, summary)
        return summary

    groups = []
    for group in manifest.get("groups") or []:
        clean_group, pruned, render_pruned = _clean_group(
            item_dir, group, render_results, render_threshold)
        summary["blank_refs_pruned"] += pruned
        summary["render_blank_refs_pruned"] += render_pruned
        if clean_group is not None:
            groups.append(clean_group)

    if not groups:
        manifest_path.unlink(missing_ok=True)
        summary["empty_manifests_removed"] = 1
        summary["status"] = "needs_review"
    else:
        manifest["groups"] = groups
        write_json(manifest_path, manifest)
        if (
            summary["blank_refs_pruned"] or summary["render_blank_refs_pruned"]
        ) and summary["status"] != "needs_review":
            summary["status"] = "reviewable"
    _write_mapping_quality(mapping_path, summary)
    return summary


def sanitize_items(
    item_dirs: list[Path],
    *,
    render_check: bool = False,
    render_threshold: float = DEFAULT_RENDER_BLANK_RATIO,
    render_results: dict[str, dict] | None = None,
) -> list[dict]:
    resolved = [Path(p).resolve() for p in item_dirs]
    if render_check and render_results is None:
        paths_by_item = {
            item_dir: _candidate_render_paths(item_dir)
            for item_dir in resolved
        }
        render_results = _render_svg_paths(paths_by_item)
    return [
        sanitize_item(item_dir, render_results=render_results, render_threshold=render_threshold)
        for item_dir in resolved
    ]


def _write_mapping_quality(mapping_path: Path, summary: dict) -> None:
    if not mapping_path.exists():
        return
    mapping = load_json(mapping_path)
    mapping["quality_gate"] = {
        "status": summary["status"],
        "blank_refs_pruned": summary["blank_refs_pruned"],
        "render_blank_refs_pruned": summary["render_blank_refs_pruned"],
        "empty_manifests_removed": summary["empty_manifests_removed"],
        "blank_item_visual": summary["blank_item_visual"],
        "item_visual_nonwhite_ratio": summary["item_visual_nonwhite_ratio"],
        "render_checked_refs": summary["render_checked_refs"],
        "render_errors": summary["render_errors"],
        "method": "structural-and-render-manifest-prune",
    }
    write_json(mapping_path, mapping)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", action="append", required=True)
    parser.add_argument("--render-check", action="store_true",
                        help="Render candidate SVGs and prune refs that render blank.")
    parser.add_argument("--render-threshold", type=float, default=DEFAULT_RENDER_BLANK_RATIO,
                        help="Minimum non-white pixel ratio for an SVG to count as visible.")
    args = parser.parse_args(argv)
    summaries = sanitize_items(
        [Path(p) for p in args.item_dir],
        render_check=args.render_check,
        render_threshold=args.render_threshold,
    )
    print(json.dumps({"items": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
