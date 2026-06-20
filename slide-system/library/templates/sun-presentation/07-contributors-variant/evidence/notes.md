# Evidence — contributors-variant

- Candidate ID: `sun.layout.contributors-variant`
- Status: `staging`
- Source: `/Users/home/Documents/work-space/sun-riser-2026/input/Sun.Presentation.pdf` (sha256 `5776b96b1a266c35...`)
- Slide or page: `7`
- Region (normalized 0-1): x=0.0 y=0.0 w=1.0 h=1.0
- Object handles: none

Source raster is referenced by path above, not copied. Add a per-item preview under `preview/` and tighten the region against the source geometry only when advancing this item to publish.

## External image packaging

- Shared-asset references across the item's SVG files: `18`.
- Unique external image files: `9`.
- Files are stored once under `artifact/assets/` and referenced relatively by both the visual and source-evidence SVG files.
- Geometry, clipping, masks, transforms, and SVG paint order were not changed.

## Editable text slots

- Semantic slots extracted: `13`.
- Source wording is stored as `example_value` for review.
- The reusable SVG contains no semantic text nodes.
- Bounds use normalized 0-1 coordinates and may be edited by callers.
- Overflow is intentionally unmanaged; content is never auto-fitted or truncated.
