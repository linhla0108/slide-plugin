# Plan: Proximity-run component grouping — distinct groups as separate items

**Date:** 2026-06-25
**Branch:** `feat/harness-enforcement-and-component-recognition`
**Status:** ✅ DONE — converged on iteration 1. Page 2 → 3 proximity groups
emitted as **3 separate catalog items**, each rendered as the whole run with
every variant preserved (Level ×5 yellow→black, role ×4 distinct icons, banner
×2 orange/blue), each carousel = [group strip, shared full-page source].
`test_gates.py` **34/34**. Browser-verified on the Draft tab. No bug surfaced.

## Goal (confirmed via interview-me)

Separation + shape-dedup already work. Change the classification rule so the
catalog Draft shows **distinct component groups as separate items**:

- **Proximity-run grouping (NEW).** Within one shape-class, instances that sit
  **near each other** (small gap on each axis — strict alignment NOT required)
  form one *group*. Each group is rendered as the **whole run as it appears in
  the original**, keeping every member's real **color/icon variation** (the 5
  Level cards yellow→black, the 4 role cards with different icons). It is NOT
  collapsed to a single representative.
- **Standalone / different-shape** instances (different shape, or same shape but
  spatially isolated) → their **own separate item**.
- The catalog emits **one item per group** (not one bundled carousel).
- **Every** group item shares the same full-page-2 **source image** for
  side-by-side comparison.

### Why
Today `classify_page_components.py` collapses each shape-class to ONE
representative card, destroying the deliberate variation (gradient progression,
4 role icons) that expresses the design intent. The user wants the adjacent run
preserved as a single reusable "pattern", and genuinely distinct elements split
out as their own items.

## Constraints
- PyMuPDF-only; no new libs (REQUIREMENTS.md). Reuse the existing
  spatial-cluster + shape-class + fragment machinery; add proximity grouping on
  top. Bbox measurement via Chromium (`measure_svg_groups.js`).
- Do **not** touch the 78 published items / canonical assets / templates.
  Only the staging batch is regenerated. Draft-only — no publishing.

## Design

### `classify_page_components.py`
1. `_proximity_groups(instances, class_idxs, gap_frac)` — union-find over the
   instances of ONE shape-class. Two instances are adjacent when the gap between
   their bboxes on **each** axis ≤ `gap_frac × min(size)` on that axis
   (overlap ⇒ gap 0). Rows (gap_y≈0, small gutter_x) and grids both group;
   distant same-shape instances split.
2. In `process_item`: `classes = _shape_classes(...)`; for each class,
   `_proximity_groups(...)`; flatten to a list of **groups**; sort by reading
   order (group top-left).
3. Each group → one fragment built from the **union of all member instances'
   leaf-members** (so every variant card is reproduced), via the existing
   `_build_fragment` (already multi-member capable).
4. Manifest rewrite: emit `groups[]` (group_id, file, shape_class,
   member_count, group_bounds, member_bounds), plus `shape_class_count`,
   `group_count`. Keep `instance_count`, `dropped_small_clusters`,
   `background_candidates`, `params` (+ `group_gap_frac`).
5. New CLI flag `--group-gap-frac` (default calibrated against page 2 — log the
   real inter-card gaps first, then set).

### `build_component_catalog.py`
- When `components-manifest.json` has `groups`, expand the single staging item
  into **one catalog item per group**: id `…board.gNN`, name `… — group NN`,
  `images = [ {group fragment}, {shared Source (original region)} ]`. No bundled
  carousel item. Fallback to prior behavior when no manifest.
- Known limitation (documented, not fixed here): per-group catalog items share
  one `staging_dir`; Delete removes the whole extraction. Acceptable for
  Draft-only review; publishing is out of scope this round.

### `test_gates.py`
- Add `test_classify_groups_adjacent_same_shape_run` (a row of 3 same-shape
  near instances ⇒ 1 group of 3).
- Add `test_classify_splits_distant_same_shape` (2 same-shape instances far
  apart ⇒ 2 groups).
- Add `test_classify_keeps_different_shapes_separate` (adjacent but different
  shape ⇒ not grouped).
- Keep all existing tests green (helpers unchanged in signature).

## Loop protocol (run until no bugs)
Each iteration: run classify + catalog → self-verify (manifest counts → render
each group fragment non-blank & shows multiple variant cards → browser Draft
shows N separate items, each = whole run + shared source) → if bug, append to
Bug Log, fix, repeat. Stop when: groups correct for page 2 (Level ×5 strip,
role ×4 strip, banner ×2 — as separate items, variants visible), each fragment
non-blank, browser shows separate items + shared source, `test_gates.py` green.

## Bug Log (append during the loop)
| ID | Symptom | Root cause | Fix | Status |
|----|---------|-----------|-----|--------|

**Iteration 1 result:** no bug surfaced. With default `group_gap_frac=0.6` the
three rows grouped correctly on the first run (group bounds spanned the full row
widths: 1960 / 1904 / 1775 px). Each group fragment rendered non-blank with all
variant cards visible; the catalog expansion produced 3 separate Draft items;
`test_gates.py` 34/34. Loop converged — no further iterations needed.

## Acceptance
Clean re-run reproduces: page-2 Draft = separate items per proximity-run, each
showing the full strip with color/icon variation + the shared full-page source;
`test_gates.py` green; plan status → ✅; session-log entry written.
