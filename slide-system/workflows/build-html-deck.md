# Build HTML Deck

Build only after `validate_selection_report.py` exits 0.
Use `<project-python>` below: `.venv\Scripts\python.exe` on Windows and
`.venv/bin/python3` on macOS/Linux.

## Pre-Build Gate

Before starting HTML construction, confirm:
1. `analysis/selection-report.json` exists and was validated (step 7b).
2. For every slide with a `reuse` decision, the component's
   `visual.svg` and `text-slots.json` are accessible in the library path.
3. For every `reuse` slide, `analysis/slot-content-plan.json` maps only the
   compact display copy that fits its native slots. Read
   `slide-system/rules/component-content-fit.md`, then run:
   ```bash
   <project-python> slide-system/scripts/validate_slot_content_plan.py \
       --plan <run>/analysis/slot-content-plan.json \
       --selection-report <run>/analysis/selection-report.json \
       --out <run>/qa/slot-content-plan-report.json
   ```
   EXIT 0 required. Do not shrink fonts, move component geometry, or fill every
   slot to make a brief fit. Put detailed explanation in speaker notes or a
   subsequent slide.

   This also enforces repeatable-unit completeness: once the plan puts copy in
   one card/step/column of a repeated set, every drawn sibling in that set must
   carry copy too. Titles, footers, page numbers, and untouched repeat groups
   stay free to be left empty. A failure here means the component is the wrong
   size for the brief — re-select or go `text-only`, do not pad the deck with
   filler copy.

   It also enforces a readability budget inside those repeated units: one short
   label (1 display line) plus at most one compact support line, 3 display lines
   per unit total. Copy that fills every native line of a card fits physically
   and still projects as narrow ragged columns. Move the detail to
   `speaker_notes`. Long-form body slides, headlines, covers, and closings are
   outside any repeat group and are not budgeted.

## Post-Build Gate

Before capture, validate every local asset reference. Missing component
fragments render as blank white regions even when text slots and brand tokens
look valid:

```bash
<project-python> slide-system/scripts/validate_deck_assets.py \
    --html <run>/deck.html \
    --out <run>/qa/deck-assets-report.json
```

EXIT 0 required. Re-run the decomposer and use its emitted `snippet.html` / asset
paths; do not leave broken asset URLs in the deck.

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

Then run the component-fidelity gate (T3) — it confirms every `reuse`
slide actually uses its selected component's structure (class signature ≥ 70%, decomposed asset, or component
`background-image`), not just a `data-base-component` marker:
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

### Render legibility (post-capture, blocking)

Matching slot ids proves the deck *used* the component; it does not prove the
result can be read. `export_pptx.py` therefore runs a second pass on the
capture manifest as soon as the renders exist, before the PPTX is built:

```bash
<project-python> slide-system/scripts/validate_component_fidelity.py \
    --export-manifest <run>/export-manifest.json --renders <run>
```

It FAILS on browser-measured evidence, not estimates, and writes
`qa/render-legibility-report.json`:

- **`text_collision`** — two text boxes overlap by ≥ 15% of the smaller box
  (nested parent/child boxes are excluded). This is the signature of approved
  copy that wrapped past its fixed slot and landed on its neighbour. Fix it by
  shortening or scaling the copy **inside its own native slot** — never by
  moving or redrawing component geometry.
- **`text_over_artwork`** — a text item that is *not* a native component slot
  stands on the component's rendered artwork. This is the text-vs-artwork half
  of legibility: `text_collision` only compares text against text, so a caption
  dropped over a component's illustration used to pass everything. Measured
  against rendered overlay ink (the alpha of the overlay PNG), not its bounding
  box. Fix by moving the text to a region the component does not paint,
  shortening it into a native slot, or moving it to speaker notes — **never by
  raising `z-index`**, which hides the clash instead of resolving it. See the
  placement contract in `slide-system/rules/component-content-fit.md`.
- **`text_contrast`** — text sits on a flat rendered background at < 3.0:1.
  Usually means the artwork behind it never rendered (white copy left on warm
  paper), not that the palette is wrong.
- **`off_canvas_object`** — an overlay's bounds lie outside the slide canvas.
  The component has no viable placement; reject it as non-buildable and select
  another rather than claim fidelity.

The background is reconstructed from `ref_notext` when present, otherwise from
the base layer plus the overlay PNGs, so a headline over rendered artwork is
not mistaken for a headline over bare paper.

## Build Rules

- Use a `1920x1080` `<deck-stage>` **backed by the `deck_stage.js` runtime** —
  never a hand-rolled static `<div id="stage" style="width:1920px">`. Copy
  `slide-system/boilerplates/deck_stage.js` into the run as `deck_stage.js`,
  load it with a plain `<script src="deck_stage.js"></script>`, and author each slide as a
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
- **Declare every text item's placement** (contract in
  `slide-system/rules/component-content-fit.md`). A native component slot is
  self-declaring via `data-slot-id` (the T2 scaffold preserves it). Mark slide
  chrome `data-placement="chrome"` and any remaining free slide text
  `data-placement="external"`. Undeclared text is treated as external — the
  checked class — so nothing is exempted by omission.
  - Only native slots may sit on their component's artwork. Chrome and external
    text must clear it geometrically, and the post-capture gate measures that
    against rendered ink.
  - A component band is drawn to the component's own bounds: its artwork
    routinely reaches above/below the band's box into space that looks empty in
    the HTML. Give external captions a region the artwork does not reach, or
    put the copy in a native slot or speaker notes.
  - Keep component bands and overlays *below* valid slide chrome in z-order,
    and set explicit z-order only **after** the geometry is already valid.
    z-index resolves which of two overlapping things is visible; it never
    resolves a placement defect, and the overlap still ships in PPTX and PDF.
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
  - `off_canvas` = geometry the source crop threw away. It is dropped, not
    emitted. When `buildable` is `false` the decomposer exits **2**: every
    measured object fell outside the source `viewBox`, so the component cannot
    be rendered at all — pick another one instead of building empty overlays.
  - `snippet.html` positions are **percentages of the source canvas**, recorded
    in `coordinate_space`. A component cropped to its own `viewBox` (e.g.
    `1999x620`) is not in slide coordinates; pasting raw px would place the
    artwork at the wrong size and position on a `1920x1080` stage.
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

This path applies to ALL items with `reuse` decisions from
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
- Map the validated plan's content onto slots **by role/id**. Get the slot list with
  `read_text_slots.py --item <library-path> --slots-only` (a ~16 KB projection);
  never `Read` the full `text-slots.json` (up to ~120 KB). Slot semantics from
  `text-slots.schema.json`: every slot is `editable` and `allow_empty` (both
  `const true`) — there is no per-slot `required` flag. Text overflow is governed
  by `text_contract.overflow_policy` at the item level (typically `"unmanaged"`),
  NOT per slot. Map plan fields (title / subtitle / body / footer) to matching
  slot roles; leave unmatched slots empty rather than inventing content.
- For slides with a `text-only` decision, render only the approved title/body
  in a simple readable text layout. Do not invent visual treatment, create a
  local component, or trigger extraction. Preserve ranked candidates and the
  extraction recommendation for an explicit end-user decision later.
- If user content exceeds native capacity, shorten display copy and preserve
  the detail in speaker notes or split it into a following slide. This is a
  blocking pre-build failure, not an approval-package warning.
