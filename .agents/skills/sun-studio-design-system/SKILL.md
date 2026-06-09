---
name: sun-studio-design-system
description: Apply the canonical SUN.STUDIO brand and slide design system to presentations, prototypes, interfaces, and visual assets. Use when work must follow SUN.STUDIO colors, Proxima Nova typography, logo/DIO rules, XO or editorial slide language, reusable deck components, or company brand voice.
---

# SUN.STUDIO Design System

Use this skill as the binding visual system for SUN.STUDIO work. Do not invent
colors, typography, logo treatments, mascot treatments, or slide patterns when
the system already defines them.

## Start Here

1. Read `references/brand-guide.md` for brand voice, visual foundations, logo,
   DIO, color, typography, layout, and motion rules.
2. Import or copy
   `assets/system/colors_and_type.css` and `assets/system/fonts/` into the
   artifact. This stylesheet is the canonical token source.
3. Inspect relevant reusable files before designing:
   - `assets/system/components/`: 12 topic-agnostic deck components
   - `assets/system/preview/`: 38 focused design-system specimens
   - `assets/system/slides/`: 12-slide XO-pattern reference deck
   - `assets/system/slides-v2/`: editorial/tactile reference slides
   - `assets/system/assets/`: master logo and DIO pose library
4. For editorial/tactile slides, also read
   `references/editorial-slide-guidelines.md`.
5. For full deck categories, read only the relevant file under
   `references/deck-prompts/`.

## Source Precedence

When sources disagree, follow this order:

1. Official Brandbook rules summarized in `references/brand-guide.md`
2. Exact tokens in `assets/system/colors_and_type.css`
3. Reusable components in `assets/system/components/`
4. Reference slides in `assets/system/slides/`
5. Editorial extension in `assets/system/slides-v2/`
6. Project-specific extracted components in the consuming repository

The Brandbook overrides patterns inferred from one-off legacy decks.

## Core Rules

- Primary orange is `#FF5533`; accent blue is `#3333FF`.
- Use Proxima Nova for digital surfaces.
- Never alter the master logo. Preserve its proportions and 2x letter-O clear
  space.
- DIO is the only default character imagery. Use the supplied poses.
- Headlines and badges use uppercase; body copy uses sentence case.
- Keep highlights rare: normally 1-3 emphasized words or blocks per slide.
- Green and red are semantic colors for explicit success/error or Do/Don't
  communication, not general decoration.
- Default slide canvas is `1920x1080`.
- Keep supplied content unchanged unless the user approves copy edits. Record
  wording suggestions separately.
- Use one strong visual anchor per slide.
- Prefer existing components and reference patterns over creating new visual
  grammar.

## Choosing A Slide Language

- **XO/poster language:** use `assets/system/slides/` for training, workshops,
  all-hands, frameworks, and energetic internal communication.
- **Editorial/tactile language:** use `assets/system/slides-v2/` for onboarding,
  policy, narrative, or more human and asymmetric communication.
- Do not mix both languages casually within one deck. Choose a dominant system
  and use contrast slides deliberately.

## Reusable Components

The canonical component set under `assets/system/components/` includes:

- chevron flow
- swimlane
- phase timeline
- ratio split and donut
- acronym framework
- numbered Q&A
- value/benefit grid
- numbered agenda
- section divider
- formula block
- competency columns
- folio/footer chrome

Each component imports `_base.css`, which imports the canonical token file.
Use the `--cs` custom property to scale components uniformly.

Project-specific reusable visuals must be registered through the shared visual
library and must not override canonical brand tokens.

## Asset Handling

For a new artifact, copy only the resources it uses while preserving relative
paths. At minimum:

```text
colors_and_type.css
fonts/
assets/logo.png or assets/dio/<pose>.png
components/<component>.css and components/_base.css
```

Do not depend on the original Claude Design project path. This skill is
self-contained under `assets/system/`.

## Verification

Before delivery:

- Confirm all local font, image, stylesheet, and script paths resolve.
- Confirm no non-canonical brand color slipped into the artifact.
- Check the slide at authored size and scaled preview size.
- Check text contrast, overflow, logo clear space, and DIO/copy overlap.
- Confirm page numbers and folio treatments are not duplicated.
- When exporting to PPTX or Canva, state any unsupported CSS or editability
  limitations.
