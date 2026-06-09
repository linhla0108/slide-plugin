# Evidence - Guideline Shape Variants

- Candidate ID: `sun.style.guideline-shape-variants`
- Status: `staging`; approval is pending.
- Source PDF: `/Users/home/Documents/work-space/sun-riser-2026/input/GUIDLINE_PRESENTATION_SUN.pdf`
- Source SHA-256: `db1312220cbc4b42230f23248a9f5e4c398eb23b02a440f1ed6f9a8aaaec5f33`
- Page: `3`
- Exact region: full page, normalized `x=0 y=0 w=1 h=1`.
- Source raster reference: `tmp/pdfs/guideline-presentation-sun/page-3.png`
- Source-faithful vector evidence: `source-with-text.svg`.
- Reusable visual-only vector: `../artifact/visual.svg`.
- Editable text contract: `../artifact/text-slots.json`.

## SVG structure

- Dimensions: `2938.83 x 2623.16`; viewBox `0 0 2938.83 2623.16`; aspect ratio `1.120340`.
- Text mode: `native-text` with `54` text/tspan records.
- Tag counts: `{"clipPath": 12, "defs": 1, "g": 23, "image": 11, "mask": 3, "path": 27, "rect": 3, "svg": 1, "text": 19, "tspan": 35, "use": 3}`.
- References: `29`; warnings: `none`.

## Extraction method

Exact full-page SVG plus semantic CSS contracts for halo, hexagonal formula, and overlapping-circle systems.

The white sheet is recorded as a separate native base-background layer. Editable text and semantic foreground content are not flattened into that layer.

## External image packaging

- Base64 data-image references replaced: `11`.
- Unique external image files: `10`.
- Files are stored under `artifact/assets/` and referenced relatively by `artifact/visual.svg` and `evidence/source-with-text.svg`.
- Geometry, clipping, masks, transforms, and SVG paint order were not changed.

## Editable text slots

- Semantic slots extracted: `35`.
- Source wording is stored as `example_value` for review.
- The reusable SVG contains no semantic text nodes.
- Bounds use normalized 0-1 coordinates and may be edited by callers.
- Overflow is intentionally unmanaged; content is never auto-fitted or truncated.
