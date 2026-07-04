# Extract Components

This workflow runs only through the manual component-extractor skill.

0. **Mandatory tool readiness check.** Before authoring a request JSON or
   running Docling/scaffold/artifact commands, check the extraction toolchain:
   `python3 slide-system/scripts/check_base_requirements.py --input pdf` for
   PDF sources, `--input pptx` for PPTX sources, or the marker-first base check
   for SVG/package sources. Stop on any `BLOCKER`. Docling is optional, but the
   source provider for the input type is not optional; do not fall back from
   Docling to manual extraction until this check passes.

> **Optional pre-step (auto-detect candidates):** when the user wants help
> finding the reusable parts, run the analysis-only
> `scripts/analyze_with_docling.py --source <file> --extraction-id <id>`. It
> writes draft candidates under
> `outputs/component-extractions/<id>/analysis/` and changes no shared state
> (no publish, no registry, no library writes). Review and rename the draft ids
> before scaffolding. Degrades cleanly when Docling is absent. Details:
> `rules/extraction-methods.md` → "Optional: Docling candidate auto-detection".

1. Require exact source path, slide/page, and region/object.
2. Validate batch requests.
3. Fingerprint each region and check for duplicates.
4. Scaffold one output item under `outputs/component-extractions/`.
5. Classify the item and use the extraction method matrix. The reusable visual
   is text-free `artifact/visual.svg` + `artifact/text-slots.json` only; never
   author a parallel `.html`/`.css` for the same region.
6. PDF input only: convert each page with
   `scripts/convert_pdf_source.py --pdf <file> --page <n> --item-dir <item>`
   (PyMuPDF — the only approved PDF→SVG path per `REQUIREMENTS.md`). Never
   render a page to PNG as the visual: baked text is invisible to validators
   and double-renders under the gallery's editable slots.
7. For SVG-based items, generate the contract with
   `scripts/extract_editable_text_slots.py --item-dir <item>`: it preserves
   `evidence/source-with-text.svg`, emits text-free `artifact/visual.svg`, and
   describes every semantic string in `artifact/text-slots.json`
   (rules in `rules/editable-text-slots.md`). Never hand-write
   `visual.svg`/`text-slots.json` — their schemas live in the scripts.
8. Write `mapping.json` and a lightweight `evidence/notes.md` (referencing the
   source raster by path), and place the reusable output in `artifact/`. Do not
   copy source images or emit per-item README/report files. Do not commit
   `*-svg-manifest.json` audit dumps into `evidence/`.
8b. Crop the full-page visual down to the component with
   `scripts/crop_svg_region.py --item-dir <item>`: it reads `source.region` from
   `mapping.json`, rewrites `visual.svg`'s viewBox to that window, and
   re-normalizes `text-slots.json`. REQUIRED for component-level items — the
   PDF→SVG path emits the whole page, so without this the artifact is the entire
   slide with text stripped. No-op for a full-page region; idempotent.
9. Lift embedded rasters with `scripts/externalize_svg_images.py --batch <dir>`,
   merge fragmented background strips with
   `scripts/flatten_svg_background.py --batch <dir>` (Playwright render,
   pixel-diff gated; rerun externalize afterwards to refresh manifests),
   trim path precision with `scripts/optimize_svg.py --batch <dir>`, and fold the
   text contract into each mapping with
   `scripts/apply_text_contract.py --batch <dir>` (no hand-written per-batch
   `_*.py`).
10. Validate content, text-slot coverage, scaling, export support, and source
   comparison with `scripts/validate_text_slots.py`.
10b. Decompose the cropped region into its DISTINCT components with
   `scripts/classify_page_components.py --item-dir <item>`: it measures every
   on-canvas object in real Chromium layout, spatially clusters them into
   component instances, then merges identical / same-shape-different-color
   instances into ONE representative class each (e.g. 5 colored Level cards →
   one class ×5). Writes `artifact/components/*.svg` +
   `components-manifest.json`. `build_component_catalog.py` then previews the
   source region, the text-free region, and detected sub-components for
   comparison, rather than only the glued strip. Needs Chromium; skip only if it
   is unavailable.

   **Auto-stage mode**: `auto_stage_candidates.py` calls
   `classify_page_components.py --manifest-only` for strip-like Drafts. This
   keeps one parent Draft in Components → Draft, then adds each detected
   sub-card to that Draft's carousel as a source-with-text preview plus a
   matching text-free variant. It does not create separate `.gNN` Draft items
   for those sub-cards.

   For large card/diagram regions, auto-stage adds `--layout-row-groups`.
   This keeps the full Draft intact but prefers horizontal row components in
   the carousel (for example: top metric circles, middle goal/key-result/task
   row, bottom platform circles), each paired with its text-free variant.

   **Gutter split**: Before clustering, `_split_on_gutter` un-glues distinct
   components that share a small overlapping leaf. When a clean empty horizontal
   or vertical band wider than 16 px divides the large leaves, the group is
   split at that band rather than treated as a single component.

   **Pipeline hardening guards**: `_child_count_mismatch` raises `SystemExit`
   if child-index alignment is lost (prevents silent misattribution of shapes to
   the wrong group). Clusters dropped for being too small are surfaced with
   their bounding boxes as stdout `WARNING` lines so they are visible in CI logs.

   **`materialize_groups()` (default ON, `--materialize-groups` flag)**:
   After detect/classify, the script materializes each group as a real staging
   item rather than a bare SVG fragment:

   - **Shape-class dedup**: Before creating directories, groups are
     deduplicated by `shape_class`. Only the first representative per class is
     materialized — if the same component appears at five different positions on
     the canvas (five proximity clusters, same shape class), exactly one staging
     item is created. This prevents the library from filling with positional
     duplicates.

   - **Coverage guard (<10%)**: If the bounding area of all deduplicated groups
     combined covers less than 10 % of the parent canvas area, materialization
     is skipped entirely and the parent item is kept as-is. This handles unified
     diagrams where detected shapes are sub-elements (e.g. node circles inside a
     flowchart), not standalone reusable components.

   - **Staging item layout**: Each materialized group gets a
     `<base>-gNN/` subdirectory under `outputs/component-extractions/` with its
     own `mapping.json`, a viewBox-cropped `artifact/visual.svg`,
     `artifact/text-slots.json`, and the component fragment SVG. Each item is
     independently publishable through the normal approve → publish flow.

   - **`decomposed_into` marker**: After all group items are created, the
     parent's `mapping.json` receives a `"decomposed_into"` field listing the
     created item names (e.g. `["hero-slide-p3-g00", "hero-slide-p3-g01"]`).
     `build_component_catalog.py` skips any item that carries this marker — the
     parent is treated as a section container, not a standalone component, so it
     does not appear as a duplicate entry in the catalog.

   - **Per-card variant carousel**: Each materialized group item gets its own
     `artifact/components/` directory containing the group fragment SVG,
     per-card variant SVGs (one per unique instance inside that group),
     optional source-with-text card crops, and a scoped
     `components-manifest.json`. `collect_images()` in
     `build_component_catalog.py` reads this manifest to drive the catalog card
     carousel: full component → text-free full component → card source previews
     → card text-free variants.

   - **Perceptual dedup (MAE)**: Within each group, per-card variant SVGs are
     compared using perceptual signatures derived from rendered PNGs. Cards
     whose mean-absolute-error (MAE) against the representative is ≤ 3.0 are
     collapsed into one entry; the entry records a `duplicate_count` rather than
     emitting N near-identical variants.

10c. For items classified as **icon sheets** (many small, identically-shaped
   elements arranged in a grid), run
   `scripts/split_icon_sheet.py --item-dir <item>`: it slices the sheet into
   individual icon SVGs (one file per cell) and writes an `icons-manifest.json`
   alongside them. `build_component_catalog.py` renders icon-sheet items as a
   searchable icon grid (single tile per icon) rather than as a long list of
   separate component items. Run after step 10b; skip for non-icon-sheet items.
11. Update extraction history.
12. Rebuild the catalog staging tab and one batch-level `gallery.html`. Compose
    SVG previews from `visual.svg` plus editable HTML text slots. Then serve the
    catalog for review by starting `python3 slide-system/catalog/catalog_server.py`
    in the background (reuse it if already on 8799) and hand the user
    **http://127.0.0.1:8799/slide-system/catalog/**. Do this automatically when
    the batch is built and whenever the user asks to view the preview. Never
    serve with a bare static server or Live Server — the Publish/Delete buttons
    POST to `/api/*`, which only `catalog_server.py` implements (static → 501,
    Live Server → 405).
13. Request approval per item. Author the per-item `preview/` only when an
    approved item is prepared for publish.
