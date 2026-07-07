# Evidence — improvement-strip

- Candidate ID: `sun.component.improvement-strip`
- Status: `staging`
- Source: `/Users/home/Documents/work-space/sun-riser-2026/input/GUIDLINE_PRESENTATION_SUN.pdf` (sha256 `db1312220cbc4b42...`)
- Slide or page: `5`
- Region (normalized 0-1): x=0.124655 y=0.59531 w=0.325338 h=0.096523
- Object handles: none

Source raster is referenced by path above, not copied. Add a per-item preview under `preview/` and tighten the region against the source geometry only when advancing this item to publish.

## External image packaging

- Shared-asset references across the item's SVG files: `8`.
- Unique external image files: `4`.
- Files are stored once under `artifact/assets/` and referenced relatively by both the visual and source-evidence SVG files.
- Geometry, clipping, masks, transforms, and SVG paint order were not changed.

## Editable text slots

- Semantic slots extracted: `3`.
- Source wording is stored as `example_value` for review.
- The reusable SVG contains no semantic text nodes.
- Bounds use normalized 0-1 coordinates and may be edited by callers.
- Overflow is intentionally unmanaged; content is never auto-fitted or truncated.
