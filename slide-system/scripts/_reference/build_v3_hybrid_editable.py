from __future__ import annotations

import sys
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
RUN = ROOT / "outputs/slide-jobs/unity-roadmap-intern-3-months/runs/2026-06-08-v3"
DEPS = ROOT / "outputs/phase-01-slides-01-10/ppt-master/.python-deps"
sys.path.insert(0, str(DEPS))

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN

SLIDE_W = Inches(13.333333)
SLIDE_H = Inches(7.5)
RENDERS = RUN / "qa/export-renders"
LAYOUT = RUN / "qa/export-layout.json"
PPTX_OUT = RUN / "pptx/unity-roadmap-intern-3-months-v3-editable-hybrid.pptx"
PDF_OUT = RUN / "pdf/unity-roadmap-intern-3-months-v3.pdf"

LAYOUT_W = 804.0
LAYOUT_H = 452.25
PX_PER_IN = 144.0


def set_run_transparent(run) -> None:
    r_pr = run._r.get_or_add_rPr()
    solid_fill = OxmlElement("a:solidFill")
    srgb = OxmlElement("a:srgbClr")
    srgb.set("val", "FFFFFF")
    alpha = OxmlElement("a:alpha")
    alpha.set("val", "0")
    srgb.append(alpha)
    solid_fill.append(srgb)
    r_pr.append(solid_fill)


def parse_css_color(value: str) -> RGBColor:
    nums = [float(n) for n in re.findall(r"[\d.]+", value)]
    if len(nums) < 3:
        return RGBColor(248, 250, 252)
    red, green, blue = [max(0, min(255, round(n))) for n in nums[:3]]
    return RGBColor(red, green, blue)


def px_box(item: dict) -> tuple[float, float, float, float]:
    scale_x = 1920.0 / LAYOUT_W
    scale_y = 1080.0 / LAYOUT_H
    x = item["x"] * scale_x / PX_PER_IN
    y = item["y"] * scale_y / PX_PER_IN
    w = max(item["w"] * scale_x / PX_PER_IN, 0.08)
    h = max(item["h"] * scale_y / PX_PER_IN, 0.08)
    return x, y, w, h


def font_pt(item: dict) -> float:
    css_px = float(str(item.get("fontSize", "18px")).replace("px", ""))
    return max(4.0, css_px * 0.5)


def should_skip(item: dict) -> bool:
    text = item["text"]
    cls = item.get("cls", "")
    if cls == "hero-title" and text == "UNITY ROADMAP":
        return True
    return False


def add_native_text(slide, item: dict) -> None:
    if should_skip(item):
        return
    x, y, w, h = px_box(item)
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(max(h * 1.35, 0.14)))
    box.name = "Editable: " + item["text"][:32]
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = Inches(0)
    tf.margin_right = Inches(0)
    tf.margin_top = Inches(0)
    tf.margin_bottom = Inches(0)
    paragraph = tf.paragraphs[0]
    align = item.get("align", "start")
    paragraph.alignment = PP_ALIGN.CENTER if align == "center" else PP_ALIGN.LEFT
    run = paragraph.add_run()
    run.text = item["text"]
    run.font.name = "Proxima Nova"
    run.font.size = Pt(font_pt(item))
    run.font.bold = int(item.get("fontWeight", "400")) >= 700
    run.font.color.rgb = parse_css_color(item.get("color", "rgb(248,250,252)"))


def build_pptx() -> None:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]
    prs.core_properties.title = "Unity Roadmap Intern 3 Months v3"
    prs.core_properties.subject = "Editable hybrid export from HTML deck"
    prs.core_properties.author = "SUN.STUDIO"
    prs.core_properties.comments = "Visuals are HTML render backgrounds; slide text is preserved as transparent native PowerPoint text overlays."

    for slide_index in range(1, 9):
        render = RENDERS / f"slide-{slide_index:02d}-bg.png"
        if not render.exists():
            raise FileNotFoundError(render)
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(render), 0, 0, width=SLIDE_W, height=SLIDE_H)
        layout = json.loads(LAYOUT.read_text())
        for item in layout[slide_index - 1]["items"]:
            add_native_text(slide, item)

    PPTX_OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(PPTX_OUT)


def build_pdf() -> None:
    images = []
    for slide_index in range(1, 9):
        render = RENDERS / f"slide-{slide_index:02d}.png"
        image = Image.open(render).convert("RGB")
        images.append(image)
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(PDF_OUT, save_all=True, append_images=images[1:], resolution=144.0)


def audit_pptx_text() -> dict[str, int]:
    layout = json.loads(LAYOUT.read_text())
    expected = sum(1 for slide in layout for item in slide["items"] if not should_skip(item))
    with zipfile.ZipFile(PPTX_OUT) as archive:
        slide_xml = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        text_hits = 0
        for name in slide_xml:
            xml = archive.read(name).decode("utf-8", errors="ignore")
            text_hits += xml.count("<a:t>")
    return {"slides": len(slide_xml), "expected_text_runs": expected, "pptx_text_runs": text_hits}


if __name__ == "__main__":
    build_pptx()
    build_pdf()
    print({
        "pptx": str(PPTX_OUT.relative_to(ROOT)),
        "pdf": str(PDF_OUT.relative_to(ROOT)),
        **audit_pptx_text(),
    })