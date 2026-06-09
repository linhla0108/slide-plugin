# SUN.STUDIO — Editorial Slide Guidelines

> Bundled skill note: original `../` implementation paths map to
> `assets/system/` in this skill.

> The "editorial / tactile" design language for **a single slide** at 1920×1080.
> Inherits SUN.STUDIO brand tokens (`../colors_and_type.css`, `../README.md`) but changes how things are *laid out & decorated*.
> Living reference: `../slides-v2/01-title.html`, `../slides-v2/03-objectives.html`, `../slides-v2/12-thank-you.html`.

---

## 1. PHILOSOPHY

The original deck (`../slides/`) is a **poster system**: symmetrical, pills, full-bleed XO pattern, rounded badges. Clean, but it easily becomes "uniform."

The editorial language goes for a **hand-set print page**: broken symmetry, type doing the decorating, added paper texture, italic serif as a second voice. Goal: *lively, natural, not mechanical* — while staying 100% inside the brand palette & fonts.

Three principles:
1. **Type is image.** The numerals 01–04, the huge display text, the tilted slash — they are content AND graphics at once. No extra decorative blocks needed.
2. **One anchor per slide.** Each slide has exactly one largest thing (the display headline, OR a numeral, OR DIO). Everything else recedes to hairlines & small mono.
3. **Deliberate asymmetry.** Bias left, leave breathing room on the right for the DIO bleed. Never center unless the geometry demands it.

---

## 2. BACKGROUND & MATERIAL

| Layer | How | Notes |
|---|---|---|
| Paper | `--paper #F1ECDE` (warmer cream than the original deck) | default background |
| Ink slide | `#141312` | for strong-rhythm slides (section divider / closing) to create contrast within the deck |
| Grain | SVG `feTurbulence` data-URI, `opacity .28`, `mix-blend-mode: multiply` | paper texture; over ink switch to `screen`, opacity .12 |
| Crease | 2 radial-gradients (light top-left, dark bottom-right) | fakes light falling on paper |

Rhythm rule: **at most 1–2 backgrounds per deck.** Usually cream for content, ink for open/close. Don't change background on every slide.

---

## 3. TYPE

Use the tokens already in `../colors_and_type.css`. The editorial-specific scale:

| Role | Font | Size | Weight | Tracking | Case |
|---|---|---|---|---|---|
| Mega display (title) | Proxima Nova | 240–280px | 900 | -.04em | UPPER |
| Display headline (content) | Proxima Nova | 80–112px | 900 | -.028em | UPPER |
| Numeral (01–04) | Proxima Nova | 64–96px | 900 | -.04em | — |
| Small section title | Proxima Nova | 26–34px | 900 | -.01em | UPPER |
| **Pull-quote / sub (secondary voice)** | **Times New Roman italic** | 18–32px | 400 | — | sentence |
| Kicker / folio / page-tag | mono (ui-monospace) | 13–16px | 500–700 | .2–.22em | UPPER |
| Body | Proxima Nova | 18–22px | 400–500 | — | sentence |

**Signature move:** italic serif (`--font-serif`) for every "secondary" sentence — pull-quotes, DIO captions, list-item subs. This is what separates this language from the original deck.

### Type-as-decoration techniques
- `.slash` — a `/` tilted 8°, orange, set between display words (SUN / RISER).
- `.ink-block` — a few characters wrapped in an ink background with paper text (local color inversion).
- `.strike` — a 9px-thick orange line-through over a "negated" word (Not ~~theory~~).
- `.mark` / `.circled` — a scribbled underline or hand-drawn circle via SVG path (orange or blue). Use at most once per slide.

---

## 4. LAYOUT

1920×1080 canvas, padding `78px 96px 76px`. Three proven grid templates:

### A. Title — asymmetric poster
- Giant display anchored top-left.
- `lower-band` (≤880px) at bottom-left: italic pull-quote + mono credit.
- DIO bleeds off the bottom-right edge (`right:-60px; bottom:-140px`), rotated -4°.
- Scattered X/O marginalia (4–5 of them), a date stamp rotated +4° top-right.
- **Anti-overlap rule:** copy always lives on the left half; DIO occupies the right half. Never let the two zones overlap.

### B. Content — 2×2 list + DIO column
- Head on top (mono kicker + headline ≤84px) — leave enough `top` clearance.
- 4-item list as a **2×2 grid**, each item: large numeral | (UPPER title + italic sub), separated by a `1px rgba(20,20,20,.2)` hairline.
- Right column (~540px) for DIO + an italic speech bubble.
- Mono footer rail (left: summary / right: §slide number).

### C. Closing — ink background
- Huge "Thank you." display, orange period.
- `sub-stack`: 3 mono lines, each with an orange `→` arrow.
- DIO + soft orange halo + P.S. note (orange sticker rotated -4.5°).
- `contact-rail` of 4 columns (k/v) separated by light hairlines.
- `bottom-bar`: tagline "SUN RISES · GAME ON" + index.

---

## 5. TACTILE DETAILS (use sparingly)

- **Sticker** — an ink/orange/tape block, rotated -2.4°, hard offset-shadow `4px 5px 0`. NO blur.
- **Stamp** — 3px orange border slightly rounded, mono, rotated +4° (like a rubber stamp).
- **Tape** — yellow `--tape` background, mono, rotated -1.4° (like masking tape).
- **Speech bubble** — `--paper-shade` background, skewed triangular tail, italic text.
- **Halo** — soft orange radial behind DIO on ink backgrounds (ink slides only).

Keep all rotations within **±2–4°**. Offset shadows are always **hard-edged**, never blurred (preserves the printed feel).

---

## 6. DIO (mascot)

- The ONLY character imagery. Poses come from `../assets/dio/` (m0–m8, no m4).
- Title → `m1-side-glance` or `m2-wink` (canonical hero).
- Closing → `m2-wink`.
- Difficult/negative → `m3-annoyed`, `m6-bored`.
- DIO's drop-shadow: hard-edged offset (`drop-shadow(14px 18px 0 …)`) on cream; on ink use an orange halo instead of a shadow.
- Always let DIO **bleed or tilt slightly** — never place it upright in the center of the frame.

---

## 7. SHARED CHROME (from `_v2.css`)

- `.folio` — top bar: deck name (left) + §number · label · month (right), sandwiched between two hairlines.
- `.page-tag` — bottom-right corner: `NN / 12` mono. **Hide it if the slide already has its own footer rail / by-line** (avoid a duplicate index).
- `.grain` + `.crease` — always placed last in the `<section>`, `z-index:1`, `pointer-events:none`.
- `.kicker-mono` — kicker with an orange `●` separator.

---

## 8. PRE-DELIVERY CHECKLIST

- [ ] Only brand colors used? (orange/blue/ink/paper/tints + green-red for Do/Don't)
- [ ] Headline UPPER, body sentence case?
- [ ] Exactly one visual anchor?
- [ ] Pull-quote/sub set in Times italic?
- [ ] Orange highlight ≤ 3 spots?
- [ ] DIO bleeding/tilted, not centered upright?
- [ ] All rotations within ±2–4°, offset-shadows un-blurred?
- [ ] Copy doesn't overlap DIO; page-tag doesn't duplicate the index?
- [ ] `data-screen-label` set?
- [ ] Grain + crease last in section, not blocking clicks?
