# Extract Components

This workflow runs only through the manual component-extractor skill.

1. Require exact source path, slide/page, and region/object.
2. Validate batch requests.
3. Fingerprint each region and check for duplicates.
4. Scaffold one output item under `outputs/component-extractions/`.
5. Classify the item and use the extraction method matrix. The reusable visual
   is text-free `artifact/visual.svg` + `artifact/text-slots.json` only; never
   author a parallel `.html`/`.css` for the same region.
6. For SVG-based items, apply `rules/editable-text-slots.md`: preserve
   `evidence/source-with-text.svg`, emit text-free `artifact/visual.svg`, and
   describe every semantic string in `artifact/text-slots.json`.
7. Write `mapping.json` and a lightweight `evidence/notes.md` (referencing the
   source raster by path), and place the reusable output in `artifact/`. Do not
   copy source images or emit per-item README/report files. Do not commit
   `*-svg-manifest.json` audit dumps into `evidence/`.
8. Lift embedded rasters with `scripts/externalize_svg_images.py --batch <dir>`,
   trim path precision with `scripts/optimize_svg.py --batch <dir>`, and fold the
   text contract into each mapping with
   `scripts/apply_text_contract.py --batch <dir>` (no hand-written per-batch
   `_*.py`).
9. Validate content, text-slot coverage, scaling, export support, and source
   comparison with `scripts/validate_text_slots.py`.
10. Update extraction history.
11. Rebuild the catalog staging tab and one batch-level `gallery.html`. Compose
    SVG previews from `visual.svg` plus editable HTML text slots.
12. Request approval per item. Author the per-item `preview/` only when an
    approved item is prepared for publish.
