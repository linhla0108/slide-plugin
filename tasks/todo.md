# TODO — Two independent cleanups

Plan: `tasks/plan.md`. **Export scripts/skills are KEPT** (earlier "remove export" idea cancelled).
Two scopes are logically independent but share `validate_registry.py` + `build_registry.py`
→ do sequentially, never in parallel.

## SCOPE 1 — Remove `compatibility` field (DO NOW)
- [ ] **S1-1** Strip `compatibility` block from `visual-library.json` + `visual-library-compact.json` (78 each) — *S*
- [ ] **S1-2** Remove `compatibility` from 6 code sites: `validate_registry.py`(45-49),
      `score_visual_items.py`(130-139), `build_registry.py`(49), `publish_extraction.py`(191),
      `scaffold_extraction.py`(170), `test_gates.py`(72) — *S*
- [ ] **Checkpoint S1** — 0 `compatibility` refs in data+code; gates green; commit

## SCOPE 2 — Unify 3 data sources (LATER — delegate to subagent)
- [ ] **S2-1** Purge all attempts of the 63 dead old ids from `extraction-history.json` (originals + tombstones) — *S*
- [ ] **S2-2** Delete `aliases.json` + remove consumer in `validate_registry.py` + scrub doc refs — *S*
- [ ] **S2-3** Simplify `build_registry.py`: purge dead published-not-in-registry, remove tombstone code — *M*
- [ ] **S2-4** Unified `--check` gate + regression + correct logs to 10 ghosts / 53 renames — *S*
- [ ] **Checkpoint S2** — history clean, aliases gone, gates green, logs corrected; commit

## Notes
- Verified: 53 renames / 10 ghosts; old ids unreferenced; `aliases.json` consumer = only `validate_registry.py`.
- Out of scope: all export scripts/skills (KEPT); `input/*.extraction-request.json` deletions.
