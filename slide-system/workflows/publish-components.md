# Publish Components

Publish only approved staging items.

1. Validate the extraction report and visual-item schema.
2. Confirm status is `approved`. The catalog UI writes `approved_by: "catalog-ui"` and `approved_at: <ISO timestamp>` into the staging mapping.json when the user clicks Publish.
   - For reusable `component` items, `publish_extraction.py` also runs the metadata quality gate (`validate_component_metadata.py`) before any registry or library mutation. A component carrying auto-stage/Docling placeholder text, OCR-noise intent, or empty retrieval fields (`keywords`, `use_cases`, `component_type`, …) is rejected with nothing mutated — author real English retrieval metadata in the Draft first.
3. Assign or verify stable ID and semantic version. Materialized group items (e.g. `sun.component.base.g01`) follow the same flow — the `.gNN` suffix is accepted by the ID pattern in both `catalog_server.py` and `publish_extraction.py`.
4. Copy the artifact into a temporary directory beside the final destination. The temp dir is created at `destination.tmp.<pid>` — the original library destination is never touched during the copy phase.
5. Swap the temp directory into place atomically (`replace_dir_atomically` in `_common.py`): the existing destination is first renamed to a `.backup.<pid>` sibling, then the temp dir is renamed to the destination. If the rename fails, the backup is restored — the destination is never empty or partially written.
6. Update the visual registry, compact projection, and retrieval index using atomic file writes (`write_json_atomic` in `_common.py`): each file is written to a `.tmp.<pid>` sibling, `fsync`ed, then `os.replace`d. A crash during any write leaves the old file intact.
7. Update extraction history (also via `write_json_atomic`).
8. Rebuild the visual catalog.
9. Remove the staging item. `prune_staging()` deletes the staging item directory and prunes empty parent dirs.
10. Validate that generation can see the item as `published`.

**Concurrency**: `catalog_server.py` acquires a filesystem-level mutex (`library_mutation_lock`) before publish or delete, preventing concurrent mutations. The lock directory (`slide-system/.library-mutation.lock.d/`) uses `mkdir`-based atomicity with PID stamping for stale-lock detection. If a lock is held, the API returns HTTP 409.

**Delete safety**: `action_delete` moves the artifact to a `.quarantine.<pid>` sibling before touching the registry or derived projections. If compact or catalog regeneration fails, the artifact is restored and the registry is reverted — the item is never permanently lost by a partial deletion.

**Failure injection**: `test_gates.py` contains 8 dedicated transactional tests covering: new publication, replacement, copy-failure recovery, staging preservation on failure, atomic quarantine delete, rollback restore, path-traversal rejection, and metadata gate preservation.

Rejected and duplicate attempts remain in history but are never selectable.
