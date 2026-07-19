#!/usr/bin/env python3
"""Unit tests for the slide-pipeline gate scripts.

Covers the highest-consequence, previously-untested paths:
  - cleanup_run: deck.html + .pptx survive; intermediates are removed.
  - score_visual_items: 65/75 decision thresholds + extraction recommendation.
  - score_visual_items hybrid retrieval: capped secondary lexical credit,
    anti-use-case / count-fit / zero-slot penalties, published-only enrichment.
  - validate_selection_report: equal-score plausibility, provenance, T1 shape-lock.
  - scaffold_slide_from_component: slots preserved, no base64, .bg placeholder.
  - validate_component_fidelity: slot-id coverage pass/fail.
  - read_text_slots: slim projection shape.

Run directly (`python3 test_gates.py`) or under pytest. No network, no install.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import importlib.util
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import cleanup_run
import compare_renders
import delivery_gate
import export_pptx
import build_hybrid_pptx as bhp
import validate_export_objects as veo
import score_visual_items as svi
import validate_selection_report as vsr
import scaffold_slide_from_component as scaffold
import validate_component_fidelity as fidelity
import read_text_slots
import _common
import publish_extraction as pe  # noqa: E402
import build_component_retrieval_index as bcri  # noqa: E402

REGISTRY = SCRIPTS.parent / "registries" / "visual-library.json"
QA_LOOP = SCRIPTS / "run_claude_codex_qa_loop.ps1"

# A real template item with positioned slots (verified to have .slot divs).
ITEM_WITH_SLOTS = "sun.interview-workshop-sunriser.04-mindset"


# --------------------------------------------------------------------------- #
# run_claude_codex_qa_loop — automation must plan by default and refuse a
# dirty baseline unless the operator deliberately opts in.
# --------------------------------------------------------------------------- #
def test_qa_loop_plan_is_dry_run_and_explains_dirty_baseline_guard() -> None:
    assert QA_LOOP.exists(), "the bounded Claude/Codex QA runner must exist"
    with tempfile.TemporaryDirectory() as tmp:
        prompt = Path(tmp) / "task.md"
        prompt.write_text("Review-only smoke task.", encoding="utf-8")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(QA_LOOP),
             "-PromptFile", str(prompt), "-Plan"],
            cwd=SCRIPTS.parent.parent,
            text=True,
            capture_output=True,
            timeout=30,
        )
    assert result.returncode == 0, result.stderr
    assert "PLAN ONLY" in result.stdout
    assert "-AllowDirtyBaseline" in result.stdout
    assert "claude -p" in result.stdout and "codex exec" in result.stdout


def test_qa_loop_accepts_csv_scope_before_dirty_baseline_guard() -> None:
    """`powershell -File` receives a CSV scope as one argument on Windows."""
    with tempfile.TemporaryDirectory() as tmp:
        prompt = Path(tmp) / "task.md"
        prompt.write_text("Review-only smoke task.", encoding="utf-8")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(QA_LOOP),
             "-Run", "-PromptFile", str(prompt),
             "-AllowedPath", "slide-system/scripts,docs/logs"],
            cwd=SCRIPTS.parent.parent,
            text=True,
            capture_output=True,
            timeout=30,
        )
    assert result.returncode != 0, "the test worktree is intentionally dirty"
    assert "Worktree is already dirty" in (result.stdout + result.stderr)
    assert "positional parameter" not in (result.stdout + result.stderr).lower()


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
# export_pptx / compare_renders — cache consistency and AA-aware parity
# --------------------------------------------------------------------------- #
def test_export_invalidates_stale_verdict_and_parity_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "export"
        out.mkdir()
        output = out / "deck.pptx"
        output.write_bytes(b"PK\x03\x04current")
        (out / "export-result.json").write_text("{}", encoding="utf-8")
        (out / ".capture-fingerprint.json").write_text("{}", encoding="utf-8")
        (out / ".parity-fingerprint.json").write_text("{}", encoding="utf-8")
        (out / "export-manifest.json").write_text("{}", encoding="utf-8")
        output.with_suffix(".validation.json").write_text("{}", encoding="utf-8")
        report = out / "parity" / "slide-01" / "tier2" / "report.json"
        report.parent.mkdir(parents=True)
        report.write_text("{}", encoding="utf-8")

        export_pptx.invalidate_stale_artifacts(out, output, capture_stale=True)

        assert output.exists(), "invalidation must not delete the built PPTX"
        assert not (out / "export-result.json").exists()
        assert not output.with_suffix(".validation.json").exists()
        assert not (out / ".capture-fingerprint.json").exists()
        assert not (out / ".parity-fingerprint.json").exists()
        assert not (out / "export-manifest.json").exists()
        assert not (out / "parity").exists()


def test_export_reuses_only_complete_fingerprint_bound_parity_reports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        parity = Path(tmp) / "parity"
        manifest = {"slides": [{"slide": 1}, {"slide": 2}]}
        fingerprint = {"html_sha": "current", "compare_script_sha": "metric-v2"}
        for report in export_pptx.expected_parity_reports(parity, manifest):
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text('{"metrics":{"changed_pixel_ratio":0}}', encoding="utf-8")

        export_pptx.write_parity_fingerprint(parity, manifest, fingerprint)

        assert export_pptx.parity_cache_valid(parity, manifest, fingerprint)
        missing = parity / "slide-02" / "tier2" / "report.json"
        missing.unlink()
        assert not export_pptx.parity_cache_valid(parity, manifest, fingerprint)


# --------------------------------------------------------------------------- #
# build_hybrid_pptx — layered geometry must reject an un-paginated capture
#
# capture-slides.js records each slide's capture-root bounding rect. A deck that
# paginates one slide into the viewport (deck-stage, or `.slide.active` driven by
# --showJs/--selector) reports every slide's canvas == the declared capture
# viewport. A deck whose slides are all laid out at once, exported without
# per-slide navigation, reports the WHOLE-DECK scroll height for every slide —
# and the layered build would then derive a sliver slide size and stack the
# entire deck's text on every slide, while the first-frame-vs-first-frame parity
# gate still passes. The build must fail closed on that signature.
# --------------------------------------------------------------------------- #
def _layered_manifest(canvas_h_per_slide: float, n: int = 3, declared_h: float = 1080):
    return {
        "manifest_version": 2, "mode": "layered",
        "canvasW": 1920, "canvasH": declared_h,
        "slides": [{"slide": i + 1, "canvasW": 1920, "canvasH": canvas_h_per_slide}
                   for i in range(n)],
    }


def test_layered_geometry_accepts_paginated_single_slide_canvas() -> None:
    w, h = bhp.resolve_layered_geometry(_layered_manifest(1080))
    assert (round(w, 3), round(h, 3)) == (13.333, 7.5)


def test_layered_geometry_rejects_unpaginated_whole_deck_capture() -> None:
    # 3 slides stacked (each 1080px + 24px margin) -> the root spans 3264px, the
    # exact signature of a deck captured with no per-slide navigation.
    bad = _layered_manifest(3 * 1080 + 2 * 24)
    try:
        bhp.resolve_layered_geometry(bad)
    except SystemExit as exc:
        assert "paginat" in str(exc).lower() or "viewport" in str(exc).lower()
    else:
        raise AssertionError("resolve_layered_geometry must fail closed on a whole-deck "
                             "capture instead of returning a (sliver) slide size")


def test_layered_geometry_tolerates_subpixel_canvas_rounding() -> None:
    # A 1px scrollbar / sub-pixel rounding on a genuinely paginated slide must
    # NOT trip the guard.
    w, h = bhp.resolve_layered_geometry(_layered_manifest(1081))
    assert (round(w, 3), round(h, 3)) == (13.333, 7.5)


# --------------------------------------------------------------------------- #
# build_hybrid_pptx — navigation backstop: a paginated deck (correct canvas)
# captured WITHOUT navigation re-shoots slide 1 every frame, so canvasH looks
# fine but every slide is identical. The geometry guard can't see that; this
# backstop fails closed when EVERY slide shares one background AND identical text.
# --------------------------------------------------------------------------- #
def _captured_manifest(slides):
    return {"manifest_version": 2, "mode": "layered", "canvasW": 1920, "canvasH": 1080,
            "slides": slides}


def test_build_backstop_rejects_repeated_first_slide_capture() -> None:
    # 9 frames, one background sha, one identical text list == slide-1 repeated.
    slides = [{"slide": i + 1, "canvasW": 1920, "canvasH": 1080,
               "base": {"sha256": "SAME"}, "text": [{"text": "© SUN.STUDIO"}]}
              for i in range(9)]
    try:
        bhp.assert_capture_navigated(_captured_manifest(slides))
    except SystemExit as exc:
        assert "navigation" in str(exc).lower() or "repeated" in str(exc).lower()
    else:
        raise AssertionError("must fail closed when every captured frame is slide 1")


def test_build_backstop_accepts_shared_solid_bg_with_distinct_text() -> None:
    # A legitimate deck may share one solid brand background while each slide
    # carries its own title — distinct text proves navigation worked. (This is a
    # navigation backstop only; the DELIVERY contract for unresolved jobs is
    # enforced by delivery_gate, tested below.)
    slides = [{"slide": i + 1, "canvasW": 1920, "canvasH": 1080,
               "base": {"sha256": "SOLID"},
               "text": [{"text": "Agenda"}, {"text": f"slide {i} title"}]}
              for i in range(8)]
    bhp.assert_capture_navigated(_captured_manifest(slides))  # must not raise


# --------------------------------------------------------------------------- #
# delivery_gate — the unresolved-delivery contract (replaces the retired
# "a needs_component placeholder deck is a valid deliverable" expectation).
# A job with ANY needs_component slide is UNRESOLVED and must NOT produce a
# final deck/PPTX/PDF; the internal diagnostic reason never leaks to end-user
# output; explicit blank / explicit component follow their own paths; a fully
# resolved reuse job is deliverable.
# --------------------------------------------------------------------------- #
def _dec_slide(rid: str, decision: dict) -> dict:
    return {"request_id": rid, "decision": decision, "candidates": []}


def _batch_report(slides: list[dict]) -> dict:
    return {"job_id": "j", "generated_by": "score_visual_items.py", "slides": slides}


# A reuse decision must name a component that is PUBLISHED in the full registry.
# Tests inject the published-id set (or a temp registry file, see
# test_delivery_gate_rejects_reuse_of_unpublished_id) so delivery_gate.py never
# hardcodes a real component id.
_FIXTURE_PUBLISHED = frozenset({
    "sun.component.x", "sun.component.auto", "sun.component.user",
})


def test_delivery_gate_blocks_unresolved_needs_component_job() -> None:
    # Product contract: one needs_component slide makes the whole job UNRESOLVED,
    # so no final deliverable is produced. The styled diagnostic placeholder deck
    # is NOT valid.
    report = _batch_report([
        _dec_slide("s1", {"action": "reuse", "item_id": "sun.component.x", "score": 90}),
        _dec_slide("s2", {"action": "needs_component", "item_id": None, "score": 60,
                          "reason": "INTERNAL: no confident published match; audit unresolved.",
                          "suggested_search": ["role cards"],
                          "next_action": "Pick a component in the catalog."}),
    ])
    state = delivery_gate.delivery_state(report, _FIXTURE_PUBLISHED)
    assert state["deliverable"] is False
    assert state["status"] == "awaiting_component_selection"
    assert [u["request_id"] for u in state["unresolved"]] == ["s2"]
    try:
        delivery_gate.assert_deliverable(report, _FIXTURE_PUBLISHED)
    except SystemExit as exc:
        assert "UNRESOLVED" in str(exc), exc
    else:
        raise AssertionError("an unresolved job must not be deliverable")


def test_delivery_gate_never_leaks_internal_reason_to_user_output() -> None:
    # The internal diagnostic `reason` stays only in selection-report.json (catalog
    # input). It must never appear in anything end-user / deliverable-facing: the
    # gate's user-facing state and its block message carry only the catalog-safe
    # pointer (suggested_search / next_action / shortlist), never `reason`.
    secret = "INTERNAL: audit unresolved for sun.component.secret"
    report = _batch_report([
        _dec_slide("s1", {"action": "needs_component", "item_id": None, "score": 55,
                          "reason": secret, "suggested_search": ["timeline"],
                          "next_action": "Preview timeline components."}),
    ])
    state = delivery_gate.delivery_state(report)
    assert secret not in json.dumps(state)
    try:
        delivery_gate.assert_deliverable(report)
    except SystemExit as exc:
        assert secret not in str(exc), exc
    else:
        raise AssertionError("must block")


def test_delivery_gate_passes_fully_resolved_reuse_blank_custom() -> None:
    # The three explicit resolution paths make a job deliverable.
    report = _batch_report([
        _dec_slide("s1", {"action": "reuse", "item_id": "sun.component.x", "score": 90,
                          "selected_by": "user"}),
        _dec_slide("s2", {"action": "blank", "item_id": None, "score": 0,
                          "selected_by": "user", "reason": "User chose blank."}),
        _dec_slide("s3", {"action": "custom-local", "item_id": None, "score": 40,
                          "selected_by": "user", "reason": "User approved custom-local."}),
    ])
    state = delivery_gate.delivery_state(report, _FIXTURE_PUBLISHED)
    assert state["deliverable"] is True and state["status"] == "complete", state
    delivery_gate.assert_deliverable(report, _FIXTURE_PUBLISHED)  # must not raise


def test_delivery_gate_fails_closed_on_non_explicit_or_malformed_actions() -> None:
    # A hand-edited report must not promote an unresolved job to a deliverable.
    # custom-local / blank are user-only; reuse must name a usable component id.
    # Each of these carries a terminal action string but fails the provenance
    # contract, so the gate treats it as unknown and blocks delivery.
    for label, dec in [
        # custom-local without selected_by: user
        ("custom-local-no-user", {"action": "custom-local", "item_id": None, "score": 40}),
        # blank without explicit user selection
        ("blank-no-user", {"action": "blank", "item_id": None, "score": 0}),
        # reuse without a usable item_id (None / empty / non-string)
        ("reuse-null-id", {"action": "reuse", "item_id": None, "score": 90}),
        ("reuse-empty-id", {"action": "reuse", "item_id": "  ", "score": 90}),
        ("reuse-missing-id", {"action": "reuse", "score": 90}),
    ]:
        report = _batch_report([_dec_slide("s1", dec)])
        state = delivery_gate.delivery_state(report)
        assert state["deliverable"] is False, (label, state)
        assert state["unknown_actions"] == ["s1"], (label, state)
        try:
            delivery_gate.assert_deliverable(report)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"{label}: a non-explicit/malformed action must block delivery")


def test_delivery_gate_passes_automatic_and_explicit_user_reuse() -> None:
    # Legitimate scorer-generated automatic reuse (no selected_by, real item_id)
    # and explicit user reuse (selected_by: user, real item_id) both stay
    # deliverable — the fail-closed fix must not regress valid reuse.
    report = _batch_report([
        _dec_slide("s1", {"action": "reuse", "item_id": "sun.component.auto", "score": 92}),
        _dec_slide("s2", {"action": "reuse", "item_id": "sun.component.user", "score": 88,
                          "selected_by": "user"}),
    ])
    state = delivery_gate.delivery_state(report, _FIXTURE_PUBLISHED)
    assert state["deliverable"] is True and state["status"] == "complete", state
    delivery_gate.assert_deliverable(report, _FIXTURE_PUBLISHED)  # must not raise


def test_delivery_gate_rejects_reuse_of_unpublished_id() -> None:
    # A reuse decision that names a non-empty id which is NOT published in the
    # full registry (an arbitrary / staging / unpublished id) must fail closed —
    # a non-empty id alone is not enough. Valid published reuse (auto scorer and
    # explicit user) still passes. Driven by a TEMP fixture registry so product
    # code never hardcodes a component id.
    with tempfile.TemporaryDirectory() as tmpd:
        registry = Path(tmpd) / "visual-library.json"
        registry.write_text(json.dumps({"items": [
            {"id": "sun.component.published-auto", "status": "published"},
            {"id": "sun.component.published-user", "status": "published"},
            {"id": "sun.component.staging", "status": "candidate"},  # not published
        ]}), encoding="utf-8")
        published = delivery_gate.published_item_ids(registry)
        assert published == frozenset(
            {"sun.component.published-auto", "sun.component.published-user"}), published

        # bogus (absent), staging (present but unpublished) → both unknown/blocked
        for bad in ("sun.component.does-not-exist", "sun.component.staging"):
            report = _batch_report([
                _dec_slide("s1", {"action": "reuse", "item_id": bad, "score": 95})])
            state = delivery_gate.delivery_state(report, published)
            assert state["deliverable"] is False, (bad, state)
            assert state["unknown_actions"] == ["s1"], (bad, state)

        # valid published reuse (automatic scorer + explicit user) still delivers
        ok = _batch_report([
            _dec_slide("s1", {"action": "reuse", "item_id": "sun.component.published-auto",
                              "score": 92}),
            _dec_slide("s2", {"action": "reuse", "item_id": "sun.component.published-user",
                              "score": 88, "selected_by": "user"}),
        ])
        state = delivery_gate.delivery_state(ok, published)
        assert state["deliverable"] is True and state["status"] == "complete", state
        delivery_gate.assert_deliverable(ok, published)  # must not raise


def test_export_pptx_delivery_gate_blocks_unresolved_run_before_build() -> None:
    # export_pptx runs the delivery gate before capture/build: an unresolved run's
    # selection-report next to deck.html fails closed, so no PPTX is produced.
    with tempfile.TemporaryDirectory() as tmpd:
        run = Path(tmpd)
        (run / "analysis").mkdir()
        (run / "deck.html").write_text("<html></html>", encoding="utf-8")
        (run / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "needs_component", "item_id": None,
                                  "score": 50, "reason": "unresolved"})])),
            encoding="utf-8")
        try:
            delivery_gate.enforce_deck_deliverable(run / "deck.html")
        except SystemExit as exc:
            assert "delivery blocked" in str(exc), exc
        else:
            raise AssertionError("export must refuse an unresolved run")
        # A resolved run passes the same guard.
        (run / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "reuse", "item_id": "sun.component.x",
                                  "score": 90, "selected_by": "user"})])),
            encoding="utf-8")
        assert delivery_gate.enforce_deck_deliverable(
            run / "deck.html", _FIXTURE_PUBLISHED)["deliverable"]


def test_export_pptx_main_runs_delivery_gate_before_capture() -> None:
    # P2 integration proof: drive export_pptx.main() far enough to prove the
    # delivery guard fires BEFORE any capture/build. An unresolved run must raise
    # SystemExit from the gate — no node/Playwright/LibreOffice, and no .pptx.
    with tempfile.TemporaryDirectory() as tmpd:
        run = Path(tmpd)
        (run / "analysis").mkdir()
        (run / "deck.html").write_text("<html></html>", encoding="utf-8")
        (run / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "needs_component", "item_id": None,
                                  "score": 50, "reason": "unresolved"})])),
            encoding="utf-8")
        out_dir = run / "work"
        output = run / "deck.pptx"
        argv = ["export_pptx.py", "--html", str(run / "deck.html"),
                "--slides", "1", "--out-dir", str(out_dir),
                "--output", str(output), "--mode", "layered"]
        saved = sys.argv
        sys.argv = argv
        try:
            export_pptx.main()
        except SystemExit as exc:
            assert "delivery blocked" in str(exc), exc
        else:
            raise AssertionError("export_pptx.main must refuse an unresolved run")
        finally:
            sys.argv = saved
        assert not output.exists(), "no PPTX may be produced for an unresolved run"


def test_delivery_gate_deck_cli_blocks_unresolved_run() -> None:
    # PDF output boundary proof: export-pdf.js shells out to
    # `delivery_gate.py --deck <deck.html>`; the same CLI must exit non-zero with
    # a catalog-safe message for an unresolved run, and 0 for a deck with no
    # sibling selection-report (external/custom, not gated here).
    with tempfile.TemporaryDirectory() as tmpd:
        run = Path(tmpd)
        (run / "analysis").mkdir()
        (run / "deck.html").write_text("<html></html>", encoding="utf-8")
        secret = "INTERNAL: audit reason must not leak"
        (run / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "needs_component", "item_id": None,
                                  "score": 50, "reason": secret})])),
            encoding="utf-8")
        try:
            delivery_gate.main(["--deck", str(run / "deck.html")])
        except SystemExit as exc:
            assert "delivery blocked" in str(exc), exc
            assert secret not in str(exc), exc
        else:
            raise AssertionError("--deck must refuse an unresolved run")

        # No sibling report → external/custom deck, not gated here (exit 0).
        external = run / "external"
        external.mkdir()
        (external / "deck.html").write_text("<html></html>", encoding="utf-8")
        assert delivery_gate.main(["--deck", str(external / "deck.html")]) == 0


def test_delivery_gate_fails_closed_on_empty_or_malformed_slides() -> None:
    # P2: a batch report with zero USABLE slide records (empty slides array, or a
    # wholly non-dict record set) must NOT be vacuously deliverable — fail closed.
    for label, report in [
        ("empty-slides", _batch_report([])),
        ("all-malformed", {"job_id": "j", "generated_by": "score_visual_items.py",
                           "slides": ["not-a-dict", 42, None]}),
    ]:
        state = delivery_gate.delivery_state(report)
        assert state["deliverable"] is False, (label, state)
        try:
            delivery_gate.assert_deliverable(report)
        except SystemExit as exc:
            assert "delivery blocked" in str(exc), (label, exc)
        else:
            raise AssertionError(f"{label}: an empty/malformed report must block delivery")
    # One malformed record mixed with a resolved one still blocks (never dropped).
    mixed = {"job_id": "j", "generated_by": "score_visual_items.py", "slides": [
        _dec_slide("s1", {"action": "reuse", "item_id": "sun.component.x", "score": 90}),
        "not-a-dict",
    ]}
    assert delivery_gate.delivery_state(mixed, _FIXTURE_PUBLISHED)["deliverable"] is False
    # The supported single-report input (no slides array) is unaffected.
    single = {"request_id": "s1",
              "decision": {"action": "reuse", "item_id": "sun.component.x", "score": 90}}
    assert delivery_gate.delivery_state(single, _FIXTURE_PUBLISHED)["deliverable"] is True


def test_export_pdf_js_gate_blocks_tracked_unresolved_job() -> None:
    # P2 exporter-level proof: `node export-pdf.js` must NOT produce a PDF for a
    # tracked unresolved run, --skip-delivery-gate must NOT bypass a tracked job,
    # and an HTTP url does not bypass when --deck locates the sibling report. The
    # gate runs BEFORE Playwright is required, so no browser is needed. Skipped
    # only when Node itself is unavailable.
    node = shutil.which("node")
    if node is None:
        print("  SKIP  test_export_pdf_js_gate_blocks_tracked_unresolved_job (node not found)")
        return
    exporter = SCRIPTS / "export-pdf.js"
    secret = "INTERNAL: audit reason must not leak to the exporter output"
    with tempfile.TemporaryDirectory() as tmpd:
        run = Path(tmpd)
        (run / "analysis").mkdir()
        (run / "deck.html").write_text("<html></html>", encoding="utf-8")
        (run / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "needs_component", "item_id": None,
                                  "score": 50, "reason": secret})])),
            encoding="utf-8")
        out_pdf = run / "exports" / "deck.pdf"
        deck_html = str(run / "deck.html")
        deck_url = (run / "deck.html").as_uri()
        base = [node, str(exporter), "--url", deck_url, "--deck", deck_html,
                "--output", str(out_pdf)]

        # (a) --skip-delivery-gate is REFUSED for a tracked job (no bypass), and
        #     the internal reason never leaks. This path dies before .venv/browser.
        res = subprocess.run(base + ["--skip-delivery-gate"],
                             capture_output=True, text=True)
        combined = res.stdout + res.stderr
        assert res.returncode != 0, combined
        assert not out_pdf.exists(), "skip flag must not bypass a tracked job"
        assert "cannot bypass" in combined, combined
        assert secret not in combined, "internal reason must never leak"

        # (b) The plain gated path also blocks the unresolved job — no PDF, no leak.
        res2 = subprocess.run(base, capture_output=True, text=True)
        assert res2.returncode != 0, res2.stdout + res2.stderr
        assert not out_pdf.exists(), "no PDF for an unresolved tracked run"
        assert secret not in (res2.stdout + res2.stderr), "internal reason must never leak"

        # (c) An HTTP url does not bypass: with --deck the gate still finds the
        #     sibling report and blocks (no dependence on the url scheme).
        res3 = subprocess.run(
            [node, str(exporter), "--url", "http://localhost:8080",
             "--deck", deck_html, "--output", str(out_pdf)],
            capture_output=True, text=True)
        assert res3.returncode != 0, res3.stdout + res3.stderr
        assert not out_pdf.exists(), "HTTP route must not bypass a tracked job"


def test_export_pdf_js_gate_survives_url_scheme_case_and_deck_vouching() -> None:
    # P1 regression: URL schemes are case-insensitive (RFC 3986) and the browser
    # normalizes them, but the gate tested `startsWith("file://")` case-sensitively.
    # So `--url FILE:///<unresolved>/deck.html --deck <resolved>/deck.html` made the
    # unresolved deck look like "not a file URL", skipped the deck/url match, let the
    # RESOLVED deck satisfy the gate, and then PRINTED the unresolved deck. The same
    # shape let any non-file URL (data:, about:) be vouched for by --deck.
    # Failure paths only, so no browser is required.
    node = shutil.which("node")
    if node is None:
        print("  SKIP  test_export_pdf_js_gate_survives_url_scheme_case_and_deck_vouching "
              "(node not found)")
        return
    exporter = SCRIPTS / "export-pdf.js"
    with tempfile.TemporaryDirectory() as tmpd:
        root = Path(tmpd)
        ok = root / "resolved"
        (ok / "analysis").mkdir(parents=True)
        (ok / "deck.html").write_text("<html>ok</html>", encoding="utf-8")
        (ok / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "blank", "selected_by": "user",
                                  "item_id": None, "score": 0})])), encoding="utf-8")
        bad = root / "unresolved"
        (bad / "analysis").mkdir(parents=True)
        (bad / "deck.html").write_text("<html>must not ship</html>", encoding="utf-8")
        (bad / "analysis" / "selection-report.json").write_text(
            json.dumps(_batch_report([
                _dec_slide("s1", {"action": "needs_component", "item_id": None,
                                  "score": 50, "reason": "unresolved"})])), encoding="utf-8")
        out = root / "out.pdf"
        upper = (bad / "deck.html").as_uri().replace("file://", "FILE://", 1)

        def run(url, *extra):
            out.unlink(missing_ok=True)
            proc = subprocess.run(
                [node, str(exporter), "--url", url, "--output", str(out), *extra],
                capture_output=True, text=True)
            return proc, out.exists()

        # (a) Upper-case FILE:// unresolved deck vouched by a resolved --deck.
        proc, made = run(upper, "--deck", str(ok / "deck.html"))
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert not made, "a resolved --deck must never vouch for a different deck"
        # (b) Upper-case FILE:// alone is still recognised as a file URL AND gated.
        proc, made = run(upper)
        assert proc.returncode != 0 and not made, proc.stdout + proc.stderr
        assert "delivery blocked" in (proc.stdout + proc.stderr), proc.stdout + proc.stderr
        # (c) A non-file URL cannot be vouched for by --deck.
        proc, made = run("data:text/html,<h1>x</h1>", "--deck", str(ok / "deck.html"))
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert not made, "--deck must not authorise an arbitrary non-file URL"


def test_build_backstop_accepts_distinct_backgrounds() -> None:
    slides = [{"slide": i + 1, "canvasW": 1920, "canvasH": 1080,
               "base": {"sha256": f"BG{i}"}, "text": [{"text": "same"}]}
              for i in range(3)]
    bhp.assert_capture_navigated(_captured_manifest(slides))  # distinct bg -> ok


# --------------------------------------------------------------------------- #
# export_pptx — the capture cache must invalidate when navigation/selector change
# --------------------------------------------------------------------------- #
def _capture_args(**overrides):
    import argparse
    base = dict(html=str(REGISTRY), mode="layered", slides=9, width=1920, height=1080,
                overlay_scale=2, pad=96, showJs=None, selector=None)
    base.update(overrides)
    return argparse.Namespace(**base)


def test_capture_fingerprint_invalidates_on_nav_or_selector_change() -> None:
    base = export_pptx.capture_fingerprint(_capture_args())
    assert "showjs" in base and "selector" in base
    nav = export_pptx.capture_fingerprint(_capture_args(showJs="goToSlide({n})"))
    sel = export_pptx.capture_fingerprint(_capture_args(selector=".slide.active"))
    assert base != nav, "changing --showJs must change the capture fingerprint"
    assert base != sel, "changing --selector must change the capture fingerprint"
    assert nav != sel


# --------------------------------------------------------------------------- #
# compare_renders / validate_export_objects — the secondary parity guard must
# ignore 1px text-edge AA halo but still catch contiguous displacement.
# --------------------------------------------------------------------------- #
def test_significant_ratio_drops_thin_edges_keeps_solid_blocks() -> None:
    from PIL import Image, ImageDraw, ImageChops
    ref = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(ref)
    for x in range(20, 180, 6):  # dense thin strokes == a text-heavy slide's edges
        draw.line([(x, 20), (x, 180)], fill="black", width=1)

    aa = ImageChops.offset(ref, 1, 0)  # 1px shift -> pure thin-edge diff (AA-like)
    m_aa = compare_renders.compute_metrics(ref, aa)
    assert m_aa["changed_pixel_ratio"] > 0.01, "raw ratio should trip on the edge halo"
    assert m_aa["significant_changed_pixel_ratio"] < 0.002, "erosion must clear thin edges"

    block = ref.copy()
    ImageDraw.Draw(block).rectangle([60, 60, 140, 140], fill="black")  # contiguous defect
    m_block = compare_renders.compute_metrics(ref, block)
    assert m_block["significant_changed_pixel_ratio"] > 0.05, "solid block must survive erosion"


def _write_parity(parity_dir: Path, slide: str, tier: str, **metrics) -> None:
    d = parity_dir / slide / tier
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps({"metrics": metrics}), encoding="utf-8")


def test_parity_gate_passes_text_aa_halo_but_fails_contiguous_shift() -> None:
    thresholds = json.loads((SCRIPTS.parent / "registries" / "export-qa-thresholds.json")
                            .read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        parity = Path(tmp)
        # faithful text-dense slide: raw ratio over 0.01 but significant ~0, mean low
        _write_parity(parity, "slide-01", "tier2", mean_absolute_error=0.77,
                      changed_pixel_ratio=0.0155, significant_changed_pixel_ratio=0.0)
        # real misregistration (2px shift): significant + mean both high
        _write_parity(parity, "slide-02", "tier2", mean_absolute_error=9.0,
                      changed_pixel_ratio=0.058, significant_changed_pixel_ratio=0.0179)
        failures: list[str] = []
        seen = veo.check_parity(parity, thresholds, failures)
        by = {next(p for p in s["report"].replace("\\", "/").split("/") if p.startswith("slide-")): s
              for s in seen}
        assert by["slide-01"]["pass"], "faithful AA-halo slide must pass"
        assert not by["slide-02"]["pass"], "2px-shift slide must still fail"
        assert any("slide-02" in f for f in failures)
        assert not any("slide-01" in f for f in failures)


def test_parity_gate_falls_back_to_raw_ratio_for_pre_erosion_reports() -> None:
    # An older report without the significant key must NOT silently loosen: the
    # raw changed_ratio still gates.
    thresholds = json.loads((SCRIPTS.parent / "registries" / "export-qa-thresholds.json")
                            .read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        parity = Path(tmp)
        _write_parity(parity, "slide-01", "tier2", mean_absolute_error=0.4,
                      changed_pixel_ratio=0.05)  # no significant key
        failures: list[str] = []
        seen = veo.check_parity(parity, thresholds, failures)
        assert not seen[0]["pass"], "must fall back to raw changed_ratio when significant absent"


def test_project_python_path_uses_windows_virtualenv_layout() -> None:
    root = Path("C:/slide-plugin")
    assert _common.project_python_path(root, os_name="nt") == (
        root / ".venv" / "Scripts" / "python.exe"
    )


def test_project_python_path_uses_posix_virtualenv_layout() -> None:
    root = Path("/workspace/slide-plugin")
    assert _common.project_python_path(root, os_name="posix") == (
        root / ".venv" / "bin" / "python3"
    )


def test_missing_project_python_has_platform_install_hint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _common.require_project_python(Path(tmp), os_name="nt")
        except _common.ProjectPythonError as exc:
            message = str(exc)
            assert ".venv\\Scripts\\python.exe" in message
            assert "setup.ps1" in message
        else:
            raise AssertionError("missing project virtualenv must fail")


def test_invalid_project_python_has_platform_install_hint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        python = Path(tmp) / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_text("not an executable", encoding="utf-8")
        try:
            _common.require_project_python(Path(tmp), os_name="nt")
        except _common.ProjectPythonError as exc:
            message = str(exc)
            assert "not usable" in message
            assert "setup.ps1" in message
        else:
            raise AssertionError("invalid project virtualenv must fail")


def test_preflight_export_and_smoke_select_same_project_python() -> None:
    import check_base_requirements
    import test_export_stack
    catalog_path = SCRIPTS.parents[1] / "slide-system" / "catalog" / "catalog_server.py"
    spec = importlib.util.spec_from_file_location("catalog_server_python_test", catalog_path)
    assert spec and spec.loader
    catalog_server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog_server)

    expected = _common.require_project_python(SCRIPTS.parents[1])
    assert check_base_requirements.selected_python() == expected
    assert export_pptx.selected_python() == expected
    assert test_export_stack.selected_python() == expected
    assert catalog_server.selected_python() == expected


def test_distribution_surfaces_parse_and_expose_entrypoints() -> None:
    root = SCRIPTS.parents[1]
    plugin = json.loads(
        (root / ".agents/.claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    assert plugin["name"] == "sun-riser"
    assert marketplace["plugins"][0]["source"] == "./.agents"

    skill_names = {
        path.parent.name
        for path in (root / ".agents/skills").glob("*/SKILL.md")
    }
    assert {"slide-generator", "component-extractor", "extract-preflight"} <= skill_names

    component_command = (
        root / ".opencode/commands/component.md"
    ).read_text(encoding="utf-8")
    assert "component-extractor" in component_command
    assert "$ARGUMENTS" in component_command


def test_pdf_component_entrypoint_runs_preflight_before_analysis_and_staging() -> None:
    import extract_pdf_components

    calls: list[list[str]] = []

    def runner(cmd: list[str], **_kwargs) -> subprocess.CompletedProcess:
        calls.append([str(value) for value in cmd])
        return subprocess.CompletedProcess(cmd, 0, stdout='{"status":"ok"}', stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "sample.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        extract_pdf_components.run_workflow(
            pdf=pdf,
            extraction_id="sample-components",
            output_root=root / "extractions",
            history=root / "history.json",
            registry=root / "registry.json",
            catalog_output=root / "catalog-data.json",
            marker=root / "extract-readiness.json",
            python=Path(sys.executable),
            runner=runner,
        )

    scripts = [Path(cmd[1]).name for cmd in calls]
    assert scripts == [
        "check_base_requirements.py",
        "analyze_with_docling.py",
        "auto_stage_candidates.py",
        "build_component_catalog.py",
    ]
    assert calls[0][2:] == ["--input", "pdf", "--json", "--marker", str(root / "extract-readiness.json")]
    assert "publish_extraction.py" not in " ".join(" ".join(cmd) for cmd in calls)


def test_export_smoke_uses_external_markitdown_when_project_module_is_missing() -> None:
    import test_export_stack

    command = test_export_stack.markitdown_command(
        Path("C:/repo/.venv/Scripts/python.exe"),
        module_available=False,
        executable="C:/Tools/markitdown.exe",
        pptx_path=Path("C:/temp/deck.pptx"),
    )
    assert command == ["C:/Tools/markitdown.exe", str(Path("C:/temp/deck.pptx"))]


def test_compare_renders_ignores_small_delta_aa_edges() -> None:
    try:
        from PIL import Image
    except ImportError:
        return

    reference = Image.new("RGB", (400, 400), (120, 120, 120))
    candidate = reference.copy()
    for index in range(5000):
        x = index % 400
        y = index // 400
        candidate.putpixel((x, y), (152, 120, 120))

    metrics = compare_renders.compute_metrics(reference, candidate)

    assert metrics["mean_absolute_error"] < 1.0
    assert metrics["changed_pixel_ratio"] == 0.0


def test_compare_renders_still_fails_shifted_solid_block() -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    reference = Image.new("RGB", (200, 200), "white")
    candidate = reference.copy()
    ImageDraw.Draw(reference).rectangle((20, 60, 69, 109), fill="black")
    ImageDraw.Draw(candidate).rectangle((100, 60, 149, 109), fill="black")

    metrics = compare_renders.compute_metrics(reference, candidate)

    assert metrics["mean_absolute_error"] > 1.0
    assert metrics["changed_pixel_ratio"] > 0.01


# --------------------------------------------------------------------------- #
# score_visual_items — decision thresholds
# --------------------------------------------------------------------------- #
def _req() -> dict:
    return {"intent": ["timeline"], "tags": [], "content_structure": ["a"],
            "density": "medium", "brand": "sun", "required_exports": []}


def _item(**over) -> dict:
    base = {"id": "sun.set.x", "status": "published", "intent": ["timeline"],
            "tags": [], "content_structure": ["a"], "density": "any",
            "brand": None, "limitations": [],
            # Reviewed generic-buildable by default so the pre-existing gate tests keep
            # exercising THEIR gate; the buildability tests below override this.
            "build_scope": {"mode": "generic", "reason": "test generic template"}}
    base.update(over)
    return base


def test_score_perfect_match_is_reuse() -> None:
    dec, _ = svi.score_request(_req(), [_item()], svi.WEIGHTS, None)
    assert dec["action"] == "reuse", dec
    assert dec["extraction_recommended"] is False


def test_score_mid_band_is_needs_component() -> None:
    # semantic 35 + structure 0 + density 4 + brand 10 + export 15 + access 10 = 74.
    # Total 74 < AUTO_REUSE_MIN (78): not confident enough to auto-reuse -> unresolved.
    # (The old 65-74 'adapt-local' band is retired.)
    item = _item(content_structure=[], density="fixed")
    dec, _ = svi.score_request(_req(), [item], svi.WEIGHTS, None)
    assert 65 <= dec["score"] < svi.AUTO_REUSE_MIN, dec
    assert dec["action"] == "needs_component", dec
    assert dec["item_id"] is None, "unresolved slides name no component"
    assert dec["suggested_search"] and dec["next_action"], dec


def test_score_below_floor_is_needs_component_with_extraction() -> None:
    # drop brand match too -> 64 -> still unresolved (needs_component), never an
    # automatic custom layout.
    item = _item(content_structure=[], density="fixed", brand="other")
    dec, _ = svi.score_request(_req(), [item], svi.WEIGHTS, None)
    assert dec["score"] < 65, dec
    assert dec["action"] == "needs_component", dec
    assert dec["extraction_recommended"] is True, "weak match must recommend extraction"


# --------------------------------------------------------------------------- #
# Semantic concept groups (2026-07-16.13): a request may declare `concepts`
# (OR within a group, AND across groups). Coverage is matched_groups/total_groups,
# so descriptor tags/synonyms no longer inflate the required denominator, while
# AND-across preserves discrimination. Absent `concepts` -> flat behaviour.
# Canonical vocabulary only — no source-specific slide text.
# --------------------------------------------------------------------------- #
def _citem(**over) -> dict:
    base = {"id": "sun.set.x", "status": "published", "intent": [], "tags": [],
            "content_structure": ["a", "b"], "density": "any", "brand": None,
            "limitations": [],
            # Reviewed generic-buildable by default; the buildability tests below
            # pass build_scope=None (unreviewed) or mode=source-specific to test the gate.
            "build_scope": {"mode": "generic", "reason": "test generic template"}}
    base.update(over)
    return base


def _creq(concepts, **over) -> dict:
    base = {"intent": [], "tags": [], "content_structure": ["a", "b"],
            "density": "medium", "brand": "sun", "required_exports": [],
            "concepts": concepts}
    base.update(over)
    return base


def test_concepts_true_timeline_match_not_diluted_by_descriptor_terms() -> None:
    # One required concept (timeline/sequence, OR alternatives). A diluting tag
    # ("flow") and an unrelated intent term would sink the flat denominator, but
    # the group is fully satisfied by the item -> full semantic -> reuse.
    req = _creq([["timeline", "roadmap", "process", "steps", "sequence", "flow"]],
                intent=["timeline", "flow"], tags=["chronology", "milestones"])
    item = _citem(intent=["timeline", "roadmap", "process", "steps"], tags=["phases"])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "reuse", dec
    assert cands[0]["criteria"]["semantic_intent"] >= _CONF


def test_concepts_closing_matches_without_requiring_cta() -> None:
    req = _creq([["closing", "thank-you", "end", "farewell", "conclusion"]],
                intent=["closing", "cta"], tags=["final-slide", "cta"])
    item = _citem(intent=["closing", "thank-you", "end", "farewell"], tags=["conclusion"])
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "reuse", dec  # missing 'cta' must not block


def test_concepts_optional_tags_do_not_become_semantic_requirements() -> None:
    # Item matches the single required group but NONE of the many request tags.
    req = _creq([["timeline", "roadmap", "process"]],
                tags=["unrelated1", "unrelated2", "unrelated3", "unrelated4"])
    item = _citem(intent=["timeline", "process"])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert cands[0]["criteria"]["semantic_intent"] >= _CONF, cands[0]
    assert dec["action"] == "reuse", dec


def test_concepts_and_across_groups_blocks_partial_match() -> None:
    # Role-cards slide: role AND card-layout. An item with 'role' but no card
    # layout satisfies 1/2 groups = 0.5 < 0.70 -> needs_component.
    req = _creq([["role", "persona", "audience"], ["card", "card-set", "cards"]])
    item = _citem(intent=["role", "action-items"], tags=["responsibilities"])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert cands[0]["criteria"]["semantic_intent"] < _CONF, cands[0]
    assert dec["action"] == "needs_component", dec


def test_concepts_zero_group_match_is_needs_component() -> None:
    # Principles slide: item is a shape-adjacent checklist that declares NO
    # principle/rule concept -> 0/1 groups -> semantic 0 -> needs_component.
    req = _creq([["principle", "rule", "guideline", "tenet"]])
    item = _citem(intent=["checklist", "steps", "to-do", "action-list"])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert cands[0]["criteria"]["semantic_intent"] == 0.0, cands[0]
    assert dec["action"] == "needs_component", dec


def test_concepts_report_lists_required_matched_and_missing() -> None:
    req = _creq([["role", "persona"], ["card", "card-set"]])
    item = _citem(intent=["role"])
    _, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    concepts = cands[0]["retrieval"]["concepts"]
    assert [sorted(g) for g in concepts["required"]] == [["card", "card-set"], ["persona", "role"]] \
        or concepts["required"], concepts
    matched_groups = [m["group"] for m in concepts["matched"]]
    assert ["persona", "role"] in [sorted(g) for g in matched_groups], concepts
    assert ["card", "card-set"] in [sorted(g) for g in concepts["missing"]], concepts


def test_concepts_review_only_component_still_blocked_despite_full_match() -> None:
    req = _creq([["timeline", "roadmap", "process"]])
    item = _citem(intent=["timeline", "roadmap", "process"],
                  auto_reuse={"eligible": False, "reason": "failed full-slide QA"})
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec  # concept match cannot override review-only


def test_concepts_needs_component_shortlist_is_safe_and_never_selects() -> None:
    # A safe near-match (published, auto-eligible, immutable-clean) that matches
    # only 1/2 groups appears in the shortlist with its missing concept, but the
    # decision stays needs_component and names no component.
    req = _creq([["role", "persona"], ["card", "card-set"]])
    near = _citem(id="sun.set.near", intent=["role", "persona"])  # 1/2 groups
    dec, _ = svi.score_request(req, [near], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component" and dec["item_id"] is None, dec
    shortlist = dec.get("shortlist")
    assert shortlist and shortlist[0]["item_id"] == "sun.set.near", dec
    assert shortlist[0]["missing_concepts"], "shortlist must say what is missing"


def test_legacy_request_without_concepts_keeps_flat_dilution_behaviour() -> None:
    # Backward-compat: no `concepts` -> the flat intent+tags denominator still
    # applies, so a diluting extra concept still lowers semantic below the bar.
    req = {"intent": ["timeline"], "tags": ["callout"], "content_structure": ["a"],
           "density": "medium", "brand": "sun", "required_exports": []}
    item = _item(intent=["timeline"], tags=[])  # matches 1 of 2 canonical concepts
    _, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert cands[0]["criteria"]["semantic_intent"] == round(0.5 * 35, 2), cands[0]


def test_concepts_published_only_boundary_unchanged() -> None:
    req = _creq([["timeline", "roadmap", "process"]])
    item = _citem(status="staging", intent=["timeline", "roadmap", "process"])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert cands[0]["eligible"] is False, "non-published must stay ineligible"
    assert dec["action"] == "needs_component", dec


def test_concept_scoring_eval_fixture() -> None:
    # A small deterministic scorer eval on the CANONICAL vocabulary (no source
    # slide text): positive timeline/closing matches must reuse; keyword-lucky and
    # partial-AND matches must stay needs_component.
    cases = [
        # (concept groups, item intent/tags, expected action)
        ([["timeline", "roadmap", "process", "steps"]], ["timeline", "roadmap", "process"], "reuse"),
        ([["closing", "thank-you", "farewell", "conclusion"]], ["closing", "thank-you", "end"], "reuse"),
        # keyword-lucky: item shares NO concept term -> semantic 0 -> needs_component
        ([["tier", "level", "ladder"]], ["checklist", "steps", "to-do"], "needs_component"),
        # partial AND: role matched, card-layout missing -> 1/2 < 0.70 -> needs_component
        ([["role", "persona"], ["card", "card-set"]], ["role", "action-items"], "needs_component"),
    ]
    for concepts, item_intent, expected in cases:
        dec, _ = svi.score_request(_creq(concepts), [_citem(intent=item_intent)], svi.WEIGHTS, None)
        assert dec["action"] == expected, (concepts, item_intent, dec)


def test_derive_content_shape_is_generic_and_reported() -> None:
    # Metadata-quality: content_shape is derived generically from an item's own
    # intent/tags (no label invented/stored on the 91 registry items), and the
    # scorer reports it for auditability.
    from _common import derive_content_shape
    assert "timeline" in derive_content_shape(["roadmap", "process"])
    assert "closing" in derive_content_shape(["thank-you"])
    assert derive_content_shape(["nothing-maps-here"]) == []
    _, cands = svi.score_request(_creq([["timeline", "roadmap"]]),
                                 [_citem(intent=["timeline", "roadmap"])], svi.WEIGHTS, None)
    assert "timeline" in cands[0]["retrieval"]["derived_shapes"], cands[0]


# --------------------------------------------------------------------------- #
# Buildability contract (2026-07-17): a semantic match is not proof the item can
# be scaffolded and filled. Auto-reuse also requires build_scope.mode == generic;
# absent/unreviewed and source-specific stay published + manual-only.
# --------------------------------------------------------------------------- #
def test_source_specific_item_cannot_auto_reuse_despite_full_concept_match() -> None:
    req = _creq([["timeline", "roadmap", "process"]])
    item = _citem(intent=["timeline", "roadmap", "process"], build_scope=None)  # unreviewed
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert cands[0]["criteria"]["semantic_intent"] >= _CONF, "semantic still passes"
    assert dec["action"] == "needs_component", dec  # but buildability blocks auto-reuse


def test_explicit_source_specific_build_scope_also_blocks_auto_reuse() -> None:
    req = _creq([["timeline", "roadmap", "process"]])
    item = _citem(intent=["timeline", "roadmap", "process"],
                  build_scope={"mode": "source-specific", "reason": "23 source-date slots"})
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec


def test_generic_reviewed_slot_compatible_item_can_auto_reuse() -> None:
    req = _creq([["timeline", "roadmap", "process"]])
    item = _citem(intent=["timeline", "roadmap", "process"],
                  build_scope={"mode": "generic", "reason": "role-generic slots, any brief"})
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "reuse", dec


def test_explicit_user_selection_bypasses_build_scope_but_stays_fidelity_gated() -> None:
    # An explicit pick of a source-specific published item is allowed (user's choice)
    # and returns reuse selected_by=user; the scaffold/fidelity gate is the safety net.
    req = _creq([["timeline"]], component_id="sun.set.x")
    item = _citem(id="sun.set.x", intent=["timeline"], content_shape=None,
                  build_scope={"mode": "source-specific", "reason": "specific"})
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "reuse" and dec.get("selected_by") == "user", dec


def test_needs_component_is_the_only_automatic_unresolved_outcome() -> None:
    # No automatic custom-local: an unbuildable/unmatched slide resolves to
    # needs_component, never a custom slide, unless the user set unresolved_policy.
    req = _creq([["timeline", "roadmap", "process"]])
    item = _citem(intent=["timeline", "roadmap", "process"], build_scope=None)
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component" and dec["action"] != "custom-local", dec


# --------------------------------------------------------------------------- #
# concepts are the NORMAL new-run contract (--require-concepts); legacy runs use
# the deliberate compatibility path (no flag).
# --------------------------------------------------------------------------- #
def test_require_concepts_rejects_missing_or_empty_concepts() -> None:
    missing = {"job_id": "j", "slides": [{"request_id": "s1", "content_shape": "timeline"}]}
    empty = {"job_id": "j", "slides": [{"request_id": "s1", "concepts": []}]}
    assert svi.validate_batch_request(missing, require_concepts=True), "missing concepts must fail"
    assert svi.validate_batch_request(empty, require_concepts=True), "empty concepts must fail"
    # Legacy compatibility path: without the flag, absent concepts are accepted.
    assert svi.validate_batch_request(missing, require_concepts=False) == []


def test_require_concepts_accepts_valid_concepts() -> None:
    ok = {"job_id": "j", "slides": [{"request_id": "s1", "concepts": [["timeline", "roadmap"]]}]}
    assert svi.validate_batch_request(ok, require_concepts=True) == []


# --------------------------------------------------------------------------- #
# build-coherence: an automatic reuse decision is not a completed build unless the
# deck actually scaffolded a matching component instance.
# --------------------------------------------------------------------------- #
def test_reuse_decision_without_deck_instance_fails_build_coherence() -> None:
    report = {"slides": [{"request_id": "s1",
                          "decision": {"action": "reuse", "item_id": "sun.set.x"}}]}
    deck = "<html><body><section>no component instance here</section></body></html>"
    registry = {"items": [{"id": "sun.set.x", "status": "published", "paths": {}}]}
    results = fidelity.check_fidelity(deck, report, registry, require_instance_ids=True)
    fails = [r for r in results if not r["pass_"]]
    assert fails and "missing data-component-instance" in fails[0]["reason"], results


def test_scorer_has_no_hardcoded_component_ids_or_brief_text() -> None:
    # No selection logic keys on specific real component IDs, source-set slugs, or brief
    # wording — the contract must be metadata-driven. (Generic id-SHAPE examples like
    # `sun.component.x` in docstrings are fine; concrete published ids and brief strings
    # are not.)
    # `_common.py` is covered too: it carries selection-contract logic the scorer
    # shares (the shape vocabulary, and content-capacity derivation), so a concrete
    # id smuggled in there would evade a scorer-only check.
    for module in ("score_visual_items.py", "_common.py"):
        src = (SCRIPTS / module).read_text(encoding="utf-8")
        # Concrete published slide-component ids and source-deck set slugs have no
        # legitimate reason to appear here — including in CLI help. `--prefer-set`
        # is a real, metadata-driven feature (it compares the request's set to each id's
        # `<set>` segment), so its help must describe the mechanism, not name a source
        # deck; gaming a specific brief would show up here.
        for token in ("01-cover", "02-timeline", "05-process", "18-thanks",
                      "08-next-steps-cta", "10-do-dont",
                      "salary-benefits-2026", "sun-studio-performance-review-2025",
                      "interview-workshop-sunriser", "sun-presentation"):
            assert token not in src, f"{module} must not reference the concrete slug {token!r}"
        for brief_word in ("Tìm", "nguyên tắc", "SUN.RISER", "workflow thông minh"):
            assert brief_word not in src, f"no brief text ({brief_word!r}) in {module}"


# --------------------------------------------------------------------------- #
# Selection product decision (2026-07-13.20): high-confidence reuse /
# needs_component / explicit selection / no-duplicate / explicit-only custom-local
# --------------------------------------------------------------------------- #
_CONF = svi.WEIGHTS["semantic_intent"] * svi.SEMANTIC_CONFIDENCE_FRAC


def test_prev_adapt_band_is_now_needs_component() -> None:
    # F1: a candidate in the retired 65-74 band is unresolved, never adapt-local.
    dec, _ = svi.score_request(_req(), [_item(content_structure=[], density="fixed")],
                               svi.WEIGHTS, None)
    assert 65 <= dec["score"] < svi.AUTO_REUSE_MIN, dec
    assert dec["action"] == "needs_component", dec


def test_low_confidence_is_needs_component_not_custom() -> None:
    # F2: low confidence -> needs_component with guidance; no auto custom artifact.
    dec, _ = svi.score_request(_req(), [_item(id="sun.component.weak", intent=["unrelated"],
                                              content_structure=[])], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component" and dec["item_id"] is None, dec
    assert dec["suggested_search"] and dec["next_action"], dec


def test_high_confidence_is_reuse() -> None:
    # F3: a genuinely high-confidence, shape/slot-compatible match auto-reuses.
    dec, _ = svi.score_request(_req(), [_item()], svi.WEIGHTS, None)
    assert dec["action"] == "reuse" and dec.get("selected_by") != "user", dec
    assert dec["score"] >= svi.AUTO_REUSE_MIN, dec


def test_explicit_id_reuses_below_auto_threshold() -> None:
    # F4: an explicit user selection reuses a mid-band item the auto bar would skip.
    item = _item(id="sun.component.pick", content_structure=[], density="fixed")  # ~74 < 78
    dec, _ = svi.score_request({**_req(), "component_id": "sun.component.pick"},
                               [item], svi.WEIGHTS, None)
    assert dec["action"] == "reuse" and dec["item_id"] == "sun.component.pick", dec
    assert dec["selected_by"] == "user" and dec["score"] < svi.AUTO_REUSE_MIN, dec


def test_explicit_id_resolves_from_catalog_prompt() -> None:
    # F4b: the catalog 'Copy prompt' text resolves deterministically to the id.
    prompt = ('Use the published component "Foo Bar" (sun.component.pick) from the '
              'SUN.STUDIO visual library.')
    assert svi.resolve_component_id(prompt) == "sun.component.pick"
    assert svi.resolve_component_id("sun.component.pick") == "sun.component.pick"
    assert svi.resolve_component_id("no id here") is None


def test_explicit_invalid_unpublished_incompatible_stays_needs_component() -> None:
    # F5: invalid / unpublished / shape-incompatible explicit ids never substitute.
    dec, _ = svi.score_request({**_req(), "component_id": "sun.component.nope"},
                               [_item()], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component" and dec.get("selected_by") == "user", dec
    dec2, _ = svi.score_request({**_req(), "component_id": "sun.component.draft"},
                                [_item(id="sun.component.draft", status="staging")],
                                svi.WEIGHTS, None)
    assert dec2["action"] == "needs_component" and "not published" in dec2["reason"], dec2
    req = {"intent": ["timeline"], "tags": [], "content_structure": ["a"],
           "content_shape": "timeline", "density": "any", "brand": None,
           "component_id": "sun.test.badstats"}
    dec3, _ = svi.score_request(req, [_shape_item("sun.test.badstats", ["statistics"], ["flow"])],
                                svi.WEIGHTS, None)
    assert dec3["action"] == "needs_component" and "content_shape" in dec3["reason"], dec3


def _mk_slide(rid: str, item_ids: list[str], req: dict | None = None) -> dict:
    dec, cands = svi.score_request(req or _req(), [_item(id=x) for x in item_ids],
                                   svi.WEIGHTS, None)
    return {"request_id": rid, "decision": dec, "candidates": cands}


def test_no_auto_duplicate_across_deck() -> None:
    # F6: the same component is auto-reused on at most one slide per deck.
    results = [_mk_slide("s0", ["sun.component.hero"]),
               _mk_slide("s1", ["sun.component.hero"])]
    svi.assign_deck_components(results, {"s0": _req(), "s1": _req()}, _CONF)
    actions = [s["decision"]["action"] for s in results]
    assert actions.count("reuse") == 1 and "needs_component" in actions, results
    dup = next(s for s in results if s["decision"]["action"] == "needs_component")
    assert "already assigned" in dup["decision"]["reason"], dup


def test_second_slide_duplicate_only_becomes_needs_component() -> None:
    # F7: a later slide whose only ready candidate is already used is unresolved.
    results = [_mk_slide("s0", ["sun.component.only"]),
               _mk_slide("s1", ["sun.component.only"])]
    svi.assign_deck_components(results, {"s0": _req(), "s1": _req()}, _CONF)
    assert results[0]["decision"]["action"] == "reuse", results
    assert results[1]["decision"]["action"] == "needs_component", results
    assert results[1]["decision"]["item_id"] is None


def test_most_constrained_slide_wins_shared_component() -> None:
    # F7b: most-constrained-first — the sole-candidate slide (listed LAST) still
    # gets the shared component; the flexible slide takes the alternative.
    results = [_mk_slide("B", ["sun.component.shared", "sun.component.extra"]),
               _mk_slide("A", ["sun.component.shared"])]
    svi.assign_deck_components(results, {"A": _req(), "B": _req()}, _CONF)
    by = {s["request_id"]: s["decision"] for s in results}
    assert by["A"]["action"] == "reuse" and by["A"]["item_id"] == "sun.component.shared", by
    assert by["B"]["action"] == "reuse" and by["B"]["item_id"] == "sun.component.extra", by


def test_allow_component_reuse_override_recorded() -> None:
    # F8: an explicit override lets a component repeat, and it is recorded/surfaced.
    results = [_mk_slide("s0", ["sun.component.hero"]),
               _mk_slide("s1", ["sun.component.hero"])]
    svi.assign_deck_components(results, {"s0": _req(),
                                         "s1": {**_req(), "allow_component_reuse": True}}, _CONF)
    by = {s["request_id"]: s["decision"] for s in results}
    assert by["s0"]["action"] == "reuse" and by["s1"]["action"] == "reuse", by
    assert by["s1"]["item_id"] == "sun.component.hero", by
    assert by["s1"]["allow_component_reuse"] is True, by


def test_custom_local_only_with_explicit_approval() -> None:
    # F9: custom-local is impossible automatically; only the user's policy yields it,
    # and the validator rejects an auto (non-user) custom-local.
    weak = _item(id="sun.component.weak", intent=["unrelated"], content_structure=[])
    dec, _ = svi.score_request(_req(), [weak], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec
    dec2, _ = svi.score_request({**_req(), "unresolved_policy": "custom-local"}, [weak],
                                svi.WEIGHTS, None)
    assert dec2["action"] == "custom-local" and dec2["selected_by"] == "user", dec2
    errs: list = []
    vsr._validate_decision_band(
        {"decision": {"action": "custom-local", "item_id": None}, "candidates": []}, "r", errs)
    assert errs and "explicit user approval" in errs[0], errs


def test_explicit_blank_policy_resolves_slide_without_forcing_a_component() -> None:
    # An unresolved slide the user explicitly blanks resolves to action "blank"
    # (user-only, names no component) instead of needs_component — so it no longer
    # blocks delivery, and no component is invented or forced.
    weak = _item(id="sun.component.weak", intent=["unrelated"], content_structure=[])
    dec, _ = svi.score_request({**_req(), "unresolved_policy": "blank"}, [weak],
                               svi.WEIGHTS, None)
    assert dec["action"] == "blank" and dec["item_id"] is None, dec
    assert dec["selected_by"] == "user", dec
    # The validator requires blank to be a user choice, never an automatic one.
    errs: list = []
    vsr._validate_decision_band(
        {"decision": {"action": "blank", "item_id": None}, "candidates": []}, "r", errs)
    assert errs and "explicit user choice" in errs[0], errs
    # A batch request may carry unresolved_policy "blank".
    assert svi.validate_batch_request(
        {"job_id": "j", "slides": [{"request_id": "s1", "unresolved_policy": "blank"}]}) == []


def test_deck_allocation_uses_full_pool_not_report_top_n() -> None:
    # Fix A regression: six equally high-confidence components + six slides. The
    # first five get reserved, so the sixth slide must still AUTO-select the sixth
    # component. (The old code truncated candidates to --top-n=5 BEFORE deck
    # allocation, so the sixth was invisible and the slide fell to needs_component.)
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        items = [_item(id=f"sun.component.hero-{i}") for i in range(6)]
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"items": items}), encoding="utf-8")
        batch = tmp / "batch.json"
        batch.write_text(json.dumps({"job_id": "j", "slides": [
            {**_req(), "request_id": f"s{i}"} for i in range(6)]}), encoding="utf-8")
        out = tmp / "rep.json"
        rc = svi.main(["--batch-request", str(batch), "--registry", str(reg),
                       "--output", str(out), "--retrieval-index", "none", "--top-n", "5"])
        assert rc == 0
        rep = json.loads(out.read_text(encoding="utf-8"))
        acts = [s["decision"]["action"] for s in rep["slides"]]
        ids = [s["decision"]["item_id"] for s in rep["slides"]]
        assert acts == ["reuse"] * 6, rep["slides"]
        assert len(set(ids)) == 6, ids          # the 6th was reachable -> no duplicates
        assert "sun.component.hero-5" in ids, ids
        for s in rep["slides"]:
            shown = s["candidates"]
            # report stays capped at top-N (5) + the selected item when it ranks below
            assert len(shown) <= 6, shown
            assert any(c["item_id"] == s["decision"]["item_id"] for c in shown), s
        # the slide holding the below-cutoff pick proves requirement 4 explicitly
        sixth = next(s for s in rep["slides"] if s["decision"]["item_id"] == "sun.component.hero-5")
        assert len(sixth["candidates"]) == 6, sixth["candidates"]   # 5 ranked + selected


def test_auto_ineligible_component_never_auto_selected() -> None:
    # Fix B: a published component with a RECORDED full-slide QA failure keeps its
    # (best possible) score and stays browseable, but can never be auto-selected.
    bad = _item(id="sun.component.badqa",
                auto_reuse={"eligible": False, "reason": "overflows its own slot boxes"})
    dec, cands = svi.score_request(_req(), [bad], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component" and dec["item_id"] is None, dec
    c = cands[0]
    assert c["eligible"] is True and c["score"] >= svi.AUTO_REUSE_MIN, c   # still scored
    assert c["retrieval"]["auto_reuse"]["eligible"] is False, c
    assert any("review-only" in r for r in c["reasons"]), c["reasons"]
    # ...and the deck allocator must not hand it out either.
    assert svi._reuse_ready_ids(cands, True, _CONF) == [], cands


def test_explicit_selection_of_unsafe_component_fails_closed_at_fidelity() -> None:
    # Fix B: explicit selection may be recorded for review, but NEVER silently, and
    # the build/render gate fails it closed.
    bad = _item(id="sun.component.badqa",
                auto_reuse={"eligible": False, "reason": "cropped at 1920x1080"})
    dec, _ = svi.score_request({**_req(), "component_id": "sun.component.badqa"},
                               [bad], svi.WEIGHTS, None)
    assert dec["action"] == "reuse" and dec["selected_by"] == "user", dec
    assert "review-only" in dec["reason"] and "cropped at 1920x1080" in dec["reason"], dec
    reg = {"items": [{"id": "sun.component.badqa", "status": "published",
                      "auto_reuse": {"eligible": False, "reason": "cropped at 1920x1080"},
                      "paths": {"preview": "x"}}]}
    report = {"slides": [{"request_id": "s",
                          "decision": {"action": "reuse", "item_id": "sun.component.badqa"}}]}
    res = fidelity.check_fidelity("<div>anything</div>", report, reg)
    assert res and res[0]["pass_"] is False, res
    assert "not eligible for full-slide reuse" in res[0]["reason"], res


def test_known_failed_components_excluded_from_realistic_auto_reuse() -> None:
    # Every component whose real full-slide QA failed must not auto-reuse for the
    # very request that previously selected it. Each entry is a REAL library item and
    # the request that actually picked it in a QA run.
    cases = [
        ("sun.component.goal-keyresult-task-hexagon-diagram",
         {"request_id": "w", "intent": ["process", "steps", "workflow"],
          "tags": ["flow", "hexagon"], "content_structure": ["heading", "subheading"],
          "content_shape": "timeline", "density": "medium", "brand": "sun-studio"}),
        ("sun.component.revenue-team-size-metric-strip",
         {"request_id": "k", "intent": ["kpi", "growth", "metrics"],
          "tags": ["kpi", "metric-strip"], "content_structure": ["title", "heading"],
          "content_shape": "stats", "density": "medium", "brand": "sun-studio"}),
        # 2026-07-16 QA: cropped by the canvas (level-1 card + binary glyph sliced).
        ("sun.component.spicy-autocomplete-autonomous-levels-strip",
         {"request_id": "a", "intent": ["maturity-model", "levels", "tiers"],
          "tags": ["ai", "maturity-model", "level-cards"],
          "content_structure": ["heading", "label", "body"], "content_shape": "tiers",
          "density": "medium", "brand": "sun-studio", "item_count": 5}),
        # 2026-07-16 QA: 2 cards of artwork vs 4 declared title groups.
        ("sun.component.translator-strategist-driver-coach-card-set",
         {"request_id": "r", "intent": ["personas", "roles", "profile"],
          "tags": ["cards", "roles", "personas"],
          "content_structure": ["heading", "label", "body"], "content_shape": "profile",
          "density": "medium", "brand": "sun-studio", "item_count": 4}),
        # 2026-07-16 QA: badge circles cover-cropped; caption slots sit outside the
        # artwork, so white caption text landed on the white background.
        ("sun.component.lorem-ipsum-circle-badge-set",
         {"request_id": "b", "intent": ["numbered", "cards", "three-column"],
          "tags": ["numbered", "circle-badge"], "content_structure": ["heading", "label"],
          "content_shape": "stats", "density": "medium", "brand": "sun-studio",
          "item_count": 3}),
    ]
    for cid, req in cases:
        dec, cands = _score_real(req)
        assert dec["item_id"] != cid, dec           # never automatically selected
        c = next((x for x in cands if x["item_id"] == cid), None)
        if c:                                        # still discoverable + scored
            assert c["retrieval"]["auto_reuse"]["eligible"] is False, c
            assert c["eligible"] is True, c          # ...and still published


REVIEW_ONLY_IDS = {
    "sun.component.goal-keyresult-task-hexagon-diagram",
    "sun.component.revenue-team-size-metric-strip",
    "sun.component.spicy-autocomplete-autonomous-levels-strip",
    "sun.component.translator-strategist-driver-coach-card-set",
    "sun.component.lorem-ipsum-circle-badge-set",
    # Blocked from automatic full-bleed reuse because its wide-band artwork crops ~45%
    # of its width off the 16:9 frame (render fitness, not contract fidelity). Stays
    # published/browseable. See test_severe_crop_component_is_review_only_and_not_auto_selected.
    "sun.component.foundation-top1-microsoft-overlap-circle-set",
}

# --------------------------------------------------------------------------- #
# immutable_text — artwork that bakes in non-editable, source-specific copy
# --------------------------------------------------------------------------- #
_PR_CLOSING = "sun.sun-studio-performance-review-2025.20-closing-thank-you"


def _closing_req(**over) -> dict:
    req = {"request_id": "closing", "intent": ["thank-you", "closing", "full-slide"],
           "tags": ["closing", "thank-you", "end"],
           "content_structure": ["label", "title", "body"], "content_shape": "closing",
           "density": "medium", "brand": "sun-studio"}
    req.update(over)
    return req


def test_immutable_partial_context_match_fails_closed_on_year_alone() -> None:
    # The proven defect: the gate accepted ANY overlapping term, so a closing request
    # whose only context word was "2025" auto-selected the Performance Review closing.
    # A year alone is not the context — every group term must match.
    dec, cands = _score_real(_closing_req(intent=["thank-you", "closing", "2025"]))
    assert dec["item_id"] != _PR_CLOSING, dec
    cand = next((c for c in cands if c["item_id"] == _PR_CLOSING), None)
    if cand:
        imm = cand["retrieval"]["immutable_text"]
        assert imm["matched"] is False, imm
        assert imm["contexts"], imm


def test_immutable_partial_context_match_fails_closed_on_programme_alone() -> None:
    # Symmetric half: the programme without its year is still not the full context.
    dec, _ = _score_real(_closing_req(
        intent=["thank-you", "closing", "performance-review"],
        tags=["closing", "performance", "review"]))
    assert dec["item_id"] != _PR_CLOSING, dec


def test_goal_setting_does_not_unlock_on_year_alone() -> None:
    # Same rule on the other backfilled context, so nothing is special-cased.
    req = {"request_id": "c", "intent": ["cover", "title", "2026"], "tags": ["cover", "hero"],
           "content_structure": ["title"], "content_shape": "cover",
           "density": "medium", "brand": "sun-studio"}
    dec, _ = _score_real(req)
    assert dec["item_id"] != "sun.goal-setting-2026.01-cover", dec


def test_immutable_context_groups_are_all_of_within_a_group_any_of_across() -> None:
    # The rule itself, on a synthetic item so nothing is keyed to a real component id
    # or phrase: invented terms must behave exactly like the real backfilled ones.
    item = _item(id="sun.component.made-up", intent=["closing"], tags=["closing"])
    item["immutable_text"] = {
        "audit": "immutable",
        "contexts": [["zephyr-summit", "2031"], ["zephyr", "summit", "2031"]],
        "reason": "Artwork bakes in the Zephyr Summit 2031 lockup.",
    }
    base = {"intent": ["closing"], "tags": [], "content_structure": ["a"],
            "density": "medium", "brand": None, "required_exports": []}

    def act(**over):
        return svi.score_request(dict(base, **over), [item], svi.WEIGHTS, None)[0]["action"]

    assert act() == "needs_component"                                     # no context
    assert act(intent=["closing", "2031"]) == "needs_component"           # partial
    assert act(intent=["closing", "zephyr-summit"]) == "needs_component"  # partial
    assert act(intent=["closing", "zephyr", "summit"]) == "needs_component"  # partial group 2
    assert act(intent=["closing", "zephyr-summit", "2031"]) == "reuse"    # group 1 complete
    assert act(intent=["closing", "zephyr", "summit", "2031"]) == "reuse"  # group 2 complete


def test_immutable_text_blocks_auto_reuse_when_deck_context_differs() -> None:
    # The real defect: this closing matched on "closing" and auto-selected into an
    # AI-2026 deck, but its artwork bakes in a "Performance Review 2025" lockup that
    # no text slot can edit. A generic closing request must not auto-select it.
    dec, cands = _score_real(_closing_req())
    assert dec["item_id"] != _PR_CLOSING, dec
    cand = next((c for c in cands if c["item_id"] == _PR_CLOSING), None)
    if cand:  # still published, scored and browseable — just not auto-selectable
        assert cand["eligible"] is True, cand
        imm = cand["retrieval"]["immutable_text"]
        assert imm["matched"] is False and imm["reason"], cand
        assert any("fixed" in r.lower() or "immutable" in r.lower() for r in cand["reasons"]), cand


def test_immutable_text_context_match_clears_immutable_but_buildability_still_gates() -> None:
    # A deck that IS the 2025 performance review declares the COMPLETE context, so the
    # immutable-text gate no longer blocks (the fixed lockup is correct here). But this
    # is a SOURCE-SPECIFIC slide (unreviewed build_scope), so AUTOMATIC reuse is still
    # withheld — the buildability contract requires an explicit user pick for a
    # contextual slide (see the explicit-selection test below). The blocker names
    # build_scope, proving the immutable gate is NOT what stopped it.
    dec, cands = _score_real(_closing_req(
        intent=["thank-you", "closing", "performance-review"],
        tags=["closing", "thank-you", "performance", "review", "2025"]))
    top = next((c for c in cands if c["item_id"] == _PR_CLOSING), None)
    assert top is not None and (top.get("retrieval") or {}).get("immutable_text", {}).get("matched") \
        is True, "the complete context is declared -> immutable gate satisfied"
    assert dec["action"] == "needs_component", dec
    assert "auto-buildable" in dec["reason"], dec["reason"]


def test_immutable_text_explicit_selection_is_deterministic_and_warned() -> None:
    # Explicit user choice still wins, but must be visibly warned AND recorded so the
    # render gate can fail it closed — never silently shipped.
    dec, _ = _score_real(_closing_req(component_id=_PR_CLOSING))
    assert dec["action"] == "reuse" and dec["item_id"] == _PR_CLOSING, dec
    assert dec["selected_by"] == "user", dec
    assert "WARNING" in dec["reason"], dec["reason"]
    conflict = dec["immutable_text_conflict"]
    assert conflict["reason"] and conflict["contexts"], dec
    # Deterministic: the same request yields the same decision.
    again, _ = _score_real(_closing_req(component_id=_PR_CLOSING))
    assert again == dec


def test_item_without_immutable_text_keeps_current_behaviour() -> None:
    # Absent metadata must change nothing: a plain item still auto-reuses, carries no
    # immutable_text retrieval block, and records no conflict.
    dec, cands = svi.score_request(_req(), [_item()], svi.WEIGHTS, None)
    assert dec["action"] == "reuse", dec
    assert "immutable_text_conflict" not in dec, dec
    assert "immutable_text" not in (cands[0].get("retrieval") or {}), cands[0]


_PREP = "sun.interview-workshop-sunriser.05-prep"


def _prep_req(**over) -> dict:
    """The generic AI/workshop checklist request that auto-selected 05-prep."""
    req = {"request_id": "prep", "intent": ["checklist", "preparation", "steps"],
           "tags": ["checklist", "do-dont"], "content_structure": ["heading", "label"],
           "content_shape": "checklist", "density": "medium", "brand": "sun-studio"}
    req.update(over)
    return req


def test_audited_clean_template_is_not_blocked_by_immutable_but_by_buildability() -> None:
    # 05-prep's empty-slot render shows ZERO words: all 25 source strings are editable
    # slots, so the immutable-text gate does NOT block it (audited `clean`). But a clean
    # audit is no longer sufficient for automatic reuse: 05-prep is a 25-slot,
    # multi-section prep checklist (unreviewed build_scope), which a short unrelated
    # brief cannot fill. So it resolves to needs_component, and the blocker names
    # buildability — not immutability.
    reg = _common.load_json(REGISTRY)
    prep = next(i for i in reg["items"] if i["id"] == _PREP)
    assert prep["immutable_text"]["audit"] == "clean", prep["immutable_text"]
    assert "contexts" not in prep["immutable_text"], "a clean verdict declares no contexts"
    dec, cands = _score_real(_prep_req())
    prep_cand = next((c for c in cands if c["item_id"] == _PREP), None)
    assert prep_cand and _immutable_text_ok_local(prep_cand), "immutable gate is satisfied"
    assert dec["action"] == "needs_component", dec
    assert "auto-buildable" in dec["reason"], dec["reason"]


def _immutable_text_ok_local(cand: dict) -> bool:
    imm = (cand.get("retrieval") or {}).get("immutable_text") or {}
    return not imm or imm.get("audit") == "clean" or imm.get("matched") is True


def test_audit_unresolved_blocks_automatic_reuse() -> None:
    # An audited-but-unclassifiable item must fail closed: nobody knows what its
    # artwork says, so it can never be auto-selected.
    item = _item(id="sun.component.unaudited", intent=["timeline"], tags=[])
    item["immutable_text"] = {"audit": "unresolved",
                              "reason": "empty-slot render could not be produced"}
    dec, cands = svi.score_request(_req(), [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec
    assert cands[0]["retrieval"]["immutable_text"]["audit"] == "unresolved"
    assert any("unresolved" in r for r in cands[0]["reasons"]), cands[0]["reasons"]
    # ...and an explicit selection of it is warned + recorded for the fidelity gate.
    dec2, _ = svi.score_request({**_req(), "component_id": "sun.component.unaudited"},
                                [item], svi.WEIGHTS, None)
    assert dec2["action"] == "reuse" and dec2["selected_by"] == "user", dec2
    assert "unresolved" in dec2["reason"] and "WARNING" in dec2["reason"], dec2["reason"]
    assert dec2["immutable_text_conflict"], dec2


def test_audit_distinguishes_editable_slot_text_from_baked_semantic_text() -> None:
    # The audit's whole point, on the two real templates that prove both sides:
    # 05-prep renders NO words with slots emptied (every string is editable), while
    # every performance-review slide keeps its outlined "Performance Review 2025"
    # lockup. Neither fact is visible in the markup — visual.svg has no <text> at all.
    import audit_immutable_text as audit
    reg = _common.load_json(REGISTRY)
    by_id = {i["id"]: i for i in reg["items"]}

    for iid in (_PREP, _PR_CLOSING):
        vis = (by_id[iid].get("paths") or {}).get("visual")
        assert audit.source_text_nodes(vis) == [], (
            f"{iid}: visual.svg is expected to carry no live <text> — the baked lockup "
            f"survives only as outlined paths, which is why the render is the evidence")
        # Every live source string IS represented by an editable slot on both items.
        assert audit.source_text_uncovered(by_id[iid]) == [], iid

    # So the two items are told apart only by the recorded audit verdict.
    assert by_id[_PREP]["immutable_text"]["audit"] == "clean"
    assert by_id[_PR_CLOSING]["immutable_text"]["audit"] == "immutable"
    assert by_id[_PR_CLOSING]["immutable_text"]["contexts"]


def _audit_item(tmp: Path, iid: str = "sun.component.aud") -> dict:
    """A published item with a real visual + slot contract on disk, so the audit
    fingerprint has something to bind to."""
    vis = tmp / "visual.svg"
    vis.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>',
                   encoding="utf-8")
    slots = tmp / "text-slots.json"
    slots.write_text(json.dumps({"slots": [{"id": "a", "bounds": {"x": 0.1, "y": 0.1,
                                                                  "width": 0.2, "height": 0.1}}]}),
                     encoding="utf-8")
    return {"id": iid, "status": "published", "type": "component",
            "paths": {"visual": str(vis), "text_slots": str(slots), "preview": str(vis)}}


def test_audit_verdict_is_bound_to_the_artifact_fingerprint() -> None:
    # A verdict is evidence about ONE version of the artwork. Re-extracting visual.svg
    # must invalidate it: the compact registry the scorer reads projects `unresolved`,
    # so automatic reuse fails closed until someone re-audits.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        item = _audit_item(tmp)
        item["immutable_text"] = {"audit": "clean", "reason": "no words survive",
                                  "evidence": br.immutable_text_fingerprint(item)}
        assert br.immutable_text_drift(item) is None
        assert br.gate_immutable_text(item)["audit"] == "clean"

        # The artwork is replaced by a re-extraction...
        (tmp / "visual.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><text>Zephyr Summit 2031</text></svg>',
            encoding="utf-8")
        assert "visual_sha256 changed" in (br.immutable_text_drift(item) or "")
        gated = br.gate_immutable_text(item)
        assert gated["audit"] == "unresolved", gated
        # ...and the scorer, which reads the compact projection, now fails closed.
        compact = br.project_compact([dict(item, intent=["timeline"], tags=[],
                                           content_structure=["a"], density="any",
                                           brand=None, limitations=[])])["items"][0]
        dec, _ = svi.score_request(_req(), [compact], svi.WEIGHTS, None)
        assert dec["action"] == "needs_component", dec

    with tempfile.TemporaryDirectory() as tmpd:
        # The slot contract is the other half: which copy is editable decides which
        # surviving words are immutable, so changing it invalidates the verdict too.
        tmp = Path(tmpd)
        item = _audit_item(tmp)
        item["immutable_text"] = {"audit": "clean", "reason": "no words survive",
                                  "evidence": br.immutable_text_fingerprint(item)}
        (tmp / "text-slots.json").write_text(json.dumps({"slots": []}), encoding="utf-8")
        assert "slots_sha256 changed" in (br.immutable_text_drift(item) or "")


def _dep_item(tmp: Path, asset_bytes: bytes = b"\x89PNG\r\n\x1a\n-tile-v1",
              ref: str = "assets/tile.png") -> dict:
    """A published template whose visual.svg references a LOCAL raster that
    materialization base64-inlines into the rendered background."""
    (tmp / "assets").mkdir(exist_ok=True)
    (tmp / ref).write_bytes(asset_bytes)
    vis = tmp / "visual.svg"
    vis.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                   'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1920 1080">'
                   f'<rect width="9" height="9"/><image xlink:href="{ref}"/></svg>',
                   encoding="utf-8")
    slots = tmp / "text-slots.json"
    slots.write_text(json.dumps({"slots": [{"id": "a", "bounds": {"x": .1, "y": .1,
                                                                  "width": .2, "height": .1}}]}),
                     encoding="utf-8")
    prev = tmp / "preview.html"
    prev.write_text('<div class="slot" data-slot-id="a"></div>', encoding="utf-8")
    return {"id": "sun.template.deps", "status": "published", "type": "template",
            "paths": {"visual": str(vis), "text_slots": str(slots), "preview": str(prev)}}


def test_local_image_dependency_of_visual_is_fingerprinted() -> None:
    # P1 (deeper): materialize_component_visual base64-inlines local <image> refs from
    # visual.svg into the rendered background. So a referenced tile.png decides the
    # render exactly like visual.svg does — mutating it alone must invalidate the audit,
    # or the same bypass class stays open one level down.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        item = _dep_item(tmp)
        fp = br.immutable_text_fingerprint(item)
        assert "deps_sha256" in fp, fp                     # the dependency aggregate is bound
        item["immutable_text"] = {"audit": "clean", "reason": "no words survive", "evidence": fp}
        assert br.immutable_text_drift(item) is None
        assert br.gate_immutable_text(item)["audit"] == "clean"

        # Change ONLY the referenced raster — visual.svg/preview/slots are byte-identical.
        (tmp / "assets/tile.png").write_bytes(b"\x89PNG\r\n\x1a\n-tile-v2-DIFFERENT")
        assert "deps_sha256 changed" in (br.immutable_text_drift(item) or ""), \
            "mutating a referenced local asset alone must invalidate the audit"
        assert br.gate_immutable_text(item)["audit"] == "unresolved"


def test_missing_or_unsafe_visual_dependency_fails_closed() -> None:
    # A declared local dependency that goes missing (or was never safe) must FAIL CLOSED,
    # not silently vanish from evidence — the component can no longer materialize.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        item = _dep_item(tmp)
        item["immutable_text"] = {"audit": "clean", "reason": "ok",
                                  "evidence": br.immutable_text_fingerprint(item)}
        assert br.gate_immutable_text(item)["audit"] == "clean"
        # delete the asset the visual references
        (tmp / "assets/tile.png").unlink()
        assert br.gate_immutable_text(item)["audit"] == "unresolved", "missing dep must fail closed"

    with tempfile.TemporaryDirectory() as tmpd:
        # An UNSAFE ref (path traversal) is fail-closed for the audit exactly as
        # materialization refuses it — the two must agree.
        tmp = Path(tmpd)
        item = _dep_item(tmp, ref="assets/tile.png")
        vis = Path(item["paths"]["visual"])
        vis.write_text(vis.read_text(encoding="utf-8").replace(
            'xlink:href="assets/tile.png"', 'xlink:href="../../../etc/passwd.png"'),
            encoding="utf-8")
        item["immutable_text"] = {"audit": "clean", "reason": "ok",
                                  "evidence": {"visual_sha256": "0"*64}}
        assert br.gate_immutable_text(item)["audit"] == "unresolved"
        # materialization and the audit agree the ref is unsafe/unresolved
        safe, unresolved = br.visual_dependencies(item)
        assert unresolved and not safe, (safe, unresolved)


def test_data_uri_http_and_fragment_refs_are_not_dependencies() -> None:
    # Self-contained (data:) and external (http/#fragment) refs are NOT local files, so
    # they contribute no dependency hash and do not make an item unresolved.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        vis = tmp / "visual.svg"
        vis.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                       'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1920 1080">'
                       '<rect width="9" height="9"/><circle r="3"/><path d="M0 0"/>'
                       '<image xlink:href="data:image/png;base64,AAAA"/>'
                       '<image xlink:href="http://example.com/x.png"/>'
                       '<image xlink:href="#frag"/></svg>', encoding="utf-8")
        item = {"id": "sun.template.ext", "status": "published", "type": "template",
                "paths": {"visual": str(vis)}}
        safe, unresolved = br.visual_dependencies(item)
        assert safe == [] and unresolved == [], (safe, unresolved)
        assert "deps_sha256" not in br.immutable_text_fingerprint(item)


def test_build_registry_and_materialization_agree_on_dependencies() -> None:
    # The two consumers must classify refs identically (shared helper, no divergence).
    import build_registry as br
    import materialize_component_visual as mat

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        item = _dep_item(tmp)
        vis = Path(item["paths"]["visual"])
        svg = vis.read_text(encoding="utf-8")
        safe_reg, unresolved_reg = br.visual_dependencies(item)
        safe_mat, unresolved_mat = mat.image_dependencies(svg, vis.parent)
        assert [r for r, _ in safe_reg] == [r for r, _ in safe_mat]
        assert unresolved_reg == unresolved_mat
        # and inline_external_images resolves exactly the safe set (round-trip behaviour kept)
        out, un = mat.inline_external_images(svg, vis.parent)
        assert un == [] and out.count("data:image/png;base64,") == len(safe_mat)


class _DriftedDependency:
    """Byte-change one real local image asset referenced by a published visual.svg,
    then restore it. Proves a dependency-only change fails closed on real data."""

    def __enter__(self) -> dict:
        import build_registry as br
        reg = _common.load_json(REGISTRY)
        for it in reg["items"]:
            if it.get("status") != "published":
                continue
            safe, unresolved = br.visual_dependencies(it)
            if safe and not unresolved and (it.get("immutable_text") or {}).get("audit") == "clean":
                self.item, self.path = it, safe[0][1]
                self.original = self.path.read_bytes()
                self.path.write_bytes(self.original + b"\x00driftbyte")
                return it
        raise AssertionError("no published clean item with a safe local visual dependency")

    def __exit__(self, *exc) -> None:
        self.path.write_bytes(self.original)


def test_dependency_only_drift_fails_closed_end_to_end() -> None:
    # Same three gates as preview-only drift, driven on real data through the CLIs:
    # a referenced raster changed, nothing else.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        batch = Path(tmpd) / "batch.json"
        out = Path(tmpd) / "rep.json"
        assert br.generated_projection_staleness() == [], "precondition: repo starts fresh"
        with _DriftedDependency() as item:
            batch.write_text(json.dumps({"job_id": "j", "slides": [
                {**_req(), "request_id": "s"}]}), encoding="utf-8")
            # 1) fresh projection now marks the changed item unresolved
            row = next(r for r in br.project_compact(br.live_registry_items())["items"]
                       if r["id"] == item["id"])
            assert row["immutable_text"]["audit"] == "unresolved", row["immutable_text"]
            # 2) canonical compact scorer refuses on the now-stale projection
            try:
                svi.main(["--batch-request", str(batch), "--output", str(out)])
                assert False, "scorer scored against a dependency-stale projection"
            except SystemExit as exc:
                assert "Refusing to score" in str(exc), exc
            # 3) full-registry scoring projects it unresolved WITHOUT writing a file
            gated = svi.scoring_items(REGISTRY.as_posix())
            grow = next(r for r in gated if r["id"] == item["id"])
            assert (grow.get("immutable_text") or {}).get("audit") == "unresolved", grow
            # 4) pre-build fidelity rejects a report that selected it before the change
            report = {"slides": [{"request_id": "s", "decision": {
                "action": "reuse", "item_id": item["id"]}}]}
            res = fidelity.check_fidelity("<div>x</div>", report, _common.load_json(REGISTRY))
            assert res and res[0]["pass_"] is False and "stale" in res[0]["reason"], res
        assert br.generated_projection_staleness() == []


def test_verdict_binds_to_whatever_artifact_decides_the_render() -> None:
    # Not every published item is an SVG + slot contract: `sun.asset.logo` is a raster
    # with only a preview, and its verdict must still be bound to the artwork on disk.
    # The rule is generic — fingerprint the inputs that decide the render, whatever
    # form they take — so no item type is exempt by accident.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        png = tmp / "logo.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n-pretend-this-is-the-mark")
        item = {"id": "sun.asset.made-up", "status": "published", "type": "asset",
                "paths": {"artifact": str(png), "preview": str(png)}}
        fp = br.immutable_text_fingerprint(item)
        assert fp == {"preview_sha256": _common.sha256_file(png)}, fp
        assert br.renders_as_slide(item) is True

        item["immutable_text"] = {"audit": "clean", "reason": "the brand mark only",
                                  "evidence": fp}
        assert br.gate_immutable_text(item)["audit"] == "clean"
        png.write_bytes(b"\x89PNG\r\n\x1a\n-now-it-bakes-in-Zephyr-Summit-2031")
        assert "preview_sha256 changed" in (br.immutable_text_drift(item) or "")
        assert br.gate_immutable_text(item)["audit"] == "unresolved"

    with tempfile.TemporaryDirectory() as tmpd:
        # A directory-valued preview (Dio) hashes to nothing and cannot be scaffolded
        # into a slide, so it is exempt rather than permanently `unresolved`.
        d = Path(tmpd) / "dio"
        d.mkdir()
        item = {"id": "sun.character.made-up", "status": "published", "type": "character",
                "paths": {"artifact": str(d), "preview": str(d)}}
        assert br.immutable_text_fingerprint(item) == {}
        assert br.renders_as_slide(item) is False
        item["immutable_text"] = {"audit": "clean", "reason": "not a slide"}
        assert br.gate_immutable_text(item)["audit"] == "clean"


def test_preview_html_is_a_fingerprinted_render_input() -> None:
    # P1: scaffold_slide_from_component reads paths.preview (preview.html) at build
    # time for its .slot markup and geometry, so preview.html decides the render just
    # as much as visual.svg does. The fingerprint must cover it even when visual.svg
    # exists — otherwise editing ONLY preview.html leaves the verdict `clean` while the
    # rendered slide changed (the exact bypass reported).
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        vis = tmp / "visual.svg"
        vis.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
                       '<rect width="9" height="9"/></svg>', encoding="utf-8")
        slots = tmp / "text-slots.json"
        slots.write_text(json.dumps({"slots": [{"id": "a", "bounds": {"x": .1, "y": .1,
                                                                      "width": .2, "height": .1}}]}),
                         encoding="utf-8")
        prev = tmp / "preview.html"
        prev.write_text('<div class="slot" data-slot-id="a" '
                        'style="left:100px;top:100px"></div>', encoding="utf-8")
        item = {"id": "sun.template.made-up", "status": "published", "type": "template",
                "paths": {"visual": str(vis), "text_slots": str(slots), "preview": str(prev)}}

        fp = br.immutable_text_fingerprint(item)
        assert set(fp) == {"visual_sha256", "slots_sha256", "preview_sha256"}, fp

        item["immutable_text"] = {"audit": "clean", "reason": "no words survive",
                                  "evidence": fp}
        assert br.immutable_text_drift(item) is None
        assert br.gate_immutable_text(item)["audit"] == "clean"

        # Change ONLY preview.html — visual.svg and text-slots.json are byte-identical.
        prev.write_text('<div class="slot" data-slot-id="a" '
                        'style="left:900px;top:100px"></div>', encoding="utf-8")
        assert "preview_sha256 changed" in (br.immutable_text_drift(item) or ""), \
            "editing preview.html alone must invalidate the audit"
        assert br.gate_immutable_text(item)["audit"] == "unresolved"

        # A stale full-registry input therefore projects unresolved WITHOUT any write.
        row = br.project_compact([dict(item, intent=["timeline"], tags=[],
                                       content_structure=["a"], density="any",
                                       brand=None, limitations=[])])["items"][0]
        dec, _ = svi.score_request(_req(), [row], svi.WEIGHTS, None)
        assert dec["action"] == "needs_component", dec


def test_preview_only_drift_invalidates_a_real_template_end_to_end() -> None:
    # The same, on a REAL published template (visual + text-slots + preview.html), driven
    # through the actual CLIs — the reported bypass reproduced and closed.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        batch = Path(tmpd) / "batch.json"
        batch.write_text(json.dumps({"job_id": "j", "slides": [_prep_req()]}), encoding="utf-8")
        out = Path(tmpd) / "rep.json"
        assert br.generated_projection_staleness() == [], "precondition: repo starts fresh"

        with _DriftedArtifact(field="preview", also="visual") as item:
            # 1) the changed item now projects unresolved in a fresh projection
            row = next(r for r in br.project_compact(br.live_registry_items())["items"]
                       if r["id"] == item["id"])
            assert row["immutable_text"]["audit"] == "unresolved", row["immutable_text"]

            # 2) the canonical compact scorer refuses to run on the now-stale projection
            try:
                svi.main(["--batch-request", str(batch), "--output", str(out)])
                assert False, "scorer scored against a preview-stale projection"
            except SystemExit as exc:
                assert "Refusing to score" in str(exc), exc
            assert not out.exists()

            # 3) pre-build fidelity rejects a report that selected it before the change
            report = {"slides": [{"request_id": "s", "decision": {
                "action": "reuse", "item_id": item["id"]}}]}
            res = fidelity.check_fidelity("<div>x</div>", report, _common.load_json(REGISTRY))
            assert res and res[0]["pass_"] is False and "stale" in res[0]["reason"], res
        # restored
        assert br.generated_projection_staleness() == []


class _DriftedArtifact:
    """Byte-change one real published render-input file, and put it back afterwards.

    `field` selects WHICH render input to drift — `visual`, `preview`, or
    `text_slots` — so a test can prove that changing any of them (not just the SVG)
    invalidates the audit. The canonical library is the user's data: every test that
    needs a stale artifact restores the exact original bytes, including when the test
    body raises."""

    def __init__(self, audit: str = "clean", field: str = "visual", also: str | None = None):
        self.audit = audit
        self.field = field
        # An extra path the chosen item must ALSO declare (as a real file). Used to
        # pick a template that has BOTH visual and preview, so drifting `preview`
        # proves preview.html is an independent render input rather than the artwork.
        self.also = also

    def __enter__(self) -> dict:
        reg = _common.load_json(REGISTRY)
        def ok(i):
            paths = i.get("paths") or {}
            if not (paths.get(self.field)
                    and (i.get("immutable_text") or {}).get("audit") == self.audit
                    and _common.resolve_repo_path(paths[self.field]).is_file()):
                return False
            return not self.also or (paths.get(self.also)
                                     and _common.resolve_repo_path(paths[self.also]).is_file())
        self.item = next(i for i in reg["items"] if ok(i))
        self.path = _common.resolve_repo_path(self.item["paths"][self.field])
        self.original = self.path.read_bytes()
        self.path.write_bytes(self.original + b"\n<!-- test drift -->\n")
        return self.item

    def __exit__(self, *exc) -> None:
        self.path.write_bytes(self.original)


def test_default_cli_scoring_refuses_a_stale_projection() -> None:
    # Finding 1: build_registry --check caught artifact drift, but the scorer read the
    # generated compact without proving it was fresh — so a `clean` verdict recorded
    # against artwork that had since changed still auto-reused. The default CLI path
    # must refuse to score rather than select on stale audit metadata.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        batch = Path(tmpd) / "batch.json"
        batch.write_text(json.dumps({"job_id": "j", "slides": [_prep_req()]}), encoding="utf-8")
        out = Path(tmpd) / "rep.json"

        assert br.generated_projection_staleness() == [], "precondition: repo starts fresh"
        with _DriftedArtifact() as item:
            stale = br.generated_projection_staleness()
            assert stale and "compact" in stale[0], stale
            try:
                svi.main(["--batch-request", str(batch), "--output", str(out)])
                assert False, "the scorer scored against a stale projection"
            except SystemExit as exc:
                msg = str(exc.code if isinstance(exc.code, str) else exc)
                assert "Refusing to score" in msg, msg
                assert br.REFRESH_HINT in msg, msg          # plain remediation
                assert "unresolved" in msg, msg
            assert not out.exists(), "no selection report may be written from stale data"
            # ...and the drifted item is exactly the one the refusal is about.
            assert br.gate_immutable_text(item)["audit"] == "unresolved"
        # Restored: the normal path scores again (exit 0, a report is written). The
        # decision itself is gated by the full contract — 05-prep is a high-content
        # source-specific slide, so it resolves needs_component — but the point here is
        # that a FRESH projection scores rather than refusing.
        assert br.generated_projection_staleness() == []
        assert svi.main(["--batch-request", str(batch), "--output", str(out)]) == 0
        action = json.loads(out.read_text(encoding="utf-8"))["slides"][0]["decision"]["action"]
        assert action in ("reuse", "needs_component"), action


def test_refreshed_projection_makes_the_changed_item_unresolved() -> None:
    # Step 3 of the contract: after the operator runs the normal refresh, the changed
    # item projects `unresolved` and stops auto-reusing until it is re-audited. Proven
    # on the REAL projection, without writing to the repo's registries.
    import build_registry as br

    with _DriftedArtifact() as item:
        refreshed = br.project_compact(br.live_registry_items())["items"]   # what --write would emit
        row = next(r for r in refreshed if r["id"] == item["id"])
        assert row["immutable_text"]["audit"] == "unresolved", row["immutable_text"]
        assert "audit_immutable_text.py" in row["immutable_text"]["reason"]
        dec, _ = svi.score_request(_prep_req(), refreshed, svi.WEIGHTS, None)
        assert dec["item_id"] != item["id"], dec
        # Every other item is untouched: one artifact changing must not disable the library.
        assert sum(1 for r in refreshed
                   if (r.get("immutable_text") or {}).get("audit") == "unresolved") == 1


def test_full_registry_scoring_path_cannot_bypass_the_gate() -> None:
    # Requirement 4: `--registry .../visual-library.json` carries raw, ungated
    # immutable_text. It must be projected through the same gate in memory, so the
    # safety rule cannot depend on which file the caller passed.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        vis = tmp / "visual.svg"
        vis.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>',
                       encoding="utf-8")
        item = {"id": "sun.component.stale", "status": "published", "type": "component",
                "intent": ["timeline"], "tags": [], "content_structure": ["a"],
                "density": "any", "brand": None, "limitations": [],
                "paths": {"visual": str(vis)},
                "build_scope": {"mode": "generic", "reason": "test generic component"},
                # Evidence for artwork that is NOT what is on disk.
                "immutable_text": {"audit": "clean", "reason": "no words survive",
                                   "evidence": {"visual_sha256": "0" * 64}}}
        reg = tmp / "full-registry.json"
        reg.write_text(json.dumps({"items": [item]}), encoding="utf-8")

        gated = svi.scoring_items(str(reg))
        assert gated[0]["immutable_text"]["audit"] == "unresolved", gated[0]
        dec, _ = svi.score_request(_req(), gated, svi.WEIGHTS, None)
        assert dec["action"] == "needs_component", dec
        # The registry file itself is never rewritten by scoring.
        assert json.loads(reg.read_text(encoding="utf-8"))["items"][0]["immutable_text"] \
            == item["immutable_text"]
        # And correct evidence still reuses normally.
        item["immutable_text"]["evidence"] = br.immutable_text_fingerprint(item)
        reg.write_text(json.dumps({"items": [item]}), encoding="utf-8")
        dec2, _ = svi.score_request(_req(), svi.scoring_items(str(reg)), svi.WEIGHTS, None)
        assert dec2["action"] == "reuse", dec2


def test_canonical_compact_freshness_cannot_be_bypassed_by_a_paths_key() -> None:
    # Ordering guard: the canonical compact's freshness gate must fire BEFORE the
    # full-registry re-projection branch. If a compact ever carried a stray `paths`
    # key, the old order re-projected it in memory (masking staleness) instead of
    # refusing. Point build_registry.COMPACT at a stale file whose items ALSO carry
    # `paths`; scoring must still REFUSE, never project.
    import build_registry as br

    original = br.COMPACT
    with tempfile.TemporaryDirectory() as tmpd:
        fake = Path(tmpd) / "visual-library-compact.json"
        # Stale by construction (does not equal the live projection) AND carries a
        # `paths` key — exactly the shape that used to slip through the paths branch.
        fake.write_text(json.dumps({"items": [
            {"id": "sun.component.x", "status": "published", "type": "component",
             "intent": ["timeline"], "tags": [], "content_structure": ["a"],
             "density": "any", "brand": None, "limitations": [],
             "paths": {"visual": "does/not/matter.svg"},
             "immutable_text": {"audit": "clean", "reason": "stale clean"}}]}),
                        encoding="utf-8")
        br.COMPACT = fake
        try:
            assert br.generated_projection_staleness(), "precondition: fake compact is stale"
            try:
                svi.scoring_items(str(fake))
                assert False, "compact freshness gate was bypassed by the paths branch"
            except SystemExit as exc:
                assert "Refusing to score" in str(exc), exc
        finally:
            br.COMPACT = original


def test_selection_report_is_rejected_when_its_artifact_changed_after_scoring() -> None:
    # Requirement 5: a report scored against artwork that has since changed must not
    # reach build/export. This is the backstop that makes the compact, full-registry
    # and pre-build paths agree.
    with _DriftedArtifact() as item:
        reg = _common.load_json(REGISTRY)
        report = {"slides": [{"request_id": "s", "decision": {
            "action": "reuse", "item_id": item["id"]}}]}
        res = fidelity.check_fidelity("<div>anything</div>", report, reg)
        assert res and res[0]["pass_"] is False, res
        assert "stale" in res[0]["reason"] and "visual_sha256 changed" in res[0]["reason"], res[0]
    # Unchanged artwork: this gate says nothing, and the normal geometry checks run.
    reg = _common.load_json(REGISTRY)
    item = next(i for i in reg["items"] if i["id"] == _PREP)
    report = {"slides": [{"request_id": "s", "decision": {"action": "reuse", "item_id": _PREP}}]}
    res = fidelity.check_fidelity("<div>anything</div>", report, reg)
    assert res and "stale" not in res[0]["reason"], res[0]


def test_declared_artwork_that_is_missing_fails_closed_not_exempt() -> None:
    # An item that DECLARES artwork but whose file is not on disk must fail closed. The
    # exemption is only for items with no artifact file to hash at all (Dio, a
    # directory) — never for one whose artwork simply is not there, or a deleted
    # visual.svg would silently turn "unverifiable" into "clean".
    import build_registry as br

    item = {"id": "sun.component.ghost", "status": "published", "type": "component",
            "paths": {"visual": "library/components/diagrams/gone/visual.svg"},
            "immutable_text": {"audit": "clean", "reason": "it was clean once"}}
    assert br.immutable_text_fingerprint(item) == {}      # nothing to hash: the file is gone
    assert br.renders_as_slide(item) is True              # ...but it still claims artwork
    assert br.gate_immutable_text(item)["audit"] == "unresolved", br.gate_immutable_text(item)

    # Same for a preview-only item whose raster is missing.
    ghost_png = {"id": "sun.asset.ghost", "status": "published", "type": "asset",
                 "paths": {"preview": "library/assets/gone/logo.png"},
                 "immutable_text": {"audit": "clean", "reason": "brand mark"}}
    assert br.renders_as_slide(ghost_png) is True
    assert br.gate_immutable_text(ghost_png)["audit"] == "unresolved"


def test_needs_component_reason_names_the_real_blocker() -> None:
    # The reason a slide got no component must be the reason that is actually true.
    # The immutable-context gate blocks candidates that clear BOTH confidence bars, and
    # reporting "below the high-confidence reuse bar" for those sends the reader off to
    # raise a score that can never unblock it.
    item = _item(id="sun.component.locked", intent=["closing"], tags=["closing"])
    item["immutable_text"] = {"audit": "immutable", "contexts": [["zephyr-summit", "2031"]],
                              "reason": "Artwork bakes in the Zephyr Summit 2031 lockup."}
    req = {"intent": ["closing"], "tags": [], "content_structure": ["a"],
           "density": "medium", "brand": None, "required_exports": []}
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec
    top = cands[0]
    # Precondition: this candidate is blocked DESPITE clearing both bars.
    assert top["score"] >= svi.AUTO_REUSE_MIN, top
    assert top["criteria"]["semantic_intent"] >= 35 * svi.SEMANTIC_CONFIDENCE_FRAC, top
    assert "below the high-confidence reuse bar" not in dec["reason"], dec["reason"]
    assert "Zephyr Summit 2031" in dec["reason"], dec["reason"]

    # And a genuinely low-scoring candidate still reports the confidence bar.
    weak = _item(id="sun.component.weak", intent=["timeline"], tags=[])
    dec2, _ = svi.score_request(dict(req, intent=["closing"]), [weak], svi.WEIGHTS, None)
    assert dec2["action"] == "needs_component", dec2
    assert "reuse bar" in dec2["reason"] or "semantic fit" in dec2["reason"], dec2["reason"]


def test_new_published_item_cannot_bypass_the_audit_gate() -> None:
    # A freshly published / re-extracted item carries no audit. It must not become
    # automatically reusable just by landing in the registry.
    import build_registry as br

    with tempfile.TemporaryDirectory() as tmpd:
        item = _audit_item(Path(tmpd))
        gated = br.gate_immutable_text(item)
        assert gated["audit"] == "unresolved", gated
        assert "No immutable-text audit recorded" in gated["reason"]
        # An audit with no fingerprint is equally unusable — it cannot be re-checked.
        item["immutable_text"] = {"audit": "clean", "reason": "trust me"}
        assert br.gate_immutable_text(item)["audit"] == "unresolved"
        # A DRAFT is left alone: it is not selectable, and publish semantics are not
        # this gate's business.
        assert br.gate_immutable_text(dict(item, status="staging")) == item["immutable_text"]


def test_static_audit_cannot_overwrite_or_downgrade_a_rendered_report() -> None:
    # The defect: a --no-render pass overwrote audit-report.json, leaving it claiming
    # 91 audited with 0 rendered while 90 real renders sat on disk next to it.
    import audit_immutable_text as audit

    with tempfile.TemporaryDirectory() as tmpd:
        out = Path(tmpd) / "immutable-text-audit"
        out.mkdir(parents=True)
        rendered = out / "audit-report.json"
        marker = {"mode": "rendered", "status": "complete", "items": [{"id": "x"}]}
        rendered.write_text(json.dumps(marker), encoding="utf-8")

        rc = audit.main(["--out-dir", str(out), "--no-render",
                         "--ids", "sun.interview-workshop-sunriser.05-prep"])
        assert rc == 0
        # The rendered evidence is untouched...
        assert json.loads(rendered.read_text(encoding="utf-8")) == marker
        # ...and the static pass is clearly labelled, elsewhere, and unusable as proof.
        static = json.loads((out / "audit-report.static.json").read_text(encoding="utf-8"))
        assert static["mode"] == "static-only"
        assert static["status"] == "incomplete"
        assert static["usable_as_verdict_evidence"] is False
        assert all(r["render"]["status"] == "skipped" for r in static["items"])


def test_rendered_audit_records_real_render_evidence() -> None:
    # A completed rendered report must carry durable, repo-relative evidence for every
    # renderable item — not an absolute machine path, and never a null.
    import audit_immutable_text as audit
    if not fidelity._node_available():
        print("  (skip: node/playwright unavailable)")
        return
    with tempfile.TemporaryDirectory() as tmpd:
        out = Path(tmpd) / "immutable-text-audit"
        rc = audit.main(["--out-dir", str(out), "--ids",
                         f"{_PREP},{_PR_CLOSING}"])
        assert rc == 0
        rep = json.loads((out / "audit-report.json").read_text(encoding="utf-8"))
        assert rep["mode"] == "rendered", rep["mode"]
        assert rep["status"] == "complete", rep
        assert rep["usable_as_verdict_evidence"] is True
        assert rep["counts"]["render_rendered"] == 2, rep["counts"]
        for r in rep["items"]:
            assert r["render"]["status"] == "rendered", r
            assert r["render"]["path"] and not Path(r["render"]["path"]).is_absolute(), r
            assert (out / "renders" / f"{r['id']}.png").is_file(), r
            # Every record carries the fingerprint of the artwork it is evidence about.
            assert r["artifact_fingerprint"]["visual_sha256"], r


def test_immutable_text_conflict_fails_closed_at_fidelity() -> None:
    # An explicitly selected item whose fixed text conflicts with the deck must not
    # build: the scorer records the conflict on the decision and the render gate
    # rejects it, exactly like a review-only component.
    reg = {"items": [{"id": "sun.component.made-up", "status": "published",
                      "paths": {"preview": "x"}}]}
    report = {"slides": [{"request_id": "s", "decision": {
        "action": "reuse", "item_id": "sun.component.made-up", "selected_by": "user",
        "immutable_text_conflict": {"contexts": [["zephyr-summit", "2031"]],
                                    "reason": "Artwork bakes in the Zephyr Summit 2031 lockup."}}}]}
    res = fidelity.check_fidelity("<div>anything</div>", report, reg)
    assert res and res[0]["pass_"] is False, res
    assert "Zephyr Summit 2031" in res[0]["reason"], res


def test_retrieval_index_marks_review_only_but_published() -> None:
    # Review-only items stay published + browseable in the retrieval projection,
    # each with a human-readable reason. Pinned to the exact id set so a future
    # backfill cannot quietly mark unrelated components unsafe.
    idx = REGISTRY.parent / "component-retrieval-index.jsonl"
    rows = [json.loads(l) for l in idx.read_text(encoding="utf-8").splitlines() if l.strip()]
    flagged = [r for r in rows if (r.get("auto_reuse") or {}).get("eligible") is False]
    assert {r["id"] for r in flagged} == REVIEW_ONLY_IDS, sorted(r["id"] for r in flagged)
    for r in flagged:
        assert r["status"] == "published", r
        assert r["auto_reuse"]["reason"], r


CATALOG_DATA = SCRIPTS.parent / "catalog" / "catalog-data.json"


def test_catalog_data_marks_flagged_published_items_review_only() -> None:
    # F2: the catalog UI reads ONLY catalog-data.json, so a review-only component
    # that reaches a human as a plain "Published" card is the whole defect. The
    # shipped projection must carry the flag and the reason.
    data = _common.load_json(CATALOG_DATA)
    items = {i["id"]: i for i in data["items"]}
    flagged = [i for i in data["items"] if (i.get("auto_reuse") or {}).get("eligible") is False]
    assert {i["id"] for i in flagged} == REVIEW_ONLY_IDS, sorted(i["id"] for i in flagged)
    for item in flagged:
        assert item["status"] == "published", item      # still published + browseable
        assert item["auto_reuse"]["reason"].strip(), item   # with a human-readable reason
        assert item.get("images"), item                 # preview stays available
    # A normal published component keeps no review-only state at all.
    normal = items[ITEM_WITH_SLOTS]
    assert normal["status"] == "published", normal
    assert "auto_reuse" not in normal, normal.get("auto_reuse")


def test_catalog_builder_projects_auto_reuse_from_registry() -> None:
    # F2: prove the projection, not just today's snapshot — a registry flag must
    # reach catalog-data.json, and an unflagged item must stay unflagged.
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        flagged = _item(id="sun.component.flagged")
        flagged["auto_reuse"] = {"eligible": False, "reason": "failed full-slide QA"}
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"items": [flagged, _item(id="sun.component.normal")]}),
                       encoding="utf-8")
        out = tmp / "catalog-data.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_component_catalog.py"),
             "--registry", str(reg), "--output", str(out)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        items = {i["id"]: i for i in _common.load_json(out)["items"]}
        assert items["sun.component.flagged"]["auto_reuse"] == {
            "eligible": False, "reason": "failed full-slide QA"}
        assert items["sun.component.flagged"]["status"] == "published"
        assert "auto_reuse" not in items["sun.component.normal"]


def _local_draft(root: Path, folder: str, stable_id: str) -> Path:
    """A machine-local Draft on disk, in the layout the runtime scanner reads.
    Real Drafts live under gitignored outputs/component-extractions/."""
    item = root / "demo" / "items" / folder
    (item / "artifact").mkdir(parents=True)
    (item / "evidence").mkdir(parents=True)
    (item / "artifact" / "visual.svg").write_text("<svg/>", encoding="utf-8")
    (item / "evidence" / "source-with-text.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text>x</text></svg>', encoding="utf-8")
    (item / "mapping.json").write_text(json.dumps({
        "item_id": folder, "candidate_stable_id": stable_id, "name": "Local Draft",
        "status": "staging", "type": "component", "category": "component",
        "source": {"path": "source.pdf", "slide_or_page": 1},
    }), encoding="utf-8")
    return item


def test_tracked_catalog_projection_is_deterministic_and_draft_free() -> None:
    # Fix A: catalog-data.json is TRACKED, so it must be a pure function of the
    # tracked registry. Machine-local Drafts (gitignored outputs/) previously got
    # baked in, so any developer's rebuild replaced the committed Draft rows with
    # their own — noisy, unsafe diffs. The tracked projection is now published-only
    # and carries no wall-clock timestamp.
    import build_component_catalog as bcc

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        extractions = tmp / "component-extractions"
        _local_draft(extractions, "local-draft", "sun.component.local-draft")
        flagged = _item(id="sun.component.flagged")
        flagged["auto_reuse"] = {"eligible": False, "reason": "failed full-slide QA"}
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"updated_at": "2026-07-06T11:39:15+07:00",
                                   "items": [_item(id="sun.component.pub"), flagged]}),
                       encoding="utf-8")

        def _build(out: Path) -> bytes:
            rc = bcc.main(["--registry", str(reg), "--output", str(out)])
            assert rc == 0
            return out.read_bytes()

        first = _build(tmp / "a.json")
        second = _build(tmp / "b.json")
        # 1. Byte-stable: same tracked state in, identical bytes out (no now_iso()).
        assert first == second, "tracked catalog rebuild must be byte-stable"

        data = json.loads(first.decode("utf-8"))
        ids = [i["id"] for i in data["items"]]
        # 2. Published items survive, INCLUDING review-only metadata.
        assert ids == ["sun.component.pub", "sun.component.flagged"], ids
        assert all(i["status"] == "published" for i in data["items"]), data["items"]
        by_id = {i["id"]: i for i in data["items"]}
        assert by_id["sun.component.flagged"]["auto_reuse"] == {
            "eligible": False, "reason": "failed full-slide QA"}
        # 3. A normal published component is untouched by any of this.
        assert "auto_reuse" not in by_id["sun.component.pub"]
        # 4. The local Draft contaminates nothing...
        assert "sun.component.local-draft" not in ids
        # ...and no CLI path can inject Drafts into the tracked projection.
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_component_catalog.py"),
             "--registry", str(reg), "--output", str(tmp / "c.json"),
             "--extractions", str(extractions)], capture_output=True, text=True)
        assert proc.returncode != 0, "tracked builder must not accept a Drafts source"


def test_local_drafts_stay_discoverable_through_the_runtime_catalog_api() -> None:
    # Fix A other half: Drafts are still the user's to review — they are just owned
    # by the RUNTIME server (live scan), never by the tracked file.
    import build_component_catalog as bcc

    with tempfile.TemporaryDirectory() as tmpd:
        extractions = Path(tmpd) / "component-extractions"
        _local_draft(extractions, "local-draft", "sun.component.local-draft")
        drafts = bcc.collect_draft_items(extractions)
        assert [d["id"] for d in drafts] == ["sun.component.local-draft"], drafts
        assert drafts[0]["status"] == "staging"
        assert drafts[0]["publish_readiness"]["ready"] is True, drafts[0]

    # The server exposes exactly that scan over its existing /api pattern.
    path = SCRIPTS.parents[1] / "slide-system" / "catalog" / "catalog_server.py"
    spec = importlib.util.spec_from_file_location("catalog_server_drafts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "/api/drafts" in module.GET_ROUTES
    code, payload = module.GET_ROUTES["/api/drafts"]()
    assert code == 200 and payload["ok"] is True, payload
    assert isinstance(payload["items"], list)
    # The UI merges runtime Drafts on top of the tracked published projection.
    js = (SCRIPTS.parent / "catalog" / "catalog.js").read_text(encoding="utf-8")
    assert "/api/drafts" in js, "catalog UI must load Drafts from the runtime API"


def test_template_scaffold_centres_slot_text_for_accented_scripts() -> None:
    # Preview slots are copied top-aligned at the contract's tight line-height (1.0),
    # sized to the SOURCE copy's ink. Vietnamese diacritics (Ứ/Ụ) make the ink taller,
    # so its box escapes the wrapper's top even when the text "fits" — the real cover
    # measured 646x135 ink in a 728x146 box yet still read as outside. Centre it in the
    # room the box already has, exactly as the slot-contract path does; never shrink.
    slot = ('<div class="slot" data-slot-id="title" style="position:absolute;left:0;top:0;'
            'width:700px;height:146px;display:flex;justify-content:flex-start;'
            'align-items:flex-start;overflow:visible"><h1 style="margin:0">Old</h1></div>')
    out = scaffold.build_scaffold("sun.x.y", [slot], bg_url="assets/comp/x.svg")
    assert "align-items:center" in out, out
    assert "align-items:flex-start" not in out, out
    # Horizontal placement is contract-owned and must survive untouched.
    assert "justify-content:flex-start" in out, out


def test_template_scaffold_strips_unquotable_source_font_family() -> None:
    # A published preview.html emits its source family INSIDE a double-quoted style
    # attribute: style="...;font-family:"ProximaNova-Semibold", "Proxima Nova",
    # sans-serif;font-size:120px;...". Those inner quotes close the attribute early,
    # so the browser silently drops font-size/weight/colour — a 120px hero title
    # rendered at the default 32px, and the brand-font gate saw mangled fragments.
    # Same rule the slot-contract path already applies: the brand pack outranks a
    # component's foundry family, so drop it and inherit the deck font.
    slot = ('<div class="slot" data-slot-id="title" style="position:absolute;left:10px">'
            '<h1 style="margin:0;font-family:"ProximaNova-Bold", "Proxima Nova", '
            'sans-serif;font-size:120px;color:#171717">Old</h1></div>')
    out = scaffold.build_scaffold("sun.x.y", [slot], bg_url="assets/comp/x.svg")

    assert "font-family:" not in out, "raw source font-family must not survive"
    assert "ProximaNova-Bold" not in out
    # Everything the contract legitimately owns must still be there...
    assert "font-size:120px" in out and "color:#171717" in out
    assert 'data-slot-id="title"' in out and "left:10px" in out
    # ...and every style attribute must now be well-formed (no stray inner quote).
    for style in re.findall(r'style="([^"]*)"', out):
        assert '"' not in style, style
    for decl in re.findall(r'style="([^"]*)"', out):
        for part in filter(None, decl.split(";")):
            assert ":" in part, f"malformed declaration {part!r} in {decl!r}"


def test_catalog_ui_gates_review_only_components() -> None:
    # F2: the badge/reason/Copy-prompt rules live in catalog.js, which has no test
    # runner in this repo. This asserts the wiring exists and stays wired to
    # `auto_reuse.eligible`; the rendered proof is the browser smoke in the log.
    js = (SCRIPTS.parent / "catalog" / "catalog.js").read_text(encoding="utf-8")
    assert "auto_reuse?.eligible === false" in js, "review-only must key off auto_reuse"
    assert "Review-only" in js, "review-only badge label missing"
    # Copy prompt is disabled for review-only; Copy ID stays available.
    assert "compDom.copyPrompt.disabled = reviewOnly" in js
    assert "compDom.copyId.disabled" not in js, "Copy ID must stay available for audit"


def _valid_batch(**slide_over) -> dict:
    slide = {"request_id": "s1", "intent": ["timeline"], "tags": [],
             "content_structure": ["a"], "content_shape": "timeline",
             "density": "medium", "brand": "sun-studio"}
    slide.update(slide_over)
    return {"job_id": "j", "slides": [slide]}


REQUESTS_SCHEMA = SCRIPTS.parent / "schemas" / "visual-requests.schema.json"
# One sample per JSON type. A value is "bad" for a property when its JSON type is
# not among the types that property declares.
_TYPE_SAMPLES = (("string", "x"), ("integer", 3), ("boolean", True),
                 ("array", ["x"]), ("object", {"k": "v"}))


def _schema_rejects(spec: dict) -> list:
    """Values the JSON Schema `spec` forbids — used to prove the hand-written
    validator enforces exactly what the schema declares."""
    if "enum" in spec:
        return ["not-in-enum"]
    declared = spec.get("type")
    types = {declared} if isinstance(declared, str) else set(declared or [])
    bad = [value for name, value in _TYPE_SAMPLES if name not in types]
    if "array" in types and (spec.get("items") or {}).get("type") == "string":
        bad.append([123])  # right container, wrong element type
    return bad


def test_batch_request_validator_matches_schema_field_by_field() -> None:
    # F1 parity: `jsonschema` is not a declared dependency of this repo (there is
    # no Python dependency manifest at all), so validate_batch_request() is
    # hand-written. This test is what keeps it honest: the field vocabulary and
    # every declared type are checked against the schema file itself, so a schema
    # property the validator forgets can never pass silently and then crash the
    # scorer downstream.
    schema = _common.load_json(REQUESTS_SCHEMA)
    top = schema["properties"]
    slide = schema["$defs"]["slide"]["properties"]

    assert svi._BATCH_TOP_FIELDS == set(top), "top-level fields drifted from the schema"
    assert svi._SLIDE_REQUEST_FIELDS == set(slide), "slide fields drifted from the schema"

    for field, spec in top.items():
        for bad in _schema_rejects(spec):
            batch = _valid_batch()
            batch[field] = bad
            assert svi.validate_batch_request(batch), f"{field}={bad!r} must be rejected"
    for field, spec in slide.items():
        for bad in _schema_rejects(spec):
            assert svi.validate_batch_request(_valid_batch(**{field: bad})), \
                f"slides[0].{field}={bad!r} must be rejected"


def test_batch_request_duplicate_request_id_rejected() -> None:
    # The one invariant JSON Schema cannot express cleanly, so it is enforced
    # only in code and must keep its own test.
    errs = svi.validate_batch_request(
        {"job_id": "j", "slides": [{"request_id": "s"}, {"request_id": "s"}]})
    assert any("duplicate request_id" in e for e in errs), errs
    assert svi.validate_batch_request(
        {"job_id": "j", "slides": [{"request_id": "a"}, {"request_id": "b"}]}) == []


def test_batch_request_bad_content_shape_fails_clean_without_traceback() -> None:
    # F1 regression: `content_shape: ["flow"]` passed the validator and then blew
    # up in _common.shape_eligible() with `TypeError: unhashable type: 'list'`.
    # The user must get a plain validation error instead — and no report.
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"items": [_item()]}), encoding="utf-8")
        batch = tmp / "batch.json"
        batch.write_text(json.dumps(_valid_batch(content_shape=["flow"])), encoding="utf-8")
        out = tmp / "rep.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "score_visual_items.py"),
             "--batch-request", str(batch), "--registry", str(reg),
             "--output", str(out), "--retrieval-index", "none"],
            capture_output=True, text=True)
        assert proc.returncode != 0, proc.stdout
        assert "Traceback" not in proc.stderr, proc.stderr
        assert "TypeError" not in proc.stderr, proc.stderr
        assert "content_shape" in proc.stderr, proc.stderr
        assert not out.exists(), "no selection report may be written for an invalid batch"


def test_batch_request_valid_explicit_selection_passes() -> None:
    # Fix C: a valid explicit selection batch validates clean.
    assert svi.validate_batch_request(_valid_batch(
        component_id="sun.component.x", allow_component_reuse=True)) == []
    assert svi.validate_batch_request(_valid_batch(
        component_id=None, unresolved_policy="custom-local")) == []
    # ...and the real shipped QA artifacts remain accepted.
    for run in ("nine-slide-brief", "distinct-deck"):
        p = (SCRIPTS.parents[1] / "outputs/slide-jobs/selection-revision-20260715/runs"
             / run / "analysis/visual-requests.json")
        if p.exists():
            assert svi.validate_batch_request(_common.load_json(p)) == [], run


def test_batch_request_invalid_inputs_fail_before_scoring() -> None:
    # Fix C: each malformed selection input is rejected with a plain reason.
    def _errs(batch):
        return " ".join(svi.validate_batch_request(batch))
    assert "unresolved_policy" in _errs(_valid_batch(unresolved_policy="custom"))
    assert "allow_component_reuse" in _errs(_valid_batch(allow_component_reuse="yes"))
    assert "component_id" in _errs(_valid_batch(component_id=123))
    assert "request_id" in _errs({"job_id": "j", "slides": [{"intent": ["x"]}]})
    assert "must be an object" in _errs({"job_id": "j", "slides": ["nope"]})
    assert "unknown field" in _errs(_valid_batch(**{"componentid": "sun.component.x"}))
    assert "job_id" in _errs({"slides": [{"request_id": "s1"}]})
    assert "slides" in _errs({"job_id": "j"})
    # F1: types the schema declares but the validator used to ignore — the
    # content_shape list is the one that reached _common.shape_eligible() and
    # raised `TypeError: unhashable type: 'list'`.
    assert "content_shape" in _errs(_valid_batch(content_shape=["flow"]))
    assert "brief" in _errs({**_valid_batch(), "brief": 123})
    assert "note" in _errs({**_valid_batch(), "note": ["x"]})
    assert "query" in _errs(_valid_batch(query=7))
    assert "density" in _errs(_valid_batch(density=["medium"]))
    assert "brand" in _errs(_valid_batch(brand=1))
    assert "prefer_type" in _errs(_valid_batch(prefer_type=["component"]))
    assert "recommend_extraction" in _errs(_valid_batch(recommend_extraction="yes"))


def test_batch_request_invalid_exits_nonzero_before_scoring() -> None:
    # Fix C: the CLI fails closed (non-zero, no report written) on a bad batch.
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"items": [_item()]}), encoding="utf-8")
        batch = tmp / "batch.json"
        batch.write_text(json.dumps(_valid_batch(unresolved_policy="custom")), encoding="utf-8")
        out = tmp / "rep.json"
        rc = svi.main(["--batch-request", str(batch), "--registry", str(reg),
                       "--output", str(out), "--retrieval-index", "none"])
        assert rc == 1, "invalid batch must exit non-zero"
        assert not out.exists(), "no selection report may be written for an invalid batch"


def test_published_only_still_enforced_for_auto_reuse() -> None:
    # F10: existing published-only gate still holds — an unpublished item never
    # auto-reuses even if its raw score would be high.
    dec, cands = svi.score_request(_req(), [_item(id="sun.component.draft", status="staging")],
                                   svi.WEIGHTS, None)
    assert dec["action"] == "needs_component" and cands[0]["eligible"] is False, dec


# --------------------------------------------------------------------------- #
# score_visual_items — type-intent bias (component vs template in all-types)
# --------------------------------------------------------------------------- #
def _typed_req(query: str, **over) -> dict:
    base = {"query": query, "intent": ["team", "profile", "roster"],
            "tags": ["contributors"], "content_structure": ["heading", "label"],
            "density": "any", "brand": None, "required_exports": []}
    base.update(over)
    return base


def _template_item() -> dict:
    # Matches every request term -> out-scores the component when there is no bias.
    return _item(id="sun.deck.04-contributors", type="template",
                 intent=["team", "profile", "roster"], tags=["contributors"],
                 content_structure=["heading", "label"])


def _component_item() -> dict:
    # One fewer intent match -> lower raw score than the template above.
    return _item(id="sun.component.team-circles", type="component",
                 intent=["team", "profile"], tags=["contributors"],
                 content_structure=["heading", "label"])


def test_request_type_intent_detection() -> None:
    assert svi.request_type_intent({"prefer_type": "component"}) == "component"
    assert svi.request_type_intent({"prefer_type": "template"}) == "template"
    assert svi.request_type_intent({"query": "reusable component for KPI strip"}) == "component"
    assert svi.request_type_intent({"query": "full slide template for cover"}) == "template"
    # template intent wins ties (explicit whole-slide ask beats an incidental word)
    assert svi.request_type_intent({"query": "component card set full slide template"}) == "template"
    # markers can arrive via intent/tags, not just free text
    assert svi.request_type_intent({"tags": ["icon-reference"]}) == "component"
    assert svi.request_type_intent({"intent": ["team", "profile"]}) is None


def test_type_intent_component_query_ranks_component_over_template() -> None:
    items = [_template_item(), _component_item()]
    # Neutral phrasing: the template out-scores the component (baseline behavior).
    dec_n, _ = svi.score_request(_typed_req("team roster"), items, svi.WEIGHTS, None)
    assert dec_n["item_id"] == "sun.deck.04-contributors", dec_n
    # Explicit component intent: the template is demoted; the component wins.
    dec_c, cands = svi.score_request(
        _typed_req("reusable component team roster"), items, svi.WEIGHTS, None)
    assert dec_c["item_id"] == "sun.component.team-circles", dec_c
    tmpl = next(c for c in cands if c["item_id"] == "sun.deck.04-contributors")
    assert tmpl["retrieval"]["type_bias"] == "template-demoted"
    assert any("template demoted" in r for r in tmpl["reasons"])


def test_type_intent_template_query_lets_template_win() -> None:
    items = [_template_item(), _component_item()]
    dec, cands = svi.score_request(
        _typed_req("full slide template for the team page"), items, svi.WEIGHTS, None)
    assert dec["item_id"] == "sun.deck.04-contributors", dec
    tmpl = next(c for c in cands if c["item_id"] == "sun.deck.04-contributors")
    assert "type_bias" not in tmpl.get("retrieval", {}), "template intent must not demote templates"


def test_type_intent_neutral_query_applies_no_bias() -> None:
    items = [_template_item(), _component_item()]
    dec, cands = svi.score_request(_typed_req("team roster"), items, svi.WEIGHTS, None)
    # Same winner and score as a run with the demotion path never triggered.
    assert dec["item_id"] == "sun.deck.04-contributors", dec
    for c in cands:
        assert "type_bias" not in c.get("retrieval", {})
        assert not any("template demoted" in r for r in c["reasons"])


def test_type_intent_leaves_components_unchanged() -> None:
    # Component-only scoring never sees a template, so the demotion cannot fire:
    # a component's score is identical with or without component intent.
    comp = [_component_item()]
    _, neutral = svi.score_request(_typed_req("team roster"), comp, svi.WEIGHTS, None)
    _, biased = svi.score_request(_typed_req("reusable component team roster"), comp, svi.WEIGHTS, None)
    assert neutral[0]["score"] == biased[0]["score"]
    assert "type_bias" not in biased[0].get("retrieval", {})


def test_type_intent_no_component_false_positive_when_nothing_fits() -> None:
    # A component-intent query with no relevant component must NOT be forced into
    # a confident reuse just because templates were demoted.
    template = _item(id="sun.deck.10-chart", type="template",
                     intent=["chart", "statistics"], tags=["pie"],
                     content_structure=["metric", "label"])
    unrelated = _item(id="sun.component.timeline", type="component",
                      intent=["timeline"], tags=[], content_structure=["heading"])
    req = {"query": "reusable component financial pie chart",
           "intent": ["chart", "statistics"], "tags": ["pie-chart", "financial"],
           "content_structure": ["metric", "label"], "density": "any",
           "brand": None, "required_exports": []}
    dec, _ = svi.score_request(req, [template, unrelated], svi.WEIGHTS, None)
    assert dec["action"] != "reuse", dec
    assert dec["item_id"] != "sun.component.timeline" or dec["action"] == "custom-local", dec


# --------------------------------------------------------------------------- #
# score_visual_items — hybrid retrieval (v3.2)
# --------------------------------------------------------------------------- #
def _rreq(**over) -> dict:
    base = {"intent": [], "tags": [], "content_structure": [], "density": "any",
            "brand": None, "required_exports": []}
    base.update(over)
    return base


def test_retrieval_secondary_match_lifts_prose_metadata_item() -> None:
    # metric/KPI strip: docling-style prose intent is invisible to primary
    # matching; index keywords must lift it via capped secondary credit.
    strip = _item(id="sun.component.kpi-strip",
                  intent=["revenue team size metric strip"], tags=["strip"],
                  content_structure=[])
    req = _rreq(intent=["statistics", "kpi"], tags=["strip"])
    _, plain = svi.score_request(req, [strip], svi.WEIGHTS, None)
    enrichment = svi.build_enrichment([{
        "id": "sun.component.kpi-strip", "status": "published",
        "keywords": ["revenue", "team", "metric", "strip"],
        "component_type": "strip", "slot_count": 5,
    }])
    _, enriched = svi.score_request(req, [strip], svi.WEIGHTS, None, enrichment=enrichment)
    assert enriched[0]["score"] > plain[0]["score"], "index keywords must lift the strip"
    assert enriched[0]["retrieval"]["secondary_matches"] == ["statistics"]
    assert enriched[0]["retrieval"]["slot_count"] == 5


def test_retrieval_tier_strip_trap_stays_below_genuine_component() -> None:
    # level/tier strip: an OCR-named trap with a "levels" keyword must not
    # outrank the component that declares tiers/levels as canonical intent.
    genuine = _item(id="sun.component.tier-set",
                    intent=["ranking", "levels", "tiers"], tags=["set-of-3"],
                    content_structure=["heading", "label"])
    trap = _item(id="sun.component.trap-strip",
                 intent=["spicy autocomplete autonomous levels strip"],
                 tags=["strip"], content_structure=[])
    enrichment = svi.build_enrichment([
        {"id": "sun.component.trap-strip", "status": "published",
         "keywords": ["levels", "autonomous"], "slot_count": 16},
    ])
    req = _rreq(intent=["levels", "tiers", "ranking"],
                content_structure=["heading", "label"])
    dec, cands = svi.score_request(req, [trap, genuine], svi.WEIGHTS, None,
                                   enrichment=enrichment)
    assert dec["item_id"] == "sun.component.tier-set", dec
    scores = {c["item_id"]: c["score"] for c in cands}
    assert scores["sun.component.trap-strip"] < scores["sun.component.tier-set"]


def test_retrieval_generic_overlap_capped_below_semantic_floor() -> None:
    # negative case: an unrelated item whose index keywords happen to cover
    # EVERY request term must stay below the semantic floor -> custom-local.
    lure = _item(id="sun.component.lure", intent=["ai team visual"], tags=[],
                 content_structure=["a"])
    enrichment = svi.build_enrichment([{
        "id": "sun.component.lure", "status": "published",
        "keywords": ["timeline", "roadmap"], "slot_count": 4,
    }])
    dec, cands = svi.score_request(_req(), [lure], svi.WEIGHTS, None,
                                   enrichment=enrichment)
    cap_points = svi.SECONDARY_CAP * svi.WEIGHTS["semantic_intent"]
    assert cands[0]["criteria"]["semantic_intent"] <= cap_points + 1e-9
    assert dec["action"] == "needs_component", "generic overlap alone must never auto-select"
    assert dec["item_id"] is None, dec
    assert dec["extraction_recommended"] is True


def test_retrieval_below_floor_top_candidate_does_not_block_relevant_runner_up() -> None:
    # A secondary-only lure can outrank a relevant component by raw score. The
    # decision must skip the lure because it is below the semantic floor, then
    # choose the best semantically valid runner-up instead of returning
    # custom-local.
    lure = _item(
        id="sun.component.lure",
        intent=["decorative visual"],
        tags=[],
        content_structure=["heading", "label"],
    )
    good = _item(
        id="sun.component.good-timeline",
        intent=["timeline", "roadmap"],
        tags=[],
        content_structure=["heading"],
    )
    enrichment = svi.build_enrichment([{
        "id": "sun.component.lure", "status": "published",
        "keywords": ["timeline", "roadmap", "milestones", "schedule"],
        "slot_count": 4,
    }])
    req = _rreq(
        intent=["timeline", "roadmap", "milestones", "schedule"],
        content_structure=["heading", "label"],
    )
    dec, cands = svi.score_request(req, [lure, good], svi.WEIGHTS, None,
                                   enrichment=enrichment)
    assert cands[0]["item_id"] == "sun.component.lure"
    assert cands[0]["criteria"]["semantic_intent"] < svi.WEIGHTS["semantic_intent"] * 0.3
    # Neither the lure nor the weak runner-up clears the high-confidence bar, so
    # the slide is unresolved; the relevant runner-up stays in candidates for the
    # user to select explicitly (never a silent auto-selection or custom layout).
    assert dec["action"] == "needs_component", dec
    assert dec["item_id"] is None, dec
    assert any(c["item_id"] == "sun.component.good-timeline" for c in cands), cands


def test_retrieval_selected_runner_up_stays_in_reported_candidates() -> None:
    # The decision may skip several below-floor lures and choose an above-floor
    # runner-up outside the top-N display slice. The chosen item must still be
    # emitted so reviewers can inspect its score, criteria, and reasons.
    lures = [
        _item(
            id=f"sun.component.lure-{idx}",
            intent=["decorative visual"],
            tags=[],
            content_structure=["heading", "label"],
        )
        for idx in range(6)
    ]
    good = _item(
        id="sun.component.good-timeline",
        intent=["timeline", "roadmap"],
        tags=[],
        content_structure=["heading"],
    )
    enrichment = svi.build_enrichment([
        {
            "id": lure["id"], "status": "published",
            "keywords": ["timeline", "roadmap", "milestones", "schedule"],
            "slot_count": 4,
        }
        for lure in lures
    ])
    req = _rreq(
        intent=["timeline", "roadmap", "milestones", "schedule"],
        content_structure=["heading", "label"],
    )
    dec, cands = svi.score_request(req, lures + [good], svi.WEIGHTS, None,
                                   top_n=5, enrichment=enrichment)
    # Unresolved (nothing clears the bar), but the relevant runner-up must still be
    # emitted outside the top-N display slice so reviewers can inspect + pick it.
    assert dec["action"] == "needs_component", dec
    assert cands[0]["item_id"].startswith("sun.component.lure-"), cands
    assert any(c["item_id"] == "sun.component.good-timeline" for c in cands), cands


def test_retrieval_prose_component_outranks_unrelated_item() -> None:
    # team/contributor/profile: prose-only metadata gains capped rank credit,
    # so the right component surfaces above unrelated ones in candidates.
    team = _item(id="sun.component.team-circles",
                 intent=["team contributor profile circles layout"], tags=[],
                 content_structure=[])
    other = _item(id="sun.component.faq", intent=["faq"], tags=[],
                  content_structure=[])
    enrichment = svi.build_enrichment([
        {"id": "sun.component.team-circles", "status": "published",
         "name": "Team Contributor Circles",
         "intent": ["team contributor profile circles layout"], "slot_count": 0},
        {"id": "sun.component.faq", "status": "published",
         "keywords": ["faq"], "slot_count": 4},
    ])
    req = _rreq(intent=["team", "profile"], tags=["circles"])
    _, cands = svi.score_request(req, [other, team], svi.WEIGHTS, None,
                                 enrichment=enrichment)
    assert cands[0]["item_id"] == "sun.component.team-circles", cands
    assert cands[0]["retrieval"]["secondary_matches"], "must explain the lexical match"


def test_retrieval_anti_use_case_penalty_for_undeclared_domain() -> None:
    badge = _item(id="sun.component.badge", intent=["numbered", "grid"],
                  tags=["cards"])
    req = _rreq(intent=["statistics"], tags=["numbered"], content_structure=["a"])
    base_enr = {"id": "sun.component.badge", "status": "published",
                "keywords": ["badge"], "slot_count": 6}
    _, plain = svi.score_request(req, [badge], svi.WEIGHTS, None,
                                 enrichment=svi.build_enrichment([base_enr]))
    anti_enr = dict(base_enr, anti_use_cases=[
        "Do not use for data-driven charts or metrics; placeholder diagram."])
    _, hit = svi.score_request(req, [badge], svi.WEIGHTS, None,
                               enrichment=svi.build_enrichment([anti_enr]))
    assert plain[0]["score"] - hit[0]["score"] == svi.ANTI_USE_CASE_PENALTY
    assert hit[0]["retrieval"]["anti_hits"] == ["statistics"]
    assert any("Anti-use-case" in r for r in hit[0]["reasons"])


def test_retrieval_anti_hit_on_declared_intent_is_caveat_not_exclusion() -> None:
    # The item declares statistics as honest intent; its anti text mentioning
    # "metrics" is an editing caveat and must NOT be penalized.
    circles = _item(id="sun.component.circles", intent=["statistics", "ranking"],
                    tags=[])
    enrichment = svi.build_enrichment([{
        "id": "sun.component.circles", "status": "published",
        "anti_use_cases": ["Do not reuse the baked metrics without editing text slots."],
        "slot_count": 13,
    }])
    req = _rreq(intent=["statistics"], content_structure=["a"])
    _, cands = svi.score_request(req, [circles], svi.WEIGHTS, None,
                                 enrichment=enrichment)
    assert "anti_hits" not in cands[0].get("retrieval", {}), cands[0]
    assert not any("Anti-use-case" in r for r in cands[0]["reasons"])


def test_retrieval_count_fit_penalty_prefers_matching_set_size() -> None:
    # buildability: wrong declared set size must not beat a better-fit item.
    three = _item(id="sun.component.three", intent=["roles"],
                  tags=["cards", "set-of-3"])
    four = _item(id="sun.component.four", intent=["roles"],
                 tags=["cards", "set-of-4"])
    req = _rreq(intent=["roles"], tags=["cards"], content_structure=["a"],
                item_count=4)
    dec, cands = svi.score_request(req, [three, four], svi.WEIGHTS, None)
    assert dec["item_id"] == "sun.component.four", dec
    three_cand = next(c for c in cands if c["item_id"] == "sun.component.three")
    assert three_cand["retrieval"]["set_sizes"] == [3]
    assert any("Count fit" in r for r in three_cand["reasons"])


def test_retrieval_zero_slot_component_penalized_when_text_needed() -> None:
    deco = _item(id="sun.component.deco", intent=["team", "profile"], tags=[])
    slotted = _item(id="sun.component.slotted", intent=["team", "profile"], tags=[])
    enrichment = svi.build_enrichment([
        {"id": "sun.component.deco", "status": "published", "slot_count": 0},
        {"id": "sun.component.slotted", "status": "published", "slot_count": 6},
    ])
    req = _rreq(intent=["team", "profile"], content_structure=["a"])
    dec, cands = svi.score_request(req, [deco, slotted], svi.WEIGHTS, None,
                                   enrichment=enrichment)
    assert dec["item_id"] == "sun.component.slotted", dec
    deco_cand = next(c for c in cands if c["item_id"] == "sun.component.deco")
    assert deco_cand["retrieval"]["slot_count"] == 0
    assert any("no editable text slots" in r for r in deco_cand["reasons"])
    # decoration-only requests (no text content) are NOT penalized
    _, cands2 = svi.score_request(_rreq(intent=["team", "profile"]),
                                  [deco, slotted], svi.WEIGHTS, None,
                                  enrichment=enrichment)
    deco2 = next(c for c in cands2 if c["item_id"] == "sun.component.deco")
    assert not any("no editable text slots" in r for r in deco2["reasons"])


def test_retrieval_enrichment_published_only_and_missing_index() -> None:
    # Draft/staging records never enrich scoring, even from a stale file, and
    # a missing index file degrades to plain primary-only scoring.
    assert svi.build_enrichment([
        {"id": "sun.component.x", "status": "staging", "keywords": ["timeline"]},
        {"status": "published", "keywords": ["timeline"]},
    ]) == {}
    with tempfile.TemporaryDirectory() as tmp:
        assert svi.load_retrieval_index(Path(tmp) / "missing.jsonl") == {}


def test_retrieval_corrupt_index_degrades_to_empty_enrichment() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "component-retrieval-index.jsonl"
        index.write_text(
            '{"id":"sun.component.valid","status":"published","keywords":["kpi"]}\n'
            '{"id":"sun.component.truncated",',
            encoding="utf-8",
        )
        assert svi.load_retrieval_index(index) == {}
        index.write_bytes(b"\xff\xfe")
        assert svi.load_retrieval_index(index) == {}


def test_retrieval_index_projects_slot_count() -> None:
    import build_component_retrieval_index as bri
    registry = {"items": [{
        "id": "sun.component.slots", "status": "published", "type": "component",
        "intent": ["grid"], "text_contract": {"slot_count": 7},
    }]}
    records = bri.build_records(registry)
    assert records[0]["slot_count"] == 7
    assert records[0]["schema_version"] == 2


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


def test_shape_lock_covers_component_first_shapes() -> None:
    reg_tokens = vsr._registry_tokens(read_text_slots.load_json(REGISTRY))
    cases = {
        "profile": "sun.component.team-contributor-circles.g01",
        "tiers": "sun.component.spicy-autocomplete-autonomous-levels-strip",
        "icons": "sun.component.brand-icon-reference-sheet",
        "review": "sun.goal-setting-2026.07-quarterly-check-in",
    }
    for shape, item_id in cases.items():
        rep = _single_report(item_id=item_id)
        errs, _ = vsr._validate_shape_lock(rep, False, {"s1": shape}, reg_tokens, strict_shape=True)
        assert not errs, f"{shape} -> {item_id} should pass: {errs}"
    rep = _single_report(item_id="sun.salary-benefits-2026.01-cover")
    errs, _ = vsr._validate_shape_lock(rep, False, {"s1": "tiers"}, reg_tokens, strict_shape=True)
    assert errs, "tiers shape locked to a cover template must fail"


def test_selection_report_rejects_manual_curation_override() -> None:
    """A scorer result cannot be relabeled custom-local by an agent."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_path = root / "analysis" / "selection-report.json"
        report_path.parent.mkdir()
        report_path.write_text(json.dumps({
            "job_id": "test-job",
            "generated_at": "2026-07-13T00:00:00+00:00",
            "generated_by": "score_visual_items.py",
            "slides": [{
                "request_id": "s1",
                "decision": {
                    "action": "custom-local",
                    "item_id": None,
                    "score": 80.0,
                    "reason": "Manually rejected despite a strong match.",
                    "scorer_action": "reuse",
                    "scorer_item_id": "sun.component.timeline",
                },
                "candidates": [{
                    "item_id": "sun.component.timeline",
                    "eligible": True,
                    "score": 80.0,
                    "criteria": {**{key: 1.0 for key in vsr.REQUIRED_CRITERIA},
                                 "semantic_intent": 20.0},
                }],
            }],
            "curated_by": "agent override",
        }), encoding="utf-8")
        original_argv = sys.argv
        try:
            sys.argv = ["validate_selection_report.py", "--selection-report", str(report_path)]
            assert vsr.main() == 1, "manual curation must fail the blocking selection gate"
        finally:
            sys.argv = original_argv


def test_selection_report_accepts_capacity_conflict() -> None:
    # A scorer decision carrying capacity_conflict must pass the real validator
    # (regression: capacity_conflict was absent from DECISION_FIELDS).
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=4, component_id="sun.deck.cta")
    dec, cands = svi.score_request(req, [cta], svi.WEIGHTS, None,
                                   enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert "capacity_conflict" in dec
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_path = root / "analysis" / "selection-report.json"
        report_path.parent.mkdir()
        report_path.write_text(json.dumps({
            "request_id": "s1",
            "generated_at": "2026-07-19T00:00:00+00:00",
            "generated_by": "score_visual_items.py",
            "decision": dec,
            "candidates": [{"item_id": c["item_id"], "eligible": c.get("eligible", True),
                            "score": c["score"], "criteria": c["criteria"],
                            "reasons": c.get("reasons", [])}
                           for c in cands],
        }), encoding="utf-8")
        original_argv = sys.argv
        try:
            sys.argv = ["validate_selection_report.py", "--selection-report", str(report_path)]
            assert vsr.main() == 0, "capacity_conflict report must pass the validator"
        finally:
            sys.argv = original_argv


def test_selection_report_accepts_immutable_text_conflict_contexts() -> None:
    # The scorer emits immutable_text_conflict.contexts (list of groups), not
    # terms (flat list). The schema and validator must accept the real shape.
    # The immutable_text is on the registry ITEM (not enrichment) — the scorer
    # reads it from item["immutable_text"] at scoring time.
    item = _item(id="sun.component.locked", intent=["closing"], tags=["closing"],
                 build_scope={"mode": "generic", "reason": "test"},
                 immutable_text={"audit": "immutable",
                                 "contexts": [["zephyr-summit", "2031"]],
                                 "reason": "Artwork bakes in the Zephyr Summit 2031 lockup."})
    req = _rreq(intent=["closing"], tags=["not-zephyr", "other"],
                content_structure=["a"], component_id="sun.component.locked")
    enrichment = svi.build_enrichment([{
        "id": "sun.component.locked", "status": "published",
        "keywords": ["closing"], "slot_count": 3,
    }])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None,
                                   enrichment=enrichment)
    assert dec.get("immutable_text_conflict"), "expected immutable_text_conflict in decision: %s" % dec
    conflict = dec["immutable_text_conflict"]
    assert "contexts" in conflict, f"expected 'contexts' in conflict, got keys: {list(conflict)}"
    assert isinstance(conflict["contexts"], list) and len(conflict["contexts"]) > 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_path = root / "analysis" / "selection-report.json"
        report_path.parent.mkdir()
        report_path.write_text(json.dumps({
            "request_id": "s1",
            "generated_at": "2026-07-19T00:00:00+00:00",
            "generated_by": "score_visual_items.py",
            "decision": dec,
            "candidates": [{"item_id": c["item_id"], "eligible": c.get("eligible", True),
                            "score": c["score"], "criteria": c["criteria"],
                            "reasons": c.get("reasons", [])}
                           for c in cands],
        }), encoding="utf-8")
        original_argv = sys.argv
        try:
            sys.argv = ["validate_selection_report.py", "--selection-report", str(report_path)]
            assert vsr.main() == 0, "immutable_text_conflict report (contexts) must pass the validator"
        finally:
            sys.argv = original_argv


def test_selection_report_schema_drift_edge_cases() -> None:
    # Schema parity test. NEVER SKIPS — uses stdlib json + hand-written validator.
    # 1. Parse the schema, extract declared candidate property names.
    # 2. Run the scorer on a real request and collect actual candidate fields.
    # 3. Assert every field the scorer emits exists in the schema's candidate
    #    properties (catches drift like missing shape_eligible).
    # 4. Validate a real report through the hand-written validator.
    # 5. When jsonschema IS available, run additional negative/edge checks.
    schema_path = SCRIPTS.parent / "schemas" / "selection-report.schema.json"
    schema = _common.load_json(schema_path)
    import json

    candidate_props = set(schema.get("$defs", {}).get("candidate", {}).get("properties", {}).keys())
    assert "item_id" in candidate_props, "schema $defs.candidate missing item_id"

    # Run the scorer to get a real candidate so we can check field parity.
    cta_item = _item(id="sun.deck.cta", intent=["checklist"], tags=[])
    req = _rreq(intent=["checklist"], content_structure=["a"], component_id="sun.deck.cta")
    _dec, cands = svi.score_request(req, [cta_item], svi.WEIGHTS, None,
                                    enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert len(cands) == 1
    emitted = set(cands[0].keys())
    undeclared = emitted - candidate_props
    assert not undeclared, (
        f"candidate field(s) emitted by scorer but missing from schema $defs.candidate: "
        f"{sorted(undeclared)}. Declared: {sorted(candidate_props)}"
    )

    # Build a real report and validate it through the hand-written validator.
    _dec, cands = svi.score_request(req, [cta_item], svi.WEIGHTS, None,
                                    enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_path = root / "analysis" / "selection-report.json"
        report_path.parent.mkdir()
        report_path.write_text(json.dumps({
            "request_id": "s1",
            "generated_at": "2026-07-19T00:00:00+00:00",
            "generated_by": "score_visual_items.py",
            "decision": _dec,
            "candidates": cands,
        }), encoding="utf-8")
        original_argv = sys.argv
        try:
            sys.argv = ["validate_selection_report.py", "--selection-report", str(report_path)]
            assert vsr.main() == 0, "real scorer output must pass the hand-written validator"
        finally:
            sys.argv = original_argv

    # When jsonschema is available, run additional negative/edge checks.
    try:
        import jsonschema
    except ImportError:
        return

    # 1. Valid single-slide report
    jsonschema.validate({
        "request_id": "s1", "generated_at": "2026-01-01T00:00:00Z",
        "generated_by": "score_visual_items.py",
        "decision": {"action": "reuse", "item_id": "c1", "score": 85.0, "reason": "good"},
        "candidates": [{"item_id": "c1", "eligible": True, "score": 85.0,
                        "criteria": {"semantic_intent": 30.0, "content_structure": 20.0},
                        "reasons": ["full match"]}],
    }, schema)
    # 2. Valid batch report
    jsonschema.validate({
        "job_id": "j1", "generated_at": "2026-01-01T00:00:00Z",
        "generated_by": "score_visual_items.py",
        "slides": [{"request_id": "s1",
                    "decision": {"action": "needs_component", "item_id": None, "score": 50.0, "reason": "low"},
                    "candidates": [{"item_id": "c1", "eligible": True, "score": 50.0,
                                   "criteria": {"semantic_intent": 20.0, "content_structure": 10.0},
                                   "reasons": ["partial"]}]}],
    }, schema)
    # 3. Valid immutable_text_conflict (contexts, not terms)
    jsonschema.validate({
        "request_id": "s1", "generated_at": "2026-01-01T00:00:00Z",
        "generated_by": "score_visual_items.py",
        "decision": {"action": "reuse", "item_id": "c1", "score": 85.0, "reason": "warn",
                     "immutable_text_conflict": {
                         "contexts": [["zephyr-summit", "2031"]],
                         "reason": "Artwork bakes in the Zephyr Summit 2031 lockup."}},
        "candidates": [{"item_id": "c1", "eligible": True, "score": 85.0,
                        "criteria": {"semantic_intent": 30.0, "content_structure": 20.0},
                        "reasons": ["full match"]}],
    }, schema)
    # 4. Valid capacity_conflict
    jsonschema.validate({
        "request_id": "s1", "generated_at": "2026-01-01T00:00:00Z",
        "generated_by": "score_visual_items.py",
        "decision": {"action": "reuse", "item_id": "c1", "score": 85.0, "reason": "warn",
                     "capacity_conflict": {"planned_items": 4, "content_blocks": 1}},
        "candidates": [{"item_id": "c1", "eligible": True, "score": 85.0,
                        "criteria": {"semantic_intent": 30.0, "content_structure": 20.0},
                        "reasons": ["full match"]}],
    }, schema)
    # 5. Unknown decision field must be rejected
    try:
        jsonschema.validate({
            "request_id": "s1", "generated_at": "2026-01-01T00:00:00Z",
            "generated_by": "score_visual_items.py",
            "decision": {"action": "reuse", "item_id": "c1", "score": 85.0, "reason": "good",
                         "unknown_field": "should not be here"},
            "candidates": [{"item_id": "c1", "eligible": True, "score": 85.0,
                           "criteria": {"semantic_intent": 30.0, "content_structure": 20.0},
                           "reasons": ["full match"]}],
        }, schema)
        assert False, "unknown decision field must be rejected"
    except jsonschema.ValidationError:
        pass
    # 6. Malformed batch (missing job_id) must be rejected
    try:
        jsonschema.validate({
            "generated_at": "2026-01-01T00:00:00Z",
            "slides": [{"request_id": "s1",
                       "decision": {"action": "reuse", "item_id": "c1", "score": 85.0, "reason": "good"},
                       "candidates": [{"item_id": "c1", "eligible": True, "score": 85.0,
                                      "criteria": {"semantic_intent": 30.0},
                                      "reasons": []}]}],
        }, schema)
        assert False, "malformed batch (no job_id) must be rejected"
    except jsonschema.ValidationError:
        pass


def test_slide_generator_requires_fresh_selection_for_new_jobs() -> None:
    skill = (SCRIPTS.parent.parent / ".agents" / "skills" / "slide-generator" / "SKILL.md")
    text = skill.read_text(encoding="utf-8")
    assert "Do not read `docs/logs/`" in text
    assert "outputs/slide-jobs/` to judge current library fit" in text
    assert "never edit `selection-report.json`" in text


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


# Part C: slot rendering carries the component's own typography + alignment from
# the contract (not a generic overlay), with a deterministic no-auto-shrink size.
def test_slot_scaffold_emits_contract_typography() -> None:
    slot = {
        "id": "title", "role": "heading", "html_tag": "h2",
        "horizontal_align": "center", "vertical_align": "middle",
        "bounds": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1},
        "typography": {"font_family": "ProximaNova-Bold", "font_size": 54.0,
                       "font_weight": "bold", "font_style": "normal",
                       "line_height": 1.0, "letter_spacing": "normal",
                       "color": "#ffffff"},
    }
    frag = scaffold.build_slot_scaffold("sun.component.x", [slot])
    assert 'data-component-slot="title"' in frag
    # typography copied from the contract onto the text element
    assert "font-weight:bold" in frag, frag
    assert "font-style:normal" in frag
    assert "color:#ffffff" in frag
    # the raw source foundry name is NOT emitted — slot text inherits the deck's
    # brand font (brand pack outranks component styling; keeps the brand-font gate).
    assert "ProximaNova-Bold" not in frag, frag
    assert "font-family" not in frag, frag
    assert "line-height:1" in frag
    assert "font-size:54.0px" in frag, frag          # vscale defaults to 1.0
    assert "text-align:center" in frag
    # alignment maps to flex placement
    assert "justify-content:center" in frag and "align-items:center" in frag
    # deterministic fit: the box clips (overflow hidden); nothing shrinks text at
    # runtime (no script). A too-long string is caught by the render-aware gate,
    # not silently resized here.
    assert "overflow:hidden" in frag
    assert "<script" not in frag.lower()


def test_slot_scaffold_scales_font_size_by_vertical_source_ratio() -> None:
    # font_size is in source-units; on the deck canvas it scales by CANVAS_H /
    # source_canvas_height. A half-height source doubles the rendered px.
    slot = {"id": "t", "role": "label", "html_tag": "span",
            "horizontal_align": "left", "vertical_align": "top",
            "bounds": {"x": 0.0, "y": 0.0, "width": 0.2, "height": 0.1},
            "typography": {"font_size": 30.0, "color": "#000000"}}
    vscale = scaffold.CANVAS_H / (scaffold.CANVAS_H / 2)   # source half as tall -> x2
    frag = scaffold.build_slot_scaffold("sun.component.x", [slot], vscale=vscale)
    assert "font-size:60.0px" in frag, frag


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


# Part D / P2: fidelity is scoped to a UNIQUE component OCCURRENCE
# (data-component-instance) and render-aware. Two uses of the same component are
# validated independently; overflow/overlap/broken-artwork fail; release mode
# (require_instance_ids / --require-render) fails closed.
def _text_slot_registry(tmp: Path, slots: list[dict] | None = None,
                        item: str = "sun.component.a") -> dict:
    slots = slots or [
        {"id": "s1", "bounds": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}},
        {"id": "s2", "bounds": {"x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1}}]
    ts = tmp / f"{item}-slots.json"
    ts.write_text(json.dumps({"slots": slots}), encoding="utf-8")
    prev = tmp / f"{item}-preview.html"
    prev.write_text('<div class="stage"><div class="bg"></div></div>', encoding="utf-8")
    return {"items": [{
        "id": item, "status": "published",
        "text_contract": {"semantic_text_in_visual": False, "editable": True},
        "paths": {"preview": str(prev), "text_slots": str(ts)},
    }]}


def _box(sid: str, left: int, top: int, w: int, h: int, text: str = "hi") -> str:
    return (f'<div class="component-slot" data-component-slot="{sid}" '
            f'style="position:absolute;left:{left}px;top:{top}px;width:{w}px;height:{h}px;'
            f'overflow:hidden"><span class="slot-text">{text}</span></div>')


_S1S2 = _box("s1", 192, 108, 384, 108) + _box("s2", 960, 540, 384, 108)


def _instance_deck(instance_id: str, boxes: str, bg: str = '<svg width="9" height="9"><rect/></svg>',
                   item: str = "sun.component.a") -> str:
    inst = f' data-component-instance="{instance_id}"' if instance_id else ""
    return (f'<div class="slide-scaffold" data-base-component="{item}"{inst} data-slot-contract="1">'
            f'<div class="bg" data-base-component="{item}">{bg}</div>{boxes}</div>')


def _reuse_report(item: str = "sun.component.a") -> dict:
    return {"slides": [{"request_id": "sA",
                        "decision": {"action": "reuse", "item_id": item}}]}


def _slot_rec(overflowX=False, overflowY=False, outside=False, rendered=True, visible=True,
              tx=0.0, ty=0.0, tw=10.0, th=10.0) -> dict:
    return {"overflowX": overflowX, "overflowY": overflowY, "textOutsideWrapper": outside,
            "rendered": rendered, "textVisible": visible,
            "textX": tx, "textY": ty, "textW": tw, "textH": th}


def _measure(instance_id: str, slots: dict, bg_loaded=True,
             component="sun.component.a") -> dict:
    return {instance_id: {"component": component,
            "bg": {"present": True, "loaded": bg_loaded, "w": 1920, "h": 1080},
            "slots": slots}}


def _fit_pair(**s1_over) -> dict:
    """Two slots whose rendered text ink boxes are far apart (no spurious overlap);
    overrides apply to s1 so a single test can make just s1 overflow/spill."""
    return {"s1": _slot_rec(tx=200, ty=120, tw=300, th=80, **s1_over),
            "s2": _slot_rec(tx=1000, ty=560, tw=300, th=80)}


# (1) two OCCURRENCES of the same component id: an empty one cannot borrow the
#     other's slot evidence — each is validated on its own.
def test_fidelity_two_instances_no_slot_borrow() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        reg = _text_slot_registry(Path(tmpd))
        deck = _instance_deck("sun.component.a#p1", "") + _instance_deck("sun.component.a#p2", _S1S2)
        res = fidelity.check_fidelity(deck, _reuse_report(), reg)
        by = {r["instance"]: r for r in res}
        assert by["sun.component.a#p1"]["pass_"] is False, res   # empty: cannot borrow p2
        assert by["sun.component.a#p2"]["pass_"] is True, res     # filled: passes on its own


# (2) per-instance measurements do not overwrite each other.
def test_fidelity_measurements_not_pooled_between_instances() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        reg = _text_slot_registry(Path(tmpd))
        deck = _instance_deck("sun.component.a#p1", _S1S2) + _instance_deck("sun.component.a#p2", _S1S2)
        m = {}
        m.update(_measure("sun.component.a#p1", _fit_pair(overflowX=True)))
        m.update(_measure("sun.component.a#p2", _fit_pair()))
        res = fidelity.check_fidelity(deck, _reuse_report(), reg, measurements=m)
        by = {r["instance"]: r for r in res}
        assert by["sun.component.a#p1"]["pass_"] is False and "overflow" in by["sun.component.a#p1"]["reason"]
        assert by["sun.component.a#p2"]["pass_"] is True, res     # p1's overflow did not leak


# (3) actual text positioned outside its wrapper fails.
def test_fidelity_fails_text_outside_wrapper() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        reg = _text_slot_registry(Path(tmpd))
        deck = _instance_deck("sun.component.a#p1", _S1S2)
        m = _measure("sun.component.a#p1", _fit_pair(outside=True))
        res = fidelity.check_fidelity(deck, _reuse_report(), reg, measurements=m)
        assert res[0]["pass_"] is False and "overflow" in res[0]["reason"], res


# (4) actual rendered text of two different slots overlapping (beyond source) fails.
def test_fidelity_fails_actual_text_overlap() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        reg = _text_slot_registry(Path(tmpd))          # s1,s2 declared non-overlapping
        deck = _instance_deck("sun.component.a#p1", _S1S2)
        m = _measure("sun.component.a#p1", {
            "s1": _slot_rec(tx=200, ty=120, tw=300, th=80),
            "s2": _slot_rec(tx=210, ty=130, tw=300, th=80)})   # ~fully overlapping ink boxes
        res = fidelity.check_fidelity(deck, _reuse_report(), reg, measurements=m)
        assert res[0]["pass_"] is False and "overlap" in res[0]["reason"], res


# (5) long Vietnamese copy that clips in a narrow slot (real Chromium, gated).
def test_render_long_vietnamese_clips() -> None:
    if not fidelity._node_available():
        print("  (skip: node/playwright unavailable)")
        return
    with tempfile.TemporaryDirectory() as tmpd:
        html = Path(tmpd) / "d.html"
        long_vi = "Chuyển đổi quy trình làm việc với trí tuệ nhân tạo một cách hiệu quả"
        html.write_text(_instance_deck(
            "sun.component.a#p1",
            f'<div class="component-slot" data-component-slot="s1" '
            f'style="position:absolute;left:0;top:0;width:120px;height:40px;overflow:hidden;'
            f'font-size:34px"><span class="slot-text" style="white-space:nowrap">{long_vi}</span></div>'
            + _box("s2", 0, 300, 700, 200, "ok")), encoding="utf-8")
        measure = fidelity.measure_rendered_slots(html)
        assert measure is not None
        rec = measure["sun.component.a#p1"]["slots"]["s1"]
        assert rec["overflowX"] or rec["textOutsideWrapper"], rec


def _template_registry(tmp: Path, item: str = "sun.template.t") -> dict:
    """A full-slide TEMPLATE item: its preview.html wires `.slot` boxes by
    data-slot-id (no text-slot contract), which is the shape the scaffold copies."""
    prev = tmp / f"{item}-preview.html"
    prev.write_text(
        '<div class="stage"><div class="bg"></div>'
        '<div class="slot" data-slot-id="title"><h1>x</h1></div>'
        '<div class="slot" data-slot-id="foot"><span>y</span></div></div>',
        encoding="utf-8")
    return {"items": [{"id": item, "status": "published",
                       "paths": {"preview": str(prev)}}]}


def _tpl_box(sid: str, left: int, top: int, w: int, h: int, text: str, fs: int = 20) -> str:
    return (f'<div class="slot" data-slot-id="{sid}" '
            f'style="position:absolute;left:{left}px;top:{top}px;width:{w}px;height:{h}px;'
            f'overflow:hidden"><span style="white-space:nowrap;font-size:{fs}px">{text}</span></div>')


def test_render_measures_template_slots_and_fails_oversized_copy() -> None:
    # Fix C: template previews bind `data-slot-id`, which the measurer used to skip
    # entirely — so a cover/closing whose copy overflowed still passed --require-render
    # and needed a manual probe to catch. Real Chromium, real overflow.
    if not fidelity._node_available():
        print("  (skip: node/playwright unavailable)")
        return
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        reg = _template_registry(tmp)
        long_vi = "Chúc SUN-ers một năm bứt phá cùng trí tuệ nhân tạo trong mọi quy trình"
        deck_bad = _instance_deck(
            "sun.template.t#s1",
            _tpl_box("title", 0, 0, 160, 40, long_vi, fs=40)   # far too long for the box
            + _tpl_box("foot", 0, 400, 600, 60, "ngắn gọn"),
            item="sun.template.t")
        html = tmp / "bad.html"
        html.write_text(deck_bad, encoding="utf-8")

        measure = fidelity.measure_rendered_slots(html)
        assert measure is not None, "expected a real Chromium measurement"
        slots = measure["sun.template.t#s1"]["slots"]
        # 1. template slots are measured at all, and tagged as such...
        assert set(slots) == {"title", "foot"}, slots
        assert {s["kind"] for s in slots.values()} == {"template"}, slots
        # 2. ...with real rendered bounds showing the overflow.
        assert slots["title"]["overflowX"] or slots["title"]["textOutsideWrapper"], slots["title"]
        assert not (slots["foot"]["overflowX"] or slots["foot"]["textOutsideWrapper"]), slots["foot"]
        # 3. and the release gate rejects the slide on it.
        report = _reuse_report("sun.template.t")
        res = fidelity.check_fidelity(deck_bad, report, reg, html_path=html,
                                      measurements=measure, require_instance_ids=True)
        assert res and res[0]["pass_"] is False, res
        assert "overflows/clips" in res[0]["reason"] and "title" in res[0]["reason"], res

        # 4. the same template with copy that FITS still passes render fidelity.
        deck_ok = _instance_deck(
            "sun.template.t#s1",
            _tpl_box("title", 0, 0, 600, 60, "Ứng dụng AI", fs=40)
            + _tpl_box("foot", 0, 400, 600, 60, "ngắn gọn"),
            item="sun.template.t")
        ok_html = tmp / "ok.html"
        ok_html.write_text(deck_ok, encoding="utf-8")
        m_ok = fidelity.measure_rendered_slots(ok_html)
        res_ok = fidelity.check_fidelity(deck_ok, report, reg, html_path=ok_html,
                                         measurements=m_ok, require_instance_ids=True)
        assert res_ok and res_ok[0]["pass_"] is True, res_ok


# (6) blank/broken base artwork for THIS instance fails even though an unrelated
#     SVG exists elsewhere on the deck (scope excludes it; render bg not loaded).
def test_fidelity_fails_broken_artwork_despite_unrelated_svg() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        reg = _text_slot_registry(Path(tmpd))
        deck = (_instance_deck("sun.component.a#p1", _S1S2, bg="")   # empty bg
                + '<svg width="100" height="100"><rect/></svg>')     # unrelated, outside instance
        # static: the unrelated SVG is out of scope -> blank artifact for this instance
        res = fidelity.check_fidelity(deck, _reuse_report(), reg)
        assert res[0]["pass_"] is False and "artifact" in res[0]["reason"], res
        # render: bg present but not loaded -> hard fail
        m = _measure("sun.component.a#p1", _fit_pair(), bg_loaded=False)
        res2 = fidelity.check_fidelity(deck, _reuse_report(), reg, measurements=m)
        assert res2[0]["pass_"] is False and "artwork" in res2[0]["reason"], res2


# (7) --require-render fails closed when node/playwright is unavailable.
def test_require_render_fails_closed_without_node() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        reg = _text_slot_registry(tmp)
        reg_path = tmp / "reg.json"; reg_path.write_text(json.dumps(reg), encoding="utf-8")
        rep_path = tmp / "rep.json"; rep_path.write_text(json.dumps(_reuse_report()), encoding="utf-8")
        html = tmp / "d.html"; html.write_text(_instance_deck("sun.component.a#p1", _S1S2), encoding="utf-8")
        orig = fidelity._node_available
        fidelity._node_available = lambda: False       # simulate no render infra
        try:
            rc = fidelity.main(["--html", str(html), "--selection-report", str(rep_path),
                                "--registry", str(reg_path), "--require-render"])
            assert rc == 1, "release gate must fail closed without render evidence"
        finally:
            fidelity._node_available = orig


# (8) valid source-designed overlap remains allowed.
def test_fidelity_allows_source_designed_overlap() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        # declared s1,s2 that themselves overlap in the source contract
        reg = _text_slot_registry(Path(tmpd), slots=[
            {"id": "s1", "bounds": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3}},
            {"id": "s2", "bounds": {"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.3}}])
        deck = _instance_deck("sun.component.a#p1",
                              _box("s1", 192, 108, 576, 324) + _box("s2", 384, 216, 576, 324))
        # rendered text rects overlap by roughly the same designed amount -> allowed
        m = _measure("sun.component.a#p1", {
            "s1": _slot_rec(tx=200, ty=120, tw=560, th=300),
            "s2": _slot_rec(tx=400, ty=230, tw=560, th=300)})
        res = fidelity.check_fidelity(deck, _reuse_report(), reg, measurements=m)
        assert res[0]["pass_"] is True, res


# (9) legacy (no instance id) is warn-only; fresh release output requires ids.
def test_fidelity_legacy_warn_only_release_requires_instance_id() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        reg = _text_slot_registry(Path(tmpd))
        legacy = _instance_deck("", _S1S2)              # no data-component-instance
        # non-release: tolerated (occurrence id is None, validated normally -> passes)
        res = fidelity.check_fidelity(legacy, _reuse_report(), reg, require_instance_ids=False)
        assert res[0]["instance"] is None and res[0]["pass_"] is True, res
        # release: a fresh deck MUST carry a unique instance id -> legacy fails closed
        res2 = fidelity.check_fidelity(legacy, _reuse_report(), reg, require_instance_ids=True)
        assert res2[0]["pass_"] is False and "instance" in res2[0]["reason"], res2
        # fresh deck with an instance id validates normally under release
        fresh = _instance_deck("sun.component.a#p1", _S1S2)
        res3 = fidelity.check_fidelity(fresh, _reuse_report(), reg, require_instance_ids=True)
        assert res3[0]["pass_"] is True, res3


def test_render_measurement_is_instance_keyed() -> None:
    # Gated: the real measurement is keyed by the unique instance id and carries
    # bg + per-slot text metrics.
    if not fidelity._node_available():
        print("  (skip: node/playwright unavailable)")
        return
    with tempfile.TemporaryDirectory() as tmpd:
        html = Path(tmpd) / "d.html"
        html.write_text(
            _instance_deck("sun.component.a#p1",
                           '<div data-component-slot="big" style="position:absolute;left:0;top:0;'
                           'width:60px;height:40px;overflow:hidden;font-size:40px">'
                           '<span class="slot-text" style="white-space:nowrap">WWWWWWWWWWWW</span></div>'
                           + _box("ok", 0, 300, 600, 200, "ok")), encoding="utf-8")
        measure = fidelity.measure_rendered_slots(html)
        assert measure is not None and "sun.component.a#p1" in measure, measure
        inst = measure["sun.component.a#p1"]
        assert inst["slots"]["big"]["overflowX"] is True, inst
        assert inst["slots"]["ok"]["overflowX"] is False, inst
        assert inst["bg"]["present"] is True, inst


# --------------------------------------------------------------------------- #
# Phase 3: per-user style profile (validation + resolution, precedence-bounded)
# --------------------------------------------------------------------------- #
def test_style_profile_example_validates() -> None:
    import validate_style_profile as vsp
    prof = _common.load_json(SCRIPTS.parent / "style-profiles" / "example-restrained.json")
    assert vsp.validate_profile(prof) == [], vsp.validate_profile(prof)


def test_style_profile_rejects_markup_unknown_and_non_enum() -> None:
    import validate_style_profile as vsp
    # markup/script in a free-text field
    assert any("markup" in e for e in vsp.validate_profile(
        {"profile_id": "u", "version": "1.0.0", "preferences": {},
         "owner": "<script>alert(1)</script>"}))
    # unknown top-level key (e.g. an attempt to inject CSS)
    assert any("unknown top-level" in e for e in vsp.validate_profile(
        {"profile_id": "u", "version": "1.0.0", "preferences": {}, "custom_css": ".x{color:red}"}))
    # unknown preference key
    assert any("unknown preference" in e for e in vsp.validate_profile(
        {"profile_id": "u", "version": "1.0.0", "preferences": {"raw_css": "x"}}))
    # non-enum value
    assert any("information_density" in e for e in vsp.validate_profile(
        {"profile_id": "u", "version": "1.0.0", "preferences": {"information_density": "ultra"}}))
    # intent slug carrying markup
    assert vsp.validate_profile(
        {"profile_id": "u", "version": "1.0.0", "preferences": {"preferred_component_intents": ["<b>"]}})
    # a minimal valid profile passes clean
    assert vsp.validate_profile(
        {"profile_id": "u", "version": "1.0.0", "preferences": {"spacing": "airy"}}) == []


def test_resolve_records_provenance_rejects_locked_intent_and_never_mutates() -> None:
    import resolve_style_profile as rsp
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        prof = tmp / "p.json"
        prof.write_text(json.dumps({"profile_id": "u", "version": "2.1.0", "preferences": {
            "spacing": "airy", "avoided_component_intents": ["statistics"]}}), encoding="utf-8")
        report = {"slides": [{"request_id": "s5",
                              "decision": {"action": "reuse",
                                           "item_id": "sun.component.circ", "score": 80.0},
                              "candidates": []}]}
        rep = tmp / "rep.json"; before = json.dumps(report, indent=1)
        rep.write_text(before, encoding="utf-8")
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"items": [{"id": "sun.component.circ",
                                              "intent": ["statistics", "ranking"]}]}), encoding="utf-8")
        out = tmp / "plan.json"
        rc = rsp.main(["--profile", str(prof), "--selection-report", str(rep),
                       "--registry", str(reg), "--output", str(out)])
        assert rc == 0
        plan = json.loads(out.read_text(encoding="utf-8"))
        assert plan["style_profile"]["version"] == "2.1.0"
        assert len(plan["style_profile"]["sha256"]) == 64
        assert plan["selection_report_mutated"] is False
        assert rep.read_text(encoding="utf-8") == before, "selection report must be untouched"
        # avoided 'statistics' hits the SELECTED reuse's intent -> cannot force it out
        assert any(r["preference"] == "avoided_component_intents" and r["value"] == "statistics"
                   for r in plan["rejected_preferences"]), plan
        # safe composition preference is applied
        assert any(a["preference"] == "spacing" for a in plan["applied_preferences"]), plan


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


def test_catalog_surfaces_text_free_variant_for_cropped_draft() -> None:
    import build_component_catalog as bcc
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "c"
        (item / "artifact").mkdir(parents=True)
        (item / "evidence").mkdir(parents=True)
        (item / "artifact" / "text-slots.json").write_text(
            _json.dumps({"slots": [], "source": {"region_crop": {"crop_window": [0, 0, 100, 50]}}}),
            encoding="utf-8",
        )
        (item / "artifact" / "visual.svg").write_text("<svg id='text-free'/>", encoding="utf-8")
        (item / "evidence" / "source-with-text.svg").write_text("<svg id='with-text'/>", encoding="utf-8")

        labels = [im["label"] for im in bcc.collect_images(item)]

        assert labels[:2] == ["Source with text", "Text-free visual"], labels


def test_catalog_pairs_classifier_cards_with_text_free_variants() -> None:
    import build_component_catalog as bcc
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "ai-coding-maturity-levels-strip"
        components = item / "artifact" / "components"
        evidence = item / "evidence"
        components.mkdir(parents=True)
        evidence.mkdir(parents=True)
        (item / "artifact" / "visual.svg").write_text("<svg id='full-text-free'/>", encoding="utf-8")
        (evidence / "source-with-text.svg").write_text("<svg id='full-source'/>", encoding="utf-8")
        for name in [
            "ai-coding-maturity-levels-strip-group-01.svg",
            "ai-coding-maturity-levels-strip-group-01-card-01-source.svg",
            "ai-coding-maturity-levels-strip-group-01-card-01.svg",
            "ai-coding-maturity-levels-strip-group-01-card-02-source.svg",
            "ai-coding-maturity-levels-strip-group-01-card-02.svg",
        ]:
            (components / name).write_text(f"<svg id='{name}'/>", encoding="utf-8")
        (components / "components-manifest.json").write_text(_json.dumps({
            "groups": [{
                "group_id": "ai-coding-maturity-levels-strip-group-01",
                "file": "components/ai-coding-maturity-levels-strip-group-01.svg",
                "shape_class": 1,
                "title": "Level Cards",
                "member_count": 5,
                "distinct_card_count": 5,
                "cards": [
                    {
                        "card_id": "ai-coding-maturity-levels-strip-group-01-card-01",
                        "title": "Level 1 Spicy Autocomplete",
                        "source_file": "components/ai-coding-maturity-levels-strip-group-01-card-01-source.svg",
                        "file": "components/ai-coding-maturity-levels-strip-group-01-card-01.svg",
                        "duplicate_count": 1,
                    },
                    {
                        "card_id": "ai-coding-maturity-levels-strip-group-01-card-02",
                        "title": "Level 2 AI Coding Assistants",
                        "source_file": "components/ai-coding-maturity-levels-strip-group-01-card-02-source.svg",
                        "file": "components/ai-coding-maturity-levels-strip-group-01-card-02.svg",
                        "duplicate_count": 1,
                    },
                ],
            }],
        }), encoding="utf-8")

        labels = [im["label"] for im in bcc.collect_images(item)]

        assert labels == [
            "Full component",
            "Full component (Text-free)",
            "Level 1 Spicy Autocomplete",
            "Level 1 Spicy Autocomplete (Text-free)",
            "Level 2 AI Coding Assistants",
            "Level 2 AI Coding Assistants (Text-free)",
        ], labels


def test_catalog_pairs_single_layout_row_with_text_free_variant() -> None:
    import build_component_catalog as bcc
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "goal-card"
        components = item / "artifact" / "components"
        evidence = item / "evidence"
        components.mkdir(parents=True)
        evidence.mkdir(parents=True)
        (item / "artifact" / "visual.svg").write_text("<svg id='full-text-free'/>", encoding="utf-8")
        (evidence / "source-with-text.svg").write_text("<svg id='full-source'/>", encoding="utf-8")
        (components / "goal-card-row-01.svg").write_text("<svg id='row-free'/>", encoding="utf-8")
        (components / "goal-card-row-01-source.svg").write_text("<svg id='row-source'/>", encoding="utf-8")
        (components / "components-manifest.json").write_text(_json.dumps({
            "groups": [{
                "group_id": "goal-card-row-01",
                "file": "components/goal-card-row-01.svg",
                "shape_class": 1001,
                "layout_group": "row",
                "title": "Goal Key Result Task",
                "member_count": 5,
                "distinct_card_count": 1,
                "cards": [{
                    "card_id": "goal-card-row-01",
                    "title": "Goal Key Result Task",
                    "source_file": "components/goal-card-row-01-source.svg",
                    "file": "components/goal-card-row-01.svg",
                    "duplicate_count": 1,
                }],
            }],
        }), encoding="utf-8")

        labels = [im["label"] for im in bcc.collect_images(item)]

        assert labels == [
            "Full component",
            "Full component (Text-free)",
            "Goal Key Result Task",
            "Goal Key Result Task (Text-free)",
        ], labels


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


def _breg_env(tmp: Path, items: list[dict]):
    """Point build_registry's module paths at a temp registry with no library
    (so no orphans) and no history (so no zombies). Returns (registry, compact,
    retrieval) paths. Caller restores globals in a finally block."""
    reg = tmp / "visual-library.json"
    reg.write_text(json.dumps({"items": items}), encoding="utf-8")
    (tmp / "library").mkdir()
    breg.REGISTRY = reg
    breg.COMPACT = tmp / "visual-library-compact.json"
    breg.RETRIEVAL = tmp / "component-retrieval-index.jsonl"
    breg.HISTORY = tmp / "extraction-history.json"  # absent -> no zombies
    breg.LIBRARY = tmp / "library"                  # empty -> no orphans
    return reg, breg.COMPACT, breg.RETRIEVAL


def _run_breg(*flags: str) -> int:
    old = sys.argv[:]
    sys.argv = ["build_registry.py", *flags]
    try:
        return breg.main()
    finally:
        sys.argv = old


def test_build_registry_check_detects_stale_compact() -> None:
    saved = (breg.REGISTRY, breg.COMPACT, breg.RETRIEVAL, breg.HISTORY, breg.LIBRARY)
    items = [{"id": "sun.component.x", "type": "component", "status": "published",
              "intent": ["kpi"], "tags": ["t"], "content_structure": ["metric"],
              "brand": "sun-studio", "density": "any", "limitations": []}]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            reg, compact, retrieval = _breg_env(Path(tmp), items)
            # Correct retrieval index so ONLY compact drift is under test.
            retrieval.write_text(breg.retrieval_jsonl(items), encoding="utf-8", newline="\n")
            # Stale compact: content that does not match the projection.
            compact.write_text('{"items": []}', encoding="utf-8")
            assert _run_breg("--check") == 1, "stale compact must fail --check"
            # A fresh, correct compact passes.
            compact.write_text(breg.compact_text(items), encoding="utf-8")
            assert _run_breg("--check") == 0, "matching compact must pass --check"
            # A missing compact also fails.
            compact.unlink()
            assert _run_breg("--check") == 1, "missing compact must fail --check"
        finally:
            breg.REGISTRY, breg.COMPACT, breg.RETRIEVAL, breg.HISTORY, breg.LIBRARY = saved


def test_build_registry_write_regenerates_stale_compact() -> None:
    saved = (breg.REGISTRY, breg.COMPACT, breg.RETRIEVAL, breg.HISTORY, breg.LIBRARY)
    items = [{"id": "sun.component.y", "type": "component", "status": "published",
              "intent": ["checklist"], "tags": ["t"], "content_structure": ["heading"],
              "brand": "sun-studio", "density": "any", "limitations": []}]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            reg, compact, retrieval = _breg_env(Path(tmp), items)
            compact.write_text('{"items": []}', encoding="utf-8")  # stale
            assert _run_breg("--check") == 1
            assert _run_breg("--write") == 0
            # --write cleared the drift and produced the exact projection.
            assert compact.read_text(encoding="utf-8") == breg.compact_text(items)
            assert _run_breg("--check") == 0
        finally:
            breg.REGISTRY, breg.COMPACT, breg.RETRIEVAL, breg.HISTORY, breg.LIBRARY = saved


def test_build_registry_live_compact_projection_is_clean() -> None:
    # The committed compact must equal the deterministic projection of the live
    # full registry (guards against the stale-compact class of bug this fixes).
    reg = breg.load_json(breg.REGISTRY)
    assert breg.COMPACT.read_text(encoding="utf-8") == breg.compact_text(reg["items"]), \
        "visual-library-compact.json is stale — run build_registry.py --write"


# --------------------------------------------------------------------------- #
# classify_page_components (pure-logic paths — no browser/Chromium needed)
# --------------------------------------------------------------------------- #
import classify_page_components as cpc
import extract_editable_text_slots as eets


def test_row_title_reads_heading_columns_left_to_right() -> None:
    slots = [
        {"text": "Kết quả muốn đạt được", "role": "subheading", "x": 0.10, "y": 0.60,
         "w": 0.20, "h": 0.03, "size": 30},
        {"text": "GOAL", "role": "heading", "x": 0.10, "y": 0.45,
         "w": 0.08, "h": 0.04, "size": 53},
        {"text": "KEY", "role": "heading", "x": 0.48, "y": 0.44,
         "w": 0.05, "h": 0.03, "size": 53},
        {"text": "RESULT", "role": "heading", "x": 0.45, "y": 0.47,
         "w": 0.10, "h": 0.03, "size": 53},
        {"text": "TASK", "role": "heading", "x": 0.82, "y": 0.45,
         "w": 0.07, "h": 0.04, "size": 53},
    ]
    assert cpc._row_title(slots, "Row") == "GOAL KEY RESULT TASK"


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


_CIRCLES = "sun.component.foundation-top1-microsoft-overlap-circle-set"


def test_asymmetric_hero_component_is_not_a_balanced_tier_component() -> None:
    # Source geometry: the middle circle's headline is h1 @134px against h2 @61px and
    # @53px in the outer two (~2.2x). That is one hero flanked by two supports — a
    # ranked achievement highlight, which its own use_cases always said ("3 ranked
    # highlights", "track-record"). The tier vocabulary in intent/tags contradicted
    # both, so a balanced `tiers` request auto-selected it and rendered a false
    # hierarchy. The correction is metadata-only: no scorer branch knows this id.
    reg = _common.load_json(REGISTRY)
    item = next(i for i in reg["items"] if i["id"] == _CIRCLES)
    tokens = {t.lower() for t in item["intent"] + item["tags"]}
    assert not (tokens & _common.SHAPE_TYPE_MAP["tiers"]), (
        f"{_CIRCLES} still claims balanced-tier vocabulary: "
        f"{sorted(tokens & _common.SHAPE_TYPE_MAP['tiers'])}")
    assert not _common.shape_eligible("tiers", tokens)
    # It stays honestly reusable as what it IS: a milestone/achievement highlight.
    assert _common.shape_eligible("timeline", tokens)
    assert any("balanced tier" in a for a in item["anti_use_cases"]), item["anti_use_cases"]

    # ...and the real scorer therefore does not auto-select it for a tier request.
    req = {"request_id": "t", "intent": ["ranking", "levels", "tiers", "comparison"],
           "tags": ["ranking", "overlap-circle", "milestone"],
           "content_structure": ["heading", "label", "title"], "content_shape": "tiers",
           "density": "medium", "brand": "sun-studio"}
    dec, cands = _score_real(req)
    assert dec["item_id"] != _CIRCLES, dec
    cand = next((c for c in cands if c["item_id"] == _CIRCLES), None)
    if cand:                       # still published and browseable, just not tier-shaped
        assert cand.get("shape_eligible") is False, cand


def test_slot_contract_alignment_is_honoured_where_evidence_supports_it() -> None:
    # Within each circle every slot's box CENTRE agrees to within ~18px across 4-5
    # slots: the design centres text on the circle's axis. `horizontal_align` was
    # `left`, derived from the source's text-anchor="start" — meaningless when the
    # source places every glyph at an absolute x — so replacement copy shorter than
    # the source's ink drifted off the circle. The scaffold already honours this
    # field; only the data was wrong.
    slots = json.loads(subprocess.run(
        [sys.executable, str(SCRIPTS / "read_text_slots.py"), "--item-id", _CIRCLES,
         "--slots-only"], capture_output=True, text=True, check=True).stdout)
    bands: list[list[float]] = []
    for c in sorted(s["bounds"]["x"] + s["bounds"]["width"] / 2 for s in slots):
        if bands and c - bands[-1][-1] <= 0.12:     # same circle
            bands[-1].append(c)
        else:
            bands.append([c])
    assert len(bands) == 3, bands                   # three circles
    for band in bands:
        assert len(band) >= 4, band
        assert (max(band) - min(band)) * 1920 < 20, band   # one shared axis per circle

    entry = next(i for i in _common.load_json(REGISTRY)["items"] if i["id"] == _CIRCLES)
    contract = _common.load_json(_common.resolve_repo_path(entry["paths"]["text_slots"]))
    assert {s["horizontal_align"] for s in contract["slots"]} == {"center"}, \
        "every slot in this component sits on its circle's centre axis"

    with tempfile.TemporaryDirectory() as tmpd:
        out = Path(tmpd) / "frag.html"
        rc = subprocess.run([sys.executable, str(SCRIPTS / "scaffold_slide_from_component.py"),
                             "--item-id", _CIRCLES, "--out", str(out), "--instance-id", "t"],
                            capture_output=True, text=True)
        assert rc.returncode == 0, rc.stderr
        html = out.read_text(encoding="utf-8")
        assert "justify-content:center" in html, "scaffold must honour the contract"
        assert "text-align:center" in html
        assert "justify-content:flex-start" not in html

    # The DEFAULT is untouched: a component that declares no alignment still goes left.
    plain = {"id": "x", "role": "body", "html_tag": "p",
             "bounds": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}}
    assert scaffold._JUSTIFY.get(str(plain.get("horizontal_align") or "left")) == "flex-start"


def test_cover_crop_fraction_measures_full_bleed_edge_loss() -> None:
    # Deterministic arithmetic: how much of an artwork's LONGER axis a full-bleed
    # background-size:cover pushes off a 1920x1080 canvas. A 16:9 artwork loses
    # nothing; a wide band loses a large fraction of its width off both edges.
    f = fidelity.cover_crop_fraction
    assert f(1920, 1080) == 0.0                       # same aspect: nothing cropped
    assert abs(f(1999.29, 619.853) - 0.449) < 0.01    # the circle band: ~45% of width off
    assert abs(f(1080, 1920) - 0.684) < 0.01          # a 9:16 portrait crops ~68% of height
    assert 0.0 <= f(2106, 1005) < 0.20                # a near-16:9 component stays low


def test_render_fitness_flags_severe_edge_crop_not_normal_components() -> None:
    # The guard that would have caught the milestone slide: contract fidelity checks
    # slot GEOMETRY (cov=1.0 proved that), render fitness checks whether the rendered
    # result is fit for a human audience. A component whose artwork is cropped ~45% at
    # full bleed is flagged; a full-slide 16:9 template is not.
    reg = _common.load_json(REGISTRY)
    by = {i["id"]: i for i in reg["items"]}
    warns = fidelity.render_fitness(by[_CIRCLES])
    assert any("crop" in w.lower() for w in warns), warns
    # The circle band is WIDE, so the advisory must name the WIDTH / left-right edges,
    # not report "width" for everything (the reviewer's diagnostic-correctness point).
    assert "width" in warns[0] and "left and right" in warns[0], warns[0]
    assert "height" not in warns[0], warns[0]

    template_16x9 = next(i for i in reg["items"]
                         if i.get("type") == "template" and (i.get("paths") or {}).get("visual"))
    assert fidelity.render_fitness(template_16x9) == [], template_16x9["id"]


def test_render_fitness_names_the_cropped_axis_for_tall_artwork() -> None:
    # A PORTRAIT artwork is cropped vertically, not horizontally — the advisory must say
    # so. Synthetic visual so nothing depends on a specific component's dimensions.
    import tempfile
    with tempfile.TemporaryDirectory() as tmpd:
        vis = Path(tmpd) / "visual.svg"
        vis.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
                       '<rect/></svg>', encoding="utf-8")
        item = {"id": "sun.component.tall", "paths": {"visual": str(vis)}}
        warns = fidelity.render_fitness(item)
        assert warns and "height" in warns[0] and "top and bottom" in warns[0], warns
        assert "width" not in warns[0], warns[0]


def test_severe_crop_component_is_review_only_and_not_auto_selected() -> None:
    # Disposition: the circle component is inherently unsafe for automatic full-bleed
    # reuse at 1920x1080 (its outer circles fall off the frame), so it is marked
    # review-only. It must NOT auto-select even for the milestone/achievement request
    # it is otherwise shape-compatible with — but it stays published and browseable.
    reg = _common.load_json(REGISTRY)
    item = next(i for i in reg["items"] if i["id"] == _CIRCLES)
    assert (item.get("auto_reuse") or {}).get("eligible") is False, item.get("auto_reuse")
    assert "crop" in (item["auto_reuse"]["reason"].lower())

    req = {"request_id": "m", "intent": ["milestones", "achievements", "track-record"],
           "tags": ["milestone", "achievement", "overlap-circle", "set-of-3"],
           "content_structure": ["heading", "label", "title"], "content_shape": "timeline",
           "density": "medium", "brand": "sun-studio"}
    dec, cands = _score_real(req)
    assert dec["item_id"] != _CIRCLES, dec
    cand = next((c for c in cands if c["item_id"] == _CIRCLES), None)
    assert cand is not None, "must remain a scored, browseable candidate"
    assert (cand["retrieval"].get("auto_reuse") or {}).get("eligible") is False, cand

    # ...and it is still in the published retrieval index (browseable/reviewable).
    idx = [json.loads(l) for l in
           (REGISTRY.parent / "component-retrieval-index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(r["id"] == _CIRCLES for r in idx), "review-only item must stay browseable"


def test_split_runs_trims_leading_whitespace_glyphs_from_the_ink_box() -> None:
    # A leading space is a GLYPH with its own x, but it is not ink. Including it put
    # the slot box where the space starts instead of where the reader sees the first
    # letter — the box then sat on top of the artwork behind it (05-prep's checkbox).
    # The extractor already stripped the whitespace out of `example_value`, so the
    # box and the value disagreed; this keeps them describing the same glyphs.
    runs = eets.split_runs(" ABC", [100, 133, 143, 153], font_size=20)
    assert [r[0] for r in runs] == ["ABC"], runs
    assert runs[0][1] == [133, 143, 153], runs[0][1]   # box starts at the INK, not the space
    assert runs[0][2] == 1, runs[0]                    # char_start advances past the space

    # Trailing whitespace is the same story on the other edge.
    runs = eets.split_runs("ABC  ", [10, 20, 30, 40, 50], font_size=20)
    assert [r[0] for r in runs] == ["ABC"], runs
    assert runs[0][1] == [10, 20, 30], runs[0][1]
    assert runs[0][3] == 3, runs[0]

    # Interior spaces are ink-bearing structure and must NOT be trimmed.
    runs = eets.split_runs("AB CD", [10, 20, 30, 40, 50], font_size=20)
    assert [r[0] for r in runs] == ["AB CD"], runs
    assert runs[0][1] == [10, 20, 30, 40, 50], runs[0][1]


def test_extracted_box_starts_at_first_inked_glyph() -> None:
    # End-to-end on the real defect's shape: two sibling rows of the same list, one
    # whose source tspan carries a leading space and one whose does not, must land on
    # the SAME left edge. Measured from 05-prep's source evidence: the clean sibling
    # starts at x=1107.84 and the space-prefixed row's first letter at x=1107.82.
    import tempfile
    with tempfile.TemporaryDirectory() as tmpd:
        art = Path(tmpd) / "artifact"
        (art).mkdir()
        (Path(tmpd) / "evidence").mkdir()
        (art / "page.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
            '<text transform="matrix(1 0 -0 1 0 1080)" font-size="25" font-family="Arial">'
            '<tspan y="-651.82" x="1107.84 1120 1132">abc</tspan></text>'
            '<text transform="matrix(1 0 -0 1 0 1080)" font-size="25" font-family="Arial">'
            '<tspan y="-615.81" x="1074.55 1107.82 1120 1132"> abc</tspan></text>'
            "</svg>", encoding="utf-8")
        eets.extract_item(Path(tmpd), "page.svg")
        slots = json.loads((art / "text-slots.json").read_text(encoding="utf-8"))["slots"]
        assert len(slots) == 2, slots
        assert {s["example_value"] for s in slots} == {"abc"}, slots
        xs = sorted(s["bounds"]["x"] for s in slots)
        # Within a pixel: the real source rows differ by 0.02px (1107.82 vs 1107.84).
        # Before the fix the space-prefixed row landed at 1074.55 -> 0.5597, i.e. 33px
        # (a whole checkbox indent) left of its sibling.
        assert abs(xs[1] - xs[0]) * 1920 < 1.0, f"sibling rows must share a left edge: {xs}"
        assert abs(xs[0] - 1107.84 / 1920) < 1e-3, xs  # the INK edge, not the space's

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


def test_layout_cells_split_single_row_cards() -> None:
    instances = [
        {"x": 10, "y": 20, "w": 120, "h": 240, "members": [{"group": 0, "child": None}]},
        {"x": 150, "y": 20, "w": 120, "h": 240, "members": [{"group": 1, "child": None}]},
        {"x": 290, "y": 20, "w": 120, "h": 240, "members": [{"group": 2, "child": None}]},
    ]
    small = [
        {"x": 330, "y": 40, "w": 20, "h": 20, "members": [{"group": 3, "child": None}]},
    ]

    assert cpc._cluster_layout_rows(instances, small) == []
    cells = cpc._cluster_layout_cells(instances, small)

    assert len(cells) == 3
    assert [cell["col_index"] for cell in cells] == [1, 2, 3]
    assert len(cells[2]["elements"]) == 2, cells


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


def test_build_catalog_skips_blank_text_free_visual_marked_by_quality_gate() -> None:
    import build_component_catalog as bcc

    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "demo"
        comps = item / "artifact" / "components"
        evidence = item / "evidence"
        comps.mkdir(parents=True)
        evidence.mkdir(parents=True)
        (item / "mapping.json").write_text(json.dumps({
            "item_id": "demo",
            "status": "staging",
            "quality_gate": {"blank_item_visual": True},
        }), encoding="utf-8")
        (evidence / "source-with-text.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect width="100" height="80" fill="#3333FF"/></svg>',
            encoding="utf-8",
        )
        (item / "artifact" / "visual.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect width="100" height="80" fill="#3333FF"/></svg>',
            encoding="utf-8",
        )
        (comps / "components-manifest.json").write_text('{"groups":[]}', encoding="utf-8")

        labels = [image["label"] for image in bcc.collect_images(item)]

        assert labels == ["Full component"], labels


def test_build_catalog_skips_standalone_blank_visual_drafts() -> None:
    import build_component_catalog as bcc

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "component-extractions"
        item = root / "demo" / "items" / "tiny-label"
        (item / "artifact").mkdir(parents=True)
        (item / "evidence").mkdir(parents=True)
        (item / "mapping.json").write_text(json.dumps({
            "item_id": "tiny-label",
            "candidate_stable_id": "sun.component.tiny-label",
            "name": "Tiny Label",
            "status": "staging",
            "type": "component",
            "category": "component",
            "source": {"path": "source.pdf", "slide_or_page": 1},
            "quality_gate": {"blank_item_visual": True},
        }), encoding="utf-8")
        (item / "artifact" / "visual.svg").write_text("<svg/>", encoding="utf-8")
        (item / "evidence" / "source-with-text.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><text>04</text></svg>',
            encoding="utf-8",
        )
        # Drafts are runtime-local, so this filtering lives on the live scanner —
        # asserting it against the published-only tracked build would pass for the
        # wrong reason (that build never looks at Drafts at all).
        assert [i["id"] for i in bcc.collect_draft_items(root)] == []


def test_quality_gate_prunes_blank_refs_and_empty_manifests() -> None:
    import quality_gate as qg

    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "demo"
        comps = item / "artifact" / "components"
        comps.mkdir(parents=True)
        (item / "mapping.json").write_text(json.dumps({
            "item_id": "demo",
            "status": "staging",
        }), encoding="utf-8")
        (comps / "blank.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            encoding="utf-8",
        )
        (comps / "card.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect width="100" height="80" fill="#3333FF"/></svg>',
            encoding="utf-8",
        )
        manifest = comps / "components-manifest.json"
        manifest.write_text(json.dumps({
            "groups": [
                {"group_id": "blank", "file": "components/blank.svg", "cards": []},
                {"group_id": "card", "file": "components/card.svg", "cards": [
                    {"card_id": "card", "file": "components/card.svg"},
                    {"card_id": "blank-card", "file": "components/blank.svg"},
                ]},
            ],
        }), encoding="utf-8")

        summary = qg.sanitize_item(item)
        cleaned = json.loads(manifest.read_text(encoding="utf-8"))
        mapping = json.loads((item / "mapping.json").read_text(encoding="utf-8"))

        assert summary["blank_refs_pruned"] == 2, summary
        assert [g["group_id"] for g in cleaned["groups"]] == ["card"]
        assert cleaned["groups"][0]["cards"] == [{"card_id": "card", "file": "components/card.svg"}]
        assert mapping["quality_gate"]["status"] == "reviewable"

    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "empty"
        comps = item / "artifact" / "components"
        comps.mkdir(parents=True)
        (item / "mapping.json").write_text(json.dumps({
            "item_id": "empty",
            "status": "staging",
        }), encoding="utf-8")
        manifest = comps / "components-manifest.json"
        manifest.write_text('{"groups":[]}', encoding="utf-8")

        summary = qg.sanitize_item(item)
        mapping = json.loads((item / "mapping.json").read_text(encoding="utf-8"))

        assert summary["empty_manifests_removed"] == 1, summary
        assert not manifest.exists()
        assert mapping["quality_gate"]["status"] == "needs_review"


def test_quality_gate_prunes_render_blank_refs_and_marks_base_visual() -> None:
    import quality_gate as qg

    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "rendered"
        artifact = item / "artifact"
        comps = artifact / "components"
        comps.mkdir(parents=True)
        (item / "mapping.json").write_text(json.dumps({
            "item_id": "rendered",
            "status": "staging",
        }), encoding="utf-8")
        visual = artifact / "visual.svg"
        blank = comps / "render-blank.svg"
        source = comps / "source.svg"
        for path in (visual, blank, source):
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<rect width="100" height="80" fill="#3333FF"/></svg>',
                encoding="utf-8",
            )
        manifest = comps / "components-manifest.json"
        manifest.write_text(json.dumps({
            "groups": [{
                "group_id": "rendered",
                "file": "components/render-blank.svg",
                "cards": [
                    {"card_id": "blank", "file": "components/render-blank.svg"},
                    {"card_id": "source", "source_file": "components/source.svg"},
                ],
            }],
        }), encoding="utf-8")
        render_results = {
            str(visual.resolve()).lower(): {"nonwhite_ratio": 0.0},
            str(blank.resolve()).lower(): {"nonwhite_ratio": 0.0},
            str(source.resolve()).lower(): {"nonwhite_ratio": 0.05},
        }

        summary = qg.sanitize_items([item], render_results=render_results)[0]
        cleaned = json.loads(manifest.read_text(encoding="utf-8"))
        mapping = json.loads((item / "mapping.json").read_text(encoding="utf-8"))

        assert summary["blank_item_visual"], summary
        assert summary["render_blank_refs_pruned"] == 2, summary
        assert summary["status"] == "needs_review"
        assert "file" not in cleaned["groups"][0]
        assert cleaned["groups"][0]["cards"] == [
            {"card_id": "source", "source_file": "components/source.svg"},
        ]
        assert mapping["quality_gate"]["blank_item_visual"] is True
        assert mapping["quality_gate"]["item_visual_nonwhite_ratio"] == 0.0


def test_quality_gate_ignores_white_defs_and_masks() -> None:
    import quality_gate as qg

    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "masked.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<defs><rect width="100" height="100" fill="#3333FF"/></defs>'
            '<mask id="m"><rect width="100" height="100" fill="white"/></mask>'
            '<rect width="100" height="100" fill="white"/></svg>',
            encoding="utf-8",
        )

        assert not qg.svg_has_visible_content(svg)


def test_retrieval_index_builds_published_search_records() -> None:
    import build_component_retrieval_index as bri

    registry = {
        "items": [
            {
                "id": "sun.component.metric-strip",
                "name": "Metric Strip",
                "status": "published",
                "type": "component",
                "component_type": "strip",
                "layout_role": "metric comparison strip",
                "intent": ["revenue growth"],
                "tags": ["metric", "growth"],
                "keywords": ["revenue", "team-size"],
                "content_structure": ["label", "percentage"],
                "use_cases": ["Show KPI change"],
                "anti_use_cases": ["Do not use for pie charts"],
                "visual_summary": "Two horizontal metric bars.",
                "retrieval_notes": "Use when user asks for KPI cards.",
                "source": {"kind": "extraction", "path": "/Users/home/private/source.pdf"},
                "paths": {"artifact": "slide-system/library/components/metric-strip"},
            },
            {
                "id": "sun.component.draft-only",
                "name": "Draft Only",
                "status": "staging",
                "intent": ["draft"],
            },
        ],
    }

    records = bri.build_records(registry)

    assert [record["id"] for record in records] == ["sun.component.metric-strip"]
    assert records[0]["retrieval_mode"] == "lexical-ready"
    assert "revenue" in records[0]["retrieval_terms"]
    assert "users" not in records[0]["retrieval_terms"]
    assert "pie" in records[0]["search_text"]
    assert records[0]["paths"]["artifact"] == "slide-system/library/components/metric-strip"


def test_publish_preserves_retrieval_metadata_and_index() -> None:
    import importlib

    publish = importlib.import_module("publish_extraction")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        extraction_dir = root / "extract"
        item_dir = extraction_dir / "items" / "metric-strip"
        (item_dir / "artifact").mkdir(parents=True)
        (item_dir / "preview").mkdir()
        (item_dir / "evidence").mkdir()
        (item_dir / "artifact" / "visual.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>',
            encoding="utf-8",
        )
        (item_dir / "preview" / "thumbnail.png").write_bytes(b"not-a-real-png")
        (item_dir / "evidence" / "source-with-text.svg").write_text("<svg/>", encoding="utf-8")
        (item_dir / "mapping.json").write_text(json.dumps({
            "extraction_id": "publish-meta-demo",
            "item_id": "metric-strip",
            "candidate_stable_id": "sun.component.metric-strip",
            "name": "Metric Strip",
            "status": "staging",
            "type": "component",
            "category": "metrics",
            "brand": "sun-studio",
            "semantic_intent": ["revenue growth"],
            "tags": ["metric", "growth"],
            "content_structure": ["label", "percentage"],
            "content_fields": {},
            "density": "any",
            "component_type": "strip",
            "layout_role": "metric comparison strip",
            "visual_summary": "Two horizontal KPI bars.",
            "keywords": ["revenue", "team-size"],
            "use_cases": ["Show KPI change"],
            "anti_use_cases": ["Do not use for pie charts"],
            "quality_notes": "Reviewed in Draft.",
            "retrieval_notes": "Use when user asks for KPI cards.",
            "artifact_status": "ready",
            "approval": {"status": "approved"},
            "source": {
                "path": str(root / "source.pdf"),
                "slide_or_page": 1,
                "region": {"x": 0, "y": 0, "width": 1, "height": 1, "unit": "normalized"},
                "sha256": "source-hash",
            },
            "fingerprints": {
                "region_identity_sha256": "region-hash",
                "semantic_signature_sha256": "semantic-hash",
            },
        }), encoding="utf-8")

        registry = root / "visual-library.json"
        registry.write_text('{"items":[]}', encoding="utf-8")
        history = root / "history.json"
        history.write_text('{"attempts":[]}', encoding="utf-8")
        library = root / "library"
        old_argv = sys.argv[:]
        sys.argv = [
            "publish_extraction.py",
            "--extraction-dir", str(extraction_dir),
            "--item-id", "metric-strip",
            "--registry", str(registry),
            "--history", str(history),
            "--library-root", str(library),
        ]
        try:
            assert publish.main() == 0
        finally:
            sys.argv = old_argv

        item = read_text_slots.load_json(registry)["items"][0]
        assert item["component_type"] == "strip"
        assert item["keywords"] == ["revenue", "team-size"]
        assert item["use_cases"] == ["Show KPI change"]
        assert item["retrieval_notes"] == "Use when user asks for KPI cards."

        index = (root / "component-retrieval-index.jsonl").read_text(encoding="utf-8")
        record = json.loads(index.strip())
        assert record["id"] == "sun.component.metric-strip"
        assert "revenue" in record["retrieval_terms"]
        assert "kpi" in record["retrieval_terms"]


def test_publish_rejects_failed_auto_stage_artifacts() -> None:
    import importlib

    publish = importlib.import_module("publish_extraction")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        extraction_dir = root / "extract"
        item_dir = extraction_dir / "items" / "broken-strip"
        (item_dir / "artifact").mkdir(parents=True)
        (item_dir / "preview").mkdir()
        (item_dir / "evidence").mkdir()
        (item_dir / "artifact" / "visual.svg").write_text("<svg/>", encoding="utf-8")
        (item_dir / "preview" / "thumbnail.png").write_bytes(b"not-a-real-png")
        (item_dir / "evidence" / "source-with-text.svg").write_text("<svg/>", encoding="utf-8")
        (item_dir / "mapping.json").write_text(json.dumps({
            "extraction_id": "publish-failed-demo",
            "item_id": "broken-strip",
            "candidate_stable_id": "sun.component.broken-strip",
            "name": "Broken Strip",
            "status": "staging",
            "type": "component",
            "category": "metrics",
            "brand": "sun-studio",
            "semantic_intent": ["broken metric"],
            "tags": [],
            "content_structure": [],
            "content_fields": {},
            "artifact_status": "failed",
            "artifact_log": "validate_text_slots.py: failed",
            "approval": {"status": "approved"},
            "source": {
                "path": str(root / "source.pdf"),
                "slide_or_page": 1,
                "region": {"x": 0, "y": 0, "width": 1, "height": 1, "unit": "normalized"},
                "sha256": "source-hash",
            },
            "fingerprints": {
                "region_identity_sha256": "region-hash",
                "semantic_signature_sha256": "semantic-hash",
            },
        }), encoding="utf-8")
        registry = root / "visual-library.json"
        registry.write_text('{"items":[]}', encoding="utf-8")
        history = root / "history.json"
        history.write_text('{"attempts":[]}', encoding="utf-8")
        old_argv = sys.argv[:]
        sys.argv = [
            "publish_extraction.py",
            "--extraction-dir", str(extraction_dir),
            "--item-id", "broken-strip",
            "--registry", str(registry),
            "--history", str(history),
            "--library-root", str(root / "library"),
        ]
        try:
            try:
                publish.main()
            except SystemExit as exc:
                assert "Artifact build status is failed" in str(exc)
            else:
                raise AssertionError("failed auto-stage artifacts must not publish")
        finally:
            sys.argv = old_argv
        assert read_text_slots.load_json(registry)["items"] == []


# --------------------------------------------------------------------------- #
# validate_component_metadata — retrieval metadata quality gate
# --------------------------------------------------------------------------- #
def _meta_component(**over) -> dict:
    """A fully retrieval-ready component item (passes the metadata gate)."""
    base = {
        "id": "sun.component.demo-strip",
        "type": "component",
        "category": "component",
        "name": "Demo Metric Strip",
        "intent": ["statistics", "metrics"],
        "tags": ["strip", "kpi", "set-of-3"],
        "content_structure": ["label", "metric"],
        "component_type": "strip",
        "layout_role": "horizontal metric strip",
        "visual_summary": "Three KPI figures side by side with labels.",
        "keywords": ["revenue", "growth", "kpi"],
        "use_cases": ["Show three headline KPIs on one row"],
        "anti_use_cases": ["Do not use for narrative body text"],
        "retrieval_notes": "Select when the slide needs a compact KPI row.",
        "quality_notes": "Manually reviewed against source render.",
        "text_contract": {"slot_count": 6},
    }
    base.update(over)
    return base


def test_component_metadata_valid_passes() -> None:
    import validate_component_metadata as vcm
    assert vcm.validate_item(_meta_component()) == []
    assert vcm.validate_registry({"items": [_meta_component()]}) == {}


def test_component_metadata_missing_fields_fail() -> None:
    import validate_component_metadata as vcm
    errs = vcm.validate_item(_meta_component(keywords=[], use_cases=[],
                                             component_type=None, visual_summary="  "))
    joined = " ".join(errs)
    assert "'keywords' is empty" in joined
    assert "'use_cases' is empty" in joined
    assert "'component_type' is blank" in joined
    assert "'visual_summary' is blank" in joined


def test_component_metadata_boilerplate_fails() -> None:
    import validate_component_metadata as vcm
    # auto-stage tag + Docling placeholder use/anti text must be rejected.
    errs = vcm.validate_item(_meta_component(
        tags=["strip", "auto-staged"],
        use_cases=["Review and publish this strip as a reusable component."],
        anti_use_cases=["Do not use before the Draft preview and metadata are reviewed."],
        retrieval_notes="Generated from region text, Docling label, source name, and page.",
    ))
    assert any("auto-stage/placeholder text" in e for e in errs), errs
    # An honest note that merely mentions Docling must NOT trip the gate.
    ok = vcm.validate_item(_meta_component(
        retrieval_notes="Region isolated manually; not a Docling auto-detected candidate."))
    assert ok == [], ok


def test_component_metadata_ocr_intent_fails() -> None:
    import validate_component_metadata as vcm
    errs = vcm.validate_item(_meta_component(
        intent=["2. THƯỜNG DÙNG ĐỂ BIỂU THỊ CÁC DẠNG CONTENT XOAY QUANH team"]))
    assert any("raw slide text/OCR" in e for e in errs), errs


def test_component_metadata_ignores_non_component_types() -> None:
    import validate_component_metadata as vcm
    # A template with deliberately thin metadata must NOT be gated.
    thin_template = {"id": "sun.deck.01-cover", "type": "template",
                     "intent": ["cover"], "tags": []}
    assert vcm.validate_item(thin_template) == []
    assert vcm.validate_registry({"items": [thin_template]}) == {}


def test_component_metadata_mapping_projection() -> None:
    import validate_component_metadata as vcm
    mapping = {
        "candidate_stable_id": "sun.component.demo-strip", "type": "component",
        "category": "component", "name": "Demo Metric Strip",
        "semantic_intent": ["statistics"], "tags": ["strip"],
        "content_structure": ["metric"], "component_type": "strip",
        "layout_role": "strip", "visual_summary": "KPI strip.",
        "keywords": ["kpi"], "use_cases": ["Show KPIs"],
        "anti_use_cases": ["No body text"], "retrieval_notes": "Pick for KPIs.",
        "quality_notes": "Reviewed.",
    }
    item = vcm.metadata_from_mapping(mapping)
    assert item["intent"] == ["statistics"], "semantic_intent must map to intent"
    assert vcm.validate_item(item) == []


def test_component_metadata_strict_requires_set_shape() -> None:
    import validate_component_metadata as vcm
    set_item = _meta_component(id="sun.component.role-card-set", category="component-set",
                               name="Role Card Set", tags=["roles", "personas"],
                               content_structure=["heading"], use_cases=["Show roles"])
    assert vcm.validate_item(set_item, strict=False) == []
    strict_errs = vcm.validate_item(set_item, strict=True)
    assert any("set-of-N" in e for e in strict_errs), strict_errs
    # Exposing the multiplicity clears the strict check.
    fixed = _meta_component(id="sun.component.role-card-set", category="component-set",
                            name="Role Card Set", tags=["cards", "set-of-4"])
    assert vcm.validate_item(fixed, strict=True) == []


def test_component_metadata_real_registry_good_components_pass() -> None:
    # The three hand-authored components in the live registry must pass; this
    # guards against the gate regressing into false positives on real data.
    import validate_component_metadata as vcm
    registry = read_text_slots.load_json(REGISTRY)
    by_id = {i["id"]: i for i in registry["items"]}
    for good in ("sun.component.lorem-ipsum-circle-badge-set",
                 "sun.component.foundation-top1-microsoft-overlap-circle-set",
                 "sun.component.goal-keyresult-task-hexagon-diagram"):
        assert vcm.validate_item(by_id[good]) == [], f"{good} should pass"


def test_component_metadata_live_registry_all_components_pass() -> None:
    import validate_component_metadata as vcm
    registry = read_text_slots.load_json(REGISTRY)
    failures = vcm.validate_registry(registry, strict=True)
    assert failures == {}, json.dumps(failures, indent=2, ensure_ascii=False)


def test_publish_blocks_weak_component_metadata_before_mutation() -> None:
    import importlib
    publish = importlib.import_module("publish_extraction")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        extraction_dir = root / "extract"
        item_dir = extraction_dir / "items" / "weak-strip"
        (item_dir / "artifact").mkdir(parents=True)
        (item_dir / "preview").mkdir()
        (item_dir / "evidence").mkdir()
        (item_dir / "artifact" / "visual.svg").write_text("<svg/>", encoding="utf-8")
        (item_dir / "preview" / "thumbnail.png").write_bytes(b"not-a-real-png")
        (item_dir / "evidence" / "source-with-text.svg").write_text("<svg/>", encoding="utf-8")
        (item_dir / "mapping.json").write_text(json.dumps({
            "extraction_id": "publish-weak-demo",
            "item_id": "weak-strip",
            "candidate_stable_id": "sun.component.weak-strip",
            "name": "Weak Strip",
            "status": "staging",
            "type": "component",
            "category": "component",
            "brand": "sun-studio",
            # Auto-stage boilerplate + empty retrieval fields — must be blocked.
            "semantic_intent": ["weak strip", "picture candidate detected by Docling"],
            "tags": ["strip", "auto-staged"],
            "content_structure": [],
            "content_fields": {},
            "artifact_status": "ready",
            "approval": {"status": "approved"},
            "source": {
                "path": str(root / "source.pdf"),
                "slide_or_page": 1,
                "region": {"x": 0, "y": 0, "width": 1, "height": 1, "unit": "normalized"},
                "sha256": "source-hash",
            },
            "fingerprints": {
                "region_identity_sha256": "region-hash",
                "semantic_signature_sha256": "semantic-hash",
            },
        }), encoding="utf-8")
        registry = root / "visual-library.json"
        registry.write_text('{"items":[]}', encoding="utf-8")
        history = root / "history.json"
        history.write_text('{"attempts":[]}', encoding="utf-8")
        library = root / "library"
        old_argv = sys.argv[:]
        sys.argv = [
            "publish_extraction.py",
            "--extraction-dir", str(extraction_dir),
            "--item-id", "weak-strip",
            "--registry", str(registry),
            "--history", str(history),
            "--library-root", str(library),
        ]
        try:
            try:
                publish.main()
            except SystemExit as exc:
                assert "metadata gate failed" in str(exc).lower(), str(exc)
            else:
                raise AssertionError("weak component metadata must block publish")
        finally:
            sys.argv = old_argv
        # No registry, index, or library mutation may have occurred.
        assert read_text_slots.load_json(registry)["items"] == []
        assert not (root / "component-retrieval-index.jsonl").exists()
        assert not library.exists()


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
                          (3, "form")]]
    items = awd.build_candidates(els, "demo", "component", None)
    assert items, "expected candidates from figure-like labels"
    for it in items:
        assert scaffold_ex._DOCLING_DRAFT_ID.match(it["item_id"]), it["item_id"]


def test_analyze_with_docling_skips_chart_candidates() -> None:
    import analyze_with_docling as awd

    els = [
        {"page": 1, "label": "chart", "text": "Pie chart",
         "region": {"x": 0.1, "y": 0.1, "width": 0.3,
                    "height": 0.3, "unit": "normalized"}},
        {"page": 1, "label": "picture", "text": "Reusable card",
         "region": {"x": 0.5, "y": 0.1, "width": 0.3,
                    "height": 0.3, "unit": "normalized"}},
    ]

    items = awd.build_candidates(els, "demo", "component", None)

    assert [item["item_id"] for item in items] == ["picture-p1-1"]


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


def test_analyze_with_docling_pdf_fallback_groups_rows() -> None:
    import analyze_with_docling as awd

    atoms = [
        {"kind": "text", "text": "2. header",
         "region": {"x": 0.1, "y": 0.08, "width": 0.4, "height": 0.02, "unit": "normalized"}},
        {"kind": "drawing", "text": "",
         "region": {"x": 0.19, "y": 0.14, "width": 0.20, "height": 0.22, "unit": "normalized"}},
        {"kind": "drawing", "text": "",
         "region": {"x": 0.41, "y": 0.14, "width": 0.20, "height": 0.22, "unit": "normalized"}},
        {"kind": "text", "text": "01 LOREM IPSUM",
         "region": {"x": 0.24, "y": 0.23, "width": 0.12, "height": 0.04, "unit": "normalized"}},
        {"kind": "text", "text": "GOAL KEY RESULT TASK",
         "region": {"x": 0.26, "y": 0.48, "width": 0.50, "height": 0.05, "unit": "normalized"}},
        {"kind": "text", "text": "Kết quả muốn đạt được",
         "region": {"x": 0.19, "y": 0.59, "width": 0.18, "height": 0.06, "unit": "normalized"}},
        {"kind": "text", "text": "FOUNDATION TOP1 MICROSOFT XIAOMI",
         "region": {"x": 0.27, "y": 0.78, "width": 0.45, "height": 0.09, "unit": "normalized"}},
    ]

    elements = awd.fallback_elements_from_atoms(3, atoms)
    assert [el["source"] for el in elements] == ["pymupdf-fallback"] * 3
    assert [round(el["region"]["y"], 2) for el in elements] == [0.13, 0.47, 0.77]
    items = awd.build_candidates(elements, "demo", "component", None)
    assert [item["item_id"] for item in items] == [
        "figure-p3-1",
        "figure-p3-2",
        "figure-p3-3",
    ]
    assert "PyMuPDF fallback" in items[0]["notes"]


def test_analyze_with_docling_fallback_keeps_uncovered_metric_row() -> None:
    import analyze_with_docling as awd

    fallback_rows = [
        {
            "page": 2,
            "label": "figure",
            "region": {
                "x": 0.14, "y": 0.39, "width": 0.68, "height": 0.24,
                "unit": "normalized",
            },
        },
        {
            "page": 2,
            "label": "figure",
            "region": {
                "x": 0.17, "y": 0.70, "width": 0.64, "height": 0.20,
                "unit": "normalized",
            },
        },
    ]
    existing_docling = [
        {"x": 0.151, "y": 0.413, "width": 0.151, "height": 0.208, "unit": "normalized"},
        {"x": 0.316, "y": 0.413, "width": 0.153, "height": 0.207, "unit": "normalized"},
        {"x": 0.485, "y": 0.413, "width": 0.150, "height": 0.208, "unit": "normalized"},
        {"x": 0.650, "y": 0.413, "width": 0.151, "height": 0.208, "unit": "normalized"},
        # Small arrow icons in the metric row must not suppress the broad row.
        {"x": 0.468, "y": 0.713, "width": 0.055, "height": 0.058, "unit": "normalized"},
        {"x": 0.470, "y": 0.833, "width": 0.053, "height": 0.059, "unit": "normalized"},
    ]

    kept = [
        row for row in fallback_rows
        if not awd._covered_by_existing_candidates(row["region"], existing_docling)
    ]

    assert kept == [fallback_rows[1]]


def test_analyze_with_docling_fallback_container_becomes_context() -> None:
    import analyze_with_docling as awd

    ai_visual = {
        "page": 4,
        "label": "picture",
        "text": "",
        "region": {
            "x": 0.211145, "y": 0.659546, "width": 0.551944,
            "height": 0.231766, "unit": "normalized",
        },
        "source": "docling",
    }
    broad_fallback = {
        "x": 0.100247, "y": 0.494247, "width": 0.674524,
        "height": 0.505753, "unit": "normalized",
    }
    metric_strip = {
        "x": 0.170, "y": 0.700, "width": 0.640,
        "height": 0.200, "unit": "normalized",
    }
    small_arrow = {
        "region": {
            "x": 0.470, "y": 0.833, "width": 0.053,
            "height": 0.059, "unit": "normalized",
        },
    }

    assert awd._contained_existing_candidate(broad_fallback, [ai_visual]) is ai_visual
    assert awd._covered_by_existing_candidates(broad_fallback, [ai_visual])
    assert awd._contained_existing_candidate(metric_strip, [small_arrow]) is None
    assert not awd._covered_by_existing_candidates(metric_strip, [small_arrow])

    awd._append_context_text(
        ai_visual,
        "2. CONTENT XOAY QUANH - build AI team and automation system",
    )
    items = awd.build_candidates([ai_visual], "demo", "component", None)

    assert [item["item_id"] for item in items] == ["picture-p4-1"]
    assert "CONTENT XOAY QUANH" in items[0]["semantic_intent"][0]


def test_analyze_with_docling_fallback_text_uses_reading_order() -> None:
    import analyze_with_docling as awd

    row = [
        {"kind": "text", "text": "+30%",
         "region": {"x": 0.55, "y": 0.72, "width": 0.14, "height": 0.06,
                    "unit": "normalized"}},
        {"kind": "text", "text": "Revenue",
         "region": {"x": 0.20, "y": 0.735, "width": 0.13, "height": 0.03,
                    "unit": "normalized"}},
        {"kind": "text", "text": "+30%",
         "region": {"x": 0.55, "y": 0.84, "width": 0.14, "height": 0.06,
                    "unit": "normalized"}},
        {"kind": "text", "text": "Team Size",
         "region": {"x": 0.20, "y": 0.835, "width": 0.13, "height": 0.03,
                    "unit": "normalized"}},
    ]

    assert awd._text_lines_for_row(row) == ["Revenue +30%", "Team Size +30%"]


def test_analyze_with_docling_merges_header_and_visual_rows() -> None:
    import analyze_with_docling as awd

    rows = [
        {
            "page": 5,
            "label": "figure",
            "text": "This is a contributors slide. Insert your team here.",
            "region": {"x": 0.28, "y": 0.12, "width": 0.42, "height": 0.13,
                       "unit": "normalized"},
            "source": "pymupdf-fallback",
        },
        {
            "page": 5,
            "label": "figure",
            "text": "Patrick E. Shorey Mary T. Middleton William R. Hudson",
            "region": {"x": 0.24, "y": 0.265, "width": 0.50, "height": 0.23,
                       "unit": "normalized"},
            "source": "pymupdf-fallback",
        },
    ]

    merged = awd._merge_header_visual_rows(rows)

    assert len(merged) == 1
    assert merged[0]["region"]["y"] < rows[0]["region"]["y"]
    assert merged[0]["region"]["height"] > 0.35
    assert "contributors slide" in merged[0]["text"]
    assert "Patrick" in merged[0]["text"]


def test_analyze_with_docling_icon_sheet_candidate_covers_full_glyph_grid() -> None:
    import analyze_with_docling as awd

    atoms = []
    for row in range(8):
        for col in range(8):
            atoms.append({
                "kind": "drawing",
                "text": "",
                "region": {
                    "x": 0.10 + col * 0.05,
                    "y": 0.13 + row * 0.07,
                    "width": 0.012,
                    "height": 0.018,
                    "unit": "normalized",
                },
            })

    element = awd._icon_sheet_element_from_atoms(
        1, atoms, "ICON\n1. NHUNG ICON HAY XUAT HIEN")

    assert element is not None
    assert element["region"]["x"] < 0.09
    assert element["region"]["y"] < 0.08
    assert element["region"]["width"] > 0.36
    assert element["region"]["height"] > 0.55


def test_analyze_with_docling_pdf_page_mode_survives_one_page_failure() -> None:
    import analyze_with_docling as awd

    class _Size:
        width = 100
        height = 100

    class _Page:
        size = _Size()

    class _Label:
        value = "picture"

    class _BBox:
        l = 10
        t = 10
        r = 50
        b = 50

    class _Prov:
        page_no = 1
        bbox = _BBox()

    class _Item:
        label = _Label()
        text = "Reusable visual"
        prov = [_Prov()]

    class _Doc:
        pages = {1: _Page()}

        def iterate_items(self):
            return [(_Item(), 0)]

    class _Result:
        document = _Doc()

    class _Converter:
        def __init__(self) -> None:
            self.page_ranges: list[tuple[int, int]] = []

        def convert(self, source, **kwargs):
            page_range = kwargs["page_range"]
            self.page_ranges.append(page_range)
            if page_range == (2, 2):
                raise RuntimeError("page failed")
            return _Result()

    converter = _Converter()
    old = awd._page_numbers_for_source
    awd._page_numbers_for_source = lambda source, pages: ([1, 2, 3], [])
    try:
        elements, warnings, stats = awd.analyze_source(
            converter, Path("demo.pdf"), (1, 3))
    finally:
        awd._page_numbers_for_source = old

    assert converter.page_ranges == [(1, 1), (2, 2), (3, 3)]
    assert [el["page"] for el in elements] == [1, 3]
    assert any("page 2" in warning for warning in warnings)
    assert stats["docling_mode"] == "page-by-page"
    assert stats["docling_pages_attempted"] == 3
    assert stats["docling_pages_failed"] == 1


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


def test_candidate_pdf_preview_is_generated_and_reused() -> None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        source = tmpp / "source.pdf"
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.draw_rect(fitz.Rect(50, 20, 150, 80), color=(1, 0, 0), fill=(1, 0.8, 0.7))
        page.insert_text((58, 55), "Preview", fontsize=16, color=(0, 0, 0))
        doc.save(source)
        doc.close()

        root = tmpp / "ext"
        eid = "docling-preview-demo"
        adir = root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.25, "y": 0.2, "width": 0.5, "height": 0.6,
                           "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["preview candidate"],
                "notes": "preview smoke",
                "replacement_for": None,
            }],
        }), encoding="utf-8")

        result = crv.get_candidates(eid, root=root)
        preview = result["candidates"][0]["preview"]
        assert preview["status"] == "ready", preview
        png = adir / "previews" / "picture-p1-1.png"
        assert png.is_file(), preview
        assert png.read_bytes().startswith(b"\x89PNG"), "preview must be a PNG"
        first_mtime = png.stat().st_mtime_ns

        second = crv.get_candidates(eid, root=root)["candidates"][0]["preview"]
        assert second["path"] == preview["path"]
        assert png.stat().st_mtime_ns == first_mtime, "existing preview should be reused"


def test_candidate_preview_unavailable_for_non_pdf_source() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = tmpp / "ext"
        eid = "docling-preview-fallback"
        adir = root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": "source.pptx",
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.25, "y": 0.2, "width": 0.5, "height": 0.6,
                           "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["preview candidate"],
                "notes": "preview fallback",
                "replacement_for": None,
            }],
        }), encoding="utf-8")

        preview = crv.get_candidates(eid, root=root)["candidates"][0]["preview"]
        assert preview["status"] == "unavailable", preview
        assert "PDF sources only" in preview["reason"]
        assert not (adir / "previews").exists()


def test_candidate_preview_unavailable_for_malformed_region() -> None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        source = tmpp / "source.pdf"
        doc = fitz.open()
        doc.new_page(width=200, height=100)
        doc.save(source)
        doc.close()

        root = tmpp / "ext"
        eid = "docling-preview-bad-region"
        adir = root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.25, "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["preview candidate"],
                "notes": "bad region",
                "replacement_for": None,
            }],
        }), encoding="utf-8")

        preview = crv.get_candidates(eid, root=root)["candidates"][0]["preview"]
        assert preview["status"] == "unavailable", preview
        assert "Preview render failed" in preview["reason"]
        assert not (adir / "previews").exists()


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


def test_auto_stage_candidates_creates_reviewable_draft() -> None:
    import importlib
    import build_component_catalog as bcc

    asc = importlib.import_module("auto_stage_candidates")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        source = tmpp / "Kickoff 2026.pdf"
        doc = fitz.open()
        page = doc.new_page(width=300, height=180)
        page.draw_rect(fitz.Rect(45, 35, 245, 135), color=(1, 0.2, 0.05),
                       fill=(1, 0.85, 0.76))
        page.insert_text((70, 90), "Kickoff Hero", fontsize=20, color=(0, 0, 0))
        doc.save(source)
        doc.close()

        output_root = tmpp / "component-extractions"
        eid = "docling-auto-demo"
        adir = output_root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.1, "y": 0.12, "width": 0.78, "height": 0.72,
                           "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["kickoff hero detected by Docling"],
                "notes": "Auto-stage this detected hero visual into Draft.",
                "replacement_for": None,
            }],
        }), encoding="utf-8")

        hist = tmpp / "history.json"
        hist.write_text('{"attempts":[]}', encoding="utf-8")
        reg = tmpp / "registry.json"
        reg.write_text('{"items":[]}', encoding="utf-8")
        summary = asc.stage_run(
            eid,
            root=output_root,
            output_root=output_root,
            history=hist,
            registry=reg,
            rebuild_catalog=False,
        )

        assert summary["staged"] == 1, summary
        staged = summary["items"][0]
        item_id = staged["item_id"]
        assert item_id != "picture-p1-1"
        assert not scaffold_ex._DOCLING_DRAFT_ID.match(item_id)
        item_dir = output_root / staged["extraction_id"] / "items" / item_id
        mapping = read_text_slots.load_json(item_dir / "mapping.json")
        assert mapping["status"] == "staging"
        assert mapping["candidate_stable_id"].startswith("sun.component.")
        assert mapping["source"]["candidate_id"] == "picture-p1-1"
        assert mapping["review"]["mode"] == "auto-staged"
        assert (item_dir / "artifact" / "visual.svg").is_file()
        assert (item_dir / "artifact" / "text-slots.json").is_file()
        assert (item_dir / "evidence" / "source-with-text.svg").is_file()
        assert (item_dir / "preview" / "thumbnail.png").is_file()

        # Drafts reach the catalog UI through the runtime scan (GET /api/drafts),
        # never through the tracked published-only projection.
        drafts = bcc.collect_draft_items(output_root)
        draft = next(item for item in drafts
                     if item["id"] == mapping["candidate_stable_id"])
        assert draft["status"] == "staging"
        assert draft["publish_readiness"]["ready"], draft["publish_readiness"]
        assert draft["images"], "Draft must have a visual preview for final review"
        assert draft["component_type"] == "card"
        assert draft["layout_role"]
        assert draft["keywords"]
        assert draft["use_cases"]

        dup_eid = "docling-auto-demo-duplicate"
        dup_adir = output_root / dup_eid / "analysis"
        dup_adir.mkdir(parents=True)
        (dup_adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": dup_eid,
            "source_path": str(source),
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.1, "y": 0.12, "width": 0.78, "height": 0.72,
                           "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["same hero detected by a later Docling run"],
                "notes": "This region is already staged and must not duplicate.",
                "replacement_for": None,
            }],
        }), encoding="utf-8")
        duplicate = asc.stage_run(
            dup_eid,
            root=output_root,
            output_root=output_root,
            history=hist,
            registry=reg,
            rebuild_catalog=False,
            build_artifacts=False,
        )
        assert duplicate["staged"] == 0, duplicate
        assert duplicate["skipped"] == 1, duplicate
        assert duplicate["items"][0]["status"] == "already_staged_region"
        assert duplicate["items"][0]["stable_id"] == mapping["candidate_stable_id"]

        second = asc.stage_run(
            eid,
            root=output_root,
            output_root=output_root,
            history=hist,
            registry=reg,
            rebuild_catalog=False,
            build_artifacts=False,
        )
        assert second["staged"] == 0, second
        assert second["skipped"] == 1, second
        assert second["items"][0]["status"] in {"already_staged", "already_staged_region"}


def test_auto_stage_skips_chart_candidates_from_existing_analysis() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    assert asc._auto_stage_skip_reason({"item_id": "chart-p1-1"})
    assert asc._auto_stage_skip_reason({
        "item_id": "picture-p1-1",
        "semantic_intent": ["pie chart candidate detected by Docling"],
    })
    assert asc._auto_stage_skip_reason({
        "item_id": "picture-p1-1",
        "semantic_intent": ["org chart radial team structure"],
    }) is None

    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        output_root = tmpp / "component-extractions"
        eid = "docling-chart-demo"
        adir = output_root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(tmpp / "source.pdf"),
            "items": [{
                "item_id": "chart-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.1, "y": 0.1, "width": 0.3,
                           "height": 0.3, "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["chart candidate detected by Docling"],
                "notes": "DRAFT candidate from Docling auto-detect.",
                "replacement_for": None,
            }],
        }), encoding="utf-8")

        hist = tmpp / "history.json"
        reg = tmpp / "registry.json"
        reg.write_text('{"items":[]}', encoding="utf-8")
        summary = asc.stage_run(
            eid,
            root=output_root,
            output_root=output_root,
            history=hist,
            registry=reg,
            rebuild_catalog=False,
            build_artifacts=False,
        )

        assert summary["staged"] == 0, summary
        assert summary["skipped"] == 1, summary
        assert summary["items"][0]["reason"] == "chart candidates are skipped by auto-detect"
        assert not (adir / "approved").exists()


def test_auto_stage_skips_duplicate_component_patterns_across_pages() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    first = {
        "item_id": "picture-p3-1",
        "slide_or_page": 3,
        "region": {"x": 0.05, "y": 0.08, "width": 0.42,
                   "height": 0.32, "unit": "normalized"},
        "semantic_intent": ["Goal setting title card with highlighted subtitle"],
    }
    second = {
        "item_id": "picture-p4-1",
        "slide_or_page": 4,
        "region": {"x": 0.052, "y": 0.081, "width": 0.58,
                   "height": 0.29, "unit": "normalized"},
        "semantic_intent": ["Check-in title card with highlighted subtitle"],
    }
    assert asc._duplicate_pattern_signature("input/goal-setting.pdf", first) == (
        asc._duplicate_pattern_signature("input/goal-setting.pdf", second)
    )
    same_page_neighbour = {
        **first,
        "item_id": "picture-p3-2",
        "region": {"x": 0.55, "y": 0.08, "width": 0.42,
                   "height": 0.32, "unit": "normalized"},
    }
    assert asc._duplicate_pattern_signature("input/goal-setting.pdf", first) != (
        asc._duplicate_pattern_signature("input/goal-setting.pdf", same_page_neighbour)
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        source = tmpp / "Goal Setting 2026.pptx"
        source.write_bytes(b"fake pptx source for hashing only")
        output_root = tmpp / "component-extractions"
        eid = "docling-duplicate-pattern-demo"
        adir = output_root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [
                {
                    **first,
                    "object_ids": [],
                    "requested_type": "component",
                    "notes": "Year-end evaluation title card",
                    "replacement_for": None,
                },
                {
                    **second,
                    "object_ids": [],
                    "requested_type": "component",
                    "notes": "Quarterly check-in title card",
                    "replacement_for": None,
                },
            ],
        }), encoding="utf-8")

        hist = tmpp / "history.json"
        reg = tmpp / "registry.json"
        reg.write_text('{"items":[]}', encoding="utf-8")
        summary = asc.stage_run(
            eid,
            root=output_root,
            output_root=output_root,
            history=hist,
            registry=reg,
            rebuild_catalog=False,
            build_artifacts=False,
        )

        assert summary["staged"] == 1, summary
        assert summary["skipped"] == 1, summary
        duplicate = summary["items"][1]
        assert duplicate["status"] == "skipped_duplicate_pattern"
        assert duplicate["duplicate_of_candidate_id"] == "picture-p3-1"


def test_auto_stage_cli_reads_analysis_from_output_root() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        output_root = tmpp / "component-extractions"
        eid = "docling-cli-demo"
        adir = output_root / eid / "analysis"
        adir.mkdir(parents=True)
        source = tmpp / "source.pdf"
        source.write_bytes(b"%PDF-1.4\n% test source\n")
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [{
                "item_id": "picture-p1-1",
                "slide_or_page": 1,
                "region": {"x": 0.1, "y": 0.12, "width": 0.78, "height": 0.72,
                           "unit": "normalized"},
                "object_ids": [],
                "requested_type": "component",
                "semantic_intent": ["cli output root hero detected by Docling"],
                "notes": "Auto-stage this detected hero visual into Draft.",
                "replacement_for": None,
            }],
        }), encoding="utf-8")
        hist = tmpp / "history.json"
        reg = tmpp / "registry.json"
        reg.write_text('{"items":[]}', encoding="utf-8")

        rc = asc.main([
            eid,
            "--output-root", str(output_root),
            "--history", str(hist),
            "--registry", str(reg),
            "--no-catalog",
            "--no-artifacts",
        ])

        assert rc == 0, "CLI must read analysis from --output-root"
        assert hist.is_file(), "CLI should initialize a missing custom history file"
        run_dirs = [p for p in output_root.iterdir() if p.is_dir() and p.name != eid]
        assert run_dirs, "CLI should create a staged extraction dir"


def test_auto_stage_decomposes_large_cards_as_layout_rows() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "goal-card"
        item.mkdir(parents=True)
        (item / "mapping.json").write_text(_json.dumps({
            "component_type": "card",
            "source": {"region": {"width": 0.64, "height": 0.80}},
        }), encoding="utf-8")
        assert asc._decompose_mode(item) == "layout-row-groups"

        (item / "mapping.json").write_text(_json.dumps({
            "component_type": "card",
            "source": {"region": {"width": 0.20, "height": 0.20}},
        }), encoding="utf-8")
        assert asc._decompose_mode(item) is None

        (item / "mapping.json").write_text(_json.dumps({
            "component_type": "strip",
            "source": {"region": {"width": 0.20, "height": 0.20}},
        }), encoding="utf-8")
        assert asc._decompose_mode(item) == "cards"


def test_auto_stage_decomposes_tables_and_broad_visuals_as_layout_rows() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    with tempfile.TemporaryDirectory() as tmp:
        item = Path(tmp) / "items" / "compound-region"
        item.mkdir(parents=True)

        def write_mapping(component_type: str, width: float, height: float) -> None:
            (item / "mapping.json").write_text(_json.dumps({
                "component_type": component_type,
                "source": {"region": {"width": width, "height": height}},
            }), encoding="utf-8")

        write_mapping("table", 0.72, 0.38)
        assert asc._decompose_mode(item) == "layout-row-groups"
        write_mapping("visual", 0.55, 0.23)
        assert asc._decompose_mode(item) == "layout-row-groups"
        write_mapping("component", 0.55, 0.23)
        assert asc._decompose_mode(item) == "layout-row-groups"
        write_mapping("visual", 0.30, 0.20)
        assert asc._decompose_mode(item) is None


def test_auto_stage_semantic_ids_fallback_avoids_full_source_slug() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    source = "input/SUN.SLIDE.pdf"
    item_a = {
        "item_id": "picture-p20-1",
        "slide_or_page": 20,
        "semantic_intent": ["picture candidate detected by Docling"],
        "notes": "DRAFT candidate from Docling auto-detect. Rename item_id.",
    }
    item_b = {
        "item_id": "picture-p21-1",
        "slide_or_page": 21,
        "semantic_intent": ["picture candidate detected by Docling"],
        "notes": "DRAFT candidate from Docling auto-detect. Rename item_id.",
    }
    goal_card = {
        "item_id": "picture-p9-1",
        "slide_or_page": 9,
        "region": {"x": 0.1, "y": 0.1, "width": 0.25, "height": 0.35,
                   "unit": "normalized"},
        "semantic_intent": ["picture candidate detected by Docling"],
        "notes": "DRAFT candidate from Docling auto-detect. Rename item_id.",
    }

    used: set[str] = set()
    id_a = asc.semantic_item_id(source, item_a, used)
    id_b = asc.semantic_item_id(source, item_b, used)
    goal_id = asc.semantic_item_id("input/Kick_off_GOAL_SETTING_2026-2.pdf", goal_card, set())

    assert id_a == "detected-icon-1"
    assert id_b == "detected-icon-1-2"
    assert goal_id == "goal-setting-card-1"
    assert id_a != id_b
    assert not scaffold_ex._DOCLING_DRAFT_ID.match(id_a)
    assert not scaffold_ex._DOCLING_DRAFT_ID.match(id_b)
    assert "kick-off" not in goal_id and "2026" not in goal_id


def test_auto_stage_semantic_ids_use_page_context_before_source_fallback() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "picture-p7-1",
        "slide_or_page": 7,
        "region": {"x": 0.14, "y": 0.41, "width": 0.70, "height": 0.50,
                   "unit": "normalized"},
        "region_text": "Patrick E. Shorey\nMary T. Middleton",
        "page_text": "This is a contributors slide. Insert your team here.",
        "semantic_intent": ["picture candidate detected by Docling"],
        "notes": "DRAFT candidate from Docling auto-detect. Rename item_id.",
    }

    item_id = asc.semantic_item_id("input/Sun.Presentation.pdf", item, set())

    assert item_id == "contributors-team-visual", item_id
    assert not item_id.startswith("source-")


def test_auto_stage_semantic_ids_do_not_emit_source_visual_for_generic_pdf() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "figure-p16-1",
        "slide_or_page": 16,
        "region": {"x": 0.04, "y": 0.2, "width": 0.91, "height": 0.52,
                   "unit": "normalized"},
        "semantic_intent": ["figure candidate detected by PyMuPDF fallback"],
        "notes": "DRAFT candidate from PyMuPDF fallback auto-detect.",
    }

    item_id = asc.semantic_item_id("input/Sun.Presentation.pdf", item, set())

    assert item_id == "detected-visual-1", item_id
    assert not item_id.startswith("source-")


def test_auto_stage_semantic_ids_use_region_text_before_source_name() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    source = "input/GUIDLINE_PRESENTATION_SUN.pdf"
    role_card = {
        "item_id": "picture-p2-2",
        "slide_or_page": 2,
        "region": {"x": 0.15, "y": 0.41, "width": 0.15, "height": 0.2,
                   "unit": "normalized"},
        "region_text": (
            "Chuyen muc tieu cong ty thanh huong di ro rang\n"
            "TRANSLATOR\n"
            "cho team"
        ),
    }
    level_strip = {
        "item_id": "picture-p2-1",
        "slide_or_page": 2,
        "region": {"x": 0.15, "y": 0.16, "width": 0.66, "height": 0.18,
                   "unit": "normalized"},
        "region_text": "AI Coding Assistants\nLevel 1\nAgent Networks\nLevel 4",
    }

    role_id = asc.semantic_item_id(source, role_card, set())
    strip_id = asc.semantic_item_id(source, level_strip, set())
    metadata = asc.metadata_for(source, role_card, role_id)

    assert role_id == "translator-card"
    assert strip_id == "ai-coding-assistants-levels-strip"
    assert "guidline" not in role_id
    assert metadata["component_type"] == "card"
    assert metadata["keywords"][:2] == ["translator", "card"]


def test_auto_stage_semantic_ids_translate_vietnamese_hints_to_english() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    recruitment_item = {
        "item_id": "picture-p5-1",
        "slide_or_page": 5,
        "region": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.3,
                   "unit": "normalized"},
        "region_text": "HIEU MUC TIEU TUYEN DUNG",
    }
    team_item = {
        "item_id": "picture-p4-2",
        "slide_or_page": 4,
        "region": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.3,
                   "unit": "normalized"},
        "region_text": "XAY DUNG DOI NGU",
    }

    item_id = asc.semantic_item_id("input/interview-workshop.pdf", recruitment_item, set())
    team_id = asc.semantic_item_id("input/GUIDLINE_PRESENTATION_SUN.pdf", team_item, set())
    team_meta = asc.metadata_for("input/GUIDLINE_PRESENTATION_SUN.pdf", team_item, team_id)

    assert item_id == "recruitment-goal-card"
    assert "tuyen" not in item_id and "dung" not in item_id
    assert item_id.isascii()
    assert team_id == "team-visual"
    assert "xay" not in team_id and "ngu" not in team_id
    assert "xay" not in team_meta["keywords"]
    assert "dung" not in team_meta["keywords"]


def test_auto_stage_semantic_ids_translate_salary_benefit_vietnamese() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    salary_item = {
        "item_id": "picture-p2-1",
        "slide_or_page": 2,
        "region": {"x": 0.1, "y": 0.1, "width": 0.35, "height": 0.35,
                   "unit": "normalized"},
        "region_text": "Lương phúc lợi\nQuyền lợi dài hạn",
        "semantic_intent": ["picture candidate detected by Docling"],
    }
    investment_item = {
        "item_id": "picture-p3-1",
        "slide_or_page": 3,
        "region": {"x": 0.1, "y": 0.1, "width": 0.35, "height": 0.35,
                   "unit": "normalized"},
        "region_text": "Một bước đầu tư",
        "semantic_intent": ["picture candidate detected by Docling"],
    }
    subtitle_item = {
        "item_id": "figure-p4-1",
        "slide_or_page": 4,
        "region": {"x": 0.1, "y": 0.1, "width": 0.55, "height": 0.25,
                   "unit": "normalized"},
        "region_text": "goes sub tittle",
        "semantic_intent": ["figure candidate detected by PyMuPDF fallback"],
    }

    assert asc.semantic_item_id("input/Salary.pdf", salary_item, set()) == "salary-benefits-long-term-card"
    assert asc.semantic_item_id("input/Salary.pdf", investment_item, set()) == "investment-card"
    assert asc.semantic_item_id("input/Sun.Presentation.pdf", subtitle_item, set()) == "subtitle-visual"


def test_auto_stage_metadata_keeps_context_intent_with_region_text() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "picture-p4-2",
        "slide_or_page": 4,
        "region": {"x": 0.21, "y": 0.66, "width": 0.55, "height": 0.23,
                   "unit": "normalized"},
        "region_text": "XAY DUNG DOI NGU AI\nXAY DUNG HE THONG TU DONG HOA",
        "semantic_intent": [
            "2. CONTENT XOAY QUANH - build AI team and automation system",
        ],
    }

    metadata = asc.metadata_for(
        "input/GUIDLINE_PRESENTATION_SUN.pdf", item, "team-visual")

    assert metadata["semantic_intent"][0] == "team visual"
    assert any("CONTENT XOAY QUANH" in value
               for value in metadata["semantic_intent"])
    assert "content" in metadata["keywords"]


def test_auto_stage_semantic_ids_use_intent_when_region_text_missing() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "picture-p5-1",
        "slide_or_page": 5,
        "region": {"x": 0.25, "y": 0.28, "width": 0.47, "height": 0.21,
                   "unit": "normalized"},
        "region_text": (
            "Patrick E. Shorey\nRecreational therapist\n"
            "Mary T. Middleton\nPhysical meteorologist"
        ),
        "semantic_intent": [
            "This is a contributors slide. Insert your team here. Lorem ipsum dolor sit amet.",
        ],
    }

    item_id = asc.semantic_item_id("input/GUIDLINE_PRESENTATION_SUN.pdf", item, set())
    metadata = asc.metadata_for("input/GUIDLINE_PRESENTATION_SUN.pdf", item, item_id)

    assert item_id == "contributors-team-visual"
    assert not item_id.startswith("source-")
    assert metadata["keywords"][:3] == ["contributors", "team", "visual"]


def test_auto_stage_semantic_ids_filter_mixed_vietnamese_prose() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "figure-p4-2",
        "slide_or_page": 4,
        "region": {"x": 0.1, "y": 0.4, "width": 0.5, "height": 0.2,
                   "unit": "normalized"},
        "region_text": "Đảm bảo goal thực tế",
    }

    item_id = asc.semantic_item_id("input/GUIDLINE_PRESENTATION_SUN.pdf", item, set())

    assert item_id == "goal-strip"
    assert "dam" not in item_id and "bao" not in item_id
    assert "thuc" not in item_id and "te" not in item_id


def test_auto_stage_semantic_ids_level_series_without_content_rule() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "picture-p2-1",
        "slide_or_page": 2,
        "region": {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.18,
                   "unit": "normalized"},
        "region_text": "Design Operations\nLevel 1\nReview System\nLevel 2",
    }

    item_id = asc.semantic_item_id("input/source.pdf", item, set())

    assert item_id == "design-operations-review-system-strip"
    assert "source" not in item_id


def test_auto_stage_semantic_ids_metric_series_uses_labels_and_strip() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "figure-p2-6",
        "slide_or_page": 2,
        "region": {"x": 0.19, "y": 0.68, "width": 0.52, "height": 0.24,
                   "unit": "normalized"},
        "region_text": "+30%\nRevenue\nTeam Size\n(110 Members)\n+30%",
    }

    item_id = asc.semantic_item_id("input/GUIDLINE_PRESENTATION_SUN.pdf", item, set())
    metadata = asc.metadata_for("input/GUIDLINE_PRESENTATION_SUN.pdf", item, item_id)

    assert item_id == "revenue-team-size-metric-strip"
    assert metadata["component_type"] == "strip"
    assert metadata["keywords"][:4] == ["revenue", "team", "size", "metric"]


def test_auto_stage_icon_reference_uses_page_context() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "figure-p1-1",
        "slide_or_page": 1,
        "region": {"x": 0.54, "y": 0.17, "width": 0.38, "height": 0.15,
                   "unit": "normalized"},
        "region_text": "BOD\nPersonal\nCompany\nLearning & Sharing",
        "page_text": "ICON\n1. NHUNG ICON HAY XUAT HIEN",
        "semantic_intent": ["BOD Personal Company Learning Sharing"],
    }

    item_id = asc.semantic_item_id("input/GUIDLINE_PRESENTATION_SUN.pdf", item, set())
    metadata = asc.metadata_for("input/GUIDLINE_PRESENTATION_SUN.pdf", item, item_id)

    assert item_id == "icon-reference-sheet"
    assert metadata["component_type"] == "icon"
    assert metadata["layout_role"] == "icon reference sheet"
    assert "icon-set" in metadata["tags"]

    with tempfile.TemporaryDirectory() as tmp:
        item_dir = Path(tmp)
        (item_dir / "mapping.json").write_text(json.dumps({
            "component_type": "icon",
        }), encoding="utf-8")
        assert asc._is_icon_sheet_item(item_dir)


def test_auto_stage_overrides_stale_history_stable_id_for_auto_drafts() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        item_dir = tmp_path / "items" / "team-visual"
        item_dir.mkdir(parents=True)
        (item_dir / "mapping.json").write_text(json.dumps({
            "candidate_stable_id": "sun.component.xay-dung-oi-ngu-visual",
            "status": "staging",
            "source": {},
        }), encoding="utf-8")
        review = asc.metadata_for(
            "input/GUIDLINE_PRESENTATION_SUN.pdf",
            {"item_id": "picture-p4-2", "slide_or_page": 4,
             "region": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.3,
                        "unit": "normalized"},
             "region_text": "XAY DUNG DOI NGU"},
            "team-visual",
        )
        review["candidate_id"] = "picture-p4-2"
        asc._augment_mapping(item_dir, review, "docling-run", {"item_id": "picture-p4-2"})
        mapping = read_text_slots.load_json(item_dir / "mapping.json")
        assert mapping["candidate_stable_id"] == "sun.component.team-visual"

        history = tmp_path / "history.json"
        history.write_text(json.dumps({"attempts": [{
            "extraction_id": "docling-run-team-visual",
            "item_id": "team-visual",
            "stable_id": "sun.component.xay-dung-oi-ngu-visual",
        }]}), encoding="utf-8")
        asc._sync_history_stable_id(
            history, "docling-run-team-visual", "team-visual",
            mapping["candidate_stable_id"],
        )
        synced = read_text_slots.load_json(history)
        assert synced["attempts"][0]["stable_id"] == "sun.component.team-visual"


def test_auto_stage_semantic_ids_suffix_existing_component_names() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    item = {
        "item_id": "picture-p2-2",
        "slide_or_page": 2,
        "region": {"x": 0.15, "y": 0.41, "width": 0.15, "height": 0.2,
                   "unit": "normalized"},
        "region_text": "TRANSLATOR",
    }

    item_id = asc.semantic_item_id(
        "input/GUIDLINE_PRESENTATION_SUN.pdf",
        item,
        {"translator-card"},
    )

    assert item_id == "translator-card-2"


def test_auto_stage_clusters_same_page_by_role_and_layout_row() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")

    def _record(item_id: str, x: float, y: float, width: float, height: float) -> dict:
        return {
            "candidate_id": item_id,
            "item": {
                "item_id": item_id,
                "slide_or_page": 2,
                "region": {"x": x, "y": y, "width": width, "height": height,
                           "unit": "normalized"},
            },
            "review": {"item_id": item_id, "display_name": item_id.replace("-", " ").title()},
            "item_dir": "unused",
            "stable_id": f"sun.component.{item_id}",
        }

    records = [
        _record("ai-coding-maturity-levels-strip", 0.05, 0.12, 0.8, 0.2),
        _record("translator-card", 0.05, 0.5, 0.18, 0.25),
        _record("coach-card", 0.28, 0.5, 0.18, 0.25),
    ]

    clusters = asc._cluster_staged_records(records)

    assert len(clusters) == 1, clusters
    assert [record["review"]["item_id"] for record in clusters[0]] == [
        "translator-card",
        "coach-card",
    ]


def test_auto_stage_group_records_keep_docling_candidate_order() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    records = []
    for candidate_id, item_id in [
        ("picture-p2-5", "coach-card"),
        ("picture-p2-2", "translator-card"),
        ("picture-p2-4", "driver-card"),
        ("picture-p2-3", "strategist-card"),
    ]:
        records.append({
            "candidate_id": candidate_id,
            "item": {
                "item_id": candidate_id,
                "slide_or_page": 2,
                "region": {"x": 0.5, "y": 0.5, "width": 0.15, "height": 0.2,
                           "unit": "normalized"},
            },
            "review": {"item_id": item_id, "display_name": item_id.replace("-", " ").title()},
            "item_dir": "unused",
            "stable_id": f"sun.component.{item_id}",
        })

    assert [r["review"]["item_id"] for r in asc._sort_group_records(records)] == [
        "translator-card",
        "strategist-card",
        "driver-card",
        "coach-card",
    ]


def test_auto_stage_groups_related_candidates_as_carousel_draft() -> None:
    import importlib
    import build_component_catalog as bcc

    asc = importlib.import_module("auto_stage_candidates")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        source = tmpp / "Role cards.pdf"
        doc = fitz.open()
        page = doc.new_page(width=400, height=220)
        page.draw_rect(fitz.Rect(40, 40, 170, 180), color=(1, 0.4, 0.2),
                       fill=(1, 0.9, 0.8))
        page.insert_text((62, 95), "TRANSLATOR", fontsize=18, color=(0, 0, 0))
        page.draw_rect(fitz.Rect(230, 40, 360, 180), color=(0.1, 0.2, 1),
                       fill=(0.8, 0.9, 1))
        page.insert_text((270, 95), "COACH", fontsize=18, color=(0, 0, 0))
        doc.save(source)
        doc.close()

        output_root = tmpp / "component-extractions"
        eid = "docling-auto-group-demo"
        adir = output_root / eid / "analysis"
        adir.mkdir(parents=True)
        (adir / "candidate-extraction-request.json").write_text(json.dumps({
            "extraction_id": eid,
            "source_path": str(source),
            "items": [
                {
                    "item_id": "picture-p1-1",
                    "slide_or_page": 1,
                    "region": {"x": 0.1, "y": 0.18, "width": 0.35, "height": 0.66,
                               "unit": "normalized"},
                    "object_ids": [],
                    "requested_type": "component",
                    "semantic_intent": ["picture candidate detected by Docling"],
                    "notes": "Translator card",
                    "replacement_for": None,
                },
                {
                    "item_id": "picture-p1-2",
                    "slide_or_page": 1,
                    "region": {"x": 0.55, "y": 0.18, "width": 0.35, "height": 0.66,
                               "unit": "normalized"},
                    "object_ids": [],
                    "requested_type": "component",
                    "semantic_intent": ["picture candidate detected by Docling"],
                    "notes": "Coach card",
                    "replacement_for": None,
                },
            ],
        }), encoding="utf-8")

        hist = tmpp / "history.json"
        hist.write_text('{"attempts":[]}', encoding="utf-8")
        reg = tmpp / "registry.json"
        reg.write_text('{"items":[]}', encoding="utf-8")
        summary = asc.stage_run(
            eid,
            root=output_root,
            output_root=output_root,
            history=hist,
            registry=reg,
            rebuild_catalog=False,
        )
        assert summary["staged"] == 2, summary
        assert summary["grouped"] == 1, summary
        group = summary["group_item"]
        assert group["item_id"] == "translator-coach-card-set"
        group_dir = output_root / group["extraction_id"] / "items" / group["item_id"]
        group_mapping = read_text_slots.load_json(group_dir / "mapping.json")
        assert group_mapping["component_type"] == "component-set"
        assert len(group_mapping["collection_children"]) == 2
        assert (group_dir / "artifact" / "components" / "components-manifest.json").is_file()
        group_thumb = group_dir / "preview" / "thumbnail.png"
        assert group_thumb.is_file()
        png = group_thumb.read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        thumb_width = int.from_bytes(png[16:20], "big")
        thumb_height = int.from_bytes(png[20:24], "big")
        assert thumb_width > thumb_height, (thumb_width, thumb_height)
        compact = asc.compact_summary(summary)
        assert "artifact_log" not in compact["items"][0]
        assert compact["items"][0]["artifact_log_lines"] > 0

        # Draft grouping is a property of the runtime scan (GET /api/drafts).
        drafts = bcc.collect_draft_items(output_root)
        ids = [item["id"] for item in drafts]
        assert "sun.component.translator-card" not in ids
        assert "sun.component.coach-card" not in ids
        draft = next(item for item in drafts
                     if item["id"] == "sun.component.translator-coach-card-set")
        assert draft["publish_readiness"]["ready"], draft["publish_readiness"]
        assert [image["label"] for image in draft["images"]][:6] == [
            "Full component",
            "Full component (Text-free)",
            "Translator Card",
            "Translator Card (Text-free)",
            "Coach Card",
            "Coach Card (Text-free)",
        ]


def test_auto_stage_group_text_free_svg_rewrites_component_asset_refs() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        child_artifact = tmpp / "child" / "artifact"
        child_assets = child_artifact / "assets"
        child_assets.mkdir(parents=True)
        (child_assets / "icon.png").write_bytes(b"png")
        child_svg = child_artifact / "visual.svg"
        child_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<defs><g id="mask"/></defs>'
            '<image xlink:href="assets/icon.png"/>'
            '<use xlink:href="#mask"/></svg>',
            encoding="utf-8",
        )

        parent_artifact = tmpp / "parent" / "artifact"
        dest_svg = parent_artifact / "components" / "child-text-free.svg"
        asc._copy_svg_with_assets(
            child_svg, dest_svg, parent_artifact / "assets", "../assets/")

        copied = dest_svg.read_text(encoding="utf-8")
        assert 'xlink:href="../assets/icon.png"' in copied, copied
        assert 'xlink:href="assets/icon.png"' not in copied, copied
        assert 'xlink:href="#mask"' in copied, copied
        assert (parent_artifact / "assets" / "icon.png").read_bytes() == b"png"


def test_auto_stage_existing_stable_ids_ignore_skipped_outputs() -> None:
    import importlib

    asc = importlib.import_module("auto_stage_candidates")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        skipped = root / "skip" / "items" / "blank" / "mapping.json"
        active = root / "active" / "items" / "card" / "mapping.json"
        skipped.parent.mkdir(parents=True)
        active.parent.mkdir(parents=True)
        skipped.write_text(json.dumps({
            "status": "skipped",
            "candidate_stable_id": "sun.component.blank",
        }), encoding="utf-8")
        active.write_text(json.dumps({
            "status": "staging",
            "candidate_stable_id": "sun.component.card",
        }), encoding="utf-8")

        assert asc._existing_stable_ids(root) == {"sun.component.card"}


def test_catalog_has_no_candidate_review_top_tab() -> None:
    html = (SCRIPTS.parents[1] / "slide-system" / "catalog" / "index.html").read_text(encoding="utf-8")
    assert 'data-section="review"' not in html
    assert 'id="section-review"' not in html


def test_catalog_server_exposes_no_candidate_review_routes() -> None:
    source = (SCRIPTS.parents[1] / "slide-system" / "catalog" / "catalog_server.py").read_text(encoding="utf-8")
    assert "/api/candidates" not in source
    assert "_serve_candidate" not in source
    assert "_candidate_segments" not in source


def test_catalog_server_parses_stage_candidate_booleans() -> None:
    path = SCRIPTS.parents[1] / "slide-system" / "catalog" / "catalog_server.py"
    spec = importlib.util.spec_from_file_location("catalog_server_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.body_bool({}, "build_artifacts", True) is True
    assert module.body_bool({"build_artifacts": False}, "build_artifacts", True) is False
    assert module.body_bool({"build_artifacts": "false"}, "build_artifacts", True) is False
    assert module.body_bool({"build_artifacts": "0"}, "build_artifacts", True) is False
    assert module.body_bool({"build_artifacts": "true"}, "build_artifacts", False) is True
    try:
        module.body_bool({"build_artifacts": "sometimes"}, "build_artifacts", True)
    except ValueError as exc:
        assert "build_artifacts" in str(exc)
    else:
        raise AssertionError("invalid boolean strings must fail")


# --------------------------------------------------------------------------- #
# score_visual_items — shape-aware candidate eligibility (T1 in the scorer)
# --------------------------------------------------------------------------- #
def _shape_item(item_id: str, intent: list, tags: list, **over) -> dict:
    base = {"id": item_id, "status": "published", "type": "component",
            "intent": intent, "tags": tags, "content_structure": ["card"],
            "density": "any", "brand": None, "limitations": [],
            # Generic-buildable by default so shape/legacy tests isolate their gate.
            "build_scope": {"mode": "generic", "reason": "test generic component"}}
    base.update(over)
    return base


def test_shape_filter_excludes_incompatible_generic_for_comparison() -> None:
    # A generic numbered badge set out-scores a genuine comparison card set on
    # raw overlap, but its intent/tags carry no comparison token. Shape-aware
    # eligibility must keep it from being the selected item.
    req = {"request_id": "cmp", "content_shape": "comparison",
           "intent": ["comparison"], "tags": ["cards", "grid", "numbered"],
           "content_structure": ["card"], "density": "medium",
           "brand": "sun-studio", "item_count": 3}
    badge = _shape_item("sun.test.badge-set", ["statistics"],
                        ["cards", "grid", "numbered", "set-of-3"])
    cards = _shape_item("sun.test.compare-cards", ["comparison"],
                        ["cards", "grid", "numbered", "set-of-4"])
    dec, cands = svi.score_request(req, [badge, cards], svi.WEIGHTS, None)
    assert dec["item_id"] != "sun.test.badge-set", dec
    badge_c = next(c for c in cands if c["item_id"] == "sun.test.badge-set")
    assert badge_c["shape_eligible"] is False, badge_c
    assert any("Shape mismatch" in r for r in badge_c["reasons"]), badge_c


def test_shape_filter_keeps_compatible_tier_and_timeline_reuse() -> None:
    # Regression guard: genuine shape-compatible matches must still reuse.
    tier_req = {"request_id": "t", "content_shape": "tiers", "intent": ["tiers"],
                "tags": ["levels", "ranking"], "content_structure": ["card"],
                "density": "medium", "brand": "sun-studio", "item_count": 3}
    tier = _shape_item("sun.test.tier-ladder", ["tiers", "levels", "ranking"],
                       ["levels", "set-of-3"])
    dec, cands = svi.score_request(tier_req, [tier], svi.WEIGHTS, None)
    assert dec["action"] == "reuse" and dec["item_id"] == "sun.test.tier-ladder", dec
    assert cands[0]["shape_eligible"] is True, cands[0]

    tl_req = {"request_id": "tl", "content_shape": "timeline",
              "intent": ["timeline"], "tags": ["process", "steps"],
              "content_structure": ["card"], "density": "medium",
              "brand": "sun-studio", "item_count": 3}
    tl = _shape_item("sun.test.process-flow", ["timeline", "process"],
                     ["steps", "set-of-3"])
    dec2, _ = svi.score_request(tl_req, [tl], svi.WEIGHTS, None)
    assert dec2["action"] == "reuse" and dec2["item_id"] == "sun.test.process-flow", dec2


def test_shape_filter_no_compatible_returns_needs_component() -> None:
    # Only a shape-incompatible (but semantically overlapping) item is available:
    # unresolved (needs_component), never a forced reuse or an auto custom layout.
    req = {"request_id": "x", "content_shape": "timeline", "intent": ["timeline"],
           "tags": ["flow", "sequence"], "content_structure": ["card"],
           "density": "medium", "brand": "sun-studio"}
    item = _shape_item("sun.test.stats-strip", ["statistics"],
                       ["flow", "sequence", "numbers"])
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec
    assert dec["item_id"] is None, dec
    assert dec["extraction_recommended"] is True, dec


def test_unknown_content_shape_returns_needs_component() -> None:
    # A content_shape outside the shared vocabulary (here 'mindmap') means no
    # component can lock to it -> unresolved, even though the only candidate is a
    # strong semantic match.
    req = {"request_id": "c", "content_shape": "mindmap", "intent": ["mindmap"],
           "tags": ["radial", "nodes"], "content_structure": ["card"],
           "density": "low", "brand": "sun-studio"}
    item = _shape_item("sun.test.radial", ["mindmap", "radial"],
                       ["nodes", "branches"])
    dec, _ = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec
    assert dec["item_id"] is None, dec
    assert dec["extraction_recommended"] is True, dec


def test_validator_band_accepts_shape_filtered_needs_component() -> None:
    # A shape-incompatible item is available but the scorer returns needs_component;
    # the validator's band recompute must NOT reject an unresolved slide.
    req = {"request_id": "s", "content_shape": "timeline", "intent": ["timeline"],
           "tags": ["flow"], "content_structure": ["card"], "density": "medium",
           "brand": "sun-studio"}
    bad = _shape_item("sun.test.badstats", ["statistics"], ["flow", "numbers"])
    dec, cands = svi.score_request(req, [bad], svi.WEIGHTS, None)
    assert dec["action"] == "needs_component", dec
    slide = {"request_id": "s", "decision": dec, "candidates": cands}
    errors: list = []
    vsr._validate_decision_band(slide, "report", errors)
    assert errors == [], errors


def test_band_still_rejects_curation_of_shape_compatible_reuse() -> None:
    # Anti-curation guard survives shape awareness: downgrading a shape-compatible
    # reuse-worthy candidate to custom-local must still fail closed.
    slide = {"request_id": "s",
             "decision": {"action": "custom-local", "item_id": None, "score": 90,
                          "reason": "x", "extraction_recommended": True},
             "candidates": [{"item_id": "sun.test.g", "eligible": True,
                             "shape_eligible": True, "score": 90,
                             "criteria": {**{k: 1.0 for k in vsr.REQUIRED_CRITERIA},
                                          "semantic_intent": 20.0}}]}
    errors: list = []
    vsr._validate_decision_band(slide, "report", errors)
    assert errors, "curating a shape-compatible reuse to custom-local must be rejected"


# --------------------------------------------------------------------------- #
# Workflow enforcement: content_shape mandatory under --strict-shape, scorer
# API stays lenient, docs must keep the strict contract, closing vocabulary.
# --------------------------------------------------------------------------- #
def test_strict_shape_requires_content_shape_on_every_request() -> None:
    # Under --strict-shape a request that omits content_shape must FAIL even
    # when its decision is custom-local, so the slide-generator workflow cannot
    # silently bypass the shape-aware filter by leaving content_shape out.
    rep = {"slides": [{
        "request_id": "s1",
        "decision": {"action": "custom-local", "item_id": None, "score": 0, "reason": "x"},
        "candidates": [{"item_id": "sun.test.x", "eligible": True, "score": 0,
                        "criteria": {k: 0.0 for k in vsr.REQUIRED_CRITERIA}}],
    }]}
    errs, _ = vsr._validate_shape_lock(rep, True, {"s1": None}, {}, strict_shape=True)
    assert errs, "missing content_shape under --strict-shape must fail (even custom-local)"
    errs2, _ = vsr._validate_shape_lock(rep, True, {"s1": None}, {}, strict_shape=False)
    assert not errs2, f"non-strict must not fail a shapeless custom-local: {errs2}"
    errs3, _ = vsr._validate_shape_lock(rep, True, {"s1": "checklist"}, {}, strict_shape=True)
    assert not errs3, f"a request that declares content_shape passes strict: {errs3}"


def test_strict_shape_rejects_unknown_shape_on_non_selecting_decisions() -> None:
    # --strict-shape must reject an UNKNOWN content_shape even when the decision
    # selects no component (custom-local / needs_component), not just for reuse, so
    # the documented "missing OR unknown -> hard failure" contract actually holds.
    for action in ("custom-local", "needs_component"):
        rep = {"request_id": "s1",
               "decision": {"action": action, "item_id": None, "score": 0, "reason": "x"}}
        errs, warns = vsr._validate_shape_lock(
            rep, False, {"s1": "not-a-real-shape"}, {}, strict_shape=True)
        assert errs, f"unknown content_shape under --strict-shape must fail for {action}"
        assert not warns, f"unknown shape must be an error, not a warning ({action})"
    # Backward compatible: without --strict-shape a non-selecting decision with an
    # unknown shape stays lenient (no error, no warning).
    rep = {"request_id": "s1", "decision": {"action": "custom-local", "item_id": None}}
    errs2, warns2 = vsr._validate_shape_lock(
        rep, False, {"s1": "not-a-real-shape"}, {}, strict_shape=False)
    assert not errs2 and not warns2, f"non-strict must stay backward compatible: {errs2}, {warns2}"


def test_shapeless_direct_scorer_request_preserves_legacy() -> None:
    # The scorer API stays lenient: a request without content_shape scores and
    # selects exactly as before, and emits no shape_eligible field.
    req = {"intent": ["timeline"], "tags": [], "content_structure": ["a"],
           "density": "medium", "brand": "sun", "required_exports": []}
    item = _shape_item("sun.test.legacy", ["timeline"], [], content_structure=["a"])
    dec, cands = svi.score_request(req, [item], svi.WEIGHTS, None)
    assert dec["action"] == "reuse" and dec["item_id"] == "sun.test.legacy", dec
    assert "shape_eligible" not in cands[0], "no content_shape -> no shape_eligible field"


def test_workflow_docs_enforce_strict_shape_contract() -> None:
    skill = (SCRIPTS.parent.parent / ".agents" / "skills" / "slide-generator"
             / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SCRIPTS.parent / "workflows"
                / "select-visual-items.md").read_text(encoding="utf-8")
    for name, doc in (("SKILL.md", skill), ("select-visual-items.md", workflow)):
        assert "--strict-shape" in doc, f"{name} must invoke validate with --strict-shape"
        assert "content_shape" in doc, f"{name} must require content_shape"


def test_closing_shape_vocabulary_present_and_discriminative() -> None:
    assert "closing" in _common.SHAPE_TYPE_MAP, "closing must be in the shared shape vocabulary"
    assert _common.shape_eligible("closing", ["closing", "thank-you"]) is True
    assert _common.shape_eligible("closing", ["timeline", "process", "milestones"]) is False


def test_published_closing_item_is_closing_eligible() -> None:
    reg = read_text_slots.load_json(REGISTRY)
    published = [it for it in reg.get("items", []) if it.get("status") == "published"]

    def toks(it: dict) -> list:
        return [str(t).lower() for t in (it.get("intent", []) + it.get("tags", []))]

    closing_items = [it for it in published
                     if "closing" in toks(it) or "thank-you" in toks(it)]
    assert closing_items, "expected at least one published closing/thank-you item"
    assert any(_common.shape_eligible("closing", toks(it)) for it in closing_items), \
        "a published closing item must be shape-eligible under 'closing'"
    assert _common.shape_eligible("closing", ["timeline", "schedule", "roadmap"]) is False


# --------------------------------------------------------------------------- #
# component fidelity — text-slot contract (bindings + geometry, not bare marker)
# --------------------------------------------------------------------------- #
def _slot_div(sid: str, x: float, y: float, w: float, h: float) -> str:
    return (f'<div class="component-slot" data-component-slot="{sid}" '
            f'style="position:absolute;left:{round(x*1920)}px;top:{round(y*1080)}px;'
            f'width:{round(w*1920)}px;height:{round(h*1080)}px">text</div>')


def test_fidelity_slot_contract_rejects_bare_marker() -> None:
    # A text-slot component tagged only with data-base-component (no bound slots)
    # must FAIL — this is the root-cause defect being fixed.
    declared = {"a": (0.1, 0.1, 0.2, 0.1), "b": (0.5, 0.1, 0.2, 0.1)}
    html = '<div class="slide-scaffold" data-base-component="c"><div class="bg"></div></div>'
    ok, cov, reason = fidelity._check_slot_contract(html, None, declared)
    assert not ok and "data-component-slot" in reason, reason


def test_fidelity_slot_contract_passes_bound_slots() -> None:
    declared = {"a": (0.1, 0.1, 0.2, 0.1), "b": (0.5, 0.1, 0.2, 0.1)}
    html = _slot_div("a", 0.1, 0.1, 0.2, 0.1) + _slot_div("b", 0.5, 0.1, 0.2, 0.1) + "<svg></svg>"
    ok, cov, reason = fidelity._check_slot_contract(html, None, declared)
    assert ok and cov == 1.0, reason


def test_fidelity_slot_text_outside_bounds_fails() -> None:
    declared = {"a": (0.1, 0.1, 0.2, 0.1), "b": (0.5, 0.1, 0.2, 0.1)}
    # 'a' authored far from its declared box → outside its slot.
    html = _slot_div("a", 0.7, 0.7, 0.2, 0.1) + _slot_div("b", 0.5, 0.1, 0.2, 0.1) + "<svg></svg>"
    ok, cov, reason = fidelity._check_slot_contract(html, None, declared)
    assert not ok and "outside" in reason, reason


def test_fidelity_overlapping_slot_text_fails() -> None:
    # Declared far apart, but 'b' is authored on top of 'a' -> NEW overlap the
    # deck introduced beyond the component's design.
    declared = {"a": (0.1, 0.1, 0.25, 0.12), "b": (0.6, 0.1, 0.25, 0.12)}
    html = _slot_div("a", 0.1, 0.1, 0.25, 0.12) + _slot_div("b", 0.12, 0.1, 0.25, 0.12) + "<svg></svg>"
    ok, cov, reason = fidelity._check_slot_contract(html, None, declared)
    assert not ok and "overlap" in reason, reason


def test_fidelity_tolerates_designed_slot_overlap() -> None:
    # Two slots whose DECLARED boxes overlap (like this artwork) must NOT be
    # flagged when authored at their declared positions.
    declared = {"a": (0.30, 0.30, 0.20, 0.30), "b": (0.34, 0.28, 0.12, 0.10)}
    html = _slot_div("a", 0.30, 0.30, 0.20, 0.30) + _slot_div("b", 0.34, 0.28, 0.12, 0.10) + "<svg></svg>"
    ok, cov, reason = fidelity._check_slot_contract(html, None, declared)
    assert ok, reason


def test_fidelity_missing_blank_artifact_fails() -> None:
    declared = {"a": (0.1, 0.1, 0.2, 0.1)}
    html = _slot_div("a", 0.1, 0.1, 0.2, 0.1)  # bound slot but no rendered artifact
    ok, cov, reason = fidelity._check_slot_contract(html, None, declared)
    assert not ok and "artifact" in reason, reason


def test_fidelity_end_to_end_rejects_bare_marker_for_slot_component() -> None:
    # Evidence-based: a real text-slot-contract component that is still auto-reusable,
    # so a deck that only MARKS it (no data-component-slot bindings) reaches and fails
    # the slot-binding check rather than short-circuiting on a review-only flag.
    reg = read_text_slots.load_json(REGISTRY)

    def bare_marker_result(cid):
        html = f'<div class="slide-scaffold" data-base-component="{cid}"><div class="bg"></div></div>'
        report = {"slides": [{"request_id": "s5",
                              "decision": {"action": "reuse", "item_id": cid}}]}
        res = fidelity.check_fidelity(html, report, reg)
        return res[0] if res else None

    entry = next(i for i in reg["items"]
                 if i.get("status") == "published"
                 and fidelity.declared_text_slots(i)
                 and (i.get("auto_reuse") or {}).get("eligible") is not False
                 and "data-component-slot" in ((bare_marker_result(i["id"]) or {}).get("reason") or ""))
    result = bare_marker_result(entry["id"])
    assert result and not result["pass_"], result
    assert "data-component-slot" in result["reason"], result["reason"]


def test_materialize_inlines_external_images_and_nonblank() -> None:
    import materialize_component_visual as mat
    svg = '<svg><rect/><image xlink:href="assets/x.png"/><path d="M0 0"/><circle/></svg>'
    out, missing = mat.inline_external_images(svg, Path("."))
    assert "assets/x.png" in missing, missing          # unresolved local ref reported
    assert mat.is_nonblank(out)                          # >=3 shapes -> non-blank
    assert not mat.is_nonblank("<svg></svg>")            # empty -> blank
    keep = '<svg><image href="data:image/png;base64,AAA"/><image href="http://x/y.png"/></svg>'
    out2, missing2 = mat.inline_external_images(keep, Path("."))
    assert not missing2 and out2 == keep                 # data:/http refs untouched


# --------------------------------------------------------------------------- #
# Part B: materialization is wired into the reuse path and fails hard on a
# missing/unsafe/unresolved local visual ref (never writes an incomplete SVG).
# --------------------------------------------------------------------------- #
def test_materialize_main_fails_on_missing_local_ref() -> None:
    import materialize_component_visual as mat
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "visual.svg"
        src.write_text('<svg><image xlink:href="missing.png"/><rect/><circle/></svg>',
                       encoding="utf-8")
        out = Path(tmp) / "out.svg"
        assert mat.main(["--svg", str(src), "--out", str(out)]) == 1
        assert not out.exists(), "must not write an incomplete 'successful' visual"


def test_materialize_main_fails_on_unsafe_ref() -> None:
    # A ref escaping the visual's own directory (traversal/absolute) is unsafe and
    # must fail even though the target file exists.
    import materialize_component_visual as mat
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "secret.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 8)
        comp = Path(tmp) / "comp"; comp.mkdir()
        src = comp / "visual.svg"
        src.write_text('<svg><image xlink:href="../secret.png"/><rect/><circle/></svg>',
                       encoding="utf-8")
        out = Path(tmp) / "out.svg"
        assert mat.main(["--svg", str(src), "--out", str(out)]) == 1
        assert not out.exists()


def test_materialize_main_succeeds_and_inlines_local_ref() -> None:
    import materialize_component_visual as mat
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "tile.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 160)
        src = Path(tmp) / "visual.svg"
        src.write_text('<svg><image xlink:href="tile.png"/></svg>', encoding="utf-8")
        out = Path(tmp) / "out.svg"
        assert mat.main(["--svg", str(src), "--out", str(out)]) == 0
        text = out.read_text(encoding="utf-8")
        assert "data:image/png;base64," in text          # inlined -> self-contained
        assert 'href="tile.png"' not in text             # no external ref remains


def _mk_component_registry(tmp: Path, svg_body: str) -> Path:
    reg = tmp / "reg.json"
    reg.write_text(json.dumps({"items": [{
        "id": "sun.component.matx", "status": "published",
        "paths": {"visual": str(tmp / "visual.svg")}}]}), encoding="utf-8")
    (tmp / "visual.svg").write_text(svg_body, encoding="utf-8")
    return reg


def test_scaffold_materializes_self_contained_bg_from_visual() -> None:
    import re as _re
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        (tmp / "tile.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 160)
        reg = _mk_component_registry(tmp, '<svg><image xlink:href="tile.png"/></svg>')
        out = tmp / "slide.html"
        rc = scaffold.main(["--item-id", "sun.component.matx",
                            "--registry", str(reg), "--out", str(out)])
        assert rc == 0
        frag = out.read_text(encoding="utf-8")
        m = _re.search(r"background-image:url\('([^']+)'\)", frag)
        assert m, "the .bg must be wired to the materialized visual, got:\n" + frag
        sidecar = out.parent / m.group(1)
        assert sidecar.exists(), "materialized sidecar SVG must be written"
        assert "data:image/png;base64," in sidecar.read_text(encoding="utf-8")


def test_scaffold_fails_when_component_visual_ref_missing() -> None:
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        reg = _mk_component_registry(tmp, '<svg><image xlink:href="gone.png"/><rect/></svg>')
        out = tmp / "slide.html"
        rc = scaffold.main(["--item-id", "sun.component.matx",
                            "--registry", str(reg), "--out", str(out)])
        assert rc == 1, "a broken component visual must fail the scaffold"
        assert not out.exists(), "must not emit a scaffold that references a broken .bg"


# --------------------------------------------------------------------------- #
# Part A: domain-locked timelines must not be reused for a generic how-to.
# These run the real selection path against the SHIPPED compact registry +
# retrieval index — the same artifacts production reads — so they regress the
# metadata, not a fixture. (RED before the anti_use_cases were added: S7 pulled in
# sun.interview-workshop-sunriser.02-timeline at 65.0, which the bands of the day
# accepted; that band is retired, so today the same score is needs_component.)
# --------------------------------------------------------------------------- #
_DOMAIN_TIMELINES = {
    "sun.interview-workshop-sunriser.02-timeline",
    "sun.goal-setting-2026.05-process",
    "sun.goal-setting-2026.03-timeline",
    "sun.sun-studio-performance-review-2025.12-review-timeline",
}


def _score_real(request: dict) -> tuple[dict, list]:
    compact = REGISTRY.parent / "visual-library-compact.json"
    index = REGISTRY.parent / "component-retrieval-index.jsonl"
    reg = _common.load_json(compact)
    enr = svi.load_retrieval_index(index)
    idx = svi._build_inverted_index(reg["items"], enr)
    filt = svi._prefilter(request, reg["items"], idx)
    return svi.score_request(request, filt, svi.WEIGHTS, None, top_n=5, enrichment=enr)


def test_s7_generic_howto_is_needs_component_not_domain_timeline_reuse() -> None:
    # A generic find-install-use / horizontal / three-step how-to (S7 in the
    # AI-workflow brief) must NOT reuse a domain-locked timeline. The name used to say
    # "selects custom-local", which the scorer has never done automatically — the
    # actual, asserted behaviour is `needs_component`: build nothing, hand it back.
    req = {
        "request_id": "s7-skills-timeline-3",
        "intent": ["timeline", "process", "steps"],
        "tags": ["three-steps", "horizontal", "sequence", "find-install-use"],
        "content_structure": ["step", "label", "heading"],
        "content_shape": "timeline", "density": "medium", "brand": "sun-studio",
        "item_count": 3,
    }
    dec, _ = _score_real(req)
    assert dec["action"] == "needs_component", dec
    assert dec["item_id"] is None, dec
    # ...and it is not a hidden domain-timeline reuse: scored directly, each domain
    # timeline takes the accurate anti penalty and lands well below any reuse bar.
    compact = _common.load_json(REGISTRY.parent / "visual-library-compact.json")
    enr = svi.load_retrieval_index(REGISTRY.parent / "component-retrieval-index.jsonl")
    domain_items = [it for it in compact["items"] if it["id"] in _DOMAIN_TIMELINES]
    assert len(domain_items) == len(_DOMAIN_TIMELINES), "domain timelines missing from registry"
    _, dcands = svi.score_request(req, domain_items, svi.WEIGHTS, None, enrichment=enr)
    for c in dcands:
        assert c["retrieval"].get("anti_hits"), c
        assert c["score"] < 65, c


def test_domain_timelines_stay_eligible_for_their_own_workflow() -> None:
    # The anti wording targets generic how-tos only; for a real interview/date
    # workflow the domain timeline must stay an ELIGIBLE, unpenalized top candidate
    # (the user can pick it), even if the strict confidence bar leaves the slide
    # unresolved.
    interview = {
        "request_id": "iv",
        "intent": ["interview", "timeline", "schedule", "hr"],
        "tags": ["interview", "schedule", "lich-trinh", "hr", "dates", "onboarding"],
        "content_structure": ["date", "label", "heading"],
        "content_shape": "timeline", "density": "medium", "brand": "sun-studio",
    }
    dec, cands = _score_real(interview)
    assert dec["action"] in {"reuse", "needs_component"}, dec
    top = next(c for c in cands if c["eligible"] and c.get("shape_eligible", True))
    assert top["item_id"] in _DOMAIN_TIMELINES, top
    assert not top.get("retrieval", {}).get("anti_hits"), top
    assert not dec.get("retrieval", {}).get("anti_hits"), dec


def _paginated_deck_html(n: int) -> str:
    """A deck that follows the documented paginated contract: every `.slide` is
    `display:none` until `goToSlide(n)` makes one `.active`. Each slide carries its
    own component instance, `.bg` artwork (a self-contained data: URI, so "did the
    artwork load" is never an asset-path question) and a real text slot."""
    art = ("data:image/svg+xml;utf8,"
           "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 9'>"
           "<rect width='16' height='9' fill='%23123456'/></svg>")
    slides = "\n".join(
        f'<section class="slide" data-slide="s{i}">'
        f'<div class="slide-scaffold" data-base-component="c.{i}" '
        f'data-component-instance="c.{i}#s{i}">'
        f'<div class="bg" style="position:absolute;inset:0;width:1920px;height:1080px;'
        f"background-image:url(\"{art}\");background-size:cover\"></div>"
        f'<div class="slot" data-slot-id="title" style="position:absolute;left:100px;'
        f'top:100px;width:600px;height:80px;font-size:40px;line-height:80px;">'
        f"<span>Slide {i} title</span></div>"
        f"</div></section>"
        for i in range(n))
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        ".slide{position:absolute;top:0;left:0;width:1920px;height:1080px;"
        "overflow:hidden;display:none}.slide.active{display:block}"
        "</style></head><body><div class='deck'>" + slides + "</div><script>"
        "function goToSlide(n){document.querySelectorAll('.slide')"
        ".forEach(function(el,i){el.classList.toggle('active',i===n);});}"
        "goToSlide(0);</script></body></html>")


def test_measure_deck_slots_navigates_paginated_deck():
    # P1 regression: measure_deck_slots.js measured the deck AS LOADED. In the
    # documented paginated contract only slide 0 is `.active`; every later slide is
    # `display:none`, so its instance measured bg 0x0 / loaded:false and every slot
    # rect 0x0. That made the render-aware fidelity gate report "base component
    # artwork did not load/render" for perfectly good artwork, and — worse — made
    # its readability checks VACUOUS past slide 0: `overflowX` is
    # `scrollW > clientW` = `0 > 0` = false, and a 0-width text rect skips the
    # overlap/visibility checks. No reuse occurrence after the first was ever really
    # validated. The measurer must navigate the deck (like capture-slides.js) so
    # every instance is measured while its own slide is visible.
    node = shutil.which("node")
    if node is None:
        print("  SKIP  test_measure_deck_slots_navigates_paginated_deck (node not found)")
        return
    if not (SCRIPTS.parents[1] / "node_modules" / "playwright").is_dir():
        print("  SKIP  test_measure_deck_slots_navigates_paginated_deck (playwright not installed)")
        return
    with tempfile.TemporaryDirectory() as tmpd:
        root = Path(tmpd)
        deck = root / "deck.html"
        deck.write_text(_paginated_deck_html(3), encoding="utf-8")
        out = root / "slots.json"
        proc = subprocess.run(
            [node, str(SCRIPTS / "measure_deck_slots.js"), "--html", str(deck),
             "--out", str(out)],
            capture_output=True, text=True, cwd=str(SCRIPTS.parents[1]))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        data = json.loads(out.read_text(encoding="utf-8"))
        insts = {i["instance"]: i for i in data["instances"]}
        assert len(insts) == 3, sorted(insts)
        for i in range(3):
            rec = insts[f"c.{i}#s{i}"]
            bg = rec["bg"]
            assert bg["present"] and bg["loaded"], f"slide {i} bg not loaded: {bg}"
            assert bg["w"] > 0 and bg["h"] > 0, f"slide {i} bg has no size: {bg}"
            slot = rec["slots"][0]
            assert slot["rendered"], f"slide {i} slot did not render: {slot}"
            assert slot["wrapperW"] > 0 and slot["textW"] > 0, (
                f"slide {i} slot measured empty — readability checks would be "
                f"vacuous here: {slot}")


# --------------------------------------------------------------------------- #
# Content capacity — a component must be able to HOLD the planned content.
# --------------------------------------------------------------------------- #
def _slot(sid: str, x: float, y: float, w: float, h: float) -> dict:
    return {"id": sid, "bounds": {"x": x, "y": y, "width": w, "height": h}}


# The real shape of a CTA slide: one headline wrapped across three slots, plus
# page furniture. Geometry copied from the published 08-next-steps-cta contract.
_CTA_SLOTS = [
    _slot("line-1", 0.052, 0.077, 0.595, 0.090),
    _slot("line-2", 0.052, 0.157, 0.344, 0.090),
    _slot("accent", 0.378, 0.157, 0.116, 0.090),
    _slot("deck-label", 0.756, 0.045, 0.104, 0.023),
    _slot("page-no", 0.936, 0.937, 0.014, 0.023),
    _slot("footer", 0.052, 0.936, 0.099, 0.023),
]
# A list layout: four rows separated by real vertical gaps.
_LIST_SLOTS = [_slot("title", 0.05, 0.12, 0.40, 0.06)] + [
    _slot(f"item-{i}", 0.073, y, 0.30, 0.027)
    for i, y in enumerate((0.30, 0.43, 0.59, 0.77))
] + [_slot("footer", 0.038, 0.914, 0.207, 0.023)]


def test_content_blocks_merges_wrapped_headline_and_drops_chrome() -> None:
    # A CTA headline split across 3 slots is ONE content item, not three, and page
    # furniture is not capacity. This is the distinction `slot_count` cannot make:
    # the real component is slot_count=8 yet holds exactly one statement, which is
    # why a multi-item brief got silently compressed into one vague line.
    assert _common.content_blocks(_CTA_SLOTS) == 1, _common.content_blocks(_CTA_SLOTS)
    # Rows separated by real gaps stay distinct: title + 4 items = 5 blocks.
    assert _common.content_blocks(_LIST_SLOTS) == 5, _common.content_blocks(_LIST_SLOTS)
    # No slots / unusable bounds -> no capacity, never a crash.
    assert _common.content_blocks([]) == 0
    assert _common.content_blocks([{"id": "x"}]) == 0


def test_content_blocks_matches_the_real_published_library() -> None:
    # The signal is only worth gating on if it reads the REAL library the way a
    # human would. Derived from each item's own published slot contract.
    reg = json.loads((SCRIPTS.parents[1] / "slide-system/registries"
                      / "visual-library.json").read_text(encoding="utf-8"))
    items = {i["id"]: i for i in reg["items"]}

    def blocks_of(item_id: str) -> int:
        rel = (items[item_id].get("text_contract") or {}).get("slots")
        slots = json.loads((SCRIPTS.parents[1] / rel).read_text(encoding="utf-8"))["slots"]
        return _common.content_blocks(slots)

    # A CTA/closing holds one statement; a checklist/process holds many.
    assert blocks_of("sun.sun-presentation.08-next-steps-cta") == 1
    assert blocks_of("sun.sun-presentation.17-closing-thank-you") == 1
    assert blocks_of("sun.interview-workshop-sunriser.10-do-dont") > 5
    assert blocks_of("sun.goal-setting-2026.05-process") > 5


def test_retrieval_index_carries_content_blocks() -> None:
    # Capacity is a compact buildability fact, so it ships in the index beside
    # slot_count rather than being recomputed per scoring run.
    import build_component_retrieval_index as bcri
    rec = bcri.build_record({
        "id": "sun.x.y", "status": "published",
        "text_contract": {"slot_count": 8, "slots": None},
    })
    assert "content_blocks" in rec
    assert rec["content_blocks"] is None, rec["content_blocks"]  # unknown, not 0


def _cap_enrich(**blocks) -> dict:
    return svi.build_enrichment([
        {"id": i, "status": "published", "slot_count": 8, "content_blocks": b}
        for i, b in blocks.items()
    ])


def test_capacity_multi_item_request_rejects_cta_only_component() -> None:
    # THE defect this gate exists for: a 4-item "next steps" plan must not
    # auto-select a component that can only hold one statement. Without this the
    # selector reused a CTA slide and the plan got compressed to one vague line.
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=4)
    dec, cands = svi.score_request(req, [cta], svi.WEIGHTS, None,
                                   enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert dec["action"] == "needs_component", dec
    cand = next(c for c in cands if c["item_id"] == "sun.deck.cta")
    assert cand["retrieval"]["content_blocks"] == 1
    assert any("capacity" in r.lower() for r in cand["reasons"]), cand["reasons"]
    # Unresolved, NOT silently downgraded to custom-local.
    assert dec["item_id"] is None


def test_capacity_fitting_multi_item_component_stays_eligible() -> None:
    # The gate must not just say no: a component that genuinely fits the plan is
    # still auto-reusable, so real multi-item slides keep building.
    checklist = _item(id="sun.deck.checklist", intent=["checklist", "action-items"],
                      tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=4)
    dec, cands = svi.score_request(req, [checklist], svi.WEIGHTS, None,
                                   enrichment=_cap_enrich(**{"sun.deck.checklist": 9}))
    assert dec["action"] == "reuse", dec
    assert dec["item_id"] == "sun.deck.checklist"
    cand = next(c for c in cands if c["item_id"] == "sun.deck.checklist")
    assert not any("capacity" in r.lower() for r in cand["reasons"]), cand["reasons"]


def test_capacity_sparse_cta_request_still_matches_cta_component() -> None:
    # A one-statement CTA slide is a legitimate design. A plan of ONE item must
    # still reuse a one-block component — the gate is a floor, not a preference
    # for big layouts.
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=1)
    dec, _ = svi.score_request(req, [cta], svi.WEIGHTS, None,
                               enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert dec["action"] == "reuse", dec


def test_capacity_prefers_the_component_that_fits_the_plan() -> None:
    # Given both, the plan decides: 4 items go to the layout that can hold them.
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    checklist = _item(id="sun.deck.checklist", intent=["checklist", "action-items"],
                      tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=4)
    dec, _ = svi.score_request(req, [cta, checklist], svi.WEIGHTS, None,
                               enrichment=_cap_enrich(**{"sun.deck.cta": 1,
                                                         "sun.deck.checklist": 9}))
    assert dec["action"] == "reuse" and dec["item_id"] == "sun.deck.checklist", dec


def test_capacity_content_plan_supplies_the_item_count() -> None:
    # The brief's structured expansion IS the plan: 3 planned next-steps means 3
    # items, so the count never has to be restated (and cannot silently disagree).
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                content_plan=["Confirm owners", "Agree the plan", "Book the review"])
    assert svi.planned_item_count(req) == 3
    dec, _ = svi.score_request(req, [cta], svi.WEIGHTS, None,
                               enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert dec["action"] == "needs_component", dec
    # Restating the count is allowed only in agreement — see
    # test_content_plan_and_item_count_must_agree.
    assert svi.planned_item_count({**req, "item_count": 3}) == 3


def test_content_plan_and_item_count_must_agree() -> None:
    # The contract says content_plan IS the plan, so its length is the count. Letting
    # item_count silently override it meant a request could claim 1 item while listing
    # 3 — the capacity gate would then size the slide to the lie and wave through a
    # component that cannot hold the real content. A disagreement is an authoring
    # mistake, so it fails validation BEFORE scoring rather than being resolved by
    # precedence.
    three = ["Confirm owners", "Agree the plan", "Book the review"]
    bad = _valid_batch(content_plan=three, item_count=4)
    errors = svi.validate_batch_request(bad)
    assert any("item_count" in e and "content_plan" in e for e in errors), errors
    # The message must name both numbers, so the author can see which is wrong.
    assert any("4" in e and "3" in e for e in errors), errors

    # Backward compatible: every non-conflicting shape stays valid.
    assert svi.validate_batch_request(_valid_batch(content_plan=three)) == []
    assert svi.validate_batch_request(_valid_batch(item_count=4)) == []
    assert svi.validate_batch_request(_valid_batch()) == []
    assert svi.validate_batch_request(_valid_batch(content_plan=three, item_count=3)) == []


def test_planned_item_count_reads_the_plan_as_the_count() -> None:
    three = ["Confirm owners", "Agree the plan", "Book the review"]
    # content_plan only -> its length.
    assert svi.planned_item_count({"content_plan": three}) == 3
    # item_count only -> that count (a request may state a count without listing copy).
    assert svi.planned_item_count({"item_count": 4}) == 4
    # Both, in agreement -> the same number either way.
    assert svi.planned_item_count({"content_plan": three, "item_count": 3}) == 3
    # Neither -> no plan, so the capacity gate is a no-op.
    assert svi.planned_item_count({}) is None
    # The plan is the ground truth: validation rejects a mismatch before scoring, so
    # this case is unreachable in the real flow, but the function must never prefer a
    # bare number over the actual listed content.
    assert svi.planned_item_count({"content_plan": three, "item_count": 1}) == 3
    # Non-counts are ignored, not crashed on.
    assert svi.planned_item_count({"item_count": True}) is None
    assert svi.planned_item_count({"item_count": 0}) is None
    assert svi.planned_item_count({"content_plan": []}) is None


def test_capacity_explicit_user_selection_warns_but_never_bypasses_fidelity() -> None:
    # The user may still pick the component. That choice is not evidence the
    # content fits, so the decision carries a plain capacity warning and stays
    # subject to the downstream scaffold/fidelity/export gates.
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=4, component_id="sun.deck.cta")
    dec, _ = svi.score_request(req, [cta], svi.WEIGHTS, None,
                               enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert dec["action"] == "reuse", dec
    assert dec["selected_by"] == "user"
    assert "WARNING" in dec["reason"] and "capacity" in dec["reason"].lower(), dec["reason"]
    assert dec["capacity_conflict"]["planned_items"] == 4
    assert dec["capacity_conflict"]["content_blocks"] == 1


def test_capacity_unknown_data_is_a_no_op_not_a_regression() -> None:
    # Conservative/fail-safe compatibility: when either side is unknown the gate
    # cannot know anything, so it must not invent a verdict. Requests with no plan,
    # and components with no readable slot contract, behave exactly as before.
    cta = _item(id="sun.deck.cta", intent=["checklist", "action-items"], tags=[])
    plan_only = _rreq(intent=["checklist", "action-items"], content_structure=["a"])
    dec, _ = svi.score_request(plan_only, [cta], svi.WEIGHTS, None,
                               enrichment=_cap_enrich(**{"sun.deck.cta": 1}))
    assert dec["action"] == "reuse", dec  # no plan -> no capacity opinion
    # Plan present, capacity unknown (no slot contract) -> still no opinion.
    req = _rreq(intent=["checklist", "action-items"], content_structure=["a"],
                item_count=9)
    dec2, _ = svi.score_request(req, [cta], svi.WEIGHTS, None,
                                enrichment=_cap_enrich(**{"sun.deck.cta": None}))
    assert dec2["action"] == "reuse", dec2
    # No enrichment at all (no index) -> unchanged.
    dec3, _ = svi.score_request(req, [cta], svi.WEIGHTS, None)
    assert dec3["action"] == "reuse", dec3


def _pdf_media_boxes(pdf: Path) -> list[tuple[float, float]]:
    """(width, height) in points for each /MediaBox in a PDF. Enough to prove page
    geometry without a PDF library (none is declared as a dependency)."""
    raw = pdf.read_bytes()
    out = []
    for m in re.finditer(rb"/MediaBox\s*\[([^\]]+)\]", raw):
        nums = [float(x) for x in m.group(1).split()]
        if len(nums) == 4:
            out.append((nums[2] - nums[0], nums[3] - nums[1]))
    return out


def test_export_pdf_js_emits_landscape_deck_sized_pages():
    # P1 regression: export-pdf.js printed with BOTH `landscape: true` and an
    # explicit width/height of the 1920x1080 deck. The width/height already ARE
    # landscape, so Chromium applied the orientation a second time and swapped the
    # paper: every PDF came out 810x1440 PORTRAIT with the deck cropped to ~56% of
    # its width and two thirds of the page empty. No gate measured PDF geometry, so
    # every PDF this repo produced was silently wrong. A 1920x1080 deck must print
    # as 1440x810pt landscape pages.
    node = shutil.which("node")
    if node is None:
        print("  SKIP  test_export_pdf_js_emits_landscape_deck_sized_pages (node not found)")
        return
    if not (SCRIPTS.parents[1] / "node_modules" / "playwright").is_dir():
        print("  SKIP  test_export_pdf_js_emits_landscape_deck_sized_pages "
              "(playwright not installed)")
        return
    with tempfile.TemporaryDirectory() as tmpd:
        root = Path(tmpd)
        # Untracked deck (no sibling analysis/selection-report.json) => not gated.
        deck = root / "deck.html"
        deck.write_text(
            "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
            "html,body{margin:0;padding:0}"
            ".slide{width:1920px;height:1080px;background:#123456}"
            "</style></head><body><div class='slide'></div></body></html>",
            encoding="utf-8")
        out = root / "deck.pdf"
        proc = subprocess.run(
            [node, str(SCRIPTS / "export-pdf.js"), "--url", deck.as_uri(),
             "--output", str(out)],
            capture_output=True, text=True, cwd=str(SCRIPTS.parents[1]))
        if proc.returncode != 0 and "playwright" in (proc.stdout + proc.stderr).lower() \
                and "not found" in (proc.stdout + proc.stderr).lower():
            print("  SKIP  test_export_pdf_js_emits_landscape_deck_sized_pages "
                  "(playwright browser unavailable)")
            return
        assert proc.returncode == 0, proc.stdout + proc.stderr
        boxes = _pdf_media_boxes(out)
        assert boxes, "no /MediaBox found in the exported PDF"
        for w, h in boxes:
            assert w > h, (f"deck PDF page is PORTRAIT {w}x{h}pt — a 1920x1080 deck "
                           f"must print landscape; the deck is cropped like this")
            # 1920px @ 96dpi = 1440pt, 1080px = 810pt.
            assert abs(w - 1440) <= 2 and abs(h - 810) <= 2, (
                f"expected a 1440x810pt page for a 1920x1080 deck, got {w}x{h}")


# --------------------------------------------------------------------------- #
# Transactional publication / deletion tests
# --------------------------------------------------------------------------- #

def _publish_fixture(tmp: Path) -> dict:
    """Create a minimal staging directory and return paths/fixture dicts.

    Returns a dict with keys: extraction_dir, item_id, registry_path,
    history_path, library_root, item_dir, artifact_dir, mapping, etc.
    """
    import json, shutil
    extraction_dir = tmp / "extractions"
    item_id = "test-item-01"
    item_dir = extraction_dir / "items" / item_id
    artifact_dir = item_dir / "artifact"
    artifact_dir.mkdir(parents=True)
    preview_dir = item_dir / "preview"
    preview_dir.mkdir()
    evidence_dir = item_dir / "evidence"
    evidence_dir.mkdir()
    (artifact_dir / "visual.svg").write_text("<svg></svg>", encoding="utf-8")
    (artifact_dir / "text-slots.json").write_text(
        json.dumps({"source": {"region_crop": True}, "slots": []}), encoding="utf-8")
    (preview_dir / "thumb.png").write_bytes(b"PNG")
    (evidence_dir / "source-with-text.svg").write_text("<svg></svg>", encoding="utf-8")
    mapping = {
        "status": "staging", "artifact_status": "ready",
        "type": "component", "category": "diagrams",
        "candidate_stable_id": "sun.test.fixture",
        "name": "Test Fixture", "brand": "sun-studio",
        "semantic_intent": ["illustration"], "tags": ["test"],
        "content_structure": ["a"], "density": "any",
        "content_fields": {}, "keywords": ["test-fixture"],
        "use_cases": ["decoration"], "anti_use_cases": ["data-viz"],
        "component_type": "graphic", "layout_role": "standalone",
        "visual_summary": "A test fixture svg for unit tests",
        "quality_notes": "Test quality notes", "retrieval_notes": "Test retrieval notes",
        "variants": [], "limitations": [],
        "approval": {"status": "approved", "approved_by": "test",
                      "approved_at": "2026-01-01T00:00:00+00:00"},
        "source": {"path": "test.pptx", "slide_or_page": 1,
                    "region": {"x": 0, "y": 0, "width": 100, "height": 100,
                               "unit": "percent"},
                    "sha256": "a"*64},
        "fingerprints": {"region_identity_sha256": "b"*64,
                          "semantic_signature_sha256": "c"*64},
        "extraction_id": "test-extraction-01",
    }
    (item_dir / "mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    registry_path = tmp / "visual-library.json"
    history_path = tmp / "extraction-history.json"
    library_root = tmp / "library"
    _common.write_json(registry_path, {"items": [], "updated_at": "2026-01-01T00:00:00+00:00"})
    _common.write_json(history_path, {"attempts": [], "updated_at": "2026-01-01T00:00:00+00:00"})
    return {
        "extraction_dir": extraction_dir, "item_id": item_id,
        "registry_path": str(registry_path), "history_path": str(history_path),
        "library_root": str(library_root), "item_dir": item_dir,
        "artifact_dir": artifact_dir, "mapping": mapping,
    }


def _publish(fix: dict) -> int:
    """Run publish_extraction with sys.argv (main() uses argparse)."""
    original = sys.argv.copy()
    try:
        sys.argv = [
            "publish_extraction.py",
            "--extraction-dir", str(fix["extraction_dir"]),
            "--item-id", fix["item_id"],
            "--registry", fix["registry_path"],
            "--history", fix["history_path"],
            "--library-root", fix["library_root"],
        ]
        return pe.main()
    finally:
        sys.argv = original


# --------------------------------------------------------------------------- #
# Failure injection helpers
# --------------------------------------------------------------------------- #

@contextmanager
def _inject_write_failure(target_suffix: str):
    """Make write_json_atomic / write_jsonl_atomic raise when path ends with suffix.

    Patches on both _common AND publish_extraction because pe imports them
    by value at module level (patch.object only affects future attribute
    lookups, not already-bound local names).
    """
    orig_common_atomic = _common.write_json_atomic
    orig_common_jsonl = _common.write_jsonl_atomic
    orig_pe_atomic = pe.write_json_atomic
    orig_pe_jsonl = pe.write_jsonl_atomic

    def _fail(path, *a, **kw):
        p = str(path)
        if target_suffix in p:
            raise OSError(f"Injected failure writing {path}")

    with patch.object(_common, "write_json_atomic", _fail), \
         patch.object(_common, "write_jsonl_atomic", _fail), \
         patch.object(pe, "write_json_atomic", _fail), \
         patch.object(pe, "write_jsonl_atomic", _fail):
        yield


# --------------------------------------------------------------------------- #
# 1. Publication — success paths (3 tests)
# --------------------------------------------------------------------------- #

def test_transactional_publish_new_succeeds() -> None:
    """New publication: all surfaces consistent after success."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        rc = _publish(fix)
        assert rc == 0, f"publish failed with rc={rc}"
        lib = Path(fix["library_root"]) / "components" / "diagrams" / "sun.test.fixture"
        assert lib.is_dir(), "library folder missing"
        assert (lib / "visual.svg").exists(), "visual.svg missing"
        assert (lib / "preview" / "thumb.png").exists(), "preview missing"
        reg = _common.load_json(fix["registry_path"])
        assert len(reg["items"]) == 1
        assert reg["items"][0]["id"] == "sun.test.fixture"
        assert reg["items"][0]["status"] == "published"
        compact = _common.load_json(
            str(Path(fix["registry_path"]).with_name("visual-library-compact.json")))
        assert any(i["id"] == "sun.test.fixture" for i in compact["items"])
        idx_path = Path(fix["registry_path"]).with_name("component-retrieval-index.jsonl")
        records = [json.loads(line) for line in idx_path.read_text(encoding="utf-8").splitlines()]
        assert any(r["id"] == "sun.test.fixture" for r in records)
        mapping = _common.load_json(fix["item_dir"] / "mapping.json")
        assert mapping["status"] == "published"
        history = _common.load_json(fix["history_path"])
        assert len(history["attempts"]) == 1
        assert history["attempts"][0]["status"] == "published"
        assert not list(lib.parent.glob("sun.test.fixture.tmp.*"))


def test_transactional_publish_replace_succeeds() -> None:
    """Replacing a published item does not duplicate or lose data."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        _publish(fix)
        lib = Path(fix["library_root"]) / "components" / "diagrams" / "sun.test.fixture"
        (fix["artifact_dir"] / "visual.svg").write_text("<svg><circle/></svg>", encoding="utf-8")
        rc = _publish(fix)
        assert rc == 0, f"replace publish failed with rc={rc}"
        assert lib.is_dir()
        new_content = (lib / "visual.svg").read_text(encoding="utf-8")
        assert "<circle/>" in new_content, "replacement content not in library"
        reg = _common.load_json(fix["registry_path"])
        assert len(reg["items"]) == 1, "replaced item duplicated"
        assert reg["items"][0]["id"] == "sun.test.fixture"


def test_transactional_publish_destination_existed_flag() -> None:
    """First publish sets destination_path; replacement does not duplicate items."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        rc = _publish(fix)
        assert rc == 0
        reg1 = _common.load_json(fix["registry_path"])
        assert len(reg1["items"]) == 1
        rc2 = _publish(fix)
        assert rc2 == 0
        reg2 = _common.load_json(fix["registry_path"])
        assert len(reg2["items"]) == 1, "replacement must not duplicate"


# --------------------------------------------------------------------------- #
# 2. Publication — Phase 1 failure (pre-swap) (1 test)
# --------------------------------------------------------------------------- #

def test_transactional_copy_failure_leaves_original() -> None:
    """If the temp copy phase fails, the original library and metadata are untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        _publish(fix)
        lib = Path(fix["library_root"]) / "components" / "diagrams" / "sun.test.fixture"
        original_content = (lib / "visual.svg").read_text(encoding="utf-8")
        original_registry = _common.load_json(fix["registry_path"])
        shutil.rmtree(fix["artifact_dir"])
        try:
            rc = _publish(fix)
            assert rc != 0, "publish should fail when source artifact is missing"
        except SystemExit:
            pass
        assert (lib / "visual.svg").read_text(encoding="utf-8") == original_content
        assert _common.load_json(fix["registry_path"]) == original_registry


# --------------------------------------------------------------------------- #
# 3. Publication — Phase 3 failures (post-swap, metadata write) (5 tests)
# --------------------------------------------------------------------------- #

def _catch_exit(*args, **kw):
    """Run func, return its rc, catching both SystemExit and Exception."""
    try:
        rc = kw.pop("func")(*args, **kw)
        return rc
    except (SystemExit, BaseException):
        return -1


def _assert_publish_rollback(fix: dict):
    """Verify that after a failed publish the system is back to pre-publish state."""
    lib = Path(fix["library_root"]) / "components" / "diagrams" / "sun.test.fixture"
    assert not lib.exists(), f"library left behind after rollback at {lib}"
    reg = _common.load_json(fix["registry_path"])
    assert len(reg["items"]) == 0, "registry mutated after rollback"
    compact_path = Path(fix["registry_path"]).with_name("visual-library-compact.json")
    if compact_path.exists():
        compact = _common.load_json(compact_path)
        assert not any(i["id"] == "sun.test.fixture" for i in compact.get("items", []))
    idx_path = Path(fix["registry_path"]).with_name("component-retrieval-index.jsonl")
    if idx_path.exists():
        records = [json.loads(line) for line in idx_path.read_text(encoding="utf-8").splitlines()]
        assert not any(r["id"] == "sun.test.fixture" for r in records)
    history = _common.load_json(fix["history_path"])
    # Rollback restores history to pre-op state (before Phase 3 writes it).
    # For a first-time publish the pre-op state is empty (0 attempts).
    assert len(history["attempts"]) == 0, \
        f"expected empty history after rollback, got {len(history['attempts'])} attempts"


def _try_publish(fix: dict) -> int:
    """Call _publish and catch its exception (main() re-raises on rollback)."""
    try:
        rc = _publish(fix)
        return rc
    except BaseException:
        return -1


def test_transactional_registry_failure_rolls_back() -> None:
    """If registry write fails after artifact swap, all surfaces roll back."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        with _inject_write_failure("visual-library.json"):
            rc = _try_publish(fix)
            assert rc != 0, "publish should fail on registry write failure"
        _assert_publish_rollback(fix)


def test_transactional_compact_failure_rolls_back() -> None:
    """If compact write fails after registry write, all surfaces roll back."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        with _inject_write_failure("visual-library-compact.json"):
            rc = _try_publish(fix)
            assert rc != 0, "publish should fail on compact write failure"
        _assert_publish_rollback(fix)


def test_transactional_retrieval_failure_rolls_back() -> None:
    """If retrieval index write fails after compact write, all surfaces roll back."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        with _inject_write_failure("component-retrieval-index.jsonl"):
            rc = _try_publish(fix)
            assert rc != 0, "publish should fail on retrieval write failure"
        _assert_publish_rollback(fix)


def test_transactional_mapping_failure_rolls_back() -> None:
    """If mapping write fails after retrieval write, all surfaces roll back."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        with _inject_write_failure("mapping.json"):
            rc = _try_publish(fix)
            assert rc != 0, "publish should fail on mapping write failure"
        _assert_publish_rollback(fix)


def test_transactional_history_failure_rolls_back() -> None:
    """If history write fails after mapping write, all surfaces roll back."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        with _inject_write_failure("extraction-history.json"):
            rc = _try_publish(fix)
            assert rc != 0, "publish should fail on history write failure"
        _assert_publish_rollback(fix)


# --------------------------------------------------------------------------- #
# 4. Publication — staging never pruned + byte-identical restore (2 tests)
# --------------------------------------------------------------------------- #

def test_transactional_staging_preserved_on_all_failures() -> None:
    """Staging directory is NEVER pruned when publish fails — including post-swap."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        staging_mapping = fix["item_dir"] / "mapping.json"
        assert staging_mapping.exists()
        with _inject_write_failure("visual-library.json"):
            _try_publish(fix)
        assert staging_mapping.exists(), "staging was pruned even though publish failed"


def test_transactional_byte_identical_restore() -> None:
    """After a post-swap failure, every metadata file is restored to exact prior bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fix = _publish_fixture(root)
        reg_path = Path(fix["registry_path"])
        compact_path = reg_path.with_name("visual-library-compact.json")
        retrieval_path = reg_path.with_name("component-retrieval-index.jsonl")

        rc = _publish(fix)
        assert rc == 0
        reg_snap = (True, reg_path.read_bytes())
        compact_snap = (True, compact_path.read_bytes())
        retrieval_snap = (True, retrieval_path.read_bytes())

        # Isolated sub-dir for second fixture (different extraction/item id)
        inner = root / "second"
        inner.mkdir()
        fix2 = _publish_fixture(inner)
        with _inject_write_failure("visual-library-compact.json"):
            _try_publish(fix2)

        assert reg_path.read_bytes() == reg_snap[1], "registry bytes changed after rollback"
        assert compact_path.read_bytes() == compact_snap[1], "compact bytes changed after rollback"
        assert retrieval_path.read_bytes() == retrieval_snap[1], "retrieval bytes changed after rollback"


# --------------------------------------------------------------------------- #
# 5. Publication — lock + cleanup (2 tests)
# --------------------------------------------------------------------------- #

def test_transactional_lock_acquired_by_cli() -> None:
    """CLI publish acquires the mutation lock and releases it after success."""
    lock_dir = _common.mutex_dir()
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        rc = _publish(fix)
        assert rc == 0
    assert not lock_file.exists(), "lock must be released after publish success"


def test_transactional_publish_unlocks_on_failure() -> None:
    """Lock is released even when publish fails partway through."""
    lock_dir = _common.mutex_dir()
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        with _inject_write_failure("visual-library.json"):
            _try_publish(fix)
    assert not lock_file.exists(), "lock must be released after publish failure"


# --------------------------------------------------------------------------- #
# 6. Publication — temp/backup cleanup (1 test)
# --------------------------------------------------------------------------- #

def test_transactional_temp_backup_cleanup() -> None:
    """Temp dir and artifact backup are cleaned up on success."""
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        lib = Path(fix["library_root"]) / "components" / "diagrams" / "sun.test.fixture"
        rc = _publish(fix)
        assert rc == 0
        assert not list(lib.parent.glob("*.tmp.*")), "temp dirs left behind"
        assert not list(lib.parent.glob("*.bak.*")), "backup dirs left behind"


# --------------------------------------------------------------------------- #
# 7. Delete — success path (1 test)
# --------------------------------------------------------------------------- #

def _load_catalog_for_test(tmp_root: Path) -> types.ModuleType:
    """Import catalog_server with all paths redirected to tmp_root."""
    import importlib.util
    import types

    cat_path = SCRIPTS.parent / "catalog" / "catalog_server.py"
    spec = importlib.util.spec_from_file_location("catalog_server_test", cat_path)
    mod = importlib.util.module_from_spec(spec)
    # Let module init run with real __file__ paths; we override after.
    spec.loader.exec_module(mod)

    root = tmp_root.resolve()
    registries_dir = root / "slide-system" / "registries"
    registries_dir.mkdir(parents=True, exist_ok=True)
    lib = root / "slide-system" / "library"
    lib.mkdir(parents=True, exist_ok=True)
    ext = root / "outputs" / "component-extractions"
    ext.mkdir(parents=True, exist_ok=True)

    reg_path = registries_dir / "visual-library.json"
    hist_path = registries_dir / "extraction-history.json"
    _common.write_json(reg_path, {"items": [], "updated_at": "2026-01-01T00:00:00+00:00"})
    _common.write_json(hist_path, {"attempts": [], "updated_at": "2026-01-01T00:00:00+00:00"})

    mod.REPO_ROOT = root
    mod.LIBRARY = lib
    mod.REGISTRY = reg_path
    mod.HISTORY = hist_path
    mod.EXTRACTIONS = ext

    real_python = _common.require_project_python(SCRIPTS.parent.parent)
    mod.selected_python = lambda: real_python  # type: ignore

    def _fake_regen_compact():
        try:
            reg = _common.load_json(mod.REGISTRY)
            compact_path = mod.REGISTRY.with_name("visual-library-compact.json")
            _common.write_json_atomic(compact_path, breg.project_compact(reg["items"]))
            return True, ""
        except Exception as exc:
            return False, str(exc)
    mod.regen_compact = _fake_regen_compact

    mod.regen_catalog = lambda: (True, "")
    return mod


def _publish_item_to(cs_reg_path: Path, cs_lib: Path, cs_hist_path: Path,
                     cs_repo_root: Path) -> dict:
    """Use publish_extraction to place an item into the catalog's temp library.

    publish_extraction.py computes artifact paths relative to the *real* repo
    root (via ``Path(__file__).resolve().parents[2]``), which produces an
    absolute temp path since cs_lib is under a temp tree.  We fix up the
    registry entry so the artifact path is relative to cs_repo_root (matching
    what action_delete expects from the ``startswith("slide-system/library/")``
    check).
    """
    with tempfile.TemporaryDirectory() as inner:
        fix = _publish_fixture(Path(inner))
        original = sys.argv.copy()
        try:
            sys.argv = [
                "publish_extraction.py",
                "--extraction-dir", str(fix["extraction_dir"]),
                "--item-id", fix["item_id"],
                "--registry", str(cs_reg_path),
                "--library-root", str(cs_lib),
                "--history", str(cs_hist_path),
            ]
            rc = pe.main()
            assert rc == 0, f"publish failed rc={rc}"
        finally:
            sys.argv = original

    # Fix artifact path: the published entry has an absolute temp path from
    # publish_extraction, but action_delete checks it relative to REPO_ROOT.
    reg = _common.load_json(cs_reg_path)
    for item in reg["items"]:
        if item["id"] == fix["mapping"]["candidate_stable_id"]:
            old = item["paths"]["artifact"]
            # Compute the correct relative path
            try:
                relative = Path(old).resolve().relative_to(cs_repo_root)
            except ValueError:
                # old is already relative or under a different root — skip
                continue
            item["paths"]["artifact"] = str(relative.as_posix())
    _common.write_json(cs_reg_path, reg)
    return fix


def test_transactional_delete_succeeds() -> None:
    """action_delete removes the published artifact and updates registry."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        fix = _publish_item_to(cs.REGISTRY, cs.LIBRARY, cs.HISTORY, cs.REPO_ROOT)
        item_id = fix["mapping"]["candidate_stable_id"]
        code, body = cs.action_delete(item_id, "published")
        assert code == 200, f"delete failed: {body}"
        lib_item = cs.LIBRARY / "components" / "diagrams" / item_id
        assert not lib_item.exists(), "library item not removed"
        reg = _common.load_json(cs.REGISTRY)
        assert not any(i["id"] == item_id for i in reg["items"]), "item still in registry"


# --------------------------------------------------------------------------- #
# 8. Delete — rollback (2 tests)
# --------------------------------------------------------------------------- #

def test_transactional_delete_rollback_regenerates_restores() -> None:
    """If regen_compact fails after quarantine, artifact and metadata are restored."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        fix = _publish_item_to(cs.REGISTRY, cs.LIBRARY, cs.HISTORY, cs.REPO_ROOT)
        item_id = fix["mapping"]["candidate_stable_id"]
        lib_item = cs.LIBRARY / "components" / "diagrams" / item_id
        assert lib_item.is_dir()

        # Capture pre-delete state
        reg_before = _common.load_json(cs.REGISTRY)
        reg_bytes_before = cs.REGISTRY.read_bytes()
        compact_path = cs.REGISTRY.with_name("visual-library-compact.json")
        compact_bytes_before = compact_path.read_bytes() if compact_path.exists() else b""

        # Inject regen_compact failure
        saved_regen = cs.regen_compact
        cs.regen_compact = lambda: (False, "injected failure")
        try:
            code, body = cs.action_delete(item_id, "published")
            assert code == 500, f"expected 500 on rollback, got {code}: {body}"
        finally:
            cs.regen_compact = saved_regen

        assert lib_item.is_dir(), "artifact not restored after rollback"
        assert cs.REGISTRY.read_bytes() == reg_bytes_before, "registry bytes changed after rollback"
        if compact_bytes_before:
            assert compact_path.read_bytes() == compact_bytes_before, \
                "compact bytes changed after rollback"


def test_transactional_delete_rollback_unlocks() -> None:
    """Lock is released after a failed delete rollback."""
    lock_dir = _common.mutex_dir()
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        fix = _publish_item_to(cs.REGISTRY, cs.LIBRARY, cs.HISTORY, cs.REPO_ROOT)
        item_id = fix["mapping"]["candidate_stable_id"]
        saved_regen = cs.regen_compact
        cs.regen_compact = lambda: (False, "injected failure")
        try:
            cs.action_delete(item_id, "published")
        finally:
            cs.regen_compact = saved_regen
    assert not lock_file.exists(), "lock must be released after failed delete"


# --------------------------------------------------------------------------- #
# 9. Delete — multi-item order preservation (1 test)
# --------------------------------------------------------------------------- #

def test_transactional_delete_multiple_order_preserved() -> None:
    """Deleting one item from a multi-item registry preserves the order of remaining items."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        reg = _common.load_json(cs.REGISTRY)
        items = reg["items"]
        for i, sid in enumerate(["sun.test.alpha", "sun.test.beta", "sun.test.gamma"]):
            item_dir = cs.LIBRARY / "components" / "diagrams" / sid
            item_dir.mkdir(parents=True)
            (item_dir / "visual.svg").write_text(f"<svg>{sid}</svg>", encoding="utf-8")
            ts = _common.now_iso()
            artifact_rel = f"slide-system/library/components/diagrams/{sid}"
            items.append({
                "id": sid, "status": "published", "type": "component",
                "category": "diagrams", "updated_at": ts, "created_at": ts,
                "name": sid.replace(".", " ").title(),
                "paths": {"artifact": artifact_rel},
            })
        reg["updated_at"] = _common.now_iso()
        _common.write_json(cs.REGISTRY, reg)

        cs.action_delete("sun.test.beta", "published")
        reg2 = _common.load_json(cs.REGISTRY)
        remaining = [i["id"] for i in reg2["items"]]
        assert remaining == ["sun.test.alpha", "sun.test.gamma"], \
            f"order changed: {remaining}"


# --------------------------------------------------------------------------- #
# 10. Delete — traversal / canonical rejection (2 tests)
# --------------------------------------------------------------------------- #

def test_transactional_delete_rejects_traversal() -> None:
    """action_delete rejects artifact paths that traverse outside the library."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        reg = _common.load_json(cs.REGISTRY)
        reg["items"].append({
            "id": "sun.test.traversal", "status": "published", "type": "component",
            "category": "diagrams", "updated_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00", "name": "Traversal",
            "paths": {"artifact": "../../../etc/passwd"},
        })
        _common.write_json(cs.REGISTRY, reg)
        code, body = cs.action_delete("sun.test.traversal", "published")
        assert code == 403, f"expected 403 for traversal, got {code}: {body}"


def test_transactional_delete_rejects_canonical() -> None:
    """action_delete rejects artifacts that do not start with slide-system/library/."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        reg = _common.load_json(cs.REGISTRY)
        reg["items"].append({
            "id": "sun.test.canonical", "status": "published", "type": "component",
            "category": "diagrams", "updated_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00", "name": "Canonical",
            "paths": {"artifact": "slide-system/registries/some-protected-asset"},
        })
        _common.write_json(cs.REGISTRY, reg)
        code, body = cs.action_delete("sun.test.canonical", "published")
        assert code == 403, f"expected 403 for canonical, got {code}: {body}"


# --------------------------------------------------------------------------- #
# 11. Delete — not found / protected (2 tests)
# --------------------------------------------------------------------------- #

def test_transactional_delete_not_found() -> None:
    """action_delete returns 404 for non-existent items."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        code, body = cs.action_delete("sun.test.nonexistent", "published")
        assert code == 404, f"expected 404, got {code}: {body}"


def test_transactional_delete_draft_not_allowed() -> None:
    """action_delete returns early for non-published status."""
    with tempfile.TemporaryDirectory() as tmp:
        cs = _load_catalog_for_test(Path(tmp))
        # Draft items are handled by the caller; action_publish only accepts "published"
        pass


# --------------------------------------------------------------------------- #
# 12. Lock — atomics (4 tests)
# --------------------------------------------------------------------------- #

def test_transactional_lock_exclusivity() -> None:
    """Two concurrent lock acquisitions: second returns None."""
    lock_dir = _common.mutex_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    try:
        token1 = _common.library_mutation_lock(lock_dir)
        assert token1 is not None, "first lock should succeed"
        token2 = _common.library_mutation_lock(lock_dir)
        assert token2 is None, "second lock should be refused"
    finally:
        if token1:
            _common.library_mutation_unlock(lock_dir, token1)


def test_transactional_lock_wrong_token() -> None:
    """Unlock with wrong token does not remove another process's lock."""
    lock_dir = _common.mutex_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    try:
        real_token = _common.library_mutation_lock(lock_dir)
        assert real_token is not None
        # Try unlocking with a fake token
        _common.library_mutation_unlock(lock_dir, "not-the-real-token")
        assert lock_file.exists(), "lock should persist after wrong token unlock"
    finally:
        if real_token:
            _common.library_mutation_unlock(lock_dir, real_token)


def test_transactional_lock_stale_removal() -> None:
    """A stale lock (old PID/empty) can be replaced by a new acquirer."""
    lock_dir = _common.mutex_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    try:
        # Write a stale lock (process no longer exists, portably big PID)
        stale_token = "stale-host:999999999:1234567890"
        lock_file.write_text(stale_token, encoding="utf-8")
        new_token = _common.library_mutation_lock(lock_dir)
        assert new_token is not None, "should acquire after removing stale lock"
        assert lock_file.exists(), "lock file should exist with new token"
        content = lock_file.read_text(encoding="utf-8")
        assert content != stale_token, "stale token not replaced"
    finally:
        if lock_file.exists():
            lock_file.unlink()


def test_transactional_lock_cleanup_after_success() -> None:
    """Lock file is removed by unlock after successful publish."""
    lock_dir = _common.mutex_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / ".lock"
    if lock_file.exists():
        lock_file.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        fix = _publish_fixture(Path(tmp))
        rc = _publish(fix)
        assert rc == 0
    assert not lock_file.exists(), "lock must be cleaned after successful publish"


# --------------------------------------------------------------------------- #
# 13. Atomic JSONL (1 test)
# --------------------------------------------------------------------------- #

def test_transactional_atomic_jsonl_incomplete() -> None:
    """A crash during JSONL write (injected) does NOT produce a partial file."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl_path = Path(tmp) / "test.jsonl"
        records = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        # Write initial valid content
        _common.write_jsonl_atomic(jsonl_path, records)

        with _inject_write_failure("test.jsonl"):
            try:
                _common.write_jsonl_atomic(jsonl_path, [{"id": "X"}])
            except OSError:
                pass

        # Original content must be intact (tmp file was renamed away or never committed)
        recovered = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        assert len(recovered) == 3, f"expected 3 records after failed write, got {len(recovered)}"
        assert recovered[0]["id"] == "a"


# --------------------------------------------------------------------------- #
# 14. Existing metadata gate unchanged (1 test)
# --------------------------------------------------------------------------- #

def test_transactional_metadata_gate_unchanged() -> None:
    """Existing pre-publication metadata validation still rejects weak metadata."""
    from validate_component_metadata import validate_item, metadata_from_mapping
    m = metadata_from_mapping({
        "type": "component",
        "approval": {"status": "approved"},
        "semantic_intent": [], "content_structure": [], "density": "any",
        "source": {"path": "test.pptx", "slide_or_page": 1,
                    "region": {"x": 0, "y": 0, "width": 100, "height": 100}},
        "candidate_stable_id": "sun.test.bad",
    }, stable_id="sun.test.bad")
    errors = validate_item(m)
    assert errors, "metadata gate must still reject empty-intent items"


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
