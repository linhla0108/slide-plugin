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

## Optional: Docling candidate auto-detection

`analyze_with_docling.py` is an **optional** pre-step that detects *candidate*
reusable regions (pictures, tables, figures) in a PDF/PPTX so a user does not
have to name every region by hand. It changes no shared registry state:

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
  (`<label>-p<page>-<n>`). Do not ask the user to review these placeholders.
  Run `auto_stage_candidates.py <extraction-id>` to deterministically rename,
  attach retrieval metadata, scaffold one Draft per candidate, and build core
  PDF artifacts where possible. User-facing review happens only in the catalog
  Draft tab.
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
python3 slide-system/scripts/auto_stage_candidates.py <id>
```

## Automated candidate staging (Draft is the review surface)

Docling emits placeholder candidates (`<label>-p<page>-<n>`), but non-technical
users should not review that intermediate form. The default hand-off is
`slide-system/scripts/auto_stage_candidates.py`, which turns one analysis run
into real catalog Draft items:

- **Review metadata under** `outputs/component-extractions/<id>/analysis/`:
  - `candidate-reviews.json` — reviewer metadata keyed by the original
    placeholder id (the contract is
    `slide-system/schemas/candidate-review.schema.json`: `item_id`,
    `display_name`, `requested_type`, `semantic_intent`, `component_type`,
    `layout_role`, `visual_summary`, `content_structure`, `tags`, `keywords`,
    `use_cases`, `anti_use_cases`, `region`, `review_status`, `reviewer`,
    `reviewed_at`, `quality_notes`, `retrieval_notes`, …). This metadata is
    deterministic and retrieval-ready (for future hybrid retrieval/RAG); this
    task adds **no** vector search or embedding dependency.
  - `previews/<candidate-id>.png` — best-effort PDF crop previews for the
    backend/debug surface. Preview generation is non-blocking: missing PyMuPDF,
    unsupported source types, missing files, or malformed regions are reported
    as unavailable and do not create approved requests.
  - `approved/<item_id>.extraction-request.json` — written on approval; a
    single-item, schema-compatible extraction request
    (`extraction-request.schema.json`). It carries a per-candidate extraction id
    (`<run-id>-<item-id>`) so approving several candidates from one run
    scaffolds into separate output dirs instead of colliding on the run id. Feed
    it to `scaffold_extraction.py`.
- **Draft outputs:** one staged item under
  `outputs/component-extractions/<run-id>-<item-id>/items/<item-id>/`. For PDF
  sources, the script runs the core standard artifact chain:
  `convert_pdf_source.py`, `extract_editable_text_slots.py`,
  `crop_svg_region.py`, `externalize_svg_images.py`, `optimize_svg.py`,
  `apply_text_contract.py`, `validate_text_slots.py`, and
  `generate_item_preview.py`. The chain must run through a Python interpreter
  with PyMuPDF available (normally the repo `.venv`) so catalog Drafts have real
  previews and editable text slots.
- **Grouped Drafts:** related candidates from one source page may be represented
  as one parent Draft. Its carousel starts with the full grouped component, then
  shows each smaller child variant; child mappings remain on disk for evidence
  but are hidden from the main catalog list.
- **Never** publishes or mutates the registry/`visual-library.json`. Publish is
  still an explicit user action from **Components → Draft**.
- **Validation** reuses the scaffold id/intent gates as the single source of
  truth, so a Docling placeholder or positional/generic id can never enter the
  Draft queue. Invalid extraction ids and path traversal are rejected.

The catalog server exposes `POST /api/stage-candidates` for the same automation.
The lower-level `candidate_review.py` API remains available for tests/debugging
but is not a user-facing review surface.
