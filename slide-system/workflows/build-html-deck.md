# Build HTML Deck

Build only after approval.

- Use a `1920x1080` `<deck-stage>`.
- Keep slide content as static, editable HTML.
- Keep each text item in a leaf element.
- Use the approved brand pack and published visual-item versions.
- Copy only required assets into the run.
- Separate raster assets into base background layers and complex overlay layers.
  Do not bake complex visual elements into the background image.
- Use background-only raster assets only for passive canvas treatments.
- Use independent transparent PNG overlays for complex export-risk elements,
  with recorded bounds, crop, scale, and z-order.
- Keep foreground content editable.
- Verify fonts, images, overflow, navigation, and deterministic capture.
