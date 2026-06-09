# Extraction Methods

The reusable visual is a single source of truth: text-free `artifact/visual.svg`
paired with `artifact/text-slots.json`. Do **not** also author a parallel
`.html`/`.css` representation of the same region — the SVG visual plus editable
text slots is the canonical artifact that every downstream surface (gallery
preview, catalog, and the consuming job's export) draws from. The extractor does
not produce per-component PPTX/PDF; the main job embeds `visual.svg` as an image
when it builds a deck (see `export-compatibility.md`).

| Artifact | Primary method | Export-safe fallback |
|---|---|---|
| Card or component | Visual-only SVG + editable text slots | SVG-image embed (raster fallback) in the consuming job |
| Section pattern | Visual-only SVG + editable text slots | SVG-image embed plus safe assets |
| Full-slide template | Visual-only SVG + editable text slots (layout contract, no source copy) | SVG-image embed with editable text overlay |
| Simple style | CSS tokens or safe SVG | Native PowerPoint treatment |
| Simple icon | Clean standalone SVG | Transparent PNG |
| Complex icon | Simplified safe SVG | Transparent PNG |
| Solid or simple background | CSS or native shapes | Safe SVG |
| Passive complex background field | Background-only PNG | PNG |
| Complex foreground or decorative element | Native/SVG when safe | Transparent PNG overlay |
| Blur, shadow, or glow | Native/CSS when safe | Background-only PNG for passive effects; transparent PNG overlay for element effects |
| Mask, filter, or blend mode | Native/SVG when safe | Transparent PNG overlay unless it is purely passive background |
| Blended multi-stop gradient | CSS/native when safe | Background-only PNG for passive fields; transparent PNG overlay for element-local effects |
| Photo or texture | Original raster plus crop metadata | Optimized PNG or JPEG |
| Dio or character | Approved source asset | PNG |

Every reusable item must be independent from one slide's hard-coded text and
coordinates. Store semantic intent, fields, variables, source mapping,
compatibility, limitations, previews, and evidence.

For SVG-based items, follow `editable-text-slots.md`. Source text is evidence;
the reusable visual must be text-free and paired with normalized editable text
slots.
