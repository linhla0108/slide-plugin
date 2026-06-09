# Export Compatibility

Each visual item declares support for `html`, `pptx`, `pdf`, and `canva`.
Support values are `supported`, `hybrid`, `raster`, `unsupported`, or
`untested`.

- HTML is the primary authored visual source unless the approved workflow says
  otherwise.
- Editable PPTX uses native text and shapes where reliable.
- Unsupported passive canvas effects use a raster background; unsupported
  element effects use localized raster overlay assets with recorded bounds and
  z-order.
- PDF must be rendered from an approved source and visually checked.
- PowerPoint packages must pass ZIP integrity and native-object inspection.
- Accepted renderer failures or fidelity limitations must appear in the final
  report and run manifest.

