# Export Editable PPTX

Run `python3 slide-system/scripts/export_pptx.py` — the single entry point. It
chains capture → build → compose → compare → `validate_export_objects.py` (the
one QA gate) and prints a machine-readable result. Default `--mode layered`
exports the 3-layer model (base picture + each tagged overlay as its own
movable shape + native text, interleaved by captured z-order); `--mode flat`
is the frozen v1 single-background path. Layer membership is declared in the
HTML via `data-export-layer` / `data-export-group` / `data-export-id`
(contract: `slide-system/scripts/_reference/export-manifest.schema.json`).

Pre-flight: a deck built from full-page artwork SVGs must have gone through
`decompose_svg_objects.py` at build time (see `build-html-deck.md`) — the gate
fails untagged visuals AND any single overlay covering ≥85% of the canvas, so
a wholesale-embedded `visual.svg` cannot pass in either form.

Priority:

1. Export through `export_pptx.py` from approved HTML.
2. Extract DOM geometry and generate native PowerPoint objects.
3. Use a manual native generator only as a documented fallback.

Text and primary structure must remain editable. Only passive canvas treatments
may be rasterized as background-only images. Complex visual elements that need
raster export safety must become separate image objects, usually transparent
PNG overlays, with their own bounds and z-order. Never merge those overlays into
the background image unless the approved plan marks them as a single passive
background.

Never describe a full-slide image deck as editable.

The run holds only the exported `.pptx`. Keep any one-off generator script under
`slide-system/scripts/`, not inside the run output.

Run ZIP, slide-count, exact-content, native-object, font, crop, z-order, and
render-parity checks.
