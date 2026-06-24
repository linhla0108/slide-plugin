# Icon Selection

## ABSOLUTE BAN: No Emoji Icons

NEVER use emoji characters (💰📊🎯✅⭐🏨✈📣🛡🎉🤝✨ etc.) as icons in
slides. This is enforced by `validate_brand_compliance.py` — any emoji in the
HTML deck will FAIL the build gate.

## Icon Priority

1. Published shared icon with matching intent and style.
2. One approved external icon family (must be SVG-based, consistent style).
3. Slide-local simple SVG (inline or referenced file).
4. Raster fallback for unsupported vector effects.

Use one icon family per deck unless the approved visual plan explicitly allows
another family. Icons must have semantic labels when meaningful and be marked
decorative when they do not convey information.

