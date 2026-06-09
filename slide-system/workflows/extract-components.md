# Extract Components

This workflow runs only through the manual component-extractor skill.

1. Require exact source path, slide/page, and region/object.
2. Validate batch requests.
3. Fingerprint each region and check for duplicates.
4. Scaffold one output item under `outputs/component-extractions/`.
5. Classify the item and use the extraction method matrix.
6. For SVG-based items, apply `rules/editable-text-slots.md`: preserve
   `evidence/source-with-text.svg`, emit text-free `artifact/visual.svg`, and
   describe every semantic string in `artifact/text-slots.json`.
7. Write `mapping.json` and a lightweight `evidence/notes.md` (referencing the
   source raster by path), and place the reusable output in `artifact/`. Do not
   copy source images or emit per-item README/report files.
8. Validate content, text-slot coverage, scaling, export support, and source
   comparison with `scripts/validate_text_slots.py`.
9. Update extraction history.
10. Rebuild the catalog staging tab and one batch-level `gallery.html`. Compose
    SVG previews from `visual.svg` plus editable HTML text slots.
11. Request approval per item. Author the per-item `preview/` only when an
    approved item is prepared for publish.
