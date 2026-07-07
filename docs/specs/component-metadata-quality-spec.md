# Spec: Component Metadata Quality Enforcement

> Status: DRAFT — awaiting human review (Phase 1 / Specify). Do not implement
> the gate (tasks #2/#3) until this spec is approved.
> Author: Claude (slide-generator session) · Date: 2026-07-07

## Assumptions (correct me before I proceed)

1. **`visual-library.json` is the semantic-metadata authority.** Verified: the
   `build_registry.py` header states intent/tags/content_structure live only in
   this file; publish copies artifact/preview/evidence, not semantic metadata.
2. **The scorer math is fixed as read today** (`score_visual_items.py` v3.1.0):
   `semantic_intent = 35 × (matched request terms / all request terms)`;
   `content_structure = 20 × (…)`; a published sun-studio item with empty
   intent/tags/cs floors at **45** (density 10 + brand 10 + export 15 + a11y 10);
   semantic floor = **10.5**; adapt ≥65; reuse ≥75. Any component with empty or
   non-canonical metadata is therefore structurally unselectable.
3. **Publish/stage entry points are** `auto_stage_candidates.py` (docling
   auto-staging) and `publish_extraction.py`, with `quality_gate.py` already
   present as a gate host. ← VERIFY these are the right hook points before coding.
4. **The 5 hand-patched components** (circle-badge-set, overlap-circle-set,
   hexagon-diagram, goal-setting-checklist-table, translator-…-coach-card-set)
   were patched directly in `visual-library.json` this session. They must be
   re-validated against the enforced schema, not grandfathered.
5. **Docling auto-staged components carry OCR-noise as `intent`** (e.g. raw slide
   text). These are not merely "thin" — they are actively wrong and must be
   rejected or quarantined, not just backfilled.

## Objective

**Problem (root cause):** published components ship with substandard semantic
metadata — empty `intent`/`tags`/`content_structure` (manual extractions) or
OCR-noise (docling auto-staged). Nothing enforces metadata quality at publish.
Because the scorer selects on canonical-vocab overlap, these components are pinned
at the 45-pt no-metadata floor (< adapt floor 65) and are **never selectable**, so
the slide generator falls back to reusing whole slides from other decks
("templates"). This defeats component-first generation.

**Goal:** every published component carries standardized, canonical semantic
metadata sufficient for the scorer to select it on merit. Enforce at
publish/stage time with an executable gate; backfill existing items to the same
bar.

**Users:** (a) the slide-generator agent, which must be able to compose from
components; (b) `/component-extractor` authors, who need clear metadata
requirements; (c) future maintainers, who need the rule enforced by a script,
not prose (per `rules_must_be_executable`).

**Success looks like:** running the scorer `--item-type component` against a
representative brief yields component picks ≥65 for slides whose communication
intent a component genuinely serves — with zero hand-editing of the registry.

## Tech Stack

- Python 3 (repo `.venv`), stdlib + existing `_common.py` helpers.
- Data: `slide-system/registries/visual-library.json` (authority),
  `visual-library-compact.json` + `component-retrieval-index.jsonl` (generated).
- Gates: existing pattern in `quality_gate.py` / `validate_*.py` (exit 0/1).

## Commands

```bash
# Rebuild registry after metadata changes
.venv/bin/python3 slide-system/scripts/build_registry.py --write

# Proposed new gate (to be built — task #2)
.venv/bin/python3 slide-system/scripts/validate_component_metadata.py \
    --registry slide-system/registries/visual-library.json [--strict]

# Prove selectability (acceptance)
.venv/bin/python3 slide-system/scripts/score_visual_items.py \
    --batch-request <brief>/visual-requests.json --output <out> \
    --item-type component
```

## Project Structure

```
slide-system/scripts/          → gate + build scripts live here (not in runs)
slide-system/registries/       → visual-library.json (authority) + generated
slide-system/scripts/_reference/ → canonical vocab source (if added)
docs/specs/                    → this spec
```

## Required Metadata Schema (the bar)

Every item of type `component` / `component-set` MUST have, in
`visual-library.json`:

- **`intent`**: ≥3 terms, each from the **canonical communication vocab** (see
  below) or its known synonyms. Describes the communication job(s) the component
  does. No raw slide text, no OCR fragments.
- **`tags`**: ≥4 terms; descriptive + Vietnamese keywords allowed; free-form but
  must not be empty.
- **`content_structure`**: ≥2 terms; real slot roles verified against the
  component's `text-slots.json` (via `read_text_slots --slots-only`), using the
  generic slot vocab (`heading`, `subheading`, `label`, `body`, `list-item`,
  `title`, `metric`) plus optional structural descriptors
  (`repeatable-set-of-3`, `flow-node`, …).

**Canonical communication vocab** (must be the single source of truth; today it
is implicit in `score_visual_items.py::SYNONYMS`): cover, closing, timeline,
comparison, statistics, checklist, agenda, faq, divider, chart, quote, callout,
instructions, layout, overview, grid, process, steps, flow, numbered, ranking,
levels, tiers, roles, milestones. → OPEN QUESTION: extract this into a shared
`registries/canonical-vocab.json` both scorer and gate import, so they cannot
drift.

### Anti-gaming rule

Metadata must **honestly describe** the component. Terms are added because the
component genuinely serves that intent, not to clear the scorer. The gate checks
*presence + canonical membership + slot-truth*, not "does it match a specific
request." Reviewer spot-checks honesty.

## Testing Strategy

- Unit: `test_gates.py` — add cases: empty metadata → gate fail; OCR-noise intent
  → fail; valid canonical metadata → pass; content_structure term not in slot
  roles → fail (slot-truth check).
- Integration: score a fixture brief `--item-type component`; assert genuinely-fit
  slides get ≥65 and unfit slides (cover/closing when no such component) stay
  custom-local.
- Regression: `build_registry.py --check` stays green after backfill.

## Boundaries

- **Always:** edit semantic metadata only in `visual-library.json` then
  `build_registry.py --write`; keep gate executable (exit 0/1); verify slot roles
  against real `text-slots.json`.
- **Ask first:** deprecating/quarantining a published component; adding the
  `canonical-vocab.json` file; changing scorer weights or floors.
- **Never:** term-stuff metadata to game scores; hand-edit generated
  `visual-library-compact.json` / retrieval index; delete a failing gate to make
  a build pass.

## Success Criteria (specific, testable)

1. `validate_component_metadata.py` exists, exits 1 on any component missing the
   schema bar or carrying OCR-noise intent, exits 0 when all pass.
2. Gate is wired into the publish/stage path so a new extraction cannot publish a
   component with substandard metadata.
3. All existing `component`/`component-set` items pass the gate (backfilled or
   quarantined). Docling OCR-noise items are either re-authored or marked
   non-published.
4. Scorer `--item-type component` on the ai-workflow brief yields the same
   component picks (≥65) achieved by this session's hand patch — reproducibly,
   with no manual registry edits beyond schema-conformant metadata.
5. Canonical vocab has one source of truth imported by both scorer and gate.

## Open Questions

1. Extract canonical vocab to a shared file, or keep in scorer and have the gate
   import it? (Recommend shared file.)
2. For docling auto-staged components: auto-quarantine (status≠published) on
   OCR-noise detection, or require human re-authoring before publish?
3. Should `content_structure` slot-truth be a hard gate or a warning during
   rollout (mirroring `validate_component_fidelity.py --warn`)?
4. Does the same substandard-metadata problem affect the 76 templates, or only
   components? (Templates scored well here, but confirm the publish path.)
