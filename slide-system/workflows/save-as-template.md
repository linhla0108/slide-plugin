# Save As Template

Run this after a successful PPTX export when the template save prompt
(pipeline step 12) fires and the user confirms.
Use `<project-python>` below: `.venv\Scripts\python.exe` on Windows and
`.venv/bin/python3` on macOS/Linux.

## Pre-conditions

- PPTX export passed validation (`validate_export_objects.py`).
- User explicitly confirmed they want to save as template.

## Flow

### 1. Choose slide(s)

- **Single-slide deck:** use that slide.
- **Multi-slide deck:** ask the user which slide(s) to save. Each template is
  one slide layout. Offer to save all as separate templates if layouts differ.

### 2. Name the template

Propose a default slug derived from the deck content or job name
(e.g. `sun.template.pitch-cover`). Let the user override. The slug must be
kebab-case, prefixed with `sun.template.`.

### 3. Create the template folder

Target: `slide-system/library/templates/sun.template.<name>/`

Required artifacts:

| File | How to produce |
|------|----------------|
| `visual.svg` | Extract the slide's artwork SVG from the built HTML. Strip editable text content but keep layout, shapes, and artwork. |
| `text-slots.json` | Run `extract_editable_text_slots.py` on the slide HTML, or adapt the existing text contract from the job's build artifacts. Must match the schema used by `sun.template.cover-title-connect/text-slots.json`. |
| `background.png` | Render the slide background layer via the existing capture pipeline (Puppeteer / `capture-slides.js`). |
| `preview/preview.html` | Run `generate_template_preview.py` against the new template folder. |
| `preview/thumbnail.png` | Capture a 400×225 thumbnail from the preview HTML. |
| `evidence/notes.md` | Auto-generate provenance: job ID, run ID, slide index, creation date, original prompt summary. |
| `evidence/source-with-text.svg` | Copy the original SVG (with text) from the job's build artifacts. |

If the slide uses external images, create `evidence/external-images.json`
listing their source paths (same format as existing templates).

### 4. Validate

- Run `validate_text_slots.py` on the new `text-slots.json`.
- Verify the folder contains all required files (visual.svg, text-slots.json,
  background.png, preview/thumbnail.png).

### 5. Rebuild catalog

```bash
<project-python> slide-system/scripts/build_component_catalog.py
<project-python> slide-system/scripts/build_template_picker_data.py
```

Both scripts already scan `library/templates/` — no registration code needed.

### 6. Confirm to user

Report completion:

> Saved template `sun.template.<name>` — you can use it in future jobs.

## Boundaries

- Never create a template without user confirmation.
- Never overwrite an existing template. If the slug already exists, append a
  numeric suffix or ask the user for a different name.
- Never modify the PPTX export pipeline.
- Never skip catalog rebuild after creating a template.
- Each template is exactly one slide layout. Do not merge multiple layouts
  into one template.
