# Select Visual Items

1. Load only `published` items from `registries/visual-library.json`.
2. Reject deprecated, staging, brand-incompatible, or export-incompatible items.
3. Write `analysis/visual-requests.json` with one request per slide. Each request
   must include: `request_id`, `intent`, `tags`, `content_structure`, `density`,
   `brand`, `required_exports`.
4. Run the scorer in **batch mode** to score ALL item types (templates AND
   standalone components — cover, timeline, checklist, comparison, closing, CTA,
   statistics, dividers, layouts) for every slide:
   ```bash
   .venv/bin/python3 slide-system/scripts/score_visual_items.py \
       --batch-request <run>/analysis/visual-requests.json \
       --output <run>/analysis/selection-report.json
   ```
   When the brief has `base_template` from a template set, pass
   `--prefer-set <set-prefix>` for same-set scoring bonus.
   Do NOT use `--item-type template` — score ALL types so standalone
   components (cover-hero, timeline, checklist, etc.) are also considered.
5. **Validate the selection report (BLOCKING):**
   ```bash
   .venv/bin/python3 slide-system/scripts/validate_selection_report.py \
       --selection-report <run>/analysis/selection-report.json \
       --visual-requests <run>/analysis/visual-requests.json
   ```
   EXIT 0 required before HTML build. EXIT 1 = re-run step 4.
6. Reuse scores of 75 or higher.
7. Use a slide-local adaptation for scores from 65 through 74.
8. Use a slide-local custom structure below 65 (no strong match).
9. Record selected and rejected candidates with reasons.
10. Record an extraction recommendation when useful. Never trigger extraction.

Write one `analysis/visual-requests.json` and one `analysis/selection-report.json`
per run. Do not emit a separate file per section.

Select structure by semantic intent before visual resemblance.

Hand-writing `selection-report.json` is a pipeline violation — the validator
detects fake reports by checking schema, candidates array, criteria sub-scores,
and provenance fields.
