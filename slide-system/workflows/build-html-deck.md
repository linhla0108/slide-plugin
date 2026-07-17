# Build HTML Deck

Build only after approval AND after `validate_selection_report.py` exits 0.
Use `<project-python>` below: `.venv\Scripts\python.exe` on Windows and
`.venv/bin/python3` on macOS/Linux.

## Pre-Build Gate

Before starting HTML construction, confirm:
1. `analysis/selection-report.json` exists and was validated (step 7b).
2. For every slide with a `reuse` decision, the component's `visual.svg` and
   `text-slots.json` are accessible in the library path. (`adapt-local` is retired;
   a `needs_component` slide builds nothing and goes back to the user for library
   review; `custom-local` only exists with explicit user approval.)

## Post-Build Gate

After HTML construction, before PPTX export, confirm the deck scales to the
viewport (uses the `deck_stage.js` runtime, not a hand-rolled fixed-`px`
stage). EXIT 0 required:
```bash
<project-python> slide-system/scripts/validate_deck_stage_runtime.py \
    --html <run>/deck.html
```
Fails when `<deck-stage>` is missing or its runtime is not loaded — either
case ships a deck locked at 1080p that never scales. Writes
`qa/deck-stage-report.json`.

Then validate brand rules:
```bash
<project-python> slide-system/scripts/validate_brand_compliance.py \
    --html <run>/deck.html \
    --selection-report <run>/analysis/selection-report.json \
    --brand-pack slide-system/brand-packs/sun-studio/manifest.json
```
EXIT 0 required. Fails on: emoji icons, non-brand fonts, excessive non-brand
colors, claimed reuse with no template reference in HTML.

Then run the component-fidelity gate (T3) — it confirms every `reuse` slide
actually uses its selected component's structure (slot coverage, decomposed asset,
or component `background-image`), not just a `data-base-component` marker, and
rejects any component recorded as `auto_reuse.eligible: false`:
```bash
<project-python> slide-system/scripts/validate_component_fidelity.py \
    --html <run>/deck.html \
    --selection-report <run>/analysis/selection-report.json \
    --registry slide-system/registries/visual-library.json \
    --warn
```
Run with `--warn` during rollout (reports failures, always exits 0) until
existing decks are rebuilt from scaffold; drop `--warn` to make it blocking.
Writes `qa/component-fidelity-report.json`.

**Contract fidelity is not render fitness.** The gate above proves a `reuse`
slide preserves its component's REFERENCE CONTRACT — slot coverage, bounds, no
overflow. It says nothing about whether the rendered result is fit for a human
audience. A component can pass fidelity (coverage 1.0) and still render unfit —
e.g. a wide-band artwork whose outer content falls off the 16:9 frame under
full-bleed `cover`, or slot text on too-light a background. The report's
`render_fitness_advisories` surface those cases (deterministically — see
`validate_component_fidelity.render_fitness`), but they are ADVISORY: a
component may only be **auto-reused** if it also passes render fitness, so a
component confirmed unfit is marked `auto_reuse.eligible: false` (blocked from
automatic selection, still browseable for manual placement). Fidelity gates the
contract; `auto_reuse.eligible` gates audience-readiness.

## Build Rules

- Use a `1920x1080` `<deck-stage>` **backed by the `deck_stage.js` runtime** —
  never a hand-rolled static `<div id="stage" style="width:1920px">`. Copy the
  starter via `copy_starter_component` (`kind: "deck_stage.js"`), load it with a
  plain `<script src="deck_stage.js"></script>`, and author each slide as a
  `<section>` child of `<deck-stage width="1920" height="1080">`.
  - **Why:** the runtime does letterboxed `transform: scale` so the deck fits
    any viewport when viewed/presented, and honours a `noscale` attribute that
    drops the transform for 1:1 authored-geometry capture. A raw fixed-`px`
    stage renders locked at 1080p (no viewport scaling) yet gains nothing for
    export — the worst of both. Export must pass
    `resetTransformSelector: "deck-stage"` (gen_pptx) / rely on capture setting
    `noscale`, so scaling never corrupts PPTX bounds.
  - `preview.html` and scaffold fragments stay fixed `1920px` on purpose (1:1
    slot geometry for editing/pasting) — this rule is about the shipped deck.
- Keep slide content as static, editable HTML.
- Keep each text item in a leaf element.
- **Colors**: Use ONLY CSS variables from the brand token set (`var(--sun-orange)`,
  `var(--ink)`, etc.). Never invent hex codes or use raw color values.
- **Fonts**: Use ONLY `"Proxima Nova"` with brand weights. Never use Georgia,
  Arial, Helvetica, or other non-brand fonts as primary.
- **Icons**: Use published shared SVG icons or slide-local simple SVGs. NEVER
  use emoji characters as icons.
- **Tag every visual object for export** (the layered PPTX export reads these;
  `validate_export_objects.py` FAILS the run when a visible `svg`/`img`/
  `canvas`/`video` carries no tag):
  - `data-export-layer="overlay"` + `data-export-id="<name>"` — each decor,
    chart, illustration, or image that must stay a separate movable object.
  - `data-export-group="<name>"` — gom nhiều element thành 1 overlay semantic.
  - `data-export-native="rect|ellipse"` + `data-export-id` — simple solid
    shapes (cards, bars, dividers) exported as real PPTX autoshapes.
  - `data-export-vector-source="<path.svg>"` — optional, path relative to the
    deck file; enables true-vector svgBlip when the element has no CSS effects.
  - `data-export-skip` — text that must stay baked in raster (gradient text…).
  - Passive full-slide canvas (gradient/texture on the slide root) needs no
    tag — it is the base layer by definition.
  - **One tag = one movable object.** Wrapping a full-page artwork SVG in a
    single overlay tag is NOT separation — every card/arrow/icon inside stays
    glued into one picture. The validator FAILS any overlay covering ≥ 85% of
    the canvas (`overlay_coverage.max_ratio` in
    `registries/export-qa-thresholds.json`).
- **Full-page artwork SVG (extraction `visual.svg`) MUST go through the
  decomposer — do not hand-split and do not embed it wholesale:**
  ```
  <project-python> slide-system/scripts/decompose_svg_objects.py \
      --svg <extraction-item>/artifact/visual.svg \
      --out-dir <job>/assets/page-NN --prefix page-NN \
      --href-base <path from deck.html to that out-dir>
  ```
  (The `artifact/` segment is the **extraction-batch** layout
  `outputs/component-extractions/<id>/items/<page>/artifact/` — it does NOT
  apply to published library items, which are flat. See the reuse section below.)
  It measures every source group in Chromium, clusters them into movable
  objects, writes per-object fragment SVGs + `snippet.html` (tagged,
  absolutely-positioned divs — paste inside the slide div) and
  `decompose-manifest.json`. Then:
  - `base_candidates` / WARN lines = full-bleed artwork → set it as the
    slide's CSS `background-image`, never as a tagged overlay.
  - Review object ids; rename to semantic names when it helps editing.
  - If two emitted objects are really one design piece, merge their divs
    (union bbox) — never the reverse (re-gluing many pieces into one tag).
- Use the approved brand pack and published visual-item versions.
- Reference shared assets in place; never copy them per run. Brand fonts,
  icons, and brand images load from the canonical brand-pack location.
- Use canonical, self-contained, resolvable font and asset paths; do not depend
  on removed prototype folders or external workspace paths.
- Keep one shared `<job-id>/assets/` folder for job-scoped assets not in a
  brand pack. Every run references that folder; runs never re-copy it.
- Copy an asset into a run only when it is unique to that single run.
- Separate raster assets into base background layers and complex overlay layers.
  Do not bake complex visual elements into the background image.
- Use background-only raster assets only for passive canvas treatments.
- Use independent transparent PNG overlays for complex export-risk elements,
  with recorded bounds, crop, scale, and z-order.
- Keep foreground content editable.
- Verify fonts, images, overflow, navigation, and deterministic capture.

## Component/Template-Based Build

This path applies to ALL items with a `reuse` decision from
the scorer — not only when `base_template` is set. A standalone component
(cover-hero, timeline, checklist, comparison, statistics, closing, CTA) with
a `reuse` decision follows the same decompose→fill-slots flow.

- Library items are **flat**: `<item-dir>/visual.svg`, `<item-dir>/text-slots.json`,
  `<item-dir>/preview/preview.html`. There is **no `artifact/` subdir** in the
  library. For templates: `slide-system/library/templates/<set>/<slide-id>/`;
  for standalone components: `slide-system/library/<type>/<item-id>/`. Take the
  path verbatim from `selection-report.json` / registry `paths` — do not glob.
- Scaffold the slide structure from the component's `preview.html` first (keeps
  the real `.bg` + `.slot` layout; you only fill text into slots):
  ```
  <project-python> slide-system/scripts/scaffold_slide_from_component.py \
      --item-id <id> --registry slide-system/registries/visual-library.json \
      --out <job>/assets/page-NN/fragment.html
  ```
- Run the item's `visual.svg` through the decomposer for the artwork (do not
  hand-split, do not embed wholesale; the script reads the SVG, you never do):
  ```
  <project-python> slide-system/scripts/decompose_svg_objects.py \
      --svg <library-path>/visual.svg \
      --out-dir <job>/assets/page-NN --prefix page-NN \
      --href-base <path from deck.html to that out-dir>
  ```
- Map the plan's content onto slots **by role/id**. Get the slot list with
  `read_text_slots.py --item <library-path> --slots-only` (a ~16 KB projection);
  never `Read` the full `text-slots.json` (up to ~120 KB). Slot semantics from
  `text-slots.schema.json`: every slot is `editable` and `allow_empty` (both
  `const true`) — there is no per-slot `required` flag. Text overflow is governed
  by `text_contract.overflow_policy` at the item level (typically `"unmanaged"`),
  NOT per slot. Map plan fields (title / subtitle / body / footer) to matching
  slot roles; leave unmatched slots empty rather than inventing content.
- **Every slot you fill must read as a complete unit.** A slot list is a set of
  disconnected regions on the artwork, not a sentence: the audience reads each
  region on its own, in whatever order the design leads their eye. So:
  - **Do not split one phrase across slots.** `foundation:"Nền tảng"` +
    `built:"riêng"` renders as two separate marks in two circles — the reader never
    reassembles "Nền tảng riêng". No slot metadata declares a continuation or group
    relationship (there is no `group` field, and `required` is `false` on every slot
    in the library), so there is nothing that licenses a phrase spanning two slots.
    Until a contract declares one, treat every slot as standing alone.
  - **Fewer, complete slots beat more, fragmented ones.** Slot coverage is not a
    score to maximise. A slot whose only purpose in the SOURCE was to continue a
    phrase (the second line of a stacked headline, a lone `&` between two partner
    names) has nothing to say on its own — leave it empty. `allow_empty` is `true`
    on every slot precisely so you can.
  - **Read the hierarchy off the contract before writing a word.** `role`,
    `html_tag`, `example_value` and `bounds` together say what each region is for:
    an `h1` at 26% of the slide height is the punchline, a `span` whose example is
    `"01"` is a rank, two slots stacked in the same column are one headline block in
    the source. Note the slot array is in the contract's own order, NOT reading
    order — sort by `bounds` yourself to see the real layout.
  - **If the component's geometry cannot carry your content coherently, do not force
    it.** Say so at the selection gate and pick another published component or leave
    the request `needs_component`. A slide that passes the overflow gate can still be
    unreadable — the gate proves text fits its box, never that it makes sense.
- For slides with `custom-local` or `blocked` decisions, fall back to the
  normal custom build above (with brand color/font/icon rules enforced).
- If user content exceeds the available slots or overflows the slot bounds,
  surface a warning in the approval package — overflow is unmanaged by design.
