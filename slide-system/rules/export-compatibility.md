# Export Compatibility

Each visual item declares support for `html`, `pptx`, `pdf`, and `canva`.
Support values are `supported`, `hybrid`, `raster`, `unsupported`, or
`untested`.

- The text-free `artifact/visual.svg` plus `artifact/text-slots.json` is the
  primary authored visual source. HTML is not authored as a parallel artifact.
- A component extraction is a reusable preview asset, not a finished export. The
  extractor does not emit per-component PPTX/PDF. Export happens in the main job
  that consumes the published component; that job embeds the optimized
  `visual.svg` as an image (SVG-image embed with a raster fallback) and is free
  to overlay editable text from `text-slots.json` if it needs native text.
- Note: SVG→PPTX/PDF rendering needs an SVG renderer (e.g. cairosvg, rsvg, or a
  headless browser). None is currently installed in this environment; choosing
  and provisioning one is a deferred decision recorded for the consuming job.
- Unsupported passive canvas effects use a raster background; unsupported
  element effects use localized raster overlay assets with recorded bounds and
  z-order.
- PDF must be rendered from an approved source and visually checked.
- Accepted renderer failures or fidelity limitations must appear in the final
  report and run manifest.

