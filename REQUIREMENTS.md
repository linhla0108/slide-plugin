# Requirements

What to install before using this slide system.

## TL;DR

- **Claude app + making a new deck → install nothing.**
- Feeding a `.pptx` / `.docx` / `.xlsx` as input → one pip: `pip install "markitdown[pptx,docx,xlsx]"`
- Extracting components from a **PDF** source → `pip install PyMuPDF`
- Machine **without** the Claude app → Node.js 18+, then `./slide-system/scripts/setup.sh`
- PDF, SVG, HTML, Markdown, text, data, images as input → never need an install.

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
| Standalone machine (no Claude app) | Node.js 18+ → `./slide-system/scripts/setup.sh` (installs Playwright, python-pptx, Pillow) |

**PyMuPDF is the only approved PDF→SVG provider.** Do not substitute
`pdftocairo`, `pdf2svg`, or `mutool` — they emit text as paths and break the
editable-text-slot pipeline. Poppler is for QA rasters only. Do not install
tools outside the tables above.

## Check what you have

```bash
python3 slide-system/scripts/check_base_requirements.py
```

Reports each tool as available / missing with the exact install hint. It only
checks — it never installs.
