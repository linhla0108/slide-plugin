# Plan: Materialize decomposed groups as real components

Spec: `tasks/spec-materialize-group-components.md` (decisions RESOLVED).
Status: **PLAN — awaiting "ok làm đi" before implementation.**

Decisions locked: keep base item · fold into `classify_page_components.py` ·
materialize single-member groups like any other (no special branch).

## Verified facts the plan relies on
- `crop_svg_region.py` has `main()` driven by `--item-dir`; it crops `visual.svg`
  + carves/re-normalizes `text-slots.json` + prunes off-canvas images, idempotent
  (marker in slots' `source` block). → **invoke via subprocess** (same way
  classify already shells out to `render_svg.js`); no refactor of its `main()`.
- `classify_page_components.py` already computes per-group `group_bounds` and the
  page `canvas` (w/h) and writes `artifact/components/components-manifest.json`.
- `build_component_catalog.main()` lists every `items/*/mapping.json` whose
  `status` ∈ {staging, qa} (line ~279). So once a group is a real item with
  `status=staging`, it is listed **automatically** — `expand_group_items` becomes
  dead code.
- `find_staging` / `find_all_staging` / `action_publish` / `action_delete` need
  **no change** — a materialized group is just another staging item.

## Tasks (ordered by dependency)

- [ ] **T1 — shared hash helpers** (`_common.py`, `scaffold_extraction.py`)
  - Add `region_identity_hash(source_sha, slide_or_page, region, object_ids)` and
    `semantic_signature_hash(intents)` to `_common.py`, lifting the exact byte
    formula from `scaffold_extraction.py:113-122`.
  - Repoint scaffold to call them.
  - Acceptance: scaffold output bytes for an existing item are **identical**
    before/after (same `region_identity_sha256`).
  - Verify: re-scaffold a throwaway request into a temp dir, diff the two
    `region_identity_sha256` values — must match. `python3 test_gates.py` green.
  - Files: `_common.py`, `scaffold_extraction.py`.

- [ ] **T2 — materialize groups in classify** (`classify_page_components.py`)
  - Add `--materialize-groups` (default **on**). After the manifest is written,
    for each group:
    1. `region` = `group_bounds`(source units) ÷ `canvas` w/h → normalized 0-1.
    2. `items/<base-slug>-gNN/{artifact,evidence}/` ← copy base full-page
       `artifact/visual.svg` + `artifact/text-slots.json` + a `notes.md` stub.
    3. Write `mapping.json`: `candidate_stable_id = sun.component.<base-slug>.gNN`,
       `type=component`, `status=staging`, `source.region`=normalized region,
       `fingerprints` via T1 helpers, `semantic_intent` = base intent + group tags.
    4. `subprocess` → `crop_svg_region.py --item-dir <new>` (crop + carve slots).
    5. `subprocess` chain → `externalize_svg_images` → `optimize_svg` →
       `apply_text_contract` → `validate_text_slots` on the new item.
  - Single-member groups: same path (region = that member's bounds). No branch.
  - Acceptance: after a classify run on a decomposed page, each group has a real
    `items/<base-slug>-gNN/mapping.json` (`status=staging`) and a cropped
    `artifact/visual.svg` whose viewBox ≈ group bounds; `validate_text_slots`
    passes for each.
  - Verify: run on `guideline-fulldeck/items/feature-step-shape-diagrams`;
    `find outputs/.../items -name mapping.json | grep -- -g0`; validate each.
  - Files: `classify_page_components.py`.

- [ ] **T3 — drop virtual projection** (`build_component_catalog.py`)
  - Replace `items.extend(expand_group_items(base, item_dir))` (lines ~334, ~367)
    with `items.append(base)`. Delete `expand_group_items` (now dead).
  - Keep the in-item review carousel (the base item's own `images` built from the
    manifest — that code is separate from the projection).
  - Acceptance: catalog lists the base item once **and** each materialized group
    item; **no** synthetic `dict(base)`-with-`.gNN`-id entries remain.
  - Verify: rebuild catalog; in `catalog-data.json` every `.gNN` id resolves to a
    real `items/*/mapping.json` on disk (no orphan virtual ids).
  - Files: `build_component_catalog.py`.

- [ ] **T4 — tests** (`test_gates.py`, no new framework)
  - `test_group_bounds_to_normalized_region`: known canvas+bounds → exact fractions.
  - `test_materialized_mapping_fields`: candidate_stable_id/region/fingerprints set.
  - `test_carved_slots_within_unit_and_subset`: post-crop slots all in [0,1] and
    count ≤ base slot count.
  - Acceptance: 53/53 green.
  - Verify: `python3 slide-system/scripts/test_gates.py`.
  - Files: `test_gates.py`.

- [ ] **T5 — re-run + end-to-end verify + log**
  - Re-run classify on `guideline-fulldeck` (materialize on), rebuild catalog,
    restart server.
  - E2E: POST `/api/publish` a former group id → expect **200** + registry entry;
    then POST `/api/delete` (status=draft) on a *different* group → only its dir
    removed, base + siblings intact. (Do **not** leave a test item published —
    delete what we publish-tested, or publish a throwaway group.)
  - Append a session-log entry.
  - Acceptance: 404 "Draft item not found" is gone for group ids; base untouched;
    78 published items unchanged unless the user approves a real publish.
  - Verify: `curl` the two endpoints; `git status` shows only expected files.
  - Files: session log; regenerated `catalog-data.json` + new staging dirs (ignored).

## Risks / mitigations
- **R1 Coordinate mismatch** (group fragment viewBox vs base page units). Mitigate:
  region is derived from `group_bounds`/`canvas` in the **same** source-unit space
  the base visual uses; `crop_svg_region` already maps normalized region → source
  units (`region_fraction`). Verify on a real group (T2 acceptance).
- **R2 Heavy copies** (full-page visual duplicated per group). Acceptable: staging
  is gitignored; crop prunes off-canvas images so each stays small.
- **R3 Stale manifest references** after a group item is deleted (base manifest
  still lists it). Cosmetic only (carousel) — note it, do not fix unless it bites.
- **R4 Naming gate**: `<base-slug>-gNN` item_id is not positional/numeric → passes
  `_BANNED_ID`; intent inherited (non-generic) → passes intent gate.

## Out of scope (explicitly NOT doing)
- No new server publish/delete code paths.
- No new slot-carving math (reuse `crop_svg_region`).
- No semantic auto-renaming of groups (keep `.gNN`).
- No touching the registry / 78 published items.
- No PDF→PNG; PyMuPDF only.
