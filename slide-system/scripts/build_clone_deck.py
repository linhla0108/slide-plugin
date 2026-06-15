#!/usr/bin/env python3
"""build_clone_deck.py — compose a 1:1 layered deck HTML from an extraction batch.

Each page's decomposed visual fragments become separate export overlays, while
full-bleed base candidates become passive CSS backgrounds. Each
`artifact/text-slots.json` slot becomes an editable leaf text element positioned
inside a fixed 1920x1080 stage. Non-16:9 source pages can be fitted into that
stage without distortion.

The output HTML follows the capture convention the export stack expects:
`.slide` / `.slide.active` + a global `goToSlide(n)` (see capture-slides.js
`--showJs "goToSlide({n})" --selector ".slide.active"`).

    python3 slide-system/scripts/build_clone_deck.py \
        --extraction-dir outputs/component-extractions/<id> \
        --decomposed-assets-dir outputs/slide-jobs/<job>/runs/<run>/assets \
        --font-css <path/to/colors_and_type.css> \
        --output <run>/deck.html
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from pathlib import Path

STAGE_W = 1920.0
STAGE_H = 1080.0

# Map a slot's font_weight to a numeric CSS weight the @font-face stack defines.
_WEIGHT = {"thin": 100, "light": 300, "normal": 400, "regular": 400,
           "medium": 500, "semibold": 600, "bold": 700, "extrabold": 800,
           "black": 900}


def css_weight(value) -> str:
    s = str(value).strip().lower()
    if s.isdigit():
        return s
    return str(_WEIGHT.get(s, 400))


def layout_box(source_w: float, source_h: float, fit_mode: str,
               stage_w: float = STAGE_W, stage_h: float = STAGE_H) -> dict[str, float]:
    if fit_mode == "stretch":
        return {
            "left": 0.0,
            "top": 0.0,
            "width": stage_w,
            "height": stage_h,
            "scale_x": stage_w / source_w,
            "scale_y": stage_h / source_h,
        }
    scale = min(stage_w / source_w, stage_h / source_h)
    width = source_w * scale
    height = source_h * scale
    return {
        "left": (stage_w - width) / 2.0,
        "top": (stage_h - height) / 2.0,
        "width": width,
        "height": height,
        "scale_x": scale,
        "scale_y": scale,
    }


def fit_bounds(bounds: dict, box: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        box["left"] + float(bounds["x"]) * box["scale_x"],
        box["top"] + float(bounds["y"]) * box["scale_y"],
        float(bounds["w"]) * box["scale_x"],
        float(bounds["h"]) * box["scale_y"],
    )


def source_size(contract: dict, svg_path: Path) -> tuple[float, float]:
    src = contract.get("source", {})
    if src.get("canvas_width") and src.get("canvas_height"):
        return float(src["canvas_width"]), float(src["canvas_height"])
    raw = svg_path.read_text(encoding="utf-8")
    view_box = re.search(r'viewBox="[^"]*\s([0-9.]+)\s([0-9.]+)"', raw)
    if view_box:
        return float(view_box.group(1)), float(view_box.group(2))
    size = re.search(r'width="([0-9.]+)"\s+height="([0-9.]+)"', raw)
    if size:
        return float(size.group(1)), float(size.group(2))
    raise SystemExit(f"Unable to determine source size for {svg_path}")


def inline_svg(svg_path: Path, width: float, height: float) -> str:
    """Return the <svg> markup sized to the fitted page box."""
    raw = svg_path.read_text(encoding="utf-8")
    # Drop any XML prolog so the SVG can be inlined inside the slide div.
    raw = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", raw)
    # Pin the root <svg> to the fitted source box while preserving its own viewBox.
    raw = re.sub(
        r"<svg\b",
        f'<svg style="position:absolute;top:0;left:0;width:{width:.6f}px;height:{height:.6f}px" '
        'preserveAspectRatio="xMidYMid meet"',
        raw, count=1)
    return raw


def slot_markup(slot: dict, source_w: float, source_h: float, box: dict[str, float],
                style_override: dict | None = None) -> str:
    b = slot["bounds"]
    t = slot["typography"]
    style_override = style_override or {}
    tag = slot.get("html_tag", "span")
    left = box["left"] + float(b["x"]) * source_w * box["scale_x"]
    top = box["top"] + float(b["y"]) * source_h * box["scale_y"]
    width = float(b["width"]) * source_w * box["scale_x"]
    height = float(b["height"]) * source_h * box["scale_y"]
    font_family = html.escape(str(t.get("font_family") or "Proxima Nova"))
    font_size = (
        float(t["font_size"]) * box["scale_y"]
        * float(style_override.get("font_scale", 1.0))
    )
    style = (
        "position:absolute;margin:0;padding:0;white-space:pre;overflow:visible;"
        "transform-origin:top left;"
        f"left:{left:.6f}px;"
        f"top:{top:.6f}px;"
        f"min-width:{width:.6f}px;"
        f"min-height:{height:.6f}px;"
        f"font-family:'{font_family}',Arial,sans-serif;"
        f"font-size:{font_size:.6f}px;"
        f"font-weight:{css_weight(t.get('font_weight', 400))};"
        f"font-style:{html.escape(str(t.get('font_style', 'normal')))};"
        f"line-height:{t.get('line_height', 1)};"
        f"letter-spacing:{html.escape(str(t.get('letter_spacing', 'normal')))};"
        f"color:{html.escape(str(style_override.get('color', t.get('color', '#171717'))))};"
        f"background:{html.escape(str(style_override.get('background', 'transparent')))};"
        f"box-shadow:0 0 0 {float(style_override.get('mask_bleed', 0)):.2f}px "
        f"{html.escape(str(style_override.get('background', 'transparent')))};"
        f"text-align:{html.escape(str(slot.get('horizontal_align', 'left')))};"
        f"transform:rotate({slot.get('rotation', 0)}deg);"
        f"z-index:{slot.get('z_order', 1)};"
    )
    return (f'<{tag} class="text-slot" data-slot-id="{html.escape(slot["id"])}" '
            f'style="{style}">{html.escape(slot["example_value"])}</{tag}>')


def decomposed_artwork_markup(page: str, assets_dir: Path, output: Path,
                              box: dict[str, float]) -> str:
    page_dir = assets_dir / page
    manifest_path = page_dir / "decompose-manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing decomposition manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    href_base = Path(os.path.relpath(page_dir.resolve(), output.parent.resolve())).as_posix()

    layers: list[str] = []
    for base in manifest.get("base_candidates", []):
        left, top, width, height = fit_bounds(base["bounds"], box)
        asset = page_dir / base["file"]
        href = f"{href_base}/{base['file']}"
        render_href = f"{href}?v={hashlib.sha256(asset.read_bytes()).hexdigest()[:12]}"
        layers.append(
            '<div class="base-artwork" '
            f'style="left:{left:.6f}px;top:{top:.6f}px;'
            f'width:{width:.6f}px;height:{height:.6f}px;'
            f'background-image:url(\'{html.escape(render_href)}\')"></div>')

    for z, obj in enumerate(manifest.get("objects", []), start=1):
        left, top, width, height = fit_bounds(obj["bounds"], box)
        asset = page_dir / obj["file"]
        href = f"{href_base}/{obj['file']}"
        render_href = f"{href}?v={hashlib.sha256(asset.read_bytes()).hexdigest()[:12]}"
        layers.append(
            f'<div class="artwork-object" data-export-layer="overlay" '
            f'data-export-id="{html.escape(obj["id"])}" '
            f'data-export-vector-source="{html.escape(href)}" '
            f'style="left:{left:.6f}px;top:{top:.6f}px;'
            f'width:{width:.6f}px;height:{height:.6f}px;z-index:{z}">'
            f'<img src="{html.escape(render_href)}" alt=""></div>')
    return "".join(layers)


def build(extraction_dir: Path, font_css: str, output: Path,
          tag_artwork: bool, decomposed_assets_dir: Path | None,
          fit_mode: str, canvas_mode: str, text_style_overrides: dict) -> int:
    items = sorted(extraction_dir.glob("items/*/"),
                   key=lambda p: p.name)
    source_sizes = []
    for item_dir in items:
        svg_path = item_dir / "artifact" / "visual.svg"
        slots_path = item_dir / "artifact" / "text-slots.json"
        if svg_path.exists() and slots_path.exists():
            source_sizes.append(source_size(
                json.loads(slots_path.read_text(encoding="utf-8")), svg_path
            ))
    if not source_sizes:
        raise SystemExit(f"No extractable items found under {extraction_dir}")
    stage_w, stage_h = (
        source_sizes[0] if canvas_mode == "source" else (STAGE_W, STAGE_H)
    )
    if canvas_mode == "source" and any(
        abs(w / h - stage_w / stage_h) > 1e-6 for w, h in source_sizes
    ):
        raise SystemExit("Source canvas mode requires one aspect ratio across all pages")

    slides_html = []
    for idx, item_dir in enumerate(items):
        svg_path = item_dir / "artifact" / "visual.svg"
        slots_path = item_dir / "artifact" / "text-slots.json"
        if not (svg_path.exists() and slots_path.exists()):
            continue
        contract = json.loads(slots_path.read_text(encoding="utf-8"))
        source_w, source_h = source_size(contract, svg_path)
        box = layout_box(source_w, source_h, fit_mode, stage_w, stage_h)
        slots = "".join(
            slot_markup(
                s, source_w, source_h, box,
                text_style_overrides.get("slots", {}).get(
                    s["id"], text_style_overrides.get("default", {})
                ),
            )
            for s in contract["slots"]
        )
        active = " active" if idx == 0 else ""
        page = item_dir.name
        if decomposed_assets_dir:
            bg = decomposed_artwork_markup(page, decomposed_assets_dir, output, box)
        elif tag_artwork:
            # 3-layer: passive canvas (slide bg) + the whole page artwork as ONE
            # tagged complex-overlay carrying its own vector_source so build embeds
            # it as a movable svgBlip picture — never baked into the base PNG. The
            # source SVG is a flat primitive soup (no semantic object boundaries),
            # so the faithful unit is the page artwork at one z behind the text.
            vector_rel = os.path.relpath(svg_path.resolve(), output.parent)
            bg = (f'<div class="artwork" data-export-layer="overlay" '
                  f'data-export-id="artwork-{page}" '
                  f'data-export-vector-source="{html.escape(vector_rel)}" '
                  f'style="left:{box["left"]:.6f}px;top:{box["top"]:.6f}px;'
                  f'width:{box["width"]:.6f}px;height:{box["height"]:.6f}px">'
                  f'{inline_svg(svg_path, box["width"], box["height"])}'
                  '</div>')
        else:
            bg = (f'<div class="bg" '
                  f'style="left:{box["left"]:.6f}px;top:{box["top"]:.6f}px;'
                  f'width:{box["width"]:.6f}px;height:{box["height"]:.6f}px">'
                  f'{inline_svg(svg_path, box["width"], box["height"])}'
                  '</div>')
        slides_html.append(
            f'<div class="slide{active}" data-page="{page}">'
            f'{bg}'
            f'<div class="text-layer">{slots}</div></div>')

    doc = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="{html.escape(font_css)}">
<style>
  html,body{{margin:0;padding:0;background:#ffffff}}
  .slide{{position:absolute;top:0;left:0;width:{stage_w:.6f}px;height:{stage_h:.6f}px;
          display:none;overflow:hidden;background:#ffffff}}
  .slide.active{{display:block}}
  .bg{{position:absolute}}
  .artwork{{position:absolute}}
  .base-artwork{{position:absolute;background-repeat:no-repeat;
                 background-size:100% 100%;pointer-events:none}}
  .artwork-object{{position:absolute}}
  .artwork-object img{{display:block;width:100%;height:100%}}
  .text-layer{{position:absolute;inset:0;width:{stage_w:.6f}px;height:{stage_h:.6f}px;z-index:1000}}
  .text-slot{{position:absolute}}
</style>
</head>
<body>
{''.join(slides_html)}
<script>
  function goToSlide(n){{
    var s=document.querySelectorAll('.slide');
    s.forEach(function(el,i){{el.classList.toggle('active', i===n);}});
  }}
  goToSlide(0);
</script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(doc, encoding="utf-8")
    print(f"Deck: {len(slides_html)} slides -> {output}")
    return len(slides_html)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--extraction-dir", required=True, type=Path)
    p.add_argument("--font-css", required=True,
                   help="href to the brand Proxima Nova @font-face stylesheet")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--tag-artwork", action="store_true",
                   help="Wrap each page artwork in a tagged data-export overlay "
                        "(3-layer export) instead of an untagged background block")
    p.add_argument("--decomposed-assets-dir", type=Path,
                   help="Directory containing page-NN/decompose-manifest.json "
                        "and fragment SVGs. Preferred for layered export.")
    p.add_argument("--fit-mode", choices=("contain", "stretch"), default="contain",
                   help="How to place a non-16:9 source page inside the 1920x1080 slide")
    p.add_argument("--canvas-mode", choices=("widescreen", "source"),
                   default="widescreen",
                   help="Use the default 1920x1080 canvas or preserve source dimensions")
    p.add_argument("--text-style-overrides", type=Path,
                   help="Optional JSON with default and per-slot color/background overrides")
    a = p.parse_args()
    assets = a.decomposed_assets_dir.resolve() if a.decomposed_assets_dir else None
    overrides = (
        json.loads(a.text_style_overrides.read_text(encoding="utf-8"))
        if a.text_style_overrides else {}
    )
    build(a.extraction_dir.resolve(), a.font_css, a.output.resolve(),
          a.tag_artwork, assets, a.fit_mode, a.canvas_mode, overrides)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
