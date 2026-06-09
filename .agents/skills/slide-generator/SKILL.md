---
name: slide-generator
description: Orchestrate AI slide generation from prompts, files, or mixed inputs. Checks requirements, plans content, selects published visual items, builds HTML, exports PPTX/PDF, and runs QA.
---

# Slide Generator

Use this as the default entry point for new slide-generation jobs.

## Required Reading

1. `slide-system/README.md`
2. `slide-system/workflows/check-requirements.md`
3. `slide-system/workflows/plan-slide-deck.md`
4. `slide-system/workflows/select-visual-items.md`
5. `slide-system/rules/background-rendering.md` when any raster background,
   complex raster visual, PPTX export, or PDF export is involved.
6. Only the build, export, and QA workflows required by the requested outputs.

## Pipeline

1. Create a job and versioned run under `outputs/slide-jobs/`.
2. Normalize prompt-only, file-only, or mixed input into job requirements.
3. Run the requirement checker using the cached capability registry.
4. Stop on blocking requirements unless the user approves an override.
5. Analyze content and source authority.
6. Create the slide plan and score published visual-library candidates.
7. Present one approval package before build.
8. Build HTML only after approval.
9. Export requested formats and run content, object, render, and parity QA.
10. Package the run with checksums, reports, and a manifest.

## Boundaries

- Never publish or extract a shared component from this skill.
- When no published visual item fits, use a slide-local solution and record an
  extraction recommendation.
- Never select staging, deprecated, or export-incompatible visual items.
- Keep historical phase outputs unchanged.
- Use the SUN.STUDIO brand pack by default unless the user selects another pack.
