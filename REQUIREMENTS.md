# Requirements & Supported Inputs

What you need to install before making slides with this system — written for
non-technical users.

---

## TL;DR

**If you use the Claude app and only want to make a new slide deck: install
nothing.** Open Claude, point it at this folder, and ask for a deck. The Claude
app already includes everything the core flow needs (slide build, PPTX export,
PDF export).

You only ever install something in two situations:

1. You feed in an **Office binary file** (`.pptx`, `.docx`, `.xlsx`) as context
   → one `pip` command (see [Tier 1](#tier-1--read-office-files-pptx-docx-xlsx)).
2. You run this system on a machine **without the Claude app** (standalone)
   → see [Standalone](#standalone-no-claude-app).

Everything else — PDF, SVG, HTML, Markdown, text, images — needs **no install**.

---

## Supported input files (context for a deck)

You can give the system many kinds of files to read for content, structure, or
visual reference. Most are read directly by the Claude app with no setup.

| File type | Examples | Used for | Install needed |
|-----------|----------|----------|:---:|
| Text / content | `.txt` `.md` `.markdown` | Deck copy, outlines, briefs | **None** |
| Data | `.json` `.csv` `.tsv` `.yaml` | Tables, stats, lists | **None** |
| PDF | `.pdf` | Source decks, guidelines, reports | **None** ✅ |
| Web / markup | `.html` `.htm` `.xml` | Reference layouts, exported pages | **None** |
| Vector | `.svg` | Icons, logos, illustrations, diagrams | **None** |
| Images | `.png` `.jpg` `.jpeg` `.webp` `.gif` | Screenshots, photos, visual references | **None** |
| **PowerPoint** | `.pptx` | Existing decks to read or rebuild | **Tier 1 (pip)** |
| **Word** | `.docx` | Source documents | **Tier 1 (pip)** |
| **Excel** | `.xlsx` `.xlsm` | Spreadsheets, data tables | **Tier 1 (pip)** |
| Legacy office | `.doc` `.odt` `.rtf` | Old documents (rare) | Pandoc (system) |

> The Claude app reads PDF, SVG, HTML, text, data, and images **natively** —
> these never require an install, no matter how large the file.

---

## Install tiers

### Tier 0 — Claude app (already bundled, nothing to do)

Shipped inside the Claude app. You do **not** install or configure these:

- Python runtime + Node.js runtime
- `gen_pptx` — exports an editable PowerPoint deck
- Playwright (browser) — exports a faithful PDF
- Native reading of PDF / SVG / HTML / text / data / images

This tier covers the **entire default flow**: idea → plan → build → export
PPTX/PDF → quality check. A non-technical user making a fresh deck stops here.

### Tier 1 — Read Office files (`.pptx`, `.docx`, `.xlsx`)

Only needed when you hand the system a PowerPoint, Word, or Excel file as
context. One command adds support for all three:

```bash
pip install "markitdown[pptx,docx,xlsx]"
```

That single package lets the system extract text and tables from Office files.
Nothing else is required just to *read* them for context.

### Tier 2 — Rebuild / polish an existing file (advanced)

Triggered only if you ask to **polish an existing `.pptx`** or **rebuild a deck
from a reference document/image**. These use the `pptx` and `ppt-master` skills,
which need extra tools:

| Tool | Install | Note |
|------|---------|------|
| Pillow | `pip install Pillow` | Image handling |
| python-pptx | `pip install python-pptx` | Build PowerPoint objects |
| PyMuPDF | `pip install PyMuPDF` | `.pdf` → page SVG **with editable text** for component extraction. The **only** approved PDF→SVG provider — do not substitute `pdftocairo`/`pdf2svg`/`mutool` (they emit text as paths or are unapproved) |
| LibreOffice | `brew install --cask libreoffice` | `.pptx` → `.pdf` (system app) |
| Poppler | `brew install poppler` | `.pdf` → images for QA (system app). Never the source-SVG provider |
| Pandoc | `brew install pandoc` | Legacy `.doc/.odt/.rtf` (rare) |

`ppt-master` has a larger optional set (PDF/SVG/audio/AI-image tooling) listed in
`.agents/skills/ppt-master/requirements.txt`. Install it only if you use that
skill's advanced features.

> **Non-tech note:** LibreOffice, Poppler, and Pandoc are full system apps, not
> simple `pip`/`npm` packages. If you don't have them, prefer the default
> *make-a-new-deck* flow (Tier 0/1), which needs none of them — the system's PDF
> export already works through the Claude app's built-in browser.

---

## Standalone (no Claude app)

For a machine that does **not** have the Claude app and must run the export
scripts directly. A non-technical user normally does not need this.

Requires **Node.js 18+** ([nodejs.org](https://nodejs.org)) installed first,
then run the one-shot setup:

```bash
./slide-system/scripts/setup.sh
```

It installs Playwright (browser, ~300 MB) and the Python build packages
(`python-pptx`, `Pillow`), then prints the capture → build → export commands.

---

## Check what you have

Run the preflight to see which tools are present on this machine:

```bash
python3 slide-system/scripts/check_base_requirements.py
```

It reports each tool as available / missing and prints the exact install hint
for anything that's absent. It never installs anything for you — it only checks.

---

## Quick decision guide

```
Are you using the Claude app?
├─ Yes
│   ├─ Making a NEW deck (text/PDF/SVG/HTML/image as context)? → install NOTHING
│   ├─ Feeding a .pptx / .docx / .xlsx as context?            → Tier 1 (one pip)
│   └─ Polishing a .pptx / rebuilding from a reference?        → Tier 2 (advanced)
└─ No (standalone machine)                                      → Node 18+ + setup.sh
```

---

## Requirements per skill / flow

What each flow in this repo actually needs. Anything not listed here runs on
Tier 0 (nothing to install).

| Flow / skill | Requirement |
|---|---|
| Make a new deck — `slide-generator`, `make-a-deck`, `sun-studio-design-system`, `export-as-editable-pptx`, `hi-fi-design`, `make-tweakable` | **Nothing** (Tier 0) |
| Component extraction — `component-extractor`, `extract-preflight`, `svg-extractor` + all `slide-system/scripts/` | **Nothing** (Tier 0, stdlib scripts). PDF source → add **PyMuPDF** (Tier 2) |
| Render-parity QA — `compare_renders.py` | `pip install Pillow` |
| Send a design to Canva — `send-to-canva` | Canva login (MCP), no install |
| Read an Office file as context | Tier 1: `pip install "markitdown[pptx,docx,xlsx]"` |
| Polish / rebuild an existing `.pptx` — `pptx` skill | Tier 1 + Pillow; LibreOffice + Poppler only for the PPTX→PDF→image QA loop |
| Bulk doc→SVG→PPTX engine — `ppt-master` (advanced) | `.agents/skills/ppt-master/requirements.txt` (~13 pip) + pandoc for legacy formats |
| Standalone machine (no Claude app) | Node 18+ → `./slide-system/scripts/setup.sh` (installs Playwright, python-pptx, Pillow) |

Notes:

- All `slide-system/scripts/` are pure Python stdlib except
  `compare_renders.py` (Pillow), `build_hybrid_pptx.py` and
  `test_export_stack.py` (standalone path, installed by `setup.sh`).
  `optimize_svg.py` uses macOS `sips` when present and silently skips raster
  recompression without it.
- The allowed library set is exactly the tables above — do not add or
  substitute converters/tools outside them (see the PyMuPDF note in Tier 2).
