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
            "brand": None, "compatibility": {}, "limitations": []}
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
    item_dir = SCRIPTS.parent / "library" / "chart" / "sun.chart.rating-scale-chart"
    data = read_text_slots.load_json(item_dir / "text-slots.json")
    slim = read_text_slots.project(data["slots"], with_typography=False)
    assert len(slim) == len(data["slots"])
    assert set(slim[0].keys()) == set(read_text_slots.SLIM_FIELDS)


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
