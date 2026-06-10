---
name: component-extractor
description: Manually extract exact user-selected slide regions into staged reusable components, sections, templates, styles, icons, backgrounds, characters, or assets with deduplication and review evidence.
---

# Component Extractor

Use only when the user explicitly asks to extract one or more visual regions.

## Required Input

Each requested item must include:

- Source file or folder path.
- Slide or page number.
- Exact region bounds or source object ID.

If any value is missing, ask the user before processing. Do not scan a complete
deck for candidates.

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
| Input is PDF/PPTX/raster (no page-level `source.svg` yet) | `.agents/skills/extract-preflight/SKILL.md` § Source-To-SVG Provider Requirements — PDF uses PyMuPDF (`page.get_svg_image`) only; do not trial other converters (allowed libraries are governed by `REQUIREMENTS.md`) |
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
3. For SVG artifacts: keep the source-with-text SVG in `evidence/`, remove
   semantic text from the reusable visual, and emit normalized editable slots
   per `editable-text-slots.md`. Then run the standard batch scripts — never
   hand-write per-batch `_*.py` helpers into the output folder:

   ```bash
   python3 slide-system/scripts/externalize_svg_images.py --batch <dir>
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
- A batch may contain multiple exact regions, but every item has independent
  status and approval.
- Complex vector, blur, shadow, glow, mask, filter, blend, and multi-stop
  gradient backgrounds become background-only PNG files.
- Foreground text and semantic content must remain separate and editable.
- Reusable SVGs must not contain semantic `<text>` or `<tspan>` nodes.
