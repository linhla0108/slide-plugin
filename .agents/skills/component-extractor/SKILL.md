---
name: component-extractor
description: Manually extract exact user-selected slide regions into staged reusable components, sections, templates, styles, icons, backgrounds, characters, or assets with deduplication and review evidence.
---

# Component Extractor

Use only when the user explicitly asks to extract one or more visual regions.

## Required Input

Each requested item must include:

- Source file or folder path.
- Slide or page number.
- Exact region bounds or source object ID.

If any value is missing, ask the user before processing. Do not scan a complete
deck for candidates.

## Required Reading

1. `slide-system/workflows/extract-components.md`
2. `slide-system/rules/extraction-methods.md`
3. `slide-system/rules/editable-text-slots.md`
4. `slide-system/rules/background-rendering.md`
5. `slide-system/rules/naming-versioning.md`
6. `slide-system/workflows/publish-components.md` only after approval.

## Pipeline

1. Validate the extraction request.
2. Fingerprint every requested region.
3. Check extraction history, aliases, and the shared registry for duplicates.
4. Scaffold one staging item per region.
5. Classify the artifact and apply its type-specific extraction method.
6. For each item write `mapping.json` (the canonical record: fingerprints,
   content contract, compatibility, approval) plus a lightweight
   `evidence/notes.md` that references the source raster by path. Put the
   reusable output in `artifact/`. Do not copy source images, and do not emit
   per-item `README.md`/`report.md` — `batch-report.md` is the staging summary.
7. For SVG artifacts, keep the source-with-text SVG in evidence, remove
   semantic text from the reusable visual, and emit normalized editable slots
   according to `editable-text-slots.md`.
8. Build one batch-level `gallery.html` as the single review surface, then
   regenerate the catalog staging tab.
9. Request approval per item.
10. Publish only approved items. At publish, author the per-item `preview/`
   and confirm `evidence/` (publish requires both).

## Boundaries

- Extraction is manual-only.
- A batch may contain multiple exact regions, but every item has independent
  status and approval.
- Complex vector, blur, shadow, glow, mask, filter, blend, and multi-stop
  gradient backgrounds become background-only PNG files.
- Foreground text and semantic content must remain separate and editable.
- Reusable SVGs must not contain semantic `<text>` or `<tspan>` nodes.
