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

## Optional: candidate review / rename / metadata (analysis-only)

Docling emits placeholder candidates (`<label>-p<page>-<n>`). Before they can be
scaffolded a human must rename each to a semantic id and confirm it. The
**candidate review layer** (`slide-system/scripts/candidate_review.py`, surfaced
in the catalog's **Review** tab) makes this reviewable for a non-technical user
and keeps the same analysis-only guarantees as the Docling pre-step:

- **Lifecycle:** `pending` → (`approved_for_extraction` | `rejected`). Editing an
  approved candidate reverts it to `pending` and drops the stale approved
  artifact, so an approval can never outlive the metadata it was based on.
- **Writes only under** `outputs/component-extractions/<id>/analysis/`:
  - `candidate-reviews.json` — reviewer metadata keyed by the original
    placeholder id (the contract is
    `slide-system/schemas/candidate-review.schema.json`: `item_id`,
    `display_name`, `requested_type`, `semantic_intent`, `component_type`,
    `layout_role`, `visual_summary`, `content_structure`, `tags`, `keywords`,
    `use_cases`, `anti_use_cases`, `region`, `review_status`, `reviewer`,
    `reviewed_at`, `quality_notes`, `retrieval_notes`, …). This metadata is
    deterministic and retrieval-ready (for future hybrid retrieval/RAG); this
    task adds **no** vector search or embedding dependency.
  - `approved/<item_id>.extraction-request.json` — written on approval; a
    single-item, schema-compatible extraction request
    (`extraction-request.schema.json`). It carries a per-candidate extraction id
    (`<run-id>-<item-id>`) so approving several candidates from one run
    scaffolds into separate output dirs instead of colliding on the run id. Feed
    it to `scaffold_extraction.py`.
- **Never** publishes, mutates the registry/`visual-library.json`, or scaffolds.
  Approval is review-only; the scaffold and publish gates still run afterward.
- **Validation** reuses the scaffold id/intent gates as the single source of
  truth, so a Docling placeholder, a positional/generic id, or missing required
  metadata is rejected with plain-language messages and produces no approved
  request. Invalid extraction ids and path traversal are rejected.

UI: serve `catalog_server.py`, open the **Review** tab. Scriptable equivalent:

```bash
python3 slide-system/scripts/candidate_review.py list
python3 slide-system/scripts/candidate_review.py show <extraction-id>
python3 slide-system/scripts/candidate_review.py approve <extraction-id> <candidate-id>
python3 slide-system/scripts/candidate_review.py reject  <extraction-id> <candidate-id> --reason "…"
```

The catalog server exposes the same actions over HTTP:
`GET /api/candidates`, `GET /api/candidates/<extraction_id>`,
`PATCH /api/candidates/<extraction_id>/<candidate_id>`, and
`POST /api/candidates/<extraction_id>/<candidate_id>/{approve,reject}`.
