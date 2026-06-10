# Evidence — slide-5

- Candidate ID: `sun.template.slide-5`
- Status: `staging`
- Source: `/Users/home/Documents/work-space/sun-riser-2026/input/SUN.SLIDE.pdf` (sha256 `2c5287c583a7240d...`)
- Slide or page: `5`
- Region (normalized 0-1): x=0.0 y=0.0 w=1.0 h=1.0
- Object handles: none

Source raster is referenced by path above, not copied. Add a per-item preview under `preview/` and tighten the region against the source geometry only when advancing this item to publish.

## External image packaging

- Base64 data-image references replaced: `6`.
- Unique external image files: `6`.
- Files are stored under `artifact/assets/` and referenced relatively by the visual and source-evidence SVG files.
- Geometry, clipping, masks, transforms, and SVG paint order were not changed.

## Editable text slots

- Semantic slots extracted: `9`.
- Source wording is stored as `example_value` for review.
- The reusable SVG contains no semantic text nodes.
- Bounds use normalized 0-1 coordinates and may be edited by callers.
- Overflow is intentionally unmanaged; content is never auto-fitted or truncated.
