# Build HTML Deck

Build only after approval.

- Use a `1920x1080` `<deck-stage>`.
- Keep slide content as static, editable HTML.
- Keep each text item in a leaf element.
- **Tag every visual object for export** (the layered PPTX export reads these;
  `validate_export_objects.py` FAILS the run when a visible `svg`/`img`/
  `canvas`/`video` carries no tag):
  - `data-export-layer="overlay"` + `data-export-id="<name>"` — each decor,
    chart, illustration, or image that must stay a separate movable object.
  - `data-export-group="<name>"` — gom nhiều element thành 1 overlay semantic.
  - `data-export-native="rect|ellipse"` + `data-export-id` — simple solid
    shapes (cards, bars, dividers) exported as real PPTX autoshapes.
  - `data-export-vector-source="<path.svg>"` — optional, path relative to the
    deck file; enables true-vector svgBlip when the element has no CSS effects.
  - `data-export-skip` — text that must stay baked in raster (gradient text…).
  - Passive full-slide canvas (gradient/texture on the slide root) needs no
    tag — it is the base layer by definition.
  - **One tag = one movable object.** Wrapping a full-page artwork SVG in a
    single overlay tag is NOT separation — every card/arrow/icon inside stays
    glued into one picture. The validator FAILS any overlay covering ≥ 85% of
    the canvas (`overlay_coverage.max_ratio` in
    `registries/export-qa-thresholds.json`).
- **Full-page artwork SVG (extraction `visual.svg`) MUST go through the
  decomposer — do not hand-split and do not embed it wholesale:**
  ```
  python3 slide-system/scripts/decompose_svg_objects.py \
      --svg <item>/artifact/visual.svg \
      --out-dir <job>/assets/page-NN --prefix page-NN \
      --href-base <path from deck.html to that out-dir>
  ```
  It measures every source group in Chromium, clusters them into movable
  objects, writes per-object fragment SVGs + `snippet.html` (tagged,
  absolutely-positioned divs — paste inside the slide div) and
  `decompose-manifest.json`. Then:
  - `base_candidates` / WARN lines = full-bleed artwork → set it as the
    slide's CSS `background-image`, never as a tagged overlay.
  - Review object ids; rename to semantic names when it helps editing.
  - If two emitted objects are really one design piece, merge their divs
    (union bbox) — never the reverse (re-gluing many pieces into one tag).
- Use the approved brand pack and published visual-item versions.
- Reference shared assets in place; never copy them per run. Brand fonts,
  icons, and brand images load from the canonical brand-pack location.
- Use canonical, self-contained, resolvable font and asset paths; do not depend
  on removed prototype folders or external workspace paths.
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
