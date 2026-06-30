# Flow walkthrough: Docling Candidates -> Auto-Staged Drafts

> Candidate review is no longer the user-facing approval surface. Docling
> candidates are backend staging material. The user reviews final reusable items
> only in **Components -> Draft**, then chooses Publish or Delete.

---

## Overview

```
analyze_with_docling.py          auto_stage_candidates.py             Catalog Draft tab
(detect candidates)        (rename + metadata + scaffold)          (human final review)
        |                               |                                   |
        v                               v                                   v
analysis/
  candidate-                 analysis/approved/<id>.json        outputs/.../items/<id>/
  extraction-request.json -> candidate-reviews.json       ->    artifact/visual.svg
                                                             evidence/source-with-text.svg
                                                             preview/thumbnail.png
```

The registry and shared library are not touched by detection or auto-staging.
Generation continues to read only `published` registry items.

---

## Default Flow

```bash
python3 slide-system/scripts/analyze_with_docling.py \
  --source <file.pdf|file.pptx> \
  --extraction-id <run-id> \
  --pages 1-3

python3 slide-system/scripts/auto_stage_candidates.py <run-id>

python3 slide-system/catalog/catalog_server.py
# open http://127.0.0.1:8799/slide-system/catalog/ -> Components -> Draft
```

`auto_stage_candidates.py` does the backend work that a non-technical user
should not have to do:

- Generates semantic item ids from extracted PDF region text and layout role;
  source name/page/Docling label are fallback context only. IDs are English and
  come from visible cues such as headings, uppercase labels, repeated `Level N`
  structures, and generic localized concepts.
- Saves retrieval metadata through the same candidate-review contract.
- Writes schema-compatible approved extraction requests under
  `analysis/approved/`.
- Scaffolds each candidate into a separate Draft namespace:
  `<run-id>-<item-id>`.
- When several candidates on the same source page form one related visual set,
  creates a grouped Draft with a carousel: first the full component region,
  then the individual child variants.
- For PDF sources, runs the core artifact chain:
  `convert_pdf_source.py`, `extract_editable_text_slots.py`,
  `crop_svg_region.py`, `externalize_svg_images.py`, `optimize_svg.py`,
  `apply_text_contract.py`, `validate_text_slots.py`, and
  `generate_item_preview.py` through the Python interpreter that can import
  PyMuPDF (usually the repo `.venv`).
- Rebuilds `slide-system/catalog/catalog-data.json`.

For PDF sources, `analyze_with_docling.py` runs Docling in page-scoped worker
processes. A bad page times out or fails independently, and the run can still
use conservative PyMuPDF text/vector row candidates for pages where Docling
does not produce reusable regions.

---

## Review Boundary

The only user-facing review boundary is the Draft tab:

| Stage | User sees it? | Can publish? | Purpose |
|---|---:|---:|---|
| Docling candidate (`picture-p1-1`) | No | No | Raw detection |
| Auto-staged Draft (`sun.component.<semantic-id>`) | Yes | Yes, if gates pass | Final human review |
| Published registry item | Yes | Already published | Reusable generation input |

If artifact generation fails, the Draft can still exist but the catalog publish
readiness blocker remains visible. That prevents a broken candidate from being
published silently.

---

## Backend / Debug Surfaces

`candidate_review.py` remains as an internal compatibility layer for tests,
debugging, and explicit reject records:

- `candidate-reviews.json`
- `analysis/previews/<candidate-id>.png`
- `analysis/approved/<item-id>.extraction-request.json`

The catalog server also exposes:

| Method | Path | Action |
|---|---|---|
| POST | `/api/stage-candidates` | Auto-stage one analysis run into Drafts |
| POST | `/api/publish` | Publish a reviewed Draft |
| POST | `/api/delete` | Delete a Draft or published item |

The old top-level Review tab is intentionally removed from the UI.

---

## References

| File | Role |
|---|---|
| `slide-system/scripts/analyze_with_docling.py` | Emits raw Docling candidates |
| `slide-system/scripts/auto_stage_candidates.py` | Converts candidates into Drafts |
| `slide-system/scripts/candidate_review.py` | Internal metadata/request compatibility layer |
| `slide-system/scripts/scaffold_extraction.py` | Owns scaffold/id gates |
| `slide-system/catalog/catalog_server.py` | Serves Draft publish/delete and auto-stage API |
| `slide-system/catalog/index.html` | User-facing catalog; no Review tab |
