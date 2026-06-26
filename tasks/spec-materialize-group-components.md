# Spec: Materialize decomposed groups as real, publishable components

Status: **DRAFT — awaiting human approval before implementation.**
Author: Claude (session 2026-06-25). Related: `tasks/plan-classify-dedup-merge-rootcause.md`.

## Assumptions (correct me before I proceed)

1. The fix lives **upstream** (at classify/extract time), not as special-case
   code in the publish server. Confirmed by user this session: *"chuyển hẳn nó
   thành component từ lúc extract"*.
2. Each detected group becomes a **real staging item** on disk (own folder +
   `mapping.json` + cropped `artifact/`), so `find_staging` resolves it and
   Publish/Delete work with **zero new server code**.
3. We **reuse `crop_svg_region.py`** for the visual crop + text-slot carve. We
   do **not** write new slot-carving math — it already exists (lines 22-23 of
   that script: re-normalizes every slot into the cropped space, drops slots
   whose center is outside the region).
4. We **reuse the fingerprint formula** from `scaffold_extraction.py`
   (`region_identity_sha256`, `semantic_signature_sha256`) so a materialized
   group is indistinguishable from a normally-scaffolded component and dedup
   keeps working.
5. Group stable id stays `sun.component.<base-slug>.gNN`. This sidesteps the
   `_BANNED_ID` naming gate (group titles are often lorem/numeric) and is
   already accepted by the publish regex fixed earlier today.
6. PDF→SVG remains PyMuPDF-only; no PDF→PNG; the 78 published items and the
   registry are untouched.

## Objective

**What:** After a full-page extraction is decomposed by
`classify_page_components.py`, turn each detected GROUP into a real,
independently-publishable component item — instead of the current *virtual*
`.gNN` catalog card that has no item on disk.

**Why:** Today `build_component_catalog.expand_group_items` projects each group
as a catalog card by shallow-copying the base item and rewriting its id to
`<base>.gNN`. No staging item exists for that id, so Publish → `find_staging`
→ 404 "Draft item not found", and Delete is equally unbacked. The author's own
docstring says per-group publish is *"out of scope here."* This makes every
decomposed page **unpublishable as components** (the base item is also hidden
when groups exist: `return out or [base]`).

**Success looks like:** Clicking Publish on a former group card publishes that
single component (its cropped visual + its carved text-slots) to the library,
exactly like any normal component. No `.gNN`-specific branch in the server.

## Root cause (verified)

| Layer | Finding |
|---|---|
| Registry | 78 published items, **0** with a `.gNN` id. Publish unit = whole staging item. |
| `expand_group_items` (line 198 `item = dict(base)`) | Group card = shallow copy of base, id → `<base>.gNN`, **inherits `publish_readiness: ready`** but **no item on disk**. |
| `find_staging` | Globs `*/items/*/mapping.json`; matches `candidate_stable_id`. No mapping carries `.gNN` → 404. |
| `crop_svg_region.py` | **Already** crops visual + carves/re-normalizes slots by `source.region`, prunes off-canvas images, idempotent. Reusable as-is. |
| `scaffold_extraction.py` | Holds the mapping schema + fingerprint formula to replicate via a shared helper. |

## Plan (implementation order)

### Step A — shared fingerprint helper (tiny refactor, prevents drift)
Extract the 4-line identity-hash logic from `scaffold_extraction.py` into
`_common.py` as `region_identity_hash(source_sha, slide_or_page, region,
object_ids)` and `semantic_signature_hash(intents)`. Repoint scaffold to use
them (no behavior change — same bytes).

### Step B — materialize groups (the core change)
Fold into `classify_page_components.py` (it already has: the base item dir, the
page canvas size, every group's `group_bounds`, titles, tags). After it writes
`components-manifest.json`, for **each group** create a sibling staging item:

1. `region` = `group_bounds` (source units) → normalized page fractions using
   the manifest `canvas` width/height.
2. `items/<base-slug>-gNN/artifact/` ← **copy** the base's full-page
   `visual.svg` + `text-slots.json` (base region is full-page, so these are
   uncropped — the correct input for cropping). Copy `evidence/notes.md` stub.
3. Write `mapping.json`: `candidate_stable_id = sun.component.<base-slug>.gNN`,
   `type=component`, `status=staging`, `source.region` = the normalized region,
   `fingerprints` via Step-A helpers, `semantic_intent` inherited from base +
   group tags, `approval=pending`.
4. Invoke `crop_svg_region` on that item dir (import its crop entry, or
   subprocess) → crops visual + carves slots to the region + prunes images.
5. Re-run `externalize_svg_images` → `optimize_svg` → `apply_text_contract` →
   `validate_text_slots` on the new item (reuse existing batch scripts; same
   sequence the workflow already uses).

Gate with `--materialize-groups` (default **on**) so the behavior is testable
and reversible.

### Step C — catalog builder
Remove `expand_group_items` virtual projection (real items now exist and list
normally as `staging`). The in-item review carousel (whole-row + cards) is
**kept** — it still reads the manifest for side-by-side review.

### Step D — tests (extend `test_gates.py`, no new framework)
- `group_bounds` → normalized region conversion (exact fractions for a known
  canvas + bounds).
- Materialized `mapping.json` has correct `candidate_stable_id`, `region`,
  non-null fingerprints.
- After crop: every surviving slot bound is within `[0,1]` and slot count ≤ the
  base count (carve dropped the outside ones).

### Step E — re-run + verify
Re-run classify on `guideline-fulldeck`, rebuild catalog, restart server,
publish one former group end-to-end (to confirm 404 is gone), then Delete it
to confirm cleanup. Log to session log.

## Commands

```
Test:      python3 slide-system/scripts/test_gates.py
Classify:  python3 slide-system/scripts/classify_page_components.py --item-dir <item> [--materialize-groups]
Crop:      python3 slide-system/scripts/crop_svg_region.py --item-dir <item>
Validate:  python3 slide-system/scripts/validate_text_slots.py --item-dir <item>
Catalog:   python3 slide-system/scripts/build_component_catalog.py
Serve:     python3 slide-system/catalog/catalog_server.py   # http://127.0.0.1:8799/slide-system/catalog/
```

## Files touched

```
slide-system/scripts/_common.py                  → +2 hash helpers (Step A)
slide-system/scripts/scaffold_extraction.py      → use the helpers (no behavior change)
slide-system/scripts/classify_page_components.py → materialize groups (Step B, core)
slide-system/scripts/build_component_catalog.py  → drop expand_group_items projection (Step C)
slide-system/scripts/test_gates.py               → +3 focused tests (Step D)
```
No new files except the materialized staging items (gitignored under `outputs/`).

## Code style
Match the surrounding scripts: stdlib + Pillow only, `_common` helpers,
`raise SystemExit("...")` for user-facing failures, no new dependencies.

## Boundaries
- **Always:** reuse `crop_svg_region` for slot carving; reuse the scaffold
  fingerprint formula; run `test_gates.py` before declaring done; PyMuPDF-only.
- **Ask first:** hiding vs keeping the base page item (see Open Q1); removing
  `expand_group_items`; anything touching the registry / published library.
- **Never:** write new slot-carving math; render PDF→PNG; touch the 78
  published items; commit without explicit approval.

## Success criteria (testable)
1. Publish on a former group id (e.g. `sun.component.feature-step-shape-diagrams.g01`)
   → 200, item appears in `visual-library.json`, artifact copied to library.
2. Delete on that draft removes only its item dir (base + siblings intact).
3. `test_gates.py` green (existing 50 + 3 new).
4. Every materialized item passes `validate_text_slots`.
5. No `.gNN`-specific code path in `catalog_server.py`.

## Decisions (RESOLVED — user approved 2026-06-25)
1. **Base page item:** ✅ **KEEP** it listed/publishable alongside the group
   items (whole-page option preserved for the comparison-table case).
2. **Materialize location:** ✅ **Fold into `classify_page_components.py`**.
3. **Single-member groups (RC-3):** ✅ **Materialize like any other group**
   (region = that single member's bounds); no special branch. The old RC-3
   fragment-reuse logic stays only for the in-item review carousel display.
```
