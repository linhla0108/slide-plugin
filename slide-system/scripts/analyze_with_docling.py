#!/usr/bin/env python3
"""Optional Docling analysis layer — detect *candidate* reusable regions.

This is an ANALYSIS-ONLY pre-step for `component-extractor`. It reads a PDF or
PPTX source, asks Docling to detect its layout (pictures, tables, figures,
section blocks), and writes candidate metadata a human reviews before any
extraction runs. It is deliberately inert with respect to shared state:

  * It NEVER publishes, never mutates the registry, and never writes a shared
    library artifact. PyMuPDF stays the canonical PDF->SVG provider; this script
    does not produce reusable `visual.svg`/`text-slots.json` at all.
  * Its only writes land under
    `outputs/component-extractions/<extraction-id>/analysis/`:
      - page-analysis.json            every detected element + normalized bbox
      - candidate-extraction-request.json   only when at least one candidate is
                                            detected; a draft request for review
      - docling-report.json           run metadata (version, source hash, counts)
  * If Docling is not installed it exits with a clear, actionable message and
    writes nothing — no partial analysis, no registry/library writes.

The candidate request is a STARTING POINT, not an auto-feed: every candidate
must be reviewed, given a semantic `item_id`, and approved before
`scaffold_extraction.py` consumes it (the scaffold naming gate rejects the
generic placeholder ids minted here on purpose).

Docling may run locally (preferred) or via a project-scoped Docling MCP server;
this script only uses the local Python package. See
`slide-system/rules/extraction-methods.md` for the optional MCP note.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import now_iso, sha256_file, write_json

# Labels Docling emits that are worth proposing as reusable visual candidates.
# Prose/text blocks are recorded in page-analysis.json but not turned into
# candidates (they are editable content, not reusable visual building blocks).
CANDIDATE_LABELS = {"picture", "figure", "table", "chart", "form"}

ID_OK = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SOURCE_SUFFIXES = {".pdf", ".pptx"}


class DoclingUnavailable(RuntimeError):
    """Raised when the Docling package cannot be imported."""


def _load_converter(enable_ocr: bool = False):
    """Import Docling lazily so `--help` and arg validation never need it.

    Returns a constructed DocumentConverter. Raises DoclingUnavailable with an
    actionable message (kept out of the heavy import path) when Docling is
    missing, so the caller can exit cleanly without any writes.
    """
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:  # noqa: PERF203 - single import site
        raise DoclingUnavailable(
            "Docling is not installed, so candidate auto-detection is "
            "unavailable.\n"
            "  - This is OPTIONAL: extraction still works fully without it "
            "(use component-extractor directly).\n"
            "  - To enable local auto-detect, install Docling into the project "
            "environment, e.g. `pip install docling` (ask before adding "
            "dependencies in a shared environment).\n"
            f"  (import error: {exc})"
        ) from exc
    pipeline_options = PdfPipelineOptions()
    # Slide PDFs are text-first in the supported pipeline, and OCR model
    # selection can vary by Docling/RapidOCR install. Keep OCR opt-in so
    # auto-detect works on ordinary PDFs without requiring OCR model support.
    pipeline_options.do_ocr = enable_ocr
    pipeline_options.do_table_structure = True
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def _normalized_bbox(bbox, page_w: float, page_h: float) -> dict | None:
    """Convert a Docling bbox to a top-left normalized region dict.

    Returns None when the page size or bbox is unusable, so a malformed element
    is skipped rather than producing a bogus 0..1 region.
    """
    if not page_w or not page_h:
        return None
    try:
        left, right = float(bbox.l), float(bbox.r)
        top, bottom = float(bbox.t), float(bbox.b)
    except (AttributeError, TypeError, ValueError):
        return None

    # Docling may report a bottom-left origin; fold it to top-left.
    origin = getattr(getattr(bbox, "coord_origin", None), "value", None) \
        or str(getattr(bbox, "coord_origin", "")).upper()
    if "BOTTOM" in str(origin).upper():
        top, bottom = page_h - top, page_h - bottom

    y0, y1 = sorted((top, bottom))
    x0, x1 = sorted((left, right))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    clamp = lambda v: round(min(max(v, 0.0), 1.0), 6)
    return {
        "x": clamp(x0 / page_w),
        "y": clamp(y0 / page_h),
        "width": clamp(w / page_w),
        "height": clamp(h / page_h),
        "unit": "normalized",
    }


def _page_sizes(doc) -> dict:
    """Map page_no -> (width, height). Tolerates Docling version differences."""
    sizes: dict = {}
    pages = getattr(doc, "pages", {}) or {}
    items = pages.items() if hasattr(pages, "items") else enumerate(pages)
    for page_no, page in items:
        size = getattr(page, "size", None)
        if size is not None:
            sizes[page_no] = (float(getattr(size, "width", 0) or 0),
                              float(getattr(size, "height", 0) or 0))
    return sizes


def analyze_document(doc) -> tuple[list[dict], list[str]]:
    """Walk a DoclingDocument and return (elements, warnings).

    Each element: {page, label, text, region}. Defensive against Docling API
    drift — any element we cannot read becomes a warning, never a crash.
    """
    sizes = _page_sizes(doc)
    elements: list[dict] = []
    warnings: list[str] = []

    try:
        walker = doc.iterate_items()
    except AttributeError:
        return [], ["Docling document exposes no iterate_items(); "
                    "version may be incompatible."]

    for entry in walker:
        item = entry[0] if isinstance(entry, tuple) else entry
        label = str(getattr(getattr(item, "label", None), "value", None)
                    or getattr(item, "label", "") or "unknown").lower()
        provs = getattr(item, "prov", None) or []
        if not provs:
            continue
        for prov in provs:
            page_no = getattr(prov, "page_no", None)
            page_w, page_h = sizes.get(page_no, (0.0, 0.0))
            region = _normalized_bbox(getattr(prov, "bbox", None), page_w, page_h)
            if region is None:
                warnings.append(f"Unreadable bbox for a '{label}' on page {page_no}.")
                continue
            text = (getattr(item, "text", "") or "").strip()
            elements.append({
                "page": page_no,
                "label": label,
                "text": text[:200],
                "region": region,
            })
    return elements, warnings


def _parse_pages(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    raw = value.strip()
    try:
        if "-" in raw:
            start, end = [int(part.strip()) for part in raw.split("-", 1)]
        else:
            start = end = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--pages must be a 1-based page number or range like 2-5"
        ) from exc
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError(
            "--pages must be 1-based and end must be >= start"
        )
    return start, end


def build_candidates(elements: list[dict], extraction_id: str,
                     requested_type: str, max_candidates: int | None,
                     min_area: float = 0.015,
                     max_area: float = 0.85) -> list[dict]:
    """Turn figure-like elements into draft extraction-request items.

    The ids are deliberate placeholders (`<label>-pN-K`); a human must rename
    them to a semantic id before scaffolding — the scaffold gate enforces this.
    """
    items: list[dict] = []
    per_page: dict = {}
    for el in elements:
        if el["label"] not in CANDIDATE_LABELS:
            continue
        region = el["region"]
        area = region["width"] * region["height"]
        if area < min_area or area > max_area:
            continue
        page = el["page"]
        per_page[page] = per_page.get(page, 0) + 1
        idx = per_page[page]
        page_token = re.sub(r"[^a-z0-9]", "", str(page).lower()) or "x"
        item_id = f"{el['label']}-p{page_token}-{idx}"
        intent = el["text"] or f"{el['label']} candidate detected by Docling"
        items.append({
            "item_id": item_id,
            "slide_or_page": page if isinstance(page, int) else str(page),
            "region": el["region"],
            "object_ids": [],
            "requested_type": requested_type,
            "semantic_intent": [intent[:120]],
            "notes": "DRAFT candidate from Docling auto-detect. Rename item_id "
                     "to a semantic descriptor and confirm the region before "
                     "scaffolding; approval is still required before publish.",
            "replacement_for": None,
        })
        if max_candidates and len(items) >= max_candidates:
            break
    return items


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Optional Docling analysis: detect candidate reusable "
                    "regions in a PDF/PPTX. Analysis-only — never publishes or "
                    "mutates the registry/library.")
    parser.add_argument("--source", required=True, help="PDF or PPTX source file.")
    parser.add_argument("--extraction-id", required=True,
                        help="Output namespace under outputs/component-extractions/.")
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parents[2] / "outputs/component-extractions"),
        help="Root for extraction outputs (default: outputs/component-extractions).")
    parser.add_argument("--requested-type", default="component",
                        help="requested_type for draft candidates (default: component).")
    parser.add_argument("--max-candidates", type=int, default=None,
                        help="Cap the number of draft candidates emitted.")
    parser.add_argument("--pages", type=_parse_pages, default=None,
                        help="Optional 1-based page or page range to convert, "
                             "for example 1 or 2-4.")
    parser.add_argument("--min-area", type=float, default=0.015,
                        help="Minimum normalized bbox area for draft candidates "
                             "(default: 0.015 to skip tiny decorations).")
    parser.add_argument("--max-area", type=float, default=0.85,
                        help="Maximum normalized bbox area for draft candidates "
                             "(default: 0.85 to skip full-page backgrounds).")
    parser.add_argument("--ocr", action="store_true",
                        help="Enable Docling OCR for scanned PDFs. Off by default "
                             "for text-first slide PDFs.")
    args = parser.parse_args()

    # --- argument validation (no Docling needed) ---------------------------- #
    if not ID_OK.match(args.extraction_id):
        print(f"ERROR: invalid --extraction-id '{args.extraction_id}' "
              "(must match ^[a-z0-9][a-z0-9._-]*$).", file=sys.stderr)
        return 2
    source = Path(args.source)
    if not source.exists() or not source.is_file():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 2
    if source.suffix.lower() not in SOURCE_SUFFIXES:
        print(f"ERROR: unsupported source type '{source.suffix}'. "
              f"Expected one of: {', '.join(sorted(SOURCE_SUFFIXES))}.",
              file=sys.stderr)
        return 2
    if args.min_area < 0 or args.max_area <= 0 or args.min_area > args.max_area:
        print("ERROR: require 0 <= --min-area <= --max-area.", file=sys.stderr)
        return 2

    # --- Docling (lazy; clean degrade) -------------------------------------- #
    try:
        converter = _load_converter(enable_ocr=args.ocr)
    except DoclingUnavailable as exc:
        # No partial writes: nothing has been created yet. Registry/library
        # are never touched by this script in any path.
        print(str(exc), file=sys.stderr)
        return 3

    try:
        convert_kwargs = {"page_range": args.pages} if args.pages else {}
        result = converter.convert(str(source), **convert_kwargs)
        doc = result.document
    except Exception as exc:  # noqa: BLE001 - report any Docling failure cleanly
        print(f"ERROR: Docling failed to convert {source}: {exc}", file=sys.stderr)
        return 4

    elements, warnings = analyze_document(doc)
    candidates = build_candidates(elements, args.extraction_id,
                                  args.requested_type, args.max_candidates,
                                  args.min_area, args.max_area)

    out_dir = Path(args.output_root) / args.extraction_id / "analysis"
    page_analysis = {
        "extraction_id": args.extraction_id,
        "source_path": str(source),
        "generated_at": now_iso(),
        "generated_by": "analyze_with_docling.py",
        "element_count": len(elements),
        "page_range": list(args.pages) if args.pages else None,
        "elements": elements,
        "warnings": warnings,
    }
    docling_version = None
    try:  # best-effort version stamp; never fatal
        from importlib.metadata import version
        docling_version = version("docling")
    except Exception:  # noqa: BLE001
        pass

    # The extraction-request schema requires items.minItems == 1, so an empty
    # candidate list must NOT be written as a request (it would be invalid and
    # falsely advertise a usable hand-off). page-analysis.json and the report
    # are always written; the report records whether a request file exists.
    candidate_request_written = bool(candidates)
    report = {
        "extraction_id": args.extraction_id,
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "docling_version": docling_version,
        "ocr_enabled": args.ocr,
        "generated_at": now_iso(),
        "element_count": len(elements),
        "candidate_count": len(candidates),
        "candidate_request_written": candidate_request_written,
        "page_range": list(args.pages) if args.pages else None,
        "candidate_filters": {
            "min_area": args.min_area,
            "max_area": args.max_area,
        },
        "warnings": warnings,
        "writes": "analysis-only (no registry/library/publish writes)",
    }

    write_json(out_dir / "page-analysis.json", page_analysis)
    if candidate_request_written:
        write_json(out_dir / "candidate-extraction-request.json", {
            "extraction_id": args.extraction_id,
            "source_path": str(source),
            "items": candidates,
        })
    write_json(out_dir / "docling-report.json", report)

    summary = {
        "status": "ok",
        "analysis_dir": str(out_dir),
        "elements": len(elements),
        "candidates": len(candidates),
        "candidate_request_written": candidate_request_written,
        "page_range": list(args.pages) if args.pages else None,
        "warnings": len(warnings),
    }
    if not candidate_request_written:
        summary["note"] = ("No candidate-extraction-request.json written: no "
                           "reusable regions were detected.")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
