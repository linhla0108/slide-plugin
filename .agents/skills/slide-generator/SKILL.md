---
name: slide-generator
description: Orchestrate AI slide generation from prompts, files, or mixed inputs. Checks requirements, plans content, selects published visual items, builds HTML, exports PPTX/PDF, and runs QA.
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
7. Only the build, export, and QA workflows required by the requested outputs.

## Pipeline

1. Run intake and triage before any other work. Treat a new user as non-tech by
   default: use plain language, attach a guess to every question, ask one at a
   time, and stop asking once you can predict the answers (cap around five to
   six questions; fill the rest with sensible defaults). Detect the case, confirm
   it in plain words, and gather the export format here too. Offer a tech escape
   hatch for users who would rather paste a complete brief. Follow
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
10. Export only the formats chosen in step 1 and run content, object, render,
    and parity QA.
11. Package the run with checksums, reports, and a manifest.

## Output Discipline

Always apply these; the build, select, and QA workflows enforce the detail.

- Export only the formats chosen in step 1. Never produce an unrequested format.
- Reference brand and job assets in place. Brand fonts, icons, and brand images
  load from the brand pack; job-scoped assets live once in `<job-id>/assets/`.
  Runs never re-copy assets. Copy into a run only an asset unique to that run.
- Write one `analysis/visual-requests.json` and one `analysis/selection-report.json`
  per run, keyed by section — not one file per section.
- `qa/export-renders/` images are intermediate. Delete them once render parity
  passes; keep only `qa-report.md`, metrics, and checksums.
- Keep one-off build scripts in `slide-system/scripts/`, never in the run.

## Boundaries

- Never publish or extract a shared component from this skill. When a user wants
  reusable pieces from an existing file, only recommend a hand-off to
  `/component-extractor`; never run extraction inline.
- When no published visual item fits, use a slide-local solution and record an
  extraction recommendation.
- Never select staging, deprecated, or export-incompatible visual items.
- Keep historical phase outputs unchanged.
- Use the SUN.STUDIO brand pack by default unless the user selects another pack.
