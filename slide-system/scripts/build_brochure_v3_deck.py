#!/usr/bin/env python3
"""Build the one-page Blues brochure as semantic layered HTML for PPTX export."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

import fitz
from PIL import Image

from build_clone_deck import css_weight


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PDF = ROOT / "input/tutu_optimized.pdf"
FONT_CSS = (
    ROOT
    / ".agents/skills/sun-studio-design-system/assets/system/colors_and_type.css"
)
CANVAS_W = 842.88
CANVAS_H = 1272.48
NAVY = "#244a86"
INK = "#17467f"
LIGHT_BLUE = "#b9ddfa"
MID_BLUE = "#2f7bc4"


NATIVE_SHAPES = [
    ("service-panel", "rect", 280.0, 0.0, 282.0, 407.0, NAVY, NAVY, 0, 0),
    ("card-1-shadow", "rect", 29.0, 116.0, 105.0, 101.0, MID_BLUE, MID_BLUE, 0, 0),
    ("card-1", "rect", 25.0, 112.0, 105.0, 101.0, LIGHT_BLUE, LIGHT_BLUE, 0, 0),
    ("card-2-shadow", "rect", 146.0, 116.0, 105.0, 101.0, MID_BLUE, MID_BLUE, 0, 0),
    ("card-2", "rect", 142.0, 112.0, 105.0, 101.0, LIGHT_BLUE, LIGHT_BLUE, 0, 0),
    ("card-3-shadow", "rect", 29.0, 242.0, 105.0, 101.0, MID_BLUE, MID_BLUE, 0, 0),
    ("card-3", "rect", 25.0, 238.0, 105.0, 101.0, LIGHT_BLUE, LIGHT_BLUE, 0, 0),
    ("card-4-shadow", "rect", 146.0, 242.0, 105.0, 101.0, MID_BLUE, MID_BLUE, 0, 0),
    ("card-4", "rect", 142.0, 238.0, 105.0, 101.0, LIGHT_BLUE, LIGHT_BLUE, 0, 0),
    ("number-1-circle", "ellipse", 58.0, 96.0, 40.0, 40.0, "#ffffff", MID_BLUE, 1.5, 20),
    ("number-2-circle", "ellipse", 175.0, 96.0, 40.0, 40.0, "#ffffff", MID_BLUE, 1.5, 20),
    ("number-3-circle", "ellipse", 58.0, 222.0, 40.0, 40.0, "#ffffff", MID_BLUE, 1.5, 20),
    ("number-4-circle", "ellipse", 175.0, 222.0, 40.0, 40.0, "#ffffff", MID_BLUE, 1.5, 20),
    ("why-heading-line", "rect", 45.0, 86.0, 180.0, 1.5, MID_BLUE, MID_BLUE, 0, 0),
    ("services-heading-line", "rect", 332.0, 86.0, 179.0, 1.5, "#ffffff", "#ffffff", 0, 0),
    ("about-heading-line", "rect", 635.0, 84.0, 134.0, 1.2, NAVY, NAVY, 0, 0),
    ("service-divider-1", "rect", 363.0, 154.0, 170.0, 1.0, "#ffffff", "#ffffff", 0, 0),
    ("service-divider-2", "rect", 363.0, 232.0, 170.0, 1.0, "#ffffff", "#ffffff", 0, 0),
    ("service-divider-3", "rect", 363.0, 308.0, 170.0, 1.0, "#ffffff", "#ffffff", 0, 0),
    ("contact-heading-line", "rect", 43.0, 766.0, 190.0, 1.4, NAVY, NAVY, 0, 0),
    ("contact-separator", "rect", 17.0, 902.0, 244.0, 1.2, NAVY, NAVY, 0, 0),
    ("website-separator", "rect", 17.0, 1008.0, 244.0, 1.2, NAVY, NAVY, 0, 0),
    ("address-heading-line", "rect", 18.0, 1010.0, 244.0, 1.2, NAVY, NAVY, 0, 0),
    ("top-left-ring-1", "ellipse", -37.0, -43.0, 166.0, 90.0, "transparent", "#b9ddfa", 0.6, 45),
    ("top-left-ring-2", "ellipse", -25.0, -31.0, 141.0, 66.0, "transparent", "#b9ddfa", 0.6, 33),
]


CROPS = [
    ("top-dot-grid", 195, 17, 58, 42),
    ("top-chevron-row", 758, 20, 73, 34),
    ("service-package-icon", 306, 99, 46, 51),
    ("service-gear-icon", 306, 174, 46, 51),
    ("service-prototype-icon", 306, 249, 46, 56),
    ("service-globe-icon", 307, 327, 44, 46),
    ("certification-logos", 575, 365, 255, 58),
    ("trusted-brand-logos", 27, 468, 231, 99),
    ("factory-photo", 280, 407, 282, 193),
    ("sewing-photo", 562, 427, 281, 173),
    ("contact-phone-1", 35, 800, 18, 18),
    ("contact-mail-1", 35, 817, 18, 18),
    ("contact-phone-2", 35, 860, 18, 18),
    ("contact-mail-2", 35, 877, 18, 18),
    ("website-qr", 160, 910, 100, 105),
    ("address-pin-1", 25, 1062, 25, 34),
    ("address-pin-2", 25, 1122, 25, 34),
    ("address-pin-3", 25, 1184, 25, 34),
    ("denim-photo", 280, 675, 282, 597),
    ("factory-building-photo", 562, 675, 281, 356),
    ("bottom-chevron-row", 575, 1161, 72, 34),
    ("bottom-left-ribbon", 0, 675, 176, 39),
    ("bottom-right-corner", 666, 1230, 177, 42),
]

SERVICE_TEXT_IDS = {
    "our-services",
    "products-denim-woven-and-knitwears",
    "specialize-in-denim-jean-and-garment-dye",
    "end-to-end-production-sourcing",
    "fabric-trims-sewing-washing-finishing",
    "delivering-advanced-and-complex",
    "denim-finishes",
    "rapid-prototyping-turn-concepts-into",
    "samples-quickly-ensuring-your-vision-is",
    "realized-efficiently",
    "logistic-deliver-to-buyer-s-warehouse-in",
    "us-europe-asia-with-the-shortest",
    "delivery-time",
}

TEXT_X_OVERRIDES = {
    "anh-do-theblues-vn": 59.7,
    "nhungha-theblues-vn": 59.7,
}


def render_source() -> Image.Image:
    doc = fitz.open(SOURCE_PDF)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def create_crop_assets(assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    source = render_source()
    sx = source.width / CANVAS_W
    sy = source.height / CANVAS_H
    for crop_id, x, y, w, h in CROPS:
        target = assets_dir / f"{crop_id}.png"
        box = (
            round(x * sx),
            round(y * sy),
            round((x + w) * sx),
            round((y + h) * sy),
        )
        source.crop(box).save(target)


def native_markup() -> str:
    parts = []
    for z, (shape_id, shape, x, y, w, h, fill, border, border_w, radius) in enumerate(
        NATIVE_SHAPES, start=10
    ):
        parts.append(
            f'<div data-export-native="{shape}" data-export-id="{shape_id}" '
            f'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:{fill};border:{border_w}px solid {border};'
            f'border-radius:{radius}px;box-sizing:border-box;z-index:{z}"></div>'
        )
    return "".join(parts)


def overlay_markup(assets_dir: Path, output: Path) -> str:
    href_base = Path(os.path.relpath(assets_dir.resolve(), output.parent.resolve())).as_posix()
    parts = []
    for z, (crop_id, x, y, w, h) in enumerate(CROPS, start=100):
        parts.append(
            f'<div data-export-layer="overlay" data-export-id="{crop_id}" '
            f'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'z-index:{z}"><img src="{href_base}/{crop_id}.png" alt="" '
            'style="display:block;width:100%;height:100%"></div>'
        )
    return "".join(parts)


def slot_markup(slot: dict) -> str:
    bounds = slot["bounds"]
    typography = slot["typography"]
    x = bounds["x"] * CANVAS_W
    y = bounds["y"] * CANVAS_H
    w = bounds["width"] * CANVAS_W
    h = bounds["height"] * CANVAS_H
    x = TEXT_X_OVERRIDES.get(slot["id"], x)
    size = float(typography["font_size"])
    if slot["id"] in {
        "more-than-a", "manufacturer-we", "deliver", "full-package",
        "garment-solutions", "strong-in-house", "washing", "expertise-for",
        "diverse-denim", "e-ects", "short-lead-time", "30-45-days",
        "flexible-moqs", "payment-terms", "focus-on-building", "long-term",
        "partnerships",
    }:
        size *= 0.72
    color = "#ffffff" if slot["id"] in SERVICE_TEXT_IDS else INK
    tag = slot.get("html_tag", "span")
    style = (
        f"position:absolute;left:{x:.6f}px;top:{y:.6f}px;"
        f"min-width:{w:.6f}px;min-height:{h:.6f}px;margin:0;padding:0;"
        "white-space:pre;overflow:visible;background:transparent;"
        f"font-family:'{html.escape(str(typography.get('font_family', 'Arial')))}',Arial,sans-serif;"
        f"font-size:{size:.6f}px;font-weight:{css_weight(typography.get('font_weight', 400))};"
        f"font-style:{html.escape(str(typography.get('font_style', 'normal')))};"
        f"line-height:{typography.get('line_height', 1)};"
        f"color:{color};"
        f"text-align:{html.escape(str(slot.get('horizontal_align', 'left')))};"
        "transform-origin:top left;"
        f"transform:rotate({slot.get('rotation', 0)}deg);z-index:1000"
    )
    return (
        f'<{tag} class="text-slot" data-slot-id="{html.escape(slot["id"])}" '
        f'style="{style}">{html.escape(slot["example_value"])}</{tag}>'
    )


def build_html(slots_path: Path, assets_dir: Path, output: Path) -> str:
    contract = json.loads(slots_path.read_text(encoding="utf-8"))
    create_crop_assets(assets_dir)
    font_href = Path(os.path.relpath(FONT_CSS.resolve(), output.parent.resolve())).as_posix()
    text = "".join(slot_markup(slot) for slot in contract["slots"])
    doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="{font_href}">
<style>
html,body{{margin:0;padding:0;background:#fff}}
.slide{{position:absolute;left:0;top:0;width:{CANVAS_W}px;height:{CANVAS_H}px;
overflow:hidden;background:#fff;display:none}}
.slide.active{{display:block}}
</style></head><body>
<div class="slide active">
{native_markup()}
{overlay_markup(assets_dir, output)}
{text}
</div>
<script>
function goToSlide(n){{document.querySelector('.slide').classList.toggle('active',n===0)}}
goToSlide(0);
</script></body></html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(doc, encoding="utf-8")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slots", required=True, type=Path)
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build_html(args.slots.resolve(), args.assets_dir.resolve(), args.output.resolve())
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
