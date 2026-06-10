#!/usr/bin/env python3
"""Build an editable hybrid PPTX from slide renders + DOM text layout.

This is the generalised version of the per-job build scripts (e.g.
build_v3_hybrid_editable.py). It works the same way:

  1. Each slide render (slide-01-bg.png …) becomes a full-slide background image.
  2. Every text item in export-layout.json is re-created as a native PowerPoint
     text box — so slide copy stays editable in PowerPoint / Keynote.

The result is a "hybrid editable" PPTX: visually identical to the HTML deck,
with native editable text. Complex styled text (gradient fills, custom SVG
glyphs, blend-mode effects) may look slightly different when edited because
PowerPoint cannot replicate all CSS effects — that is expected and documented.

This script needs only standard pip packages (no Claude Code required):
    pip install python-pptx Pillow

Usage:
    python3 build_hybrid_pptx.py \\
        --layout   qa/export-layout.json \\
        --renders  qa/export-renders/ \\
        --slides   8 \\
        --output   exports/deck-editable.pptx

Options:
    --layout      Path to export-layout.json produced by capture-slides.js
    --renders     Directory containing slide-01-bg.png, slide-02-bg.png …
    --slides      Total slide count
    --output      Output .pptx path
    --layout-w    Pixel width used when the layout was captured (default: 1920)
    --layout-h    Pixel height used when the layout was captured (default: 1080)
    --font        Font name to embed in text boxes (default: Proxima Nova)
    --fallback-font  Font name used when --font is unavailable on the viewer's
                  machine (default: Arial). PowerPoint substitutes this
                  automatically if Proxima Nova is not installed.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN
except ImportError:
    raise SystemExit(
        "python-pptx not found. Run:  pip install python-pptx\n"
        "(Also install Pillow if not present: pip install Pillow)"
    )

SLIDE_W = Inches(13.333333)  # 16:9 widescreen
SLIDE_H = Inches(7.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--layout",       required=True, help="Path to export-layout.json")
    p.add_argument("--renders",      required=True, help="Directory with slide-XX-bg.png files")
    p.add_argument("--slides",       required=True, type=int, help="Number of slides")
    p.add_argument("--output",       required=True, help="Output .pptx path")
    p.add_argument("--layout-w",     type=float, default=1920.0,
                   help="Pixel width of the layout coordinate space (default: 1920)")
    p.add_argument("--layout-h",     type=float, default=1080.0,
                   help="Pixel height of the layout coordinate space (default: 1080)")
    p.add_argument("--font",         default="Proxima Nova",
                   help="Primary font name for text boxes (default: Proxima Nova)")
    p.add_argument("--fallback-font", default="Arial",
                   help="Fallback font if primary is unavailable (default: Arial)")
    return p.parse_args()


def parse_css_color(value: str) -> RGBColor:
    """Convert css rgb(...) / rgba(...) / #rrggbb to RGBColor."""
    if value.startswith("#"):
        hex_val = value.lstrip("#")
        if len(hex_val) == 3:
            hex_val = "".join(c * 2 for c in hex_val)
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        return RGBColor(r, g, b)
    nums = [float(n) for n in re.findall(r"[\d.]+", value)]
    if len(nums) < 3:
        return RGBColor(248, 250, 252)
    r, g, b = [max(0, min(255, round(n))) for n in nums[:3]]
    return RGBColor(r, g, b)


def px_to_inches(px_val: float, layout_px: float, slide_inches: float) -> float:
    """Convert layout-space pixels to slide inches."""
    return (px_val / layout_px) * float(slide_inches / Inches(1))


def font_pt(item: dict, layout_w: float) -> float:
    """Convert CSS fontSize (px) to points for the slide.

    VERIFIED against the proven Phase 1 build (build_v3_hybrid_editable.py):
    a 1920px-wide canvas maps to a 13.333in (=960pt) slide, so the exact
    px->pt factor is 960/1920 = 0.5 — NOT the generic 96dpi 0.75.

    fontSize in export-layout.json is the UNSCALED computed CSS px (e.g. 102px),
    captured with `noscale` set so it is already in the authored design-px
    space. The factor below is design_pt_width / design_px_width.
    """
    css_px = float(str(item.get("fontSize", "18px")).replace("px", "").strip())
    SLIDE_W_PT = 13.333333 * 72.0  # 960pt
    factor = SLIDE_W_PT / layout_w  # = 0.5 when layout_w == 1920
    return max(4.0, round(css_px * factor, 1))


def box_inches(item: dict, layout_w: float, layout_h: float) -> tuple[float, float, float, float]:
    """Return (left, top, width, height) in inches for the slide."""
    slide_w_in = 13.333333
    slide_h_in = 7.5
    x = item["x"] / layout_w * slide_w_in
    y = item["y"] / layout_h * slide_h_in
    w = max(item["w"] / layout_w * slide_w_in, 0.08)
    h = max(item["h"] / layout_h * slide_h_in * 1.35, 0.14)  # 35% taller for wrapping
    return x, y, w, h


def add_text_box(slide, item: dict, font_name: str, layout_w: float, layout_h: float) -> None:
    x, y, w, h = box_inches(item, layout_w, layout_h)
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    box.name = f"Editable: {item['text'][:40]}"

    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = Inches(0)
    tf.margin_right = Inches(0)
    tf.margin_top = Inches(0)
    tf.margin_bottom = Inches(0)

    para = tf.paragraphs[0]
    align = item.get("align", "start")
    para.alignment = PP_ALIGN.CENTER if align == "center" else (
        PP_ALIGN.RIGHT if align == "right" else PP_ALIGN.LEFT
    )

    run = para.add_run()
    run.text = item["text"]
    run.font.name = font_name
    run.font.size = Pt(font_pt(item, layout_w))
    run.font.bold = int(str(item.get("fontWeight", "400")).replace("bold", "700").replace("normal", "400")) >= 700
    run.font.color.rgb = parse_css_color(item.get("color", "rgb(248,250,252)"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(args: argparse.Namespace) -> None:
    layout_path = Path(args.layout)
    renders_dir = Path(args.renders)
    output_path = Path(args.output)

    if not layout_path.exists():
        raise FileNotFoundError(f"Layout file not found: {layout_path}")
    if not renders_dir.is_dir():
        raise FileNotFoundError(f"Renders directory not found: {renders_dir}")

    layout: list[dict] = json.loads(layout_path.read_text(encoding="utf-8"))

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]  # blank

    print(f"[build_hybrid_pptx] Building {args.slides} slides → {output_path}")

    text_count = 0
    for slide_index in range(1, args.slides + 1):
        render_path = renders_dir / f"slide-{slide_index:02d}-bg.png"
        if not render_path.exists():
            raise FileNotFoundError(f"Render not found: {render_path}")

        slide = prs.slides.add_slide(blank_layout)
        # Full-slide background image
        slide.shapes.add_picture(str(render_path), 0, 0,
                                  width=SLIDE_W, height=SLIDE_H)

        # Native text boxes.
        #
        # This script consumes export-layout.json produced by capture-slides.js,
        # which captures with deck-stage `noscale` set. In that mode BOTH the box
        # coordinates AND the unscaled CSS fontSize live in the same authored
        # design space (canvasW x canvasH, normally 1920x1080), so a single
        # canvas dimension scales both correctly:
        #   box:  x / canvasW * 13.333in           font: css_px * 960 / canvasW
        # (For canvasW = 1920 the font factor is 960/1920 = 0.5, matching the
        #  proven Phase 1 build.)
        #
        # NOTE: this does NOT correctly process the legacy Phase-1
        # export-layout.json, whose coordinates were captured in 804x452.25
        # space while its fonts stayed in 1920 space (a split the old per-job
        # build patched by hand). Always regenerate layout via capture-slides.js.
        slide_data = next((s for s in layout if s.get("slide") == slide_index), None)
        if slide_data:
            cw = float(slide_data.get("canvasW") or args.layout_w)
            ch = float(slide_data.get("canvasH") or args.layout_h)
            if not slide_data.get("canvasW"):
                print(f"  WARNING slide {slide_index:02d}: layout has no canvasW; "
                      f"using --layout-w {args.layout_w}. Font sizes may be wrong "
                      f"if this is not freshly captured data.")
            for item in slide_data.get("items", []):
                if not item.get("text", "").strip():
                    continue
                add_text_box(slide, item, args.font, cw, ch)
                text_count += 1

        print(f"  slide {slide_index:02d} ✓")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))

    # Quick audit
    with zipfile.ZipFile(output_path) as zf:
        slide_xmls = [n for n in zf.namelist()
                      if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        pptx_runs = sum(
            zf.read(n).decode("utf-8", errors="ignore").count("<a:t>")
            for n in slide_xmls
        )

    print(f"\n[build_hybrid_pptx] Done")
    print(f"  output       → {output_path}")
    print(f"  slides       → {len(slide_xmls)}")
    print(f"  text boxes   → {text_count} layout items")
    print(f"  pptx <a:t>   → {pptx_runs} text runs")
    print(f"\nNOTE: Visual backgrounds are PNG images. Slide text is natively")
    print(f"      editable. Complex CSS effects (gradients, blends) in the")
    print(f"      background will not change when text is edited — that is expected.")


if __name__ == "__main__":
    build(parse_args())
