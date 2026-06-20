# Plan Slide Deck

Start from the confirmed intake brief (`workflows/intake-and-triage.md`).
Expand it into:

- Requirement brief and audience.
- Exact content model and source authority.
- Slide titles and narrative order.
- Section map and reading order.
- Divergence summary when supplied sources disagree.
- Visual direction and brand pack.
- Base template adoption: when `base_template` is set in the brief, adopt that
  published template's layout structure as the starting point for matching
  slides, and plan the remaining slides normally. Note the template's set prefix
  (second segment of the ID, e.g. `interview-workshop-sunriser`) for the visual
  selection step — it drives `--prefer-set` scoring.
- Export contract and editability level.
- Known limitations and unresolved decisions.
- **Intent tags per slide** for visual-library matching. Each slide must specify
  `intent` tags that map to visual-library item types — not just template
  matching but also standalone component matching. Examples:
  - A cover slide: `["cover", "title", "brand"]`
  - A timeline slide: `["timeline", "process", "steps"]`
  - A checklist slide: `["checklist", "list", "action-items"]`
  - A comparison slide: `["comparison", "table", "versus"]`
  - A statistics slide: `["statistics", "metrics", "data"]`
  - A closing slide: `["closing", "cta", "next-steps"]`
  These intent tags feed directly into `visual-requests.json` for the scorer.

The title sequence must communicate the deck story without body text. Preserve
source content verbatim when the request is a reconstruction or polish task.
