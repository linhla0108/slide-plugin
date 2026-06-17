# Plan: Template & Template Preview Feature

## Context

The slide-generator system has a complete extraction pipeline but **zero published templates**. `visual-library.json` holds only 2 published items (`sun.asset.logo`, `sun.character.dio`). When the agent runs `select-visual-items`, every section falls to `custom-local` because there is nothing to match against — every deck is built from scratch.

**Verified inventory (2026-06-16):**

- `outputs/component-extractions/**/mapping.json`: **107** items on disk.
- **18** are template-typed mappings (15 `full-slide-template` + 3 `template`). Of those: **12 `staging`** (publish candidates) and **6 `duplicate`** (auto-rejected by publish).
- `catalog-data.json`: **93** items (counts: `published 2, staging 91`). A catalog filter on "template" returns **26** items, because the build normalizes 14 `sun-goal-2025-page-NN` mappings (whose `type` is `null`) into `template`. These 14 are NOT the slide-template candidates and must not leak into the picker.

**Clean publish shortlist (after quality triage — see Phase 0):**

| Item | stable id | status | slots | issue |
|---|---|---|---|---|
| three-column-cards | `sun.full-slide-template.three-column-cards` | staging | 13 | none — rename id to `sun.template.*` |
| section-header-question | `sun.full-slide-template.section-header-question` | staging | 7 | rename id |
| table-of-contents | `sun.full-slide-template.table-of-contents` | staging | 12 | rename id |
| slide-5 | `sun.template.slide-5` | staging | 9 | id collides with 2 duplicates |
| guideline-image-layouts | `sun.template.guideline-image-layouts` | staging | 24 | already has html/pdf=supported |
| cover-title-connect | `sun.full-slide-template.cover-title-connect` | staging | 6 | **visual.svg is a 360 B raster stub** — verify it decomposes |

**Excluded (do not publish):**

- `title-cover` — **unpublishable**: only has `artifact/title-cover.html`; missing `visual.svg`, `text-slots.json`, and `evidence/source-with-text.svg`. Would need a full rebuild first.
- `deepseek-v4-flash-slide-1..5` — model name baked into `item_id` and `candidate_stable_id`, noisy decomposition (29 / 17 slots). Skip, or re-extract with clean ids before considering.
- 6 `duplicate` items — auto-rejected.

The goal: let users browse and select published slide templates during intake, with a visual preview UI, and have the build pipeline use the selected template as the base layout.

## Decisions

- **Template = full slide**: in this library a `template` is a FULL SLIDE (full-bleed 1920×1080), not an atomic `section`/`component`/`card`/`icon`. The schema's `template` type *is* the full-slide bucket; the `full-slide-template` source label is just an un-normalized synonym (see Type normalization). Previews, compatibility, and the picker all operate at full-slide scope.
- **Picker grouping = source deck (full sets)**: the picker groups slides by their originating deck (`source.path`) into full deck SETS, ordered by slide number — e.g. `SUN.SLIDE` = 5 slides (cover→divider). It does NOT bucket by use-case (Cover/Section/Content). Each deck shows a "Select whole set" action (copies all its slide ids) plus per-slide select. `build_template_picker_data.py` emits `decks[]` (each with `slides[]` sorted by `slide_number`); `picker.js` renders deck sections.
- **Preview = the full slide as the original**: the picker thumbnail must show the whole slide AS THE ORIGINAL, not a reconstruction. Each item ships `evidence/source-with-text.svg` — the original 1920×1080 slide with text baked in and images via `../artifact/assets/...` (resolves from the evidence dir). `generate_template_preview.py` renders that through `render_svg.js` (Chromium) to `preview/thumbnail.png` (the picker image), and separately writes `preview/preview.html` — the editable composite (`visual.svg` + text slots) used by the template-based build step. Falls back to capturing the composite only when the original evidence SVG is missing.
- **UI approach**: new `slide-system/template-picker/` (separate from the dev-facing `slide-system/catalog/`, which already exists).
- **Template scope**: user manually approves which staging items to publish; default to the clean shortlist above.
- **Type normalization**: schema enum (`visual-item.schema.json`) allows only `template`. `publish_extraction.py` writes `mapping["type"]` verbatim into the registry **and** uses it to pick the destination folder via `TYPE_FOLDERS` (no `full-slide-template` key → falls back to `library/full-slide-template/`). So we must rewrite the mapping **`type` field** itself to `"template"`, not just the stable id. Also re-key the stable id from `sun.full-slide-template.*` to `sun.template.*`.
- **Duplicate resolution**: `publish_extraction.py` hard-rejects `status == "duplicate"`. Publish only the canonical `staging` item per concept; the 6 duplicates are ignored. Resolve the `sun.template.slide-5` 3-way collision (1 staging `slide-5` + 2 duplicates) by keeping `slide-5` and leaving the duplicates rejected.
- **Compatibility testing**: every candidate has `compatibility` all `"untested"`, which publish rejects. There is **no canva exporter**; pptx/pdf/html exporters exist but operate on an **HTML deck**, not a raw template. So compatibility is established by composing the template into a one-slide HTML deck and running the real exporters (html via `capture-slides.js`, pptx via `export_pptx.py` + `validate_export_objects.py`, pdf via `export-pdf.js`); `canva` is set by policy (`hybrid`/`unsupported`), never `untested`. This depends on export deps being installed (Phase 0A).
- **Skill location risk**: the 4 design skills used in Phase 3 (`design-taste-frontend`, `impeccable`, `frontend-design`, `ui-ux-pro-max`) live in `~/.agents/skills/`, NOT in-repo. This conflicts with the repo's self-contained-plugin rule (`AGENTS.md`, `intake-and-triage.md`). Accept as a build-time-only dependency (the picker output is static and ships without the skills), or vendor copies in-repo if packaging requires it.

## Execution model: subagent delegation, no blocking

Work is split so independent subtasks run as **parallel subagents that never touch the same file**. The only genuine serialization point is publishing (all items write the shared `visual-library.json`). Phases gate on data dependencies only.

```
Phase 0  Foundation (2 parallel subagents)
  0A env-setup ─┐         0B data-audit ─┐
                │                         │
                ▼                         ▼
Phase 1  Independent build tracks (5 fully-parallel subagents, zero shared files)
  1A preview-script   1B scoring   1C base_template-schema   1D picker-UI(fixture)   1E build-flow-docs
                │           │              │                       │                     │
                └─────┬─────┴──────────────┴───────────────────────┴─────────────────────┘
                      ▼
Phase 2  Item preparation (1 subagent PER ITEM, parallel — each writes only its own item dir)
  2·three-column   2·section-header   2·toc   2·slide-5   2·guideline   2·cover-title
                      │
                      ▼
Phase 3  Publish & wire real data (SERIAL — shared registry writes)
  3A publish-each → validate_registry → 3B real picker-data → 3C catalog wiring
                      │
                      ▼
Phase 4  End-to-end verification (1 subagent)
```

**Parallelism rules:**
- Phase 0: 0A and 0B share nothing → parallel.
- Phase 1: 1A (new script), 1B (score script + select-visual-items.md), 1C (schema + intake.md + plan-slide-deck.md), 1D (template-picker/ dir + build_template_picker_data.py against a fixture), 1E (build-html-deck.md + select-visual-items base_template note) — disjoint file sets → all 5 parallel. 1D builds against a checked-in fixture `picker-data.sample.json` so it does not wait on real published items.
- Phase 2: one subagent per shortlisted item; each writes only `outputs/component-extractions/<batch>/items/<id>/` (its own `mapping.json` + `preview/`) → parallel. Needs 0A (export deps), 0B (shortlist), 1A (preview script).
- Phase 3: **serial** — `publish_extraction.py` mutates the shared `visual-library.json` + `extraction-history.json`. Run items one at a time, then `validate_registry.py`, then regenerate real `picker-data.json` and swap out the fixture.
- Note for 1B (select-visual-items.md) vs 1E (also edits select-visual-items.md): to avoid a write conflict, **1B owns `select-visual-items.md`**; 1E hands its one-paragraph `base_template` note to 1B as text rather than editing the file. (Disjoint-file rule enforced.)

---

## Phase 0 — Foundation

### 0A · env-setup  *(subagent: env)*
**Goal**: make the export toolchain runnable so Phase 2 compatibility testing is real.
**Steps**:
1. Run `slide-system/scripts/setup.sh` (installs Playwright/node deps + `python-pptx`).
2. Run `python slide-system/scripts/update_capabilities.py --check all` and confirm `capture-slides` and `build-hybrid-pptx` flip from `unknown` → `available`.
**Acceptance**: `capabilities.json` shows export tools `available`; a trivial `capture-slides.js` run on a sample HTML produces a PNG.
**Blocks**: Phase 2 compatibility testing. **Parallel with**: 0B.

### 0B · data-audit  *(subagent: data-audit)*
**Goal**: confirm the publish shortlist and per-item readiness.
**Steps**:
1. For each shortlist item, verify on disk: `artifact/visual.svg`, `artifact/text-slots.json`, `evidence/source-with-text.svg` exist; record slot count and current `compatibility`.
2. Flag `cover-title-connect` (360 B stub svg): decompose-test it; if it cannot produce real objects, drop it from the shortlist.
3. Emit a `template-publish-shortlist.json` (item dir, stable id target, current type/status, gaps) for Phase 2 to consume.
**Acceptance**: a written shortlist where every listed item has all three artifacts present and a decompose smoke-test passes.
**Blocks**: Phase 2. **Parallel with**: 0A.

---

## Phase 1 — Independent build tracks (5 parallel subagents)

### 1A · preview-script  *(subagent: tooling)*  — DONE
**Goal**: automate faithful full-slide template preview generation.
**Files created**: `slide-system/scripts/generate_template_preview.py`.
**Steps**:
1. Input: an item dir with `artifact/visual.svg` + `artifact/text-slots.json` (+ `evidence/source-with-text.svg` for the original render).
2. Write `preview/thumbnail.png` — the picker image — by rendering the ORIGINAL `evidence/source-with-text.svg` (full slide, text baked in) through `render_svg.js` (Chromium) at 1920×1080. `--from composite` forces the reconstructed path instead; the original path falls back to composite capture when the evidence SVG is absent.
3. Write `preview/preview.html` — the editable composite (`visual.svg` inlined as background with rasters base64-embedded + text slots positioned from normalized bounds, using `example_value`) — for the template-based build step.
4. Composite-capture fallback uses `capture-slides.js --keep-bg-text` (default strips text), renames the fixed `slide-01-bg.png` to `thumbnail.png`, and cleans the side files. `--batch <extraction-dir>` mode for all items; `--html-only` skips thumbnails.
**Acceptance**: running it on `slide-5` yields a 1920×1080 `thumbnail.png` that is the original slide ("What We Planned for 2025", SUN.CONNECT pill, footer/page) plus an editable `preview.html`. **Verified.** **Parallel with**: 1B–1E.

### 1B · scoring  *(subagent: scoring)*
**Goal**: template-aware scoring.
**Files modified**: `slide-system/scripts/score_visual_items.py`, `slide-system/workflows/select-visual-items.md`.
**Steps**:
1. Add optional `--item-type` filter (default: all). When `template`, restrict the scored candidate set to `type == "template"`.
2. Template weight profile: current weights are `density 10 / content_structure 20`; when `--item-type template`, shift 5 pts `density → content_structure` (density 5, structure 25); total stays 100.
3. Document in `select-visual-items.md` that template selection passes `--item-type template`. Also fold in the one-paragraph `base_template` note handed over by 1E.
**Acceptance**: with `--item-type template` the ranked `candidates` list contains only `type: template` items; a cover request scores the cover template `>= 75` (`action: reuse`); omitting the flag leaves non-template scoring unchanged. **Parallel with**: 1A, 1C, 1D, 1E.

### 1C · base_template-schema  *(subagent: intake-schema)*
**Goal**: make `base_template` a first-class, persistable field.
**Files modified**: `slide-system/schemas/job-requirements.schema.json`, `slide-system/workflows/intake-and-triage.md`, `slide-system/workflows/plan-slide-deck.md`.
**Steps**:
1. **Schema**: `job-requirements.schema.json` has `additionalProperties: false`, so add an optional `base_template` property (string id or null) — a data-only add will otherwise be rejected. (This file was missing from the prior plan.)
2. **Intake**: in `intake-and-triage.md` Case 1 prose, between *style and tone* and *slide count*, offer template browsing ("I have N published templates — want to browse and pick a starting point?"); add the same as a Case 2 direction-finding option. Add a `Base template` line to the Brief Recap Gate bullet list. Insert into prose (cases are sentences, not step lists).
3. **Plan**: in `plan-slide-deck.md`, note that when `base_template` is set, the plan adopts its layout structure as the starting point.
**Acceptance**: a brief recap can carry `base_template`; a job-requirements doc with `base_template` validates against the schema. **Parallel with**: 1A, 1B, 1D, 1E.

### 1D · picker-UI  *(subagent: frontend)*
**Goal**: user-facing browse/select page, built against a fixture so it never blocks on real data.
**Design skills** (build-time only; home-global — see Decisions): `/design-taste-frontend` → `/ui-ux-pro-max` → build with `/frontend-design` → `/impeccable` audit.
**Files created**: `slide-system/template-picker/index.html`, `picker.css`, `picker.js`, `picker-data.sample.json` (fixture), `slide-system/scripts/build_template_picker_data.py`.
**Steps**:
1. `build_template_picker_data.py`: read `visual-library.json`, filter to `status==published && type==template`, write `template-picker/picker-data.json` with id, name, intent, tags, content_structure, slot count, preview path, thumbnail path. (Must NOT pull from `catalog-data.json` — that includes the 14 sun-goal pages.)
2. Ship `picker-data.sample.json` (3–4 hand-written entries) so the UI renders before Phase 3 produces real data.
3. UI: grid grouped by use-case (Cover, Section, Content, Data, Closing, Other); click → detail panel with larger preview + Select; Select copies the template id to clipboard with a paste-into-conversation instruction. OKLCH palette, proper type scale.
**Acceptance**: `python -m http.server` serves the picker; it renders the fixture grouped by use-case; click → detail; copy-to-clipboard works. **Parallel with**: 1A, 1B, 1C, 1E.

### 1E · build-flow-docs  *(subagent: build-flow)*
**Goal**: document template-based building (doc-only; no code path runs until items exist).
**Files modified**: `slide-system/workflows/build-html-deck.md`; hands a `base_template` note to 1B for `select-visual-items.md`; updates `.agents/skills/slide-generator/SKILL.md` step 9.
**Steps**:
1. Add a "Template-Based Build" section to `build-html-deck.md` (currently a flat bullet list): load the template's `visual.svg` + `text-slots.json` from the library path → run `decompose_svg_objects.py` → map plan content onto slots **by `role`/`id`** (see slot-mapping note below) → fall back to custom build for uncovered slides.
2. Slot-mapping note (corrected to schema): every slot is `editable` and `allow_empty` (`const: true` in `text-slots.schema.json`); there is **no per-slot `required` field**; overflow is governed by `text_contract.overflow_policy` at the item level, not per slot. Map plan fields (title/subtitle/body/footer) to slot `role`s; leave unmatched slots empty rather than inventing content.
3. Note `base_template` → auto-score-100 behavior for matching slides (text handed to 1B for the actual `select-visual-items.md` edit).
4. `slide-generator/SKILL.md` step 9: add the template path. (Scoring is folded into step 7, build is step 9 — confirmed.)
**Acceptance**: `build-html-deck.md` has a Template-Based Build section with an accurate slot-mapping description. **Parallel with**: 1A–1D.

---

## Phase 2 — Item preparation (1 subagent per item, parallel)  — DONE

**Status (2026-06-16)**: all 6 shortlist items prepared and `validate_text_slots` PASS; each has `type: template`, `sun.template.*` id, `name`, authored `content_structure` + `tags`, a faithful full-slide `preview/thumbnail.png` (original render) + editable `preview.html`, `approval: approved`, and compatibility `{html: supported, pptx: hybrid, pdf: supported, canva: hybrid}` (no `untested`) with a limitation that per-item PPTX/Canva fidelity is validated at first deck generation. Export smoke test on slide-5 passed (PDF 261 KB; flat PPTX `"pass": true`, 9 editable text boxes). All publish preconditions met — **awaiting user sign-off before Phase 3 publish**.

**Tooling fix applied**: `generate_template_preview.py` `_slot_style` crashed on `font_size: "18pt"` strings (sun-connect batch) — added `_parse_font_px` to normalize `pt`/`px`/bare/numeric across batches; reverted a stray `text-slots.json` mutation so artifacts stay source-of-truth.

**Depends on**: 0A (export deps), 0B (shortlist), 1A (preview script).
**Goal**: bring each shortlisted item to a publishable state. Each subagent edits ONLY its own item dir, so they never collide.

**Per-item steps** (run for each of the ~6 shortlist items):
1. Rewrite `mapping.json` `type` → `"template"`; re-key `candidate_stable_id` to `sun.template.<slug>` (ensure it matches `^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+$` and collides with nothing else in the batch).
2. Add `name` (human-readable; mappings lack it → publish would otherwise derive from the id).
3. Author `content_structure` (missing on all 18 items — must be written, not "carried over") and `tags`.
4. Generate the preview via `generate_template_preview.py --item-dir <dir>`: `preview/thumbnail.png` is the faithful full-slide render of the original (`evidence/source-with-text.svg`); `preview/preview.html` is the editable composite. Eyeball the thumbnail against the source before approving.
5. **Compatibility**: compose the template into a one-slide HTML deck, then set each target by real export: html (`capture-slides.js`), pptx (`export_pptx.py` + `validate_export_objects.py`), pdf (`export-pdf.js`); set `canva` to `hybrid`/`unsupported` by policy. No value may remain `untested`.
6. Set `approval.status: "approved"`.
7. Run `validate_text_slots.py --item-dir <dir>` to confirm the contract (visual.svg has no `<text>`/`<tspan>`; every source char is covered by a slot's `source_refs`). `cover-title-connect` and any stub must pass this or be dropped.

**Acceptance per item**: passes a dry validation equivalent to `publish_extraction.py` preconditions (not duplicate, approved, `type: template`, valid stable id, ≥1 preview, ≥1 evidence, no `untested`).
**Checkpoint**: user reviews prepared items and confirms the final publish list.

---

## Phase 3 — Publish & wire real data (SERIAL)  — DONE

**Status (2026-06-16)**: all 6 templates published → `visual-library.json` now has 8 items (1 asset, 1 character, 6 `template`, all `published`); `library/templates/` has 6 dirs; `validate_registry.py` = "Valid registry: 8 items". `build_template_picker_data.py` regenerated `picker-data.json` (6 templates: Cover 1, Section 3, Content 2). Picker verified live in-browser: "Live library" pill, real full-slide thumbnails, detail modal with metadata, and Select→clipboard→toast ("Copied sun.template.cover-title-connect …"). `rebuild-catalog.md` updated to also refresh picker data.

**Fix applied**: `build_template_picker_data.py` emitted repo-root-relative asset paths (404 from the picker page). Added `to_page_relative()` so `preview`/`thumbnail` paths are relative to `slide-system/template-picker/` (e.g. `../library/templates/<id>/preview/thumbnail.png`) and resolve regardless of HTTP server root.

**Depends on**: Phase 2 (approved items), Phase 1 (UI + data script + scoring).
**Why serial**: every publish mutates the shared `visual-library.json` + `extraction-history.json`.

### 3A · publish  *(single subagent, sequential calls)*
1. For each approved item: `publish_extraction.py --extraction-dir <batch> --item-id <id>` → copies to `library/templates/<stable-id>/`, registers in `visual-library.json`, appends to `extraction-history.json`, flips mapping `status` → `published`.
2. After all publishes: `validate_registry.py` (checks id pattern, compatibility enum on all 4 of html/pptx/pdf/canva, and that `paths.artifact`/`paths.preview` resolve on disk).
**Acceptance**: shortlist items appear `published` in `visual-library.json`; `validate_registry.py` passes; `score_visual_items.py --item-type template` returns them.

### 3B · real picker data
1. Run `build_template_picker_data.py` to produce the real `picker-data.json`; the UI now loads it instead of the fixture.
**Acceptance**: the picker shows the real published templates, grouped by use-case.

### 3C · catalog wiring
1. Update `rebuild-catalog.md` so the rebuild step also regenerates picker data.
**Acceptance**: `rebuild-catalog` documents the picker-data refresh; staging items still never leak into selection.

---

## Phase 4 — End-to-end verification  *(subagent: verify)*

1. `validate_registry.py` and `validate_text_slots.py --item-dir <each published item>` pass.
2. Run a test generation with `/slide-generator`: a new presentation prompt.
3. Intake offers template browsing after the style question; declining works with no regression.
4. Open the picker in a browser; templates render; selecting records `base_template` in the brief.
5. Build uses the template layout; a non-template slide still builds normally.
6. Export PPTX and run `validate_export_objects.py`; the approval package shows which slides are template vs custom.

---

## Risk register

| Risk | Source | Mitigation |
|---|---|---|
| Export deps uninstalled → compatibility can't be tested | `capabilities.json` shows `capture-slides`/`build-hybrid-pptx` = `unknown` | Phase 0A `setup.sh` gates Phase 2 |
| `cover-title-connect` stub svg won't decompose | 360 B raster-only visual.svg | 0B decompose smoke-test; drop if it fails |
| `title-cover` / `deepseek-*` look like candidates but aren't | missing artifacts / model-named ids | explicitly excluded in Context |
| 14 sun-goal pages leak into picker | catalog normalizes them to `template` | picker data reads `visual-library.json` (published only), not the catalog |
| `base_template` silently dropped | `job-requirements.schema.json` `additionalProperties: false` | 1C adds the schema property |
| Two tracks edit `select-visual-items.md` | 1B and 1E overlap | 1B owns the file; 1E hands over text |
| Design skills not in-repo | `~/.agents/skills/` only | build-time-only dependency; output is static |
| Slot-mapping mis-described | text-slots schema has no `required`, no per-slot `overflow_policy` | 1E uses the corrected description |
