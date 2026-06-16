#!/usr/bin/env python3
"""Generate a publish-grade preview/ for one staging item.

Full-slide templates delegate to generate_template_preview.py (PDF/SVG render
of the whole slide). Atomic items (component/section/style/icon/background/
card/asset) render their evidence/source-with-text.svg (or artifact/visual.svg)
to preview/thumbnail.png via render_svg.js, and write a self-contained
preview.html. Either way the item ends up with a non-empty preview/, which is
the gate publish_extraction.py enforces.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RENDER_SVG = SCRIPT_DIR / "render_svg.js"
TEMPLATE_PREVIEW = SCRIPT_DIR / "generate_template_preview.py"

VIEWBOX_RE = re.compile(r'viewBox\s*=\s*"([\d.\s-]+)"')
WIDTH_RE = re.compile(r'\bwidth\s*=\s*"([\d.]+)')
HEIGHT_RE = re.compile(r'\bheight\s*=\s*"([\d.]+)')


def svg_dimensions(svg_text: str) -> tuple[int, int]:
    """Best-effort intrinsic size for an SVG, defaulting to a sane box."""
    width = WIDTH_RE.search(svg_text)
    height = HEIGHT_RE.search(svg_text)
    if width and height:
        return max(1, round(float(width.group(1)))), max(1, round(float(height.group(1))))
    box = VIEWBOX_RE.search(svg_text)
    if box:
        parts = box.group(1).replace(",", " ").split()
        if len(parts) == 4:
            return max(1, round(float(parts[2]))), max(1, round(float(parts[3])))
    return 1920, 1080


def render_atomic(item_dir: Path) -> dict:
    preview_dir = item_dir / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    source = item_dir / "evidence" / "source-with-text.svg"
    if not source.exists():
        source = item_dir / "artifact" / "visual.svg"
    if not source.exists():
        raise SystemExit("No evidence/source-with-text.svg or artifact/visual.svg to render.")

    svg_text = source.read_text(encoding="utf-8")
    width, height = svg_dimensions(svg_text)
    # Cap the longest edge so atomic thumbnails stay reasonable.
    cap = 1600
    longest = max(width, height)
    if longest > cap:
        scale = cap / longest
        width = max(1, round(width * scale))
        height = max(1, round(height * scale))

    thumbnail = preview_dir / "thumbnail.png"
    jobs = [{"svg": str(source.resolve()), "output": str(thumbnail.resolve()),
             "width": width, "height": height}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(jobs, handle)
        jobs_path = handle.name
    try:
        result = subprocess.run(
            ["node", str(RENDER_SVG), "--jobs", jobs_path],
            capture_output=True, text=True,
        )
    finally:
        Path(jobs_path).unlink(missing_ok=True)
    if result.returncode != 0 or not thumbnail.exists():
        raise SystemExit(f"render_svg.js failed: {result.stderr.strip() or result.stdout.strip()}")

    preview_html = preview_dir / "preview.html"
    preview_html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Preview</title><style>html,body{margin:0;background:#FFFDF8;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh}"
        f"svg{{max-width:100%;height:auto}}</style></head><body>{svg_text}</body></html>",
        encoding="utf-8",
    )
    return {"type": "atomic", "thumbnail": str(thumbnail), "width": width, "height": height}


def render_template(item_dir: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(TEMPLATE_PREVIEW), "--item-dir", str(item_dir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"generate_template_preview.py failed: {result.stderr.strip() or result.stdout.strip()}")
    return {"type": "template", "stdout": result.stdout.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", required=True, help="Staging item directory (contains mapping.json).")
    args = parser.parse_args()

    item_dir = Path(args.item_dir).resolve()
    mapping_path = item_dir / "mapping.json"
    if not mapping_path.exists():
        raise SystemExit(f"Missing mapping: {mapping_path}")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    item_type = mapping.get("type", "unknown")

    info = render_template(item_dir) if item_type == "template" else render_atomic(item_dir)
    print(json.dumps({"ok": True, "id": mapping.get("candidate_stable_id", mapping.get("id")),
                      "item_type": item_type, **info}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
