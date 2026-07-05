#!/usr/bin/env python3
"""Lightweight post-stage quality gate for component Draft artifacts.

This is intentionally structural and fast. It does not launch Chromium or run
pixel checks in the `/component` hot path. Browser/pixel audits remain a tester
workflow; this gate only removes obviously unusable manifest references and
records whether a Draft needs closer human review.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from _common import load_json, write_json

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
VISIBLE_TAGS = {
    "circle", "ellipse", "image", "line", "path", "polygon", "polyline",
    "rect", "text", "use",
}
VISIBLE_COLOR_RE = re.compile(r"#(?!fff(?:fff)?\b)[0-9a-f]{3,8}|rgb\(|hsl\(", re.I)


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
    for el in root.iter():
        tag = _local_name(el.tag)
        if tag not in VISIBLE_TAGS:
            continue
        if _attr(el, "display") == "none" or _attr(el, "visibility") == "hidden":
            continue
        opacity = _attr(el, "opacity")
        if opacity is not None:
            try:
                if float(opacity) <= 0:
                    continue
            except ValueError:
                pass
        if tag in {"image", "text", "use"}:
            return True
        fill = (_attr(el, "fill") or "").strip().lower()
        stroke = (_attr(el, "stroke") or "").strip().lower()
        if fill and fill not in {"none", "transparent", "#fff", "#ffffff"}:
            return True
        if stroke and stroke not in {"none", "transparent", "#fff", "#ffffff"}:
            return True
        if VISIBLE_COLOR_RE.search(el.get("style", "")):
            return True
    return False


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


def _clean_group(item_dir: Path, group: dict) -> tuple[dict | None, int]:
    pruned = 0
    out = dict(group)
    file_value = out.get("file")
    if file_value and not _valid_ref(item_dir, file_value):
        out.pop("file", None)
        pruned += 1
    cards = []
    for card in out.get("cards") or []:
        clean = dict(card)
        has_visual_ref = False
        for key in ("file", "source_file"):
            if clean.get(key):
                if _valid_ref(item_dir, clean[key]):
                    has_visual_ref = True
                else:
                    clean.pop(key, None)
                    pruned += 1
        if has_visual_ref:
            cards.append(clean)
    out["cards"] = cards
    if not out.get("file") and not cards:
        return None, pruned
    return out, pruned


def sanitize_item(item_dir: Path) -> dict:
    item_dir = item_dir.resolve()
    manifest_path = item_dir / "artifact" / "components" / "components-manifest.json"
    mapping_path = item_dir / "mapping.json"
    summary = {
        "item_dir": str(item_dir),
        "blank_refs_pruned": 0,
        "empty_manifests_removed": 0,
        "status": "reviewable",
    }
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
        clean_group, pruned = _clean_group(item_dir, group)
        summary["blank_refs_pruned"] += pruned
        if clean_group is not None:
            groups.append(clean_group)

    if not groups:
        manifest_path.unlink(missing_ok=True)
        summary["empty_manifests_removed"] = 1
        summary["status"] = "needs_review"
    else:
        manifest["groups"] = groups
        write_json(manifest_path, manifest)
        if summary["blank_refs_pruned"]:
            summary["status"] = "reviewable"
    _write_mapping_quality(mapping_path, summary)
    return summary


def _write_mapping_quality(mapping_path: Path, summary: dict) -> None:
    if not mapping_path.exists():
        return
    mapping = load_json(mapping_path)
    mapping["quality_gate"] = {
        "status": summary["status"],
        "blank_refs_pruned": summary["blank_refs_pruned"],
        "empty_manifests_removed": summary["empty_manifests_removed"],
        "method": "structural-manifest-prune",
    }
    write_json(mapping_path, mapping)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", action="append", required=True)
    args = parser.parse_args(argv)
    summaries = [sanitize_item(Path(p)) for p in args.item_dir]
    print(json.dumps({"items": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
