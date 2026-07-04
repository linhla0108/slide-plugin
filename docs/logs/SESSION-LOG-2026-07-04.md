# Session Log — 2026-07-04

Branch: `feature/auto-stage-docling-drafts`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` → "Task Logging").

---

## 2026-07-04.1 — Skip chart candidates during auto-detect

**When:** 2026-07-04 18:48
**Request:** Remove chart-like Draft candidates from the component auto-detect output.
**Actions:**
- Removed `chart` from Docling auto-detect candidate labels so new analysis runs do not emit chart candidates by default.
- Added an auto-stage skip guard for legacy `chart-p...` candidates and data-chart text cues such as pie/bar/line/rating-scale chart, while leaving manually requested chart extraction available.
- Updated component extraction docs and user guide to say data charts are skipped by auto-detect.
- Added regression tests for analyzer chart filtering and auto-stage chart skipping.
**Result:** Verification passed: `python -m py_compile slide-system/scripts/analyze_with_docling.py slide-system/scripts/auto_stage_candidates.py slide-system/scripts/test_gates.py`; `python slide-system/scripts/test_gates.py` (112/112); `python slide-system/scripts/validate_registry.py`; `python slide-system/scripts/build_registry.py --check`; `git diff --check`. Current catalog Draft scan found one Draft, `sun.component.ai-adoption-radial-diagram`, with no chart content.
**Files:** .agents/skills/component-extractor/SKILL.md, docs/how-to-use.md, docs/logs/SESSION-LOG-2026-07-04.md, slide-system/rules/extraction-methods.md, slide-system/scripts/analyze_with_docling.py, slide-system/scripts/auto_stage_candidates.py, slide-system/scripts/test_gates.py
**Symbols:** CANDIDATE_LABELS, DATA_CHART_RE, _auto_stage_skip_reason, stage_run, test_analyze_with_docling_skips_chart_candidates, test_auto_stage_skips_chart_candidates_from_existing_analysis
**State:** Not committed

---

## 2026-07-04.2 — Skip duplicate component patterns

**When:** 2026-07-04 18:48
**Request:** Reduce duplicate Draft components where the same visual pattern appears many times with different text.
**Actions:**
- Added duplicate-pattern signatures in `auto_stage_candidates.py` based on source, component role, rounded crop geometry, and text-structure profile; instance notes are excluded so different copy in the same layout does not create a new component pattern.
- Updated `stage_run` to keep the first representative Draft and skip later same-pattern candidates as `skipped_duplicate_pattern`, including when the representative already exists from a previous staging pass.
- Documented the duplicate-pattern skip in the component extractor skill, extraction methods rule, and user guide.
- Added a regression test for two title-card candidates on different pages with the same crop pattern but different text.
**Result:** Verification passed: `python -m py_compile slide-system/scripts/analyze_with_docling.py slide-system/scripts/auto_stage_candidates.py slide-system/scripts/test_gates.py`; `python slide-system/scripts/test_gates.py` (113/113); `python slide-system/scripts/validate_registry.py`; `python slide-system/scripts/build_registry.py --check`; `git diff --check`.
**Files:** .agents/skills/component-extractor/SKILL.md, docs/how-to-use.md, docs/logs/SESSION-LOG-2026-07-04.md, slide-system/rules/extraction-methods.md, slide-system/scripts/auto_stage_candidates.py, slide-system/scripts/test_gates.py
**Symbols:** _pattern_region_bins, _pattern_text_profile, _duplicate_pattern_signature, stage_run, test_auto_stage_skips_duplicate_component_patterns_across_pages
**State:** Not committed

---

## 2026-07-04.3 — Loosen duplicate pattern matching across pages

**When:** 2026-07-04 19:00
**Request:** Reduce remaining duplicate Drafts where visually identical title-card patterns still appeared with different instance text.
**Actions:**
- Changed duplicate signatures in `auto_stage_candidates.py` from exact rounded crop geometry to a coarse layout profile so variable text length does not create separate patterns.
- Normalized `card`, `strip`, and `visual` roles to one component pattern role for cross-page duplicate detection, while preserving same-page neighboring components.
- Updated the duplicate-pattern regression test with variable-width title-card crops and a same-page neighbor that must remain separate.
- Updated component extraction docs to describe the coarse layout duplicate rule.
**Result:** Verification passed: `python slide-system/scripts/test_gates.py` (113/113); `python slide-system/scripts/validate_registry.py`; `python slide-system/scripts/build_registry.py --check`; `git diff --check`. Synthetic smoke in `E:\Temp\slide-plugin-dup-synthetic-20260704-185941` staged 2 candidates and skipped 1 cross-page duplicate as `skipped_duplicate_pattern`.
**Files:** .agents/skills/component-extractor/SKILL.md, docs/logs/SESSION-LOG-2026-07-04.md, slide-system/rules/extraction-methods.md, slide-system/scripts/auto_stage_candidates.py, slide-system/scripts/test_gates.py
**Symbols:** _size_band, _duplicate_pattern_signature, stage_run, test_auto_stage_skips_duplicate_component_patterns_across_pages
**State:** Not committed

---

## 2026-07-04.4 — Split single-row card sets into carousel cells

**When:** 2026-07-04 19:07
**Request:** Fix Draft components that still show only the full grouped component and text-free component instead of smaller card-level components.
**Actions:**
- Added layout-cell clustering in `classify_page_components.py` so a single row of adjacent cards can produce one carousel source/text-free pair per card/cell.
- Kept existing row-level decomposition for multi-row diagrams, but prefer cell-level records when a broad region is a single-row component set.
- Broadened `auto_stage_candidates.py` decomposition routing so broad `component` regions run the classifier, not only `card` and `visual`.
- Updated component extraction docs and user guide to describe row/cell carousel variants.
- Added regression tests for single-row card cell splitting and broad `component` decomposition routing.
**Result:** Verification passed: `python -m py_compile slide-system/scripts/classify_page_components.py slide-system/scripts/auto_stage_candidates.py slide-system/scripts/test_gates.py`; `python slide-system/scripts/test_gates.py` (114/114); `python slide-system/scripts/validate_registry.py`; `python slide-system/scripts/build_registry.py --check`; `git diff --check`.
**Files:** .agents/skills/component-extractor/SKILL.md, docs/how-to-use.md, docs/logs/SESSION-LOG-2026-07-04.md, slide-system/rules/extraction-methods.md, slide-system/scripts/auto_stage_candidates.py, slide-system/scripts/classify_page_components.py, slide-system/scripts/test_gates.py
**Symbols:** _center_x, _cluster_layout_rows_any, _cluster_layout_cells, _slots_by_cells, _build_layout_cell_records, process_item, _decompose_mode, test_layout_cells_split_single_row_cards, test_auto_stage_decomposes_tables_and_broad_visuals_as_layout_rows
**State:** Not committed

---

## 2026-07-04.5 — Require tool readiness before extraction

**When:** 2026-07-04 19:09
**Request:** Add a requirements rule so every component extraction checks tools before running.
**Actions:**
- Added a mandatory tool readiness section to the component extractor skill: run the input-scoped base requirements check before Docling analysis, manual request scaffolding, auto-stage, or artifact generation.
- Updated the extract-components workflow with a step 0 guard that stops on blockers and prevents falling back from Docling to manual extraction until the PDF/PPTX source provider passes.
- Updated `REQUIREMENTS.md` and extraction methods docs to describe the per-extraction check and clarify that Docling is optional but the source provider is not.
- Did not run `check_base_requirements.py` because the task was docs/rule-only and that script may update the readiness marker.
**Result:** Verification passed: docs diff reviewed; `git diff --check`; `python slide-system/scripts/build_log_index.py --write`; `python slide-system/scripts/build_log_index.py --check`.
**Files:** .agents/skills/component-extractor/SKILL.md, REQUIREMENTS.md, docs/logs/SESSION-LOG-2026-07-04.md, slide-system/rules/extraction-methods.md, slide-system/workflows/extract-components.md
**Symbols:** none
**State:** Not committed

---

## 2026-07-04.6 — Run full PDF extraction tester pass

**When:** 2026-07-04 23:59
**Request:** Use tester to component each PDF individually, compare staged Draft output against the source PDFs, fix extraction drift, and repeat until the PR is stable.
**Actions:**
- Ran the input-scoped requirement check in a temporary venv at `E:\Temp\slide-plugin-tester-venv`; system Python lacked the PDF provider, while the venv passed with PyMuPDF installed.
- Re-ran Docling analysis plus auto-stage across all 7 input PDFs into `E:\Temp\slide-plugin-pr1-fulltester-20260704-200940`; all files completed, producing 300 visible Draft items after skips/grouping.
- Audited staged SVGs with a browser/short-path renderer because PyMuPDF cannot resolve relative external image hrefs reliably on grouped carousel SVGs.
- Fixed grouped carousel text-free component SVGs so copied child visuals also copy referenced `artifact/assets` files into the parent Draft artifact and rewrite hrefs from `assets/...` to `../assets/...` where needed.
- Added a regression test for copied component SVG asset href rewriting and a regression test so skipped outputs do not reserve semantic stable IDs.
- Tested an attempted runtime blank/text-free prune, found it made staging time out, then removed it from the `/component` hot path to preserve the existing workflow speed and reliability.
- Re-ran stage-only output for all 7 PDFs into `E:\Temp\slide-plugin-pr1-stageaudit-20260704-232601`; all files completed.
- Ran final visible audit at `E:\Temp\slide-plugin-pr1-stageaudit-20260704-232601\visible-audit\visible-audit-report.json`; no missing SVG asset references and no P1 source crop mismatch remained.
- Scanned changed runtime scripts for source/PDF-specific hardcoding; only test fixtures contain source names such as `GUIDLINE_PRESENTATION_SUN.pdf`.
**Result:** Verification passed: `python -m py_compile slide-system/scripts/auto_stage_candidates.py slide-system/scripts/test_gates.py slide-system/scripts/classify_page_components.py slide-system/scripts/analyze_with_docling.py`; `python slide-system/scripts/test_gates.py` (116/116); `python slide-system/scripts/validate_registry.py`; `python slide-system/scripts/build_registry.py --check`; `git diff --check`. Residual tester findings remain in generated artifacts only: 18 blank manifest refs, 22 blank-or-near-blank text-free SVG variants, and 78 empty component manifests; these are not missing asset refs, but should be handled by a separate bounded post-stage QA/prune pass rather than inline runtime rendering.
**Files:** docs/logs/SESSION-LOG-2026-07-04.md, slide-system/scripts/auto_stage_candidates.py, slide-system/scripts/test_gates.py
**Symbols:** SVG_ASSET_HREF_RE, _copy_svg_with_assets, _materialize_group_item, _existing_stable_ids, test_auto_stage_group_text_free_svg_rewrites_component_asset_refs, test_auto_stage_existing_stable_ids_ignore_skipped_outputs
**State:** Not committed

---

## 2026-07-04.7 — Reject unsafe blank-prune shortcut

**When:** 2026-07-04 23:59
**Request:** Continue the tester loop carefully and avoid hardcoded extraction fixes.
**Actions:**
- Tried a generic visible-area filter in `classify_page_components.py` to drop mostly off-canvas crop residue before carousel grouping.
- Re-ran all 7 existing analysis runs into `E:\Temp\slide-plugin-pr1-stageaudit-visiblefilter-20260704`; all stage runs completed, but browser audit still found 23 blank-or-near-blank SVG refs and 80 empty component manifests.
- Determined the geometry filter did not materially improve blank text-free variants and risked dropping valid materialized child items, so reverted that code/test before final checks.
- Kept the earlier proven asset-href fix and stable-id skip fix intact.
**Result:** Verification passed after revert: `python -m py_compile slide-system/scripts/auto_stage_candidates.py slide-system/scripts/test_gates.py slide-system/scripts/classify_page_components.py slide-system/scripts/analyze_with_docling.py`; `python slide-system/scripts/test_gates.py` (116/116); `python slide-system/scripts/validate_registry.py`; `python slide-system/scripts/build_registry.py --check`. Remaining issue is architectural: blank text-free carousel variants need a bounded post-stage QA/prune step with renderer timeouts/cache, not inline render pruning inside `/component`.
**Files:** docs/logs/SESSION-LOG-2026-07-04.md
**Symbols:** none
**State:** Not committed
