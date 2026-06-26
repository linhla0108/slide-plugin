# HANDOFF — Materialize decomposed groups as real, publishable components

> Self-contained brief for a fresh agent. You do **not** need the chat history.
> Read this top-to-bottom, then `tasks/spec-materialize-group-components.md`
> (the spec) and `tasks/plan-materialize-group-components.md` (the task list).
> All three are committed-intent docs; this one has the exact line anchors,
> reusable signatures, coordinate math, and gotchas.

## 0. Hard constraints (READ FIRST — violating these wastes the work)
- **Do NOT commit or push** unless the user explicitly says so. Nothing in this
  task is committed yet.
- **Do NOT touch the 78 published items** in `slide-system/registries/visual-library.json`
  or `slide-system/library/`. This task only creates **staging** items under
  `outputs/component-extractions/` (gitignored).
- **PDF→SVG is PyMuPDF only** (`convert_pdf_source.py`). Never render a PDF/PPTX
  page to PNG as the visual. Governed by `REQUIREMENTS.md`.
- **Do NOT write new slot-carving / SVG-cropping math.** It already exists in
  `crop_svg_region.py`. Reuse it (subprocess). Writing your own = fabrication.
- **No new dependencies.** stdlib + Pillow only, same as the other scripts.
- **Maintain the session log**: append one entry to
  `docs/logs/SESSION-LOG-<YYYY-MM-DD>.md` when done (rule in `AGENTS.md` → Task
  Logging). Log only what actually happened.
- Extraction-request JSONs are temporary → they must live under
  `outputs/extraction-requests/` (gitignored), **never** in tracked `input/`.
  (A guard in `scaffold_extraction.py` now enforces this.)

## 1. The problem (root cause, verified)
A decomposed page is **one** staging item on disk, but the catalog shows it as N
*virtual* group cards `<base>.gNN` that have **no item on disk**. Publishing one
fails with **"Draft item not found"**.

Chain (all file:line verified):
- `slide-system/scripts/build_component_catalog.py:131` `expand_group_items()`
  does `item = dict(base)` (shallow copy of the base item) then sets
  `item["id"] = f"{base['id']}.g{nn}"`. It inherits the base's
  `publish_readiness: ready` but creates **no** `mapping.json` for that id.
  Called at `:334` and `:367` via `items.extend(expand_group_items(base, item_dir))`.
- `slide-system/catalog/catalog_server.py:80` `find_staging(item_id)` globs
  `outputs/component-extractions/*/items/*/mapping.json` and matches
  `candidate_stable_id` / `id` / folder name. No mapping has a `.gNN` id → returns
  `None` → `action_publish` (`:161`) returns 404 "Draft item not found".
- The base item is **hidden** when groups exist (`expand_group_items` returns
  `out or [base]`, i.e. only the group cards), so a decomposed page currently has
  **no** publishable unit at all.
- `catalog_server.py:38` `ID_PATTERN` was already fixed this session to accept the
  optional `.gNN` suffix: `^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+(\.g\d+)?$`. That fix
  is necessary but NOT sufficient — the missing item on disk is the real cause.

## 2. The fix (one sentence)
Make each detected group a **real staging item** at classify time, so
Publish/Delete work through the existing code with **zero** server changes.

## 3. Reusable pieces (do not reinvent)
- **`slide-system/scripts/crop_svg_region.py`** — `main()` driven by
  `--item-dir` (append, required). Reads `source.region` (0-1) from `mapping.json`,
  crops `artifact/visual.svg` to that window, **re-normalizes every text-slot into
  the cropped space and drops slots whose center is outside the region**, prunes
  off-canvas `<image>`s, idempotent (writes a `region_crop` marker into
  `text-slots.json`'s `source` block). `region_fraction()` at `:202` maps a
  normalized region → source units. **Invoke via subprocess** (don't refactor its
  main); classify already shells out to `render_svg.js`, same pattern.
- **`slide-system/scripts/scaffold_extraction.py:113-122`** — the exact fingerprint
  formula to lift into `_common.py` (Task T1):
  ```python
  identity = {"source_sha256": source_hash, "slide_or_page": str(slide_or_page),
              "region": region, "object_ids": sorted(object_ids)}
  region_hash   = sha256_text(json.dumps(identity, sort_keys=True))
  semantic_hash = sha256_text("|".join(sorted(v.lower() for v in semantic_intent)))
  ```
  Mapping schema to mirror is `scaffold_extraction.py:167-194` (keys:
  `extraction_id, item_id, candidate_stable_id, status, type, category, brand,
  source{path,sha256,slide_or_page,region,object_ids}, fingerprints{
  region_identity_sha256, semantic_signature_sha256, perceptual_hash},
  semantic_intent, content_fields, variables, variants, limitations, approval,
  duplicate_of`). Set `perceptual_hash` to `None`.
- **`_common.py` helpers available**: `load_json`, `write_json`, `now_iso`,
  `sha256_file`, `sha256_text`, `resolve_repo_path`, `normalized_bounds(region)`.
- **`build_component_catalog.main()`** already lists every `items/*/mapping.json`
  with `status` ∈ {staging, qa} (filter at `:279`). So a real group item is listed
  **automatically** once it exists — `expand_group_items` becomes dead code.
- **`catalog_server.py`**: `find_staging` `:80`, `find_all_staging` `:96`,
  `action_publish` `:161`, `action_delete` `:194`. **All work unchanged** for a
  real group item. Do not add `.gNN` branches here.

## 4. Data you get from the manifest (verified shapes)
`artifact/components/components-manifest.json`:
- `canvas`: `{"w": 2938.83…, "h": 2623.16…}` (page size in source units).
- `groups[i]`: keys `group_id, file, shape_class, title, tags, member_count,
  distinct_card_count, group_bounds, member_bounds, cards`.
- `group_bounds`: `{"x":563.1,"y":371.4,"w":1867.5,"h":586.3}` (source units,
  same space as `canvas`).

### Coordinate math for the new item's `source.region` (normalized 0-1)
```
region = {
  "x": gb["x"] / canvas["w"],
  "y": gb["y"] / canvas["h"],
  "width":  gb["w"] / canvas["w"],
  "height": gb["h"] / canvas["h"],
  "unit": "normalized",
}
```
Then `crop_svg_region` does the rest (it converts back to source units via
`region_fraction`). This is why R1 (coordinate mismatch) is low risk: region and
visual share the same source-unit space.

## 5. Implementation steps (full detail in plan doc)
**T1** — Add `region_identity_hash(...)` + `semantic_signature_hash(...)` to
`_common.py` (verbatim formula above); repoint `scaffold_extraction.py`. Byte-for-
byte identical output (regression-test by re-scaffolding a temp request and
diffing `region_identity_sha256`).

**T2** — In `classify_page_components.py` add `--materialize-groups` (default ON).
After the manifest is written, for each group:
1. Compute normalized `region` (§4).
2. `item_id = f"{base_slug}-g{nn}"` (e.g. `feature-step-shape-diagrams-g01`).
   `candidate_stable_id = f"sun.component.{base_slug}.g{nn}"`.
   (`base_slug` = the base item's folder name / `slug(item_id)`.)
3. Create `outputs/.../items/<item_id>/{artifact,evidence}/`. Copy the base's
   full-page `artifact/visual.svg` + `artifact/text-slots.json` into it, and write
   a one-line `evidence/notes.md`.
4. Write `mapping.json` (schema §3): `status="staging"`, `type="component"`,
   `source.region`=region, fingerprints via T1 helpers, `semantic_intent` = base
   intent + `group["tags"]`.
5. `subprocess`: `crop_svg_region.py --item-dir <new>` → then
   `validate_text_slots.py --item-dir <new>`.
6. Once per batch after all groups materialized, run the `--batch` scripts
   (idempotent): `externalize_svg_images.py --batch <batch>` →
   `optimize_svg.py --batch <batch>` → `apply_text_contract.py --batch <batch>`.
   (These take `--batch <dir>`, not `--item-dir`; re-running over the whole batch
   is safe.)
- Single-member groups: **same path**, region = the member's bounds. No branch.

**T3** — `build_component_catalog.py`: replace both
`items.extend(expand_group_items(base, item_dir))` calls (`:334`, `:367`) with
`items.append(base)`; delete `expand_group_items`. Keep the base item's own
`images` carousel (built separately from the manifest). Verify no orphan `.gNN`
ids remain in `catalog-data.json` (every id must map to a real `mapping.json`).

**T4** — Add 3 tests to `slide-system/scripts/test_gates.py` (currently 50):
`test_group_bounds_to_normalized_region`, `test_materialized_mapping_fields`,
`test_carved_slots_within_unit_and_subset`. Target 53/53.

**T5** — Re-run + e2e verify + log (§7).

## 6. Commands
```
Test:        python3 slide-system/scripts/test_gates.py
Classify:    python3 slide-system/scripts/classify_page_components.py --item-dir <item-dir> [--materialize-groups]
Crop:        python3 slide-system/scripts/crop_svg_region.py --item-dir <new-item-dir>
Validate:    python3 slide-system/scripts/validate_text_slots.py --item-dir <new-item-dir>
Batch post:  python3 slide-system/scripts/externalize_svg_images.py --batch <batch-dir>
             python3 slide-system/scripts/optimize_svg.py --batch <batch-dir>
             python3 slide-system/scripts/apply_text_contract.py --batch <batch-dir>
Catalog:     python3 slide-system/scripts/build_component_catalog.py
Serve:       python3 slide-system/catalog/catalog_server.py   # http://127.0.0.1:8799/slide-system/catalog/
```
Test target item dir:
`outputs/component-extractions/guideline-fulldeck/items/feature-step-shape-diagrams`
(has a 3-group manifest; base text-slots.json has 36 slots; page 2938.83×2623.16).

## 7. Verification / e2e
- After T2: `find outputs/component-extractions/guideline-fulldeck/items -name mapping.json | grep -- '-g0'`
  → expect one dir per group; each `validate_text_slots` passes.
- After T3: rebuild catalog; confirm every `.gNN` id in `catalog-data.json`
  resolves to a real `items/*/mapping.json` (no virtual ids).
- Publish e2e (server up): `curl -s -X POST http://127.0.0.1:8799/api/publish
  -H 'Content-Type: application/json' -d '{"id":"sun.component.feature-step-shape-diagrams.g01"}'`
  → expect `{"ok": true, ...}` (was 404). **If you publish for real, the registry
  changes — only do it as the user's explicit test, and Delete it afterward** so
  the 78-item published set is restored. Safer: probe a *non-existent* well-formed
  id to confirm routing, and let the user click Publish in the UI.

### GOTCHA — restarting the catalog server
The server is a long-running process holding port 8799; a code change needs a
restart. **`lsof` can hang in this sandbox** (a `kill`+`lsof` one-liner timed out
at 2 min this session). Use this instead:
```bash
pkill -f catalog_server.py          # stop old
# probe WITHOUT lsof:
python3 - <<'PY'
import socket; s=socket.socket(); s.settimeout(0.5)
try: s.connect(("127.0.0.1",8799)); print("OPEN")
except Exception as e: print("FREE", e)
finally: s.close()
PY
# start fresh in the BACKGROUND (run_in_background), then probe again for OPEN
python3 slide-system/catalog/catalog_server.py
```

## 8. Out of scope (do NOT do — these are fabrication traps)
- No new publish/delete code in `catalog_server.py`.
- No new slot-carving or SVG-crop math (reuse `crop_svg_region`).
- No semantic auto-renaming of groups (keep the `.gNN` id).
- No PDF→PNG; PyMuPDF only.
- No touching the registry / 78 published items / `slide-system/library/`.
- No commit/push without explicit user approval.

## 9. Known residual (note, don't fix unless it bites)
Deleting a materialized group item leaves a stale reference to it in the base
item's `components-manifest.json` (cosmetic — only affects the review carousel).
`find_all_staging` already sweeps all dirs for a given id, so the delete itself is
clean.
