# Spec: classify_page_components hardening — fix-now bugs

**Status:** ✅ DONE — approved + implemented. BUG-1 fail-loud guard + BUG-2
dropped-small surfacing both shipped; `test_gates.py` 47/47; page-2 output
unchanged (3 groups / 11 cards / icons intact, guard silent, `dropped_small []`).
**Date:** 2026-06-25 · Branch: `feat/harness-enforcement-and-component-recognition`

## Objective
Close the two latent bugs in `classify_page_components.py` that can corrupt
output silently on decks other than page 2:

- **BUG-1 — child-index misalignment.** `_build_fragment` copies a group's
  children by the child index reported by `measure_svg_groups.js`
  (`kids = list(source); kids[ci]`, `classify:446-448`). The only structural
  guard checks **top-level group count** (`classify:299-302`), not per-group
  child count. If Chromium's child enumeration ever differs from
  ElementTree's (skipped/extra nodes), the fragment copies the **wrong**
  children → scrambled/missing component content, with no error. This is the
  same failure family as the icon paint-order bug — it must fail loud.
- **BUG-2 — small components dropped silently.** A cluster below
  `min_area_frac` is discarded with `dropped_small += 1; continue`
  (`classify:~426`). Only a COUNT survives in the manifest. A genuine small
  component (lone icon, badge, logo) vanishes with no trace for review.

**Success = a wrong-child copy can never happen unnoticed, and a dropped small
cluster is always inspectable.**

Who benefits: the extractor agent + the human reviewing the Draft, on any deck.

## Tech Stack
Python 3 (stdlib only), reuses `decompose_svg_objects.measure` (Chromium via
`measure_svg_groups.js`) and `render_svg.js`. No new dependencies (REQUIREMENTS.md).

## Commands
```
Run classify:  python3 slide-system/scripts/classify_page_components.py \
                 --item-dir outputs/component-extractions/guideline-ai-maturity-levels/items/ai-maturity-levels-board
Tests:         python3 slide-system/scripts/test_gates.py
Rebuild catalog: python3 slide-system/scripts/build_component_catalog.py
```

## Project Structure (touched)
```
slide-system/scripts/classify_page_components.py  → the two fixes
slide-system/scripts/test_gates.py                → regression tests (pure-logic)
tasks/spec-classify-hardening.md                  → this spec
docs/logs/SESSION-LOG-2026-06-25.md               → log entry on completion
```

## Code Style
Match the file: small pure helpers, fail-loud `raise SystemExit(...)` for
structural invariants (mirror the existing top-level guard), additive manifest
fields, comments explain the WHY (the bug being prevented). Example (BUG-1):
```python
# Per-group child counts must match too — _build_fragment indexes children by
# the measured child index, so a mismatch means the indices refer to different
# nodes and copying would lift the WRONG children (same failure class as the
# icon paint-order bug). Fail loud, like the top-level count guard.
for gi, (g, mg) in enumerate(zip(groups, measured["groups"])):
    if len(list(g)) != len(mg.get("children", [])):
        raise SystemExit(f"child-count mismatch in {item_dir} group {gi}: "
                         f"parsed {len(list(g))} vs measured {len(mg.get('children', []))}")
```

## Testing Strategy
`test_gates.py` (single-file runner, currently 44/44). Add **pure-logic** tests
(no Chromium): a helper extracted for the guard so it is unit-testable, and a
manifest-shape assertion for the dropped list. Re-run full `test_gates.py`.
Then run classify on the page-2 item and confirm: still 3 groups / 11 cards,
guard does NOT fire, `dropped_small` list present (empty for page 2).

## Boundaries
- **Always:** run `test_gates.py` green before done; keep page-2 output identical
  (3 groups, 11 distinct cards, all icons); additive manifest changes only.
- **Ask first:** changing `min_area_frac` default; making the BUG-1 guard a
  silent fallback instead of fail-loud; touching the extraction/crop steps.
- **Never:** re-run convert/extract (no need); alter the 78 published items;
  commit without explicit ask.

## Success Criteria (testable)
1. Running classify on a synthetic SVG whose measured child count ≠ ET child
   count raises `SystemExit` with a "child-count mismatch" message (unit test).
2. On the real page-2 item: classify still emits 3 groups, 11 distinct cards,
   every icon present; the guard does **not** fire.
3. `components-manifest.json` gains `dropped_small` (list of `{x,y,w,h}` for
   each discarded cluster); `dropped_small_clusters` count still present; main()
   prints a warning line when the list is non-empty.
4. `test_gates.py` green (≥ 46/46 after +2 tests).

## Open Questions
- BUG-1 on a real mismatch: **fail loud** (assumed) vs. **degrade** (fall back to
  copying the whole group)? Fail-loud is safer for correctness but blocks the
  batch; degrade keeps going but may over-include. Recommend fail-loud now.
- Should `dropped_small` also be surfaced in the catalog Draft (a "N small bits
  dropped" note), or is the manifest + stdout warning enough for now? Recommend
  manifest + stdout only this round.

---

## Plan (Phase 2)

Two independent fixes, same file, no ordering dependency; both small.

- **Component A — BUG-1 guard.** Extract a pure helper
  `_child_count_mismatch(groups, measured_groups) -> list[tuple[int,int,int]]`
  returning `(group_index, parsed_count, measured_count)` for any group whose
  ET element-child count ≠ measured child count. In `process_item`, right after
  the existing top-level count guard, call it and `raise SystemExit` if non-empty.
  - Risk: a false positive would block a currently-working deck. Mitigation:
    verified all 20 groups on page 2 already align (ET == measured), so the
    guard is a no-op there; the helper is unit-tested both ways.
- **Component B — BUG-2 surfacing.** In `process_item`, collect dropped clusters
  into a `dropped_small: list[{x,y,w,h}]` (rounded) instead of only counting;
  add it to the manifest alongside `dropped_small_clusters`. In `main()`, print
  a `WARNING: dropped N small cluster(s): ...` line when the list is non-empty.
  - Risk: none structural (additive). Catalog ignores unknown fields.

Verification checkpoints: (1) unit tests pass; (2) classify on page-2 unchanged
output + guard silent + `dropped_small == []`; (3) full `test_gates.py` green.

## Tasks (Phase 3)

- [ ] **T1 — BUG-1 guard helper + wiring.**
  - Acceptance: `_child_count_mismatch` returns offending groups; `process_item`
    raises `SystemExit("child-count mismatch ...")` when any group mismatches,
    immediately after the top-level guard.
  - Verify: unit test `test_child_count_mismatch_detects` (mismatch → non-empty)
    and `test_child_count_mismatch_clean` (aligned → empty).
  - Files: `classify_page_components.py`, `test_gates.py`.
- [ ] **T2 — BUG-2 dropped-small surfacing.**
  - Acceptance: manifest has `dropped_small` list of `{x,y,w,h}`; count field
    retained; `main()` warns when non-empty.
  - Verify: unit test asserting a crafted clusters set yields the expected
    dropped list shape; manual classify run shows `dropped_small: []` on page 2.
  - Files: `classify_page_components.py`, `test_gates.py`.
- [ ] **T3 — Regression run + docs.**
  - Acceptance: `test_gates.py` green (≥46); page-2 classify still 3 groups /
    11 cards / icons intact / guard silent; session-log entry written.
  - Verify: run classify + `test_gates.py`; eyeball manifest counts.
  - Files: `docs/logs/SESSION-LOG-2026-06-25.md`, `docs/logs/INDEX.jsonl`.

## Sign-off
Awaiting human **yes** on: scope (BUG-1 + BUG-2 only), fail-loud for BUG-1,
manifest+stdout for BUG-2. On approval → implement T1→T3.
