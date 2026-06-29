#!/usr/bin/env python3
"""Unit tests for the slide-pipeline gate scripts.

Covers the highest-consequence, previously-untested paths:
  - cleanup_run: deck.html + .pptx survive; intermediates are removed.
  - score_visual_items: 65/75 decision thresholds + extraction recommendation.
  - validate_selection_report: equal-score plausibility, provenance, T1 shape-lock.
  - scaffold_slide_from_component: slots preserved, no base64, .bg placeholder.
  - validate_component_fidelity: slot-id coverage pass/fail.
  - read_text_slots: slim projection shape.

Run directly (`python3 test_gates.py`) or under pytest. No network, no install.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import cleanup_run
import score_visual_items as svi
import validate_selection_report as vsr
import scaffold_slide_from_component as scaffold
import validate_component_fidelity as fidelity
import read_text_slots

REGISTRY = SCRIPTS.parent / "registries" / "visual-library.json"

# A real template item with positioned slots (verified to have .slot divs).
ITEM_WITH_SLOTS = "sun.interview-workshop-sunriser.04-mindset"


# --------------------------------------------------------------------------- #
# cleanup_run
# --------------------------------------------------------------------------- #
def test_cleanup_keeps_deck_and_pptx() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        (run / "deck.html").write_text("<html></html>")
        (run / "out.pptx").write_bytes(b"PK\x03\x04fake")
        (run / "analysis").mkdir()
        (run / "analysis" / "selection-report.json").write_text("{}")
        (run / "slide-1-bg.png").write_bytes(b"png")
        (run / "parity").mkdir()
        (run / "parity" / "x.png").write_bytes(b"png")

        removed = cleanup_run.cleanup(run, dry_run=False)

        assert (run / "deck.html").exists(), "deck.html must survive cleanup"
        assert (run / "out.pptx").exists(), ".pptx must survive cleanup"
        assert (run / "analysis" / "selection-report.json").exists(), "analysis/ must survive"
        assert not (run / "slide-1-bg.png").exists(), "intermediate png must be removed"
        assert not (run / "parity").exists(), "parity/ dir must be removed"
        assert any("parity" in r for r in removed)


# --------------------------------------------------------------------------- #
# score_visual_items — decision thresholds
# --------------------------------------------------------------------------- #
def _req() -> dict:
    return {"intent": ["timeline"], "tags": [], "content_structure": ["a"],
            "density": "medium", "brand": "sun", "required_exports": []}


def _item(**over) -> dict:
    base = {"id": "sun.set.x", "status": "published", "intent": ["timeline"],
            "tags": [], "content_structure": ["a"], "density": "any",
            "brand": None, "limitations": []}
    base.update(over)
    return base


def test_score_perfect_match_is_reuse() -> None:
    dec, _ = svi.score_request(_req(), [_item()], svi.WEIGHTS, None)
    assert dec["action"] == "reuse", dec
    assert dec["extraction_recommended"] is False


def test_score_mid_band_is_adapt_local() -> None:
    # semantic 35 + structure 0 + density 4 + brand 10 + export 15 + access 10 = 74
    item = _item(content_structure=[], density="fixed")
    dec, _ = svi.score_request(_req(), [item], svi.WEIGHTS, None)
    assert 65 <= dec["score"] < 75, dec
    assert dec["action"] == "adapt-local", dec


def test_score_below_floor_is_custom_local_with_extraction() -> None:
    # drop brand match too -> 64 -> custom-local + extraction recommended
    item = _item(content_structure=[], density="fixed", brand="other")
    dec, _ = svi.score_request(_req(), [item], svi.WEIGHTS, None)
    assert dec["score"] < 65, dec
    assert dec["action"] == "custom-local", dec
    assert dec["extraction_recommended"] is True, "weak match must recommend extraction"


# --------------------------------------------------------------------------- #
# validate_selection_report
# --------------------------------------------------------------------------- #
def _single_report(item_id="sun.interview-workshop-sunriser.02-timeline", score=80.0,
                   action="reuse", scores=(80.0, 80.0)) -> dict:
    crit = {k: 1.0 for k in vsr.REQUIRED_CRITERIA}
    return {
        "request_id": "s1",
        "generated_at": "x",
        "generated_by": "score_visual_items.py",
        "decision": {"action": action, "item_id": item_id, "score": score, "reason": "r"},
        "candidates": [{"item_id": f"c{i}", "eligible": True, "score": s, "criteria": crit}
                       for i, s in enumerate(scores)],
    }


def test_equal_scores_are_plausible() -> None:
    checks, errors, warnings = [], [], []
    vsr._validate_single(_single_report(scores=(48.0, 48.0)), checks, errors, warnings, errors.append)
    plaus = next(c for c in checks if c["name"] == "score_plausibility")
    assert plaus["pass"] is True, "two equal scores must NOT fail plausibility"


def test_eligible_all_zero_still_fails() -> None:
    checks, errors, warnings = [], [], []
    vsr._validate_single(_single_report(scores=(0.0, 0.0)), checks, errors, warnings, errors.append)
    plaus = next(c for c in checks if c["name"] == "score_plausibility")
    assert plaus["pass"] is False, "eligible items all scoring 0 must fail"


def test_shape_lock_matches_and_mismatches() -> None:
    reg_tokens = vsr._registry_tokens(read_text_slots.load_json(REGISTRY))
    rep = _single_report(item_id="sun.interview-workshop-sunriser.02-timeline")
    # match: timeline shape -> timeline item
    errs, _ = vsr._validate_shape_lock(rep, False, {"s1": "timeline"}, reg_tokens, strict_shape=False)
    assert not errs, f"timeline->timeline should pass: {errs}"
    # mismatch: cover shape -> timeline item
    errs, _ = vsr._validate_shape_lock(rep, False, {"s1": "cover"}, reg_tokens, strict_shape=False)
    assert errs, "cover shape locked to a timeline item must fail"


def test_missing_shape_warns_unless_strict() -> None:
    reg_tokens = vsr._registry_tokens(read_text_slots.load_json(REGISTRY))
    rep = _single_report(item_id="sun.interview-workshop-sunriser.02-timeline")
    errs, warns = vsr._validate_shape_lock(rep, False, {"s1": None}, reg_tokens, strict_shape=False)
    assert not errs and warns, "missing shape is a warning by default"
    errs, warns = vsr._validate_shape_lock(rep, False, {"s1": None}, reg_tokens, strict_shape=True)
    assert errs and not warns, "missing shape is an error under --strict-shape"


# --------------------------------------------------------------------------- #
# scaffold_slide_from_component
# --------------------------------------------------------------------------- #
def test_scaffold_preserves_slots_no_base64() -> None:
    preview = scaffold._preview_path(ITEM_WITH_SLOTS, str(REGISTRY))
    slots = scaffold._extract_slots(preview.read_text(encoding="utf-8", errors="replace"))
    assert slots, "expected positioned slots in this component"
    frag = scaffold.build_scaffold(ITEM_WITH_SLOTS, slots)
    assert frag.count("data-slot-id=") >= len(slots), "every slot id must survive"
    assert "base64" not in frag, "scaffold must NOT embed the raster SVG"
    assert 'class="bg"' in frag, "scaffold must include a .bg placeholder"


def test_scaffold_rejects_compact_registry() -> None:
    # A registry whose items lack `paths` (the compact shape) must be rejected
    # with a clear error rather than silently producing nothing.
    import json
    with tempfile.TemporaryDirectory() as tmp:
        compact = Path(tmp) / "compact.json"
        compact.write_text(json.dumps({"items": [{"id": ITEM_WITH_SLOTS}]}))
        try:
            scaffold._preview_path(ITEM_WITH_SLOTS, str(compact))
        except SystemExit as exc:
            assert "paths.preview" in str(exc) or "full" in str(exc).lower()
        else:
            raise AssertionError("registry without paths must be rejected")


# --------------------------------------------------------------------------- #
# validate_component_fidelity
# --------------------------------------------------------------------------- #
def _registry_dict() -> dict:
    return read_text_slots.load_json(REGISTRY)


def test_fidelity_pass_and_fail() -> None:
    reg = _registry_dict()
    preview = scaffold._preview_path(ITEM_WITH_SLOTS, str(REGISTRY))
    slots = scaffold._extract_slots(preview.read_text(encoding="utf-8", errors="replace"))
    deck_ok = scaffold.build_scaffold(ITEM_WITH_SLOTS, slots)  # full coverage + .bg
    report = {"slides": [{"request_id": "s1",
                          "decision": {"action": "reuse", "item_id": ITEM_WITH_SLOTS}}]}

    res = fidelity.check_fidelity(deck_ok, report, reg)
    assert res and res[0]["pass_"] is True, res

    res = fidelity.check_fidelity("<html>nothing</html>", report, reg)
    assert res and res[0]["pass_"] is False, "deck with no slots/bg must fail fidelity"


# --------------------------------------------------------------------------- #
# read_text_slots
# --------------------------------------------------------------------------- #
def test_read_text_slots_projection() -> None:
    # Resolve the slots fixture from the registry (not a hardcoded path) so a
    # pruned/renamed item can never leave this test bound to a ghost folder —
    # the exact failure mode that made guideline-board-layouts break it.
    registry = read_text_slots.load_json(REGISTRY)
    entry = next(i for i in registry["items"] if i["id"] == ITEM_WITH_SLOTS)
    slots_path = SCRIPTS.parents[1] / entry["paths"]["text_slots"]
    data = read_text_slots.load_json(slots_path)
    slim = read_text_slots.project(data["slots"], with_typography=False)
    assert len(slim) == len(data["slots"])
    assert set(slim[0].keys()) == set(read_text_slots.SLIM_FIELDS)


# --------------------------------------------------------------------------- #
# crop_svg_region
# --------------------------------------------------------------------------- #
import json as _json
import crop_svg_region as crop
import validate_text_slots as vts


def _crop_fixture(tmp: Path, region: dict) -> Path:
    item = tmp / "items" / "metric-card"
    (item / "artifact").mkdir(parents=True)
    (item / "artifact" / "visual.svg").write_text(
        '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 1000 600" width="1000" height="600">'
        '<defs><clipPath id="c1"><rect width="1000" height="600"/></clipPath></defs>'
        '<rect x="500" y="60" width="400" height="240" fill="#f60"/></svg>',
        encoding="utf-8",
    )
    (item / "artifact" / "text-slots.json").write_text(_json.dumps({
        "slots": [
            {"id": "in", "bounds": {"x": 0.55, "y": 0.12, "width": 0.30, "height": 0.10}, "z_order": 1},
            {"id": "out", "bounds": {"x": 0.05, "y": 0.80, "width": 0.10, "height": 0.05}, "z_order": 2},
        ],
        "source": {"view_box": [0, 0, 1000, 600], "canvas_width": 1000, "canvas_height": 600},
    }), encoding="utf-8")
    (item / "mapping.json").write_text(_json.dumps(
        {"item_id": "metric-card", "type": "component", "source": {"region": region}}), encoding="utf-8")
    return item


def test_crop_region_rewrites_viewbox_and_slots() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_fixture(Path(tmp), {"x": 0.5, "y": 0.1, "width": 0.4, "height": 0.4, "unit": "normalized"})
        res = crop.crop_item(item)
        assert res["status"] == "cropped" and res["slots_dropped"] == 1, res
        svg = (item / "artifact" / "visual.svg").read_text()
        assert 'viewBox="0 0 400 240"' in svg and "translate(-500.0 -60.0)" in svg, svg
        slots = crop.load_json(item / "artifact" / "text-slots.json")
        assert [s["id"] for s in slots["slots"]] == ["in"], "out-of-region slot must drop"
        b = slots["slots"][0]["bounds"]
        assert abs(b["x"] - 0.125) < 1e-6 and abs(b["width"] - 0.75) < 1e-6, b
        assert slots["source"]["region_crop"]["crop_window"] == [500.0, 60.0, 400.0, 240.0]


def test_crop_region_idempotent_and_full_page_noop() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_fixture(Path(tmp), {"x": 0.5, "y": 0.1, "width": 0.4, "height": 0.4, "unit": "normalized"})
        crop.crop_item(item)
        assert crop.crop_item(item)["status"] == "already-cropped"
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_fixture(Path(tmp), {"x": 0, "y": 0, "width": 1, "height": 1, "unit": "normalized"})
        assert crop.crop_item(item)["status"] == "full-page-noop"


def test_crop_region_honors_absolute_units() -> None:
    # On the 1000x600 fixture page, a pt region must crop identically to the
    # equivalent normalized region (regression: pt was treated as a 0-1 fraction
    # and silently produced a ~1000x-too-large viewBox with every slot dropped).
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_fixture(Path(tmp), {"x": 500, "y": 60, "width": 400, "height": 240, "unit": "pt"})
        res = crop.crop_item(item)
        assert res["status"] == "cropped" and res["slots_dropped"] == 1, res
        svg = (item / "artifact" / "visual.svg").read_text()
        assert 'viewBox="0 0 400 240"' in svg, svg
        slots = crop.load_json(item / "artifact" / "text-slots.json")
        assert slots["source"]["region_crop"]["crop_window"] == [500.0, 60.0, 400.0, 240.0]
    # an unsupported unit must fail loud, never silently mis-scale.
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_fixture(Path(tmp), {"x": 1, "y": 1, "width": 1, "height": 1, "unit": "furlongs"})
        try:
            crop.crop_item(item)
        except SystemExit:
            pass
        else:
            raise AssertionError("unknown region unit must raise SystemExit")


def test_validate_excludes_cropped_out_source_text() -> None:
    # After a region crop, source text outside the region has no slot. The
    # full-page source-with-text.svg must NOT report it as unmapped, because
    # crop_svg_region.py recorded it in source.region_crop.dropped_source_refs.
    def _build(item: Path, with_marker: bool) -> None:
        (item / "artifact").mkdir(parents=True)
        (item / "evidence").mkdir(parents=True)
        (item / "artifact" / "visual.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect width="100" height="100"/></svg>', encoding="utf-8")
        (item / "evidence" / "source-with-text.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><text>IN</text>'
            '<text>OUT</text></svg>', encoding="utf-8")
        source = {}
        if with_marker:
            source["region_crop"] = {"dropped_source_refs": [
                {"text_index": 1, "tspan_index": 0, "character_range": [0, 3]}]}
        (item / "artifact" / "text-slots.json").write_text(_json.dumps({
            "schema_version": 1,
            "slots": [{"id": "s1", "editable": True, "allow_empty": True,
                       "bounds": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
                       "source_refs": [{"text_index": 0, "tspan_index": 0,
                                        "character_range": [0, 2]}]}],
            "source": source,
        }), encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "card"
        _build(item, with_marker=True)
        assert vts.validate(item) == [], "cropped-out text must be excluded"
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "card"
        _build(item, with_marker=False)
        errs = vts.validate(item)
        assert any("Unmapped source text" in e for e in errs), errs


# --------------------------------------------------------------------------- #
# crop_svg_region — off-canvas <image> pruning
# --------------------------------------------------------------------------- #
import xml.etree.ElementTree as _ET

_SVG = "{http://www.w3.org/2000/svg}"


def _crop_image_fixture(tmp: Path, body: str, defs: str = "") -> Path:
    # 1000x600 page; region -> crop window page-space [500, 60, 400, 240],
    # i.e. the page-space rectangle x:500..900, y:60..300.
    item = tmp / "items" / "img-card"
    (item / "artifact").mkdir(parents=True)
    (item / "artifact" / "visual.svg").write_text(
        '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 1000 600" width="1000" height="600">'
        f'<defs>{defs}</defs>{body}</svg>', encoding="utf-8")
    (item / "artifact" / "text-slots.json").write_text(_json.dumps({
        "slots": [],
        "source": {"view_box": [0, 0, 1000, 600], "canvas_width": 1000, "canvas_height": 600},
    }), encoding="utf-8")
    (item / "mapping.json").write_text(_json.dumps(
        {"item_id": "img-card", "type": "component",
         "source": {"region": {"x": 0.5, "y": 0.1, "width": 0.4, "height": 0.4, "unit": "normalized"}}}),
        encoding="utf-8")
    return item


def _img_ids(item: Path) -> list[str]:
    root = _ET.parse(item / "artifact" / "visual.svg").getroot()
    return sorted(im.get("id") for im in root.iter(_SVG + "image"))


def test_crop_prunes_offcanvas_body_images() -> None:
    # inside the window -> keep; straddling the edge (partial overlap) -> keep;
    # wholly below the window -> drop.
    body = (
        '<image id="inside" x="550" y="80" width="100" height="50" href="#a"/>'
        '<image id="straddle" x="480" y="80" width="60" height="50" href="#b"/>'
        '<image id="outside" x="50" y="400" width="80" height="40" href="#c"/>'
    )
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_image_fixture(Path(tmp), body)
        res = crop.crop_item(item)
        assert res["images_pruned"] == 1, res
        assert _img_ids(item) == ["inside", "straddle"], _img_ids(item)


def test_crop_keeps_defs_images() -> None:
    # an off-canvas image painted indirectly via <defs> is never pruned.
    defs = '<image id="d1" x="50" y="400" width="80" height="40" href="#d"/>'
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_image_fixture(Path(tmp), "", defs)
        res = crop.crop_item(item)
        assert res["images_pruned"] == 0, res
        assert _img_ids(item) == ["d1"], _img_ids(item)


def test_crop_failsafe_unparseable_transform() -> None:
    # an off-canvas body image under a non-affine transform (rotate) is KEPT —
    # we never drop an element we cannot fully reason about.
    body = ('<g transform="rotate(45)">'
            '<image id="rot" x="50" y="400" width="80" height="40" href="#e"/></g>')
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_image_fixture(Path(tmp), body)
        res = crop.crop_item(item)
        assert res["images_pruned"] == 0, res
        assert "rot" in _img_ids(item), _img_ids(item)


def test_crop_affine_transform_honored() -> None:
    # 'moved-in' is off-canvas by raw coords but a translate brings it into the
    # window -> kept. 'moved-out' is on-canvas raw but a translate pushes it
    # wholly below the window -> dropped.
    body = (
        '<g transform="translate(600 0)">'
        '<image id="moved-in" x="0" y="80" width="100" height="50" href="#f"/></g>'
        '<g transform="translate(0 400)">'
        '<image id="moved-out" x="550" y="80" width="100" height="50" href="#g"/></g>'
    )
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_image_fixture(Path(tmp), body)
        res = crop.crop_item(item)
        assert res["images_pruned"] == 1, res
        ids = _img_ids(item)
        assert "moved-in" in ids and "moved-out" not in ids, ids


def test_crop_also_crops_evidence_svg() -> None:
    # the full-page evidence SVG is cropped to the same window so it stops
    # referencing off-canvas images; its <text> is preserved (validate relies on
    # the text enumeration), and the off-canvas image ref is dropped.
    with tempfile.TemporaryDirectory() as tmp:
        item = _crop_image_fixture(
            Path(tmp), '<image id="vis" x="550" y="80" width="100" height="50" href="#a"/>')
        ev = item / "evidence"
        ev.mkdir(parents=True)
        (ev / "source-with-text.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
            '<image id="ev-in" x="550" y="80" width="100" height="50" href="#a"/>'
            '<image id="ev-out" x="50" y="400" width="80" height="40" href="#c"/>'
            '<text>LABEL</text></svg>', encoding="utf-8")
        res = crop.crop_item(item)
        assert res["evidence_images_pruned"] == 1, res
        root = _ET.parse(ev / "source-with-text.svg").getroot()
        assert root.get("viewBox") == "0 0 400 240", root.get("viewBox")
        ids = sorted(im.get("id") for im in root.iter(_SVG + "image"))
        assert ids == ["ev-in"], ids
        assert len(list(root.iter(_SVG + "text"))) == 1, "evidence text must survive"


def test_gc_removes_unreferenced_assets() -> None:
    import externalize_svg_images as ext
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "card"
        assets = item / "artifact" / "assets"
        assets.mkdir(parents=True)
        (item / "artifact" / "visual.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<image href="assets/keep.png"/></svg>', encoding="utf-8")
        (assets / "keep.png").write_bytes(b"k")
        (assets / "orphan.png").write_bytes(b"o")
        removed = ext.gc_unreferenced_assets(ext.item_svg_specs(item), assets)
        assert removed == 1, removed
        assert sorted(p.name for p in assets.iterdir()) == ["keep.png"]


def test_catalog_preview_skips_fullpage_reference_when_cropped() -> None:
    # A cropped component must NOT surface the whole-page reference.png as a
    # preview (that is what made the Draft show the full slide). The cropped
    # source-with-text.svg is the preview instead.
    import build_component_catalog as bcc
    def _build(item: Path, cropped: bool) -> None:
        (item / "artifact").mkdir(parents=True)
        (item / "evidence").mkdir(parents=True)
        src = {"region_crop": {"crop_window": [0, 0, 100, 50]}} if cropped else {}
        (item / "artifact" / "text-slots.json").write_text(
            _json.dumps({"slots": [], "source": src}), encoding="utf-8")
        (item / "evidence" / "source-with-text.svg").write_text("<svg/>", encoding="utf-8")
        (item / "evidence" / "reference.png").write_bytes(b"png")
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "c"
        _build(item, cropped=True)
        labels = [im["label"] for im in bcc.collect_images(item)]
        assert "Reference" not in labels and "Source with text" in labels, labels
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "c"
        _build(item, cropped=False)
        labels = [im["label"] for im in bcc.collect_images(item)]
        assert "Reference" in labels, "full-page items still surface reference.png"


def test_catalog_rel_uses_web_safe_posix_paths() -> None:
    import build_component_catalog as bcc
    path = bcc.PROJECT_ROOT / "slide-system" / "library" / "x" / "visual.svg"
    assert bcc.rel(path) == "slide-system/library/x/visual.svg"


# --------------------------------------------------------------------------- #
# build_registry
# --------------------------------------------------------------------------- #
import build_registry as breg


def test_build_registry_projection_and_compact_keys() -> None:
    items = [{"id": "sun.x.y", "type": "card", "intent": ["a"], "tags": ["t"],
              "status": "published", "name": "drop me", "paths": {"x": 1}}]
    compact = breg.project_compact(items)
    row = compact["items"][0]
    # only the compact keys survive; heavy/identifying extras are dropped.
    assert set(row.keys()) == set(breg.COMPACT_KEYS)
    assert "name" not in row and "paths" not in row
    assert row["id"] == "sun.x.y" and row["intent"] == ["a"]


def test_build_registry_live_is_clean() -> None:
    # the real registry must have no dangling entries (every artifact exists).
    reg = breg.load_json(breg.REGISTRY)
    dangling = [i["id"] for i in reg["items"]
                if i.get("paths", {}).get("artifact")
                and not breg.resolve_repo_path(i["paths"]["artifact"]).exists()]
    assert dangling == [], f"dangling registry entries: {dangling}"


# --------------------------------------------------------------------------- #
# classify_page_components (pure-logic paths — no browser/Chromium needed)
# --------------------------------------------------------------------------- #
import classify_page_components as cpc
import extract_editable_text_slots as eets


def test_split_runs_breaks_on_large_forward_gap() -> None:
    # Three column headings concatenated in one tspan, separated by large x-gaps
    # (no space chars) must split into three runs — the bug that merged
    # STRATEGIST/DRIVER/COACH into one slot.
    text = "ABCDEFGHI"
    xs = [0, 10, 20, 200, 210, 220, 400, 410, 420]   # 3 clusters, gap 180 >> advance 10
    runs = eets.split_runs(text, xs, font_size=20)
    assert [r[0] for r in runs] == ["ABC", "DEF", "GHI"], runs


def test_split_runs_keeps_tight_text_together() -> None:
    # Ordinary evenly-spaced glyphs (a single word) are NOT split.
    text = "ABCDEF"
    xs = [0, 10, 20, 30, 40, 50]
    runs = eets.split_runs(text, xs, font_size=20)
    assert [r[0] for r in runs] == ["ABCDEF"], runs


def test_split_runs_still_breaks_on_line_wrap() -> None:
    # A backward x-jump (x resets left) is a line wrap and still splits.
    text = "ABCDE"
    xs = [0, 10, 20, 2, 12]
    runs = eets.split_runs(text, xs, font_size=20)
    assert [r[0] for r in runs] == ["ABC", "DE"], runs

_SVGNS = "http://www.w3.org/2000/svg"


def _measured(width: float, height: float, groups: list[dict]) -> dict:
    out = []
    for i, g in enumerate(groups):
        out.append({"index": i, "x": g["x"], "y": g["y"], "w": g["w"], "h": g["h"],
                    "children": g.get("children", [])})
    return {"width": width, "height": height, "groups": out}


def test_classify_drops_offcanvas_leaves() -> None:
    # A crop leaves vector junk below the viewBox; those leaves must be dropped.
    m = _measured(1000, 400, [
        {"x": 10, "y": 10, "w": 100, "h": 100},      # on-canvas
        {"x": 10, "y": 900, "w": 100, "h": 100},     # off-canvas (y >> 400)
    ])
    leaves = cpc._leaf_boxes(m, window_pad=20)
    assert len(leaves) == 1 and leaves[0]["y"] == 10, leaves


def test_classify_tall_card_absorbs_icon() -> None:
    # A portrait card filling 96% of canvas height (but narrow) must NOT be
    # treated as a bridging "bar": it has to absorb its own icon into one
    # cluster. This is the bug that left icons orphaned.
    H = 500
    m = _measured(1000, H, [
        {"x": 8, "y": 10, "w": 380, "h": 480},        # tall narrow card
        {"x": 300, "y": 400, "w": 80, "h": 80},       # icon inside the card
    ])
    leaves = cpc._leaf_boxes(m, window_pad=20)
    clusters = cpc._cluster_spatial(leaves, merge_gap=6, canvas_w=1000, canvas_h=H)
    assert len(clusters) == 1, [len(c) for c in clusters]


def test_classify_divider_does_not_bridge() -> None:
    # A thin full-width rule (extreme aspect ratio) must stay its own singleton
    # so it does not glue two separated cards into one blob.
    m = _measured(1000, 500, [
        {"x": 8, "y": 10, "w": 380, "h": 480},        # card A
        {"x": 612, "y": 10, "w": 380, "h": 480},      # card B (x-disjoint)
        {"x": 5, "y": 240, "w": 990, "h": 8},         # full-width divider
    ])
    leaves = cpc._leaf_boxes(m, window_pad=20)
    clusters = cpc._cluster_spatial(leaves, merge_gap=6, canvas_w=1000, canvas_h=500)
    # 2 cards + 1 divider singleton == 3 clusters; cards never merge.
    assert len(clusters) == 3, [cpc._bounds(c) for c in clusters]


def test_classify_dedups_same_shape_different_color() -> None:
    # Three congruent instances => one shape class (identical AND same-shape-
    # different-color both collapse). Slightly different size => its own class.
    inst = [{"w": 380, "h": 480}, {"w": 378, "h": 476}, {"w": 381, "h": 479},
            {"w": 120, "h": 120}]
    classes = cpc._shape_classes(inst, tol=0.14)
    sizes = sorted(len(c) for c in classes)
    assert sizes == [1, 3], sizes


def test_classify_groups_adjacent_same_shape_run() -> None:
    # A row of 3 same-shape instances with small gutters is ONE proximity group
    # (the whole run, rendered with each member's variant preserved).
    inst = [{"x": 0, "y": 0, "w": 100, "h": 200},
            {"x": 120, "y": 0, "w": 100, "h": 200},   # gutter 20 < 0.6*100
            {"x": 240, "y": 0, "w": 100, "h": 200}]
    groups = cpc._proximity_groups(inst, [0, 1, 2], gap_frac=0.6)
    assert len(groups) == 1 and sorted(groups[0]) == [0, 1, 2], groups


def test_classify_splits_distant_same_shape() -> None:
    # Same-shape instances sitting far apart are NOT one group — each is its own
    # standalone item.
    inst = [{"x": 0, "y": 0, "w": 100, "h": 100},
            {"x": 900, "y": 0, "w": 100, "h": 100}]   # gap 800 >> 0.6*100
    groups = cpc._proximity_groups(inst, [0, 1], gap_frac=0.6)
    assert len(groups) == 2, groups


def test_classify_keeps_different_shapes_separate() -> None:
    # Two adjacent boxes of clearly different shape land in different shape-
    # classes, so grouping (which is within-class) keeps them as 2 groups even
    # though they sit side by side.
    inst = [{"x": 0, "y": 0, "w": 100, "h": 200},     # tall
            {"x": 110, "y": 0, "w": 300, "h": 80}]    # wide — different shape
    classes = cpc._shape_classes(inst, tol=0.14)
    groups: list = []
    for class_idxs in classes:
        groups += cpc._proximity_groups(inst, class_idxs, gap_frac=0.6)
    assert len(groups) == 2, (classes, groups)


def test_child_count_mismatch_detects() -> None:
    # A group whose ElementTree child count differs from the measured child
    # count is flagged (its measured indices would copy wrong nodes).
    svg = (f'<svg xmlns="{_SVGNS}"><g><rect/><rect/></g><g><rect/></g></svg>')
    root = _ET.fromstring(svg)
    groups = list(root)  # two <g>
    measured = [{"children": [{}, {}]}, {"children": [{}, {}]}]  # 2nd says 2, ET has 1
    bad = cpc._child_count_mismatch(groups, measured)
    assert bad == [(1, 1, 2)], bad


def test_child_count_mismatch_clean() -> None:
    svg = (f'<svg xmlns="{_SVGNS}"><g><rect/><rect/></g><g><rect/></g></svg>')
    root = _ET.fromstring(svg)
    groups = list(root)
    measured = [{"children": [{}, {}]}, {"children": [{}]}]
    assert cpc._child_count_mismatch(groups, measured) == []


# Exact-equality distance for the dedup tests: 0 when equal (<= any threshold),
# large otherwise. The real call injects perceptual-signature distance instead.
_EQ_DIST = lambda a, b: 0.0 if a == b else 999.0


def test_collapse_duplicates_keeps_first_and_counts() -> None:
    # Identical items collapse into the first; counts track how many.
    kept, counts = cpc._collapse_duplicates(["a", "b", "a", "a", "c"], _EQ_DIST, 0.0)
    assert kept == [0, 1, 4] and counts == [3, 1, 1], (kept, counts)


def test_collapse_duplicates_none_never_merges() -> None:
    # A failed render (None) is always kept on its own — never silently
    # dropped or merged with another None.
    kept, counts = cpc._collapse_duplicates([None, "a", None, "a"], _EQ_DIST, 0.0)
    assert kept == [0, 1, 2] and counts == [1, 2, 1], (kept, counts)


def test_collapse_duplicates_merges_within_threshold() -> None:
    # Distance-based: items within `threshold` collapse (near-identical →
    # "tương tự"), items beyond it stay distinct (different color/icon).
    dist = lambda a, b: abs(a - b)
    # 10 and 11 are within 3 of each other; 50 is far → kept separate.
    kept, counts = cpc._collapse_duplicates([10, 11, 50, 10], dist, 3.0)
    assert kept == [0, 2] and counts == [3, 1], (kept, counts)


def test_split_on_gutter_separates_bridged_components() -> None:
    # Two big leaves with a 30px gutter, bridged by one tiny leaf sitting in the
    # gap (the card↔photo failure). The split ignores the tiny leaf when finding
    # the gutter and assigns it to the nearer side → two components.
    members = [
        {"x": 0, "y": 0, "w": 100, "h": 100},     # big left
        {"x": 130, "y": 0, "w": 100, "h": 100},   # big right (30px gutter)
        {"x": 110, "y": 45, "w": 12, "h": 12},    # tiny bridge in the gutter
    ]
    parts = cpc._split_on_gutter(members, min_gutter_px=16.0)
    assert len(parts) == 2, parts
    assert {len(p) for p in parts} == {1, 2}, parts  # tiny joins one side


def test_split_on_gutter_keeps_single_component_intact() -> None:
    # A genuine component (parts within a small gap, < threshold) is NOT split.
    members = [
        {"x": 0, "y": 0, "w": 100, "h": 100},
        {"x": 108, "y": 0, "w": 100, "h": 100},   # 8px gap < 16px threshold
    ]
    assert cpc._split_on_gutter(members, min_gutter_px=16.0) == [members]


def test_heading_picks_largest_font_with_subtitle() -> None:
    # Heading = largest font tier; a short second tier (subtitle) is appended,
    # read top-to-bottom.
    slots = [{"text": "Level 1", "x": 0.1, "y": 0.10, "w": 0.1, "h": 0.02, "size": 53.0},
             {"text": "Spicy", "x": 0.1, "y": 0.14, "w": 0.1, "h": 0.02, "size": 42.0},
             {"text": "Autocomplete", "x": 0.1, "y": 0.16, "w": 0.1, "h": 0.02, "size": 42.0},
             {"text": "a long body copy line here", "x": 0.1, "y": 0.30, "w": 0.1, "h": 0.02, "size": 18.0}]
    assert cpc._heading(slots) == "Level 1 Spicy Autocomplete", cpc._heading(slots)


def test_heading_drops_paragraph_tier() -> None:
    # When the second font tier is a multi-slot paragraph (>3 slots), it is NOT
    # appended — only the heading survives.
    slots = [{"text": "TRANSLATOR", "x": 0.1, "y": 0.10, "w": 0.1, "h": 0.02, "size": 38.0}]
    slots += [{"text": f"w{i}", "x": 0.1, "y": 0.2 + i * 0.01, "w": 0.05, "h": 0.01, "size": 20.0}
              for i in range(5)]
    assert cpc._heading(slots) == "TRANSLATOR", cpc._heading(slots)


def test_group_title_common_prefix_and_join() -> None:
    assert cpc._group_title(["Level 1 X", "Level 2 Y", "Level 3 Z"]) == "Level cards"
    # No shared prefix → join the heading-like (short, capitalized) titles only.
    assert cpc._group_title(["TRANSLATOR", "a long body copy fallback here", "DRIVER"]) \
        == "TRANSLATOR / DRIVER"


def test_tags_from_dedups_and_skips_stopwords() -> None:
    tags = cpc._tags_from(["Level 1 Spicy", "Level 2 Coding", "the and Spicy"])
    assert tags == ["Level", "1", "Spicy", "2", "Coding"], tags


def test_slots_in_uses_center_point() -> None:
    slots = [{"text": "in", "x": 0.10, "y": 0.10, "w": 0.05, "h": 0.05, "size": 10},
             {"text": "out", "x": 0.80, "y": 0.80, "w": 0.05, "h": 0.05, "size": 10}]
    got = cpc._slots_in(slots, 0, 0, 500, 500, 1000, 1000)  # px box covers left-top quadrant
    assert [s["text"] for s in got] == ["in"], got


def test_classify_records_dropped_small_with_bounds() -> None:
    # A cluster below the area floor is recorded with its bounds (not just
    # counted), so a genuine small component stays inspectable.
    canvas_w, canvas_h = 1000.0, 1000.0
    area = canvas_w * canvas_h
    clusters = [
        [{"x": 10, "y": 10, "w": 20, "h": 20, "group": 0, "child": None}],   # tiny < 1.5%
        [{"x": 100, "y": 100, "w": 300, "h": 300, "group": 1, "child": None}],
    ]
    dropped = []
    for members in clusters:
        x0, y0, w, h = cpc._bounds(members)
        a = w * h
        if a < 0.015 * area:
            dropped.append({"x": round(x0, 1), "y": round(y0, 1),
                            "w": round(w, 1), "h": round(h, 1),
                            "area_frac": round(a / area, 4)})
    assert len(dropped) == 1
    assert set(dropped[0]) == {"x", "y", "w", "h", "area_frac"}, dropped[0]
    assert dropped[0]["w"] == 20 and dropped[0]["area_frac"] == 0.0004, dropped[0]


def test_classify_excludes_fullbleed_background() -> None:
    # On a full page the background cluster (≈ canvas size) must be routed to
    # background_candidates, NOT emitted as a component class.
    canvas_w, canvas_h = 1000.0, 800.0
    clusters = [
        [{"x": 2, "y": 2, "w": 996, "h": 796, "group": 0, "child": None}],   # bg
        [{"x": 100, "y": 100, "w": 200, "h": 200, "group": 1, "child": None}],
        [{"x": 400, "y": 100, "w": 200, "h": 200, "group": 2, "child": None}],
    ]
    area = canvas_w * canvas_h
    bg, inst, dropped = [], [], 0
    for members in clusters:
        x0, y0, w, h = cpc._bounds(members)
        a = w * h
        if a < 0.015 * area:
            dropped += 1
        elif a >= 0.7 * area:
            bg.append(members)
        else:
            inst.append(members)
    assert len(bg) == 1 and len(inst) == 2, (len(bg), len(inst))


def test_classify_ancestor_transform_and_fragment() -> None:
    # The crop wrapper transform must be captured and re-applied in fragments,
    # else geometry lands off-canvas and the fragment renders blank.
    svg = (f'<svg xmlns="{_SVGNS}" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           'viewBox="0 0 100 100">'
           '<g transform="translate(-440 -440)"><g>'
           '<g inkscape:groupmode="layer">'
           '<g><rect x="450" y="450" width="20" height="20"/></g>'
           '</g></g></g></svg>')
    root = _ET.fromstring(svg)
    groups = cpc.document_groups(root)
    parent_map = {c: p for p in root.iter() for c in p}
    chain = cpc._ancestor_transform(root, parent_map, groups[0])
    assert chain == "translate(-440 -440)", repr(chain)
    members = [{"x": 10, "y": 10, "w": 20, "h": 20, "group": 0, "child": None}]
    frag = cpc._build_fragment(members, groups, [], margin=3,
                               source_dir=Path("."), ancestor_transform=chain)
    blob = _ET.tostring(frag, encoding="unicode")
    assert "translate(-440 -440)" in blob and "rect" in blob, blob


# --------------------------------------------------------------------------- #
# split_icon_sheet — icon-sheet decomposition helpers
# --------------------------------------------------------------------------- #
def test_split_cluster_1d_groups_within_tol() -> None:
    import split_icon_sheet as sis
    # two tight groups (~5 and ~105) separated by a wide gap -> two lines
    lines = sis._cluster_1d([4, 5, 6, 104, 105, 106], tol=20)
    assert len(lines) == 2, lines
    assert abs(lines[0] - 5) < 1 and abs(lines[1] - 105) < 1, lines


def test_split_merge_within_fuses_overlap_keeps_distant() -> None:
    import split_icon_sheet as sis
    # A and B overlap (gap 0); C is far away on x -> {A,B} merged, C separate.
    clusters = [
        {"x": 0, "y": 0, "w": 20, "h": 20, "members": [{"x": 0, "y": 0, "w": 20, "h": 20}]},
        {"x": 18, "y": 2, "w": 20, "h": 20, "members": [{"x": 18, "y": 2, "w": 20, "h": 20}]},
        {"x": 200, "y": 0, "w": 20, "h": 20, "members": [{"x": 200, "y": 0, "w": 20, "h": 20}]},
    ]
    out = sis._merge_within(clusters, gap=10)
    assert len(out) == 2, [(o["x"], o["w"]) for o in out]
    big = max(out, key=lambda o: o["w"])
    assert len(big["members"]) == 2, big


def test_split_per_row_gap_separates_neighbours_fuses_fragments() -> None:
    """The core grid rule: cells in one row split into icons by the gap valley —
    fragments (gap < col_tol) fuse, neighbours (gap >> col_tol) stay separate."""
    import split_icon_sheet as sis
    # row of cells (same y): two fragments of icon A (x=0..20, 25..45, gap 5),
    # then icon B far right (x=120..145, gap 75). col_tol=35 sits in the valley.
    row = [
        {"x": 0, "y": 0, "w": 20, "h": 30},
        {"x": 25, "y": 0, "w": 20, "h": 30},
        {"x": 120, "y": 0, "w": 25, "h": 30},
    ]
    by_cell: dict = {}
    row.sort(key=lambda c: c["x"])
    col, right = 0, None
    for c in row:
        if right is not None and (c["x"] - right) >= 35:
            col += 1
        by_cell.setdefault(col, []).append(c)
        right = max(right if right is not None else c["x"] + c["w"], c["x"] + c["w"])
    assert len(by_cell) == 2, by_cell
    assert len(by_cell[0]) == 2 and len(by_cell[1]) == 1, by_cell


def test_build_catalog_collect_icon_set_parses_and_absent() -> None:
    import build_component_catalog as bcc
    import json as _json
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp)
        # no manifest -> None
        assert bcc.collect_icon_set(item) is None
        icons_dir = item / "artifact" / "icons"
        icons_dir.mkdir(parents=True)
        (icons_dir / "icon-000.svg").write_text("<svg/>")
        (icons_dir / "icon-001.svg").write_text("<svg/>")
        (icons_dir / "icons-manifest.json").write_text(_json.dumps({"icons": [
            {"index": 0, "file": "icon-000.svg", "slug": "bod", "name": "BOD",
             "region": "frequently-used", "row": -1, "col": -1},
            {"index": 1, "file": "icon-001.svg", "slug": "wifi", "name": "wifi",
             "region": "grid", "row": 1, "col": 2},
            {"index": 2, "file": "missing.svg", "slug": "x", "name": "x",
             "region": "grid", "row": 1, "col": 3},
        ]}))
        iset = bcc.collect_icon_set(item)
        assert iset and iset["count"] == 2, iset  # missing file dropped
        slugs = [i["slug"] for i in iset["icons"]]
        assert slugs == ["bod", "wifi"], slugs
        assert iset["icons"][0]["path"].endswith("icon-000.svg")


# --------------------------------------------------------------------------- #
# materialize_groups (classify_page_components + _common hash helpers)
# --------------------------------------------------------------------------- #
import json as _json_stdlib
from _common import normalized_bounds as _normalized_bounds
from _common import region_identity_hash as _region_identity_hash
from _common import semantic_signature_hash as _semantic_signature_hash


def test_group_bounds_to_normalized_region() -> None:
    canvas = {"w": 2938.83, "h": 2623.16}
    gb = {"x": 563.1, "y": 371.4, "w": 1867.5, "h": 586.3}
    region = _normalized_bounds({
        "x": gb["x"] / canvas["w"],
        "y": gb["y"] / canvas["h"],
        "width": gb["w"] / canvas["w"],
        "height": gb["h"] / canvas["h"],
        "unit": "normalized",
    })
    assert region["unit"] == "normalized"
    assert 0.0 < region["x"] < 1.0, region["x"]
    assert 0.0 < region["y"] < 1.0, region["y"]
    assert 0.0 < region["width"] < 1.0, region["width"]
    assert 0.0 < region["height"] < 1.0, region["height"]
    assert abs(region["x"] - 563.1 / 2938.83) < 1e-5
    assert abs(region["width"] - 1867.5 / 2938.83) < 1e-5


def test_materialized_mapping_fields() -> None:
    region = _normalized_bounds({
        "x": 0.19, "y": 0.14, "width": 0.64, "height": 0.22, "unit": "normalized",
    })
    rh = _region_identity_hash("sha_abc", "2", region, ["obj-1"])
    sh = _semantic_signature_hash(["Cover", "intro"])
    assert isinstance(rh, str) and len(rh) == 64, rh
    assert isinstance(sh, str) and len(sh) == 64, sh
    candidate = "sun.component.feature-step-shape-diagrams.g01"
    assert candidate.startswith("sun.component.")
    assert candidate.endswith(".g01")
    rh2 = _region_identity_hash("sha_abc", 2, region, ["obj-1"])
    assert rh == rh2, "int vs str slide_or_page must produce same hash"


def test_carved_slots_within_unit_and_subset() -> None:
    base_slots = [
        {"id": f"s{i}", "bounds": {"x": i * 0.1, "y": 0.1, "width": 0.08, "height": 0.05}}
        for i in range(10)
    ]
    region = {"x": 0.2, "y": 0.05, "width": 0.5, "height": 0.3}
    carved = [
        s for s in base_slots
        if (region["x"] <= s["bounds"]["x"] + s["bounds"]["width"] / 2 <= region["x"] + region["width"]
            and region["y"] <= s["bounds"]["y"] + s["bounds"]["height"] / 2 <= region["y"] + region["height"])
    ]
    assert len(carved) < len(base_slots), "carve should drop some slots"
    assert len(carved) > 0, "carve should keep some slots"
    for s in carved:
        cx = s["bounds"]["x"] + s["bounds"]["width"] / 2
        cy = s["bounds"]["y"] + s["bounds"]["height"] / 2
        assert region["x"] <= cx <= region["x"] + region["width"]
        assert region["y"] <= cy <= region["y"] + region["height"]


# --------------------------------------------------------------------------- #
# scaffold_extraction — ID gating + analysis-dir coexistence
# --------------------------------------------------------------------------- #
import scaffold_extraction as scaffold_ex


def test_scaffold_rejects_docling_draft_ids() -> None:
    # Every placeholder analyze_with_docling.py can mint must be rejected so it
    # can never become a stable identity without a human rename.
    for bad in ("picture-p1-1", "figure-p2-3", "table-p10-1", "chart-px-1",
                "form-p3-2"):
        assert scaffold_ex._DOCLING_DRAFT_ID.match(bad), bad
    # Real semantic names (and the suggested renames) must pass.
    for ok in ("metric-card", "salary-table", "org-chart", "picture-frame",
               "table-of-contents"):
        assert not scaffold_ex._DOCLING_DRAFT_ID.match(ok), ok


def test_scaffold_still_rejects_positional_ids() -> None:
    # The pre-existing positional gate is unchanged by the refactor.
    for bad in ("page-01", "slide-3-full", "42", "top-left", "center"):
        assert scaffold_ex._BANNED_ID.match(bad), bad
    for ok in ("left-rail", "top-banner", "metric-card"):
        assert not scaffold_ex._BANNED_ID.match(ok), ok


def test_analyze_with_docling_emits_only_draft_ids() -> None:
    # Guard the contract between the two scripts: every candidate id the analyzer
    # produces must be caught by the scaffold draft gate.
    import analyze_with_docling as awd
    els = [{"page": p, "label": lbl, "text": "",
            "region": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2,
                       "unit": "normalized"}}
           for p, lbl in [(1, "picture"), (2, "table"), (10, "figure"),
                          ("x", "chart"), (3, "form")]]
    items = awd.build_candidates(els, "demo", "component", None)
    assert items, "expected candidates from figure-like labels"
    for it in items:
        assert scaffold_ex._DOCLING_DRAFT_ID.match(it["item_id"]), it["item_id"]


def test_analyze_with_docling_filters_tiny_candidates() -> None:
    import analyze_with_docling as awd
    els = [
        {"page": 1, "label": "picture", "text": "",
         "region": {"x": 0.1, "y": 0.1, "width": 0.02,
                    "height": 0.02, "unit": "normalized"}},
        {"page": 1, "label": "picture", "text": "",
         "region": {"x": 0.2, "y": 0.2, "width": 0.2,
                    "height": 0.2, "unit": "normalized"}},
    ]
    items = awd.build_candidates(els, "demo", "component", None)
    assert [item["item_id"] for item in items] == ["picture-p1-1"]


def test_scaffold_rejects_docling_draft_without_polluting_analysis_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.pdf"
        source.write_text("fake", encoding="utf-8")
        output_root = root / "outputs"
        analysis = output_root / "docling-demo" / "analysis"
        analysis.mkdir(parents=True)
        request_path = root / "request.json"
        request_path.write_text(json.dumps({
            "extraction_id": "docling-demo",
            "source_path": str(source),
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.1, "y": 0.1, "width": 0.2,
                           "height": 0.2, "unit": "normalized"},
                "requested_type": "component",
                "semantic_intent": ["picture candidate detected by Docling"],
            }],
        }), encoding="utf-8")
        history = root / "history.json"
        registry = root / "registry.json"
        history.write_text('{"attempts":[]}', encoding="utf-8")
        registry.write_text('{"items":[]}', encoding="utf-8")
        old_argv = sys.argv[:]
        try:
            sys.argv = [
                "scaffold_extraction.py", "--request", str(request_path),
                "--output-root", str(output_root), "--history", str(history),
                "--registry", str(registry),
            ]
            try:
                scaffold_ex.main()
            except SystemExit as exc:
                assert "Docling draft placeholder" in str(exc)
            else:
                raise AssertionError("expected Docling draft placeholder rejection")
        finally:
            sys.argv = old_argv
        assert analysis.exists(), "analysis/ should be preserved"
        assert not (output_root / "docling-demo" / "request.json").exists()
        assert not (output_root / "docling-demo" / "items").exists()


# --------------------------------------------------------------------------- #
# candidate_review — rename / metadata / approval (analysis-only)
# --------------------------------------------------------------------------- #
import candidate_review as crv

_EXTRACTION_SCHEMA = SCRIPTS.parent / "schemas" / "extraction-request.schema.json"


def _review_fixture(tmp: Path, candidate_id: str = "picture-p1-1") -> tuple[Path, str]:
    """Create an extractions root with one analysis run carrying a placeholder
    candidate. Returns (root, extraction_id)."""
    extraction_id = "docling-demo"
    adir = tmp / extraction_id / "analysis"
    adir.mkdir(parents=True)
    (adir / "candidate-extraction-request.json").write_text(json.dumps({
        "extraction_id": extraction_id,
        "source_path": "input/Demo.pdf",
        "items": [{
            "item_id": candidate_id,
            "slide_or_page": 1,
            "region": {"x": 0.5, "y": 0.0, "width": 0.4, "height": 0.9,
                       "unit": "normalized"},
            "object_ids": [],
            "requested_type": "component",
            "semantic_intent": ["picture candidate detected by Docling"],
            "notes": "DRAFT candidate from Docling auto-detect.",
            "replacement_for": None,
        }],
    }), encoding="utf-8")
    (adir / "page-analysis.json").write_text('{"elements": []}', encoding="utf-8")
    (adir / "docling-report.json").write_text('{"candidate_count": 1}', encoding="utf-8")
    return tmp, extraction_id


def _valid_metadata(item_id: str = "kickoff-2026-hero-visual") -> dict:
    return {
        "item_id": item_id,
        "display_name": "Kick-off 2026 hero visual",
        "requested_type": "component",
        "component_type": "hero",
        "layout_role": "full-bleed",
        "visual_summary": "A tall orange hero illustration on the right column.",
        "semantic_intent": ["kickoff hero", "goal setting cover"],
        "content_structure": ["illustration"],
        "tags": ["hero", "orange"],
        "keywords": ["kickoff", "2026"],
        "use_cases": ["cover slide"],
        "anti_use_cases": ["dense data slide"],
        "quality_notes": "",
        "retrieval_notes": "",
    }


def test_candidate_placeholder_id_cannot_be_approved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        # Save valid metadata but keep the Docling placeholder as item_id.
        meta = _valid_metadata(item_id="picture-p1-1")
        crv.save_review(eid, "picture-p1-1", meta, reviewer="t", root=root)
        try:
            crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        except crv.CandidateValidationError as exc:
            assert any("placeholder" in e.lower() for e in exc.errors), exc.errors
        else:
            raise AssertionError("placeholder item_id must not be approvable")
        # No approved artifact written.
        assert not (root / eid / "analysis" / "approved").exists()


def test_candidate_positional_id_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        crv.save_review(eid, "picture-p1-1", _valid_metadata("top-left"),
                        reviewer="t", root=root)
        errors = crv.validate_review(crv.get_candidates(eid, root=root)
                                     ["candidates"][0]["review"])
        assert any("positional" in e.lower() or "generic" in e.lower() for e in errors), errors


def test_candidate_required_metadata_enforced() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        # rename only, leave all metadata empty
        crv.save_review(eid, "picture-p1-1", {"item_id": "kickoff-hero"},
                        reviewer="t", root=root)
        try:
            crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        except crv.CandidateValidationError as exc:
            joined = " ".join(exc.errors).lower()
            assert "display name" in joined and "visual summary" in joined, exc.errors
        else:
            raise AssertionError("missing required metadata must block approval")


def test_candidate_approve_writes_schema_compatible_request() -> None:
    schema = read_text_slots.load_json(_EXTRACTION_SCHEMA)
    item_schema = schema["properties"]["items"]["items"]
    allowed = set(item_schema["properties"])
    required = set(item_schema["required"])
    top_required = set(schema["required"])

    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        crv.save_review(eid, "picture-p1-1", _valid_metadata(), reviewer="t", root=root)
        result = crv.approve(eid, "picture-p1-1", reviewer="t", root=root)

        approved_path = root / eid / "analysis" / "approved" / "kickoff-2026-hero-visual.extraction-request.json"
        assert approved_path.is_file(), result
        req = read_text_slots.load_json(approved_path)
        assert top_required <= set(req), req
        item = req["items"][0]
        assert required <= set(item), item
        assert set(item) <= allowed, f"extra keys not in schema: {set(item) - allowed}"
        assert item["item_id"] == "kickoff-2026-hero-visual"
        # The approved request must also pass the live scaffold gate.
        scaffold_ex.validate_request_item(item)
        # review status updated, reviewer recorded.
        cand = crv.get_candidates(eid, root=root)["candidates"][0]
        assert cand["review"]["review_status"] == "approved_for_extraction"
        assert cand["review"]["reviewer"] == "t"


def test_candidate_reject_produces_no_approved_request() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        crv.save_review(eid, "picture-p1-1", _valid_metadata(), reviewer="t", root=root)
        crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        approved_path = root / eid / "analysis" / "approved" / "kickoff-2026-hero-visual.extraction-request.json"
        assert approved_path.is_file()
        # Rejecting must drop the stale approved artifact and flip status.
        review = crv.reject(eid, "picture-p1-1", "wrong crop", reviewer="t", root=root)
        assert review["review_status"] == "rejected"
        assert not approved_path.exists(), "reject must remove the approved request"
        # A reject with no reason is refused.
        try:
            crv.reject(eid, "picture-p1-1", "", root=root)
        except crv.CandidateError:
            pass
        else:
            raise AssertionError("reject without a reason must fail")


def test_candidate_review_preserves_analysis_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        adir = root / eid / "analysis"
        before = (adir / "candidate-extraction-request.json").read_text(encoding="utf-8")
        page_before = (adir / "page-analysis.json").read_text(encoding="utf-8")
        crv.save_review(eid, "picture-p1-1", _valid_metadata(), reviewer="t", root=root)
        crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        assert (adir / "candidate-extraction-request.json").read_text(encoding="utf-8") == before
        assert (adir / "page-analysis.json").read_text(encoding="utf-8") == page_before
        assert (adir / "docling-report.json").exists()


def test_candidate_review_does_not_touch_registry_or_library() -> None:
    # candidate_review must only write under the analysis dir; the real registry,
    # compact registry, history, and library must be byte-identical afterwards.
    repo = SCRIPTS.parents[1]
    watched = [
        repo / "slide-system" / "registries" / "visual-library.json",
        repo / "slide-system" / "registries" / "visual-library-compact.json",
        repo / "slide-system" / "registries" / "extraction-history.json",
    ]
    before = {p: p.read_bytes() for p in watched if p.exists()}
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        crv.save_review(eid, "picture-p1-1", _valid_metadata(), reviewer="t", root=root)
        crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        crv.reject(eid, "picture-p1-1", "redo", reviewer="t", root=root)
    after = {p: p.read_bytes() for p in watched if p.exists()}
    assert before == after, "candidate review must not mutate registry/history/library"


def test_candidate_invalid_extraction_id_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for bad in ("../escape", "..", "a/b", "/etc", "bad id"):
            try:
                crv.get_candidates(bad, root=root)
            except crv.CandidateError:
                pass
            else:
                raise AssertionError(f"invalid extraction id must be rejected: {bad!r}")


def test_candidate_editing_resets_approval() -> None:
    # Editing an approved candidate must revert it to pending and drop the stale
    # approved request, so an approval never outlives the metadata it was built on.
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        crv.save_review(eid, "picture-p1-1", _valid_metadata(), reviewer="t", root=root)
        crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        approved_path = root / eid / "analysis" / "approved" / "kickoff-2026-hero-visual.extraction-request.json"
        assert approved_path.is_file()
        crv.save_review(eid, "picture-p1-1", {"visual_summary": "edited"},
                        reviewer="t", root=root)
        assert not approved_path.exists(), "editing must drop the stale approved request"
        cand = crv.get_candidates(eid, root=root)["candidates"][0]
        assert cand["review"]["review_status"] == "pending"


def test_candidate_multiple_approvals_scaffold_without_collision() -> None:
    # Regression: every approved request from one run must get its own scaffold
    # extraction id, else the second candidate fails with "already exists".
    import scaffold_extraction as sx
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        source = tmpp / "Demo.pdf"
        source.write_bytes(b"%PDF-1.4 fake source")
        eid = "docling-demo"
        root = tmpp / "ext"
        adir = root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [
                {"item_id": f"picture-p1-{i}", "slide_or_page": 1,
                 "region": {"x": 0.1 * i, "y": 0.1, "width": 0.3, "height": 0.3,
                            "unit": "normalized"},
                 "object_ids": [], "requested_type": "component",
                 "semantic_intent": ["pic"], "replacement_for": None}
                for i in (1, 2)
            ],
        }), encoding="utf-8")

        for i in (1, 2):
            crv.save_review(eid, f"picture-p1-{i}", _valid_metadata(f"hero-{i}"),
                            reviewer="t", root=root)
            crv.approve(eid, f"picture-p1-{i}", reviewer="t", root=root)

        req1 = read_text_slots.load_json(adir / "approved" / "hero-1.extraction-request.json")
        req2 = read_text_slots.load_json(adir / "approved" / "hero-2.extraction-request.json")
        assert req1["extraction_id"] == "docling-demo-hero-1", req1["extraction_id"]
        assert req1["extraction_id"] != req2["extraction_id"]

        out_root = tmpp / "out"
        hist = tmpp / "history.json"; hist.write_text('{"attempts":[]}', encoding="utf-8")
        reg = tmpp / "registry.json"; reg.write_text('{"items":[]}', encoding="utf-8")
        for name in ("hero-1", "hero-2"):
            req = adir / "approved" / f"{name}.extraction-request.json"
            old_argv = sys.argv[:]
            sys.argv = ["scaffold_extraction.py", "--request", str(req),
                        "--output-root", str(out_root), "--history", str(hist),
                        "--registry", str(reg)]
            try:
                assert sx.main() == 0, name
            finally:
                sys.argv = old_argv
        # Both scaffolded into separate, non-colliding output dirs.
        assert (out_root / "docling-demo-hero-1" / "items" / "hero-1").is_dir()
        assert (out_root / "docling-demo-hero-2" / "items" / "hero-2").is_dir()


def test_candidate_rename_removes_old_approved_artifact() -> None:
    # Renaming an approved candidate must not orphan the old item_id's request.
    with tempfile.TemporaryDirectory() as tmp:
        root, eid = _review_fixture(Path(tmp))
        crv.save_review(eid, "picture-p1-1", _valid_metadata("hero-a"), reviewer="t", root=root)
        crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        old = root / eid / "analysis" / "approved" / "hero-a.extraction-request.json"
        assert old.is_file()
        meta = _valid_metadata("hero-b")
        crv.save_review(eid, "picture-p1-1", meta, reviewer="t", root=root)
        assert not old.exists(), "old-name approved request must be removed on rename"
        crv.approve(eid, "picture-p1-1", reviewer="t", root=root)
        new = root / eid / "analysis" / "approved" / "hero-b.extraction-request.json"
        assert new.is_file() and not old.exists()


# --------------------------------------------------------------------------- #
def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
