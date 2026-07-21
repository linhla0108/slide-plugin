# Component Content Fit

A published component is a visual grammar with finite native text capacity. It
is not a blank container for every sentence in a brief.

## Required run-local plan

For every selected `reuse` slide, create
`analysis/slot-content-plan.json` before writing `deck.html`. The plan is
job-local: it never mutates the shared library, registry, retrieval index, or
selection report.

```json
{
  "schema_version": 1,
  "slides": [
    {
      "request_id": "slide-03",
      "item_id": "sun.component.example",
      "slots": [
        {
          "slot_id": "headline",
          "display_copy": "Three short words",
          "speaker_notes": "The full supporting explanation stays editable in notes."
        }
      ]
    }
  ]
}
```

Only list slots that will carry generated copy. Empty native slots stay empty.
Do not add slots, change their geometry, or reduce their typography to make
copy fit.

## Copy hierarchy

- Keep the slide-level message in one headline.
- A card, node, or badge gets **one short label and at most one compact
  supporting line** — never a paragraph, and never one word per native line.
  Extraction splits a card's original wrapped paragraph into one slot per drawn
  line, so a card offering five slots is still a one-label surface, not a
  five-line surface.
- Preserve detailed evidence in speaker notes or the following slide rather
  than turning cards into paragraphs.
- Map three parallel ideas to a component that repeats exactly three native
  units. Do not select a five-unit component and leave two blank, and do not
  invent a fourth idea to fill a unit the brief does not have.
- **An explanation of a parallel item belongs in that item's native slot or in
  speaker notes — never in an ad-hoc caption placed near the component.** When
  the label slot is too small for the explanation, that is the answer, not a
  problem to route around: the detail goes to `speaker_notes`. Writing it as a
  free `<p>` positioned above/below/beside the artwork is the failure mode the
  placement contract below rejects, because the component's artwork is drawn to
  its own bounds and will reach into whatever space looks empty in the HTML.

## Placement contract

Every generated text item on a slide is exactly one of:

| Class | How it is declared | Artwork rule |
| --- | --- | --- |
| Native component slot | `data-slot-id` on the element or an ancestor | exempt from its own component's artwork — the component drew that box for that copy |
| Slide chrome | `data-placement="chrome"` (title, kicker, footer) | must clear the artwork |
| External text | `data-placement="external"`, and the default for anything undeclared | must clear the artwork |

Only a native slot is exempt. Chrome and external text must sit in a region the
component does not paint; declaring an item `external` records the intent, it
does not grant permission. Undeclared text is treated as external on purpose,
so a missing attribute can never buy an exemption.

`validate_component_fidelity.py --export-manifest` enforces this after capture
as `text_over_artwork`, measured against the *rendered* overlay ink rather than
its bounding box (a circle set fills about 78% of its own box, and its top edge
is a thin arc). A failure names the slide, the text, the overlay and the
measured share. Fix it by one of:

1. move the text to a genuine safe region the artwork does not reach;
2. shorten it into a native slot of the component; or
3. move it to `speaker_notes`.

Raising the text's `z-index` is not a fix. It picks a winner between two things
in the same place; it does not give the text a place of its own, and the copy
still lands on artwork in the PPTX and PDF. Set explicit z-order only once the
geometry is already valid.

## Repeatable visual units

A component draws its cards, steps, columns, and tiers whether or not copy
lands in them, so a plan can pass every per-slot check and still ship a
visibly unfinished slide. Two gates enforce completeness, both reading the
component's own normalized bounds and typography — no item ids, page ids, or
component names are involved.

- **Selection (`score_visual_items.py`)** — when a request declares `item_count`
  of 2 or more, a candidate whose primary repeat count differs stays ranked and
  carries an explicit `Visual-unit fit` reason, but is not buildable. Selection
  falls through to the next compatible published component, or emits `text-only`
  with the normal extraction evidence when none exists. A component with no
  repeat structure (cover, quote, closing) declares no unit count; unknown is
  not a mismatch. `validate_selection_report.py` re-checks the same rule as
  `visual_unit_lock` — defense in depth, not the fallback implementation.
- **Layout grammar (`score_visual_items.py`)** — a component built around a
  display/quote panel beside a much denser working surface hosts one statement,
  not N parallel items. When a request wants 2 or more parallel items and such a
  component offers no matching repeat group, it takes a bounded score penalty so
  a better-matched published candidate can win. It stays eligible on purpose:
  when nothing better is published the selection stands and the decision carries
  a warning. A cover or quote request never triggers this.
- **Plan (`validate_slot_content_plan.py`)** — once a repeated unit group is
  engaged, every drawn sibling in it must carry copy, and no engaged unit may
  exceed its readability budget (below). Repeat groups the plan never touches
  are untouched by design and are not flagged.

Units are inferred geometrically: page chrome (top/bottom margin bands) is
dropped, remaining slots are clustered into drawn units by spatial adjacency,
and units with congruent anchor typography form a repeat group. A slide title,
kicker, footer, page number, or decorative label has no congruent sibling, so
it forms no group and stays free to be left empty.

## Capacity and readability

Run before HTML construction:

```bash
<project-python> slide-system/scripts/validate_slot_content_plan.py \
  --plan <run>/analysis/slot-content-plan.json \
  --selection-report <run>/analysis/selection-report.json \
  --out <run>/qa/slot-content-plan-report.json
```

The validator derives capacity from the selected component's own normalized
bounds and typography. It fails when a mapped slot is unknown, repeated,
missing for a reuse slide, below its projection readability floor, or contains
more copy than its native line capacity.

Projection floors are intentionally role-based rather than component-specific:

| Slot role | Minimum native size |
| --- | --- |
| heading/title | 36 px |
| body/list-item | 18 px |
| label/footer | 16 px |

### Readability budget inside repeated units

Physical capacity is the wrong ceiling for a repeated card, step, column, or
strip cell. A card is scanned in about a second from the back of a room, so
copy that fills every native line technically fits and still projects as a set
of narrow ragged columns. Inside an engaged repeat group only, the plan gate
applies a stricter budget in wrapped *display lines*:

| Unit copy | Budget | Note |
| --- | --- | --- |
| Label (slots in the unit's anchor type) | 1 line | only where the unit has a distinct support tier |
| Whole unit (label + support) | 3 lines | total per drawn unit |

Author to one label plus one compact support line; the extra line of headroom
exists so a support line that wraps by a word is not rejected. Detail that does
not fit goes to `speaker_notes`, not into more card slots. Nothing outside a
repeat group is budgeted: long-form body slides, global headlines, covers,
quotes, closings, and speaker notes are unaffected, as are component geometry
and the role-based font floors above.

The browser render-legibility gate remains mandatory after capture. It catches
actual collision, contrast, artwork-placement, and off-canvas failures that a
pre-build estimate cannot observe: the plan gate validates native slots only,
so text the plan never mentions is governed by the placement contract instead.
