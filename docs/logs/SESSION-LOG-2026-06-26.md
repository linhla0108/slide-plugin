# Session Log — 2026-06-26

Branch: `feat/harness-enforcement-and-component-recognition`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` -> "Task Logging").

---

## 2026-06-26.1 — Fix brand font (Proxima Nova) not rendering in catalog preview & draft views

**Request:** User noticed components in preview and draft views were not applying the brand guideline font (Proxima Nova).

**Investigation:**
- Traced font rendering pipeline across catalog.js and catalog.css
- Mapped all 8 SVG rendering sites in catalog (component tiles, modal carousel, icon set, template viewer stage/filmstrip/cards)
- Identified 4 root causes

**Root causes found:**
1. **CSS syntax bug** (catalog.js L32): `BRAND_FONT_CSS` template produced `url(...)format(...)` with no space before `format()` — invalid CSS, all 8 @font-face rules silently rejected by browser. Font injection into `<object>` SVGs was structurally correct but injected broken CSS.
2. **Draft tile previews use `<img>`** (catalog.js L331): Draft/staging items only have SVGs (no PNG thumbnails). `<img>` fully sandboxes SVGs — no font injection possible.
3. **Template viewer never injects fonts** (catalog.js L1139/1253/1309/1365): All template viewer functions always use `<img>`, no SVG detection or font injection. Latent bug (all template slides currently have PNGs).
4. **Catalog UI font relies on system font** (catalog.css L40): `--font: "Proxima Nova"` had no matching @font-face under unified family name. Only PostScript names were registered.

**Changes:**
- `slide-system/catalog/catalog.js`:
  - Fixed missing space in BRAND_FONT_CSS template (`) format("opentype")`)
  - Extended BRAND_FONT_CSS with unified "Proxima Nova" family entries (weight/style descriptors)
  - Added `isSvgPath()` helper for SVG URL detection
  - Updated `compCreateTile` to use `<object>` + font injection for SVG tiles
  - Updated `tplRenderStageImage`, `tplRenderFilmstrip`, `tplBuildCard`, `tplBuildSetCard` with SVG detection and `<object>` + font injection
- `slide-system/catalog/catalog.css`:
  - Added 9 unified "Proxima Nova" @font-face declarations (weight 400-900)
  - Extended `.tile-preview` rules to cover `<object>` elements with `pointer-events: none`
  - Extended `.stage-frame` rules to cover `<object>` elements

**Verification:**
- JS parses without errors (`node --check`)
- All 9 font OTF files return HTTP 200 from catalog server
- Updated CSS/JS files served correctly
- Browser verification not possible (Playwright MCP disconnected) — manual browser check needed

**Result:** Not committed. Needs manual browser verification at http://127.0.0.1:8799/slide-system/catalog/

---

## 2026-06-26.2 — Investigate .gNN Draft items in catalog

**Request:** User asked why `.gNN` draft items still appear in catalog after previous fix.
**Actions:**
- Verified `expand_group_items` already removed from `build_component_catalog.py`
- Confirmed 5 materialized `.gNN` items exist on disk under `guideline-resplit-staging/items/` with real `mapping.json` files
- Confirmed `find_staging` resolves them, `ID_PATTERN` accepts `.gNN`, `publish_readiness` shows ready
- Conclusion: the "Draft" tag is correct behavior — `status=staging` items display as Draft; they are real items awaiting publish, not virtual/broken cards
**Result:** No code change needed. Items are functional and publishable.
**Files:** none
**Symbols:** none
**State:** Not committed

---

## 2026-06-26.3 — Remove delete confirmation popup from catalog

**Request:** User did not request the confirm dialog feature and wants it removed — delete should fire immediately.
**Actions:**
- Simplified `compOnDelete` in `catalog.js` to call API directly without `compConfirmDialog`
- Deleted `compConfirmDialog` function (~50 lines JS)
- Removed orphaned `.confirm-overlay` guard in keyboard handler
- Deleted all confirm dialog CSS (~120 lines: `.confirm-overlay`, `.confirm-box`, `.confirm-title`, `.confirm-body`, `.confirm-type`, `.confirm-type-input`, `.confirm-actions`, `.confirm-cancel`, `.confirm-ok`)
**Result:** Delete button now fires immediately. No popup.
**Files:** slide-system/catalog/catalog.js, slide-system/catalog/catalog.css
**Symbols:** compOnDelete, compConfirmDialog
**State:** Not committed

---

## 2026-06-26.4 — Add karpathy-guidelines to CLAUDE.md

**Request:** User asked to add karpathy-guidelines skill reference to project CLAUDE.md so it is invoked automatically.
**Actions:**
- Added "Karpathy Guidelines (always active)" section at top of `.claude/CLAUDE.md` referencing `/karpathy-guidelines`
**Result:** Skill will be referenced in all future sessions for this repo.
**Files:** .claude/CLAUDE.md
**Symbols:** none
**State:** Not committed

---

## 2026-06-26.5 — Align published tile preview with draft (source-with-text.svg first, not thumbnail.png)

**Request:** Published components show `thumbnail.png` as tile preview while draft shows `source-with-text.svg` — user wants them to look identical. Additionally, 3 published components (brand-icon-reference-sheet, feature-step-shape-diagrams, style-card-sampler-board) had offset thumbnails because full-page PDF canvas content wasn't centered and CSS `object-fit: cover` with `aspect-ratio: 16/9` crops symmetrically.

**Root cause:**
- `build_component_catalog.py` L191-196: published fallback order put `thumbnail.png` first, while draft's `collect_images()` put `source-with-text.svg` first.
- Offset thumbnail issue is a consequence of using PNG (fixed-canvas raster) instead of SVG (viewBox scales properly).

**Changes:**
- `slide-system/scripts/build_component_catalog.py`: reordered published fallback `preview_candidates` to put `source-with-text.svg` first, then `thumbnail.png`, `reference.png`, `visual.svg` — matching draft behavior.
- Rebuilt `catalog-data.json` (85 items).

**Verification:**
- All 3 affected components now show `source-with-text.svg` as `images[0]`
- All 76 published templates also now show `source-with-text.svg` first
- Draft items unchanged (already showed SVG first)
- Combined with font fix (2026-06-26.1), SVG tiles now render with `<object>` + Proxima Nova font injection

**Result:** Not committed. Published and draft tile previews now use the same image source. Offset thumbnail issue is moot for tiles (SVG used instead).

**Backfill:** Also added missing entry 2026-06-25.15 (publication of 3 GUIDLINE components) to the June 25 session log.

---

## 2026-06-26.6 — Fix thumbnail generation clipping (render_svg.js viewport vs intrinsic size)

**Request:** User noticed "Preview" thumbnails of published components are cropped — asked if it's a generation bug.

**Root cause:**
- `render_svg.js` opens SVG as a standalone page with viewport sized to the target dimensions (e.g. 1600×1428)
- SVGs from `convert_pdf_source.py` have explicit `width="2938.83" height="2623.16"` attributes — the browser renders at intrinsic size (2938×2623), not scaled to the viewport
- The screenshot `clip: {x:0, y:0, width:1600, height:1428}` captures only the top-left ~54%, cutting off content in the bottom and right portions

**Changes:**
- `slide-system/scripts/render_svg.js`: after navigation, evaluate JS to set SVG root `width="100%"` and `height="100%"` — forces the viewBox to scale the SVG content to fit the viewport instead of overflowing it. Safe for smaller SVGs (viewport already matches intrinsic size, scale ≈ 1.0).
- Regenerated `preview/thumbnail.png` for all 3 published components via direct `render_svg.js` invocation (published items lack `mapping.json` needed by `generate_item_preview.py`).

**Verification:**
- All 3 thumbnails now have content across full image (bottom 100px and right 100px verified non-empty via PIL getbbox)
- `test_gates.py` **57/57** pass
- No impact on existing fragment/icon rendering (intrinsic size ≤ viewport → scale unchanged)

**Result:** Not committed. Thumbnails correctly capture full SVG content. The "Preview" carousel image now matches the "Source with text" SVG.

---

## 2026-06-26.7 — Re-extract guideline-resplit-staging batch (4 items) with pipeline fixes

**Request:** User asked to re-extract the 4 staging draft items from `guideline-resplit-staging`. Multiple bugs had been found in prior sessions: region_crop marker causing skipped crops on materialized groups, validate_text_slots failing on materialized groups, naming not flowing from manifest to catalog.

**Bugs fixed (code changes from earlier in this session):**
1. `classify_page_components.py`: clear `region_crop` marker from copied text-slots.json before running crop on materialized groups
2. `classify_page_components.py`: removed `validate_text_slots` call for materialized groups (evidence SVG has parent's full text, slots cover only sub-region → false unmapped-text errors)
3. `classify_page_components.py`: added name/tags from components-manifest.json to materialized group mapping.json, using Title Case format (`base_slug.replace("-", " ").title()`)
4. `scaffold_extraction.py`: added `"name": item_slug.replace("-", " ").title()` to mapping dict so parent items also get Title Case names

**Actions:**
- Deleted old `outputs/component-extractions/guideline-resplit-staging/`
- Re-scaffolded from `outputs/extraction-requests/guideline-resplit-staging.json` (4 items, correct regions from session 2026-06-25.5)
- Ran full pipeline: convert_pdf_source → extract_editable_text_slots → crop_svg_region → externalize_svg_images → flatten_svg_background → externalize (refresh) → optimize_svg → apply_text_contract → validate_text_slots → classify_page_components
- All 4 items validated successfully
- Classify produced: goal-setting-checklist-table (0 groups), ai-adoption-radial-diagram (2 groups), work-environment-image-cards (2 groups), team-contributor-circles (1 group)
- Rebuilt catalog: 90 items total
- All staging items show Title Case names matching published convention

**Catalog items (staging):**
- Goal Setting Checklist Table
- Ai Adoption Radial Diagram + 2 groups (XÂY cards)
- Work Environment Image Cards + 2 groups (Leadership cards, Rewards & Recognition / Engagement)
- Team Contributor Circles + 1 group

**Files:** scaffold_extraction.py, classify_page_components.py (changes from earlier), outputs/component-extractions/guideline-resplit-staging/ (regenerated)
**State:** Not committed

---

## 2026-06-26.8 — Fix component fragmentation: dedup same shape-class + hide decomposed parents

**Request:** User noticed materialized group items fragmented across catalog — same component appearing multiple times (e.g. `ai-adoption-radial-diagram-g01` AND `g02` both shape-class 1), plus parent items showing alongside their groups.

**Root causes:**
1. `materialize_groups()` created one item per proximity run, even when multiple runs had the same shape_class (same component at different positions)
2. Parent items with groups still appeared in catalog as separate entries (parent is a section, not a standalone component)

**Changes:**
- `slide-system/scripts/classify_page_components.py`:
  - Added shape_class dedup in `materialize_groups()`: only first representative per shape_class gets materialized
  - After materializing, writes `"decomposed_into"` marker to parent mapping.json
- `slide-system/scripts/build_component_catalog.py`:
  - Skips staging items with `"decomposed_into"` in their mapping

**Result:** ai-adoption-radial-diagram went from 3 catalog entries (parent + g01 + g02) to 1 (g01 only). Total staging items: 9 → 5. Published items: 81 (unchanged).

**Verification:**
- Catalog rebuilt: 86 items (81 published + 5 staging)
- No parent+group duplicates
- No same-shape-class duplicates
- All staging items have Title Case names

**Catalog staging items (final):**
1. Goal Setting Checklist Table
2. Ai Adoption Radial Diagram — XÂY cards
3. Work Environment Image Cards — Leadership cards
4. Work Environment Image Cards — Rewards & Recognition / Engagement
5. Team Contributor Circles

**State:** Committed (b2c7e69d)

---

## 2026-06-26.9 — Restore per-card variant carousel in materialized group drafts

**Request:** User noticed draft items only show 1 preview image. The per-card variant carousel (whole row → per-card variants → source) was lost when `expand_group_items` was replaced by `materialize_groups` in session 2026-06-25.5.

**Root cause:** `materialize_groups()` copied `visual.svg` + `text-slots.json` but NOT the component fragment SVGs and per-card variant SVGs from the parent's `artifact/components/`. Without a `components-manifest.json` in the materialized item, `collect_images()` fell through to the generic path and only found `source-with-text.svg`.

**Changes:**
- `slide-system/scripts/classify_page_components.py` — `materialize_groups()`: copies group fragment SVG + per-card variant SVGs into materialized item's `artifact/components/`, writes scoped `components-manifest.json`
- `slide-system/scripts/build_component_catalog.py` — `collect_images()`: added per-card variant loop from manifest `cards[]`, uses `title` field for labels

**Verification:**
- work-environment-image-cards-g02: 4 images [Rewards & Recognition / Engagement (×2), Rewards & Recognition, Engagement, Source]
- team-contributor-circles-g01: 3 images [Group 01 (×3), Card 01 (×3), Source]
- Single-member groups: 2 images [group fragment, Source]
- goal-setting-checklist-table (no groups): 1 image [Source with text]

**State:** Committed (ae7818a7)

---

## 2026-06-26.10 — Coverage guard + approval audit trail in publish

**Request:** (1) ai-adoption-radial-diagram incorrectly decomposed into tiny diamond-shape fragments. (2) 3 user-published items had no audit trail — `publish_extraction.py` dropped `approval` metadata from the registry entry.

**Root causes:**
1. `materialize_groups()` created group items even when groups cover <10% of parent canvas (sub-elements of a unified diagram, not standalone components)
2. `catalog_server.py` writes `approved_by`/`approved_at` into `mapping.json`, but `publish_extraction.py` never carried `mapping.approval` into the registry entry. Then `prune_staging()` deletes the mapping — approval metadata lost forever.

**Changes:**
- `slide-system/scripts/classify_page_components.py`: added coverage guard — skip materialization when deduped groups cover <10% of canvas
- `slide-system/scripts/publish_extraction.py`: carry `mapping.approval` into registry entry
- Re-published 3 items user had manually published via catalog API
- Restored LFS PDF file (`git lfs pull`)

**Verification:**
- ai-adoption-radial-diagram: 0 materialized groups (coverage ~5% < 10% threshold), stays as full diagram
- Registry entries now carry `approval: {status, approved_by: "catalog-ui", approved_at}`
- Catalog: Published 8, Draft 2

**State:** Committed (e4094b7d)

---

## 2026-06-26.11 — Update docs and flow diagrams for new features

**Request:** User noted docs and flow simulations were not updated after adding new features. Audited all doc files against session logs 2026-06-25 and 2026-06-26.

**Audit findings:** 1 critical stale doc (catalog-publish still described deleted confirm dialog), 4 high-impact gaps (extract-components, naming-versioning, publish-components, skill-flows missing materialize/dedup/coverage/approval features).

**Changes (5 files):**
- `docs/flows/catalog-publish.md`: removed confirm dialog references, added `.gNN` ID support, approval audit trail note, tile preview order fix, brand font injection
- `docs/flows/skill-flows.md`: added steps i (classify_page_components + materialize_groups) and j (split_icon_sheet), approval audit trail in publish gate
- `slide-system/workflows/extract-components.md`: added gutter split, pipeline hardening guards, full materialize_groups block (shape-class dedup, coverage guard, staging layout, decomposed_into, per-card carousel, perceptual dedup), step 10c for split_icon_sheet
- `slide-system/rules/naming-versioning.md`: added `.gNN` group suffix pattern, Title Case display names section
- `slide-system/workflows/publish-components.md`: added approval metadata write, `.gNN` support, prune_staging step with audit trail note

**State:** Not committed

---

## 2026-06-26.12 — Docling analysis layer + registry/threshold/export drift fixes

**Request:** On `feature/docling-analysis-pipeline`, add an optional Docling-assisted candidate-detection layer while stabilizing current registry/docs/script drift: `.gNN` ID validation, visual-selection thresholds, stale `export_pptx.py` CLI examples, published-library flat paths, host-aware capabilities, and non-technical docs.

**Changes:**
- `slide-system/scripts/validate_registry.py` + `slide-system/schemas/visual-item.schema.json`: accept optional `.gNN` group suffix in IDs (`^…(\.g[0-9]+)?$`); negative cases (`sun.a.b.c`, `.g`, `.gab`, uppercase) still rejected.
- Thresholds set everywhere to reuse `>= 75` / adapt-local `65-74` / custom-local `< 65`: `slide-system/rules/visual-selection.md`, `docs/flows/component-selection-flow.md` (table + ASCII tree), `docs/flows/slide-generator-workflow.md` (score list + script table `75/65`).
- Export CLI corrected from stale `--run-dir` to real `--html/--slides/--out-dir/--output`: `docs/flows/slide-generator-workflow.md`, `docs/flows/3layer-export.md`.
- Published-library flat path fix: `docs/flows/slide-generator-workflow.md` template decompose now `…/<id>/visual.svg` (extraction `<item>/artifact/visual.svg` references left intact).
- New `slide-system/scripts/analyze_with_docling.py`: optional, analysis-only Docling layer. Writes only `outputs/component-extractions/<id>/analysis/{page-analysis,candidate-extraction-request,docling-report}.json`. Never publishes/mutates registry/library. Lazy Docling import (so `--help` and arg-validation need no heavy deps); clean degrade with actionable message + no writes when Docling absent. Candidate request is schema-compatible with `extraction-request.schema.json` (placeholder ids requiring human rename/approval before scaffolding).
- `slide-system/scripts/check_requirements.py`: host-aware staleness warning when an "available" tool's recorded path is missing on this host (capabilities.json holds foreign Mac paths) — points to `update_capabilities.py --force`.
- Docs for the new layer: `slide-system/rules/extraction-methods.md` (analysis-only section + MCP-optional note), `slide-system/workflows/extract-components.md` (optional pre-step callout), `.agents/skills/component-extractor/SKILL.md` (auto-detect subsection), `docs/how-to-use.md` (plain-language "auto-detect reusable parts" + approval-still-required, no MCP/bbox jargon).

**Verification (all pass):**
- `python slide-system/scripts/test_gates.py` → 57/57 passed
- `python slide-system/scripts/validate_registry.py` → Valid registry: 84 items (EXIT 0)
- `python slide-system/scripts/build_registry.py --check` → clean: 0 dangling/orphan/zombie, 84 valid
- `python slide-system/scripts/export_pptx.py --help` → matches documented `--html/--slides/--out-dir/--output`
- `analyze_with_docling.py --help` → EXIT 0 (no heavy imports); degrade path EXIT 3 with message and no `analysis/` dir created; draft candidate JSON validates against `extraction-request.schema.json` (jsonschema)
- Regex spot-check: `.gNN` accepted, malformed IDs rejected
- `py_compile` clean for changed scripts

**Docling integration does NOT:** publish, mutate the registry, write shared library artifacts, or replace PyMuPDF (still canonical PDF→SVG). It only proposes draft candidates for human review/approval.

**State:** Not committed

## 2026-06-26.13 — Docling analysis follow-up review fixes (analyze->scaffold handoff)

**Request:** Fix 4 review findings so the Docling auto-detect flow can safely hand off to `scaffold_extraction.py`.

**Fixes:**
- **P1 dir conflict:** `slide-system/scripts/scaffold_extraction.py` — an existing `outputs/component-extractions/<id>/` is now allowed through ONLY when it is an analysis-only shell (contains `analysis/`, lacks `request.json`/`manifest.json`/`items/`); the `analysis/` dir is preserved and real prior extractions are still rejected.
- **P1 placeholder gating:** added module-level `_DOCLING_DRAFT_ID` regex (`^(?:picture|figure|table|chart|form)-p[a-z0-9]+-\d+$`); scaffold now rejects Docling draft ids with a rename-to-semantic message. Lifted `_BANNED_ID`/`_DOCLING_DRAFT_ID`/`_GENERIC_INTENT` to module scope for testability.
- **P2 empty candidates:** `slide-system/scripts/analyze_with_docling.py` — `candidate-extraction-request.json` is written only when >=1 candidate exists (schema requires `items.minItems==1`); always writes `page-analysis.json` + `docling-report.json`; report carries `candidate_request_written` bool; summary prints a clear no-request note when empty.
- **P2 stale readiness:** `slide-system/scripts/check_requirements.py` — a required tool that is `available` but whose cached path is missing on this host now adds an unresolved blocker (status `blocked`), in addition to the existing warning for all stale tools. `capabilities.json` not edited.
- **Tests:** `slide-system/scripts/test_gates.py` — added `test_scaffold_rejects_docling_draft_ids`, `test_scaffold_still_rejects_positional_ids`, `test_analyze_with_docling_emits_only_draft_ids` (contract: every analyzer-minted id is caught by the scaffold draft gate).
- **Docs:** `slide-system/rules/extraction-methods.md` (analysis-dir coexistence, no-request-when-empty, placeholder pattern) and `.agents/skills/component-extractor/SKILL.md` (Docling draft placeholder added to prohibited-patterns list).

**Verification (all pass):**
- `python -m py_compile analyze_with_docling.py scaffold_extraction.py check_requirements.py` -> OK
- `python slide-system/scripts/test_gates.py` -> 60/60 passed (was 57)
- `python slide-system/scripts/validate_registry.py` -> Valid registry: 84 items (EXIT 0)
- `python slide-system/scripts/build_registry.py --check` -> clean, 84 valid (EXIT 0)
- `python slide-system/scripts/analyze_with_docling.py --help` -> EXIT 0 (no Docling import)
- Smoke: scaffold over `<id>/analysis/`-only dir -> EXIT 0, analysis preserved, request/manifest/items written
- Smoke: scaffold over real prior extraction (`items/` present) -> "already exists", EXIT 1
- Smoke: scaffold of `picture-p1-1` -> rejected, EXIT 1
- Smoke: required stale tool (`available` + missing path) -> status `blocked`, EXIT 1, blocker text emitted

**Residual risk:** The live Docling extraction (`analyze_document` bbox/label mapping) still cannot be exercised end-to-end here (Docling not installed); written defensively against the documented API. Unchanged from prior entry.

**State:** Not committed

---

## 2026-06-26.14 — Fix Docling docs and validate analysis handoff

**Request:** Fix the remaining Docling docs mismatch directly, then run the new component/auto-detect flow to see whether it works better.

**Actions:**
- Updated `slide-system/scripts/analyze_with_docling.py` top-level documentation so `candidate-extraction-request.json` is described as written only when candidates exist.
- Updated `.agents/skills/component-extractor/SKILL.md` to say the analysis directory always gets `page-analysis.json` and `docling-report.json`, while `candidate-extraction-request.json` exists only when reusable candidates are detected.
- While smoke-testing the flow, found an additional handoff bug: `scaffold_extraction.py` wrote `request.json` before rejecting Docling draft IDs, which polluted an analysis-only directory and blocked a later renamed request.
- Added `validate_request_item()` in `slide-system/scripts/scaffold_extraction.py` and moved item validation before any scaffold output write.
- Added `test_scaffold_rejects_docling_draft_without_polluting_analysis_dir` in `slide-system/scripts/test_gates.py`.

**Result:** Verification passed. `python -m py_compile slide-system/scripts/analyze_with_docling.py slide-system/scripts/scaffold_extraction.py slide-system/scripts/check_requirements.py slide-system/scripts/test_gates.py` OK; `python slide-system/scripts/test_gates.py` -> 61/61 passed; `python slide-system/scripts/validate_registry.py` -> Valid registry: 84 items; `python slide-system/scripts/build_registry.py --check` -> clean, 84 valid; `python slide-system/scripts/analyze_with_docling.py --help` OK; missing-Docling smoke exits 3 with no output directory; fake-Docling smoke detects one candidate, rejects raw `picture-p1-1` without pollution, then scaffolds successfully after renaming to `team-contribution-diagram` while preserving `analysis/`. Live Docling PDF parsing was not run because `docling` is not installed.

**Files:** `slide-system/scripts/analyze_with_docling.py`, `.agents/skills/component-extractor/SKILL.md`, `slide-system/scripts/scaffold_extraction.py`, `slide-system/scripts/test_gates.py`, `docs/logs/SESSION-LOG-2026-06-26.md`, `docs/logs/INDEX.jsonl`

**Symbols:** `validate_request_item`, `main`, `test_scaffold_rejects_docling_draft_without_polluting_analysis_dir`

**State:** Not committed

---

## 2026-06-26.15 — Preflight, install environment, and live-test Docling component detection

**Request:** Check requirements first, install the needed environment, then test whether the new component auto-detect flow works better.

**Actions:**
- Ran `extract-preflight` guidance via `check_base_requirements.py --input pdf --force --json`; initial state was blocked: missing `xmllint`, missing PDF provider PyMuPDF, missing standalone npm deps, and Docling was not installed.
- Created/verified repo-local `.venv`, installed approved Python providers with `uv pip install --python .venv\Scripts\python.exe PyMuPDF docling`; installed `markitdown[pptx,docx,xlsx]` into `.venv` after export-stack C1 exposed the missing module; installed npm deps with `npm install --package-lock=false`; installed MSYS2 via `winget install -e --id MSYS2.MSYS2 --silent` and `libxml2` via `pacman --noconfirm -S libxml2`; installed Playwright Chromium with `npx playwright install chromium`.
- Re-ran PDF preflight with `PATH=C:\msys64\usr\bin;.venv\Scripts;%PATH%`; status became `ready`, PDF input gate `ready`, PyMuPDF `1.27.2.3`, Docling import OK, `xmllint` available.
- Live-tested `analyze_with_docling.py` on `input\Kick_off_GOAL_SETTING_2026-2.pdf`. First full-deck run showed Docling could run but default OCR caused RapidOCR config failure; updated analyzer to use Docling `PdfPipelineOptions` with OCR off by default and added `--ocr` for scanned PDFs.
- Added `--pages`, `--min-area`, and `--max-area` to `analyze_with_docling.py` so users can analyze a focused page range and skip tiny decorative candidates by default. Updated `.agents/skills/component-extractor/SKILL.md` and `slide-system/rules/extraction-methods.md`; added `test_analyze_with_docling_filters_tiny_candidates`.
- Live-tested `--pages 1 --max-candidates 5`: output in `E:\tmp\slide-plugin-live-docling-page1-83b433413e594d80aecd2ee9ac09472e`; Docling 2.107.0 produced 4 elements and 1 candidate request.
- Verified handoff: raw `picture-p1-1` was rejected by scaffold without polluting output; after renaming to `kickoff-hero-visual`, scaffold succeeded and preserved `analysis/`.
- Ran the PDF extraction sub-pipeline on the renamed candidate: `convert_pdf_source.py`, `extract_editable_text_slots.py`, `crop_svg_region.py`, `externalize_svg_images.py`, `optimize_svg.py`, `validate_text_slots.py`, and `generate_item_preview.py`.

**Result:** Environment and live smoke passed for PDF component detection. Verification: `check_base_requirements.py --input pdf --force --json` -> ready; `python -m py_compile ...` OK; `test_gates.py` -> 62/62 passed; `validate_registry.py` -> 84 valid; `build_registry.py --check` -> clean; `test_export_stack.py` -> PASS for editable PPTX, HTML->PDF, PPTX text read via markitdown, layered 3-layer export, and SVG decomposition; live Docling focused page run -> exit 0, 1 candidate; renamed scaffold -> exit 0; extraction sub-pipeline -> `validate_text_slots` valid; preview thumbnail rendered successfully. The resulting preview is the right-side 2026 hero visual crop, not the full slide and not mixed with text.

**Files:** `slide-system/scripts/analyze_with_docling.py`, `.agents/skills/component-extractor/SKILL.md`, `slide-system/rules/extraction-methods.md`, `slide-system/registries/extract-readiness.json`, `docs/logs/SESSION-LOG-2026-06-26.md`, `docs/logs/INDEX.jsonl`

**Symbols:** `_load_converter`, `_parse_pages`, `build_candidates`, `main`, `test_analyze_with_docling_filters_tiny_candidates`

**State:** Not committed

---

## 2026-06-26.16 — Tester pass for Docling analysis pipeline

**When:** 2026-06-26 17:33
**Request:** Use the `tester` skill to retest the Docling/component pipeline.
**Actions:**
- Loaded `tester` skill and treated this as an independent Agent/tool QA pass for the Docling analysis handoff, not a feature implementation pass.
- Reviewed changed-file scope and key diffs; checked the untracked `slide-system/scripts/analyze_with_docling.py` source directly because normal `git diff` does not show untracked file contents.
- Ran requirement/environment checks with `PATH=C:\msys64\usr\bin;.venv\Scripts;%PATH%`; confirmed `.venv` packages: Docling 2.107.0, PyMuPDF 1.27.2.3, markitdown 0.1.6.
- Ran automated gates: `py_compile`, `test_gates.py`, `validate_registry.py`, `build_registry.py --check`, `test_export_stack.py`, `git diff --check`.
- Ran negative CLI checks for invalid `--pages 5-2` and invalid `--min-area 0.9 --max-area 0.1`; both failed cleanly with expected errors.
- Ran stale-capabilities smoke using `slide-system/boilerplates/job-requirements.json` and checked-in `capabilities.json`; expected `blocked` result confirmed stale Mac paths for required node/python are unresolved blockers on this host.
- Ran fresh live smoke under `E:\tmp\tester-docling-20260626173130-ad842252`: Docling analyzed page 1 of `input\Kick_off_GOAL_SETTING_2026-2.pdf`, emitted 4 elements and 1 candidate; raw `picture-p1-1` scaffold was rejected without polluting the analysis-only dir; after scratch rename to `kickoff-2026-hero-visual`, scaffold and the PDF extraction sub-pipeline succeeded through preview generation.
- Visually inspected `E:\tmp\tester-docling-20260626173130-ad842252\tester-docling-page1\items\kickoff-2026-hero-visual\preview\thumbnail.png`; preview is the right-side 2026 hero visual crop, not a full-slide capture.
- Ran empty-candidate smoke under `E:\tmp\tester-docling-empty-20260626173154-99414499`; analyzer wrote `page-analysis.json` and `docling-report.json`, did not write `candidate-extraction-request.json`, and reported `candidate_request_written=false`.
- During the first smoke, used the real `slide-system/registries/extraction-history.json` as the scaffold history path by mistake; confirmed the only diff was one test attempt plus `updated_at`, removed that artifact, and verified the file hash matches `HEAD`.
**Result:** No blocking defect found in tested scope. Verification passed: PDF preflight `ready` with no blockers; `py_compile` OK; `test_gates.py` 62/62; `validate_registry.py` 84 valid; `build_registry.py --check` clean; `test_export_stack.py` pass for editable PPTX, HTML->PDF, PPTX text read, layered 3-layer export, and SVG decomposition; stale-capabilities smoke blocks as intended; live Docling handoff creates a usable component preview after human rename; empty-candidate path does not write an invalid request. `git diff --check` reports no whitespace errors, only expected CRLF warnings.
**Files:** `docs/logs/SESSION-LOG-2026-06-26.md`, `docs/logs/INDEX.jsonl`
**Symbols:** none
**State:** Not committed

---

## 2026-06-26.17 — Start catalog control server for human review

**When:** 2026-06-26 17:40
**Request:** Turn on the web port for human rename/approval.
**Actions:**
- Reviewed `slide-system/catalog/catalog_server.py` and `docs/flows/catalog-publish.md`; confirmed the mutate-capable local server is `catalog_server.py` on `127.0.0.1:8799`, not a static `http.server`.
- Regenerated `slide-system/catalog/catalog-data.json` before serving. Current catalog has 84 published items and 0 staging/Draft items, because `outputs/component-extractions/` has no active draft items.
- Started the catalog control server with `.venv\Scripts\python.exe slide-system/catalog/catalog_server.py` in a hidden background process; verified `http://127.0.0.1:8799/slide-system/catalog/` returns HTTP 200.
- Found Windows regeneration was emitting backslash paths in `catalog-data.json`; fixed `build_component_catalog.rel()` to emit POSIX `/` paths for web-safe URLs and added `test_catalog_rel_uses_web_safe_posix_paths`.
- Rebuilt catalog data and verified a sample asset path from the served `catalog-data.json` returns HTTP 200.
**Result:** Server is running locally at `http://127.0.0.1:8799/slide-system/catalog/`. The UI can handle publish/delete approval for Draft items when they exist; there are currently no Draft items to approve. The current catalog UI does not implement Docling candidate rename before scaffold; that remains a separate UI/workflow gap.
**Files:** `slide-system/scripts/build_component_catalog.py`, `slide-system/scripts/test_gates.py`, `slide-system/catalog/catalog-data.json`, `docs/logs/SESSION-LOG-2026-06-26.md`, `docs/logs/INDEX.jsonl`
**Symbols:** `build_component_catalog.rel`, `test_catalog_rel_uses_web_safe_posix_paths`
**State:** Not committed

---

## 2026-06-26.18 — Create a real Docling draft for catalog approval

**When:** 2026-06-26 17:47
**Request:** User could not see any new Draft item and asked whether the pipeline had actually been rerun.
**Actions:**
- Confirmed the previous Docling smoke had used `E:\tmp`, so it did not create a real catalog Draft under `outputs/component-extractions/`.
- Used `component-extractor` guidance and ran PDF preflight: `check_base_requirements.py --input pdf --json` -> ready, no blockers.
- Ran `analyze_with_docling.py --source input\Kick_off_GOAL_SETTING_2026-2.pdf --extraction-id docling-kickoff-page1 --output-root outputs\component-extractions --pages 1 --max-candidates 5`; Docling found 4 elements and 1 candidate.
- Renamed the candidate request before scaffolding from Docling placeholder `picture-p1-1` to semantic `kickoff-2026-hero-visual` with intent `kickoff 2026 hero visual crop`.
- Ran the real extraction pipeline into `outputs/component-extractions/docling-kickoff-page1`: `scaffold_extraction.py`, `convert_pdf_source.py`, `extract_editable_text_slots.py`, `crop_svg_region.py`, `externalize_svg_images.py`, `flatten_svg_background.py`, second `externalize_svg_images.py`, `optimize_svg.py`, `apply_text_contract.py`, `validate_text_slots.py`, `classify_page_components.py`, `build_text_slot_gallery.py`, and `build_component_catalog.py`.
- Restarted the catalog control server and verified `http://127.0.0.1:8799/slide-system/catalog/catalog-data.json` now reports one Draft item: `sun.component.kickoff-2026-hero-visual`.
**Result:** A real Draft now exists in the catalog: `sun.component.kickoff-2026-hero-visual` / `Kickoff 2026 Hero Visual`, staging dir `outputs/component-extractions/docling-kickoff-page1/items/kickoff-2026-hero-visual`, publish readiness `ready=True`. Server is running at `http://127.0.0.1:8799/slide-system/catalog/`. Note: catalog UI can approve/publish this Draft, but still does not provide a pre-scaffold Docling candidate rename UI.
**Files:** `outputs/component-extractions/docling-kickoff-page1/`, `slide-system/catalog/catalog-data.json`, `slide-system/registries/extraction-history.json`, `docs/logs/SESSION-LOG-2026-06-26.md`, `docs/logs/INDEX.jsonl`
**Symbols:** none
**State:** Not committed

---

## 2026-06-26.19 — Run Docling over all input PDFs and compare with old results

**When:** 2026-06-26 18:17
**Request:** Run the new Docling pipeline over every input file and evaluate whether results improve over the old pipeline.
**Actions:**
- Inventoried all input PDFs: 7 files / 121 pages total (`GUIDLINE_PRESENTATION_SUN.pdf` 5, `Interview_Workshop_Sunriser.pdf` 12, `Kick_off_GOAL_SETTING_2026-2.pdf` 9, `Salary&Benefits_Sun.Studio_2026_Suner.pdf` 18, `Sun.Presentation.pdf` 17, `SUN.SLIDE.pdf` 40, `SUN.STUDIO_-_Performance_Review_-_2025.pdf` 20).
- Captured old baseline from `visual-library.json`: 84 published items, mostly page/template coverage by source (Performance 20, Salary 18, Sun.Presentation 17, Interview 12, Goal Setting 9, Guideline 6, plus logo/Dio); extraction history has many old full-page/staging/duplicate attempts.
- Ran full-file `analyze_with_docling.py` once per PDF under `outputs/component-extractions/docling-all-*`; all commands exited 0 but Docling logged many `std::bad_alloc` page preprocess failures and produced partial coverage only.
- Reran Docling per page for all 121 pages under `outputs/component-extractions/docling-page-pass-20260626-*-pNN/analysis/`; all 121 page runs exited 0.
- Aggregated results into `outputs/component-extractions/docling-page-pass-20260626-summary.json`, `outputs/component-extractions/docling-page-pass-20260626-candidates.csv`, `outputs/component-extractions/docling-page-pass-20260626-evaluation.json`, and `outputs/component-extractions/docling-page-pass-20260626-evaluation.md`.
**Result:** Per-page Docling pass succeeded on 121/121 pages, found 1126 layout elements and 115 candidate regions across 61 pages (`picture=114`, `table=1`). By file: Guideline 13 candidates, Interview 10, Goal Setting 9, Performance 8, Salary 13, Sun.Presentation 9, SUN.SLIDE 53. Compared with the old pipeline, Docling improves automatic sub-slide candidate discovery (old published library is mostly full-page/template items), but it does not replace canonical extraction: candidates still have placeholder IDs/generic intent and need human rename before scaffold/publish; text-heavy layout pages often have no visual candidate. Full-file Docling mode is not reliable for large decks because it can return exit 0 while silently missing pages after `std::bad_alloc`; per-page/chunk fallback is required.
**Files:** `outputs/component-extractions/docling-all-*/analysis/`, `outputs/component-extractions/docling-page-pass-20260626-*/analysis/`, `outputs/component-extractions/docling-page-pass-20260626-summary.json`, `outputs/component-extractions/docling-page-pass-20260626-candidates.csv`, `outputs/component-extractions/docling-page-pass-20260626-evaluation.json`, `outputs/component-extractions/docling-page-pass-20260626-evaluation.md`, `docs/logs/SESSION-LOG-2026-06-26.md`, `docs/logs/INDEX.jsonl`
**Symbols:** none
**State:** Not committed
