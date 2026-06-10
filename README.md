# SUN.RISER 2026 Slide Workspace

This repository contains SUN.STUDIO source material, canonical brand assets,
reusable visual items, slide-generation workflows, and generated outputs.

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

## Setup & Supported Inputs

See [`REQUIREMENTS.md`](REQUIREMENTS.md) for what to install before making
slides and which input file types are supported. For most non-technical users
making a new deck in the Claude app, the answer is: install nothing.

## Important Boundaries

- Canonical SUN.STUDIO assets remain in
  `.agents/skills/sun-studio-design-system/assets/system/`.
- Shared system contracts and scripts remain in `slide-system/`.
- New deck outputs belong in `outputs/slide-jobs/`.
- Manual extraction outputs belong in `outputs/component-extractions/`.
- Historical SUN.RISER phase contracts and prototype folders were removed.
  Current work should use `AGENTS.md`, `.agents/skills/`, and `slide-system/`.
