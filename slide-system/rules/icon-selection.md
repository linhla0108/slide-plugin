# Icon Selection

## ABSOLUTE BAN: No Emoji Icons

NEVER use emoji characters (💰📊🎯✅⭐🏨✈📣🛡🎉🤝✨ etc.) as icons in
slides. This is enforced by `validate_brand_compliance.py` — any emoji in the
HTML deck will FAIL the build gate.

## Icon Priority

1. Brand-pack icon library (`sun.asset.guideline-icon-library` — 10 brand icons).
2. Published shared icon with matching intent and style.
3. One approved external icon family (must be SVG-based, consistent style).
4. Slide-local simple SVG (inline or referenced file).
5. Raster fallback for unsupported vector effects.

Use one icon family per deck unless the approved visual plan explicitly allows
another family. Icons must have semantic labels when meaningful and be marked
decorative when they do not convey information.

## Where to Find Brand Icons

The brand icon library is at:
`slide-system/library/assets/sun.asset.guideline-icon-library/`

Load the `visual.svg` file and extract individual icons by group/id. Each icon
is a self-contained SVG group that can be placed inline or referenced via
`<use>` or `<img>`.

