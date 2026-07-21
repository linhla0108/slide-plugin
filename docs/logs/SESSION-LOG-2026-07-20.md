# Session Log — 2026-07-20

Branch: `feature/published-only-retrieval`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` → "Task Logging").

---

## 2026-07-20.1 — Enforce published-only text fallback

**Request:** When no suitable component exists, still generate the slide with approved text only, return component suggestions, and require explicit end-user approval before any new component extraction.
**Actions:**
- Replaced reuse/adapt/custom/blocked score bands with a published-only `reuse` or `text-only` decision contract.
- Raised the canonical semantic reuse safety floor to reject single generic signals, and excluded zero-slot visuals when editable copy is requested.
- Updated selection, brand, and fidelity gates plus slide-generation workflows so text-only is not a local visual/custom component path.
- Added regression coverage for text-only fallbacks, zero-slot candidates, and invalid local-custom actions.
- Ran a real scorer smoke against `docs/intent/ai-workflow-deck-brief.md`; it produced seven reuse decisions and two text-only decisions. A Claude build was stopped after it produced analysis/assets but did not finish PPTX/PDF export.
**Result:** `test_gates.py` passed 176/176; registry, compact projection, and retrieval index checks passed. The scorer and validator accepted the real brief report with one existing missing-content-shape warning.
**Files:** .agents/skills/slide-generator/SKILL.md, docs/flows/component-selection-flow.md, docs/flows/slide-generator-workflow.md, slide-system/schemas/selection-report.schema.json, slide-system/scripts/score_visual_items.py, slide-system/scripts/test_gates.py, slide-system/scripts/validate_brand_compliance.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/validate_selection_report.py, slide-system/workflows/build-html-deck.md, slide-system/workflows/select-visual-items.md
**Symbols:** score_request, MIN_REUSE_SEMANTIC_SCORE, _validate_decision_action, _validate_shape_lock, check_template_assets, check_fidelity
**State:** Not committed

---

## 2026-07-20.4 — Make generation and PDF acceptance enforceable

**Request:** Continue the published-only acceptance loop until a real deck can be tested.
**Actions:**
- Added the missing repository-local `deck_stage.js` starter and changed slide skills/workflow to copy it from `slide-system/boilerplates/` rather than call an unavailable helper.
- Added a gate test for the starter and verified it with `node --check`.
- Fixed `export-pdf.js` to print every requested slide in print layout instead of emitting only the active slide; strengthened `test_export_stack.py` to verify its real PDF page count with PyMuPDF when available.
- Rebuilt the AI workflow acceptance deck and ran its selection, stage, brand, fidelity, PPTX, parity, PDF, and editable-text checks. Cleared a competing orphaned Claude export process before the final clean export.
**Result:** The final run has 1 reuse and 8 text-only decisions, all generation gates pass, the clean PPTX passes export validation/parity, and the clean PDF has 9 pages. Visual review of the rendered text-only slides found no overlapping or clipped text.
**Files:** .agents/skills/make-a-deck/SKILL.md, .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-20.md, slide-system/boilerplates/deck_stage.js, slide-system/scripts/export-pdf.js, slide-system/scripts/test_export_stack.py, slide-system/scripts/test_gates.py, slide-system/workflows/build-html-deck.md
**Symbols:** DeckStage, DeckStage.goTo, export_pptx.generation_gate_commands, export_pdf.main, pdf_pages
**State:** Not committed

---

## 2026-07-20.3 — Block invalid generated decks before export

**Request:** Continue acceptance testing of the published-only generation path.
**Actions:**
- Inspected the interrupted Claude-generated deck and found that it used a hand-rolled static stage and only component markers instead of scaffolded reuse structure.
- Added job-aware pre-export gates in `export_pptx.py`: selection report, deck-stage runtime, brand compliance, and component fidelity run automatically when `analysis/selection-report.json` exists beside the deck.
- Kept standalone HTML exports unchanged when no slide-job analysis folder exists.
- Added an export-gate command construction test and ran the exporter against the invalid acceptance deck.
**Result:** `test_gates.py` passed 178/178 and `test_export_stack.py --json` passed. The real invalid deck was rejected at the deck-stage gate with exit 1 before capture, and no PPTX was written.
**Files:** .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-20.md, slide-system/scripts/export_pptx.py, slide-system/scripts/test_gates.py
**Symbols:** generation_gate_commands, run_generation_gates, export_pptx.main
**State:** Not committed

---

## 2026-07-20.2 — Tighten text-only decision validation

**Request:** Continue the published-only fallback work without allowing self-authored visuals when retrieval has no suitable component.
**Actions:**
- Raised the direct-reuse semantic floor from one generic canonical signal to `MIN_REUSE_SEMANTIC_SCORE = 15.0` and shared that value with the selection validator.
- Required `text-only` reports to use `item_id: null`, `score: 0`, and `extraction_recommended`; added JSON Schema and Python-gate enforcement.
- Re-scored the AI workflow brief after the safety change and verified the report through the selection gate.
**Result:** `test_gates.py` passed 177/177. The real brief report passed selection validation and produced seven reuse decisions plus two text-only fallbacks (`slide-02-ai-per-role`, `slide-04-choose-app`). The Claude acceptance build did not reach PPTX/PDF export before it was stopped for no progress.
**Files:** docs/logs/SESSION-LOG-2026-07-20.md, slide-system/schemas/selection-report.schema.json, slide-system/scripts/score_visual_items.py, slide-system/scripts/test_gates.py, slide-system/scripts/validate_selection_report.py
**Symbols:** MIN_REUSE_SEMANTIC_SCORE, score_request, _validate_decision_action, _validate_single, _validate_slide_entry
**State:** Not committed

---

## 2026-07-20.3 — Fix PDF delivery P0 and request-normalization root cause

**Request:** Act as builder + QA on the published-only worktree: reproduce the confirmed review findings (portrait PDF, non-canonical deliverable, deck-stage print race, prose `intent` diluting the semantic ratio, missing `profile`/`tiers` vocabulary, shape-vs-topic mismatch, absolute semantic floor, thin fidelity/editability observability), fix them, then generate a real deck from `docs/intent/ai-workflow-deck-brief.md` and review the rendered output.

**Actions:**
- `export-pdf.js`: removed `landscape: true` from `page.pdf()`. With an explicit `width`/`height` Chromium applies the orientation *on top of* the paper box and swaps it, printing a 1920x1080 deck as an 810x1440pt portrait sheet. Also pinned each flattened slide to the design canvas (`width`/`height`/`overflow:hidden`), made the stage/body backgrounds transparent (the black band under the last page), and locked the stage transform with `setProperty(..., "important")` so `deck_stage.fit()` cannot re-apply its scale during the print resize.
- `export_pptx.py`: added `--pdf-output`, `pdf_geometry()` (dependency-free page count + MediaBox), `EDITABILITY_TIERS`, a `deliverables` block, a stale-PDF warning, and a `try/except SystemExit` in `main()` so a failing gate still writes `export-result.json` with `pass: false` instead of exiting silently.
- `score_visual_items.py`: added `_semantic_terms()` so intent/tags drop STOPWORDS/short tokens exactly as `_field_tokens` already did for the index side (`_canonicalize` left unchanged — `content_structure` slot names are not prose); added `uncanonical_terms()` to report off-vocabulary `intent` instead of silently scoring it; added `profile`/`tiers`/`icons`/`review` canonicals plus `stats`; made the reuse floor a ratio (`MIN_REUSE_SEMANTIC_RATIO`, `semantic_floor_for()`) so a reweighted profile cannot drift; promoted zero-slot, set-of-N count mismatch and `content_shape` from score penalties to hard eligibility guards; moved `SHAPE_TYPE_MAP` here (validator now imports it) and added a `closing` shape; added `subject_tokens`/`subject_warning` and a `decision.warnings` list; added `--reject-item` to implement the SKILL's documented "reject a defective item and regenerate" loop.
- `validate_selection_report.py`, `selection-report.schema.json`: accept and surface `decision.warnings`; import `SHAPE_TYPE_MAP` from the scorer.
- `validate_component_fidelity.py`: report `coverage` as checked/total (`2/9`) instead of a bare `valid: true`.
- `test_gates.py` (+13 tests) and `test_export_stack.py`: filler symmetry, prose reporting, hard count-fit, subject warning, shape-lock/vocabulary drift, floor-vs-weights, `pdf_geometry`, the two export-pdf source invariants, editability tier, fidelity coverage, `--reject-item`; B1 now asserts the produced PDF is landscape.
- Acceptance run `outputs/slide-jobs/published-only-normalization-20260720/run-03/` from the real brief, with canonical `intent` per the contract and prose moved to `query`. Reviewed the rendered PDF: rejected `sun.interview-workshop-sunriser.02-timeline`, `sun.component.foundation-top1-microsoft-overlap-circle-set`, `sun.sun-studio-performance-review-2025.08-how-level-expectation-card` and `sun.goal-setting-2026.05-process` via `--reject-item` after `read_text_slots.py` showed their slots are fixed line fragments of another deck's copy (`22/05`, `Mar 5 - Mar 12`, `MICROSOFT`, `XIAOMI`) that the approved text cannot replace.
- Deck CSS: added `.text-only.on-dark` (white copy over the dark reused background, per the brand rule) and top padding for `.has-component`, both found by looking at the rendered page, not by a gate.

**Result:** `test_gates.py` 191/191, `test_export_stack.py --json` all PASS (B1 now reports `1440x810pt landscape`), `validate_registry.py`, `build_registry.py --check`, `build_component_retrieval_index.py --check` clean at 91 items, `py_compile` and `node --check` clean. run-03 exports with `pass: true`: PPTX + a single canonical `ai-workflow-deck.pdf` at 9 pages, 1440x810pt landscape, no stale PDF warning. Reuse went 1/9 -> 2/9 (`slide-01` cover, `slide-09` closing — the closing was a real false negative at 14.58 vs the 15.0 floor plus a missing `closing` shape). The other seven stay `text-only`: `slide-02/03/04/05/06/07/08` are genuine library gaps, since every full-slide template carries baked topic-specific copy in fixed-width line slots. No registry, brand asset, or `run-02` artifact was modified.

**Files:** docs/logs/SESSION-LOG-2026-07-20.md, outputs/slide-jobs/published-only-normalization-20260720/run-03/*, slide-system/schemas/selection-report.schema.json, slide-system/scripts/export-pdf.js, slide-system/scripts/export_pptx.py, slide-system/scripts/score_visual_items.py, slide-system/scripts/test_export_stack.py, slide-system/scripts/test_gates.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/validate_selection_report.py
**Symbols:** _semantic_terms, uncanonical_terms, semantic_floor_for, MIN_REUSE_SEMANTIC_RATIO, SHAPE_TYPE_MAP, STRUCTURAL_WORDS, subject_tokens, subject_warning, score_request, main (score_visual_items), pdf_geometry, EDITABILITY_TIERS, _run_export, export_pptx.main, _validate_slide_entry, check_fidelity, pdf_page_size
**State:** Not committed

---

## 2026-07-20.4 — Make published-only reuse safe by construction

**Request:** Fix four confirmed defects so the pipeline auto-reuses a component only when it is content-safe and structurally buildable: (1) `intent` prose still diluted the semantic ratio, (2) wrong-topic artwork shipped with a warning only, (3) acceptance depended on manual `--reject-item`, (4) an ambiguous PDF delivery still passed. Then regenerate the deck without `--reject-item` and review it against a supplied reference deck.

**Actions:**
- Reproduced all four first. `_semantic_terms(["timeline","of","a","real","case"])` returned `{timeline, real, case}` → semantic 11.67 vs 35.0 for the canonical request; the run-03 report auto-selected two `goal-setting-2026` items with warnings only; `rejected_items` was absent from the report; the stale-PDF path only appended a warning.
- Rendered the supplied reference PDF with PyMuPDF (4 portrait screenshot pages) and extracted the reusable *patterns* only — 3-up card set, 4-step chevron flow, 3-column ordinal comparison, tier cards + quota strip, staggered numbered grids, a 3-column matrix, full-bleed CTA. No content, asset, or layout/print mechanism was copied.
- `score_visual_items.py`: replaced `uncanonical_terms` with `normalize_intent()`, which keeps only canonical vocabulary in `intent` and returns the dropped terms as evidence. Corpus membership was tried as an escape hatch and removed — `what` survived it because one item carried that string, which made the guarantee probabilistic. `tags` stay literal, `_canonicalize`/`content_structure` untouched.
- `score_visual_items.py`: replaced advisory `subject_warning` with `topic_conflict()` used as an **eligibility** rule in `safe`. `subject_tokens` now reads the retrieval-index `name` as well as the id, and ignores canonical vocabulary, structural/container/capacity nouns, placeholder markers and digits. A candidate with topic tokens the request never supports is skipped and the runner-up considered; text-only if none survive. Added `decision.evidence` (`scored_intent_terms`, `dropped_intent_terms`, `subject_blocked`).
- `score_visual_items.py`: `--reject-item` documented as diagnostic-only and persisted to `rejected_items` in the scorer-owned report so a rerun is reproducible.
- `export_pptx.py`: added `quarantine_superseded_pdfs()` — PDFs this job previously emitted (tracked in `_export/.pdf-deliverables.json`) move to `<run>/superseded/`; any unrecognised PDF fails the delivery with explicit evidence and is never moved or deleted.
- Schema/validator accept `rejected_items` and `decision.evidence`.
- Added 9 regression tests and reconciled 8 pre-existing fixtures whose ids (`sun.component.trio`, `good-timeline`, `sun.deck.*`, …) read as subject matter under the new, correct rule; `deck`/`template`/`quad`/`slot` etc. were added to `STRUCTURAL_WORDS` as genuine container/capacity words.

**Result:** `test_gates.py` 197/197, `test_export_stack.py --json` all PASS (B1 `1440x810pt landscape`), `validate_registry.py` / `build_registry.py --check` / `build_component_retrieval_index.py --check` clean at 91 items, `py_compile` + `node --check` clean, `git diff --check` clean. Verified `intent=["timeline","of","a","real","case","showing","what"]` now yields byte-identical decision, score, candidate order and criteria to `intent=["timeline"]`, with all six prose terms reported. Verified the delivery gate fails (`pass:false`, exit 1) on a foreign PDF and leaves that file untouched. Fresh run `outputs/slide-jobs/published-only-subject-safe-20260721/run-01/` generated **without `--reject-item`** (`rejected_items: []`): reuse 2/9 → **0/9**, because all 15 previously-selectable candidates are source-specific artwork (`goal-setting`, `interview-workshop`, `salary-benefits`, `performance`, `foundation/microsoft/top1`). PDF: 9 pages, 1440x810pt landscape, one canonical deliverable. Only 1 of 91 published items has no topic tokens, so the library — not retrieval — is now the binding constraint.

**Files:** docs/logs/SESSION-LOG-2026-07-20.md, outputs/slide-jobs/published-only-subject-safe-20260721/run-01/*, slide-system/schemas/selection-report.schema.json, slide-system/scripts/export_pptx.py, slide-system/scripts/score_visual_items.py, slide-system/scripts/test_gates.py, slide-system/scripts/validate_selection_report.py
**Symbols:** normalize_intent, subject_tokens, topic_conflict, subject_safe, score_request, main (score_visual_items), STRUCTURAL_WORDS, PLACEHOLDER_WORDS, quarantine_superseded_pdfs, PDF_HISTORY, SUPERSEDED_DIR, _run_export, DECISION_FIELDS, SINGLE_REPORT_FIELDS, BATCH_REPORT_FIELDS
**State:** Not committed

---
