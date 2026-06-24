# Plan: Prune off-canvas `<image>` elements during component crop

**Date:** 2026-06-24
**Branch:** `feat/harness-enforcement-and-component-recognition`
**Status:** ✅ IMPLEMENTED (§26). Premise correction below: pruning `visual.svg`
alone reclaims **no** disk — the off-canvas rasters are pinned by the full-page
**evidence** SVG (`evidence/source-with-text.svg`), which `publish_extraction.py`
ships. The shipped fix therefore also crops the evidence SVG to the same window
and GC-deletes now-unreferenced assets. Result: raster **101 KB → 52 KB** (49 KB /
4 files reclaimed), `validate_text_slots.py` still exit 0, suite **24/24**.
Defect originally re-confirmed live in §25 (numbers fingerprint-verified).
**Source of finding:** `docs/logs/SESSION-LOG-2026-06-24.md` §24 (first sighting)
+ §25 (re-verify) — e2e retests of `component-extractor` on
`input/GUIDLINE_PRESENTATION_SUN.pdf`.

---

## Problem

`crop_svg_region.py` rewrites a full-page extraction visual down to the selected
component region by (a) wrapping all drawables in
`<g transform="translate(-crop_x -crop_y)">` and (b) rewriting the viewBox to
`0 0 crop_w crop_h` (see lines 132–150). It **does not remove** elements that
fall entirely outside the crop window — they are merely clipped by the new
viewport but remain in the document.

`externalize_svg_images.py` then harvests **every** `<image>` into
`artifact/assets/`, including the off-canvas ones (its own docstring states it
never changes geometry — so it is the wrong place to make this decision).

### Measured impact (Level 1-5 cards, page 2 — verified §25)

Crop window pt `[440, 440, 1975, 495]`. 11 images bundled, **101 KB** total
raster on disk after `optimize_svg.py`. Visibility test = each image's page-space
bbox, shifted by the wrapper `translate(-440,-440)`, intersected with the
`0..1975 × 0..495` window:

| Group | Images | Location in SVG | KB / files |
|---|---|---|---|
| **VISIBLE — keep** | image-03..07 (the 5 cards, transY≈[10,486]) | body | 41 / 5 |
| **off-canvas — PRUNE** | image-08, 10 (metric bars 1775×272) + image-09, 11 (transY 1382–1975) | body | **49 / 4** |
| **off-canvas — leave** | image-01, 02 (transY 1434–1975) | `<defs>` (indirect paint) | 11 / 2 |

**Prunable = 49 KB / 101 KB = 48%** of raster payload (4 body images that are
wholly below the viewBox). The 11 KB in `<defs>` is referenced indirectly and
is *not* counted as prunable — it is left in place by design (see scope). Output
renders correctly today (the viewBox clips the dead images); this is an
**efficiency/cleanliness** defect, not a correctness bug. It affects **every
component-level PDF extraction**, not just this deck.

---

## Goal & scope

**Goal:** the cropped `visual.svg` (and therefore `artifact/assets/`) should
carry only images that actually intersect the crop window.

**In scope:** prune off-canvas `<image>` elements that live in the document
body (not in `<defs>`), during `crop_svg_region.py`, with a strict fail-safe.

**Explicitly out of scope (known limitation, document it):**
- Vector content (`<path>`/`<rect>`/`<text>`) off-canvas. Pruning arbitrary
  paths needs a real geometry engine (path bbox) that we do not have and that
  `REQUIREMENTS.md` does not sanction. Off-canvas vectors only bloat SVG text,
  which `optimize_svg.py` + gzip already mitigate; raster files are the real
  disk cost.
- Images inside `<defs>` — painted indirectly via pattern/mask/`<use>`; their
  on-canvas position is not locally decidable. Small here (10 KB); leave them.

---

## Design

Add a prune step to `crop_item()` in `slide-system/scripts/crop_svg_region.py`,
**after** the wrapper group is built (after line 145) and **before**
`tree.write(...)` (line 150). Reuse the already-computed crop window
`(crop_x, crop_y, crop_w, crop_h)`.

Work in **page coordinate space**: the wrapper's `translate(-crop_x, -crop_y)`
is a single uniform shift applied to all body content, so it does not change
intersection results — test each image's *page-space* bbox against
`[crop_x, crop_y, crop_x+crop_w, crop_y+crop_h]` directly.

### Algorithm

1. Collect the set of `<image>` elements reachable from any `<defs>` subtree →
   the **defs-image exclusion set** (skip these).
2. Walk the wrapper group. Maintain parent pointers (ElementTree has no
   `.getparent()` — build a child→parent map up front).
3. For each body `<image>` not in the exclusion set:
   - Read `x/y/width/height`. If any is missing → **KEEP** (fail-safe).
   - Accumulate the product of ancestor `transform` attributes, supporting only
     affine forms: `translate(tx[,ty])`, `scale(sx[,sy])`, `matrix(a b c d e f)`.
     **Decision (chosen):** work in page space. Walk from the **wrapper group's
     children** downward and accumulate their transforms; do **not** include the
     wrapper group's own `translate(-crop_x, -crop_y)`, and test the resulting
     bbox against the page-space window `[crop_x, crop_y, crop_x+crop_w,
     crop_y+crop_h]`. The wrapper translate is a single uniform shift applied to
     everything, so excluding it from both sides leaves intersection results
     unchanged and avoids a double-shift bug. Source-SVG nested transforms inside
     the drawables (if any) ARE accumulated — they affect on-canvas position.
     If any transform token is non-affine / unparseable → **KEEP** (fail-safe).
   - Compute the transformed bbox (transform the 4 corners; take min/max).
   - **Drop** the element only if the bbox does **not** intersect the window,
     using a small epsilon so edge-touching images are kept. Partial overlap →
     keep.
4. After removals, recursively delete any `<g>` left with no element children.
5. Proceed to `tree.write(...)` unchanged.

### Why this ordering is safe

- Crop runs **before** externalize in the pipeline. At crop time images are
  still embedded `data:` URIs; removing the `<image>` element means externalize
  never harvests it. **No pipeline reordering needed.**
- Idempotency is preserved: the existing `region_crop` marker already short-
  circuits a second run (lines 108–109).
- `validate_text_slots.py` is unaffected — text slots are pruned separately by
  the center test (lines 156–187) and that logic is untouched.

### Fail-safe rule (non-negotiable)

Never drop an image we cannot fully reason about. Missing geometry, a
`<defs>` ancestor, or any unparseable/non-affine transform ⇒ keep it. A few
extra KB is acceptable; a missing visible image is a correctness regression.

---

## Files to change

| File | Change |
|---|---|
| `slide-system/scripts/crop_svg_region.py` | Add `_prune_offcanvas_images(group, defs_images, window)` + affine-transform/bbox helpers; call it in `crop_item()` after the wrapper group is built. Record a count in the `region_crop` block (e.g. `"images_pruned": N`) for traceability. |
| `slide-system/scripts/test_gates.py` | New regression test(s) — see below. |
| `crop_svg_region.py` docstring | Note the new prune step + its scope/limitation. |
| `docs/logs/SESSION-LOG-<date>.md` | Log the fix (Request/Actions/Result/State). |

No change to `externalize_svg_images.py` (must stay geometry-neutral).

---

## Tests (add to `test_gates.py`)

1. **Prunes off-canvas body images** — synth SVG with: one image fully inside
   the window, one fully outside (body), one straddling the edge (partial).
   Assert after crop: inside + straddling kept, outside removed.
2. **Keeps images in `<defs>`** — an off-canvas image inside `<defs>` survives.
3. **Fail-safe on unparseable transform** — an off-canvas body image whose
   ancestor has a non-affine/garbage `transform` is **kept**.
4. **Affine transform honored** — an image placed on-canvas only via a
   `matrix(...)`/`translate(...)` is kept; one transformed off-canvas is dropped.
5. **End-to-end on the fixture** — re-run the §24 pipeline on the Level cards;
   assert `artifact/assets/` ends with exactly the 5 visible card images + the
   2 defs images (7 files), 0 of the 4 off-canvas body images.
6. **No regression** — `crop_svg_region.py` on a full-page region is still a
   no-op; all four existing crop/validate tests in `test_gates.py` still pass:
   `test_crop_region_rewrites_viewbox_and_slots` (line ~246),
   `test_crop_region_idempotent_and_full_page_noop` (~260),
   `test_crop_region_honors_absolute_units` (~270),
   `test_validate_excludes_cropped_out_source_text` (~293). The new prune step
   inserts between the wrapper-build and `tree.write`, so a no-image or
   full-page SVG is untouched.

---

## Verification (per global tool ladder — logic change, no browser)

1. `python3 -m py_compile slide-system/scripts/crop_svg_region.py`
2. `python3 slide-system/scripts/test_gates.py` → expect **all pass**
   (currently 18/18; +new tests).
3. Re-run the §24 e2e pipeline on the Level cards; confirm:
   - crop result reports `images_pruned: 4`;
   - `artifact/assets/` has 7 files (was 11);
   - inline-render still shows all 5 cards intact (no missing visible image);
   - `validate_text_slots.py` still exits 0, 16 slots kept.
4. `build_registry.py --check` clean.

**Acceptance:** dead body raster payload removed (≈49 KB / 4 files on the
fixture; 101 KB → ~52 KB raster), all visible content intact, full suite green,
no pipeline reordering.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Dropping a visible image (transform mis-parsed) | Fail-safe: keep on any uncertainty; intersection test keeps partial-overlap; epsilon keeps edge-touch. |
| Breaking a `<defs>`-referenced image | defs images excluded entirely. |
| Removing a `<g>` that still anchors a clip/gradient via id | Only remove groups with **no element children**; ids on `<defs>` are untouched. |
| ElementTree lacks parent refs | Build child→parent map before walking. |

---

## Out-of-scope follow-ups (note, do not do here)

- Generic off-canvas **vector** pruning (needs path-bbox engine).
- Stripping now-unused `<defs>` entries — `optimize_svg.py` already drops unused
  defs; out of scope for this fix.
