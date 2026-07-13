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
  * If Docling is not installed, PDF analysis falls back to the approved local
    PyMuPDF region detector. PPTX auto-detection still reports Docling missing.

The candidate request is a STARTING POINT, not an auto-feed: every candidate
must be reviewed, given a semantic `item_id`, and approved before
`scaffold_extraction.py` consumes it (the scaffold naming gate rejects the
generic placeholder ids minted here on purpose).

Docling may run locally (preferred) or via a project-scoped Docling MCP server;
this script only uses the local Python package. See
`slide-system/rules/extraction-methods.md` for the optional MCP note.

Data-chart regions are skipped by default during auto-detect because they are
usually source-specific, not reusable visual components. Manual extraction can
still target an exact chart region when the user explicitly asks for one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _common import now_iso, sha256_file, write_json

# Labels Docling emits that are worth proposing as reusable visual candidates.
# Prose/text blocks are recorded in page-analysis.json but not turned into
# candidates (they are editable content, not reusable visual building blocks).
# Data-chart regions are intentionally skipped by auto-detect: they are usually
# source-specific data, not reusable brand components. A user can still manually
# extract an exact chart region through component-extractor when requested.
CANDIDATE_LABELS = {"picture", "figure", "table", "form"}

ID_OK = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SOURCE_SUFFIXES = {".pdf", ".pptx"}
FALLBACK_LABEL = "figure"


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


def _docling_import_available() -> bool:
    try:
        from importlib.util import find_spec
        return find_spec("docling") is not None
    except Exception:  # noqa: BLE001 - availability check must not crash help/preflight
        return False


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


def _pdf_page_count(source: Path) -> tuple[int | None, str | None]:
    if source.suffix.lower() != ".pdf":
        return None, None
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        return None, f"PyMuPDF page count unavailable: {exc}"
    try:
        doc = fitz.open(source)
        count = int(doc.page_count)
        doc.close()
        return count, None
    except Exception as exc:  # noqa: BLE001 - analysis should degrade cleanly
        return None, f"PyMuPDF page count failed: {exc}"


def _page_numbers_for_source(source: Path,
                             pages: tuple[int, int] | None) -> tuple[list[int], list[str]]:
    warnings: list[str] = []
    if pages:
        start, end = pages
        page_count, warning = _pdf_page_count(source)
        if warning:
            warnings.append(warning)
        if page_count is not None:
            end = min(end, page_count)
        return list(range(start, end + 1)), warnings
    page_count, warning = _pdf_page_count(source)
    if warning:
        warnings.append(warning)
    if not page_count:
        return [], warnings
    return list(range(1, page_count + 1)), warnings


def _remap_single_page_elements(elements: list[dict],
                                requested_page: int) -> list[dict]:
    observed = {
        el.get("page")
        for el in elements
        if el.get("page") not in (None, "")
    }
    if requested_page != 1 and observed == {1}:
        for el in elements:
            if el.get("page") == 1:
                el["page"] = requested_page
    return elements


def analyze_source(converter, source: Path,
                   pages: tuple[int, int] | None) -> tuple[list[dict], list[str], dict]:
    """Run Docling with PDF page isolation when possible.

    A bad slide page should not abort the whole analysis run. For PDFs we use
    Docling's page_range support one page at a time, then let the PyMuPDF
    fallback propose regions for pages where Docling yielded no candidates.
    Non-PDF sources keep the original single-pass behavior.
    """
    warnings: list[str] = []
    stats = {
        "docling_mode": "single-pass",
        "docling_pages_attempted": 0,
        "docling_pages_failed": 0,
    }
    page_numbers, page_warnings = _page_numbers_for_source(source, pages)
    warnings.extend(page_warnings)
    if source.suffix.lower() == ".pdf" and page_numbers:
        stats["docling_mode"] = "page-by-page"
        elements: list[dict] = []
        for page_no in page_numbers:
            stats["docling_pages_attempted"] += 1
            try:
                result = converter.convert(
                    str(source),
                    page_range=(page_no, page_no),
                    raises_on_error=False,
                )
                page_doc = result.document
            except Exception as exc:  # noqa: BLE001 - keep other pages alive
                stats["docling_pages_failed"] += 1
                warnings.append(f"Docling failed on page {page_no}: {exc}")
                continue
            if page_doc is None:
                stats["docling_pages_failed"] += 1
                warnings.append(f"Docling returned no document for page {page_no}.")
                continue
            page_elements, page_element_warnings = analyze_document(page_doc)
            elements.extend(_remap_single_page_elements(page_elements, page_no))
            warnings.extend(
                f"page {page_no}: {warning}" for warning in page_element_warnings
            )
        return elements, warnings, stats

    convert_kwargs = {"page_range": pages} if pages else {}
    result = converter.convert(str(source), **convert_kwargs)
    elements, doc_warnings = analyze_document(result.document)
    warnings.extend(doc_warnings)
    return elements, warnings, stats


def analyze_pdf_pages_in_subprocess(source: Path, pages: tuple[int, int] | None,
                                    enable_ocr: bool,
                                    timeout_seconds: int) -> tuple[list[dict], list[str], dict]:
    page_numbers, warnings = _page_numbers_for_source(source, pages)
    stats = {
        "docling_mode": "subprocess-page-by-page",
        "docling_pages_attempted": 0,
        "docling_pages_failed": 0,
    }
    elements: list[dict] = []
    for page_no in page_numbers:
        stats["docling_pages_attempted"] += 1
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--source",
            str(source),
            "--extraction-id",
            "worker",
            "--_worker-page",
            str(page_no),
        ]
        if enable_ocr:
            cmd.append("--ocr")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(Path(__file__).resolve().parents[2]),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            stats["docling_pages_failed"] += 1
            warnings.append(f"Docling worker timed out on page {page_no}.")
            continue
        if proc.returncode != 0:
            stats["docling_pages_failed"] += 1
            error = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = error[-1] if error else f"exit {proc.returncode}"
            warnings.append(f"Docling worker failed on page {page_no}: {detail}")
            continue
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            stats["docling_pages_failed"] += 1
            warnings.append(f"Docling worker returned invalid JSON on page {page_no}: {exc}")
            continue
        page_elements = _remap_single_page_elements(
            list(payload.get("elements") or []), page_no)
        elements.extend(page_elements)
        warnings.extend(
            f"page {page_no}: {warning}"
            for warning in payload.get("warnings", [])
        )
    return elements, warnings, stats


def worker_page(source: Path, page_no: int, enable_ocr: bool) -> int:
    try:
        converter = _load_converter(enable_ocr=enable_ocr)
        result = converter.convert(
            str(source),
            page_range=(page_no, page_no),
            raises_on_error=False,
        )
        if result.document is None:
            raise RuntimeError("Docling returned no document")
        elements, warnings = analyze_document(result.document)
        payload = {
            "page": page_no,
            "elements": _remap_single_page_elements(elements, page_no),
            "warnings": warnings,
        }
        print(json.dumps(payload))
        return 0
    except DoclingUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - worker boundary reports failures
        print(f"ERROR: Docling worker failed on page {page_no}: {exc}", file=sys.stderr)
        return 4


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
        source = str(el.get("source") or "docling")
        detector = "PyMuPDF fallback" if source == "pymupdf-fallback" else "Docling"
        text = str(el.get("text") or "").strip()
        context_text = str(el.get("context_text") or "").strip()
        if text and context_text and context_text not in text:
            intent = f"{text} Context: {context_text}"
        elif text:
            intent = text
        elif context_text:
            intent = context_text
        else:
            intent = f"{el['label']} candidate detected by {detector}"
        items.append({
            "item_id": item_id,
            "slide_or_page": page if isinstance(page, int) else str(page),
            "region": el["region"],
            "object_ids": [],
            "requested_type": requested_type,
            "semantic_intent": [intent[:120]],
            "notes": f"DRAFT candidate from {detector} auto-detect. Rename item_id "
                     "to a semantic descriptor and confirm the region before "
                     "scaffolding; approval is still required before publish.",
            "replacement_for": None,
        })
        if max_candidates and len(items) >= max_candidates:
            break
    return items


def _candidate_regions_by_page(elements: list[dict], min_area: float,
                               max_area: float) -> dict[int | str, list[dict]]:
    regions: dict[int | str, list[dict]] = {}
    for el in elements:
        if el.get("label") not in CANDIDATE_LABELS:
            continue
        region = el.get("region") or {}
        try:
            area = float(region.get("width", 0)) * float(region.get("height", 0))
        except (TypeError, ValueError):
            continue
        if min_area <= area <= max_area:
            regions.setdefault(el.get("page"), []).append(el)
    return regions


def _clamp_region(x0: float, y0: float, x1: float, y1: float) -> dict | None:
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 <= x0 or y1 <= y0:
        return None
    return {
        "x": round(x0, 6),
        "y": round(y0, 6),
        "width": round(x1 - x0, 6),
        "height": round(y1 - y0, 6),
        "unit": "normalized",
    }


def _atom_center_y(atom: dict) -> float:
    r = atom["region"]
    return float(r["y"]) + float(r["height"]) / 2


def _union_region(regions: list[dict], pad: float = 0.012) -> dict | None:
    if not regions:
        return None
    x0 = min(float(r["x"]) for r in regions) - pad
    y0 = min(float(r["y"]) for r in regions) - pad
    x1 = max(float(r["x"]) + float(r["width"]) for r in regions) + pad
    y1 = max(float(r["y"]) + float(r["height"]) for r in regions) + pad
    return _clamp_region(x0, y0, x1, y1)


def _region_area(region: dict) -> float:
    try:
        return max(0.0, float(region.get("width", 0))) * max(
            0.0, float(region.get("height", 0)))
    except (TypeError, ValueError):
        return 0.0


def _intersection_area(a: dict, b: dict) -> float:
    try:
        ax0, ay0 = float(a["x"]), float(a["y"])
        ax1 = ax0 + float(a["width"])
        ay1 = ay0 + float(a["height"])
        bx0, by0 = float(b["x"]), float(b["y"])
        bx1 = bx0 + float(b["width"])
        by1 = by0 + float(b["height"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    width = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    height = max(0.0, min(ay1, by1) - max(ay0, by0))
    return width * height


def _candidate_region(candidate: dict) -> dict:
    region = candidate.get("region") if isinstance(candidate, dict) else None
    return region if isinstance(region, dict) else candidate


def _contained_existing_candidate(region: dict, existing: list[dict]) -> dict | None:
    """Return the existing candidate represented by a larger fallback crop.

    This keeps broad text/vector fallback rows from creating duplicate Drafts
    around a Docling visual that is already the reusable component. Tiny
    embedded detections, such as arrow icons in a metric strip, are ignored so
    the broader missing component is still staged.
    """
    area = _region_area(region)
    if area <= 0:
        return None
    best: dict | None = None
    best_score = 0.0
    for candidate in existing:
        candidate_region = _candidate_region(candidate)
        candidate_area = _region_area(candidate_region)
        if candidate_area <= 0:
            continue
        intersection = _intersection_area(region, candidate_region)
        if intersection <= 0:
            continue
        candidate_coverage = intersection / candidate_area
        candidate_share = candidate_area / area
        if candidate_coverage >= 0.82 and candidate_share >= 0.20:
            score = candidate_coverage * candidate_share
            if score > best_score:
                best = candidate
                best_score = score
    return best


def _append_context_text(candidate: dict | None, text: str) -> None:
    if not isinstance(candidate, dict):
        return
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return
    existing = str(candidate.get("context_text") or "").strip()
    if existing and text in existing:
        return
    combined = f"{existing} {text}".strip() if existing else text
    candidate["context_text"] = combined[:320]


def _covered_by_existing_candidates(region: dict, existing: list[dict]) -> bool:
    """Return true when a fallback row is already represented by candidates.

    Small Docling detections inside a larger missing row, such as an arrow icon
    inside a metric strip, should not suppress the fallback row. A broad
    candidate or a set of adjacent candidates that covers most of the row
    should suppress it to avoid duplicate Drafts.
    """
    area = _region_area(region)
    if area <= 0:
        return True
    if _contained_existing_candidate(region, existing):
        return True
    intersections = [
        _intersection_area(region, _candidate_region(candidate))
        for candidate in existing
    ]
    if not intersections:
        return False
    if max(intersections) / area >= 0.72:
        return True
    return sum(intersections) / area >= 0.55


def _cluster_atoms_by_row(atoms: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for atom in sorted(atoms, key=lambda a: (_atom_center_y(a), a["region"]["x"])):
        cy = _atom_center_y(atom)
        target: list[dict] | None = None
        best_delta: float | None = None
        for row in rows:
            region = _union_region([a["region"] for a in row], pad=0.0)
            if not region:
                continue
            row_cy = float(region["y"]) + float(region["height"]) / 2
            threshold = 0.13
            delta = abs(cy - row_cy)
            if delta <= threshold and (best_delta is None or delta < best_delta):
                target = row
                best_delta = delta
        if target is None:
            rows.append([atom])
        else:
            target.append(atom)
    return rows


def _text_lines_for_row(row: list[dict]) -> list[str]:
    text_atoms = [atom for atom in row if str(atom.get("text") or "").strip()]
    lines: list[list[dict]] = []
    for atom in sorted(text_atoms, key=lambda a: (_atom_center_y(a), a["region"]["x"])):
        cy = _atom_center_y(atom)
        target: list[dict] | None = None
        best_delta: float | None = None
        for line in lines:
            line_cy = sum(_atom_center_y(a) for a in line) / len(line)
            delta = abs(cy - line_cy)
            if delta <= 0.075 and (best_delta is None or delta < best_delta):
                target = line
                best_delta = delta
        if target is None:
            lines.append([atom])
        else:
            target.append(atom)
    ordered_lines: list[str] = []
    for line in lines:
        text = " ".join(
            str(atom.get("text") or "").strip()
            for atom in sorted(line, key=lambda a: a["region"]["x"])
            if str(atom.get("text") or "").strip()
        )
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            ordered_lines.append(text)
    return ordered_lines


def _merge_header_visual_rows(elements: list[dict]) -> list[dict]:
    if len(elements) < 2:
        return elements
    merged: list[dict] = []
    i = 0
    while i < len(elements):
        current = elements[i]
        if i + 1 >= len(elements):
            merged.append(current)
            break
        nxt = elements[i + 1]
        cur_region = current.get("region") or {}
        next_region = nxt.get("region") or {}
        try:
            cur_bottom = float(cur_region["y"]) + float(cur_region["height"])
            next_top = float(next_region["y"])
            gap = next_top - cur_bottom
            cur_center = float(cur_region["x"]) + float(cur_region["width"]) / 2
            next_center = float(next_region["x"]) + float(next_region["width"]) / 2
            combined_height = (
                max(float(cur_region["y"]) + float(cur_region["height"]),
                    float(next_region["y"]) + float(next_region["height"]))
                - min(float(cur_region["y"]), float(next_region["y"]))
            )
        except (KeyError, TypeError, ValueError):
            merged.append(current)
            i += 1
            continue
        current_text = str(current.get("text") or "")
        next_text = str(nxt.get("text") or "")
        current_words = len(re.findall(r"[A-Za-z0-9]+", current_text))
        next_words = len(re.findall(r"[A-Za-z0-9]+", next_text))
        close_vertical = 0 <= gap <= 0.055
        aligned = abs(cur_center - next_center) <= 0.12
        header_like = current_words >= 4 and float(cur_region.get("height", 0)) <= 0.18
        visual_like = (
            _region_area(next_region) >= 0.05
            or next_words >= 6
        )
        if close_vertical and aligned and header_like and visual_like and combined_height <= 0.45:
            region = _union_region([cur_region, next_region], pad=0.012)
            merged.append({
                "page": current.get("page"),
                "label": current.get("label", FALLBACK_LABEL),
                "text": re.sub(
                    r"\s+", " ",
                    "\n".join([current_text, next_text]).strip()
                )[:240],
                "region": region,
                "source": current.get("source") or nxt.get("source") or "pymupdf-fallback",
            })
            i += 2
        else:
            merged.append(current)
            i += 1
    return merged


def _icon_sheet_element_from_atoms(page_no: int, atoms: list[dict],
                                   page_text: str,
                                   min_icons: int = 40) -> dict | None:
    if not re.search(r"\bicons?\b", page_text, re.I):
        return None
    small_drawings = []
    for atom in atoms:
        if atom.get("kind") != "drawing":
            continue
        area = _region_area(atom.get("region") or {})
        if 0.00002 <= area <= 0.01:
            small_drawings.append(atom)
    if len(small_drawings) < min_icons:
        return None
    region = _union_region([atom["region"] for atom in small_drawings], pad=0.025)
    if not region:
        return None
    # Include the sheet title/section heading above the glyph grid while keeping
    # the region tied to the detected icon geometry.
    expanded = _clamp_region(
        float(region["x"]) - 0.01,
        float(region["y"]) - 0.075,
        float(region["x"]) + float(region["width"]) + 0.01,
        float(region["y"]) + float(region["height"]) + 0.025,
    )
    if not expanded:
        return None
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    text = " ".join(lines[:12])
    return {
        "page": page_no,
        "label": FALLBACK_LABEL,
        "text": re.sub(r"\s+", " ", text).strip()[:240],
        "region": expanded,
        "source": "pymupdf-fallback",
    }


def fallback_elements_from_atoms(page_no: int, atoms: list[dict],
                                 min_area: float = 0.015,
                                 max_area: float = 0.85) -> list[dict]:
    """Build broad row candidates from PDF text/vector atoms.

    This is intentionally conservative. It proposes review regions that Docling
    missed; it does not replace the canonical PDF->SVG extraction path.
    """
    elements: list[dict] = []
    atoms = [
        atom for atom in atoms
        if 0.12 <= float((atom.get("region") or {}).get("y", 0)) <= 0.93
    ]
    for row in _cluster_atoms_by_row(atoms):
        region = _union_region([a["region"] for a in row])
        if not region:
            continue
        area = region["width"] * region["height"]
        has_visual = any(a.get("kind") == "drawing" for a in row)
        text_atoms = [a for a in row if a.get("text")]
        if area < min_area or area > max_area:
            continue
        joined_text = " ".join(a.get("text", "") for a in text_atoms)
        word_count = len(re.findall(r"[A-Za-z0-9]+", joined_text))
        broad_text = (
            region["width"] >= 0.25
            and region["height"] >= 0.035
            and word_count >= 3
        )
        if not has_visual and (len(text_atoms) < 2 and not broad_text):
            continue
        text = "\n".join(_text_lines_for_row(row))
        elements.append({
            "page": page_no,
            "label": FALLBACK_LABEL,
            "text": re.sub(r"\s+", " ", text).strip()[:200],
            "region": region,
            "source": "pymupdf-fallback",
        })
    return _merge_header_visual_rows(elements)


def _pdf_fallback_elements(source: Path, pages: tuple[int, int] | None,
                           existing_candidates: dict[int | str, list[dict]],
                           min_area: float, max_area: float) -> tuple[list[dict], list[str]]:
    if source.suffix.lower() != ".pdf":
        return [], []
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        return [], [f"PyMuPDF fallback unavailable: {exc}"]

    fallback: list[dict] = []
    warnings: list[str] = []
    doc = fitz.open(source)
    start, end = pages or (1, doc.page_count)
    end = min(end, doc.page_count)
    for page_no in range(start, end + 1):
        page = doc[page_no - 1]
        page_w, page_h = float(page.rect.width), float(page.rect.height)
        page_text = page.get_text("text") or ""
        atoms: list[dict] = []
        icon_atoms: list[dict] = []
        for block in page.get_text("blocks"):
            x0, y0, x1, y1, text, *_rest = block
            text = re.sub(r"\s+", " ", str(text or "")).strip()
            if not text or (text.isdigit() and len(text) <= 3):
                continue
            region = _clamp_region(x0 / page_w, y0 / page_h, x1 / page_w, y1 / page_h)
            if not region:
                continue
            if 0.05 <= region["y"] <= 0.95:
                icon_atoms.append({"kind": "text", "text": text[:120], "region": region})
            if region["y"] < 0.12 or region["y"] > 0.93:
                continue
            atoms.append({"kind": "text", "text": text[:120], "region": region})
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if not rect:
                continue
            region = _clamp_region(rect.x0 / page_w, rect.y0 / page_h,
                                   rect.x1 / page_w, rect.y1 / page_h)
            if not region:
                continue
            area = region["width"] * region["height"]
            if 0.05 <= region["y"] <= 0.97:
                icon_atoms.append({"kind": "drawing", "text": "", "region": region})
            if region["y"] < 0.12 or region["y"] > 0.93:
                continue
            if area < max(0.003, min_area * 0.2) or area > max_area:
                continue
            atoms.append({"kind": "drawing", "text": "", "region": region})
        icon_sheet = _icon_sheet_element_from_atoms(page_no, icon_atoms, page_text)
        if icon_sheet:
            fallback.append(icon_sheet)
            continue
        raw_page_elements = fallback_elements_from_atoms(
            page_no, atoms, min_area=min_area, max_area=max_area)
        page_existing = [
            *existing_candidates.get(page_no, []),
            *existing_candidates.get(str(page_no), []),
        ]
        page_elements: list[dict] = []
        for el in raw_page_elements:
            region = el.get("region") or {}
            context_target = _contained_existing_candidate(region, page_existing)
            if context_target:
                _append_context_text(context_target, str(el.get("text") or ""))
                continue
            if _covered_by_existing_candidates(region, page_existing):
                continue
            page_elements.append(el)
        if page_elements:
            fallback.extend(page_elements)
        elif not raw_page_elements:
            warnings.append(f"PyMuPDF fallback found no candidate rows on page {page_no}.")
    doc.close()
    return fallback, warnings


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
    parser.add_argument("--page-timeout", type=int, default=180,
                        help="Seconds before a PDF page worker is treated as failed "
                             "(default: 180).")
    parser.add_argument("--_worker-page", type=int, default=None,
                        help=argparse.SUPPRESS)
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
    if args.page_timeout <= 0:
        print("ERROR: require --page-timeout > 0.", file=sys.stderr)
        return 2

    if args._worker_page is not None:
        return worker_page(source, args._worker_page, args.ocr)

    # --- Docling (lazy; PyMuPDF-only fallback for PDF) ---------------------- #
    docling_available = _docling_import_available()
    if not docling_available and source.suffix.lower() != ".pdf":
        print(
            "Docling is not installed, so candidate auto-detection is unavailable.\n"
            "  - This is OPTIONAL: extraction still works fully without it "
            "(use component-extractor directly).\n"
            "  - To enable local auto-detect, install Docling into the project "
            "environment, e.g. `pip install docling` (ask before adding "
            "dependencies in a shared environment).",
            file=sys.stderr,
        )
        return 3

    if source.suffix.lower() == ".pdf" and docling_available:
        elements, warnings, docling_stats = analyze_pdf_pages_in_subprocess(
            source, args.pages, args.ocr, args.page_timeout)
    elif source.suffix.lower() == ".pdf":
        elements = []
        warnings = ["Docling is not installed; used the approved PyMuPDF fallback detector."]
        docling_stats = {
            "docling_mode": "pymupdf-fallback-only",
            "docling_pages_attempted": 0,
            "docling_pages_failed": 0,
        }
    else:
        try:
            converter = _load_converter(enable_ocr=args.ocr)
            elements, warnings, docling_stats = analyze_source(converter, source, args.pages)
        except DoclingUnavailable as exc:
            print(str(exc), file=sys.stderr)
            return 3
        except Exception as exc:  # noqa: BLE001 - report any Docling failure cleanly
            print(f"ERROR: Docling failed to convert {source}: {exc}", file=sys.stderr)
            return 4
    existing_candidates = _candidate_regions_by_page(
        elements, args.min_area, args.max_area)
    fallback_elements, fallback_warnings = _pdf_fallback_elements(
        source, args.pages, existing_candidates, args.min_area, args.max_area)
    if fallback_elements:
        elements.extend(fallback_elements)
    warnings.extend(fallback_warnings)
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
        "fallback_element_count": len(fallback_elements),
        "docling": docling_stats,
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
        "fallback_element_count": len(fallback_elements),
        **docling_stats,
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
        "fallback_elements": len(fallback_elements),
        **docling_stats,
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
