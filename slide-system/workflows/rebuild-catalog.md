# Rebuild Catalog

Run `scripts/build_component_catalog.py` (dev-facing catalog), then
`scripts/build_template_picker_data.py` to refresh the user-facing template
picker data (`template-picker/picker-data.json`) from the published library.

The generated catalog must:

- Separate Published and Staging views.
- Group items by visual type.
- Support search by ID, name, intent, tag, and source.
- Filter by status, brand, type, and export support.
- Show preview, version, source, variants, compatibility, and limitations.
- Never expose staging items to slide-generation selection.

The template picker data must include only `status: published`, `type: template`
items (never read `catalog-data.json`, which normalizes non-template pages into
`template`).
