---
name: slide-generator
description: Orchestrate AI slide generation from prompts, files, or mixed inputs. Interpret natural-language output requests, default PowerPoint/PPT/PPTX requests to editable PPTX, check requirements, plan content, select published visual items, build HTML, export PPTX/PDF, and run QA.
---

# Slide Generator

Use this as the default entry point for new slide-generation jobs.

## Required Reading

1. `slide-system/README.md`
2. `slide-system/workflows/intake-and-triage.md`
3. `slide-system/workflows/check-requirements.md`
4. `slide-system/workflows/plan-slide-deck.md`
5. `slide-system/workflows/select-visual-items.md`
6. `slide-system/rules/background-rendering.md` when any raster background,
   complex raster visual, PPTX export, or PDF export is involved.
7. `slide-system/workflows/build-html-deck.md` — ALWAYS when output is PPTX.
8. `slide-system/workflows/export-editable-pptx.md` — ALWAYS when output is PPTX.
9. Other build, export, and QA workflows required by the requested outputs.
10. `slide-system/workflows/save-as-template.md` — when the template save
    prompt (step 12) fires.

## Environment Auto-Setup

Before running any Python script, check that `.venv` exists and has the
required packages. If not, bootstrap it silently:

```bash
if [ ! -f .venv/bin/python3 ] || ! .venv/bin/python3 -c "import pptx, PIL, fitz" 2>/dev/null; then
  ./slide-system/scripts/setup.sh
fi
```

After setup, run all `python3` commands through the venv:

```bash
.venv/bin/python3 slide-system/scripts/<script>.py [args]
```

This is transparent to the user — they never see terminal output. The agent
handles setup on first use and reuses `.venv` on subsequent runs. If `setup.sh`
fails (e.g. Node.js not installed), report the missing prerequisite to the user
in plain language and link to the download page.

## Pipeline

1. Run intake and triage before any other work. Treat a new user as non-tech by
   default: use plain language, attach a guess to every question, ask one at a
   time, and stop asking once you can predict the answers (cap around five to
   six questions; fill the rest with sensible defaults). Detect the case, confirm
   it in plain words, and gather or infer the export format here too. Normalize
   any request for "PowerPoint", "power point", "PPT", or "PPTX" to editable
   `.pptx` without asking a follow-up about file type or editability. Offer a
   tech escape hatch for users who would rather paste a complete brief. Follow
   `workflows/intake-and-triage.md`.
2. End intake with a plain-language brief recap. Do not start building until the
   user confirms the recap. The recap becomes the job requirements and the
   export contract.
3. Create a job and versioned run under `outputs/slide-jobs/`.
4. Run the requirement checker using the cached capability registry.
5. Stop on blocking requirements unless the user approves an override.
6. Analyze content and source authority.
7. Create the slide plan and score published visual-library candidates.
8. Present one approval package before build.
9. Build HTML only after approval.
    - **Template path (conditional):** when a slide's plan sets `base_template`,
      build that slide from the template — load its `visual.svg` + text-slots
      from `slide-system/library/templates/<id>/`, decompose the `visual.svg`,
      and fill slots by role/id — before falling back to a custom build. See
      the "Template-Based Build" section of `build-html-deck.md`.
    a. **Decompose (conditional):** when the deck uses full-page artwork SVGs
       (extraction `visual.svg`), run `decompose_svg_objects.py` FIRST to
       split each page into per-object fragment SVGs + `snippet.html`. Paste
       the snippet into the slide div; base-candidates become CSS
       `background-image` on the slide root (no tag).
    b. **Tag (unconditional — ALL PPTX builds):** tag every visible visual
       element with `data-export-layer` / `data-export-id` / etc. per the
       contract in `build-html-deck.md`. This applies whether visuals come
       from extraction, from `ppt-master`, or are built from scratch. A deck
       with untagged visuals or a single overlay covering ≥85% of the canvas
       will FAIL the export gate.
    c. **Iterate on old run:** if resuming a run originally built with
       `--mode flat` (v1, no tags), do NOT attempt layered export on the
       existing HTML. Either rebuild the HTML with proper tags for a new
       layered run, or keep `--mode flat` for a patch. Ask the user which
       path they prefer.
10. Export PPTX through `export_pptx.py` — the single entry point. Default is
    `--mode layered` (3-layer: base + overlay shapes + native text). Use
    `--mode flat` ONLY when the user explicitly asks for frozen/non-editable.
    Run content, object, render, and parity QA. The validator
    (`validate_export_objects.py`) is the one pass/fail gate.
11. Package the run with checksums, reports, and a manifest.
12. **Template save prompt (PPTX only).** After a successful PPTX export,
    check whether the user's original prompt contains a template-intent
    signal. If it does, ask: *"Bạn có muốn thêm bộ deck slide này thành
    template để lúc sau dùng lại không?"* Follow
    `workflows/save-as-template.md` for the full flow.
    - **Hard keywords** (case-insensitive, anywhere in prompt): `extract
      full slide`, `extract full deck`, `clone`, `template`, `copy slide`,
      `lưu mẫu`, `save as template`.
    - **Contextual inference:** when no hard keyword matches but the prompt
      clearly implies reuse intent (e.g. "tạo lại bộ slide giống hôm
      trước", "giữ nguyên bố cục, chỉ đổi nội dung"), treat it as a
      trigger. Only trigger when confidence is high; when uncertain, skip.
    - **Do NOT trigger** on pure content-generation prompts, non-PPTX
      exports, or failed exports.
    - If the user confirms, run the save-as-template pipeline automatically
      (create template folder, generate artifacts, rebuild catalog). See
      the workflow for step-by-step details.

## Output Discipline

Always apply these; the build, select, and QA workflows enforce the detail.

- Export only the formats chosen in step 1. Never produce an unrequested format.
- Treat "PowerPoint", "power point", "PPT", and "PPTX" as the same output
  request: editable `.pptx` using layered mode. State this inferred default in
  the recap, but do not ask the user to confirm format or editability separately.
  Use flat/frozen PPTX only when the user explicitly asks for a flattened,
  image-only, frozen, or non-editable presentation.
- Reference brand and job assets in place. Brand fonts, icons, and brand images
  load from the brand pack; job-scoped assets live once in `<job-id>/assets/`.
  Runs never re-copy assets. Copy into a run only an asset unique to that run.
- Write one `analysis/visual-requests.json` and one `analysis/selection-report.json`
  per run, keyed by section — not one file per section.
- `qa/export-renders/` images are intermediate. Delete them once render parity
  passes; keep only `qa-report.md`, metrics, and checksums.
- Keep one-off build scripts in `slide-system/scripts/`, never in the run.
- Export PPTX only through `python3 slide-system/scripts/export_pptx.py` — one command
  runs capture → build → compose → compare → validate. `--mode layered` (default)
  exports tagged objects as separate movable shapes; `--mode flat` is the frozen v1
  path. `validate_export_objects.py` is the only pass/fail gate; never hand-stitch steps.
- Full-page artwork SVGs (extraction `visual.svg`) go through
  `python3 slide-system/scripts/decompose_svg_objects.py` before deck build — it
  splits the artwork into per-object fragment SVGs plus a ready-tagged
  `snippet.html`. Never wrap a whole-page SVG in one overlay tag (the gate
  fails any overlay covering ≥85% of the canvas) and never hand-split
  (transforms make static bbox math wrong); see `workflows/build-html-deck.md`.
- Never `mkdir` a folder before having content for it. `package_job.py`
  auto-prunes empty directories at packaging; a finished run must contain none
  (ad-hoc sweep: `python3 slide-system/scripts/prune_empty_dirs.py outputs/`).

## Boundaries

- Never publish or extract a shared component from this skill. When a user wants
  reusable pieces from an existing file, only recommend a hand-off to
  `/component-extractor`; never run extraction inline.
- When no published visual item fits, use a slide-local solution and record an
  extraction recommendation.
- Never select staging, deprecated, or export-incompatible visual items.
- Keep historical phase outputs unchanged.
- Use the SUN.STUDIO brand pack by default unless the user selects another pack.
