# Build HTML Deck

Build only after approval AND after `validate_selection_report.py` exits 0.

## Pre-Build Gate

Before starting HTML construction, confirm:
1. `analysis/selection-report.json` exists and was validated (step 7b).
2. For every slide with a `reuse` or `adapt-local` decision, the component's
   `visual.svg` and `text-slots.json` are accessible in the library path.

## Post-Build Gate

After HTML construction, before PPTX export:
```bash
.venv/bin/python3 slide-system/scripts/validate_brand_compliance.py \
    --html <run>/deck.html \
    --selection-report <run>/analysis/selection-report.json \
    --brand-pack slide-system/brand-packs/sun-studio/manifest.json
```
EXIT 0 required. Fails on: emoji icons, non-brand fonts, excessive non-brand
colors, claimed reuse with no template reference in HTML.

Then run the component-fidelity gate (T3) — it confirms every `reuse` /
`adapt-local` slide actually uses its selected component's structure (class
signature ≥ 70% reuse / ≥ 45% adapt, decomposed asset, or component
`background-image`), not just a `data-base-component` marker:
```bash
.venv/bin/python3 slide-system/scripts/validate_component_fidelity.py \
    --html <run>/deck.html \
    --selection-report <run>/analysis/selection-report.json \
    --registry slide-system/registries/visual-library.json \
    --warn
```
Run with `--warn` during rollout (reports failures, always exits 0) until
existing decks are rebuilt from scaffold; drop `--warn` to make it blocking.
Writes `qa/component-fidelity-report.json`.

## Build Rules

- Use a `1920x1080` `<deck-stage>`.
- Keep slide content as static, editable HTML.
- Keep each text item in a leaf element.
- **Colors**: Use ONLY CSS variables from the brand token set (`var(--sun-orange)`,
  `var(--ink)`, etc.). Never invent hex codes or use raw color values.
- **Fonts**: Use ONLY `"Proxima Nova"` with brand weights. Never use Georgia,
  Arial, Helvetica, or other non-brand fonts as primary.
- **Icons**: Use SVG icons from the brand icon library
  (`sun.asset.guideline-icon-library`) or slide-local simple SVGs. NEVER use
  emoji characters as icons.
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
  .venv/bin/python3 slide-system/scripts/decompose_svg_objects.py \
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

This path applies to ALL items with `reuse` or `adapt-local` decisions from
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
  .venv/bin/python3 slide-system/scripts/scaffold_slide_from_component.py \
      --item-id <id> --registry slide-system/registries/visual-library.json \
      --out <job>/assets/page-NN/fragment.html
  ```
- Run the item's `visual.svg` through the decomposer for the artwork (do not
  hand-split, do not embed wholesale; the script reads the SVG, you never do):
  ```
  .venv/bin/python3 slide-system/scripts/decompose_svg_objects.py \
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
- For slides with `custom-local` or `blocked` decisions, fall back to the
  normal custom build above (with brand color/font/icon rules enforced).
- If user content exceeds the available slots or overflows the slot bounds,
  surface a warning in the approval package — overflow is unmanaged by design.
