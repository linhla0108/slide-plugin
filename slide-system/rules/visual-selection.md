# Visual Selection

Only items with `status: published` may be selected for generated decks.

Score candidates with these weights:

| Criterion | Weight |
|---|---:|
| Semantic intent | 35 |
| Content structure | 20 |
| Information density | 10 |
| Brand and visual language | 10 |
| Required export compatibility | 15 |
| Accessibility and constraints | 10 |

Decision thresholds:

- `75-100`: reuse the published item.
- `55-74`: create a slide-local adaptation without changing the shared item.
- Below `55`: create a slide-local custom structure.

Always record selected and rejected candidates with scores and reasons.
Extraction may be recommended, but generation must never trigger extraction
automatically.

