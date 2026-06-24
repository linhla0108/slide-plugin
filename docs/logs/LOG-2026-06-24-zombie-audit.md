# Zombie Component Audit — 2026-06-24

## Task
User requested a full check of all resources, components, and their references to ensure no zombie components exist.

## Actions
1. Delegated 3 subagents to check:
   - Physical library assets inventory
   - Component references across entire repo
   - Extraction history and output directories
2. Verified findings with targeted searches (grep, python scripts)
3. Checked aliases.json, visual-library.json, extraction-history.json

## Findings

### Visual Library
- 78 items in visual-library.json — all valid, all have physical files
- Types: 76 templates, 1 asset (logo), 1 character (dio)
- Status: all published

### Extraction History
- 250 total attempts across 16 batches
- 174 unique stable_ids
- Final status **per unique stable_id** (deduped): 139 published, 29 staging, 6 duplicate (sums to 174)
- Raw **attempt-level** status (all 250): 145 published, 96 staging, 9 duplicate
- The large staging gap (96 attempts → 29 unique items) reflects regions scaffolded
  repeatedly — the re-scaffold duplication pattern fixed in `scaffold_extraction.py`
  (duplicate status was driven by history attempts, not the registry).

### Zombie Items
> NOTE: this initial pass under-counted. The fingerprint-verified total is **10
> true ghosts** (not 3) out of **63 dead ids**. See "Corrected Analysis" below.
The 3 first spotted (all with no physical files):
- `sun.asset.guideline-icon-library`
- `sun.style.guideline-shape-variants`
- `sun.component.guideline-card-variants`

Root cause: Old IDs never mapped to new canonical IDs; dead history records left `published`.

### ID Mapping Gap
63 ids marked "published" in extraction-history have no matching entry in visual-library
(53 are renames to canonical IDs, 10 are true ghosts). They use old-style IDs (e.g.,
`sun.cover.cover-hero`) while the library uses canonical IDs (e.g.,
`sun.sun-presentation.01-cover`). See "Corrected Analysis" for the verified split.

### Staging Items (29 never promoted)
- 9 from sunriser-2026-slides-1-5 (early batch, superseded)
- 5 from deepseek-v4-flash (experimental)
- 1 from tutu-optimized (the-blues-brochure)
- 2 from guideline-card attempts (level-progression-cards)
- 5 from second sun-connect batch (conflicting stable_ids)
- 7 others

### Duplicate Items (6 dead ends)
- 2x level-progression-cards
- qr-stack, folio, agenda, divider

### Empty Library Subdirs (5)
- assets/, styles/, backgrounds/, icons/, sections/ — each contains only README.md

### Reference Integrity
- **CORRECTION (2026-06-24):** the original "0 broken references" claim was wrong.
  At audit time, `sun.asset.guideline-icon-library` and
  `sun.style.guideline-shape-variants` were live-referenced in 5 active files
  (`rules/icon-selection.md`, `rules/component-composition.md`,
  `.agents/skills/slide-generator/SKILL.md`, `workflows/build-html-deck.md`, and
  `docs/slide-generator-token-efficiency-plan.md`) — also flagged by the same-day
  DOCS-SKILLS-AUDIT. Those references were removed (asset-removal, not re-extraction).
  The third zombie, `sun.component.guideline-card-variants`, only ever appeared in
  extraction-history metadata, never in active code.
- Post-cleanup: 0 active-code references to any of the 3 zombies (verified by git grep).
- All 78 visual-library items have valid physical paths
- All scripts reference correct registry/schema paths
- No scripts reference the zombie IDs or the empty library subdirs.

## Result
No zombie components that break functionality. Zombies exist only in extraction-history metadata. Active pipeline is healthy.

## Fix Applied — superseded (see Final Fix below)

> The first attempt (commit 43dd659f) appended 63 `unpublished` tombstone records
> and reported "5 genuine ghosts / 58 renames". **Both the counts and the approach
> were wrong** — see the corrected analysis and final fix below.

## Corrected Analysis (fingerprint-verified)

Classification was redone by matching `region_identity_sha256` between each dead
old id's `published` attempt and the live registry ids' `published` attempts:

- **53 RENAMES** — the old id shares an exact region fingerprint with a live
  registry id (same content, republished under the canonical name). Map is 1:1.
- **10 TRUE GHOSTS** — no registry id shares the fingerprint; content is gone:
  `guideline-icon-library`, `guideline-shape-variants`, `guideline-card-variants`,
  `guideline-board-layouts`, `guideline-image-layouts`, `cover-title-connect`,
  `section-header-question`, `slide-5`, `table-of-contents`, `three-column-cards`.

The earlier "5 ghosts / 58 renames" was incorrect.

## Final Fix — purge, not tombstone (2026-06-24)

The registry (`visual-library.json`) is the single source of truth. A history
record for an id that is not in the registry is pure noise, so instead of
tombstoning we **purge** it outright — no `unpublished` record, no alias.

- All 63 dead old ids (53 renames + 10 ghosts) removed entirely from
  extraction-history: **195 attempts purged, 119 remain**
  (76 published, 30 staging, 5 duplicate — every published id now in the registry).
- `aliases.json` deleted (it was empty; old ids are not referenced anywhere) and
  its only consumer in `validate_registry.py` removed.
- `build_registry.py` rewritten: `reconcile_history` (tombstone appender) replaced
  by `purge_history`; `--check` now GATES on zombies (`history_zombie_ids`, exit 1);
  `--write` purges them.

### Verification
- `build_registry.py --check` → `clean: 0 dangling, 0 orphan, 0 zombie, 78 valid items` (exit 0)
- Negative test: inject a published-not-in-registry record → `--check` exit 1 →
  `--write` purges it → `--check` exit 0.
- `test_gates.py` → 18/18 passed. `validate_registry.py` → `Valid registry: 78 items`.
