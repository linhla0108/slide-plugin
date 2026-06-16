#!/usr/bin/env python3
"""generate_template_preview.py — Render an extracted FULL-SLIDE template into a
faithful full-slide preview, plus an editable composite.

A "template" in this library is a FULL SLIDE (full-bleed 1920x1080), not an
atomic section/component/card/icon. The picker must therefore show the whole
slide AS THE ORIGINAL, not a reconstruction that might drift from the source.

Why this exists (TEMPLATE-PICKER-PLAN.md, Phase 1A): each extracted item carries
both the original slide and its editable decomposition:
  - evidence/source-with-text.svg  the ORIGINAL full slide, 1920x1080, with text
                                   baked in and images referenced via
                                   ../artifact/assets/... (resolves on disk).
  - artifact/visual.svg            the passive (text-free) artwork.
  - artifact/text-slots.json       the editable text, positioned in normalized
                                   0..1 bounds with typography + alignment.

This script produces, per item, in preview/:
  preview/thumbnail.png  THE picker image — the original full slide rendered
                         straight from its source PDF page (via PyMuPDF), which
                         avoids the text duplication some evidence SVGs cause by
                         overlaying vector text on a text-baked background raster.
                         Falls back to the evidence-SVG render, then the
                         composite, when the PDF is unavailable.
  preview/preview.html   a self-contained, offline-openable 1920x1080 stage —
                         visual.svg inlined as the background (external rasters
                         base64-embedded) with every text slot positioned from
                         its normalized bounds and example_value. This is the
                         EDITABLE layer used by the template-based build step.

Usage:
    generate_template_preview.py --item-dir <item> [--width 1920] [--height 1080]
    generate_template_preview.py --batch <extraction-dir> [--width ...] [--height ...]
    # --html-only  : write preview.html only; skip the thumbnail.
    # --from {original,composite} : thumbnail source (default: original).

A single item dir contains artifact/visual.svg + artifact/text-slots.json (e.g.
outputs/component-extractions/<batch>/items/<id>); the original render also needs
evidence/source-with-text.svg. --batch processes every items/* subfolder.

Exit codes:
    0  success (or --html-only: preview.html written, thumbnail skipped).
    1  a thumbnail was required (not --html-only) but failed — preview.html is
       still written; the failure is reported clearly.
    2  operational error (bad input dir, unreadable artifacts).
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from _common import SCRIPT_DIR, REPO_ROOT, load_json, now_iso

CAPTURE_JS = SCRIPT_DIR / "capture-slides.js"
RENDER_JS = SCRIPT_DIR / "render_svg.js"

SVG_NS = "http://www.w3.org/2000/svg"
INK_NS = "http://www.inkscape.org/namespaces/inkscape"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INK_NS)
ET.register_namespace("xlink", XLINK_NS)

# Alignment maps: text-slots horizontal/vertical_align -> CSS flexbox.
_H_JUSTIFY = {"left": "flex-start", "center": "center", "right": "flex-end"}
_V_ALIGN = {"top": "flex-start", "middle": "center", "bottom": "flex-end"}


# --------------------------------------------------------------------------- #
# SVG background
# --------------------------------------------------------------------------- #
def _embed_external_images(root: ET.Element, source_dir: Path) -> int:
    """Inline every external <image> as a base64 data URI so the preview is
    self-contained for file:// and headless capture.

    Mirrors decompose_svg_objects.embed_external_images: a browser will NOT load
    an external href that lives inside an SVG referenced via <img>, and an
    inlined SVG's relative href would resolve against preview/ (wrong dir). Both
    failure modes are avoided by baking the bytes in.
    """
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


def _build_background(svg_path: Path) -> tuple[str, list[str]]:
    """Return (inline-svg-markup, warnings) for the stage background.

    Primary path: parse the SVG, base64-embed external rasters, re-serialize as
    inline markup sized to fill the stage. Fallback (unparseable / raster stub):
    base64 the whole file into an <img> so the preview still renders something.
    """
    warnings: list[str] = []
    raw = svg_path.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        warnings.append(
            f"visual.svg is not parseable XML ({error}); embedding it as a flat "
            f"<img> — any external references inside it will not render"
        )
        encoded = base64.b64encode(svg_path.read_bytes()).decode("ascii")
        return (
            f'<img class="bg" alt="" '
            f'src="data:image/svg+xml;base64,{encoded}">',
            warnings,
        )

    embedded = _embed_external_images(root, svg_path.parent)
    if embedded:
        warnings.append(f"embedded {embedded} external image(s) as base64")
    # Fill the stage: drop any pixel width/height so the viewBox drives scaling.
    root.set("preserveAspectRatio", "xMidYMid meet")
    existing_class = root.get("class", "")
    root.set("class", (existing_class + " bg").strip())
    markup = ET.tostring(root, encoding="unicode")
    return markup, warnings


# --------------------------------------------------------------------------- #
# Text slots
# --------------------------------------------------------------------------- #
def _parse_font_px(value: Any) -> float | None:
    """Normalize a font_size to px. Extraction batches differ: some store a bare
    number (already px), others a unit string like "18pt" or "24px". Returns None
    for empty/unparseable input so the slot simply inherits the default size.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    try:
        if text.endswith("pt"):
            return float(text[:-2]) * 96.0 / 72.0  # pt -> px at 96dpi
        if text.endswith("px"):
            return float(text[:-2])
        return float(text)
    except ValueError:
        return None


def _canvas_size(slots_doc: dict[str, Any], width: int, height: int) -> tuple[float, float]:
    """Source canvas size in source units (for font-size scaling)."""
    source = slots_doc.get("source", {}) or {}
    view_box = source.get("view_box") or [0, 0, width, height]
    canvas_w = float(source.get("canvas_width") or view_box[2] or width)
    canvas_h = float(source.get("canvas_height") or view_box[3] or height)
    return canvas_w or float(width), canvas_h or float(height)


def _slot_style(
    slot: dict[str, Any], width: int, height: int, font_scale: float
) -> tuple[str, str]:
    """Return (outer container style, inner text style) for one slot."""
    bounds = slot.get("bounds", {}) or {}
    x = float(bounds.get("x", 0.0)) * width
    y = float(bounds.get("y", 0.0)) * height
    w = float(bounds.get("width", 0.0)) * width
    h = float(bounds.get("height", 0.0)) * height

    h_align = slot.get("horizontal_align", "left")
    v_align = slot.get("vertical_align", "top")
    justify = _H_JUSTIFY.get(h_align, "flex-start")
    align = _V_ALIGN.get(v_align, "flex-start")

    container = [
        "position:absolute",
        f"left:{x:.4f}px",
        f"top:{y:.4f}px",
        f"width:{w:.4f}px",
        f"height:{h:.4f}px",
        "display:flex",
        f"justify-content:{justify}",
        f"align-items:{align}",
        "box-sizing:border-box",
        "overflow:visible",
        "margin:0",
        "padding:0",
    ]
    rotation = float(slot.get("rotation", 0.0) or 0.0)
    if rotation:
        container.append(f"transform:rotate({rotation}deg)")
        container.append("transform-origin:center center")

    typo = slot.get("typography", {}) or {}
    inner = ["margin:0", "padding:0", "display:block", "white-space:pre-wrap"]
    font_family = typo.get("font_family")
    if font_family:
        # Quote the family and fall back to generic sans so the slot still reads
        # when the exact brand face is not installed on the rendering host.
        inner.append(f'font-family:"{font_family}", "Proxima Nova", sans-serif')
    font_size = typo.get("font_size")
    font_px = _parse_font_px(font_size)
    if font_px is not None:
        inner.append(f"font-size:{font_px * font_scale:.4f}px")
    font_weight = typo.get("font_weight")
    if font_weight is not None:
        inner.append(f"font-weight:{font_weight}")
    font_style = typo.get("font_style")
    if font_style:
        inner.append(f"font-style:{font_style}")
    line_height = typo.get("line_height")
    if line_height is not None:
        inner.append(f"line-height:{line_height}")
    letter_spacing = typo.get("letter_spacing")
    if letter_spacing and letter_spacing != "normal":
        inner.append(f"letter-spacing:{letter_spacing}")
    color = typo.get("color")
    if color:
        inner.append(f"color:{color}")
    text_align = {"left": "left", "center": "center", "right": "right"}.get(h_align, "left")
    inner.append(f"text-align:{text_align}")

    return ";".join(container), ";".join(inner)


def _render_slot(slot: dict[str, Any], width: int, height: int, font_scale: float) -> str:
    tag = slot.get("html_tag", "span")
    if tag not in {"h1", "h2", "h3", "p", "span", "li", "th", "td"}:
        tag = "span"
    value = html.escape(str(slot.get("example_value", "")))
    slot_id = html.escape(str(slot.get("id", "")), quote=True)
    container_style, inner_style = _slot_style(slot, width, height, font_scale)
    return (
        f'  <div class="slot" data-slot-id="{slot_id}" style="{container_style}">'
        f'<{tag} style="{inner_style}">{value}</{tag}></div>'
    )


# --------------------------------------------------------------------------- #
# Preview HTML
# --------------------------------------------------------------------------- #
def _item_artifacts(item_dir: Path) -> tuple[Path, Path]:
    svg_path = item_dir / "artifact" / "visual.svg"
    slots_path = item_dir / "artifact" / "text-slots.json"
    return svg_path, slots_path


def generate_preview_html(item_dir: Path, width: int, height: int) -> tuple[Path, list[str]]:
    """Build <item>/preview/preview.html. Returns (path, warnings)."""
    svg_path, slots_path = _item_artifacts(item_dir)
    if not svg_path.is_file():
        raise FileNotFoundError(f"missing artifact/visual.svg in {item_dir}")
    if not slots_path.is_file():
        raise FileNotFoundError(f"missing artifact/text-slots.json in {item_dir}")

    slots_doc = load_json(slots_path)
    slots = slots_doc.get("slots", []) or []
    canvas_w, _canvas_h = _canvas_size(slots_doc, width, height)
    font_scale = width / canvas_w if canvas_w else 1.0

    background, warnings = _build_background(svg_path)
    slot_markup = "\n".join(
        _render_slot(slot, width, height, font_scale) for slot in slots
    )

    title = html.escape(item_dir.name)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={width}, height={height}">
<title>Template preview — {title}</title>
<!-- Generated by generate_template_preview.py at {now_iso()}.
     Self-contained 1920x1080 stage: visual.svg inlined as the background with
     external rasters base64-embedded, plus each editable text slot positioned
     from its normalized bounds. Open directly in a browser (offline). -->
<style>
  html, body {{ margin: 0; padding: 0; background: #ffffff; }}
  #stage {{
    position: relative;
    width: {width}px;
    height: {height}px;
    overflow: hidden;
    background: #ffffff;
  }}
  #stage > .bg {{
    position: absolute;
    inset: 0;
    width: {width}px;
    height: {height}px;
    display: block;
  }}
  .slot {{ pointer-events: none; }}
  .slot > * {{ margin: 0; }}
</style>
</head>
<body>
  <div id="stage" data-deck-active>
{background}
{slot_markup}
  </div>
</body>
</html>
"""

    preview_dir = item_dir / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / "preview.html"
    preview_path.write_text(document, encoding="utf-8")
    return preview_path, warnings


# --------------------------------------------------------------------------- #
# Thumbnail capture
# --------------------------------------------------------------------------- #
class ThumbnailError(RuntimeError):
    """Raised when a thumbnail step cannot complete."""


def render_pdf_thumbnail(item_dir: Path, width: int, height: int) -> Path:
    """Render the ORIGINAL slide straight from its source PDF page to
    <item>/preview/thumbnail.png — the cleanest "as the original".

    Preferred over the evidence-SVG render because some extracted
    source-with-text.svg files overlay vector text on a background raster that
    ALREADY contains that text, producing a doubled/ghosted preview. The source
    PDF page has no such duplication. Reads the PDF path + page from the item's
    mapping.json (`source.path`, `source.slide_or_page`). Raises ThumbnailError
    so callers can fall back to the SVG render / composite.
    """
    mapping_path = item_dir / "mapping.json"
    if not mapping_path.is_file():
        raise ThumbnailError(f"no mapping.json in {item_dir} — cannot locate source PDF")
    source = (load_json(mapping_path).get("source") or {})
    pdf_ref = source.get("path")
    page_no = source.get("slide_or_page")
    if not pdf_ref or page_no is None:
        raise ThumbnailError("mapping.source.path / slide_or_page missing")
    pdf_path = Path(pdf_ref)
    if not pdf_path.is_absolute():
        pdf_path = REPO_ROOT / pdf_ref
    if pdf_path.suffix.lower() != ".pdf" or not pdf_path.is_file():
        raise ThumbnailError(f"source is not a readable PDF: {pdf_path}")
    try:
        import fitz  # PyMuPDF
    except ImportError as error:
        raise ThumbnailError(f"PyMuPDF (fitz) not available: {error}") from error

    preview_dir = item_dir / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = preview_dir / "thumbnail.png"
    try:
        doc = fitz.open(str(pdf_path))
        try:
            index = int(page_no) - 1
            if index < 0 or index >= doc.page_count:
                raise ThumbnailError(
                    f"page {page_no} out of range (doc has {doc.page_count})"
                )
            page = doc[index]
            rect = page.rect
            matrix = fitz.Matrix(width / rect.width, height / rect.height)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(str(thumbnail_path))
        finally:
            doc.close()
    except ThumbnailError:
        raise
    except Exception as error:  # noqa: BLE001 - surface any fitz failure cleanly
        raise ThumbnailError(f"fitz render failed: {error}") from error
    return thumbnail_path


def render_original_thumbnail(item_dir: Path, width: int, height: int) -> Path:
    """Render the ORIGINAL full slide (evidence/source-with-text.svg) to
    <item>/preview/thumbnail.png via render_svg.js — the slide "as the original".

    This is the faithful, preferred preview: it renders the source evidence SVG
    (text baked in, images referenced via ../artifact/assets/... which resolve
    from the evidence dir on disk) at 1920x1080 through Playwright/Chromium.
    Raises ThumbnailError (never an uncaught crash) when the evidence is missing
    or node/playwright fail, so callers can fall back to the composite capture.
    """
    source_svg = item_dir / "evidence" / "source-with-text.svg"
    if not source_svg.is_file():
        raise ThumbnailError(
            f"no evidence/source-with-text.svg in {item_dir} — cannot render the "
            f"original; fall back to the composite"
        )
    if not RENDER_JS.is_file():
        raise ThumbnailError(f"render_svg.js not found at {RENDER_JS}")

    preview_dir = item_dir / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = preview_dir / "thumbnail.png"
    temp_dir = Path(tempfile.mkdtemp(prefix="template-original-"))
    try:
        jobs = [{
            "svg": str(source_svg.resolve()),
            "output": str(thumbnail_path.resolve()),
            "width": width,
            "height": height,
        }]
        jobs_path = temp_dir / "jobs.json"
        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        cmd = ["node", str(RENDER_JS), "--jobs", str(jobs_path)]
        try:
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=180
            )
        except FileNotFoundError as error:
            raise ThumbnailError(
                f"node not found — cannot run render_svg.js ({error})"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ThumbnailError(f"render_svg.js timed out: {error}") from error
        if result.returncode != 0 or not thumbnail_path.is_file():
            detail = (result.stderr or result.stdout or "").strip()
            raise ThumbnailError(
                "render_svg.js did not produce thumbnail.png "
                f"(exit {result.returncode}). Likely export deps are not "
                f"installed yet. Detail: {detail or 'no output'}"
            )
        return thumbnail_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def capture_thumbnail(preview_path: Path, width: int, height: int) -> Path:
    """Render preview.html to <item>/preview/thumbnail.png via capture-slides.js.

    capture-slides.js writes a FIXED slide-01-bg.png and strips editable text by
    default; we pass --keep-bg-text for a faithful image, capture into a temp
    dir, move the PNG to thumbnail.png, and remove the side files. Raises
    ThumbnailError (never an uncaught crash) when node/playwright/capture fail.
    """
    if not CAPTURE_JS.is_file():
        raise ThumbnailError(f"capture-slides.js not found at {CAPTURE_JS}")

    preview_dir = preview_path.parent
    thumbnail_path = preview_dir / "thumbnail.png"
    temp_dir = Path(tempfile.mkdtemp(prefix="template-preview-"))
    try:
        cmd = [
            "node", str(CAPTURE_JS),
            "--url", preview_path.resolve().as_uri(),
            "--slides", "1",
            "--keep-bg-text",
            "--out-dir", str(temp_dir),
            "--width", str(width),
            "--height", str(height),
        ]
        try:
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=180
            )
        except FileNotFoundError as error:
            raise ThumbnailError(
                f"node not found — cannot run capture-slides.js ({error})"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ThumbnailError(f"capture-slides.js timed out: {error}") from error

        produced = temp_dir / "slide-01-bg.png"
        if result.returncode != 0 or not produced.is_file():
            detail = (result.stderr or result.stdout or "").strip()
            # capture-slides.js dies with a clear message when playwright is not
            # installed; surface it so the env-setup task is the obvious fix.
            raise ThumbnailError(
                "capture-slides.js did not produce slide-01-bg.png "
                f"(exit {result.returncode}). Likely export deps are not "
                f"installed yet. Detail: {detail or 'no output'}"
            )

        shutil.move(str(produced), str(thumbnail_path))
        return thumbnail_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Item / batch drivers
# --------------------------------------------------------------------------- #
def _looks_like_item(path: Path) -> bool:
    return (path / "artifact" / "visual.svg").is_file() and (
        path / "artifact" / "text-slots.json"
    ).is_file()


def process_item(
    item_dir: Path, width: int, height: int, html_only: bool, thumb_from: str
) -> bool:
    """Generate preview.html (the editable composite) plus, unless html_only, a
    full-slide thumbnail.png. Returns success.

    Thumbnail source (with fallback):
      - "pdf" (default): render the original slide straight from its source PDF
        page — cleanest, no text duplication. Falls back to "original" then
        "composite".
      - "original": render evidence/source-with-text.svg. Falls back to composite.
      - "composite": capture the reconstructed preview.html.
    """
    label = item_dir.name
    try:
        preview_path, warnings = generate_preview_html(item_dir, width, height)
    except (FileNotFoundError, OSError) as error:
        print(f"ERROR [{label}] {error}", file=sys.stderr)
        return False

    for note in warnings:
        print(f"  note [{label}] {note}")
    print(f"OK   [{label}] preview.html -> {preview_path}")

    if html_only:
        print(f"  skip [{label}] thumbnail (--html-only)")
        return True

    if thumb_from == "pdf":
        chain = ["pdf", "original", "composite"]
    elif thumb_from == "original":
        chain = ["original", "composite"]
    else:
        chain = ["composite"]

    renderers = {
        "pdf": lambda: render_pdf_thumbnail(item_dir, width, height),
        "original": lambda: render_original_thumbnail(item_dir, width, height),
        "composite": lambda: capture_thumbnail(preview_path, width, height),
    }
    for method in chain:
        try:
            thumb = renderers[method]()
            print(f"OK   [{label}] thumbnail.png ({method}) -> {thumb}")
            return True
        except ThumbnailError as error:
            print(f"  note [{label}] {method} render unavailable — {error}")

    print(
        f"WARN [{label}] thumbnail skipped — all sources failed; preview.html was "
        f"written. Re-run after export deps are installed.",
        file=sys.stderr,
    )
    return False


def iter_batch_items(extraction_dir: Path) -> list[Path]:
    items_root = extraction_dir / "items"
    if not items_root.is_dir():
        # Allow pointing --batch straight at an items/ dir too.
        items_root = extraction_dir
    return sorted(
        child for child in items_root.iterdir()
        if child.is_dir() and _looks_like_item(child)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--item-dir",
        help="A single item dir containing artifact/visual.svg + text-slots.json",
    )
    group.add_argument(
        "--batch",
        help="An extraction dir; processes every items/* item under it",
    )
    parser.add_argument("--width", type=int, default=1920, help="Stage width px")
    parser.add_argument("--height", type=int, default=1080, help="Stage height px")
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Write preview.html only; skip the thumbnail capture (exit 0)",
    )
    parser.add_argument(
        "--from",
        dest="thumb_from",
        choices=["pdf", "original", "composite"],
        default="pdf",
        help="Thumbnail source: 'pdf' renders the source PDF page (the original, "
        "no text duplication, default); 'original' renders "
        "evidence/source-with-text.svg; 'composite' captures the reconstructed "
        "preview.html. Each falls back to the next.",
    )
    args = parser.parse_args()

    if args.item_dir:
        item_dir = Path(args.item_dir).resolve()
        if not item_dir.is_dir():
            print(f"ERROR --item-dir not a directory: {item_dir}", file=sys.stderr)
            return 2
        if not _looks_like_item(item_dir):
            print(
                f"ERROR --item-dir missing artifact/visual.svg or "
                f"artifact/text-slots.json: {item_dir}",
                file=sys.stderr,
            )
            return 2
        ok = process_item(item_dir, args.width, args.height, args.html_only, args.thumb_from)
        return 0 if ok else 1

    extraction_dir = Path(args.batch).resolve()
    if not extraction_dir.is_dir():
        print(f"ERROR --batch not a directory: {extraction_dir}", file=sys.stderr)
        return 2
    items = iter_batch_items(extraction_dir)
    if not items:
        print(f"ERROR no items with artifacts found under {extraction_dir}", file=sys.stderr)
        return 2

    print(f"[batch] {len(items)} item(s) under {extraction_dir}")
    failures = 0
    for item_dir in items:
        if not process_item(item_dir, args.width, args.height, args.html_only, args.thumb_from):
            failures += 1
    print(f"[batch] done — {len(items) - failures}/{len(items)} succeeded")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
