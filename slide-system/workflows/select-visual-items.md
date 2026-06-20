# Select Visual Items

1. Load only `published` items from `registries/visual-library.json`.
2. Reject deprecated, staging, brand-incompatible, or export-incompatible items.
3. Score candidates with `scripts/score_visual_items.py`.
   For template selection, invoke the scorer with `--item-type template` so only
   registry items of type `template` are scored.
   When the brief has `base_template` and it belongs to a template set
   (determined by ID prefix, e.g. `sun.interview-workshop-sunriser.01-cover` →
   set prefix `interview-workshop-sunriser`), pass
   `--prefer-set <set-prefix>` to the scorer. This encourages visual
   consistency across the deck by giving same-set items a +5 bonus.
4. Reuse scores of 75 or higher.
5. Use a slide-local adaptation for scores from 55 through 74.
6. Use a slide-local custom structure below 55.
7. Record selected and rejected candidates with reasons.
8. Record an extraction recommendation when useful. Never trigger extraction.

Write one `analysis/visual-requests.json` and one `analysis/selection-report.json`
per run, keyed by section. Do not emit a separate file per section.

Select structure by semantic intent before visual resemblance.

When `base_template` is set in the confirmed brief, auto-assign a score of 100 to
slides whose intent matches the chosen template, and score the remaining slides
normally via `scripts/score_visual_items.py`.
