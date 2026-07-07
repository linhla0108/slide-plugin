# Requirements

What to install before using this slide system.

## TL;DR

- **Claude app + making a new deck → install nothing.**
- Feeding a `.pptx` / `.docx` / `.xlsx` as input → one pip: `pip install "markitdown[pptx,docx,xlsx]"`
- Extracting components from a **PDF** source → `pip install PyMuPDF`
- Machine **without** the Claude app → Node.js 18+, then `./slide-system/scripts/setup.sh`
- PDF, SVG, HTML, Markdown, text, data, images as input → never need an install.

**Where `pip install` goes:** into the repo-local venv, on every machine. Modern
system pythons (Homebrew, Debian/Ubuntu) are PEP 668 externally-managed and
refuse `pip install` with `error: externally-managed-environment`. Create the
venv once, then every `pip install X` in this document means:

```bash
python3 -m venv .venv          # once per machine (setup.sh also does this)
.venv/bin/pip install X
```

Run the corresponding python steps with `.venv/bin/python3`. Never use
`--break-system-packages`.

## Supported inputs

| Input | Install |
|-------|---------|
| `.txt` `.md` `.json` `.csv` `.tsv` `.yaml` `.html` `.xml` `.svg` `.pdf` `.png` `.jpg` `.webp` `.gif` | **None** |
| `.pptx` `.docx` `.xlsx` `.xlsm` | `pip install "markitdown[pptx,docx,xlsx]"` |
| `.doc` `.odt` `.rtf` (legacy, rare) | `brew install pandoc` |

## Requirements per flow

| Flow / skill | Requirement |
|---|---|
| New deck — `slide-generator`, `make-a-deck`, `sun-studio-design-system`, `export-as-editable-pptx`, `hi-fi-design`, `make-tweakable` | **Nothing** |
| Component extraction — `component-extractor`, `extract-preflight`, `svg-extractor` + `slide-system/scripts/` | **Nothing**; PDF source → `pip install PyMuPDF` |
| Render-parity QA — `compare_renders.py` | `pip install Pillow` |
| Send to Canva — `send-to-canva` | Canva login (MCP), no install |
| Polish / rebuild an existing `.pptx` — `pptx` skill | `markitdown` + Pillow; LibreOffice (`brew install --cask libreoffice`) + Poppler (`brew install poppler`) only for the PPTX→PDF→image QA loop |
| Bulk doc→SVG→PPTX — `ppt-master` (advanced) | `pip install -r .agents/skills/ppt-master/requirements.txt` (~13 packages) + pandoc for legacy formats |
| Standalone machine (no Claude app) / Export editable PPTX 3 lớp — `slide-system/scripts/export_pptx.py` (+ `decompose_svg_objects.py` to split full-page artwork into per-object overlays at deck build) | Node.js 18+ → `./slide-system/scripts/setup.sh` (installs Playwright, python-pptx, Pillow). Smoke-test: `python3 slide-system/scripts/test_export_stack.py` |

**PyMuPDF is the only approved PDF→SVG provider.** Do not substitute
`pdftocairo`, `pdf2svg`, or `mutool` — they emit text as paths and break the
editable-text-slot pipeline. Poppler is for QA rasters only. Do not install
tools outside the tables above.

## Check what you have

Run the readiness check at the start of every component extraction session.
The script reuses `slide-system/registries/extract-readiness.json`, so repeat
checks are cheap and do not reinstall anything.

```bash
python3 slide-system/scripts/check_base_requirements.py
```

For source files that must be converted, use the input-scoped check before
authoring the extraction request:

```bash
python3 slide-system/scripts/check_base_requirements.py --input pdf
python3 slide-system/scripts/check_base_requirements.py --input pptx
```

Reports each tool as available / missing with the exact install hint. It only
checks — it never installs. Stop on `BLOCKER`; do not scaffold or fall back from
Docling to manual extraction until the required source provider passes.
