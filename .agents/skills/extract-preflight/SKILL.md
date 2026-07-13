---
name: extract-preflight
description: Verify the base toolchain before component extraction, source-to-SVG conversion, embedded raster/base64 handling, vectorization, or HTML preview work, and record a readiness marker so a satisfied environment is never re-checked or re-installed from scratch.
---

# Extract Preflight

Run this once before starting component-extraction, source-to-SVG conversion, or
preview work. It confirms the base tools the pipeline depends on and writes a
readiness marker keyed to the current environment. A satisfied environment
short-circuits on the next run — no re-probing, no re-install.

This skill covers the environment preflight only. It does not perform extraction
or conversion. Use it to decide which provider path is available before the
`component-extractor` workflow consumes page-level `source.svg`/`reference.png`
artifacts.

## When To Run

- Before the first `component-extractor` batch in a fresh environment or checkout.
- Before accepting PDF, PPTX, or PNG/JPG inputs that must be normalized to SVG.
- Before enabling optional raster vectorization for embedded images.
- After changing the toolchain (new machine, reinstalled tools, updated PATH).
- Never on every job — the marker exists precisely so you skip repeat checks.

## How To Run

Use `.venv\Scripts\python.exe` on Windows or `.venv/bin/python3` on
macOS/Linux. If that interpreter is missing, run
`powershell -ExecutionPolicy Bypass -File .\slide-system\scripts\setup.ps1` on
Windows or `./slide-system/scripts/setup.sh` on macOS/Linux.

```text
<project-python> slide-system/scripts/check_base_requirements.py
<project-python> slide-system/scripts/check_base_requirements.py --input pdf
<project-python> slide-system/scripts/check_base_requirements.py --force
<project-python> slide-system/scripts/check_base_requirements.py --json
```

Exit code `0` = ready (proceed), `1` = blocked (a required tool is missing).
When the upcoming job must normalize a PDF or PPTX input, always pass
`--input pdf` / `--input pptx`: the plain run reports missing source providers
as warnings only, the gated run treats them as blockers for that job.

## Readiness Marker

The script writes `slide-system/registries/extract-readiness.json` with the
status, the environment fingerprint, a per-requirement result, and a
`source_providers` array (schema version 3). On the next run, if the schema
version and fingerprint still match and the status is `ready`, it prints
`REUSED marker` and returns immediately without probing again. This is the
"don't set up from scratch every time" guarantee — treat a `ready` marker with a
matching fingerprint as authoritative. Use `--force` only when you deliberately
changed the toolchain.

`status: ready` means the SVG-package pipeline is ready — it does NOT imply the
PDF/PPTX providers are installed. Source-to-SVG providers are input-type-scoped:
the marker records them under `source_providers` (ids `pdf-provider` for
PyMuPDF, `pptx-provider` for LibreOffice) with availability and an
`install_hint`, and a missing one is surfaced as a warning, never a global
blocker. Before accepting a PDF or PPTX input, check the matching
`source_providers` entry; if it is `missing`, treat that as a blocker for that
job and install via its hint (repo-local venv for PyMuPDF, see below /
the official LibreOffice download). The fingerprint covers provider
availability, so installing PyMuPDF or LibreOffice invalidates the marker and
triggers a re-probe automatically.

The report records the selected project interpreter in top-level `python` and
in the `pdf-provider` entry. Run all PDF, export, and validation steps with that
same interpreter; it is `.venv\Scripts\python.exe` on Windows and
`.venv/bin/python3` on macOS/Linux.

Do not hand-edit the marker; regenerate it with `--force`.

## Base Requirements

These are the minimum requirements for the SVG-first extractor after page SVGs
already exist.

| Requirement | Level | Why |
|---|---|---|
| project Python | required | Run every `slide-system/scripts/` step from `.venv`. |
| `xmllint` | required | Validate `visual.svg` / `source-with-text.svg` stay well-formed XML. |
| raster optimizer (`sips`, `magick`, or `convert`) | recommended | Downsample / recompress embedded rasters in `optimize_svg.py`. Without it the SVG is still precision-trimmed but large images stay at source size. |
| SVG renderer (`playwright`/Chromium, `rsvg-convert`, `resvg`, `inkscape`, or `cairosvg`) | recommended | Render SVG to PNG for preview/parity checks. Chromium/Playwright is preferred for masks, clips, filters, and gallery-equivalent rendering. |

## Source-To-SVG Provider Requirements

When the user provides non-SVG inputs, preflight must check the matching provider
path before claiming the extraction environment is ready for that input type.
Keep this as a separate source-normalization layer before `component-extractor`.
The preflight script probes these automatically (`import fitz` for PyMuPDF,
`soffice` on PATH or in `/Applications/LibreOffice.app` for LibreOffice) and
records the result in the marker's `source_providers` array with level
`input-scoped` — read availability from there instead of re-probing by hand.

**Allowed-library policy:** the approved install surface is governed by
`REQUIREMENTS.md` at the repo root. Use only the providers listed below — do not
try, suggest, or install alternatives (`pdf2svg`, `mutool`, Aspose, `vtracer`,
`potrace`, `cairosvg`, `rsvg-convert`, `inkscape`, …) even if they are present
on the machine.

| Input | Allowed provider | Level | Why |
|---|---|---|---|
| PDF → source SVG | `PyMuPDF` via `slide-system/scripts/convert_pdf_source.py --pdf <file> --page <n> --item-dir <item>` | required for PDF source extraction | The only approved text-preserving PDF→SVG provider. The script emits `artifact/source-page.svg` (with `<text>` nodes) plus `evidence/reference.png`; never call converters by hand or render pages to PNG as the visual. |
| PDF → reference PNG | PyMuPDF `page.get_pixmap(...)`; Poppler (`pdftoppm`) acceptable if already installed | recommended | Raster reference for render-parity QA only. |
| PPTX | LibreOffice `soffice --headless` → PDF, then PyMuPDF | required for PPTX input | System app, approved in `REQUIREMENTS.md`. Verify fonts are installed before judging fidelity. |
| PNG/JPG | SVG image wrapper `<svg><image .../></svg>` | required for raster input | Preserve appearance exactly; no tracing. |

Provider caveats:

- Poppler's `pdftocairo -svg` renders text as vector paths (zero `<text>`
  nodes), which breaks the editable-text-slot pipeline — never use it as the
  extraction source SVG.
- Raster vectorization (`vtracer`/`potrace`) is **not** in the approved set:
  keep embedded rasters as optimized raster files.

Do not treat missing source-to-SVG providers as a blocker for jobs that already
provide page-level SVG and PNG reference files. Do treat them as blockers when
the requested source type requires that provider.

## Embedded Raster And Base64 Policy

PDF/PPTX-to-SVG converters may emit `<image href="data:image/...;base64,...">`
inside otherwise valid SVG. This is expected, not a failure.

Required handling:

1. Decode and externalize embedded base64 rasters with
   `slide-system/scripts/externalize_svg_images.py`.
2. Store raster files under `artifact/assets/`.
3. Record `reference_count`, `unique_file_count`, `mime_type`, `byte_size`, and
   `sha256` in `evidence/external-images.json`.
4. Preserve original SVG geometry: `x`, `y`, `width`, `height`, `transform`,
   `clip-path`, `mask`, z-order, and paint order.

Vectorization of embedded rasters is not allowed (`vtracer`/`potrace` are
outside the approved library set in `REQUIREMENTS.md`). Keep rasters as
optimized raster files with their original `transform`/`clip-path`/`mask`
contract intact.

## Recommended Source Normalization Output

Source conversion providers should emit a source package before extraction:

```text
outputs/source-svg/<job-id>/
  pages/page-001/source.svg
  pages/page-001/reference.png
  pages/page-001/source-metadata.json
  manifest.json
```

The manifest should record input checksum, provider, provider version/command,
page size, fonts warning, raster/base64 handling, optional vectorization
decisions, fallback provider use, and render-parity evidence.

## Satisfying Missing Requirements

Only install from the approved list in `REQUIREMENTS.md`:

- `xmllint`: ships with libxml2 (preinstalled on macOS; `apt install libxml2-utils` on Debian/Ubuntu).
- raster optimizer: `sips` is built into macOS; `optimize_svg.py` silently skips raster optimization when absent — never a hard requirement.
- SVG renderer: use the built-in Playwright/Chromium for parity checks; do not install standalone renderers.
- PDF provider (PyMuPDF, the only approved PDF→SVG provider): install into the
  repo-local venv with `setup.ps1` on Windows or `setup.sh` on macOS/Linux. Do NOT
  `pip install` into the system interpreter: Homebrew/Debian pythons are PEP 668
  externally-managed and refuse with `error: externally-managed-environment`;
  never work around that with `--break-system-packages`. The preflight probe
  checks PyMuPDF in the project `.venv`.
- PPTX provider: install LibreOffice from its official download, then verify fonts used by the deck are installed.

A missing `optional` tool never blocks extraction — it is recorded as deferred.
A missing source provider blocks only that source type, not SVG-package
extraction.
