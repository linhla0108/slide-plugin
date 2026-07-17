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

- **Semantic coverage = concept groups.** A request declares `concepts`: OR
  alternatives within a group, AND across groups. `semantic_intent` measures
  matched_groups/total_groups, so `intent`/`tags` only rank/retrieve and a synonym
  or descriptor never dilutes the required denominator. `--require-concepts` makes
  this mandatory for new runs; a legacy run without `concepts` falls back to the
  flat `intent+tags` denominator.
- **`reuse`** (automatic) requires BOTH `>= 78` total AND `>= 24.5` semantic_intent
  (`0.7 x 35`), plus published + shape-compatible + auto-reuse-eligible (no failed
  QA) + immutable-safe + not already used in the deck — AND the item is a reviewed
  generic-buildable template (`build_scope.mode == "generic"`). A mediocre total
  never authorises reuse; neither does a strong semantic score on a specific slide.
- **Buildability (`build_scope`).** A semantic match is NOT proof a slide can be
  scaffolded and filled from the brief. `build_scope.mode == "generic"` marks a
  reviewed, role-generic template a short brief can fill; `source-specific` (or
  ABSENT/unreviewed — the conservative default) means published + catalog/manually
  selectable but NEVER auto-reused. Set it from a real review of the item's slot
  contract (roles, count/capacity, source-context), not a filename/ID rule. An
  explicit `component_id` pick may still use a source-specific item, but routes
  through the scaffold/fidelity gate and fails closed if the slots cannot be filled.
- **`needs_component`**: everything else automatic. Build nothing; hand the slide
  back to the user with a reason and suggested searches.
- **`custom-local`**: ONLY when the user set `unresolved_policy: "custom-local"`.
- A user may also name a component outright with `component_id`; that is still
  `reuse`, and it is validated + fidelity-gated like any other.

Always record selected and rejected candidates with scores and reasons.
Extraction may be recommended, but generation must never trigger extraction
automatically.

Prefer published reusable resources before creating slide-local structures, but
do not create or modify public reusable components without explicit user
approval.
