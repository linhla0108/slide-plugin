# Flow walkthrough: Component Selection & Composition

> The flow for selecting a visual item from the library and composing standalone components onto a slide.
> Based on `rules/component-composition.md`, `scripts/score_visual_items.py`,
> and the `select-visual-items.md`, `plan-slide-deck.md` workflows (updated 2026-06-17).

---

## Overview

When the agent builds a slide deck, it needs to:

1. **Select a template** for each slide from the visual library (scoring).
2. **Compose standalone items** (logo, dio, shapes) onto the slide at the right positions (composition).
3. **Keep the visuals consistent** within the same deck (set preference).

```
User request
    │
    ▼
┌─────────────────────────────────────┐
│  INTAKE & TRIAGE                    │
│  → determine base_template (if any) │
│  → record set prefix               │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  PLAN SLIDE DECK                    │
│  → list out slides + intent        │
│  → note set prefix for scoring     │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  SELECT VISUAL ITEMS                │
│  → score each slide need            │
│  → apply --prefer-set if present   │
│  → decide reuse / adapt / custom    │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  BUILD HTML DECK                    │
│  → read component-composition.md   │
│  → compose standalone items by layer│
└─────────────────────────────────────┘
```

---

## 1. Determine the template set (Intake → Plan)

When the user picks a template from the picker (for example `sun.interview-workshop-sunriser.01-cover`),
the agent extracts the set prefix from the ID:

```
sun.interview-workshop-sunriser.01-cover
 │          │                        │
 │          │                        └── slide slug
 │          └── set prefix = "interview-workshop-sunriser"
 └── brand prefix
```

**How to derive:** `item_id.split(".")[1]` → `"interview-workshop-sunriser"`

The set prefix is recorded in the brief and passed down to the scoring step.

---

## 2. Scoring visual items (in detail)

```
                    ┌──────────────────────────┐
                    │  visual-request.json      │
                    │  (intent, tags, density,  │
                    │   brand, required_exports) │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │  score_visual_items.py    │
                    │  --request <file>         │
                    │  --item-type template     │
                    │  --prefer-set <prefix>    │ ← new
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
     ┌─────────────┐   ┌──────────────┐    ┌──────────────┐
     │ Candidate A  │   │ Candidate B  │    │ Candidate C  │
     │ same set     │   │ same set     │    │ diff. set    │
     └──────┬──────┘   └──────┬───────┘    └──────┬───────┘
            │                  │                    │
            ▼                  ▼                    ▼
     ┌─────────────┐   ┌──────────────┐    ┌──────────────┐
     │ Base score   │   │ Base score   │    │ Base score   │
     │    77.5      │   │    70.0      │    │    73.75     │
     │  + SET +5    │   │  + SET +5    │    │  (no bonus)  │
     │  ─────────   │   │  ─────────   │    │  ─────────   │
     │  = 82.5  ✓   │   │  = 75.0  ✓   │    │  = 73.75     │
     │   REUSE      │   │   REUSE      │    │   ADAPT      │
     └─────────────┘   └──────────────┘    └──────────────┘
```

### Scoring criteria (weights unchanged)

| Criterion | Weight (component) | Weight (template) |
|---|---|---|
| semantic_intent | 35 | 35 |
| content_structure | 20 | **25** |
| density | 10 | **5** |
| brand | 10 | 10 |
| export_compatibility | 15 | 15 |
| accessibility | 10 | 10 |

### Set preference bonus

```
IF --prefer-set is passed
   AND item eligible (published + export OK)
   AND score > 0
   AND item_id.split(".")[1] == prefer_set
THEN
   score = min(100, score + 5)
```

- Bonus = **+5 points** (fixed, does not change the weights).
- Does not affect items from another set or items without the flag.
- When `--prefer-set` is not passed, the scorer behaves exactly as before.

### Decision thresholds

| Score | Decision | Meaning |
|---|---|---|
| ≥ 75 | **reuse** | Use the published item as-is |
| 65–74 | **adapt-local** | Use it but adjust locally for the slide |
| < 65 | **custom-local** | Build a new one for this slide |
| 0 (no eligible item) | **blocked** | No suitable item available |

---

## 3. Composition — compose standalone items onto the slide

After selecting a template, the agent reads `rules/component-composition.md` to know
where to place the standalone items.

### Layer order (back → front)

```
┌──────────────────────────────────────────────┐
│                                              │
│  ⑤ Character (dio)           ┌──────┐       │
│                               │ dio  │       │
│  ④ Assets (logo)              │ 🌻  │       │
│     ┌─────────┐              └──────┘       │
│     │  LOGO   │                              │
│     └─────────┘                              │
│                                              │
│  ③ Content (text, charts, tables)            │
│     ┌────────────────────────────────┐       │
│     │  Heading text here             │       │
│     │  • Bullet point 1             │       │
│     │  • Bullet point 2             │       │
│     └────────────────────────────────┘       │
│                                              │
│  ② Style shapes (halo, hex, circles)         │
│     ░░░░░░░░░░░░░░░░░░                      │
│     ░░ halo-orange  ░░                       │
│     ░░░░░░░░░░░░░░░░░░                      │
│                                              │
│  ① Background (solid / gradient / PNG)       │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
└──────────────────────────────────────────────┘
```

### Deciding where to place each item

```
                ┌─────────────────────┐
                │ Which components    │
                │ besides the template?│
                └─────────┬───────────┘
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
     Cover/Closing?    Divider?      Data/Formal?
           │           Callout?           │
           │              │               │
           ▼              ▼               ▼
     ┌──────────┐  ┌───────────┐   ┌───────────┐
     │ ✅ Logo  │  │ ✅ Dio    │   │ ❌ Dio    │
     │ top-left │  │ corner    │   │ (too heavy)│
     │ 120-180px│  │ 80-140px  │   │           │
     └──────────┘  └───────────┘   └───────────┘
           │              │
           ▼              ▼
     Pick variant?   Pick variant?
           │              │
           │         ┌────┴────────────────────────┐
           │         │ Check the slide mood/context:│
           │         │ celebration → dancing         │
           │         │ problem    → annoyed          │
           │         │ neutral    → normal           │
           │         │ surprise   → bewildered       │
           │         │ tips       → wink             │
           │         └─────────────────────────────┘
           │
           ▼
     Shape accent?
           │
     ┌─────┴──────────────────────────────┐
     │ Check the slide content:           │
     │ key metric    → halo-blue          │
     │ warning/alert → halo-orange        │
     │ growth/win    → halo-lime          │
     │ process/steps → hex-formula        │
     │ relationships → overlap-circles    │
     └────────────────────────────────────┘
```

---

## 4. End-to-end example

### Scenario: Build a 12-slide "Interview Workshop" deck, user picks a template set

```
Step 1: Intake
    User: "Build an interview workshop slide deck, using the interview workshop template"
    → base_template = sun.interview-workshop-sunriser.01-cover
    → set_prefix = "interview-workshop-sunriser"

Step 2: Plan
    Slide 1: cover          intent=[cover, branded]
    Slide 2: agenda         intent=[agenda, list]
    Slide 3: timeline       intent=[timeline, process]
    Slide 4: tips           intent=[emphasis, tips]
    ...
    → Note: set_prefix = interview-workshop-sunriser

Step 3: Score (per slide)
    Slide 1 (cover):
      score_visual_items.py --item-type template \
                            --prefer-set interview-workshop-sunriser
      → sun.interview-workshop-sunriser.01-cover = 82.5 (reuse)
      → sun.salary-benefits-2026.01-cover        = 73.75 (no bonus)
      → Pick: .01-cover ✓

    Slide 3 (timeline):
      → sun.interview-workshop-sunriser.02-timeline = 82.5 (reuse)
      → Pick: .02-timeline ✓  (same set, consistent visuals)

Step 4: Compose
    Slide 1 (cover):
      Layer 1: background from template
      Layer 2: (no shape accent for the cover)
      Layer 3: heading + subheading from text-slots
      Layer 4: sun.asset.logo → top-left, 150px
      Layer 5: sun.character.dio (normal) → bottom-right, 120px

    Slide 4 (tips):
      Layer 1: background
      Layer 2: halo-blue accent next to the key tip
      Layer 3: tip content
      Layer 4: (no logo needed on middle slides)
      Layer 5: sun.character.dio (wink) → bottom-right
```

---

## 5. Combined decision flow (flowchart)

```
START: Agent receives the slide plan
  │
  ├── Is there a base_template in the brief?
  │     │
  │     ├── YES → derive set prefix from the ID
  │     │         pass --prefer-set to the scorer
  │     │
  │     └── NO → scorer runs normally (no bonus)
  │
  ▼
FOR each slide in the deck:
  │
  ├── [SCORE] Run score_visual_items.py
  │     │
  │     ├── score ≥ 75 → REUSE template as-is
  │     ├── score 65-74 → ADAPT template + local tweaks
  │     └── score < 65 → CUSTOM build from scratch
  │
  ├── [COMPOSE] Read component-composition.md
  │     │
  │     ├── Is the slide a cover/closing?
  │     │     └── Add logo (layer 4)
  │     │
  │     ├── Does the slide need emphasis/divider?
  │     │     └── Add dio character (layer 5)
  │     │         Pick variant by mood
  │     │
  │     ├── Does the slide have a metric/process/relationship that needs an accent?
  │     │     └── Add shape variant (layer 2)
  │     │         Pick variant by content
  │     │
  │     └── Stack by layer order:
  │           background → shapes → content → assets → characters
  │
  └── → Slide done, move to the next slide
  │
  ▼
DONE: Deck has consistent visuals thanks to set preference + composition rules
```

---

## References

| File | Role |
|---|---|
| `slide-system/rules/component-composition.md` | Rules for placing standalone items |
| `slide-system/scripts/score_visual_items.py` | Scorer with `--prefer-set` |
| `slide-system/workflows/select-visual-items.md` | Visual item selection flow |
| `slide-system/workflows/plan-slide-deck.md` | Plan the slides + note the set prefix |
| `slide-system/workflows/intake-and-triage.md` | Determine base_template |
| `slide-system/registries/visual-library.json` | Registry containing all published items |
| `.agents/skills/slide-generator/SKILL.md` | Main pipeline; item 7 points to the composition guide |
