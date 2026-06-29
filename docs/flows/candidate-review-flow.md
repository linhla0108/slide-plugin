# Flow walkthrough: Candidate Review (Docling → rename/metadata → approve)

> The analysis-only review stage that sits between Docling auto-detect and
> `scaffold_extraction.py`. Lets a non-technical reviewer rename each placeholder
> candidate, attach retrieval-ready metadata, and approve it for extraction —
> without publishing, scaffolding, or touching the shared registry/library.
>
> Based on `slide-system/scripts/candidate_review.py`,
> `slide-system/scripts/analyze_with_docling.py`,
> `slide-system/catalog/catalog_server.py` (Review tab), and
> `slide-system/schemas/candidate-review.schema.json` (added 2026-06-29).

---

## Overview

```
analyze_with_docling.py            candidate_review.py                scaffold_extraction.py
(detect placeholders)        (rename + metadata + approve)            (build staging items)
        │                                │                                    │
        ▼                                ▼                                    ▼
┌───────────────────┐   review   ┌───────────────────────┐  approved   ┌──────────────────┐
│ candidate-        │──────────▶ │ candidate-reviews.json │──────────▶ │ approved/<id>.   │
│ extraction-       │            │ (per-candidate meta)   │            │ extraction-      │
│ request.json      │            │ pending/approved/reject│            │ request.json     │
└───────────────────┘            └───────────────────────┘            └──────────────────┘
        all under outputs/component-extractions/<id>/analysis/            (feed to scaffold)
```

Every write lands under the run's `analysis/` directory. The registry,
`visual-library.json`, the catalog Draft tab, and publish are never touched by
this stage.

---

## Lifecycle

```
            ┌─────────┐   save/edit (PATCH)   ┌─────────┐
   detect → │ pending │ ◀───────────────────▶ │ pending │
            └────┬────┘                       └────┬────┘
                 │ approve (valid)                 │ reject (with reason)
                 ▼                                 ▼
     ┌────────────────────────┐            ┌──────────────┐
     │ approved_for_extraction│            │   rejected    │
     │ writes approved/<id>.  │            │ no approved   │
     │ extraction-request.json│            │ artifact      │
     └────────────────────────┘            └──────────────┘
```

- **Editing an approved candidate reverts it to `pending`** and removes the
  stale `approved/<id>.extraction-request.json`, so an approval can never
  outlive the metadata it was built on (a rename removes the old-name file too).
- **Rejecting removes any approved artifact** and requires a reason.

---

## Validation (the approve gate)

The approve gate reuses the exact `scaffold_extraction.py` id/intent rules as
the single source of truth, plus the metadata contract. A candidate cannot be
approved when:

| Blocker | Message (plain language) |
|---|---|
| `item_id` still a Docling placeholder (`picture-p1-1`) | "still the Docling placeholder. Rename it…" |
| `item_id` positional/generic (`top-left`, `center`, `page-01`) | "positional/generic. Describe the visual content…" |
| `item_id` malformed | "may only contain lowercase letters, numbers, dot, dash, underscore…" |
| Required metadata empty (`display_name`, `requested_type`, `component_type`, `layout_role`, `visual_summary`, `semantic_intent`, `content_structure`, `tags`, `keywords`, `use_cases`) | "<Field> is required." / "At least one <field> value is required." |
| `semantic_intent` only generic | "Semantic intent is only generic. Add descriptive values…" |
| Region malformed | "Region is malformed (need x, y, width, height, unit)." |

Invalid extraction ids and path traversal (`..`, `a/b`) are rejected before any
file is touched.

---

## Surfaces

### UI — catalog Review tab

```bash
python3 slide-system/catalog/catalog_server.py
# open http://127.0.0.1:8799/slide-system/catalog/  → "Review" tab
```

Left: analysis runs with pending/approved/rejected counts. Middle: candidates
for the selected run. Right: a form to rename + fill metadata, with **Save
draft**, **Approve for extraction**, and **Reject** (with reason). Validation
errors are shown in plain language under the form.

### CLI / API

```bash
python3 slide-system/scripts/candidate_review.py list
python3 slide-system/scripts/candidate_review.py show <extraction-id>
python3 slide-system/scripts/candidate_review.py approve <extraction-id> <candidate-id>
python3 slide-system/scripts/candidate_review.py reject  <extraction-id> <candidate-id> --reason "…"
```

HTTP (served by `catalog_server.py`):

| Method | Path | Action |
|---|---|---|
| GET | `/api/candidates` | list analysis runs with counts |
| GET | `/api/candidates/<extraction_id>` | candidates + saved metadata for one run |
| PATCH | `/api/candidates/<extraction_id>/<candidate_id>` | save draft metadata (resets to pending) |
| POST | `/api/candidates/<extraction_id>/<candidate_id>/approve` | validate + write approved request |
| POST | `/api/candidates/<extraction_id>/<candidate_id>/reject` | mark rejected (reason required) |

---

## After approval

Approval only writes `analysis/approved/<item_id>.extraction-request.json`. Each
approved request carries its own scaffold extraction id (`<run-id>-<item-id>`)
so approving several candidates from one run scaffolds them into separate output
directories instead of colliding on the shared run id. To actually create
staging items, feed it to the scaffold as usual:

```bash
python3 slide-system/scripts/scaffold_extraction.py \
    --request outputs/component-extractions/<id>/analysis/approved/<item_id>.extraction-request.json
```

The item then goes through the normal staging → catalog Draft → publish gate.
Generation still reads only `published` registry items.

---

## References

| File | Role |
|---|---|
| `slide-system/scripts/candidate_review.py` | Review/rename/approve logic + CLI |
| `slide-system/schemas/candidate-review.schema.json` | Reviewed-candidate metadata contract |
| `slide-system/schemas/extraction-request.schema.json` | Shape of the approved request |
| `slide-system/scripts/analyze_with_docling.py` | Emits the placeholder candidates |
| `slide-system/scripts/scaffold_extraction.py` | Consumes the approved request; owns the id gate |
| `slide-system/catalog/catalog_server.py` | Serves the Review tab + candidate API |
| `slide-system/rules/extraction-methods.md` | Rule: candidate review (analysis-only) |
