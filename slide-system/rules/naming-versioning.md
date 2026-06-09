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

Never reuse an ID for a different semantic purpose. Legacy names belong in
`registries/aliases.json`. Replacement and deprecation must retain history.

