---
name: sun-studio-design-system
description: Apply the canonical SUN.STUDIO brand and slide design system to presentations, prototypes, interfaces, and visual assets. Use when work must follow SUN.STUDIO colors, Proxima Nova typography, logo/DIO rules, XO or editorial slide language, reusable layout patterns, or company brand voice.
---

# SUN.STUDIO Design System

Use this skill as the binding visual system for SUN.STUDIO work. Do not invent
colors, typography, logo treatments, mascot treatments, or slide patterns when
the system already defines them.

## Start Here

1. Import or copy
   `assets/system/colors_and_type.css` and `assets/system/fonts/` into the
   artifact. This stylesheet is the canonical token source.
2. Use `assets/system/assets/logo.png` for the master logo and
   `assets/system/assets/dio/` for DIO poses.

## Source Precedence

When sources disagree, follow this order:

1. Rules in this skill
2. Exact tokens in `assets/system/colors_and_type.css`
3. Project-specific extracted components in the consuming repository

The rules in this skill override patterns inferred from one-off source decks.

## Core Rules

- Primary orange is `#FF5533`; accent blue is `#3333FF`.
- Use Proxima Nova for digital surfaces.
- Never alter the master logo. Preserve its proportions and 2x letter-O clear
  space.
- DIO is the only default character imagery. Use the supplied poses.
- Brand voice is sincere, competent, concise, warm, and action-oriented.
- Internal Vietnamese communication may use "chúng ta" / "bạn" and English
  keywords when they are canonical terms.
- Headlines, badges, and kickers use uppercase; body copy uses sentence case.
- Keep highlights rare: normally 1-3 emphasized words or blocks per slide.
- Green and red are semantic colors for explicit success/error or Do/Don't
  communication, not general decoration.
- Default slide canvas is `1920x1080`.
- Keep supplied content unchanged unless the user approves copy edits. Record
  wording suggestions separately.
- Use one strong visual anchor per slide.
- Prefer canonical tokens, logo, DIO, and layout rules over inventing new visual
  grammar.

## Choosing A Slide Language

- **XO/poster language:** use for training, workshops, all-hands, frameworks,
  metrics, and energetic internal communication. Visual cues: warm paper, XO
  pattern wash, orange/blue numbered circles, strong h1 tabs, cards, arrows,
  and a clear bottom action capsule.
- **Editorial/tactile language:** use for onboarding, policy, narrative, or
  more human and asymmetric communication. Visual cues: one anchor per slide,
  deliberate asymmetry, large display type, hairlines, paper texture, italic
  serif as a secondary voice, and restrained tactile details.
- Do not mix both languages casually within one deck. Choose a dominant system
  and use contrast slides deliberately.

## Reusable Layout Patterns

The reusable CSS component files have been removed from this skill. Keep these
as layout vocabulary and rebuild them in-place when a deck needs them:

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

Project-specific reusable visuals must be registered through the shared visual
library and must not override canonical brand tokens.

## Asset Handling

For a new artifact, copy only the resources it uses while preserving relative
paths. At minimum:

```text
colors_and_type.css
fonts/
assets/logo.png or assets/dio/<pose>.png
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
