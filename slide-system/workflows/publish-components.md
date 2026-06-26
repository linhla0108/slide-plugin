# Publish Components

Publish only approved staging items.

1. Validate the extraction report and visual-item schema.
2. Confirm status is `approved`. The catalog UI writes `approved_by: "catalog-ui"` and `approved_at: <ISO timestamp>` into the staging mapping.json when the user clicks Publish.
3. Assign or verify stable ID and semantic version. Materialized group items (e.g. `sun.component.base.g01`) follow the same flow — the `.gNN` suffix is accepted by the ID pattern in both `catalog_server.py` and `publish_extraction.py`.
4. Copy the artifact into the typed shared library folder.
5. Update the visual registry and aliases. `publish_extraction.py` carries `mapping.get("approval", {})` into the registry entry so the audit trail (`approved_by`, `approved_at`) is preserved in `visual-library.json`.
6. Update extraction history.
7. Rebuild the visual catalog.
8. Remove the staging item. `prune_staging()` deletes the staging item directory and prunes empty parent dirs. Because the staging mapping.json (which held the approval data) is deleted at this point, step 5 must persist the approval data into the registry first.
9. Validate that generation can see the item as `published`.

Rejected and duplicate attempts remain in history but are never selectable.
