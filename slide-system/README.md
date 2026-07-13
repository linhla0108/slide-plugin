# AI Slide Generation System

This directory contains the shared, brand-portable system for generating slide
decks and maintaining a reusable visual library.

## Entry Points

- `.agents/skills/slide-generator/SKILL.md`: create a new slide deck.
- `.agents/skills/component-extractor/SKILL.md`: manually extract exact regions.
- `slide-system/scripts/extract_pdf_components.py`: preflight a PDF, create
  review-only Drafts without hand-authored JSON, and rebuild catalog data.
- `slide-system/catalog/catalog_server.py`: review, publish, or delete Drafts.

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
the project-local `.venv`. On Windows run:

```powershell
powershell -ExecutionPolicy Bypass -File .\slide-system\scripts\setup.ps1
```

On macOS/Linux run `./slide-system/scripts/setup.sh`.

Use `.venv\Scripts\python.exe` on Windows and `.venv/bin/python3` on
macOS/Linux for every script. The preflight, extraction, catalog, and export
paths resolve the same interpreter and fail with the matching setup hint rather
than falling back to a global Python.

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

Create review-only Drafts directly from a PDF without authoring request JSON:

```text
<project-python> slide-system/scripts/extract_pdf_components.py \
  --pdf <file.pdf> --extraction-id <id> [--pages 1|2-4]
```

The command runs PDF preflight before analysis and staging. It never publishes.
Docling is optional; when absent, PDF analysis uses the approved PyMuPDF
fallback detector.

Split semantic SVG text into editable slots:

```bash
python3 slide-system/scripts/extract_editable_text_slots.py \
  --item-dir outputs/component-extractions/<extraction-id>/items/<item-id>
```

The reusable contract is `artifact/visual.svg` plus
`artifact/text-slots.json`. The source-faithful SVG remains under
`evidence/source-with-text.svg`; review HTML composes the visual and editable
text rather than reading semantic text from the SVG.

Crop the full-page visual down to the selected component region:

```bash
python3 slide-system/scripts/crop_svg_region.py \
  --item-dir outputs/component-extractions/<extraction-id>/items/<item-id>
```

The PDF→SVG path converts the whole page, so a component-level item must be
cropped to its `source.region` (from `mapping.json`) — otherwise the artifact is
the entire slide with text stripped, not a single component. The script rewrites
`visual.svg`'s viewBox and re-normalizes `text-slots.json`; it is a no-op for a
full-page region and idempotent (marker `source.region_crop`). `publish_extraction.py`
blocks publishing a component-level item that lacks this marker.

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

`visual-library.json` is the metadata authority (published folders do not keep
`mapping.json`, so it cannot be rebuilt from disk). `visual-library-compact.json`
— the file `score_visual_items.py` actually reads — is a derived projection and
must never be hand-edited. `component-retrieval-index.jsonl` is the
lexical/RAG-ready projection; it is derived from published registry items only
and has no embedding/vector dependency. `score_visual_items.py` consumes it for
hybrid lexical matching — broadened keyword/summary matches earn reduced,
capped credit (never enough to cross the semantic floor alone), while
anti-use-case hits, `set-of-N` count mismatches, and zero editable text slots
(record schema v2 `slot_count`) subtract score with explicit reasons.
`publish_extraction.py` regenerates both derived projections on every publish;
for bulk reconciles after manual deletes use:

```bash
python3 slide-system/scripts/build_registry.py --check   # gate: exit 1 on drift
python3 slide-system/scripts/build_registry.py --write    # drop dangling entries + rebuild compact
```

It drops registry entries whose artifact folder is gone and reports library
folders that have a `visual.svg` but no registry entry (orphans) — it never
deletes folders itself.

Rebuild/check the retrieval index after publish or registry changes:

```bash
python3 slide-system/scripts/build_component_retrieval_index.py
python3 slide-system/scripts/build_component_retrieval_index.py --check
```

Rebuild and serve the catalog:

```bash
python3 slide-system/scripts/build_component_catalog.py
# Serve via the control server (static files + Publish/Delete endpoints):
python3 slide-system/catalog/catalog_server.py
```

Then open **http://127.0.0.1:8799/slide-system/catalog/**.

> **Always serve the catalog with `catalog_server.py`, not a bare static
> server.** The Publish/Delete buttons POST to `/api/publish` and `/api/delete`,
> which only `catalog_server.py` (port 8799) implements. Open the page from any
> other origin and those buttons fail on the POST:
> - `python3 -m http.server` → **501** ("control server not running") — view-only.
> - VS Code **Live Server** (:5500) → **405 Method Not Allowed**.
>
> `fetch` uses an origin-relative path, so the page **must** be opened from
> `127.0.0.1:8799` for managing to work. A bare static server is fine only for
> read-only viewing.

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
- For reusable `component` items, retrieval-ready metadata that passes
  `validate_component_metadata.py` (non-empty intent/tags/content_structure/
  keywords/use_cases/anti_use_cases, non-blank component_type/layout_role/
  visual_summary/retrieval_notes/quality_notes, and no auto-stage/OCR
  placeholder text). `publish_extraction.py` enforces this before any registry
  or library mutation.
