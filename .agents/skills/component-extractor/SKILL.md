---
name: component-extractor
description: Extract user-selected slide regions into staged reusable components, sections, templates, styles, icons, backgrounds, characters, or assets with deduplication and review evidence. Default mode is component-level; full-slide templates are created only after component extraction when the user opts in.
---

# Component Extractor

Use only when the user explicitly asks to extract one or more visual regions.

## Required Input

Default extraction mode is **component-level**. Every item must target a
specific visual element — a card, chart, icon, background pattern, section
layout, or other reusable building block — not an entire page.

Resolve these values from the request:

- Source file or folder path.
- Slide/page scope.
- Region/object scope — the specific visual element(s) to extract.

These values are written into an **extraction-request JSON** — the mandatory
input interface to the pipeline. `scaffold_extraction.py --request <file.json>`
(`--request` is required) consumes it; the schema is
`slide-system/schemas/extraction-request.schema.json` and a starter lives at
`slide-system/boilerplates/extraction-request.json`. Each item must carry
`item_id`, `slide_or_page`, `region`, `requested_type`, and `semantic_intent`
(the scaffold gate rejects missing/empty fields — see Naming contract below).

### Interpreting scope

- A request naming a visible element semantically ("the title block",
  "the orange chart", "the footer") is an exact user selection. Inspect
  the page to derive its bounds.
- "all components on this slide" means identify each distinct visual element
  on the page and extract them separately with semantic names.
- "this slide" or "this page" without further narrowing: extract as
  components first — identify and name each visual element. After extraction
  completes, ask the user whether they also want a full-slide template
  that reuses the same artifacts.

### Full-page scope

When the user explicitly requests full-page or full-deck extraction
("extract all slides", "extract the whole deck"):

1. For each page, inspect the content and auto-assign semantic component
   names based on visual content (e.g., `cover-title-branded`,
   `section-divider-numbered`, `agenda-numbered-list`). Do NOT stop to
   ask the user to approve the breakdown — proceed directly to extraction.
   The `scaffold_extraction.py` naming gate is the safety net; if a name
   is too generic, the script will reject it.
2. After component extraction completes, automatically promote all
   extracted pages to full-slide templates (full set matching the
   original deck). Do NOT ask which pages to promote — default is all.

### Naming contract

Every `item_id` must be a semantic descriptor of the visual content.

Prohibited patterns (`scaffold_extraction.py`'s `_BANNED_ID` gate rejects these):
- Numeric-suffixed placeholders: `page-<n>`, `slide-<n>`, `slide-<n>-full`,
  `item-<n>` (e.g. `page-01`, `slide-3-full`).
- A purely numeric id (e.g. `42`).
- A positional-only id built from direction words — `top`/`bottom`/`left`/
  `right`/`center`/`centre`/`middle`/`upper`/`lower`, alone or joined
  (e.g. `top-left`, `center`, `bottom-right`).
- A Docling draft placeholder `<label>-p<page>-<n>` (e.g. `picture-p1-1`,
  `table-p10-1`) minted by `analyze_with_docling.py` — rename it to a semantic
  id before scaffolding.

A semantic name that merely starts with a direction word is fine
(`left-rail`, `top-banner`). The gate also rejects items whose
`semantic_intent` is only generic values (`full-page extraction`,
`full-slide`, `page`).

Good examples: `metric-card`, `timeline-horizontal`, `org-chart-radial`,
`salary-table-header`, `goal-cover-title`, `orange-wave-background`

If any value is missing or ambiguous, ask one focused clarification.
Do not infer and proceed silently.

### Optional: auto-detect candidate regions (Docling)

When the user wants help finding the reusable parts ("suggest the reusable
parts", "look through this file"), an optional analysis-only pre-step can
detect candidate regions instead of naming each by hand:

```bash
python3 slide-system/scripts/analyze_with_docling.py \
    --source <file.pdf|file.pptx> --extraction-id <id> [--pages 1|2-4]
```

It writes analysis under `outputs/component-extractions/<id>/analysis/`. When
at least one candidate is detected, it also writes
`candidate-extraction-request.json`; when none are found, it writes only
`page-analysis.json` and `docling-report.json`. It never publishes, never
touches the registry, and never writes a library artifact. Review the draft
with the user, rename each `item_id` to a semantic descriptor, then feed the
cleaned request to `scaffold_extraction.py`. If Docling is not installed it
exits cleanly with a message; just proceed with the normal manual flow. See
`slide-system/rules/extraction-methods.md` → "Optional: Docling candidate
auto-detection". OCR is off by default for text-first slide PDFs; use `--ocr`
only for scanned PDFs. Tiny decorative candidates are filtered by default
(`--min-area 0.015`) and can be relaxed for icon-heavy pages.

### Optional: candidate review / rename / metadata (before scaffold)

Between Docling auto-detect and `scaffold_extraction.py` there is an
**analysis-only review layer** (`slide-system/scripts/candidate_review.py`,
served through the catalog's **Review** tab) so a non-technical user can rename
each placeholder and attach retrieval-ready metadata before anything is
scaffolded:

- It reads the run's `candidate-extraction-request.json` and writes only under
  the same `analysis/` directory: `candidate-reviews.json` (the reviewer
  metadata, keyed by the original placeholder id) and, on approval,
  `approved/<item_id>.extraction-request.json` (a schema-compatible request).
- It NEVER publishes, never mutates the registry/`visual-library.json`, and
  never scaffolds. Approval only writes the reviewed request artifact; a human
  still runs `scaffold_extraction.py` and the publish gate afterward.
- The approve gate reuses the scaffold id/intent rules, so a Docling
  placeholder, a positional/generic id, or missing required metadata can never
  be approved. The metadata contract is
  `slide-system/schemas/candidate-review.schema.json`.
- UI: serve `catalog_server.py` and open the **Review** tab
  (`http://127.0.0.1:8799/slide-system/catalog/`). API/CLI:
  `python3 slide-system/scripts/candidate_review.py list|show|approve|reject`.
- After a candidate is `approved_for_extraction`, feed its
  `analysis/approved/<item_id>.extraction-request.json` to
  `scaffold_extraction.py --request ...` as usual. Each approved request carries
  a per-candidate extraction id (`<run-id>-<item-id>`), so approving several
  candidates from one run scaffolds into separate output dirs without colliding.

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
   region — it is never consumed downstream. The PDF→SVG path converts the whole
   page, so a component-level item MUST be cropped to its `source.region` with
   `crop_svg_region.py` (step 3) — otherwise the artifact is the entire slide
   with text stripped, not a single component.
3. For SVG artifacts: generate the artifacts with the standard scripts — never
   hand-write `visual.svg`/`text-slots.json` (their schemas live in the
   scripts; hand-written files fail validation in rounds) and never hand-write
   per-batch `_*.py` helpers into the output folder:

   ```bash
   # PDF input only: text-preserving source SVG + QA raster (PyMuPDF)
   python3 slide-system/scripts/convert_pdf_source.py --pdf <file> --page <n> --item-dir <item>
   # source-page.svg -> text-free visual.svg + text-slots.json + evidence SVG
   python3 slide-system/scripts/extract_editable_text_slots.py --item-dir <item> [--item-dir ...]
   # crop the full-page visual down to the selected component region (source.region
   # in mapping.json). REQUIRED for component-level items — without it visual.svg
   # stays the whole slide. No-op for a full-page region; idempotent.
   python3 slide-system/scripts/crop_svg_region.py --item-dir <item> [--item-dir ...]
   python3 slide-system/scripts/externalize_svg_images.py --batch <dir>
   # merge fragmented PDF background strips into one base PNG (Playwright; pixel-diff gated)
   python3 slide-system/scripts/flatten_svg_background.py --batch <dir>
   python3 slide-system/scripts/externalize_svg_images.py --batch <dir>  # refresh manifests after flatten
   python3 slide-system/scripts/optimize_svg.py --batch <dir>
   python3 slide-system/scripts/apply_text_contract.py --batch <dir>
   python3 slide-system/scripts/validate_text_slots.py --item-dir <item> [--item-dir ...]
   # decompose the cropped region into its DISTINCT components and classify
   # them: spatially cluster on-canvas objects, then merge identical /
   # same-shape-different-color instances into ONE representative each (e.g.
   # 5 colored Level cards -> 1 class x5). Writes artifact/components/*.svg +
   # components-manifest.json. The catalog Draft then previews one SVG per
   # distinct component + the source region for comparison, instead of the
   # glued strip. Needs Chromium (measure_svg_groups.js); skip only if absent.
   python3 slide-system/scripts/classify_page_components.py --item-dir <item> [--item-dir ...]
   ```

4. For each item write `mapping.json` (the canonical record: fingerprints,
   content contract, compatibility, approval) plus a lightweight
   `evidence/notes.md` that references the source raster by path. Put the
   reusable output in `artifact/`. Do not copy source images, do not emit
   per-item `README.md`/`report.md` (`batch-report.md` is the staging summary),
   and do not commit `*-svg-manifest.json` audit dumps into `evidence/`.
5. Build one batch-level `gallery.html` as the single review surface,
   regenerate the catalog staging tab, and update extraction history.
   Then serve the catalog so the user can review (and Publish/Delete) — do this
   automatically once the batch is built, and whenever the user asks to "see the
   preview/catalog":

   ```bash
   # start in the BACKGROUND (long-running); reuse it if already up on 8799
   python3 slide-system/catalog/catalog_server.py
   ```

   Give the user **http://127.0.0.1:8799/slide-system/catalog/**. Always serve
   via `catalog_server.py`, never `python3 -m http.server` or VS Code Live
   Server — the Publish/Delete buttons POST to `/api/*`, which only the control
   server implements (a bare static server returns 501, Live Server returns 405).
6. Request approval per item. Publish only approved items; at publish, author
   the per-item `preview/` and confirm `evidence/` (publish requires both).

### Template promotion (automatic for full-deck extraction)

When the extraction scope was a full page or full deck, promote all
pages to templates automatically — do not ask which ones:

1. Create a new item in the same batch with `requested_type: "template"`.
2. The template's `candidate_stable_id` follows `sun.<set-slug>.<slide-slug>`
   pattern (e.g., `sun.kick-off-2026.01-cover`).
3. The template reuses the same `artifact/visual.svg` and
   `artifact/text-slots.json` from the component extraction — do not
   re-run the extraction pipeline.
4. Write a new `mapping.json` with type `template` pointing to the shared
   artifacts.
5. The template goes through the same approval gate before publishing.

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
