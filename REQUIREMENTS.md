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

# Inventory — skills & scripts

A full audit of what each skill and script does, what it needs installed, and
whether to keep or trim it. **Audit only** — nothing here was removed.

**Legend for the "Install" column:**
`none` = runs on Claude built-ins, zero install ·
`pip`/`npm` = language package ·
`system` = full app via `brew`/installer (hardest for non-tech).

## Skills (`.agents/skills/`)

Ten of the twelve skills are **prompt-only** — they carry no bundled code and
just drive Claude's built-in tools (`gen_pptx`, Playwright, Canva MCP, the file
reader, vision). They cost **nothing to install** and should all be kept.

| Skill | What it does | Bundled code | Install | Keep / Cut |
|-------|--------------|:---:|:---:|------------|
| `slide-generator` | Master orchestrator: intake → plan → select → build → export → QA | prompt only | none | **Keep** — main entry point |
| `make-a-deck` | Build a self-contained HTML deck (narrative, typography, notes) | prompt only | none | **Keep** — core HTML build |
| `sun-studio-design-system` | Apply SUN.STUDIO brand (colors, Proxima Nova, logo/Dio, layouts) | prompt only | none | **Keep** — brand authority + fonts |
| `export-as-editable-pptx` | HTML deck → editable PPTX via `gen_pptx` | prompt only | none (built-in) | **Keep** — primary PPTX path |
| `component-extractor` | Extract user-selected regions into reusable library items | prompt only¹ | none | **Keep** — drives slide-system scripts |
| `svg-extractor` | Inspect SVG structure/geometry/text for reconstruction | 1 py (stdlib) | none | **Keep** — zero cost |
| `extract-preflight` | Verify toolchain before extraction; write readiness marker | prompt only | none | **Keep** — zero cost |
| `hi-fi-design` | Polished hi-fi interface/design explorations | prompt only | none | **Keep** — zero cost |
| `make-tweakable` | Add a "Tweaks" control panel to a design | prompt only | none | **Keep** — zero cost |
| `send-to-canva` | Publish HTML design → import into Canva (Canva MCP) | prompt only | none (MCP) | **Keep** — zero cost; needs Canva login only |
| `pptx` | Read / edit / create `.pptx` files directly | 16 py | pip + **system** | **Keep, trim deps** — see below |
| `ppt-master` | Doc (PDF/DOCX/URL/MD) → SVG pages → PPTX, multi-role engine | 124 py + reqs | pip-heavy + **system** | **Review / candidate cut** — see below |

¹ `component-extractor` has no bundled code itself; it calls the stdlib scripts
in `slide-system/scripts/` (below).

### The two heavy skills

**`pptx`** — needed only when a user brings an existing `.pptx` to read or edit
(intake Case 3). Its declared deps: `markitdown[pptx]`, `Pillow` (pip) and
**LibreOffice + Poppler** (system).
- **Keep the skill.** **Trim the system deps:** Claude reads `.pptx` text through
  `markitdown` (pip) and can render previews via the built-in Playwright instead
  of LibreOffice/Poppler. The two system apps are only needed for the
  PPTX→PDF→image QA loop; the HTML-first flow avoids them.

**`ppt-master`** — a complete alternate engine (Chinese multi-role SVG→PPTX) that
converts source documents into slides. Even after the 2026-06 dep trim (TTS,
watermark, and rotate tooling removed), it carries the **single largest install
burden** in the repo: `python-pptx`, `PyMuPDF`, `cairosvg`/`svglib`+`reportlab`,
`Pillow`, `mammoth`, `markdownify`, `ebooklib`, `nbconvert`, `openpyxl`,
`requests`, `beautifulsoup4`, `flask`, plus `pandoc` (system). Its optional AI
image backend additionally imports `google-genai` at its own load time (not in
`requirements.txt`).
- **Function overlap:** deck creation is already covered by `make-a-deck` +
  `slide-generator`; PPTX export by `export-as-editable-pptx`.
- Its **unique** capability is bulk **document-ingestion → SVG pages** (PDF/DOCX/
  URL → slides) — not offered elsewhere.
- **Recommendation:** if you never use the doc→SVG bulk flow, **cut this skill**
  to erase the entire `requirements.txt` burden. If you do, **keep it but mark it
  advanced** and install its reqs only on demand. This is the #1 lever for a
  lighter non-tech footprint.

## Scripts (`slide-system/scripts/`)

**Almost every script is pure Python stdlib.** The exceptions: `build_hybrid_pptx.py`
(python-pptx, Pillow — standalone path), `compare_renders.py` (Pillow — exits with a
clear install hint when absent), and `test_export_stack.py` (python-pptx — tests the
standalone path). `_common.py` uses Pillow only for image hashing and degrades
gracefully without it. The stdlib scripts run on the Claude-bundled Python with
**zero install** and should all be kept.

| Script | What it does | Install | Used by | Keep / Cut |
|--------|--------------|:---:|---------|------------|
| `_common.py` | Shared helpers (paths, hashing, JSON, fingerprints) | none | all scripts | **Keep** |
| `check_requirements.py` | Validate a job's requirement file vs capabilities | none | slide-generator | **Keep** |
| `check_base_requirements.py` | Preflight toolchain; write readiness marker (probes only) | none | extract-preflight | **Keep** |
| `update_capabilities.py` | Refresh cached tool capabilities when needed | none | both pipelines | **Keep** |
| `score_visual_items.py` | Score published library items for a slide need | none | slide-generator | **Keep** |
| `validate_registry.py` | Validate registry IDs / paths / statuses / aliases | none | library upkeep | **Keep** |
| `package_job.py` | Build checksum manifest for a finished run | none | package-delivery | **Keep** |
| `compare_renders.py` | Visual-diff evidence for two equal-size renders | **pip**: Pillow | render parity QA | **Keep** |
| `scaffold_extraction.py` | Stage a manual extraction package | none | component-extractor | **Keep** |
| `publish_extraction.py` | Publish an approved item into the shared library | none | component-extractor | **Keep** |
| `fingerprint_source.py` | Deterministic source/region fingerprints | none | component-extractor | **Keep** |
| `extract_editable_text_slots.py` | Split SVG text into editable text-slot contracts | none | component-extractor | **Keep** |
| `validate_text_slots.py` | Validate the text-slot contract | none | component-extractor | **Keep** |
| `apply_text_contract.py` | Update batch mappings after text-slot extraction | none | component-extractor | **Keep** |
| `build_text_slot_gallery.py` | Build a batch review gallery | none | component-extractor | **Keep** |
| `build_component_catalog.py` | Generate catalog data from registry items | none | rebuild-catalog | **Keep** |
| `externalize_svg_images.py` | Replace embedded SVG data-URIs with files | none | component-extractor | **Keep** |
| `optimize_svg.py` | Trim SVG precision; recompress rasters | none² | component-extractor | **Keep** |
| `build_hybrid_pptx.py` | Renders + DOM layout → editable PPTX (no Claude) | **pip**: python-pptx, Pillow | standalone path | **Keep (fallback)** — see below |
| `test_export_stack.py` | Self-test for the standalone export stack | **pip**: python-pptx | standalone path | **Keep (fallback)** |
| `capture-slides.js` | Render slides to PNG + extract DOM layout (Playwright) | **npm**: playwright | standalone path | **Keep (fallback)** |
| `export-pdf.js` | HTML deck → PDF via headless Chromium (Playwright) | **npm**: playwright | standalone path | **Keep (fallback)** |
| `setup.sh` | One-shot installer for the standalone path | — | non-Claude machines | **Keep (fallback)** |

² `optimize_svg.py` uses `sips` (built into macOS) when present and silently
skips raster optimization if absent — never a hard requirement.

## The standalone path is a deliberate fallback — keep it

`build_hybrid_pptx.py`, `capture-slides.js`, `export-pdf.js`, `setup.sh`,
`package.json`, and their deps (`playwright`, `python-pptx`, `Pillow`) exist so
the system can run **without the Claude app** — e.g. driven by another LLM or in
plain CI. **Keep all of it.** These deps install **only** when someone runs
`setup.sh` on a non-Claude machine; they never burden a Claude-app user.

## Bottom line — what actually needs installing

| Group | Items | Install | Verdict |
|-------|-------|:---:|---------|
| 10 prompt skills + 19 stdlib scripts | the whole core flow | **none** | Keep all — free |
| Office-file reading | `markitdown[pptx,docx,xlsx]` | one `pip` | Keep — light, on demand |
| Standalone fallback | playwright, python-pptx, Pillow | `setup.sh` | Keep — non-Claude path, on demand |
| `pptx` system deps | LibreOffice, Poppler | system | **Trimmable** — replace with markitdown + Playwright |
| `ppt-master` full reqs | ~13 pip + pandoc | pip-heavy + system | **#1 cut candidate** if doc→SVG flow is unused |

**Net:** for a non-tech Claude-app user, the realistic install surface shrinks to
**zero** (new decks) or **one `pip` line** (Office files). The only genuinely
heavy thing in the repo is `ppt-master`; cutting or deferring it removes almost
the entire install burden without touching the core slide pipeline.
