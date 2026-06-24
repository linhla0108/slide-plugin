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

### Zombie Items (3 ghost published)
Items marked "published" in extraction-history but NOT in visual-library:
- `sun.asset.guideline-icon-library` — no physical files
- `sun.style.guideline-shape-variants` — no physical files
- `sun.component.guideline-card-variants` — no physical files

Root cause: Old IDs never mapped to new canonical IDs. aliases.json is empty.

### ID Mapping Gap
61 items marked "published" in extraction-history have no matching entry in visual-library. They use old-style IDs (e.g., `sun.cover.cover-hero`) while library uses new canonical IDs (e.g., `sun.sun-presentation.01-cover`).

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

## Fix Applied (2026-06-24 12:04)

### Root Cause
`build_registry.py` had `reconcile_history()` function but only called it for DANGLING items (in registry but folder missing). Ghost-published items completely absent from the registry were never reconciled.

### Fix
Added `reconcile_history(ghosts)` call in `--write` branch to also correct ghost-published items absent from the registry.

### Reconciliation Results
- 63 extraction-history records corrected to `unpublished`
- 5 genuine ghosts (guideline-icon-library, shape-variants, card-variants, board-layouts, image-layouts)
- 58 old-style IDs published under different canonical names
- extraction-history now: 145 published, 97 staging, 9 duplicate, 63 unpublished

### Verification
- `build_registry.py --check` → clean (0 dangling, 0 orphan, 78 valid)
- `test_gates.py` → 17/18 passed (1 pre-existing unrelated failure)
- Zero remaining ghost published items

## State
Changes committed: NO
- `slide-system/scripts/build_registry.py` — added ghost reconciliation
- `slide-system/registries/extraction-history.json` — 63 records marked unpublished
