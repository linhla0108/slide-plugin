# Naming And Versioning

Stable IDs use lowercase dot-separated names:

`<brand-or-core>.<type>.<name>`

Examples:

- `sun.component.metric-card`
- `sun.template.q4-objectives`
- `core.background.soft-grid`

**Group suffix (`.gNN`):** Materialized group items extend the base ID with a
zero-padded two-digit group index:

`sun.component.<base-name>.gNN`

Example: `sun.component.work-environment-image-cards.g01`

The `.gNN` suffix is accepted by `catalog_server.py` `ID_PATTERN` and
`publish_extraction.py`. The base name (`sun.component.<base-name>`) remains
the canonical identity; group items are variants of it.

Use semantic versioning:

- Patch: visual or metadata fix without contract changes.
- Minor: backward-compatible variant or optional field.
- Major: required-field, layout-contract, or behavior change.

Never reuse an ID for a different semantic purpose. A renamed or removed item
is dropped from `visual-library.json` (the single source of truth); stale
extraction-history records for it are purged by `build_registry --write`.

## Display Names

The `name` field in `mapping.json` uses **Title Case** derived from the slug:

```
item_slug.replace("-", " ").title()
```

This is applied by:
- `scaffold_extraction.py` — for all new items at scaffold time.
- `classify_page_components.py` materialize step — for base items and group
  items.

**Group display name format:** when a group has a `title` in the
components-manifest, the display name is:

`"<Base Title> — <Group Title>"`

Example: `"Work Environment Image Cards — Leadership cards"`

When no group title is present, only the base title is used.

