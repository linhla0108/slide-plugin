# /slide-generator — Complete Workflow Reference

> LLM reference file — read this instead of re-analyzing the full system each session.
> Updated: 2026-06-17. Sources: `SKILL.md`, `slide-system/workflows/*`, `slide-system/rules/*`,
> `slide-system/schemas/*`, `slide-system/registries/*`, `slide-system/scripts/*`.

---

## 0. Architecture Overview

```
.agents/skills/slide-generator/SKILL.md     ← sole entry point for all slide-generation jobs
slide-system/                                ← core engine
├── workflows/    15 files — ordered procedures, loaded on demand
├── rules/        10 files — quality constraints and hard rules
├── schemas/       8 files — JSON contracts for scripts + artifacts
├── registries/    6 files — capabilities, visual items, thresholds, history, aliases
├── library/       published visual artifacts (templates, components, assets)
├── brand-packs/   brand manifests (currently: sun-studio/)
├── catalog/       review UI for published + staging items
├── template-picker/  browse + select template UI
├── boilerplates/  starter files for jobs, approvals, extraction
└── scripts/       Python + Node.js automation

outputs/
├── slide-jobs/<job-id>/runs/<run-id>/    ← output per job
└── component-extractions/                ← output of /component-extractor (separate skill)
```

**Relationship between the two skills:**
```
/component-extractor ──publish──▶ slide-system/library/ ──select──▶ /slide-generator
     (staging → approve)           (published items)         (published only)
```

---

## 1. 12-Step Pipeline

### Step 1 — Intake & Triage

**Workflow:** `workflows/intake-and-triage.md`

**Persona:** Treat new users as non-technical by default. Use plain language, avoid jargon.

**Questioning approach:**
- One question per turn, each with a guess attached
- Cap at 5–6 questions; stop once answers become predictable
- Fill remaining gaps with sensible defaults stated in the recap
- Tech escape hatch: if the user pastes a complete brief, only ask about gaps

**Export format normalization:**
- "PowerPoint" / "PPT" / "PPTX" / "power point" → editable `.pptx` in layered mode
- Do NOT ask `.ppt` vs `.pptx`; do NOT ask about editability
- Flat/frozen PPTX only when the user explicitly says "flattened" / "image-only" / "frozen" / "non-editable"
- PowerPoint + PDF → export both

**7 case types:**

| Case | Trigger | Details |
|------|---------|---------|
| 1 | **New from idea/brief** | Ask: purpose, audience, content, style, template?, slide count, icons, brand, format |
| 2 | **Needs advice** | Guided questioning → folds into Case 1 once intent is clear |
| 3 | **Polish existing file** | Upload .pptx/.pdf. Editable → fix in place. Flat → offer rebuild |
| 4 | **Rebuild from reference** | Upload image/PDF. Ask: keep content or change the look? |
| 5 | **Iterate previous run** | "Change slide 3". Read existing job via `resume-job.md`, only ask about changes |
| 6 | **Rebrand/localize** | Keep content + layout, swap brand pack or language |
| 7 | **Raw data → slides** | Doc/table/numbers → delegate to `ppt-master` or `make-a-deck` |

**Template offer (Cases 1, 2):** after the style question, before slide count:
> "I have N published templates ready — want to browse and pick one as a starting point?"
- If selected → record `base_template` ID in the brief
- If declined → continue with custom build

### Step 2 — Recap & Confirm Gate

**Plain-language recap covering:**
- Purpose and context
- Audience
- Main content and source fidelity
- Style direction
- Base template (if chosen)
- Slide count
- Image/icon needs
- Brand pack
- Export format
- Out of scope

**STOP — do not build until the user explicitly confirms.** The recap becomes the job requirements and export contract.

### Step 3 — Job Creation & Versioning

Create the output structure:
```
outputs/slide-jobs/<job-id>/
├── requirements/
│   └── job-requirements.json       ← validated against job-requirements.schema.json
├── runs/<run-id>/
│   ├── analysis/
│   ├── build/
│   ├── exports/
│   ├── qa/
│   └── run-manifest.json
└── assets/                          ← job-wide, shared across runs
```

### Step 4 — Check Requirements

**Workflow:** `workflows/check-requirements.md` | **Script:** `check_requirements.py`

1. Validate `job-requirements.json` against the schema
2. Read `registries/capabilities.json` (cached — refresh only when unknown / path missing / fingerprint changed)
3. Verify: inputs, checksums, source authority, brand pack, fonts, export targets, editability, renderer support, approvals
4. Classify each finding: `pass` / `warning` / `blocker`

### Step 5 — Blocker Gate

**STOP on blockers.** Continue only when the user approves an override. Record overrides in the manifest.

### Step 6 — Content Analysis & Source Authority

**Rule:** `rules/source-authority.md`

Priority order when sources conflict:
1. Explicit user instructions for the current job
2. Approved job requirements
3. Supplied source files (content + reference appearance)
4. Brand-pack rules and canonical assets
5. Published visual-library items
6. Project-local implementations

When sources disagree → create a divergence summary, ask the user.

**Rule:** `rules/content-fidelity.md`
- Preserve wording, numbers, ordering, and language unless the user explicitly approves changes
- Preserve grouping, hierarchy, and reading order
- Do NOT omit content to solve layout pressure
- Keep semantic foreground editable

### Step 7 — Slide Plan + Visual Selection

**Plan** (`workflows/plan-slide-deck.md`): Expand the brief into:
- Content model, slide titles, narrative order, section map
- Visual direction, base template adoption (if set)
- Export contract, known limitations

**Visual Selection** (`workflows/select-visual-items.md`):
1. Load only `published` items from `registries/visual-library.json`
2. Reject: deprecated / staging / brand-incompatible / export-incompatible
3. Score with `score_visual_items.py`:
   - ≥75 → reuse as-is
   - 55–74 → slide-local adaptation
   - <55 → custom build
4. When `base_template` is set → auto-assign score 100 to slides matching the template intent
5. Record extraction recommendations (NEVER trigger extraction)
6. Output: one `analysis/visual-requests.json` + one `analysis/selection-report.json` per run

### Step 8 — Approval Package

Present a single approval package containing:
- Capability report
- Visual selections + scores + reasons
- Warnings (if any)

**STOP — user must approve before building.**

### Step 9 — Build HTML Deck

**Workflow:** `workflows/build-html-deck.md`

**Canvas:** `1920×1080` `<deck-stage>`

#### 9a. Template-Based Build (conditional — when the brief has `base_template`)

```bash
# Decompose template artwork (MANDATORY — no hand-splitting, no wholesale embedding)
.venv/bin/python3 slide-system/scripts/decompose_svg_objects.py \
    --svg slide-system/library/templates/<id>/artifact/visual.svg \
    --out-dir <job>/assets/page-NN --prefix page-NN \
    --href-base <relative-path-from-deck.html>
```
- Map plan content → slots by role/id (from `text-slots.json`)
- Slot semantics: every slot has `editable: true`, `allow_empty: true`
- Unmatched slots → leave empty, NEVER invent content
- Slides beyond template coverage → fall back to custom build
- Content overflow → surface a warning (overflow is unmanaged by design)

#### 9b. Full-Page Artwork SVG (conditional — SVG from extraction)

```bash
# Decompose extraction artwork (MANDATORY)
.venv/bin/python3 slide-system/scripts/decompose_svg_objects.py \
    --svg <item>/artifact/visual.svg \
    --out-dir <job>/assets/page-NN --prefix page-NN \
    --href-base <relative-path>
```
- Output: fragment SVGs + `snippet.html` (pre-tagged divs) + `decompose-manifest.json`
- `base_candidates` (≥85% canvas) → CSS `background-image` on the slide root, NOT tagged as overlay
- Paste snippet into the slide div
- Review object IDs; rename to semantic names when helpful

#### 9c. Layer Tagging (MANDATORY for all PPTX builds)

| Attribute | Meaning |
|-----------|---------|
| `data-export-layer="overlay"` + `data-export-id="<name>"` | Independent movable object |
| `data-export-group="<name>"` | Group multiple elements into one semantic overlay |
| `data-export-native="rect\|ellipse"` + `data-export-id` | Simple shape → native PPTX autoshape |
| `data-export-vector-source="<path.svg>"` | Enable true-vector svgBlip |
| `data-export-skip` | Text baked into raster (gradient text, etc.) |
| *(no tag)* | Passive full-slide canvas = base layer |

**Validation gates:**
- Visible `svg`/`img`/`canvas`/`video` without a tag → **FAIL**
- Single overlay covering ≥85% of the canvas → **FAIL** (anti-loophole)

#### Layer assignment decision table

```
Element on slide
  ├─ full-slide gradient/texture ──────────── BASE                   (C1)
  ├─ vector decor / blob ──────────────────── OVERLAY (own shape)    (C2)
  ├─ chart / diagram ──────────────────────── OVERLAY group          (C3)
  ├─ has shadow/glow beyond bbox ──────────── OVERLAY, expanded rect (C4)
  ├─ backdrop-filter (frosted glass)
  │     ├─ only base behind it ────────────── OVERLAY opaque         (C5a)
  │     └─ other overlays behind it ───────── bake into BASE + warn  (C5b)
  ├─ mix-blend-mode ───────────────────────── bake into BASE + warn  (C6)
  ├─ text inside overlay (chart label)
  │     ├─ user needs to edit ─────────────── NATIVE TEXT            (C7a)
  │     └─ decorative ─────────────────────── data-export-skip       (C7b)
  ├─ text below an object ─────────────────── unified z-order        (C8)
  ├─ pure rotate(θ) ──────────────────────── record angle, PPTX rot (C9a)
  ├─ skew/complex matrix ─────────────────── bake into BASE + warn  (C9b)
  ├─ photo with rounded corners/mask ──────── OVERLAY transparent PNG(C10)
  ├─ intentionally full-image deck ────────── --keep-bg-text         (C11)
  ├─ card/pill/line with solid fill ───────── (P2) native autoshape  (C12)
  └─ two overlapping overlays ─────────────── allowed, z recorded    (C13)
```

#### Iterating on old flat-mode runs

When resuming a run originally built with `--mode flat` (v1, no tags), do NOT attempt
layered export on the existing HTML. Either rebuild the HTML with proper tags for a new
layered run, or keep `--mode flat` for a patch. Ask the user which path they prefer.

#### Asset management

- Brand assets → reference in-place (canonical brand-pack path)
- Job-scoped assets → `<job-id>/assets/` (shared across runs)
- Copy into a run ONLY when unique to that single run
- Do NOT create empty directories — `package_job.py` auto-prunes

### Step 10 — Export

#### 10a. Export PPTX

**Workflow:** `workflows/export-editable-pptx.md`

**Single entry point:**
```bash
.venv/bin/python3 slide-system/scripts/export_pptx.py \
    --run-dir <run> [--mode layered|flat]
```
- Default: `--mode layered` (3-layer: base + overlay shapes + native text)
- `--mode flat`: only when the user explicitly requests frozen/non-editable
- `--keep-bg-text`: separate capture flag for intentionally full-image decks — NOT a mode
  (can combine with `--mode flat`; see case C11)

**v1 ↔ v2 isolation rules:**
- `--mode flat` = frozen v1 behavior (strip text + text box, output unchanged)
- `--mode layered` is the default ONLY via the orchestrator; legacy direct script
  invocations retain v1 defaults
- Manifest must declare `manifest_version` + `mode`; `slide-XX-bg.png` semantics are
  read from the manifest, never inferred from the filename
- Layered mode must NOT emit the v1 shim `export-layout.json` (build v1 would silently
  consume it and drop overlays)
- Validator is mode-aware — checks differ per mode
- Flat-mode regression tests are pinned in `test_export_stack.py` — P1/P2 changes must
  not alter v1 output

**Automatically chained pipeline:**

```
(0) Cache check
    │  key = sha(capture-slides.js) + sha(HTML+assets) + Playwright version pin
    │  match → skip capture, reuse existing renders
    │  --no-cache = escape hatch
    ▼
(a) capture-slides.js (multi-pass, single browser session)
    │  ├─ wait for document.fonts.ready (brand font fails to load → exit non-zero)
    │  ├─ single page.evaluate → {text[], objects[]} (DOM text layout + object inventory)
    │  ├─ pass REF-FULL → slide-XX-ref-full.png (parity reference tier-2)
    │  ├─ pass REF-NOTEXT → slide-XX-ref-notext.png (parity reference tier-1)
    │  ├─ pass BASE → slide-XX-bg.png (1920×1080, text + overlays hidden)
    │  ├─ pass OVERLAY (per group) → slide-XX-ov-<id>.png (transparent, 2× scale)
    │  ├─ pass TEXT-LAYER → slide-XX-text.png (text only, omitBackground)
    │  └─ write export-manifest.json (manifest_version, mode, slides, objects, text, z)
    ▼
(b) build_hybrid_pptx.py
    │  ├─ 1 base picture at slide bottom
    │  ├─ N overlay pictures (EMU bounds, unified z-order from manifest)
    │  ├─ native text boxes (accurate lineHeight, text-transform: uppercase)
    │  ├─ (P2) native autoshapes + svgBlip
    │  └─ crashes only on operational errors (missing renders / unparseable manifest)
    ▼
(c) compose candidate (PIL-only, no second browser launch)
    │  tier-1 = bg + ov-*.png by bounds/z
    │  tier-2 = tier-1 + text.png
    ▼
(d) compare_renders.py (always exit 0 — NOT a gate)
    │  tier-1 candidate vs ref-notext.png
    │  tier-2 candidate vs ref-full.png
    │  emits report.json + evidence
    ▼
(e) validate_export_objects.py ← THE SINGLE QA GATE
    │  ├─ manifest vs JSON Schema (manifest_version, mode, slides)
    │  ├─ PPTX structure: picture count, shape names, bounds ±0.02in, text count, z-order
    │  ├─ report.json vs thresholds (from registries/export-qa-thresholds.json):
    │  │     tier1: max_mean_err=0.5, max_changed_ratio=0.01
    │  │     tier2: max_mean_err=1.0, max_changed_ratio=0.01
    │  │     overlay coverage: max_ratio=0.85
    │  ├─ anti-loophole: untagged visuals → FAIL (escape: --allow-untagged)
    │  ├─ anti-loophole: overlay ≥85% canvas → FAIL (escape: --allow-full-bleed)
    │  └─ exit 0 = PASS, exit 1 = FAIL
    ▼
(f) export-result.json (machine-readable pass/fail + metrics)
```

**3-layer model inside the PPTX:**
```
Layer 1 (Base)      → 1 background picture (solid, texture, gradient) — 1920×1080
Layer 2 (Overlay)   → N transparent PNG pictures — each object separate, own bounds + z
Layer 3 (Editable)  → native text boxes + native autoshapes — editable in PowerPoint
```

**4 QA layers:**
1. Content QA — exact text validation
2. Object QA — PPTX structure (count, names, bounds, z-order)
3. Render QA — capture fidelity (layered only)
4. Parity QA — visual similarity metrics (layered only)

**Cleanup:** `qa/export-renders/` images are deleted after parity passes. Kept: `qa-report.md`, metrics, checksums.

#### 10b. Export PDF

**Workflow:** `workflows/export-pdf.md`

| Priority | Renderer | When | Requires |
|----------|----------|------|----------|
| 1 | **Playwright MCP** | HTML → PDF (default) | Claude Code built-in |
| 2 | **LibreOffice** | PPTX → PDF | `capabilities.json → libreoffice.status == available` |
| 3 | **Cannot render** | Both unavailable | Record as blocker |

### Step 11 — Package & Delivery

**Workflow:** `workflows/package-delivery.md` | **Script:** `package_job.py`

1. Validate run manifest
2. Verify exports and QA reports exist
3. Compute checksums for final artifacts
4. Write delivery report: paths, tests, limitations, overrides
5. `package_job.py` creates the delivery manifest and auto-prunes empty directories

### Step 12 — Template Save Prompt (PPTX only, post-export)

**Workflow:** `workflows/save-as-template.md`

**Trigger conditions:**
- Hard keywords (case-insensitive): `extract full slide`, `extract full deck`, `clone`,
  `template`, `copy slide`, `lưu mẫu`, `save as template`
- Contextual inference: prompt clearly implies reuse intent (high confidence only)
- **Do NOT trigger:** on pure content-generation prompts, non-PPTX exports, or failed exports

**Prompt:** "Do you want to save this deck as a template for future reuse?"

**Flow if the user confirms:**
1. Choose slide(s): single-slide → use it; multi-slide → ask which ones
2. Name: `sun.template.<kebab-name>` (user override allowed)
3. Create folder `slide-system/library/templates/sun.template.<name>/`:
   - `visual.svg` — artwork without semantic text
   - `text-slots.json` — editable slot schema
   - `background.png` — rendered slide background
   - `preview/preview.html` + `preview/thumbnail.png`
   - `evidence/notes.md` + `evidence/source-with-text.svg`
   - `evidence/external-images.json` (if external images are used)
4. Validate: `validate_text_slots.py`
5. Rebuild catalog:
   ```bash
   .venv/bin/python3 slide-system/scripts/build_component_catalog.py
   .venv/bin/python3 slide-system/scripts/build_template_picker_data.py
   ```
6. Confirm to user

**Boundaries:**
- Never create a template without user confirmation
- Never overwrite an existing template (append suffix or ask for a different name)
- Never skip catalog rebuild
- One template = one slide layout

---

## 2. Complete Output Structure

```
outputs/slide-jobs/<job-id>/
├── requirements/
│   ├── job-requirements.json
│   └── capability-report.json
├── assets/                              ← job-wide, all runs reference this
├── runs/<run-id>/
│   ├── analysis/
│   │   ├── visual-requests.json         ← what visuals each slide needs
│   │   └── selection-report.json        ← which items chosen, scores, reasons
│   ├── build/
│   │   └── deck.html                    ← 1920×1080, tagged
│   ├── exports/
│   │   ├── deck.pptx                    ← final output
│   │   ├── deck.pdf                     ← if PDF was requested
│   │   └── export-result.json           ← pass/fail + metrics
│   ├── qa/
│   │   ├── parity/slide-NN/tier1/report.json
│   │   ├── parity/slide-NN/tier2/report.json
│   │   └── qa-report.md
│   ├── export-manifest.json             ← PPTX manifest
│   └── run-manifest.json                ← status, approval, inputs, outputs, checksums
└── (assets/ shared)
```

---

## 3. Core Scripts

| Script | Language | Role |
|--------|----------|------|
| `export_pptx.py` | Python | **Orchestrator** — single command runs the entire PPTX pipeline |
| `capture-slides.js` | Node.js | Render slides → PNG multi-pass + extract DOM text (Playwright) |
| `build_hybrid_pptx.py` | Python | Manifest → native PPTX objects (python-pptx) |
| `validate_export_objects.py` | Python | **The single QA gate** — checks manifest + PPTX structure + parity |
| `compare_renders.py` | Python | Measure parity metrics (always exit 0, not a gate) |
| `decompose_svg_objects.py` | Python | Split full-page SVG → fragments + tagged snippet.html |
| `measure_svg_groups.js` | Node.js | Measure group bboxes in Chromium (used by decompose) |
| `score_visual_items.py` | Python | Score visual candidates (75/55 thresholds) |
| `check_requirements.py` | Python | Validate requirements + capabilities |
| `package_job.py` | Python | Delivery manifest + prune empty directories |
| `build_component_catalog.py` | Python | Rebuild visual library review UI |
| `build_template_picker_data.py` | Python | Rebuild template picker data |
| `extract_editable_text_slots.py` | Python | Extract text from SVG → text-slots.json + visual.svg |
| `crop_svg_region.py` | Python | Crop full-page visual.svg → selected component region (source.region); re-normalizes text-slots |
| `publish_extraction.py` | Python | Move item from staging → published (gates component crop) |
| `export-pdf.js` | Node.js | PDF export via Playwright |

**Environment setup:**
```bash
# Auto-setup (idempotent, runs once on first use)
if [ ! -f .venv/bin/python3 ] || ! .venv/bin/python3 -c "import pptx, PIL, fitz" 2>/dev/null; then
  ./slide-system/scripts/setup.sh
fi

# All Python scripts run through the venv
.venv/bin/python3 slide-system/scripts/<script>.py [args]
```

**Prerequisites (user installs):** Python 3.10+, Node.js 18+
**Auto-installed by setup.sh:** python-pptx, Pillow, PyMuPDF, Playwright + Chromium

---

## 4. Registries

| File | Description |
|------|-------------|
| `capabilities.json` | Tool availability: node, python, playwright, libreoffice, pillow, pymupdf |
| `visual-library.json` | 200+ items (cards, templates, characters, icons, etc.) — published + staging |
| `export-qa-thresholds.json` | Parity thresholds + overlay coverage limits |
| `extraction-history.json` | Extraction history, deduplication guard |
| `extract-readiness.json` | Preflight checks for extraction |

---

## 5. Rules (Hard Constraints)

| Rule | File | Summary |
|------|------|---------|
| Background rendering | `background-rendering.md` | 3 layers: base-background / complex-overlay / editable-foreground. Never merge all into one background image. |
| Content fidelity | `content-fidelity.md` | Preserve wording/numbers/ordering. Never omit content for layout. Static slides by default. |
| Source authority | `source-authority.md` | 6-tier priority. Record overrides in manifest. Ask user on conflict. |
| Visual selection | `visual-selection.md` | Select by semantic intent before visual resemblance. Reject staging/deprecated. |
| Icon selection | `icon-selection.md` | Prefer brand pack icons. External only when the brand does not cover the concept. |
| Extraction methods | `extraction-methods.md` | PDF → convert_pdf_source.py (PyMuPDF only). Never render PDF page → PNG. Reusable SVG must contain no semantic text. |
| Naming & versioning | `naming-versioning.md` | ID: `sun.<type>.<kebab-name>`. Version: semver 1.0.0. |
| Approval gates | `approval-gates.md` | One gate before build. Template save requires explicit confirmation. |
| Export compatibility | `export-compatibility.md` | Per-item compatibility levels: supported / hybrid / raster / unsupported / untested per format. |
| Editable text slots | `editable-text-slots.md` | Slot schema contract for templates. |

---

## 6. Schemas

| Schema | Description |
|--------|-------------|
| `job-requirements.schema.json` | job_id, brand_pack, base_template, inputs, authority, exports, editability, visual_needs, fonts, effects, required_tools, approvals, overrides |
| `visual-item.schema.json` | id (`sun.<type>.<name>`), version, intent[], text_contract, compatibility (html/pptx/pdf/canva), source, paths |
| `text-slots.schema.json` | Slot: id, role, editable (const true), allow_empty (const true), bounds, text_style |
| `run-manifest.schema.json` | status, approval, inputs, outputs, checksums |
| `capabilities.schema.json` | Tool: status, path, version, fingerprint |
| `selection-report.schema.json` | Per-section: item selected, score, reason, rejected candidates |
| `extraction-report.schema.json` | Extraction metadata + validation results |
| `extraction-request.schema.json` | Request: source, page, region, type |
| `export-manifest.schema.json` | Manifest: manifest_version, mode, slides[], base, objects[], text[] (at `scripts/_reference/`) |

---

## 7. Brand Pack & Visual Library

**Current brand pack:** `sun-studio/` (default)
- Manifest: `slide-system/brand-packs/sun-studio/manifest.json`
- Canonical assets: `.agents/skills/sun-studio-design-system/assets/system/`
- Includes: fonts, color tokens (CSS), logo, character assets (Dio), selection rules, licensing

**Visual library:** `registries/visual-library.json`
- 200+ items — types: card, component, section, template, style, icon, background, character, asset
- Status: `published` (usable) / `staging` (pending approval) / `deprecated` (rejected)
- Each item has: id, version, intent[], compatibility, source, paths (artifact, visual, text_slots, preview)

**Template library:** `slide-system/library/templates/`
- Current: `interview-workshop-sunriser/` (12 layouts: cover, timeline, overview, etc.)
- Each layout: `visual.svg` + `text-slots.json` + `background.png` + `preview/` + `evidence/`

**Template picker UI:** `slide-system/template-picker/index.html`
- Browse grouped template sets, full deck preview, filmstrip navigation
- Click slide → copy prompt; click set → copy whole-set prompt

**Catalog UI:** `slide-system/catalog/index.html`
- Review published + staging items, grouped by type/category
- Preview images, text slots, compatibility badges

---

## 8. Agent Boundaries

| Prohibited | Reason |
|------------|--------|
| Publish or extract components inline | Hand off to `/component-extractor` |
| Select staging / deprecated / export-incompatible items | Published only |
| Modify the export pipeline | Use `export_pptx.py` as-is |
| Hand-stitch PPTX steps | `export_pptx.py` chains automatically |
| Wrap a whole-page SVG in one overlay tag | Decomposer handles it; gate FAILS ≥85% coverage |
| Hand-split SVG (static bbox math ignores transforms) | Decomposer uses Chromium measurement |
| Skip catalog rebuild after template save | Hard rule |
| Merge multiple layouts into one template | One template = one layout |
| Copy assets per run | Reference in-place |
| Create empty directories | `package_job.py` auto-prunes |
| Assume `--mode flat` | Default is `--mode layered` |
| Export a format not chosen at intake | Export only confirmed formats |
| Describe a full-image deck as "editable" | Gate enforces this |
| Trigger extraction inline | Only record recommendations |

---

## 9. Capability Summary

When a user invokes `/slide-generator`, the agent can:

1. **Create a complete slide deck** from a prompt, brief, or mixed input (text + files + URL)
2. **Polish or redesign** an existing deck from PPTX or PDF
3. **Rebuild** from a screenshot or image reference (reconstruction or redesign)
4. **Iterate** on a previous job (edit specific slides without re-interviewing)
5. **Rebrand or localize** a deck to a different brand pack or language
6. **Convert raw data** (documents, tables, numbers) into slides (delegates to `ppt-master`)
7. **Advise** when the user is unsure where to start → guided questioning → folds into creation
8. **Use an existing template** as the base layout (browse picker → select → build from template)
9. **Export editable PPTX** with the 3-layer model (text and shapes editable in PowerPoint)
10. **Export PDF** via Playwright or LibreOffice
11. **Automated QA** across 4 layers: content, object, render, parity
12. **Save as template** from the newly created deck for future reuse (only on user confirmation)

---

## 10. Non-Interactive Guard

This workflow requires a live user. In a non-interactive context (CI, scheduled run, loop) with an incomplete brief, STOP and report missing information as a blocker instead of guessing.
