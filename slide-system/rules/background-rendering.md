# Background And Raster Layer Rendering

Use raster layers when vectors or CSS effects are likely to change during PPTX
or PDF export. This includes dense vector fields, blur, drop shadows, glows,
masks, filters, blend modes, and blended multi-stop gradients.

Do not merge all export-risk visuals into one slide background image. Split the
slide into explicit layers:

- `base-background`: the passive canvas only, such as solid fills, paper,
  textures, grids, ambient washes, or non-semantic decoration that always sits
  behind the whole slide.
- `complex-overlay`: each complex visual element or semantic visual group that
  must remain raster for export safety, such as complex charts, illustrations,
  decorative motifs, masked images, glow treatments, or shadowed composites.
- `editable-foreground`: editable text and native shapes required by the export
  contract.

Requirements:

- Keep base backgrounds separate from complex overlays.
- Exclude editable text and semantic foreground content from every raster.
- Export complex overlays as independent image objects, normally transparent
  PNG, with their own bounds and z-order.
- Flatten multiple complex elements into one overlay only when they form one
  semantic visual group and share the same z-order.
- Render full-slide base backgrounds at `1920x1080`.
- Render partial backgrounds and complex overlays at their final display pixel
  size.
- Prefer PNG when transparency, gradients, shadows, or vector edges matter.
- Preserve original source or SVG in extraction evidence.
- Store each raster layer's role, bounds, crop, scale, checksum, and intended
  z-order.
- Compose exports in the recorded order: base background, complex overlays,
  editable foreground, then any approved top chrome.

