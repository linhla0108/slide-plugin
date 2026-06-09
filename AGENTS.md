# SUN.RISER 2026 Agent Context

@/Users/home/.codex/RTK.md

## Default Entry Points

For new AI slide work, use:

- `.agents/skills/slide-generator/SKILL.md` for deck generation and export.
- `.agents/skills/component-extractor/SKILL.md` for manual, user-selected
  component extraction.

The shared architecture is documented in `slide-system/README.md`.
Historical SUN.RISER planning contracts and phase artifacts have been removed;
use the active skills, rules, workflows, registries, and brand pack instead.

Use `rtk` as required by `/Users/home/.codex/RTK.md`.

## Source Order

For a new slide job, read:

1. `AGENTS.md`
2. The selected orchestrator skill
3. `slide-system/README.md`
4. Relevant workflows and rules under `slide-system/`
5. The selected brand-pack manifest
6. Job inputs and approved requirement package
7. Published items in `slide-system/registries/visual-library.json`

## Product Direction

This workspace serves SUN.STUDIO slide creators, reviewers, mentors, and
internal teams producing training, onboarding, workshop, and presentation
materials from structured prompts and approved brand resources.

Outputs should be content-faithful, on brand, editable where required, and
packaged with source authority, QA evidence, checksums, and delivery manifests.

Use a friendly, skilled, reliable voice: energetic but professional, coaching
rather than lecturing, and concise enough for internal presentations.

## Canonical SUN.STUDIO Assets

Do not move or duplicate the canonical design system. It remains at:

- `.agents/skills/sun-studio-design-system/SKILL.md`
- `.agents/skills/sun-studio-design-system/assets/system/`

Use its token stylesheet, Proxima Nova fonts, logo, Dio poses, canonical
components, and reference slides. `slide-system/brand-packs/sun-studio/`
references these assets through a portable manifest.

Primary brand values:

- Orange: `#FF5533`
- Blue: `#3333FF`
- Warm paper: `#FFFDF8`
- Ink: `#171717`
- Canvas: `1920x1080`, 16:9

`#3531FF` is a documented legacy source value and is not a canonical token.

## Shared Visual Library

- Generation may read only items with `status: published`.
- `qa` and `staging` items remain review-only.
- Select by semantic intent and content structure before appearance.
- Keep full-slide templates separate from atomic components and styles.
- Keep semantic foreground content editable where required.
- Use separate raster layers for export-risk visuals: background-only PNG for
  passive canvas treatments, and independent transparent PNG overlays for
  complex elements, blur, shadows, glow, masks, filters, blend modes, and
  blended gradients that must stay visually faithful.
- Never trigger extraction automatically from slide generation.

## Output Boundaries

New slide jobs:

`outputs/slide-jobs/<job-id>/`

Manual extraction jobs:

`outputs/component-extractions/<extraction-id>/`

Do not mix job outputs, extraction staging packages, shared library artifacts,
or canonical brand assets.

## Approval

Slide generation has one approval gate before build. Component extraction is
manual-only and requires source path, slide or page, and exact region or object.
Each item requires explicit approval before publication.

## Content And Quality

- Preserve approved source content exactly unless the user approves edits.
- Record copy suggestions separately.
- Avoid generic AI slide templates, stock-looking visuals, overused glass
  cards, decorative gradients without content purpose, unsupported staging
  components, and unapproved changes to generated outputs.
- Preserve source authority before visual invention.
- Use one strong visual anchor per slide.
- Prefer published reusable resources before creating slide-local structures.
- Keep foreground content editable and reviewable.
- Target clear projection readability at `1920x1080`, strong text contrast,
  restrained motion with reduced-motion support, no overlapping text, and slide
  layouts that remain legible when scaled in the deck viewer.
- Record source authority, selected/rejected visual candidates, overrides,
  export limitations, and checksums.
- Verify HTML content, editable PPTX objects, PDF render, PPTX ZIP integrity,
  font availability, image crop and z-order, and HTML-versus-PPTX evidence.
