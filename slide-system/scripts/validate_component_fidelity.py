#!/usr/bin/env python3
"""T3 — fidelity safety net: prove reused slides actually use the component.

The signal is structural, not textual: a real preview.html has only `.bg` and
`.slot` classes, so class-name overlap is meaningless. Instead we match on the
component's `data-slot-id` set (preserved verbatim by the T2 scaffold) plus the
presence of a `.bg` layer. Slot IDs are language-independent because the
scaffold copies them from preview.html rather than regenerating them from the
(Vietnamese) deck copy.

Without a run-local slot-content plan, coverage is computed against the whole
component as a coarse safety net. With a validated plan, coverage is computed
against exactly the planned slots: empty native slots are intentional and must
not force placeholder content into the deck. Run with --warn during rollout;
drop --warn to make it BLOCKING once a scaffold-built deck passes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import load_json, now_iso, write_json

SLOT_ID_RE = re.compile(r'data-slot-id="([^"]+)"')
BG_RE = re.compile(r'class="[^"]*\bbg\b[^"]*"', re.IGNORECASE)

REUSE_MIN = 0.70


def _slot_ids(html: str) -> set[str]:
    return set(SLOT_ID_RE.findall(html))


def _preview_map(registry: dict) -> dict[str, str]:
    return {
        item.get("id"): (item.get("paths") or {}).get("preview")
        for item in registry.get("items", [])
        if (item.get("paths") or {}).get("preview")
    }


def _decisions(report: dict) -> list[tuple[str, dict]]:
    if isinstance(report.get("slides"), list):
        return [(s.get("request_id", "?"), s.get("decision") or {})
                for s in report["slides"] if isinstance(s, dict)]
    return [(report.get("request_id", "?"), report.get("decision") or {})]


def _planned_slots(plan: dict | None, request_id: str, item_id: str) -> set[str] | None:
    """Return declared slot ids for one reuse slide, or None without a plan."""
    if not isinstance(plan, dict):
        return None
    for entry in plan.get("slides") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("request_id") == request_id and entry.get("item_id") == item_id:
            return {
                slot.get("slot_id") for slot in entry.get("slots") or []
                if isinstance(slot, dict) and slot.get("slot_id")
            }
    return set()


def check_fidelity(deck_html: str, report: dict, registry: dict,
                   slot_content_plan: dict | None = None) -> list[dict]:
    preview_map = _preview_map(registry)
    deck_slot_ids = _slot_ids(deck_html)
    deck_has_bg = bool(BG_RE.search(deck_html))
    results: list[dict] = []

    for rid, dec in _decisions(report):
        action = dec.get("action", "")
        item_id = dec.get("item_id")
        if action != "reuse" or not item_id:
            continue

        preview_path = preview_map.get(item_id)
        entry = {"request_id": rid, "item_id": item_id, "action": action}

        if not preview_path:
            entry.update(pass_=False, reason=f"item {item_id!r} missing paths.preview "
                         f"(pass the full registry, not compact)")
            results.append(entry)
            continue

        p = Path(preview_path)
        if not p.exists():
            entry.update(pass_=False, reason=f"preview.html not found: {preview_path}")
            results.append(entry)
            continue

        comp_ids = _slot_ids(p.read_text(encoding="utf-8", errors="replace"))
        if not comp_ids:
            # No slots to match on — fall back to data-base-component presence.
            used = f'data-base-component="{item_id}"' in deck_html
            entry.update(pass_=used, coverage=None,
                         reason="component has no slots; matched on data-base-component"
                         if used else "no slots and no data-base-component marker in deck")
            results.append(entry)
            continue

        planned = _planned_slots(slot_content_plan, rid, item_id)
        expected_ids = planned if planned is not None else comp_ids
        coverage_scope = "planned-slots" if planned is not None else "all-native-slots"
        if planned is not None and not planned:
            entry.update(pass_=False, coverage=0.0, threshold=1.0,
                         coverage_scope=coverage_scope,
                         reason="slot-content plan has no mapped slots for this reuse slide")
            results.append(entry)
            continue
        unknown = expected_ids - comp_ids
        if unknown:
            entry.update(pass_=False, coverage=0.0, threshold=1.0,
                         coverage_scope=coverage_scope,
                         reason=f"slot-content plan references unknown slot ids: {sorted(unknown)}")
            results.append(entry)
            continue
        present = expected_ids & deck_slot_ids
        coverage = len(present) / len(expected_ids)
        threshold = 1.0 if planned is not None else REUSE_MIN
        ok = coverage >= threshold and deck_has_bg
        reasons = []
        if coverage < threshold:
            reasons.append(f"slot-id coverage {coverage:.0%} < {threshold:.0%} "
                           f"({len(present)}/{len(comp_ids)} ids present)")
        if not deck_has_bg:
            reasons.append("no .bg layer found in deck")
        entry.update(pass_=ok, coverage=round(coverage, 3), threshold=threshold,
                     coverage_scope=coverage_scope,
                     reason="; ".join(reasons) if reasons else "fidelity ok")
        results.append(entry)

    return results


# --------------------------------------------------------------------------- #
# Render legibility — a reused component must be READABLE, not merely present.
#
# Matching slot ids proves the deck used the component; it says nothing about
# whether the result can be read off a projector. These checks run on the real
# capture output (export-manifest.json: browser-measured text boxes and object
# bounds, plus the rendered PNGs), so they report what the deck actually looks
# like rather than an estimate of it.
# --------------------------------------------------------------------------- #

# Two text boxes may touch (stacked slots) or nest (a span inside its parent).
# A real collision covers a meaningful share of the smaller box — that is the
# signature of copy that wrapped past its slot and landed on its neighbour.
TEXT_OVERLAP_MIN_RATIO = 0.15
# WCAG AA for large text. Deck copy is >= 19px and mostly bold/display sized,
# and this is a legibility floor, not a full accessibility audit.
CONTRAST_MIN = 3.0
# Only fail contrast when the text sits on a genuinely flat field; busy artwork
# behind a headline is a design choice we do not second-guess here.
FLAT_BACKGROUND_MIN_SHARE = 0.6

# Placement contract. Every measured text item on a slide is one of:
#   "slot"     — a native component slot (the element carries data-slot-id)
#   "chrome"   — slide furniture (title/kicker/footer), data-placement="chrome"
#   "external" — free slide text, and the default for anything undeclared
# Only a native slot may sit on its own component's artwork: the component drew
# that box for that copy, and the slot plan / readability contracts already
# govern what goes in it. Chrome and external text must clear the artwork
# *geometrically*. Raising z-index only decides which of two things in the same
# place is visible, so it hides the defect instead of fixing it.
#
# The tolerance is a rounding allowance, not a budget: any real share of a
# generated caption sitting on a component's ink is the defect this catches.
# Measured against the text item's own box, so it does not scale with the size
# of the artwork behind it.
TEXT_ARTWORK_MAX_RATIO = 0.01
# Alpha above which an overlay pixel counts as painted artwork rather than the
# transparent padding an overlay's bounding box carries around its ink.
ARTWORK_INK_ALPHA = 32
EXEMPT_PLACEMENTS = {"slot"}


def parse_css_color(value: str | None) -> tuple[int, int, int] | None:
    """Parse `rgb()`, `rgba()` and `#rgb`/`#rrggbb` into an RGB triple."""
    if not value:
        return None
    text = value.strip().lower()
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", text)
    if m:
        raw = m.group(1)
        if len(raw) == 3:
            raw = "".join(c * 2 for c in raw)
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    return None


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """WCAG 2.x contrast ratio between two opaque colours."""
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


def _rect(box: dict) -> tuple[float, float, float, float]:
    return (box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"])


def _intersection_area(a, b) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def _contains(outer, inner, tol: float = 1.0) -> bool:
    return (outer[0] <= inner[0] + tol and outer[1] <= inner[1] + tol
            and outer[2] >= inner[2] - tol and outer[3] >= inner[3] - tol)


def find_text_collisions(texts: list[dict]) -> list[dict]:
    """Pairs of measured text boxes that visibly overlap each other.

    Containment is excluded: the capture measures nested elements too, and a
    parent box enclosing its own child is normal DOM structure, not a clash.
    """
    boxes = [t for t in texts if (t.get("text") or "").strip()]
    out: list[dict] = []
    for i, first in enumerate(boxes):
        for second in boxes[i + 1:]:
            a, b = _rect(first), _rect(second)
            area = _intersection_area(a, b)
            if not area or _contains(a, b) or _contains(b, a):
                continue
            smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            ratio = area / smaller if smaller else 0.0
            if ratio >= TEXT_OVERLAP_MIN_RATIO:
                out.append({"ratio": round(ratio, 3),
                            "a": first.get("text", "")[:60],
                            "b": second.get("text", "")[:60],
                            "box_a": {k: first[k] for k in ("x", "y", "w", "h")},
                            "box_b": {k: second[k] for k in ("x", "y", "w", "h")}})
    return out


def text_placement(text: dict) -> str:
    """Which class of the placement contract this measured text item belongs to.

    Undeclared text is `external` on purpose: the checked class is the safe
    default, so a missing attribute can never grant an artwork exemption.
    """
    if text.get("slotId"):
        return "slot"
    declared = str(text.get("placement") or "").strip().lower()
    return declared if declared in {"slot", "chrome", "external"} else "external"


def overlay_ink_ratio(obj: dict, rect, renders_dir: Path | None) -> float | None:
    """Share of `rect` this overlay actually *paints*, or None if unmeasurable.

    An overlay's bounding box is mostly transparent for any artwork that is not
    rectangular — a circle set fills about 78% of its own box, and its top edge
    is a thin arc. Judging placement on bounds alone would therefore reject
    text that clears the ink, so the rendered alpha is the evidence whenever
    the capture PNGs are on disk.
    """
    if renders_dir is None:
        return None
    png = obj.get("png")
    bounds = obj.get("bounds") or {}
    width, height = float(bounds.get("w") or 0), float(bounds.get("h") or 0)
    if not png or width <= 0 or height <= 0:
        return None
    path = renders_dir / png
    if not path.is_file():
        return None
    try:
        from PIL import Image  # noqa: PLC0415 — optional; absent runs fall back to bounds
    except ImportError:
        return None
    try:
        image = Image.open(path).convert("RGBA")
    except OSError:
        return None
    x, y = float(bounds.get("x") or 0), float(bounds.get("y") or 0)
    scale_x, scale_y = image.width / width, image.height / height
    left, top = max(rect[0], x), max(rect[1], y)
    right, bottom = min(rect[2], x + width), min(rect[3], y + height)
    if right <= left or bottom <= top:
        return 0.0
    crop = image.crop((int((left - x) * scale_x), int((top - y) * scale_y),
                       max(int((right - x) * scale_x), int((left - x) * scale_x) + 1),
                       max(int((bottom - y) * scale_y), int((top - y) * scale_y) + 1)))
    alpha = crop.getchannel("A").getcolors(256) or []
    ink = sum(count for count, value in alpha if value > ARTWORK_INK_ALPHA)
    text_px = (rect[2] - rect[0]) * scale_x * (rect[3] - rect[1]) * scale_y
    return min(1.0, ink / text_px) if text_px > 0 else None


def find_text_over_artwork(slide: dict, renders_dir: Path | None = None) -> list[dict]:
    """Non-slot text items placed on top of the component's rendered artwork.

    This is the text-vs-artwork half of legibility. `find_text_collisions` only
    compares text against text, so a caption dropped over a component's tall
    illustration passes every text check while being unreadable on the slide.

    Native slots are skipped: they are the component's own boxes, exempt from
    its own artwork by the placement contract.
    """
    out: list[dict] = []
    for text in slide.get("text", []):
        if not (text.get("text") or "").strip():
            continue
        placement = text_placement(text)
        if placement in EXEMPT_PLACEMENTS:
            continue
        rect = _rect(text)
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if area <= 0:
            continue
        for obj in slide.get("objects", []):
            bounds = obj.get("bounds") or {}
            if not all(k in bounds for k in ("x", "y", "w", "h")):
                continue
            if not _intersection_area(rect, _rect(bounds)):
                continue
            ink = overlay_ink_ratio(obj, rect, renders_dir)
            ratio = ink if ink is not None else _intersection_area(rect, _rect(bounds)) / area
            evidence = "rendered overlay ink" if ink is not None else "declared overlay bounds"
            if ratio < TEXT_ARTWORK_MAX_RATIO:
                continue
            out.append({
                "placement": placement, "object_id": obj.get("id"),
                "ratio": ratio, "evidence": evidence,
                "text": text.get("text", "")[:60],
                "box": {k: text[k] for k in ("x", "y", "w", "h")},
                "overlay": {k: bounds[k] for k in ("x", "y", "w", "h")},
            })
    return out


def off_canvas_objects(slide: dict, canvas_w: float, canvas_h: float) -> list[dict]:
    """Overlay objects whose bounds do not intersect the slide canvas at all."""
    out = []
    for obj in slide.get("objects", []):
        bounds = obj.get("bounds") or {}
        if not all(k in bounds for k in ("x", "y", "w", "h")):
            continue
        r = _rect(bounds)
        if not (r[2] > 0 and r[0] < canvas_w and r[3] > 0 and r[1] < canvas_h):
            out.append({"id": obj.get("id"), "bounds": bounds})
    return out


def _dominant_color(image, box) -> tuple[tuple[int, int, int], float] | None:
    """Most common opaque colour under `box` and the share of pixels it covers."""
    left, top, right, bottom = (max(0, int(box[0])), max(0, int(box[1])),
                                min(image.width, int(box[2])), min(image.height, int(box[3])))
    if right - left < 2 or bottom - top < 2:
        return None
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    counts = crop.getcolors(maxcolors=1 << 16)
    if not counts:
        # More than 65k distinct colours: photographic/gradient artwork, which
        # is never the flat field this check is meant to catch.
        return None
    hits, color = max(counts)
    return color, hits / (crop.width * crop.height)


def _background_image(slide: dict, renders_dir: Path):
    """The rendered slide as the viewer sees it MINUS its text.

    `ref_notext` is exactly that and is preferred. It is deleted once a run
    passes, so rebuild the equivalent from the base layer plus the overlay
    PNGs: the base alone would report the paper colour behind a card and
    wrongly fail white copy that actually sits on rendered artwork.
    """
    try:
        from PIL import Image  # noqa: PLC0415 — optional; absent runs skip contrast
    except ImportError:
        return None, "Pillow not installed"

    ref = (slide.get("qa") or {}).get("ref_notext")
    if ref and (renders_dir / ref).is_file():
        return Image.open(renders_dir / ref).convert("RGB"), None

    base_name = (slide.get("base") or {}).get("png")
    if not base_name or not (renders_dir / base_name).is_file():
        return None, "no rendered background available"
    canvas = Image.open(renders_dir / base_name).convert("RGBA")

    for obj in slide.get("objects", []):
        png, bounds = obj.get("png"), obj.get("bounds") or {}
        if not png or not (renders_dir / png).is_file():
            return None, (f"overlay {obj.get('id')} render missing — cannot "
                          f"reconstruct the background faithfully")
        overlay = Image.open(renders_dir / png).convert("RGBA")
        width, height = int(bounds.get("w", 0)), int(bounds.get("h", 0))
        if width < 1 or height < 1:
            continue
        # paste-into-a-layer rather than alpha_composite: an off-canvas overlay
        # has negative bounds, which alpha_composite rejects outright.
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(overlay.resize((width, height)),
                    (int(bounds.get("x", 0)), int(bounds.get("y", 0))))
        canvas = Image.alpha_composite(canvas, layer)
    return canvas.convert("RGB"), None


def check_render_legibility(manifest: dict, renders_dir: Path | None) -> dict:
    """Fit / contrast / off-canvas verdict over a capture manifest."""
    canvas_w = float(manifest.get("canvasW") or 1920)
    canvas_h = float(manifest.get("canvasH") or 1080)
    failures: list[dict] = []
    notes: list[str] = []

    for slide in manifest.get("slides", []):
        number = slide.get("slide")

        for obj in off_canvas_objects(slide, canvas_w, canvas_h):
            failures.append({
                "check": "off_canvas_object", "slide": number, "id": obj["id"],
                "detail": f"object {obj['id']} bounds {obj['bounds']} lie outside "
                          f"the {canvas_w:.0f}x{canvas_h:.0f} canvas — the component "
                          f"has no viable placement here and is not buildable",
            })

        for hit in find_text_collisions(slide.get("text", [])):
            failures.append({
                "check": "text_collision", "slide": number,
                "detail": f"text overlaps by {hit['ratio']:.0%} of the smaller box: "
                          f"{hit['a']!r} vs {hit['b']!r} — shorten or scale the copy "
                          f"inside its own slot",
                "boxes": [hit["box_a"], hit["box_b"]],
            })

        for hit in find_text_over_artwork(slide, renders_dir):
            failures.append({
                "check": "text_over_artwork", "slide": number,
                "id": hit["object_id"], "placement": hit["placement"],
                "ratio": round(hit["ratio"], 3),
                "detail": f"{hit['placement']} text {hit['text']!r} at {hit['box']} sits on "
                          f"{hit['ratio']:.0%} of its own box over component artwork "
                          f"{hit['object_id']} at {hit['overlay']} ({hit['evidence']}) — move it "
                          f"to a region the component does not paint, shorten it into a native "
                          f"slot, or move it to speaker notes. Do not raise its z-index: that "
                          f"picks a winner between two things in the same place, it does not "
                          f"give the text a place of its own",
                "boxes": [hit["box"], hit["overlay"]],
            })

        if renders_dir is None:
            continue
        image, why = _background_image(slide, renders_dir)
        if image is None:
            notes.append(f"slide {number}: contrast not checked ({why})")
            continue
        scale_x = image.width / canvas_w
        scale_y = image.height / canvas_h
        for text in slide.get("text", []):
            if not (text.get("text") or "").strip():
                continue
            fg = parse_css_color(text.get("color"))
            if fg is None:
                continue
            r = _rect(text)
            sampled = _dominant_color(image, (r[0] * scale_x, r[1] * scale_y,
                                              r[2] * scale_x, r[3] * scale_y))
            if sampled is None:
                continue
            bg, share = sampled
            if share < FLAT_BACKGROUND_MIN_SHARE:
                continue
            ratio = contrast_ratio(fg, bg)
            if ratio < CONTRAST_MIN:
                failures.append({
                    "check": "text_contrast", "slide": number,
                    "detail": f"{text['text'][:40]!r} is {ratio:.2f}:1 against the "
                              f"rendered background rgb{bg} (min {CONTRAST_MIN}:1) — "
                              f"the artwork behind it did not render, or the copy "
                              f"colour does not belong on this component",
                    "ratio": round(ratio, 2),
                })

    return {"valid": not failures, "checked_at": now_iso(),
            "canvas": {"w": canvas_w, "h": canvas_h},
            "thresholds": {"text_overlap_min_ratio": TEXT_OVERLAP_MIN_RATIO,
                           "text_artwork_max_ratio": TEXT_ARTWORK_MAX_RATIO,
                           "contrast_min": CONTRAST_MIN},
            "failures": failures, "notes": notes}


def _run_legibility(manifest_path: Path, renders_dir: Path | None, warn: bool) -> int:
    manifest = load_json(manifest_path)
    renders = renders_dir or manifest_path.parent
    report = check_render_legibility(manifest, renders)
    write_json(renders / "qa" / "render-legibility-report.json", report)
    status = "PASS" if report["valid"] else ("WARN" if warn else "FAIL")
    print(f"render_legibility: {status} ({len(report['failures'])} finding(s))")
    for failure in report["failures"]:
        print(f"  [{failure['check']}] slide {failure['slide']}: {failure['detail']}")
    for note in report["notes"]:
        print(f"  [note] {note}")
    return 0 if (report["valid"] or warn) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate deck slides use their selected components.")
    ap.add_argument("--export-manifest", default=None,
                    help="Run the render-legibility checks on a capture manifest "
                         "(fit/contrast/off-canvas) instead of the slot-id match.")
    ap.add_argument("--renders", default=None,
                    help="Directory holding the manifest's PNGs (default: the "
                         "manifest's own directory).")
    ap.add_argument("--html", required=False)
    ap.add_argument("--selection-report", required=False)
    ap.add_argument("--slot-content-plan", required=False,
                    help="Optional run-local plan; when supplied fidelity requires all planned slots, not 70%% of native slots.")
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--warn", action="store_true",
                    help="Report failures but always exit 0 (rollout mode).")
    args = ap.parse_args()

    if args.export_manifest:
        manifest_path = Path(args.export_manifest).resolve()
        if not manifest_path.exists():
            print(f"ERROR: export manifest not found: {manifest_path}", file=sys.stderr)
            return 1
        return _run_legibility(manifest_path,
                               Path(args.renders).resolve() if args.renders else None,
                               args.warn)

    # The slot-id path must never become opt-out: both inputs stay mandatory
    # there, they are only relaxed for the manifest-driven legibility mode.
    if not args.html or not args.selection_report:
        print("ERROR: pass --html AND --selection-report (slot-id fidelity), "
              "or --export-manifest (render legibility)", file=sys.stderr)
        return 1

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        print(f"ERROR: HTML not found: {html_path}", file=sys.stderr)
        return 1

    deck_html = html_path.read_text(encoding="utf-8", errors="replace")
    report = load_json(args.selection_report)
    registry = load_json(args.registry)

    plan = load_json(args.slot_content_plan) if args.slot_content_plan else None
    results = check_fidelity(deck_html, report, registry, plan)
    failed = [r for r in results if not r["pass_"]]
    valid = not failed

    # A bare `valid: true` reads as "the whole deck was verified" when in fact
    # only `reuse` slides carry a component to check. Publish the ratio so a
    # 1-of-9 run cannot be mistaken for full coverage.
    total_slides = len(list(_decisions(report)))
    coverage = {
        "slides_checked": len(results),
        "slides_total": total_slides,
        "ratio": f"{len(results)}/{total_slides}",
        "unchecked_reason": "text-only slides render approved copy and reuse no component",
    }
    out = {
        "valid": valid,
        "checked_at": now_iso(),
        "html_path": str(html_path),
        "warn_only": args.warn,
        "coverage": coverage,
        "results": results,
    }
    write_json(html_path.parent / "qa" / "component-fidelity-report.json", out)

    status = "PASS" if valid else ("WARN" if args.warn else "FAIL")
    print(f"component_fidelity: {status} (coverage {coverage['ratio']} slides — "
          f"only reuse decisions carry a component)")
    for r in results:
        mark = "OK" if r["pass_"] else "FAIL"
        cov = f" cov={r['coverage']:.0%}" if r.get("coverage") is not None else ""
        print(f"  [{mark}] {r['request_id']} {r['item_id']} ({r['action']}){cov}: {r['reason']}")

    if valid or args.warn:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
