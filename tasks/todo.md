# TODO — Two independent cleanups ✅ DONE (2026-06-24)

Plan: `tasks/plan.md`. **Export scripts/skills are KEPT** (earlier "remove export" idea cancelled).
Both scopes completed sequentially. Full write-up in `docs/logs/SESSION-LOG-2026-06-24.md` §13–§15.

## SCOPE 1 — Remove `compatibility` field ✅ (commit ec20b6ff)
- [x] **S1-1** Strip `compatibility` block from `visual-library.json` + `visual-library-compact.json` (78 each)
- [x] **S1-2** Remove `compatibility` from 6 code sites: `validate_registry.py`,
      `score_visual_items.py`, `build_registry.py`, `publish_extraction.py`,
      `scaffold_extraction.py`, `test_gates.py`
- [x] **Checkpoint S1** — 0 `compatibility` refs in data+code; gates green; committed

## SCOPE 2 — Unify 3 data sources ✅ (commits a64e43d5, db37667f, 234e846a)
- [x] **S2-1** Purge all attempts of the 63 dead old ids from `extraction-history.json` (195 attempts removed, 119 remain)
- [x] **S2-2** Delete `aliases.json` + remove consumer in `validate_registry.py` + scrub doc refs
- [x] **S2-3** Simplify `build_registry.py`: `purge_history` replaces tombstones; `--check` gates on zombies
- [x] **S2-4** Unified `--check` gate + regression + corrected logs to 10 ghosts / 53 renames
- [x] **Checkpoint S2** — history clean, aliases gone, gates green, logs corrected; committed
- [x] Follow-up: `build_registry.py` writes canonical JSON via `write_json` (234e846a)

## Catalog draft-delete sync (found via browser test, not in original plan) ✅
- [x] **#1** draft delete sweeps ALL staging folders for an id (commit 8f19ea23)
- [x] **#2** draft delete purges the id's non-published history trail (commit 8f19ea23)
- [x] **#3** remove `compatibility` UI from catalog front-end + no-store cache headers (commit 113a12e8)

## Notes
- Verified: 53 renames / 10 ghosts; old ids unreferenced; `aliases.json` consumer = only `validate_registry.py`.
- Out of scope (untouched): all export scripts/skills (KEPT); `input/*.extraction-request.json` (restored in 49a875c2).
- All commits local, not yet pushed.
