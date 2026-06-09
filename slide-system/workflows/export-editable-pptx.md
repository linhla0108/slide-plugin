# Export Editable PPTX

Priority:

1. Export directly from approved HTML with `gen_pptx`.
2. Extract DOM geometry and generate native PowerPoint objects.
3. Use a manual native generator only as a documented fallback.

Text and primary structure must remain editable. Only passive canvas treatments
may be rasterized as background-only images. Complex visual elements that need
raster export safety must become separate image objects, usually transparent
PNG overlays, with their own bounds and z-order. Never merge those overlays into
the background image unless the approved plan marks them as a single passive
background.

Never describe a full-slide image deck as editable.

Run ZIP, slide-count, exact-content, native-object, font, crop, z-order, and
render-parity checks.
