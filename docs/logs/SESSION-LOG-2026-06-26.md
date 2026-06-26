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
