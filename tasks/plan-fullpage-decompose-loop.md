# Plan: Full-page decompose — autonomous fix / run / test loop

**Date:** 2026-06-25
**Branch:** `feat/harness-enforcement-and-component-recognition`
**Status:** ✅ DONE — converged after iteration 1. Full page 2 decomposed into
**3 distinct classes** (Level cards ×5, role cards ×4, metric banners ×2 = 11
instances), each rendered non-blank + visually distinct, browser-verified in the
Draft (3 component previews + source), `test_gates.py` **31/31**. No background
emitted as a component (B1 guard added + tested).

## Goal (confirmed via interview-me)

A **clean, reproducible** proof: delete the current staging batch, re-extract
**the full page 2** of `input/GUIDLINE_PRESENTATION_SUN.pdf`, and let the
pipeline auto-decompose it so the catalog Draft shows **each distinct component
separated + classified** (identical / same-shape-different-color merged into one
representative each; different shapes kept apart) plus **one source image** of
the page for comparison.

Why full page (not the card strip): on the narrow strip, dedup collapses to a
single class (×5), which reads like "only one thing was separated." The full
page has genuine variety (top card row, lower row, heading, icons) so it
demonstrates BOTH separation AND classification.

## Constraints

- PDF→SVG via PyMuPDF only; bbox measurement via Chromium (`measure_svg_groups.js`).
  No new libraries (REQUIREMENTS.md).
- Do **not** touch the 78 published items, canonical assets, or templates.
  Only the staging batch is deleted/regenerated.

## Loop protocol (run until no bugs)

Each iteration:
1. **Run** the pipeline step(s) under test.
2. **Self-verify** at three levels, cheapest first:
   - structural — `components-manifest.json` counts, classes, dropped/background.
   - render — rasterize each class fragment; confirm non-blank + visually distinct.
   - browser — Draft tile + modal carousel = distinct classes + source.
3. **If a bug is found** → append it to the **Bug Log** below (symptom + root
   cause), fix it, then go to 1.
4. **Stop** when ALL hold:
   - classify yields the correct set of distinct classes for page 2;
   - the full-page background is NOT listed as a component;
   - every class fragment renders non-blank and is visually distinct;
   - browser Draft shows the distinct classes + a source image;
   - `test_gates.py` is green (existing + any new regression tests).

## Steps (iteration 1 baseline)

- **S1.** Delete staging batch `outputs/component-extractions/guideline-level-progression-cards/`.
- **S2.** Author a full-page-2 extraction request (semantic `item_id`, region = whole page).
- **S3.** Run the pipeline: `scaffold_extraction` → `convert_pdf_source --page 2`
  → `extract_editable_text_slots` → `crop_svg_region` (no-op for full page)
  → `externalize_svg_images` → `flatten_svg_background` → `externalize` (refresh)
  → `optimize_svg` → `apply_text_contract` → `validate_text_slots`
  → `classify_page_components` → `build_component_catalog`.
- **S4.** Verify classify manifest: >1 class, background excluded, instance counts plausible.
- **S5.** Render each class fragment → non-blank, distinct.
- **S6.** Browser: Draft tile + modal carousel.
- **S7.** `test_gates.py`.

## Anticipated bug (pre-logged)

- **B1 — full-bleed background becomes a fake component class.** On a full page
  the background (a near-canvas-size rect/image) forms its own cluster and would
  be emitted as a "class." Fix: in `classify_page_components.py`, treat a cluster
  whose coverage ≥ a threshold (≈0.7) as a **background candidate** — exclude it
  from `classes`, record it under `background_candidates` in the manifest (mirror
  how `decompose_svg_objects.py` flags base-candidates). Status: **pending**.

## Bug Log (append during the loop)

| ID | Symptom | Root cause | Fix | Status |
|----|---------|-----------|-----|--------|
| B1 | (anticipated) full-page bg listed as a component | near-full-bleed cluster emitted as a class | exclude clusters with coverage ≥ 0.7; record as `background_candidates` | ✅ guarded + tested (did NOT occur on page 2 — no discrete bg rect — but hardened for other decks; `test_classify_excludes_fullbleed_background`) |

**Iteration 1 result:** no real bug surfaced — the prior-session implementation
decomposed page 2 correctly on the first clean run. Only the pre-logged latent
B1 was hardened. Loop converged (no further iterations needed).

## Acceptance

Clean run from the request JSON reproduces: page-2 Draft shows the distinct
component classes (separated + deduped), no background tile, + a source image;
`test_gates.py` green. Then this plan's status → ✅ and a session-log entry is
written.
