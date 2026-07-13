#!/usr/bin/env python3
"""Convert PDF pages to text-preserving source SVG + reference PNG.

This is the ONLY approved PDF->SVG path (REQUIREMENTS.md: PyMuPDF). Per page it
writes into the staging item directory:

    <item-dir>/artifact/source-page.svg   text-preserving SVG (page.get_svg_image)
    <item-dir>/evidence/reference.png     raster for render-parity QA (page.get_pixmap)

`source-page.svg` is the input `extract_editable_text_slots.py` consumes. Never
render a PDF page to PNG and use it as the reusable visual — that bakes text
into pixels where validate_text_slots.py cannot detect it, and the gallery then
shows the baked text underneath the editable slot overlay (double text).

    python3 slide-system/scripts/convert_pdf_source.py \
      --pdf input/deck.pdf --page 5 --item-dir outputs/.../items/slide-5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import project_python_install_hint

INSTALL_HINT = f"Run {project_python_install_hint()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--page", action="append", type=int, required=True,
                        help="1-based page number; repeat together with --item-dir")
    parser.add_argument("--item-dir", action="append", type=Path, required=True,
                        help="Staging item directory receiving that page")
    parser.add_argument("--scale", type=float, default=None,
                        help="reference.png raster scale. Default: auto — fit a "
                             "1920px-wide render so the reference matches the QA "
                             "export render size (compare_renders.py rejects the "
                             "pair on size mismatch)")
    parser.add_argument("--reference-only", action="store_true",
                        help="regenerate evidence/reference.png only; leave "
                             "artifact/source-page.svg untouched")
    args = parser.parse_args()
    if len(args.page) != len(args.item_dir):
        parser.error("--page and --item-dir must be repeated the same number of times")
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    try:
        import fitz  # noqa: PLC0415 — the import IS the provider probe
    except ImportError:
        print(
            "BLOCKED: PyMuPDF (the only approved PDF->SVG provider) is not "
            f"importable by {sys.executable}.\n"
            f"Install: {INSTALL_HINT}\n"
            "Do not substitute pdftocairo/pdf2svg/mutool/ghostscript or a "
            "raster render — they break the editable-text-slot pipeline.",
            file=sys.stderr,
        )
        return 1

    document = fitz.open(args.pdf)
    results = {}
    for page_number, item_dir in zip(args.page, args.item_dir):
        if not 1 <= page_number <= document.page_count:
            print(f"BLOCKED: page {page_number} out of range 1..{document.page_count}",
                  file=sys.stderr)
            return 1
        page = document[page_number - 1]
        svg_path = item_dir / "artifact" / "source-page.svg"
        if not args.reference_only:
            svg_path.parent.mkdir(parents=True, exist_ok=True)
            svg_path.write_text(page.get_svg_image(text_as_path=False), encoding="utf-8")
        evidence_dir = item_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        reference_path = evidence_dir / "reference.png"
        scale = args.scale if args.scale is not None else 1920.0 / page.rect.width
        page.get_pixmap(matrix=fitz.Matrix(scale, scale)).save(reference_path)
        try:  # lossless recompress — pixels unchanged, ~15-20% smaller
            from PIL import Image
            with Image.open(reference_path) as image:
                image.load()
                image.save(reference_path, "PNG", optimize=True, compress_level=9)
        except ImportError:
            pass
        results[item_dir.name] = {
            "page": page_number,
            "source_svg": str(svg_path) if not args.reference_only else None,
            "reference_png": str(reference_path),
            "reference_scale": round(scale, 4),
            "page_size_pt": [round(page.rect.width, 2), round(page.rect.height, 2)],
            "provider": f"PyMuPDF {fitz.pymupdf_version}",
        }

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
