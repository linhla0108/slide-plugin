# Plan — Multi-deck component extraction via per-file subagents

**Goal:** Extract reusable components from 4 PDFs (one subagent per file), then
review every result, root-cause the wrong ones, and fix them.

## Targets

| # | Source PDF | Pages | Size | Deck slug / batch id | Request JSON exists? |
|---|---|---|---|---|---|
| 1 | `SUN.STUDIO_-_Performance_Review_-_2025.pdf` | 20 | 4.7M | `performance-review-2025` | ❌ author it |
| 2 | `SUN.SLIDE.pdf` | 40 | 111M | `sun-slide` | ❌ author it (heaviest) |
| 3 | `Sun.Presentation.pdf` | 17 | 15.4M | `sun-presentation` | ❌ author it |
| 4 | `Salary&Benefits_Sun.Studio_2026_Suner.pdf` | 18 | 27.2M | `salary-benefits-sun-studio-2026-suner-full-pages` | ✅ `input/salary_benefits_sun_studio_2026_suner.extraction-request.json` |

Scope = **full-deck, component-level** (the pipeline default): each page is
inspected, given a semantic `item_id`, converted, cropped, and decomposed into
distinct component classes by `classify_page_components.py`. No full-slide
template promotion unless the user opts in afterward.

## Why a phase split (concurrency safety)

`outputs/component-extractions/<deck>/` is **disjoint per deck → parallel-safe.**
But two pieces of shared state are NOT:

- `slide-system/registries/extraction-history.json` — `scaffold_extraction.py`
  does read-modify-write append; concurrent appends clobber each other.
- `slide-system/catalog/catalog-data.json` — single rewritten dict.

`build_component_catalog.py` rebuilds by **scanning every batch's mapping.json**,
so the catalog must be built **once, by the orchestrator, after all 4 finish** —
never by the subagents. Run mode options (pick one in the kickoff question):

- **A. Parallel + worktree isolation (recommended for speed):** each subagent runs
  in its own `isolation: "worktree"`; no shared-file races at all. Orchestrator
  reconciles afterward (copy 4 batch dirs into main tree, union the
  `extraction-history` attempts, rebuild catalog once).
- **B. Sequential in main tree (zero-risk, slower):** run the 4 subagents one at a
  time; shared appends never overlap. Simplest, ~95 pages end-to-end.

Either way: **subagents stop before the catalog/serve step.** Catalog build +
`catalog_server.py` on :8799 is orchestrator-only.

## Phase A — Extraction (one subagent per deck)

Each subagent owns exactly one PDF and runs the component-extractor pipeline
(`.agents/skills/component-extractor/SKILL.md` → Pipeline). Per-subagent steps:

1. **Preflight (PDF):** `python3 slide-system/scripts/check_base_requirements.py --input pdf`
   — stop on BLOCKER (PyMuPDF missing). Marker `ready` covers base tools only.
2. **Author the extraction-request JSON** (skip for deck #4, already exists):
   inspect each page, assign a **semantic** `item_id` (no `page-N`/`slide-N`/
   positional-only — the scaffold `_BANNED_ID` gate rejects those), full-page
   `region` normalized 0..1, `requested_type: "component"`, real `semantic_intent`.
   Write to `input/<deck-slug>.extraction-request.json`. Mirror the shape of the
   existing salary-benefits request.
3. `scaffold_extraction.py --request input/<deck-slug>.extraction-request.json`
4. Per item, the SVG pipeline in order (PDF path):
   `convert_pdf_source.py` → `extract_editable_text_slots.py` →
   `crop_svg_region.py` → `externalize_svg_images.py` →
   `flatten_svg_background.py` → `externalize_svg_images.py` (refresh) →
   `optimize_svg.py` → `apply_text_contract.py` → `validate_text_slots.py` →
   `classify_page_components.py`. (Batch-capable steps accept `--batch <dir>`.)
5. Write `mapping.json` + lightweight `evidence/notes.md` per item. **Do NOT**
   build the catalog, **do NOT** start `catalog_server.py`, **do NOT** run
   template promotion.
6. Return a manifest: items produced, any per-item validation failures with the
   stage that failed and the script output (verbatim — no invented results).

## Phase B — Orchestrator reconcile + build (me)

1. If run mode A: copy each worktree's `outputs/component-extractions/<deck>/`
   into the main tree; union `extraction-history.json` `attempts` (dedup by id);
   run `build_registry.py` to purge zombie ids.
2. `build_component_catalog.py` once (scans all batches).
3. Start `python3 slide-system/catalog/catalog_server.py` in background (reuse if
   already on 8799). Hand over **http://127.0.0.1:8799/slide-system/catalog/**.

## Phase C — Review + root-cause + fix (the acceptance gate)

For **every** item, check these and log pass/fail to
`docs/logs/SESSION-LOG-2026-06-25.md`:

| Check | How to verify | If it fails → likely stage → fix |
|---|---|---|
| No baked/semantic text in artifact | `visual.svg` has zero `<text>/<tspan>`; `validate_text_slots.py` green | text-slot extraction → re-run `extract_editable_text_slots.py`; never PNG-render a page as the visual |
| Crop = component, not whole slide | `visual.svg` viewBox ≠ full page for component items; catalog Draft shows the component, not the full deck (regression fixed in 76bea2a1) | `crop_svg_region.py` didn't run / bad `source.region` → fix region in mapping, re-crop |
| Text-slot coverage complete | every source string present in `text-slots.json` | extraction missed strings → re-run extract, check `evidence/source-with-text.svg` |
| Component classes are sane | `components-manifest.json`: not one giant class, not N undeduped duplicates (5 colored cards → 1 class ×5) | `classify_page_components.py` clustering/merge → inspect, re-run; needs Chromium |
| No off-canvas / stale rasters | no pruned-image regressions (278d944a); externalize manifests fresh | re-run `externalize_svg_images.py` after flatten |
| Source-vs-artifact match | catalog Draft previews one SVG per class + source region side by side | visual mismatch → trace to the offending stage above |

**Fix loop:** categorize each failure to its pipeline stage (table col 3),
re-run *only* that stage for the affected item, re-validate, rebuild catalog.
Record root cause + fix per item — no guessing; quote script output.

## Acceptance

- 4 batches present under `outputs/component-extractions/`, all items
  `validate_text_slots.py`-green.
- Catalog served on :8799 showing component-level Drafts (not full slides).
- Review log in `docs/logs/SESSION-LOG-2026-06-25.md` listing every item's
  pass/fail and, for each failure, root cause + applied fix.
- No regressions in shared registries (history/catalog rebuilt, no zombies).
