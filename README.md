# SUN.RISER 2026 Slide Workspace

This repository contains SUN.STUDIO source material, HTML deck prototypes,
canonical brand assets, reusable visual items, slide-generation workflows, and
historical phase outputs.

## New AI Slide Work

Use one of the two manual entry points:

- `.agents/skills/slide-generator/SKILL.md`
- `.agents/skills/component-extractor/SKILL.md`

The complete system guide is `slide-system/README.md`. It covers requirement
checks, planning, visual selection, approval, HTML build, editable PPTX and PDF
export, PPT Master, render parity, manual extraction, publication, catalog
rebuild, delivery packaging, and job resume.

Open `slide-system/catalog/index.html` through a local HTTP server to review
published and staging visual items.

## Important Boundaries

- Canonical SUN.STUDIO assets remain in
  `.agents/skills/sun-studio-design-system/assets/system/`.
- Shared system contracts and scripts remain in `slide-system/`.
- New deck outputs belong in `outputs/slide-jobs/`.
- Manual extraction outputs belong in `outputs/component-extractions/`.
- Legacy files in `project/`, `component-from-slide/`, `style-from-slide/`, and
  existing phase output folders remain available for historical compatibility.

## Legacy SUN.RISER Job

`plan.md` and `plan_per_phase.md` describe the earlier SUN.RISER production
job. They are not the architecture for future AI slide jobs.
