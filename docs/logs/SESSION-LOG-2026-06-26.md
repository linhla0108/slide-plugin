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

**State:** Not committed
