# Component Composition Guide

Rules for placing standalone published items (assets, characters, styles) on
slides. Templates are self-contained and do not need this guide.

## Standalone Items

### sun.asset.logo

- **Where:** cover slide and closing slide only.
- **Placement:** top-left corner or horizontally centered, depending on the
  template's header area. Never place in the main content zone.
- **Size:** 120–180 px width. Never stretch or distort the aspect ratio.
- **Layer:** above background, below content text.

### sun.character.dio

- **Where:** section dividers, emphasis callouts, light-hearted slides. Avoid
  on data-heavy, formal, or dense-content slides.
- **Placement:** bottom-right or bottom-left corner, partially overlapping the
  slide edge. Keep clear of body text and data visuals.
- **Size:** 80–140 px height. Scale proportionally.
- **Variant selection:**

| Variant | Mood / Context |
|---------|----------------|
| normal | Neutral, default, introductions |
| side-glance | Curiosity, "check this out" |
| wink | Confidence, tips, insider info |
| annoyed | Problems, pain points, blockers |
| dancing | Celebration, wins, milestones |
| bored | Tedious topics acknowledged with humor |
| bewildered | Surprise, unexpected data, plot twists |
| variant | Alternative neutral pose |

### sun.style.guideline-shape-variants

- **Where:** level indicators, formula diagrams, branded shape accents,
  section backgrounds.
- **Placement:** behind or beside content. Never cover body text or data.
- **Variant selection:**

| Variant | Use case |
|---------|----------|
| halo-blue | Primary emphasis, key metrics, highlights |
| halo-orange | Secondary emphasis, warnings, energy |
| halo-lime | Tertiary emphasis, growth, success |
| hex-formula | Process steps, formulas, methodologies |
| overlap-circles | Relationships, intersections, Venn-style concepts |

- **Limitations:** layered halo and blended gradient treatments may require
  raster fallback in PPTX/Canva. Editable labels must stay outside raster
  layers.

## Layer Order

When composing a slide from multiple published items, stack in this order
(back to front):

1. **Background** — solid color, gradient, or background PNG from template.
2. **Style shapes** — `sun.style.guideline-shape-variants` accents.
3. **Content** — text, tables, charts, data visuals.
4. **Assets** — `sun.asset.logo` and other brand marks.
5. **Characters** — `sun.character.dio` on top of everything.

## Set Consistency

When a deck uses a `base_template` from a template set (e.g.,
`sun.interview-workshop-sunriser.*`), prefer other templates from the same
set for all matching slides. Template set membership is determined by the
second segment of the item ID: `item_id.split(".")[1]`.

Pass `--prefer-set <set-prefix>` to `score_visual_items.py` to apply a
scoring bonus for same-set items.
