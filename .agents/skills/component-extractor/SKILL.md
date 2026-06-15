---
name: component-extractor
description: Interpret natural-language requests to manually extract user-selected slide regions, full slides, page ranges, or complete decks into staged reusable components, sections, templates, styles, icons, backgrounds, characters, or assets with deduplication and review evidence.
---

# Component Extractor

Use only when the user explicitly asks to extract one or more visual regions.

## Required Input

Accept natural-language scope. Normalize the user's wording before deciding
that information is missing. Do not require the user to repeat their request
in schema-like language.

Resolve these values from the request:

- Source file or folder path.
- Slide/page scope.
- Region/object scope.

Apply these defaults:

- "all slides", "every slide/page", "whole/complete/full deck", or equivalent
  means page 1 through the final page, inclusive. Inspect the source to
  determine the final page; do not ask the user for the page count.
- "everything in/on each slide", "all content on all slides", or equivalent,
  without words such as "separately", "individual", "each object", or "each
  element", means one full-slide item per page using the complete page/media
  box.
- "this slide/page" means the slide/page explicitly referenced by the user or
  available from the immediate conversation context.
- A request naming a visible region semantically, such as "the title block",
  "the orange diagram", or "the footer", is an exact user selection. Inspect
  the specified page to derive its bounds; do not demand coordinates first.

Proceed without confirmation when these rules produce one reasonable
interpretation. Do not ask the user to confirm an inferred final page, full-page
region, or exhaustive page range.

Ask one focused clarification only when a required value cannot be inferred,
the request has conflicting interpretations, or the user explicitly requests
separate object/element extraction from a source that has no reliable semantic
object boundaries, such as a PDF. Explain the specific ambiguity rather than
listing every input field again.

An explicit complete-deck or full-page request is exhaustive user selection,
not an automatic candidate scan. Do not scan a complete deck to invent or
recommend extraction candidates.

## Preflight (marker-first — do not run the script by default)

Readiness is recorded in `slide-system/registries/extract-readiness.json`.
Checking it costs one file read, not a Python process:

```bash
grep -q '"status": "ready"' slide-system/registries/extract-readiness.json 2>/dev/null \
  && echo "preflight: ready (marker)" \
  || python3 slide-system/scripts/check_base_requirements.py
```

- Marker says `ready` → proceed immediately. Do **not** run
  `check_base_requirements.py` and do not invoke the `extract-preflight` skill.
- **Exception — input is PDF or PPTX:** the marker's `ready` covers base tools
  only. Run `python3 slide-system/scripts/check_base_requirements.py --input pdf`
  (or `--input pptx`) instead — it reuses the marker (cheap) but exits 1 when
  the required source provider (PyMuPDF / LibreOffice) is missing. Stop on
  BLOCKER; never substitute another converter or a raster render.
- Marker missing or not `ready` → the fallback runs the script once; stop only
  on a `blocked` result (a required tool is missing).
- A tool fails mid-batch despite a `ready` marker → re-run the script with
  `--force` (toolchain changed).
- Missing `recommended`/`optional` tools (raster optimizer, SVG renderer) never
  block extraction or preview.

## Reference Docs (read on demand, not upfront)

Read a doc only when its branch is actually hit in the batch:

| When | Read |
|---|---|
| Input is PDF (no page-level source SVG yet) | Nothing — run `python3 slide-system/scripts/convert_pdf_source.py --pdf <file> --page <n> --item-dir <item>` (PyMuPDF, the only approved path). Do not trial other converters or render pages to PNG (allowed libraries are governed by `REQUIREMENTS.md`) |
| Input is PPTX/raster | `.agents/skills/extract-preflight/SKILL.md` § Source-To-SVG Provider Requirements |
| Unsure which extraction method fits an artifact type | `slide-system/rules/extraction-methods.md` |
| Producing an SVG artifact that carries text | `slide-system/rules/editable-text-slots.md` |
| Region has blur/shadow/glow/mask/filter/blend/complex background | `slide-system/rules/background-rendering.md` |
| Assigning stable IDs or versions | `slide-system/rules/naming-versioning.md` |
| Publishing approved items | `slide-system/workflows/publish-components.md` |

`slide-system/workflows/extract-components.md` mirrors the pipeline below — do
not read it separately.

## Pipeline

1. Validate the request, fingerprint every requested region, and check
   extraction history, aliases, and the shared registry for duplicates.
2. Scaffold one staging item per region under `outputs/component-extractions/`,
   classify the artifact, and apply its type-specific extraction method. The
   reusable visual is text-free `artifact/visual.svg` + `artifact/text-slots.json`
   only. Do not author a parallel `.html`/`.css` representation of the same
   region — it is never consumed downstream.
3. For SVG artifacts: generate the artifacts with the standard scripts — never
   hand-write `visual.svg`/`text-slots.json` (their schemas live in the
   scripts; hand-written files fail validation in rounds) and never hand-write
   per-batch `_*.py` helpers into the output folder:

   ```bash
   # PDF input only: text-preserving source SVG + QA raster (PyMuPDF)
   python3 slide-system/scripts/convert_pdf_source.py --pdf <file> --page <n> --item-dir <item>
   # source-page.svg -> text-free visual.svg + text-slots.json + evidence SVG
   python3 slide-system/scripts/extract_editable_text_slots.py --item-dir <item> [--item-dir ...]
   python3 slide-system/scripts/externalize_svg_images.py --batch <dir>
   # merge fragmented PDF background strips into one base PNG (Playwright; pixel-diff gated)
   python3 slide-system/scripts/flatten_svg_background.py --batch <dir>
   python3 slide-system/scripts/externalize_svg_images.py --batch <dir>  # refresh manifests after flatten
   python3 slide-system/scripts/optimize_svg.py --batch <dir>
   python3 slide-system/scripts/apply_text_contract.py --batch <dir>
   python3 slide-system/scripts/validate_text_slots.py --item-dir <item> [--item-dir ...]
   ```

4. For each item write `mapping.json` (the canonical record: fingerprints,
   content contract, compatibility, approval) plus a lightweight
   `evidence/notes.md` that references the source raster by path. Put the
   reusable output in `artifact/`. Do not copy source images, do not emit
   per-item `README.md`/`report.md` (`batch-report.md` is the staging summary),
   and do not commit `*-svg-manifest.json` audit dumps into `evidence/`.
5. Build one batch-level `gallery.html` as the single review surface,
   regenerate the catalog staging tab, and update extraction history.
6. Request approval per item. Publish only approved items; at publish, author
   the per-item `preview/` and confirm `evidence/` (publish requires both).

## Boundaries

- Extraction is manual-only.
- Never `mkdir` a folder before having content for it; sweep leftovers with
  `python3 slide-system/scripts/prune_empty_dirs.py outputs/component-extractions/`.
- A batch may contain multiple exact regions, but every item has independent
  status and approval.
- Complex vector, blur, shadow, glow, mask, filter, blend, and multi-stop
  gradient backgrounds become background-only PNG files.
- Foreground text and semantic content must remain separate and editable.
- Reusable SVGs must not contain semantic `<text>` or `<tspan>` nodes.
- Never render a PDF/PPTX page to PNG and use it as the visual: that bakes the
  text into pixels where `validate_text_slots.py` cannot detect it, and the
  gallery then shows baked text underneath the editable slots (double text).
  Background-only PNGs (per `background-rendering.md`) must contain zero text.
