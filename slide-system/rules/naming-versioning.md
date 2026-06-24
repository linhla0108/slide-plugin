# Naming And Versioning

Stable IDs use lowercase dot-separated names:

`<brand-or-core>.<type>.<name>`

Examples:

- `sun.component.metric-card`
- `sun.template.q4-objectives`
- `core.background.soft-grid`

Use semantic versioning:

- Patch: visual or metadata fix without contract changes.
- Minor: backward-compatible variant or optional field.
- Major: required-field, layout-contract, or behavior change.

Never reuse an ID for a different semantic purpose. A renamed or removed item
is dropped from `visual-library.json` (the single source of truth); stale
extraction-history records for it are purged by `build_registry --write`.

