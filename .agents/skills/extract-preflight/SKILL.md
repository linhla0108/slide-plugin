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

```bash
python3 slide-system/scripts/check_base_requirements.py          # check or reuse marker
python3 slide-system/scripts/check_base_requirements.py --force  # re-probe, ignore marker
python3 slide-system/scripts/check_base_requirements.py --json   # machine-readable
```

Exit code `0` = ready (proceed), `1` = blocked (a required tool is missing).

## Readiness Marker

The script writes `slide-system/registries/extract-readiness.json` with the
status, the environment fingerprint, and a per-requirement result. On the next
run, if the fingerprint still matches and the status is `ready`, it prints
`REUSED marker` and returns immediately without probing again. This is the
"don't set up from scratch every time" guarantee — treat a `ready` marker with a
matching fingerprint as authoritative. Use `--force` only when you deliberately
changed the toolchain.

Do not hand-edit the marker; regenerate it with `--force`.

## Base Requirements

These are the minimum requirements for the SVG-first extractor after page SVGs
already exist.

| Requirement | Level | Why |
|---|---|---|
| `python3` | required | Run every `slide-system/scripts/` step. |
| `xmllint` | required | Validate `visual.svg` / `source-with-text.svg` stay well-formed XML. |
| raster optimizer (`sips`, `magick`, or `convert`) | recommended | Downsample / recompress embedded rasters in `optimize_svg.py`. Without it the SVG is still precision-trimmed but large images stay at source size. |
| SVG renderer (`playwright`/Chromium, `rsvg-convert`, `resvg`, `inkscape`, or `cairosvg`) | recommended | Render SVG to PNG for preview/parity checks. Chromium/Playwright is preferred for masks, clips, filters, and gallery-equivalent rendering. |

## Source-To-SVG Provider Requirements

When the user provides non-SVG inputs, preflight must check the matching provider
path before claiming the extraction environment is ready for that input type.
Keep this as a separate source-normalization layer before `component-extractor`.

| Input | Preferred provider | Level | Why |
|---|---|---|---|
| PDF | `PyMuPDF` / `fitz` or `pdf2svg`/Poppler | required for PDF-only input | Historical PDF extraction used a bundled PDF runtime to generate exact page SVGs. PyMuPDF's `page.get_svg_image(...)` can emit native SVG with embedded raster images. Poppler/pdf2svg is the open-source CLI alternative. |
| PDF fallback | MuPDF `mutool draw -F svg` | recommended | Strong fallback when Poppler/PyMuPDF output fails or a page needs a second converter. |
| PPTX | LibreOffice/`soffice --headless` to PDF, then PDF-to-SVG provider | required for PPTX input | Practical local/offline route for PowerPoint sources. Verify fonts are installed before judging fidelity. |
| PPTX high fidelity | Aspose.Slides local SDK | optional | Commercial fallback when LibreOffice fidelity is not enough. Do not use cloud converters for sensitive sources. |
| PNG/JPG exact | SVG image wrapper | required for raster input | Preserve appearance by wrapping the raster in `<svg><image .../></svg>` when true vectorization is not appropriate. |
| PNG/JPG vectorization | `vtracer` or `potrace` | optional | Trace flat art, icons, logos, or monochrome line art only when render parity passes. Do not trace photos/screenshots by default. |

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

Optional vectorization:

- Use `vtracer` for color flat art, icons, logos, diagrams, and small
  illustration fragments.
- Use `potrace` for binary or monochrome line art after thresholding.
- Never vectorize photos, screenshots, textures, or rich gradients by default;
  keep them raster and optimize them instead.
- Replace an `<image>` with traced paths only when HTML/Chromium render parity
  against the pre-vectorized SVG passes. If parity fails, keep the raster.
- If an embedded raster sits under a matrix transform, clip, or mask, the traced
  replacement must preserve that same transform/clip/mask contract.

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

- `xmllint`: ships with libxml2 (preinstalled on macOS; `apt install libxml2-utils` on Debian/Ubuntu).
- raster optimizer: `sips` is built into macOS; elsewhere install ImageMagick (`magick`/`convert`).
- SVG renderer: prefer Playwright/Chromium for project parity checks; use `brew install librsvg` (`rsvg-convert`) or `pip install cairosvg` only when its SVG feature coverage is sufficient for the source.
- PDF providers: `python3 -m pip install PyMuPDF`, `brew install poppler pdf2svg`, or `brew install mupdf`.
- PPTX provider: `brew install --cask libreoffice`, then verify fonts used by the deck are installed.
- raster vectorizers: `python3 -m pip install vtracer` and/or `brew install potrace`.

A missing `optional` tool never blocks extraction — it is recorded as deferred.
A missing source provider blocks only that source type, not SVG-package
extraction.
