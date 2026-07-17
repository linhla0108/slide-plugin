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
4. **NO skipping published components, NO forcing weak ones.** When scorer says
   `reuse`, scaffold from that exact component (materialize + declared slots + fidelity).
   When it says `needs_component`, the slide is UNRESOLVED — do NOT invent a custom
   layout and do NOT force an unrelated component; take it to the user for library
   review (step 9). `adapt-local` is retired; `custom-local` requires explicit user
   approval.
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
   (one entry per slide with `intent`, `tags`, `content_structure`, a REQUIRED
   `content_shape` — one of the shapes in the shared `SHAPE_TYPE_MAP` in
   `slide-system/scripts/_common.py`, which the scorer and validator share; it
   drives shape-aware candidate eligibility — and a REQUIRED non-empty `concepts`:
   a list of semantic concept GROUPS (OR alternatives within a group, AND across
   groups) derived from the slide's PURPOSE, using the canonical vocabulary. e.g.
   a role-cards slide → `[["role","persona","audience"],["card","card-set"]]`.
   Concept coverage (matched_groups/total_groups) is the required semantic
   denominator; `intent`/`tags` then only rank/retrieve, so a synonym or descriptor
   never dilutes the match. Author concepts generically — NEVER invent
   source-specific text. Add `item_count` when the slide carries N parallel items),
   then:
   ```bash
    <project-python> slide-system/scripts/score_visual_items.py \
       --batch-request <run>/analysis/visual-requests.json \
       --require-concepts \
       --output <run>/analysis/selection-report.json
   ```
   `--require-concepts` makes concepts mandatory (the normal new-run contract);
   omit it ONLY for an old/resumed run whose requests predate concepts (legacy
   compatibility). Automatic `reuse` requires BOTH a semantic concept match AND a
   reviewed generic-buildable component (`build_scope.mode == "generic"` — a
   template a short brief can actually fill). A SOURCE-SPECIFIC or unreviewed item
   stays published + manually selectable but is NOT auto-reused: a high semantic
   score alone never auto-picks a specific published slide (dates/names/context
   slots). Such a slide resolves `needs_component` — do NOT force it.
   Score ALL types (templates + standalone components). Pass
   `--prefer-set <set>` when brief has `base_template`. The scorer
   auto-reads `registries/component-retrieval-index.jsonl` for broadened
   (capped) lexical matching plus anti-use-case / count-fit / zero-slot
   penalties; read each candidate's `retrieval` block and `reasons` when
   reviewing decisions. If the top raw scorer is below the semantic floor, the
   decision may choose the best valid runner-up; review the emitted selected
   candidate rather than assuming `candidates[0]` is always the decision.
   Score != buildability — still verify geometry/count/domain fit before
   building a `reuse` slide.
   The scorer owns this file: never edit `selection-report.json`, add
   `curation_note`/`scorer_*` fields, or relabel a decision. If the selected
   item has a real geometry or domain defect, show it during the approval step
   and ask the user whether to proceed; regenerate the requests/report after
   the decision rather than mutating scorer output.
8. **Validate selection (BLOCKING GATE).**
   ```bash
    <project-python> slide-system/scripts/validate_selection_report.py \
       --selection-report <run>/analysis/selection-report.json \
       --visual-requests <run>/analysis/visual-requests.json \
       --strict-shape
   ```
   EXIT 0 required. EXIT 1 = fix and re-run step 7. `--strict-shape` makes a
   missing or unknown `content_shape` a hard failure, so shape-aware selection
   is always enforced in the normal workflow (never silently skipped).
8b. **Style profile (OPTIONAL).** Only when the job's `style_profile` is set
    (explicit `profile_id` + `path`; never load another user's profile
    implicitly). Validate it, then record its influence in a design-plan artifact
    — it never mutates `selection-report.json`:
    ```bash
     <project-python> slide-system/scripts/validate_style_profile.py --profile <path>
     <project-python> slide-system/scripts/resolve_style_profile.py \
        --profile <path> \
        --selection-report <run>/analysis/selection-report.json \
        --registry slide-system/registries/visual-library.json \
        --output <run>/analysis/design-plan.json
    ```
    The profile influences ONE thing: how you compose a slide the user already
    approved as `custom-local`. `score_visual_items.py` does NOT read the profile —
    any `tie_break_advisories` in the design plan are non-binding notes, not
    selections. It must never override source content, SUN.STUDIO tokens,
    readability, canvas bounds, published-only retrieval, or component fidelity.
    Precedence and boundaries: `slide-system/rules/style-profiles.md`. Apply only
    the `applied_preferences` from `design-plan.json` when composing custom-local
    slides; honour every `rejected_preferences` reason.
9. **Approval + library review.** Show scorer decisions per slide: `reuse`
   (high-confidence auto or explicit), `needs_component` (unresolved), or
   `custom-local` (only if the user already approved it). For each
   `needs_component` slide, show ONLY the catalog-safe pointer — its
   `request_id`, `suggested_search`, `shortlist` (top safe candidate ids), and
   `next_action`. NEVER surface the internal `decision.reason` to the user: it is
   an internal diagnostic that stays in `selection-report.json` for catalog /
   library review only. Then let the user:
   - open the catalog (`catalog/catalog_server.py`, http://127.0.0.1:8799/), search
     + preview published components, and **Copy ID** or **Copy prompt**;
   - paste that into the slide's `component_id` (a stable id or the copied prompt)
     and re-run steps 7–8 to reuse it; OR
   - set `unresolved_policy: "custom-local"` to approve a custom slide as a last
     resort; OR set `unresolved_policy: "blank"` to leave the slide deliberately blank.
   Until EVERY slide is resolved this way, the job is UNRESOLVED
   (`awaiting_component_selection`): the delivery gate produces NO deck / PPTX / PDF.
   **The artifact the user edits and re-submits is `<run>/analysis/visual-requests.json`**
   (contract: `slide-system/schemas/visual-requests.schema.json`; slide selections do
   NOT live in `job-requirements.json`). The scorer validates it in code before
   scoring — every field and type the schema declares — and exits non-zero with a
   plain reason, writing no report, on a bad `component_id` / `allow_component_reuse` /
   `unresolved_policy` / `content_shape`.
   A component is never auto-reused twice; to reuse one deliberately, set
   `allow_component_reuse: true` on that slide. A component recorded as
   `auto_reuse.eligible: false` (failed full-slide QA) is browseable but never
   auto-selected, and its build is rejected by the fidelity gate — the catalog shows
   it as **Review-only** with the reason, and disables its Copy prompt. When a style
   profile is active, also show applied vs rejected preferences from
   `design-plan.json`.
10. **Build HTML** (after approval only).
    - **`reuse` slides:** scaffold from the component — do NOT redraw. Run
      `scaffold_slide_from_component.py --item-id <id>` for a fragment with the real
      `.bg` + `.slot` structure (from `preview.html`), then fill text into the
      slots. Decompose artwork via `decompose_svg_objects.py` (it reads the SVG);
      get slot metadata via `read_text_slots.py --slots-only`. Never `Read`
      `visual.svg`/`text-slots.json` directly.
      **Every slot you fill must read as a complete unit.** Slots are disconnected
      regions of artwork, not a sentence — never split one phrase across two of them
      (no slot metadata declares a continuation/group relationship, and `required` is
      false everywhere). Leave a slot empty when it only existed to continue the
      source's phrase: `allow_empty` is true on every slot, and coverage is not a
      score to maximise. Read the hierarchy off `role`/`html_tag`/`example_value`/
      `bounds` before writing a word. If the component's geometry cannot carry the
      content coherently, pick another published component or leave the request
      `needs_component` — passing the overflow gate proves text fits its box, never
      that the slide reads. Full rule: `workflows/build-html-deck.md`.
    - **`needs_component` slides:** UNRESOLVED — do NOT invent a layout, force a
      component, or emit a diagnostic placeholder. The job is not a deliverable:
      stop at this gate for the user to resolve it (above). Only an explicit
      `unresolved_policy: "blank"` produces a slide, and that slide is deliberately
      EMPTY — never render the component id, audit `reason`, `suggested_search`, or
      any QA text into the deck. Those stay in `selection-report.json` for catalog /
      library review only.
    - **`custom-local` slides (explicit user approval ONLY):** build from scratch
      with brand rules: colors=CSS vars only, font=Proxima Nova only, icons=SVG
      only. Mark them visibly as custom in the job plan; never report as reuse.
    - Tag ALL visuals with `data-export-layer`/`data-export-id` for PPTX.
    - Full-page SVGs MUST go through `decompose_svg_objects.py` first.
    - Canvas: `1920×1080`. Keep text in leaf elements. Keep editable.
    - **Paginate multi-slide decks** so the export isolates one slide per frame:
      each `.slide` absolutely positioned + `display:none`, `.slide.active { display:block }`,
      and a global `goToSlide(n)` that toggles `.active` (add an `@media print` rule
      that un-paginates — `position:static; display:block; page-break-after:always` —
      so the PDF prints every slide). The default export command auto-detects this
      `.slide` + `goToSlide(n)` contract (or a `<deck-stage>`) and drives it — no
      `--showJs`/`--selector` needed; pass them only to override. A deck whose slides
      are all visible at once, or that offers no navigator, is REJECTED: `capture-slides.js`
      fails closed rather than capture slide 1 N times, and `build_hybrid_pptx.py`
      rejects a whole-deck or identical-frame manifest. `build_clone_deck.py` shows the pattern.
11. **Validate brand compliance (BLOCKING GATE).**
    ```bash
    <project-python> slide-system/scripts/validate_brand_compliance.py \
        --html <run>/deck.html \
        --selection-report <run>/analysis/selection-report.json \
        --brand-pack slide-system/brand-packs/sun-studio/manifest.json
    ```
    EXIT 0 required. EXIT 1 = fix HTML and re-validate.
    Then run the component-fidelity gate (T3) — confirms `reuse` slides actually
    use their selected component AND that the reused text renders
    readably (no clip/overflow/overlap, base artwork loaded). RELEASE gate uses
    real-browser evidence and fails closed:
    ```bash
    <project-python> slide-system/scripts/validate_component_fidelity.py \
        --html <run>/deck.html \
        --selection-report <run>/analysis/selection-report.json \
        --registry slide-system/registries/visual-library.json \
        --render --require-render
    ```
    `--require-render` (release) measures every component instance in Chromium,
    fails closed if node/playwright is unavailable, and requires each reused
    occurrence to carry a unique `data-component-instance` (fresh scaffolds emit
    it automatically). Overflowing/clipped/overlapping text or unloaded artwork
    fails — do NOT shrink text; route that slide to `custom-local` or shorter
    approved copy. Local diagnostics may use `--warn` (never for release) or plain
    `--render`. EXIT 0 required for release.
12. **Export PPTX.** Single command:
    ```bash
    <project-python> slide-system/scripts/export_pptx.py \
        --html <run>/deck.html --output <run>/<name>.pptx --mode layered
    ```
    Export first runs the delivery gate (`delivery_gate.py`): if the run's
    `analysis/selection-report.json` still holds any `needs_component` slide the
    job is UNRESOLVED and export refuses to build — resolve every slide first.
    `validate_export_objects.py` is then the pass/fail gate.
    **PDF export** (`workflows/export-pdf.md`) is bound by the SAME gate on every
    route. The `browser_pdf` (Playwright MCP) route does NOT go through the Node
    exporter, so run the gate preflight
    (`delivery_gate.py --deck <run>/deck.html`) BEFORE `browser_pdf`: a tracked
    job that exits non-zero produces NO PDF — do not call `browser_pdf`.
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

When scorer says `reuse` (auto high-confidence or explicit user selection):
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
- When no published item fits, use slide-local and record extraction rec.
- Never select staging, deprecated, or export-incompatible items.
- Use SUN.STUDIO brand pack by default unless user selects another.
