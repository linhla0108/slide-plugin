# template-picker flow: library → picker → prompt → slide-generator

> Summary modeled on the actual structure of `slide-system/template-picker/`
> and the registry pipeline (updated 2026-06-16). Same style as `SKILL-FLOWS.md`.

The template-picker is a **static UI** (HTML/CSS/JS, no build step, no framework)
for non-technical users to pick **one complete slide-template** (full-bleed
1920×1080) from the published library, then copy a **plain-language prompt** to
hand off to `/slide-generator`. The picker does NOT generate slides — it only
selects and generates a prompt.

---

## 1. Data pipeline: from published item → picker-data.json

```
slide-system/registries/visual-library.json   (single source of truth)
        │   only items: status == "published" && type == "template"
        ▼
[A] build_template_picker_data.py
        │   • filter published + template (do NOT read catalog-data.json —
        │     avoids 14 sun-goal-* pages leaking into the user picker)
        │   • derive_deck(item): group slides by SOURCE DECK from source.path
        │       basename → deck_id (slug) + name; slides in the same deck = 1 set
        │   • derive_thumbnail(): prefer <preview-dir>/thumbnail.png
        │   • derive_use_case(): bucket by intent/tags
        │       (Cover/Section/Data/Content/Closing/Other)
        │   • path → CONVERT to relative to the picker directory (../library/...)
        │   • sort slides within a deck by slide_number;
        │     sort decks by slide_count descending then alphabetically
        ▼
slide-system/template-picker/picker-data.json   (GENERATED — do not edit by hand)
        │   { decks: [ { deck_id, name, source, slide_count,
        │               slides: [ {id, name, intent, tags,
        │                          content_structure, slide_number,
        │                          preview, thumbnail, use_case} ] } ],
        │     templates: [...] }
        ▼
[B] index.html + picker.js + picker.css   (fetch picker-data.json on load)
        │   • load ./picker-data.json; FAIL → fallback ./picker-data.sample.json
        │     (checked-in fixture) so the UI renders before anything is published
        │   • source-pill: "Live library" / "Sample data" / "Load error"
        │   • decksOf() accepts BOTH the deck-grouped shape AND a flat `templates`
        │     list (wrapped into a single "Full-slide templates" deck)
```

**Key point:** set grouping is **registry-driven via `source.path`**, NOT dependent
on the layout folder. Renaming/moving a template folder does not break grouping —
only the path string changes. (So the restructure that grouped folders by set did
not touch the picker logic.)

---

## 2. Lifecycle of one template on disk (after publishing)

`/component-extractor` publishes an item with `type=template` and id `sun.<set>.<slide>` →
`publish_extraction.py` places it in a layout **grouped by set**:

```
slide-system/library/templates/
  <set-slug>/                          e.g. interview-workshop-sunriser/
    <slide-slug>/                      e.g. 01-cover/   (id: sun.interview-workshop-sunriser.01-cover)
      visual.svg              ← editable background, NO <text>; new content is poured on top
      text-slots.json         ← editable text contract (normalized bounds + typography)
      preview/
        thumbnail.png         ← PICKER IMAGE: rendered from the original PDF (with text), 1920×1080
        preview.html          ← editable composite: visual.svg + positioned slots;
                                  this is the layer /slide-generator uses to build the slide
      evidence/
        source-with-text.svg  ← original full slide (evidence, with text baked in)
        notes.md              ← extraction notes
```

| File | Has text? | Role | Used by picker? |
|---|---|---|---|
| `visual.svg` | no (intentional) | editable background to overlay new content | indirectly (preview.html) |
| `text-slots.json` | — | position + typography contract for text | no |
| `preview/thumbnail.png` | yes | image shown in the picker (original PDF raster) | **YES** |
| `preview/preview.html` | yes (sample) | editable composite for the build step | no |
| `evidence/source-with-text.svg` | yes | original kept as reference evidence | no |
| `evidence/notes.md` | — | extraction notes | no |

**Why the picker uses `thumbnail.png` instead of rendering `source-with-text.svg`:**
rendering the evidence SVG easily **doubles the text** (vector text overlaid on a
raster that already has text), so the picker takes the original PDF raster directly
for a clean result.

**`thumbnail.png` is REQUIRED.** The picker (`thumbSrc`) prefers `thumbnail`, falling
back to `preview` — but for templates `preview` = `preview/preview.html`, which can't
be used as an `<img src>` → if the thumbnail is missing the cell shows a "No preview"
placeholder.

**`reference.png` is staging-only:** `convert_pdf_source.py` generates it as a raster
for QA render-parity (`page.get_pixmap`), pixel-identical to `thumbnail.png`.
`publish_extraction.py` **excludes it from the published folder** (kept only in
`outputs/component-extractions/...` for QA). It is not carried into the library.

---

## 3. Picker UX: two tiers + slide-viewer modal

```
[1] Sets list   (first screen)
        │   each set = one deck card (deck name, representative thumbnail, slide count)
        │   does NOT show "slot count" anywhere
        ▼  click card → smooth scroll (respects prefers-reduced-motion)
[2] Deck slide grid   (openDeck)
        │   grid of slides in the deck; each cell = thumbnail + name + button
        │   back-bar "All template sets" + jump-nav (set switcher) in the hero —
        │     jump-nav ONLY shows when ≥2 decks (with 1 deck it is now hidden)
        ▼  click slide → openModal(deck, index)
[3] Slide-viewer modal
        │   • top bar: close · deck name · "N / M" counter · whole-set button
        │   • vertical filmstrip (numbered thumbs, orange active ring, auto scroll-into-view)
        │   • center stage: container-query fit width:min(100cqw,100cqh*16/9) + gutter
        │   • nav: SVG left/right chevron (no glyph), single-step,
        │     disabled at the start/end of the deck
        │   • info bar: kicker(use_case bucket, fallback "Slide N") / name /
        │     intent+tags chips / id
        │   • footer: key hints (ONLY shows ← → / Home·End / Esc — a subset of
        │     the keys that actually work)
        │
        │   main JS: openModal · goTo · renderFilmstrip · next · prev · trapFocus
        ▼
[4] Copy prompt  (3 buttons, all labeled "Copy prompt")
        │   • slidePrompt(card)      → single-slide prompt (name + id)   [info bar]
        │   • deckPrompt(deck, ids)  → whole-set prompt (deck name + ids) [top bar + detail head]
        │   prompt = English, plain language, WITH ids so the generator can look them up
        │   clipboard: navigator.clipboard → fallback execCommand
        │   → confirmation toast (stack of max 3, hover-pause, auto-dismiss ~4.2s)
        ▼
   user pastes the prompt into /slide-generator → selects a published item → build
```

**Shortcuts:** `←/→` `↑/↓` `PageUp/PageDown` `Home/End` (navigation) ·
`Esc` (close) · `Tab` (trap focus inside the modal).
`C`/`S` have been **removed** (clashed with system keys) — selecting an item is now
done via on-screen buttons.
The footer advertises only a subset (`← →`, `Home/End`, `Esc`).

---

## 4. Regenerate & validate (run after every registry change)

```
# from slide-system/
python3 scripts/build_template_picker_data.py    # → template-picker/picker-data.json
python3 scripts/build_component_catalog.py        # → catalog/catalog-data.json
python3 scripts/validate_registry.py              # gate: id pattern + path exists

# preview (macOS has no `timeout`):
python3 -m http.server 8777    # from repo root
# open http://localhost:8777/slide-system/template-picker/index.html
```

---

## 5. Hard rules

- `picker-data.json` and `catalog-data.json` are **GENERATED** — always regenerate
  with the script, do NOT edit by hand.
- The picker only reads `visual-library.json`, only items with `status==published` &
  `type==template`. Staging/deprecated items never get in.
- "Template" = **one complete slide** 1920×1080, not a section/card/icon.
- The preview image must be the **full original slide** (PDF raster), not a rebuild
  that could drift from the source → use `thumbnail.png`, do not render
  `source-with-text.svg`.
- Group sets by `source.path` (registry-driven), independent of the layout folder.
- Id mirrors layout: `sun.<set-slug>.<slide-slug>` ↔ `templates/<set>/<slide>/`.
- Copy the prompt in **English**, with id; the embedded slide name may be Vietnamese (data).
- All animations respect `prefers-reduced-motion` (modal close uses `is-closing`
  + `animationend`/240ms fallback; reduced-motion skips it).
- No "slot count" anywhere in the UI.

---

## 6. Relationship to the 2 source skills

```
/component-extractor ──publish──▶ library/templates/<set>/<slide>/
        (staging → approve)              │
                                         ▼  build_template_picker_data.py
                                  template-picker/picker-data.json
                                         │
                                         ▼  static UI, Copy prompt
                                  prompt (id + plain language)
                                         │
                                         ▼  user pastes
                                  /slide-generator (only selects published)
```

The picker sits **between** the published library and `/slide-generator`: it does not
extract and does not build slides — it is only a *discovery + prompt-generation* layer
so non-technical users can pick the right complete template and hand it off to the
generator.
