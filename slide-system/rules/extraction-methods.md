# Extraction Methods

The reusable visual is a single source of truth: text-free `artifact/visual.svg`
paired with `artifact/text-slots.json`. Do **not** also author a parallel
`.html`/`.css` representation of the same region — the SVG visual plus editable
text slots is the canonical artifact that every downstream surface (gallery
preview, catalog, and the consuming job's export) draws from. The extractor does
not produce per-component PPTX/PDF; the main job embeds `visual.svg` as an image
when it builds a deck (see `export-compatibility.md`).

| Artifact | Primary method | Export-safe fallback |
|---|---|---|
| Card or component | Visual-only SVG + editable text slots | SVG-image embed (raster fallback) in the consuming job |
| Section pattern | Visual-only SVG + editable text slots | SVG-image embed plus safe assets |
| Full-slide template | Visual-only SVG + editable text slots (layout contract, no source copy) | SVG-image embed with editable text overlay |
| Simple style | CSS tokens or safe SVG | Native PowerPoint treatment |
| Simple icon | Clean standalone SVG | Transparent PNG |
| Complex icon | Simplified safe SVG | Transparent PNG |
| Solid or simple background | CSS or native shapes | Safe SVG |
| Passive complex background field | Background-only PNG | PNG |
| Complex foreground or decorative element | Native/SVG when safe | Transparent PNG overlay |
| Blur, shadow, or glow | Native/CSS when safe | Background-only PNG for passive effects; transparent PNG overlay for element effects |
| Mask, filter, or blend mode | Native/SVG when safe | Transparent PNG overlay unless it is purely passive background |
| Blended multi-stop gradient | CSS/native when safe | Background-only PNG for passive fields; transparent PNG overlay for element-local effects |
| Photo or texture | Original raster plus crop metadata | Optimized PNG or JPEG |
| Dio or character | Approved source asset | PNG |

Every reusable item must be independent from one slide's hard-coded text and
coordinates. Store semantic intent, fields, variables, source mapping,
compatibility, limitations, previews, and evidence.

For SVG-based items, follow `editable-text-slots.md`. Source text is evidence;
the reusable visual must be text-free and paired with normalized editable text
slots.

## Optional: Docling candidate auto-detection (analysis-only)

`analyze_with_docling.py` is an **optional** pre-step that detects *candidate*
reusable regions (pictures, tables, figures) in a PDF/PPTX so a user does not
have to name every region by hand. It is analysis-only and changes no shared
state:

- It writes only under
  `outputs/component-extractions/<extraction-id>/analysis/`:
  `page-analysis.json`, `docling-report.json`, and — only when at least one
  candidate is detected — `candidate-extraction-request.json`. When no reusable
  regions are found, the request file is NOT written (the schema requires
  `items.minItems == 1`); `docling-report.json` records
  `candidate_request_written: false`. This `analysis/` directory may coexist
  with a later `scaffold_extraction.py` run for the same `extraction-id` — the
  scaffold preserves it and proceeds.
- It never publishes, never mutates the registry, and never writes a reusable
  library artifact. **PyMuPDF remains the canonical PDF->SVG provider**; Docling
  does not replace the extraction pipeline.
- The emitted `candidate-extraction-request.json` is schema-compatible with
  `extraction-request.schema.json`, but its `item_id`s are placeholders
  (`<label>-p<page>-<n>`). A human must rename them to semantic ids and confirm
  regions before `scaffold_extraction.py` consumes the request — the scaffold
  naming gate rejects these placeholders on purpose. Approval is still required
  before any candidate becomes a published, reusable item.
- If Docling is not installed the script exits with a clear message and writes
  nothing. Docling normally runs **locally** (`pip install docling`); a
  project-scoped Docling MCP server is an optional alternative and is never
  required by this pipeline.
- OCR is off by default for text-first slide PDFs. Use `--ocr` only for scanned
  PDFs. Use `--pages <n|start-end>` for focused review, and adjust
  `--min-area`/`--max-area` when the default candidate filter is too strict or
  too loose for icon-heavy or full-bleed pages.

Run example:

```bash
python3 slide-system/scripts/analyze_with_docling.py \
    --source <file.pdf|file.pptx> --extraction-id <id> --pages 1-3
```
