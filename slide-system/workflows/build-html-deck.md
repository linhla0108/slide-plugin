# Build HTML Deck

Build only after approval.

- Use a `1920x1080` `<deck-stage>`.
- Keep slide content as static, editable HTML.
- Keep each text item in a leaf element.
- Use the approved brand pack and published visual-item versions.
- Reference shared assets in place; never copy them per run. Brand fonts,
  icons, and brand images load from the canonical brand-pack location.
- Keep one shared `<job-id>/assets/` folder for job-scoped assets not in a
  brand pack. Every run references that folder; runs never re-copy it.
- Copy an asset into a run only when it is unique to that single run.
- Separate raster assets into base background layers and complex overlay layers.
  Do not bake complex visual elements into the background image.
- Use background-only raster assets only for passive canvas treatments.
- Use independent transparent PNG overlays for complex export-risk elements,
  with recorded bounds, crop, scale, and z-order.
- Keep foreground content editable.
- Verify fonts, images, overflow, navigation, and deterministic capture.
