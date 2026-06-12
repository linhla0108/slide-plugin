# Extract Components

This workflow runs only through the manual component-extractor skill.

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
11. Update extraction history.
12. Rebuild the catalog staging tab and one batch-level `gallery.html`. Compose
    SVG previews from `visual.svg` plus editable HTML text slots.
13. Request approval per item. Author the per-item `preview/` only when an
    approved item is prepared for publish.
