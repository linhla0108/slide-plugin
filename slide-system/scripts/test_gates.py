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
