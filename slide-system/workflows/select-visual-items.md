# Select Visual Items

1. Load only `published` items from `registries/visual-library.json`.
2. Reject deprecated, staging, brand-incompatible, or export-incompatible items.
3. Score candidates with `scripts/score_visual_items.py`.
4. Reuse scores of 75 or higher.
5. Use a slide-local adaptation for scores from 55 through 74.
6. Use a slide-local custom structure below 55.
7. Record selected and rejected candidates with reasons.
8. Record an extraction recommendation when useful. Never trigger extraction.

Select structure by semantic intent before visual resemblance.
