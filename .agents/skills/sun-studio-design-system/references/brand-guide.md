# SUN.STUDIO Design System

> Bundled skill note: paths in this document are rooted at
> `assets/system/` unless stated otherwise.

> Internal design system extracted for **SUN.RISER 2026 — Interview Workshop Deck**, built on top of the official SUN.STUDIO brand guidelines (SUN.Brandbook_2025.pdf).

SUN.STUDIO is a Vietnamese mobile-game studio (Ho Chi Minh City) that ships small, fun, fast-to-play games. The brand voice and visual identity revolve around three core values — **Fast & Faster**, **Quality**, **Responsibility** — and three personality traits — **Friendly**, **Skilled**, **Reliable**. The signature mascot is **Dio**, a dinosaur-meets-sun hybrid in `#FF5533` orange.

The specific surface this system was built for is the **SUN.RISER 2026 Interview Workshop deck** — a 12-slide internal training for Hiring Managers, used to train them on the *Hire-to-Develop* philosophy, S-T-A-R-R questioning, and a 6-step interview structure. Slides are bilingual in spirit (Vietnamese copy, English keywords) and built around a distinctive rotated **XO grid pattern** wash.

---

## Sources

These materials were used to extract this system. Reader does not necessarily have access — paths recorded for reproducibility.

| Source | What it was used for |
|---|---|
| `claude-design-slide-deck/materials/SUN.Brandbook_2025.pdf` | Master brand book — colors, type, logo rules, mascot, patterns, tone of voice |
| `claude-design-slide-deck/materials/SUN-STUDIO-Brand-Guidelines.md` | Pre-extracted markdown of the brandbook (primary reference) |
| `claude-design-slide-deck/materials/content.txt` | Slide-by-slide content brief for the 12-slide workshop deck (Vietnamese) |
| `claude-design-slide-deck/materials/Slides_GoalSetting2026_SUNers.pdf` | Reference deck — color usage, layout density |
| `claude-design-slide-deck/materials/Kick_off_GOAL_SETTING_2026-2.pdf` | Reference deck — title-slide treatment, mascot poses in context |
| `claude-design-slide-deck/materials/7. Cam Nang Vuyp2.pdf` | Internal playbook — patterns of badge/checklist/quote treatments |
| `claude-design-slide-deck/materials/SUN.STUDIO_-_Performance_Review_-_2025.pdf` | Reference deck — body-density / serif vs sans usage |
| `xo-pattern-slides/*.html` (12 slides) | The actual workshop deck — XO-pattern variant, the closest thing to a "production" surface. Copied wholesale into `slides/` |
| `uploads/Proxima-*.otf` | Brand typeface — Proxima Nova family + Black + italics |
| `uploads/logo.png` | Master logo (1939×487) — orange Dio + wordmark |
| `uploads/m0–m8.png` | Mascot pose sheet (no m4) — see `assets/dio/` |
| `uploads/image-selection-guide.txt` | Pose → file mapping for Dio mascot |

---

## Index — what's in this folder

```
README.md                  ← you are here
SKILL.md                   ← Agent Skill manifest (cross-compatible with Claude Code)
colors_and_type.css        ← Single source of truth for color + type tokens

fonts/                     ← Proxima Nova family (.otf)
assets/
  logo.png                 ← Master logo (orange Dio + SUN.STUDIO wordmark)
  dio/                     ← Mascot pose sheet (m0, m1, m2, m3, m5, m6, m7, m8 — no m4)

slides/                    ← Reference deck: 12 slides of XO-pattern interview workshop
  01-title.html  …  12-thank-you.html
  index.html               ← navigator for the 12 slides

preview/                   ← Tiny card files that render in the Design System tab
                             (registered via the asset manifest)

components/                ← Reusable deck components mined from legacy-decks/
  _base.css                ← Shared base every component inherits (imports tokens, --cs scale)
  chevron-flow.css … folio.css  ← 12 component stylesheets (one per component)
  _gallery.html            ← All 12 components on one reviewable page
```

### Deck components (mined from `legacy-decks/`)
Twelve layout components were extracted from the four real decks (Goal Setting 2026, Performance
Review 2025, the SUNers training deck, VUÝP handbook) and rebuilt in the brand-standard skin:
**chevron flow, swimlane, phase timeline, ratio split + donut, acronym framework, numbered Q&A,
value/benefit grid, agenda 01–04, section divider, formula block, competency columns, folio chrome.**
Each lives in its own `components/<name>.css`, `@import`s `components/_base.css` (which pulls the
canonical tokens), and scales uniformly via the `--cs` custom property (`--cs: 1` at slide scale,
smaller in preview cards). They render as cards 27–38 in the Design System tab.

### The reference deck
Twelve fully-built slides live in `slides/`. They are the canonical example of the system in motion — XO geometric pattern wash, orange `tab-orange` h1 word, blue numbered circles, orange "golden-rule" capsule footers, Dio mascot drop-ins, "kicker → h1 → split column → arrow-box" rhythm. Use them as templates.

---

## CONTENT FUNDAMENTALS

### Voice pillars
- **Sincerity** — honest, warm, human, empathetic. Avoid corporate jargon.
- **Competence** — clear, direct, with purpose. Every message has an actionable takeaway.

### Tone defaults
- Energetic, *not* cheerful. Confident, *not* loud. Coaching, *not* lecturing.
- **Concise** — short sentences, strong verbs. The brand's own internal value "Fast & Faster" applies to copy too.
- **Action-oriented** — every slide has a takeaway, an arrow, a "do this next."
- **Warm but professional** — bilingual Vietnamese decks freely sprinkle English keywords (`Growth mindset`, `What if`, `S-T-A-R-R`, `JD`) when they're the canonical term.

### Casing
- **Headlines & buttons**: `ALL CAPS`, always, with `letter-spacing: -.025em` to keep them tight.
- **Eyebrows / kickers**: ALL CAPS, looser tracking (`.18em`).
- **Body, sub-titles, descriptions**: **Sentence case**. Never title case. ("Tâm thế tuyển dụng", not "Tâm Thế Tuyển Dụng".)
- **Numbers**: written as numerals (`6 bước`, `25 phút`, `19 ngày`), not spelled out. Often promoted to display size.

### Person & address
- **Internal voice → "chúng ta" / "bạn"** (we / you). Inclusive, peer-to-peer, never top-down.
- Marketing/external voice → "we" or implied imperative ("Trang bị kỹ năng phỏng vấn cho Hiring Managers"). Avoid "I."

### Emoji
- **Use sparingly**, only in informal contexts (slide-deck speaker notes, "action item" rows in the closing slide, the occasional Dio caption). They are *not* part of the canonical visual vocabulary — never use them as section icons or hierarchical markers. Prefer **SVG icons in brand color**.
- Acceptable when present: 📧 📅 🎯 🌅 ⏱️ 💡 ✅ ❌ — and almost always at the end of the deck (thank-you slide), not the start.

### Sentence patterns
| Pattern | Example |
|---|---|
| **Provocation → answer** | "Bạn chọn ai?" → "Không có đáp án đúng. Có câu hỏi đúng." |
| **Negation → contrast** | "Hire-to-do. ❌ — Hire-to-develop. ✓" |
| **Imperative with object** | "Đọc lại JD như thể bạn đang viết nó lần đầu." |
| **Formula** | "NGHE 80% — FOLLOW-UP 20%" |
| **Arrow as logic** | "Người phù hợp + đúng thời điểm = đội ngũ bền vững" |

### Highlight rule
The brand highlights critical words by wrapping them in a coloured block. **Orange = primary impact**, **blue = secondary information**, **ink = quietly emphatic**. These should be **rare** — typically 1–3 highlights per slide. Treat them like a marker: choose the word the audience must remember.

### Taglines & signatures
- Master tagline: **SUN RISES. GAME ON.**
- Recurring closer: **LET'S FIND OUR NEXT RISERS!**
- The brand often closes with a *formula*: `→ X + Y = Z`.

---

## VISUAL FOUNDATIONS

### Colors
- **Primary Orange `#FF5533`** — energy, CTAs, highlights, key numbers, headline tab. Used for the single thing on a slide the viewer must remember.
- **Accent Blue `#3333FF`** — backgrounds (rarely), secondary numbered circles, "info" surfaces, S-T-A-R-R blue rings, secondary borders.
- **White `#FFFFFF`** — base. The brand is *not* a "dark-mode" brand.
- **Warm paper `#FFFDF8`** — used as slide background behind the XO grid (slightly warmer than pure white).
- **Ink `#171717`** — text, "golden rule" footer capsules, contrast surfaces.
- Tints applied in **25 / 50 / 75 / 100** increments. Soft-tinted backgrounds: `#FFF3EF` (orange-soft) and `#F4F5FF` (blue-soft).
- Semantic green `#22C55E` and red `#EF4444` exist *only* for explicit Do / Don't, checkmarks, and warning surfaces — never as brand accents.

### Typography
- **Proxima Nova** is the only typeface for digital surfaces (Black, Bold, SemiBold, Medium, Regular, plus their italics).
- Hierarchy:
  - Mega display: 100–136px / 900 black / `-.025em` tracking / UPPERCASE
  - h1: 72–78px / 900 black / UPPERCASE
  - h2: 52px / 900 / UPPERCASE
  - h3: 26–34px / 900 / UPPERCASE
  - lead: 28px / 700
  - body: 22px / 500
  - kicker: 16px / 800 / `.18em` tracking / UPPERCASE, prefixed with a 42×4px orange bar
- Headline leading is `font-size × 1.1`; paragraph leading `× 1.2`.
- Left-aligned is the default. Centre only when geometrically necessary (clock, onion, hero badges).

### Backgrounds
- **Warm paper** (`#FFFDF8`) is the dominant slide background.
- **XO grid pattern** — the system's signature backdrop. Tiled grid of X and O glyphs, rotated `-24°`, opacity ~16% with a few "hot" cells at full opacity acting as small focal accents. Drop-shadow offset of `16px 20px` gives a hand-printed feel. A radial orange wash (top-right) + horizontal paper gradient (left→right) soften the pattern so foreground text stays readable. Always combine pattern + `.wash` overlay together.
- Hard backgrounds: ink (`#171717`) for the bottom "golden rule" capsule, orange (`#FF5533`) for action footers.
- No photography. No gradients beyond brand-color soft washes. No drop-shadows other than the two systems below.

### Patterns
- **XO grid** — the production pattern. Geometric, scalable, derived from the logo's circular Dio-with-eye and the implied "vs" / "tic-tac-toe" theme of the workshop.
- **Diagonal-stripe pattern** — older fallback in some slides (`.pattern { background-size: 84px 84px, 64px 64px }`). Use only when XO would be too busy.

### Borders
- Cards: `2px solid var(--line)` (`#E7E7E7`).
- Emphasized cards: `2–4px solid var(--sun-orange)` (or blue).
- Most card corners: `radius 10–22px`. Pills use full `999px`.

### Shadows
Two distinct shadow systems:
1. **Soft elevation** (cards, panels, lifted surfaces):
   - sm `0 4px 12px rgba(0,0,0,.04)`
   - md `0 10px 26px rgba(0,0,0,.06)`
   - lg `0 18px 46px rgba(0,0,0,.10)`
   - xl `0 24px 80px rgba(0,0,0,.35)` (stage frame only)
2. **Coloured halos** (orange / blue, attached to a card of the same colour):
   - `0 14px 38px rgba(255,85,51,.24)`
   - `0 12px 34px rgba(51,51,255,.24)`
3. **Offset poster shadow** (very signature) — `18px 18px 0 rgba(255,85,51,.18)` behind the orange title tab and "hot" XO cells. Hard-edged, no blur. Hand-printed feel.

### Corner radii
- **xs** 4px — inline highlights
- **sm** 8–10px — buttons, small badges
- **md** 12–14px — cards, action items
- **lg** 18–22px — panels, hero blocks
- **pill** 999px — pill chips, numbered circles
- Slide hero h1 tab uses **asymmetric** `0 30px 30px 0` — only round on the right side, butting the text against the slide edge.

### Cards
The canonical card is **white background, 2–3px solid orange (or grey) border, 12–18px radius, soft md shadow, 18–34px padding, no inner drop-shadow**. Stronger emphasis = thicker border + coloured halo. Cards never use gradient backgrounds *except* a 135° wash from the soft-tinted brand color into white (e.g. `linear-gradient(135deg, #FFD4CC 0%, rgba(255,85,51,.06) 100%)`).

### Animation
- All entry animations use `cubic-bezier(.2,.8,.2,1)` (a punchy ease-out) at **620–780ms**.
- Three canonical motions:
  - `fadeUp` — translateY(34px) + opacity 0 → 0
  - `slideIn` — translateX(-24px) + opacity 0 → 0
  - `slideRight` — translateX(-54px) + opacity 0 → 0
- Staggered by `~80–120ms` per item.
- No bouncy, no spring, no scale-pop except subtle hover scale on interactive ring/pill (`scale(1.05)`).

### Hover / press
- Hover: subtle scale (1.05) or opacity bump on small interactive items. Cards never lift on hover in production decks (they are read-only).
- Press / active: shrink to `scale(.98)`, or use `--sun-orange-dark (#EB462D)` for orange buttons.

### Transparency & blur
- Used sparingly. The "paper wash" gradient over the XO pattern uses 72→44→10% paper-color stops to fade the pattern under text. Backdrop-blur is **not** part of the system.

### Imagery
- Two image categories only: **logo** + **Dio mascot poses**. No photography, no stock illustrations.
- Mascot poses are flat-vector, monochrome orange (`#FF5533`) on white. Drop-shadow `0 18px 24px rgba(0,0,0,.16)` when placed on light surfaces.

### Layout rules
- Slide canvas is **1920×1080** (16:9), scaled to viewport with a single `transform: scale()` on `#stage`. Page chrome is letterboxed black.
- Default slide padding: `84px 96px 78px`.
- Slide number lives bottom-right, 20px / weight 500, 70% opacity, `pointer-events:none`.
- Three vertical zones: **top (kicker + h1)** → **content** → **bottom action capsule**. The bottom capsule is the closer; it's usually orange or ink with a single sentence.
- Grid columns: 12-col implicit (split layouts are 50/50, 3-col 33/33/33, or 1fr-only).

### Layout fixtures (positioning)
- Logo: top-left, 176px wide
- Pills (eyebrow chips): top-right, 16px gap, orange pill outline
- Slide number: bottom-right
- Bottom action capsule: 88px tall, full-bleed minus 96px gutters

---

## ICONOGRAPHY

### What this brand uses
- **Inline SVGs** are the dominant icon medium. Most icons are hand-authored at 24×24 or 28×28 viewBox with `stroke="currentColor"`, `stroke-width: 2.5–3.5`, `stroke-linecap: round`, `stroke-linejoin: round`. They live alongside the markup that uses them — there is *no* central icon font or sprite.
- **The X and O glyphs** (used in the XO pattern wash) are the system's most recognizable icon-style elements. Specs:
  - X — `<path d="M24 24L76 76M76 24L24 76" stroke-width="18" stroke-linecap="round" />` (100-viewBox), orange `#FF5533`.
  - O — `<circle cx="50" cy="50" r="31" stroke-width="17" />`, ink black `#000`.
  - Both with a hard-edged offset drop-shadow (`16px 20px 0`) for the printed-poster look.
- **Status circles** — green/red filled circles with white checkmark/X inside for Do/Don't, success/error.
- **Numbered circles / pills** — orange or blue solid disc, 32–70px, white black-weight number inside.
- **Arrow vocabulary** — short straight arrows (`→`), drawn as 24-viewBox `path` strokes. They show up everywhere: footer capsules, slide flows, "see next" pointers.

### Emoji
Used sparingly and only at "celebration" moments — primarily the **thank-you / closing slide** (📧 📅 🎯 🌅), the occasional Do/Don't sub-bullet, or in informal speaker notes. They are not load-bearing.

### Unicode characters as icons
- Checkmarks: `✓` (success in inline copy) and `✅` for headline-scale.
- Crosses: `✗` and `❌` for the same.
- Em-dash `—` and arrow `→` are common rhythm devices in body copy.

### When you need a CDN fallback
If a slide needs an icon outside the brand's tight set (e.g. a clipboard, calendar, mail icon for an info row), the closest match is **Lucide** — it has the same stroke-2.5/round-cap aesthetic. Substitution is acceptable; flag it.

```html
<!-- Lucide via CDN (substitute) -->
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
```

### Available image assets
- `assets/logo.png` — master logo (1939×487, transparent PNG)
- `assets/dio/m0-normal.png` — neutral stance
- `assets/dio/m1-side-glance.png`
- `assets/dio/m2-wink.png` — **hero / canonical** (4500×4500)
- `assets/dio/m3-annoyed.png`
- `assets/dio/m5-dancing.png`
- `assets/dio/m6-bored.png`
- `assets/dio/m7-bewildered.png`
- `assets/dio/m8-variant.png` — hi-res variant (1180×1045)
- *(no m4 — clapping pose is missing from the source set; if needed, substitute m2)*

---

## Fonts: substitution notes
All Proxima Nova OTFs in `fonts/` are shipped (Regular, Medium, SemiBold, Bold, Black, plus matching italics). **No substitution required** — but two notes:

1. The brand book lists "Extra-bold" as a separate weight; the OTFs we have are Black (900) and Bold (700). Map `font-weight: 800` to fall back to one of these. The tokens file does this.
2. The optional secondary face for letterhead bodies (Times New Roman) and email signatures (Aptos) are *not* shipped — they're standard system fonts on Windows / macOS. Set them as fallback in the stack only.

---

## Quick start

```html
<link rel="stylesheet" href="./colors_and_type.css">
<style>
  body { background: var(--xo-paper); font-family: var(--font-body); }
</style>

<header class="kicker">Tâm thế tuyển dụng</header>
<h1 class="h1">Hai triết lý <span class="tab-orange">tuyển dụng</span></h1>
<p class="lead">SUN.RISER = Đầu tư vào người trẻ có khả năng <span class="hi-orange">RISE FAST</span>.</p>
```

For a full-bleed slide, copy any file from `slides/` and remix.
