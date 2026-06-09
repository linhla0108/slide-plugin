# Editable Text Slots

Reusable vector artifacts must not hard-code semantic text.

## Required Separation

For SVG-based components, sections, styles, and templates:

- Store the source-faithful SVG with native text under
  `evidence/source-with-text.svg`.
- Store the reusable visual-only vector under `artifact/visual.svg`.
- Store editable semantic text under `artifact/text-slots.json`.
- Use the source wording only as `example_value` for review and preview.
- Keep logo and wordmark lettering in the visual only when it is brand artwork.
- Do not OCR lettering that is inseparable from a raster image.

`artifact/visual.svg` must not contain semantic `<text>` or `<tspan>` elements.
Deleting or changing a text slot must never require editing the SVG.

## Text Slot Contract

Each slot records:

- Stable slot ID, semantic role, and recommended HTML tag.
- Editable example content and whether the slot may be empty.
- Normalized `x`, `y`, `width`, and `height` bounds from `0` to `1`. The
  `width`/`height` describe the original glyph extent and are **advisory only** —
  each slot is a single source line. A renderer must expose them as a minimum
  box (e.g. `min-width`), never as a fixed `width`, or the web font will wrap the
  last glyph (`BOARD` → `BOAR` / `D`).
- Anchor, horizontal and vertical alignment, rotation, and z-order.
- Font family, size, weight, style, line height, letter spacing, and color.
- Source text/tspan indices and source character range for audit.
- User-overridable properties, including content, bounds, typography, and color.

Do not auto-fit, truncate, reject, or otherwise modify user content. The user or
calling generator owns font-size and bounds adjustments.

## Review And Export

- Compose review HTML from `visual.svg` plus `text-slots.json`.
- Preview with `example_value` so reviewers can compare against the source.
- Render text as editable HTML or native PPTX objects, never as part of a
  raster fallback.
- Preserve normalized bounds when the component scales.
- Render each slot as a single line that does not auto-wrap (`white-space: pre`),
  so source lines stay intact and only explicit user newlines break.
- Preserve original visual geometry, masks, crops, transforms, and z-order.

