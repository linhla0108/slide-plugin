# AI Slide Generation System

This directory contains the shared, brand-portable system for generating slide
decks and maintaining a reusable visual library.

## Entry Points

- `.agents/skills/slide-generator/SKILL.md`: create a new slide deck.
- `.agents/skills/component-extractor/SKILL.md`: manually extract exact regions.

## System Areas

| Area | Purpose |
|---|---|
| `workflows/` | Ordered procedures loaded only when needed |
| `rules/` | Stable decisions and quality constraints |
| `schemas/` | JSON interfaces used by scripts and artifacts |
| `registries/` | Capabilities, visual items, history, and aliases |
| `library/` | Published visual artifacts grouped by type |
| `brand-packs/` | Brand references without asset duplication |
| `catalog/` | Visual review UI for published and staging items |
| `boilerplates/` | Starter files for jobs, approvals, and extraction |
| `scripts/` | Repeatable validation, scoring, publishing, and packaging |

## Output Boundaries

- New deck jobs: `outputs/slide-jobs/<job-id>/runs/<run-id>/`
- Manual extraction batches: `outputs/component-extractions/<extraction-id>/`
- Shared system files never belong inside a job run.
- Job runs reference published visual IDs and versions.

## Default Brand

SUN.STUDIO is the default brand pack. Its manifest references the canonical
assets already stored in `.agents/skills/sun-studio-design-system/`.

## Approval Model

- Deck generation has one approval gate before build.
- Extraction has approval per staged item before publication.
- Approved overrides and limitations must be recorded in manifests.

## Folder Map

```text
slide-system/
├── workflows/      ordered operating procedures
├── rules/          stable decisions and fallback policies
├── schemas/        JSON contracts
├── registries/     capability, visual, alias, and extraction records
├── library/        published extraction artifacts
├── brand-packs/    brand-neutral manifest implementations
├── catalog/        published and staging review application
├── boilerplates/   starter requirement and report files
└── scripts/        repeatable command-line automation

outputs/
├── slide-jobs/<job-id>/requirements, inputs, and runs
└── component-extractions/<extraction-id>/staging packages
```

## Runtime

Python scripts require dependencies (python-pptx, Pillow, PyMuPDF) installed in
a project-local virtual environment (`.venv`). The agent bootstraps this
automatically — see the auto-setup rule in `slide-generator/SKILL.md`. For
manual setup, run `./slide-system/scripts/setup.sh`.

All `python3` commands in this doc assume `.venv` is activated or the agent
has set `PATH` to include `.venv/bin` before running scripts.

The capability registry stores the actual executable path and only advertises
image analysis when Pillow imports successfully.

## Common Commands

Refresh capabilities:

```bash
python3 slide-system/scripts/update_capabilities.py
```

Check job requirements:

```bash
python3 slide-system/scripts/check_requirements.py \
  --requirements outputs/slide-jobs/<job-id>/requirements/job-requirements.json \
  --output outputs/slide-jobs/<job-id>/requirements/capability-report.json
```

Score published visual items:

```bash
python3 slide-system/scripts/score_visual_items.py \
  --request <visual-request.json> \
  --output <selection-report.json>
```

Create a manual extraction staging package:

```bash
python3 slide-system/scripts/scaffold_extraction.py \
  --request <extraction-request.json>
```

Split semantic SVG text into editable slots:

```bash
python3 slide-system/scripts/extract_editable_text_slots.py \
  --item-dir outputs/component-extractions/<extraction-id>/items/<item-id>
```

The reusable contract is `artifact/visual.svg` plus
`artifact/text-slots.json`. The source-faithful SVG remains under
`evidence/source-with-text.svg`; review HTML composes the visual and editable
text rather than reading semantic text from the SVG.

Build an editable batch review gallery:

```bash
python3 slide-system/scripts/build_text_slot_gallery.py \
  --extraction-dir outputs/component-extractions/<extraction-id>
```

Validate editable SVG contracts:

```bash
python3 slide-system/scripts/validate_text_slots.py \
  --item-dir outputs/component-extractions/<extraction-id>/items/<item-id>
```

Publish one approved extraction:

```bash
python3 slide-system/scripts/publish_extraction.py \
  --extraction-dir outputs/component-extractions/<extraction-id> \
  --item-id <item-id>
```

Rebuild and serve the catalog:

```bash
python3 slide-system/scripts/build_component_catalog.py
python3 -m http.server 8000
```

Then open `/slide-system/catalog/index.html`.

Compare equal-size HTML and exported renders:

```bash
python3 slide-system/scripts/compare_renders.py \
  --reference <html-render.png> \
  --candidate <export-render.png> \
  --output-dir <qa/parity>
```

Package a completed run:

```bash
python3 slide-system/scripts/package_job.py \
  --run-dir outputs/slide-jobs/<job-id>/runs/<run-id>
```

## Publication Minimum

An extraction cannot be published until it has:

- Explicit per-item approval.
- A valid stable ID and version.
- At least one reusable artifact.
- At least one preview.
- Source-versus-reconstruction evidence.
- Tested HTML, PPTX, PDF, and Canva compatibility declarations.
- Documented limitations and a valid source mapping.
