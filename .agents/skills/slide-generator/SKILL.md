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

Before running any Python script, use the repository virtual environment. On
Windows the interpreter is `.venv\Scripts\python.exe`; on macOS/Linux it is
`.venv/bin/python3`. If it is missing or cannot import `pptx`, `PIL`, and
`fitz`, run the matching local setup script and report any actionable error:

```powershell
powershell -ExecutionPolicy Bypass -File .\slide-system\scripts\setup.ps1
```

```bash
./slide-system/scripts/setup.sh
```

Run every Python command through that platform-specific project interpreter.
Never fall back to WindowsApps `python3`, a global Python, or a different venv.

## Absolute Prohibitions (enforced by script gates)

1. **NO emoji icons.** Use published shared SVG icons or slide-local SVGs.
   Gate: `validate_brand_compliance.py`.
2. **NO random colors.** Use ONLY CSS variables from brand tokens
   (`var(--sun-orange)`, `var(--ink)`, etc.). Gate fails >5 non-brand colors.
3. **NO hand-written selection reports.** Run `score_visual_items.py` — never
   fabricate `selection-report.json`. Gate: `validate_selection_report.py`.
4. **Published-only visuals.** When scorer says `reuse`, pass the item path to
   `decompose_svg_objects.py` and use the emitted `snippet.html` fragments. A
   `text-only` decision must render only the approved copy; never invent a
   slide-local visual, component, or Draft.
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
   - **New-job isolation:** Do not read `docs/logs/` or another job under
     `outputs/slide-jobs/` to judge current library fit, copy a prior deck, or
     reuse a prior selection report. Historical logs are process history, not
     generation input. Read them only when the user explicitly asks to resume
     that named job.
   - A new brief needs a fresh job/run path. If its `deck.html` or
     `analysis/selection-report.json` already exists, stop and ask whether to
     resume that run or create a new version; never silently build over it.
4. **Requirements check.** Run `check_requirements.py` against capabilities.
5. **Stop on blockers** unless user approves override.
6. **Content analysis** and source authority.
7. **Score visual library (BLOCKING).** Write `analysis/visual-requests.json`
   (one entry per slide with `intent`, `tags`, `content_structure`; add
   `item_count` when the slide carries N parallel items — the scorer
   penalizes set-of-N mismatches), then:
   ```bash
    <project-python> slide-system/scripts/score_visual_items.py \
       --batch-request <run>/analysis/visual-requests.json \
       --output <run>/analysis/selection-report.json
   ```
   Score ALL types (templates + standalone components). Pass
   `--prefer-set <set>` when brief has `base_template`. The scorer
   auto-reads `registries/component-retrieval-index.jsonl` for broadened
   (capped) lexical matching plus anti-use-case / count-fit / zero-slot
   penalties; read each candidate's `retrieval` block and `reasons` when
    reviewing decisions. Score ranks candidates but is not an approval floor:
    reuse the top published candidate that passes editable-content, count, and
    content-shape gates. A source-topic mismatch is emitted as a warning for
    review, not a selection blocker. Otherwise the action is `text-only`;
    candidates remain suggestions for a user-approved future extraction, never
    an automatic build instruction.
   The scorer owns this file: never edit `selection-report.json`, add
   `curation_note`/`scorer_*` fields, or relabel a decision. If the selected
   item has a real geometry or domain defect, show it during the approval step
   and regenerate the requests/report after the decision rather than mutating
   scorer output.
8. **Validate selection (BLOCKING GATE).**
   ```bash
    <project-python> slide-system/scripts/validate_selection_report.py \
       --selection-report <run>/analysis/selection-report.json \
       --visual-requests <run>/analysis/visual-requests.json
   ```
   EXIT 0 required. EXIT 1 = fix and re-run step 7.
9. **Plan reusable-slot copy (BLOCKING for reuse).** For every `reuse`
   decision, create `<run>/analysis/slot-content-plan.json` using the selected
   component's actual slot ids from `read_text_slots.py --with-typography`.
   Use only compact display copy that belongs in the native layout; leave
   unused slots empty and put detailed explanation in speaker notes or a
   follow-up slide. Never solve capacity by shrinking below the native
   projection floor, moving geometry, or filling every slot.
   **Inside a repeated unit (card, step, column, strip cell): one short label
   plus at most one compact support line.** Extraction splits the original
   card's wrapped paragraph into one slot per drawn line, so a card with five
   slots is still a one-label surface — filling all of them projects as narrow
   ragged columns and the gate rejects it. Detail goes to `speaker_notes`.
   **An explanation of a parallel item goes in that item's native slot or in
   `speaker_notes` — never into an ad-hoc caption positioned near the
   component.** A component's artwork is drawn to its own bounds and reaches
   into space that looks empty in the HTML, so a caption placed above/below the
   band lands on the artwork. The post-capture `text_over_artwork` gate rejects
   that, and z-index does not fix it.
   Validate:
   ```bash
   <project-python> slide-system/scripts/validate_slot_content_plan.py \
       --plan <run>/analysis/slot-content-plan.json \
       --selection-report <run>/analysis/selection-report.json \
       --out <run>/qa/slot-content-plan-report.json
   ```
   Read `slide-system/rules/component-content-fit.md` for the contract.
   `text-only` slides need no plan entry.
10. **Build HTML.** A normal slide job does not wait for component selection.
   - Copy `slide-system/boilerplates/deck_stage.js` to `<run>/deck_stage.js`,
     load it with `<script src="deck_stage.js"></script>`, and place every
     `<section>` inside `<deck-stage width="1920" height="1080">`. Do not
     hand-roll fixed-canvas navigation or scaling.
    - **Reuse slides:** scaffold from the component — do NOT redraw.
      Run `scaffold_slide_from_component.py --item-id <id>` for a fragment with
      the real `.bg` + `.slot` structure (from `preview.html`), then fill text
      into the slots. Decompose artwork via `decompose_svg_objects.py` (it reads
      the SVG); get slot metadata via `read_text_slots.py --slots-only`. Never
      `Read` `visual.svg`/`text-slots.json` directly.
    - **Text-only slides:** render the approved title/body in a simple readable
      text layout. Do not add an invented visual, icon, decorative treatment,
      or Draft. Keep `candidates` and `extraction_recommended` as suggestions
      for the end user; create/extract a component only after their explicit
      approval in the manual component workflow.
    - Tag ALL visuals with `data-export-layer`/`data-export-id` for PPTX.
    - Declare each text item's placement: native slots carry `data-slot-id`
      (kept by the scaffold); mark chrome `data-placement="chrome"` and free
      slide text `data-placement="external"`. Only native slots may sit on
      their component's artwork; everything else must clear it geometrically.
      Keep bands/overlays below valid chrome, and set explicit z-order only
      after the geometry is valid.
    - Full-page SVGs MUST go through `decompose_svg_objects.py` first.
    - Canvas: `1920×1080`. Keep text in leaf elements. Keep editable.
    - Before export, every local `img`, `href`, and CSS `url()` asset must
      resolve from the run. Do not leave a decomposer snippet pointing at an
      asset directory that was never generated.
11. **Validate brand compliance (BLOCKING GATE).**
    ```bash
    <project-python> slide-system/scripts/validate_brand_compliance.py \
        --html <run>/deck.html \
        --selection-report <run>/analysis/selection-report.json \
        --brand-pack slide-system/brand-packs/sun-studio/manifest.json
    ```
    EXIT 0 required. EXIT 1 = fix HTML and re-validate.
    Then run the component-fidelity gate (T3) — confirms `reuse`
    slides actually use their selected component, not just a marker:
    ```bash
    <project-python> slide-system/scripts/validate_component_fidelity.py \
        --html <run>/deck.html \
        --selection-report <run>/analysis/selection-report.json \
        --registry slide-system/registries/visual-library.json --warn
    ```
    Runs in `--warn` mode during rollout (always exits 0); drop `--warn` to
    make it blocking once existing decks are rebuilt from scaffold.

    Slot-id coverage proves the component was *used*; it does not prove the
    slide is *readable*. Export runs a second, blocking pass on the capture
    manifest (`--export-manifest`) that fails on overlapping text, text under
    3.0:1 contrast against the rendered background, and overlays placed off the
    canvas. When it fires: shorten or scale the copy inside its own native
    slot, or — if the component has no viable placement — treat it as
    non-buildable and select another. Never move or redraw component geometry,
    and never hand-draw a replacement for artwork that would not render.
12. **Export PPTX.** Single command:
    ```bash
    <project-python> slide-system/scripts/export_pptx.py \
        --html <run>/deck.html --slides <N> --out-dir <run> \
        --output <run>/<name>.pptx --mode layered
    ```
    For a normal slide-job run with `analysis/selection-report.json`, export
    re-runs selection, deck-stage, brand, and component-fidelity gates before
    capture, then the render-legibility gate on the capture manifest before the
    PPTX is built. `validate_export_objects.py` remains the export-object
    pass/fail gate after capture.
13. **Cleanup (MANDATORY).** Run after export PASS:
    ```bash
    <project-python> slide-system/scripts/cleanup_run.py <run>
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

When scorer says `reuse`:
1. Take the item path **verbatim** from `selection-report.json` / the registry
   `paths` (`paths.visual`, `paths.preview`). Do NOT glob `library/` — that risks
   Reading the 12 MB SVGs. Library items are flat: `<item-dir>/visual.svg`,
   `<item-dir>/text-slots.json`, `<item-dir>/preview/preview.html`. There is no
   `artifact/` subdirectory.
2. Scaffold the slide structure from the component's `preview.html`:
   ```bash
    <project-python> slide-system/scripts/scaffold_slide_from_component.py \
       --item-id <id> --registry slide-system/registries/visual-library.json \
       --out <job>/assets/page-NN/fragment.html
   ```
3. Decompose the artwork SVG (the script reads it — you never do):
   ```bash
    <project-python> slide-system/scripts/decompose_svg_objects.py \
       --svg <library-path>/visual.svg \
       --out-dir <job>/assets/page-NN --prefix page-NN \
       --href-base <relative-path-from-deck.html>
   ```
4. Paste `snippet.html` into the slide div; set the base art as CSS
   `background-image` (no overlay tag). Fill text slots by role/id using:
   ```bash
    <project-python> slide-system/scripts/read_text_slots.py \
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
- When no published item fits, render approved text only and record the ranked
  candidates plus an extraction recommendation. Never create a local visual or
  trigger extraction without explicit end-user approval.
- Never select staging, deprecated, or export-incompatible items.
- Use SUN.STUDIO brand pack by default unless user selects another.
