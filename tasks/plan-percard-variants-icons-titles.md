# Plan: Per-card variants + icon fix + content-derived titles (fix/run/test loop)

**Date:** 2026-06-25
**Branch:** `feat/harness-enforcement-and-component-recognition`
**Status:** ✅ DONE — all 3 bugs fixed, `test_gates.py` 41/41, browser-verified.

## Goal (confirmed via interview-me)
Three bugs on top of the proximity-group output:
1. **Titles/tags** were generic ("group 01"). Derive group/card titles + tags
   from the card text the pipeline already captured (`text-slots.json`).
2. **Missing icons** — `g01` extracted Level cards with only card 1's icon;
   cards 2–5 came out blank. Every card must keep its own icon.
3. **Per-card variants** — keep the whole-row variant AND surface each
   visually-distinct individual card; dedup only cards identical in
   icon + color + shape ("giống y hệt thì bỏ qua"). Share one source image.

## Constraints
PyMuPDF-only; reuse existing cluster/shape/fragment + render_svg.js machinery;
don't touch the 78 published items; Draft-only (no publishing). Out of scope:
separate catalog items per card (chose variants-within-group); per-card publish.

## Bug Log
| ID | Symptom | Root cause | Fix | Status |
|----|---------|-----------|-----|--------|
| C1 | g01 Level cards 2–5 render with no icon; banner row showed stray off-canvas images | `_build_fragment` copied source groups in member-traversal order, not document order. The shared icon layer (group 13, painted last in the original) landed early, so later cards' background images painted over their icons | Copy groups in document-index order (`for gi in sorted(by_group)`) so paint order = document order; icon layer paints last | ✅ fixed + verified (all 5 icons render) |
| C2 | Only the whole row was a component; individual cards missing | No per-card extraction step | Pass-1 builds a per-card fragment per member instance; Pass-2 renders each (render_svg.js), hashes pixels, collapses identical (icon+color+shape) via `_collapse_duplicates`, writes `…-group-NN-card-MM.svg`; manifest gains `cards[]` + `distinct_card_count` | ✅ done (5/4/2 distinct cards; dedup proven: identical→same hash) |
| C3 | Titles generic; tags too narrow | Names came from `item_id`, not content | `_load_text_slots` + `_slots_in` + `_heading` (top-2 font tiers, drop body-copy paragraphs, dedup repeats) + `_group_title` + `_tags_from`; written into manifest; catalog uses them | ✅ done (Level + banner rows clean) |
| C4 | Role row titles wrong: TRANSLATOR ok but STRATEGIST/DRIVER/COACH merged into one slot, two cards fell back to body copy | `extract_editable_text_slots.split_runs` only broke on BACKWARD x-jumps (line wraps); the three headings sit on one baseline with large FORWARD x-gaps in a single `<tspan>`, so they never split | Add forward-gap splitting: break when a glyph advance exceeds `max(3×median advance, font_size)`. Regenerated `text-slots.json` surgically from `evidence/source-with-text.svg` (visual.svg untouched), re-ran contract+classify+catalog | ✅ fixed + browser-verified (cards = TRANSLATOR/STRATEGIST/DRIVER/COACH; title joins all four) |

## Known limitations (documented, not bugs)
- 2 inert banner-mask `<image>`s ride along in copied `<defs>` (off-canvas, never
  referenced) — minor pre-existing bloat, not a render bug.

## Acceptance
g01 Draft modal = [Whole row ×5 → each distinct Level card titled from content →
shared source]; every card keeps its icon; identical cards collapse; titles/tags
content-derived; `test_gates.py` green; browser-verified. ✅ all met.
