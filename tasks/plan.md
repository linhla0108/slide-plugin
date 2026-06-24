# Plan: Two independent cleanups — (1) drop `compatibility` field, (2) unify data sources

> ✅ **COMPLETED 2026-06-24.** Both scopes done; see `tasks/todo.md` for the
> commit-by-commit status and `docs/logs/SESSION-LOG-2026-06-24.md` §13–§15 for the
> full write-up. Commits: `ec20b6ff` (Scope 1), `a64e43d5` + `db37667f` + `234e846a`
> (Scope 2), `8f19ea23` + `113a12e8` (catalog draft-delete sync, found via browser test).

**Date:** 2026-06-24 (revised — correct scope)
**Branch:** `feat/harness-enforcement-and-component-recognition`

> **Earlier draft about "removing HTML/PPTX/export scripts & skills" is CANCELLED.**
> That was a misunderstanding. **All export scripts and `.agents` skills stay.**
> The real asks are the two scopes below.

## Are the two scopes independent? (the key question)

**Logically: YES — independent, neither blocks the other**, can be done in any order.
**Physically: they share 2 files** — `validate_registry.py` and `build_registry.py`
(different regions/functions in each). So:

- ✅ Safe to delegate to separate sessions/subagents.
- ⚠️ **Do NOT run them in parallel at the same time** → git conflict risk on those 2 files.
- ✅ Recommended: **Scope 1 first → commit → then Scope 2** from a clean base.

| File | Scope 1 touches | Scope 2 touches |
|------|-----------------|-----------------|
| `validate_registry.py` | compat-target loop (~L45-49) | alias loop (~L25-26, 32, 56-58) |
| `build_registry.py` | `"compatibility"` in projection list (~L49) | tombstone machinery + purge logic |
| everything else | disjoint | disjoint |

---

# SCOPE 1 — Remove the `compatibility` field (DO NOW)

**Goal:** Delete the per-item `compatibility` block (`html`/`pptx`/`pdf`/`canva`) from the
registries and all 6 code sites that read/write it. Keep every export script/skill.

**Verified locations:**
- Data: `visual-library.json` (78 blocks) + `visual-library-compact.json` (78 blocks),
  shape `"compatibility": {"html":..,"pptx":..,"pdf":..,"canva":..}`.
- Code consumers (6): `validate_registry.py:45-49`, `score_visual_items.py:130-139`,
  `build_registry.py:49`, `publish_extraction.py:191`, `scaffold_extraction.py:170`,
  `test_gates.py:72`.

### Task S1-1: Strip `compatibility` from both registries
**Description:** Remove the `compatibility` object from every item in
`visual-library.json` and `visual-library-compact.json` (script the edit to stay exact;
preserve all other fields and formatting).
**Acceptance:**
- [ ] 0 occurrences of `"compatibility"` in either registry.
- [ ] Item count unchanged (78); no other field altered (diff shows only block removals).
**Verify:** `grep -c '"compatibility"'` on both → 0; `git diff --stat` sane.
**Files:** the 2 registry JSONs · **Scope:** S

### Task S1-2: Remove `compatibility` from the 6 code sites
**Description:**
- `validate_registry.py` — delete the `for target in ("html","pptx","pdf","canva")`
  validation loop; drop `VALID_SUPPORT` if now unused.
- `score_visual_items.py` — delete the `required_exports`/`compat`/`incompatible`
  eligibility block (L130-139); items no longer rejected by export support.
- `build_registry.py` — remove `"compatibility"` from the compact-projection field list (L49).
- `publish_extraction.py` — remove `"compatibility": mapping["compatibility"],` (L191).
- `scaffold_extraction.py` — remove the default `"compatibility": {...}` it emits (L170).
- `test_gates.py` — remove `"compatibility": {}` from the fixture (L72).
**Acceptance:**
- [ ] No `*.py` references `compatibility` except historical logs.
- [ ] `test_gates.py` all pass; `validate_registry.py` exits 0; `build_registry.py --check` exits 0.
**Verify:** `git grep -n compatibility -- 'slide-system/scripts/*.py'` → none; run the 3 gates.
**Files:** the 6 scripts above · **Scope:** S

### Checkpoint S1
- [ ] `compatibility` gone from data + code; gates green; export scripts untouched. Commit.

---

# SCOPE 2 — Unify the 3 data sources (LATER — delegate to a subagent)

**Goal:** Make `visual-library.json` the single source of truth; remove dead/zombie
records and aliases. **No tombstones, no new status vocab — delete what's dead.**

**Verified ground truth (fingerprint match on `region_identity_sha256`):**
- **53 renames** (old id republished under a canonical id, exact fingerprint match) +
  **10 true ghosts** (content gone): `guideline-icon-library`, `guideline-shape-variants`,
  `guideline-card-variants`, `guideline-board-layouts`, `guideline-image-layouts`,
  `cover-title-connect`, `section-header-question`, `slide-5`, `table-of-contents`,
  `three-column-cards`. (Prior logs say "5 ghosts / 58 renames" — **wrong**.)
- Old ids are **not functionally referenced** anywhere (only provenance notes + audit docs).
- `aliases.json` real consumer = **only `validate_registry.py`**. (The `aliases` dict in
  `extract_editable_text_slots.py` is an unrelated font-family map.)
- The other agent already appended 63 `unpublished` tombstones today, so each dead old id
  now has BOTH its original `published` attempt AND a tombstone → purge ALL of them.

### Task S2-1: Purge all attempts of the 63 dead old ids from history
Remove every attempt in `extraction-history.json` whose `stable_id` is one of the 63 dead
old ids (originals + today's tombstones). Keep registry ids' history and legitimate
in-progress `staging`/`qa` attempts.
**Acceptance:** 0 history ids `published`-but-absent-from-registry; 0 null-`extraction_id`
tombstones; no registry id loses history. **Verify:** diagnostic + `git diff`. · **Scope:** S

### Task S2-2: Delete `aliases.json` + its consumer
`git rm slide-system/registries/aliases.json`; remove the `--aliases` arg + load + alias
loop from `validate_registry.py` (L25-26, 32, 56-58, the `len(aliases)` print); scrub
`aliases.json` mentions in `rules/naming-versioning.md` and
`docs/flows/slide-generator-workflow.md`.
**Acceptance:** file gone; validator no longer reads it; `git grep aliases.json -- '*.py'`
→ none; `validate_registry.py` exits 0. · **Scope:** S

### Task S2-3: Simplify `build_registry.py` — purge, don't tombstone
Remove tombstone machinery (`reconcile_history` + the other agent's ghost/superseded
additions). `--write` deletes history attempts for ids whose latest status is `published`
but absent from the registry (idempotent). `--check` exits 1 on such drift.
**Acceptance:** no tombstone/superseded/removed code; `--write` idempotent purge;
`--check` exit 1 on injected drift, 0 clean. **Verify:** inject→check→write→check cycle. · **Scope:** M

### Task S2-4: Unified gate + regression + correct logs
`build_registry.py --check` asserts: registry==compact, no dangling, no orphan, no
history-`published` absent. Run full gates. Correct `SESSION-LOG-2026-06-24.md` (Task 11)
and `LOG-2026-06-24-zombie-audit.md` to **10 ghosts / 53 renames** + the purge approach.
**Acceptance:** all gates green; logs corrected; session-log entry added. · **Scope:** S

### Checkpoint S2
- [ ] history clean, aliases gone, gates green, logs corrected. Commit.

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope 1 & 2 edited in parallel → conflict on the 2 shared files | Med | Sequence them (S1 commit → then S2); never run concurrently. |
| Removing `score_visual_items` compat check changes scoring results | Low | Check only ever *rejected* items by export support; removing it can only widen eligibility, never breaks a gate. Covered by `test_gates`. |
| Purging history seen as "rewriting audit log" | Low | User chose delete-not-tombstone; registry stays the authority; only dead ids removed. |

## Out of scope
- All export scripts & `.agents` skills — **kept**.
- The 2 pre-existing `input/*.extraction-request.json` deletions.
