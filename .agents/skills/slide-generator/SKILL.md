---
name: slide-generator
description: Orchestrate AI slide generation from prompts, files, or mixed inputs. Interpret natural-language output requests, default PowerPoint/PPT/PPTX requests to editable PPTX, check requirements, plan content, select published visual items, build HTML, export PPTX/PDF, and run QA.
---

# Slide Generator

## Conditional Reading (read ONLY when needed)

- `slide-system/workflows/save-as-template.md` — ONLY when template save
  prompt fires (step 12).
- `slide-system/rules/background-rendering.md` — ONLY when raster
  backgrounds or complex visual overlays are involved.
- `slide-system/workflows/resume-job.md` — ONLY when iterating an existing run.

Everything else you need is in this file. Do NOT read other workflow or rule
docs unless explicitly referenced above.

## Environment Auto-Setup

Before running any Python script, check that `.venv` exists and has the
required packages. If not, bootstrap it silently:

```bash
if [ ! -f .venv/bin/python3 ] || ! .venv/bin/python3 -c "import pptx, PIL, fitz" 2>/dev/null; then
  ./slide-system/scripts/setup.sh
fi
```

Run all `python3` commands through: `.venv/bin/python3 slide-system/scripts/<script>.py [args]`

## Absolute Prohibitions (enforced by script gates)

1. **NO emoji icons.** Use published shared SVG icons or slide-local SVGs.
   Gate: `validate_brand_compliance.py`.
2. **NO random colors.** Use ONLY CSS variables from brand tokens
   (`var(--sun-orange)`, `var(--ink)`, etc.). Gate fails >5 non-brand colors.
3. **NO hand-written selection reports.** Run `score_visual_items.py` — never
   fabricate `selection-report.json`. Gate: `validate_selection_report.py`.
4. **NO skipping published components.** When scorer says `reuse` (≥75) or
   `adapt-local`, pass the item path to `decompose_svg_objects.py` and use the
   emitted `snippet.html` fragments. No raw CSS, no eyeballing the layout.
5. **NEVER `Read`/`cat` heavy library files into context.** `visual.svg` (up to
   12 MB, ~100% base64 PNG), `text-slots.json` (up to ~120 KB), `evidence/*`,
   `preview/*`, `catalog-data.json`, `picker-data.json`. Route them through
   scripts — `decompose_svg_objects.py` for the SVG,
   `read_text_slots.py --slots-only` for slots — and consume only the compact
   output. A single literal Read of one of these can blow the context window.

## Pipeline

1. **Intake.** Treat user as non-tech. Ask one question at a time with a
   guess attached. Cap at ~5-6 questions; fill rest with defaults. Normalize
   "PowerPoint/PPT/PPTX" → editable `.pptx` layered mode. Detect case:
   new-from-brief | polish | rebuild | iterate | rebrand | raw-data.
   For details on case routing: `slide-system/workflows/intake-and-triage.md`.
2. **Recap gate.** Plain-language brief recap. Wait for user confirmation.
3. **Job setup.** Create job + versioned run under `outputs/slide-jobs/`.
4. **Requirements check.** Run `check_requirements.py` against capabilities.
5. **Stop on blockers** unless user approves override.
6. **Content analysis** and source authority.
7. **Score visual library (BLOCKING).** Write `analysis/visual-requests.json`
   (one entry per slide with `intent`, `tags`, `content_structure`; add
   `item_count` when the slide carries N parallel items — the scorer
   penalizes set-of-N mismatches), then:
   ```bash
   .venv/bin/python3 slide-system/scripts/score_visual_items.py \
       --batch-request <run>/analysis/visual-requests.json \
       --output <run>/analysis/selection-report.json
   ```
   Score ALL types (templates + standalone components). Pass
   `--prefer-set <set>` when brief has `base_template`. The scorer
   auto-reads `registries/component-retrieval-index.jsonl` for broadened
   (capped) lexical matching plus anti-use-case / count-fit / zero-slot
   penalties; read each candidate's `retrieval` block and `reasons` when
   reviewing decisions. Score != buildability — still verify
   geometry/count/domain fit before building a reuse/adapt slide.
8. **Validate selection (BLOCKING GATE).**
   ```bash
   .venv/bin/python3 slide-system/scripts/validate_selection_report.py \
       --selection-report <run>/analysis/selection-report.json \
       --visual-requests <run>/analysis/visual-requests.json
   ```
   EXIT 0 required. EXIT 1 = fix and re-run step 7.
9. **Approval.** Show scorer decisions (reuse/adapt/custom per slide).
10. **Build HTML** (after approval only).
    - **Reuse/adapt-local slides:** scaffold from the component — do NOT redraw.
      Run `scaffold_slide_from_component.py --item-id <id>` for a fragment with
      the real `.bg` + `.slot` structure (from `preview.html`), then fill text
      into the slots. Decompose artwork via `decompose_svg_objects.py` (it reads
      the SVG); get slot metadata via `read_text_slots.py --slots-only`. Never
      `Read` `visual.svg`/`text-slots.json` directly.
    - **Custom-local slides:** build from scratch with brand rules:
      colors=CSS vars only, font=Proxima Nova only, icons=SVG only.
    - Tag ALL visuals with `data-export-layer`/`data-export-id` for PPTX.
    - Full-page SVGs MUST go through `decompose_svg_objects.py` first.
    - Canvas: `1920×1080`. Keep text in leaf elements. Keep editable.
11. **Validate brand compliance (BLOCKING GATE).**
    ```bash
    .venv/bin/python3 slide-system/scripts/validate_brand_compliance.py \
        --html <run>/deck.html \
        --selection-report <run>/analysis/selection-report.json \
        --brand-pack slide-system/brand-packs/sun-studio/manifest.json
    ```
    EXIT 0 required. EXIT 1 = fix HTML and re-validate.
    Then run the component-fidelity gate (T3) — confirms `reuse`/`adapt-local`
    slides actually use their selected component, not just a marker:
    ```bash
    .venv/bin/python3 slide-system/scripts/validate_component_fidelity.py \
        --html <run>/deck.html \
        --selection-report <run>/analysis/selection-report.json \
        --registry slide-system/registries/visual-library.json --warn
    ```
    Runs in `--warn` mode during rollout (always exits 0); drop `--warn` to
    make it blocking once existing decks are rebuilt from scaffold.
12. **Export PPTX.** Single command:
    ```bash
    .venv/bin/python3 slide-system/scripts/export_pptx.py \
        --html <run>/deck.html --output <run>/<name>.pptx --mode layered
    ```
    `validate_export_objects.py` is the pass/fail gate.
13. **Cleanup (MANDATORY).** Run after export PASS:
    ```bash
    .venv/bin/python3 slide-system/scripts/cleanup_run.py <run>
    ```
    This deletes parity images, intermediate PNGs, compacts manifests.
    A finished run should contain ONLY:
    - `deck.html` — the built deck
    - `<name>.pptx` — exported presentation
    - `analysis/selection-report.json` — scorer output
    - `export-manifest.json` — compact export metadata
14. **Template save prompt (PPTX only).** Check for template-intent signals
    (`template`, `clone`, `lưu mẫu`, `save as template`). If found, ask user.
    Follow `workflows/save-as-template.md` for the flow.

## Token Optimization Rules

- **Do NOT read workflow/rule docs** unless listed in Conditional Reading.
  This file is self-contained for the standard pipeline.
- **Minimize file creation.** A run needs: deck.html, .pptx, selection-report.
  Everything else is intermediate — create only if needed, delete after.
- **No separate approval-package.md** — present approval inline in chat.
- **No per-section files.** One visual-requests.json, one selection-report.json.
- **No scaffolding dirs.** Never `mkdir` before having content.
- **No intermediate reports.** Don't create delivery-manifest.json,
  validation.json, export-result.json — the cleanup script removes them anyway.
- **Run cleanup_run.py** at the end of every successful export.
- **Reuse job-level assets.** Brand fonts/icons/images from brand pack.
  Job assets in `<job-id>/assets/`. Runs never re-copy.
- **Compact manifests.** Export-manifest should be <10KB. Strip per-pixel
  parity data and intermediate checksums.

## Component/Template Build Reference

When scorer says `reuse` or `adapt-local`:
1. Take the item path **verbatim** from `selection-report.json` / the registry
   `paths` (`paths.visual`, `paths.preview`). Do NOT glob `library/` — that risks
   Reading the 12 MB SVGs. Library items are flat: `<item-dir>/visual.svg`,
   `<item-dir>/text-slots.json`, `<item-dir>/preview/preview.html`. There is no
   `artifact/` subdirectory.
2. Scaffold the slide structure from the component's `preview.html`:
   ```bash
   .venv/bin/python3 slide-system/scripts/scaffold_slide_from_component.py \
       --item-id <id> --registry slide-system/registries/visual-library.json \
       --out <job>/assets/page-NN/fragment.html
   ```
3. Decompose the artwork SVG (the script reads it — you never do):
   ```bash
   .venv/bin/python3 slide-system/scripts/decompose_svg_objects.py \
       --svg <library-path>/visual.svg \
       --out-dir <job>/assets/page-NN --prefix page-NN \
       --href-base <relative-path-from-deck.html>
   ```
4. Paste `snippet.html` into the slide div; set the base art as CSS
   `background-image` (no overlay tag). Fill text slots by role/id using:
   ```bash
   .venv/bin/python3 slide-system/scripts/read_text_slots.py \
       --item <library-path> --slots-only
   ```
   (never `Read` `text-slots.json` whole — it is up to ~120 KB).

## Standalone Item Rules

- **Logo** (`sun.asset.logo`): cover + closing only, top-left or centered,
  120–180px width, above background / below text.
- **Dio** (`sun.character.dio`): section dividers and emphasis slides,
  bottom corner, 80–140px. Variants: normal/side-glance/wink/annoyed/
  dancing/bored/bewildered.
- **Icons**: use published shared SVG icons or slide-local inline SVGs. NEVER
  use emoji.

## Brand Tokens (SUN.STUDIO)

Primary: `--sun-orange:#FF5533`, `--sun-blue:#3333FF`, `--ink:#171717`
Extended: `--sun-orange-soft:#FFF3EF`, `--sun-blue-soft:#F4F5FF`,
`--muted:#666666`, `--line:#E7E7E7`, `--soft:#FAFAFA`, `--paper:#FFFFFF`
Font: `"Proxima Nova"` (300–900 weights)
Canvas: `1920×1080`, `16:9`

## Boundaries

- Never extract/publish shared components. Recommend `/component-extractor`.
- When no published item fits, use slide-local and record extraction rec.
- Never select staging, deprecated, or export-incompatible items.
- Use SUN.STUDIO brand pack by default unless user selects another.
