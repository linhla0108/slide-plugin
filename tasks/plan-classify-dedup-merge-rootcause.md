# Plan: classify_page_components — root-cause fix for duplicates & mis-grouping

**Status:** ✅ IMPLEMENTED (RC-1..RC-3 + RC-2b auto-merge). `test_gates` 50/50;
all 5 pages re-run + render-verified; catalog 78 published + 11 staging. One
documented limitation: the comparison table's "section below" is not
geometrically separable (see "Implementation result"). RC-4 deferred (perceptual
dedup made its dedup-stability benefit moot; only de-bloat remains).
**Date:** 2026-06-25 · Branch: `feat/harness-enforcement-and-component-recognition`
**Trigger:** user-reported defects on the `guideline-fulldeck` batch:
1. `contributor-and-image-showcase.g01` → duplicate items, all the same.
2. `content-comparison-table-board.g01`, `contributor-and-image-showcase.g02`
   → multiple components glued, not separated.
3. `contributor-and-image-showcase.g03` vs `.g02` → same component split wrong.
4. `feature-step-shape-diagrams.g03` → two identical items (duplicate).

## Honest note on the prior "fix"
The earlier page-3 change was **parameter tuning only**
(`--min-area-frac 0.012 --group-gap-frac 1.2`). It changed *which* clusters
survive and *which* same-shape clusters group, for one page. It did **not**
address any of the four structural defects below — those were latent and
untouched. This plan targets the actual root causes in
`slide-system/scripts/classify_page_components.py`.

## Root causes (evidence-backed)

### RC-1 — Spatial clustering over-merges distinct objects
`_cluster_spatial` (`classify_page_components.py:127-179`) unions any two leaf
bboxes within `merge_gap` (default 6px). Adjacent-but-distinct components
collapse into one instance; there is no notion of a visible gutter/boundary.
- **Evidence:** `contributor…g02` renders a blue rounded card **+ a separate
  event photo** as one group; `content-comparison…g01` is the whole table as
  one instance.
- **Knock-on (your issue 3):** g02's blue card (merged with the photo → bbox
  1460×597) and g03's standalone identical blue card (484×474) fall into
  **different shape-classes** → the two copies of the *same* component split
  into different groups.
- **Causes reports 2 and 3.**

### RC-2 — Dedup is a raster byte-hash, defeated by sub-pixel translate residue
`_build_fragment` (`classify_page_components.py:434-436`) sets the viewport
origin with `math.floor(x0 - margin)` — an **integer** translate. Instances
sit at fractional coordinates, so each normalized per-card fragment lands at a
**different sub-pixel phase** → different anti-aliasing → different PNG md5 →
`_collapse_duplicates` (`classify_page_components.py:321-341`) never matches.
- **Evidence:** the 3 `g01` avatars have **byte-identical geometry** (22/22
  path `d` values equal elementwise) yet 3 different render hashes; the two
  orange hexagons (GOAL/KEY RESULT) differ only by translate (−674 vs −1344).
- **Causes report 1** (+ the orange-hexagon near-dup on page 3).

### RC-3 — Single-member groups emit a redundant group+card twin
classify always writes both `…-group-NN.svg` (whole run) and
`…-group-NN-card-01.svg`. For a 1-member group these are **byte-identical**,
and the catalog lists both as separate Draft items.
- **Evidence:** `feature-step…-group-03.svg` and `…-group-03-card-01.svg` share
  one MD5 (`e8b3e35…`, 71709 bytes). Also affects contributor g02, g03,
  content-comparison g01.
- **Causes report 4.**

### RC-4 — Fragments bake in N copies of the full-page background (contributing)
`_build_fragment` copies whole source groups (`classify_page_components.py:456-467`).
Layered PDF→SVG export gives each layer-group its own full-canvas background
rect, so they accumulate inside every fragment.
- **Evidence:** `contributor…card-01` holds **7 copies** of the page rect
  `M0 2623.16H2938.83V0H0Z` (7 of 15 paths). Bloats fragments and makes the
  raster hash (RC-2) even more fragile.

## Bug → root-cause map
| Report | Root cause |
|---|---|
| 1 — g01 duplicates not collapsed | RC-2 (+ RC-4 worsens it) |
| 2 — g02 / table glue multiple components | RC-1 |
| 3 — g02 vs g03 split wrong | RC-1 (knock-on shape-class drift) |
| 4 — feature-step g03 two identical items | RC-3 |

## Fix plan (dependency order; low-risk first)

### Step 1 — RC-3: stop emitting the group/card twin (small)
In `process_item`, when a group's `member_count == 1`, write a single fragment
and a single manifest entry (no separate `-card-01`). Update
`build_component_catalog.py` so a 1-member group yields **one** catalog entry.
- Verify: `feature-step…g03`, contributor g02/g03, content-comparison g01 each
  produce exactly one Draft tile; no two output SVGs in a group share an MD5.

### Step 2 — RC-4: drop full-canvas background children when copying a group (small-med)
In `_build_fragment`, skip any copied child whose measured bbox ≈ full canvas
(area ≥ `bg_coverage` × canvas, matching the existing background test). Keeps
the real component, removes the redundant page rects.
- Verify: re-render contributor card-01 → 0 full-canvas bg paths, avatar still
  intact; visual unchanged for page 2/3 (no regression in icons/gradients).

### Step 3 — RC-2: translate-invariant dedup (medium)
Replace the per-card **pixel** hash with a hash of the **canonicalized
fragment content**: strip the outer `translate(...)` wrapper, then hash inner
geometry + fills + image hrefs. Translate-invariant ⇒ identical components
collapse regardless of sub-pixel position; differing color/gradient/image keep
them distinct. Bonus: removes the Chromium dedup render entirely (closes the
deferred cost item #3 in `spec-classify-hardening.md`).
- Alternative (smaller, kept as fallback): make the inner translate use the
  **exact float** origin so identical instances normalize to byte-identical
  geometry, then dedup by file hash.
- Verify: 3 g01 avatars → 1 distinct card with `duplicate_count: 3`; 2 orange
  hexagons collapse, blue hexagon stays separate.

### Step 4 — RC-1: cluster only on true overlap (medium-high) — NEEDS DECISION
Change `_cluster_spatial` to bridge two leaves only when their bboxes **truly
overlap** (gap ≤ ~0 px), not within a 6px proximity gap. A single object's own
parts overlap → stay together; a card adjacent to a photo has a gutter → split.
- Expected: g02 → blue card and photo separate; g02's blue card and g03's blue
  card rejoin the same shape-class/group (report 3 resolved); a single card is
  not shattered.
- **Open decision (table granularity):** with overlap-only, the comparison
  table stays **one** component (its cells share borders). If you want the
  table broken into cells/columns, that is the more aggressive
  "decompose-containers" variant (higher risk of over-splitting) — confirm
  which you want for `content-comparison-table-board`.

## Verification (every step)
- Re-run `classify_page_components.py` on the affected item(s).
- Render group + per-card fragments at **native aspect** (render_svg.js does
  not scale — viewport must match the fragment viewBox or it clips) and inspect.
- MD5-compare known-identical components to prove dedup fires.
- `test_gates.py` must stay green; add regressions:
  - sub-pixel-offset identical instances collapse to one (RC-2),
  - overlap-only clustering splits adjacent / keeps overlapping (RC-1),
  - 1-member group emits a single artifact + single catalog entry (RC-3),
  - copied group drops full-canvas bg child (RC-4).
- Rebuild gallery + catalog; confirm Draft tiles match the de-duplicated,
  separated components.

## Risk / ordering notes
- Steps 1, 2 are isolated and safe; do first.
- Step 3 must come **after** Step 2 (bg removal stabilizes the content hash).
- Step 4 is the only behavior-changing step that needs a product decision; it
  can ship last (or be deferred) without blocking 1-3.
- Page 2 output (3 groups / 11 cards, icons intact) is the regression anchor —
  it must not change except for legitimate dedup collapses.

## Decisions needed before coding
1. RC-1 split depth: **overlap-only** (recommended) vs decompose-containers.
2. Comparison-table granularity: whole table (1 component) vs split into cells.
3. Scope: implement all of 1-4 now, or land 1-3 first and defer RC-1.

---

## UPDATE 2026-06-25 — user clarifications + deeper inspection

User answered the 3 decisions; deeper inspection then changed the picture.

### User decisions
1. **RC-1 = overlap-only, confirmed.** Extra nuance: a row can contain **2
   similar items + 1 completely different** — the row must stay grouped *and*
   the classification must show which are the same vs different.
2. **Table = keep whole**, BUT g01 currently also swallows **a separate
   section below that is unrelated to the table** — that section must be split
   off (table stays one component; the unrelated section becomes its own).
3. Scope priority left to my judgment (see "Recommended order" below).

### Finding A — dedup is TWO problems, not one (splits RC-2)
Inspected the actual fragment contents:
- **contributor g01 avatars = pure VECTOR**, geometry byte-identical across all
  3 (`images=0`, 22/22 path `d` equal). These are **true duplicates** → an
  exact, translate-invariant normalization collapses them cleanly. Call this
  **RC-2a (exact dedup)** — low risk, clearly correct.
- **feature-step g02 hexagons = 4 EMBEDDED PNGs each.** The two orange ones
  share 3 identical PNGs but differ in the **4th = the inner icon**
  (6876 vs 6888 bytes); blue differs more. So "2 tương tự" are the **same
  orange hexagon container with different icons inside** — visually similar,
  byte-different, and arguably *genuinely distinct components*. Collapsing them
  needs a **perceptual / threshold** similarity (pHash / down-scaled pixel
  distance), which **risks false-merge** (it could merge two cards that only
  differ by an icon the user cares about). Call this **RC-2b (perceptual
  dedup)** — higher risk, a policy call.
- ⇒ RC-2a and RC-2b are different mechanisms. RC-2a is safe to ship; RC-2b
  should either (a) be skipped (keep similar-but-different cards distinct), or
  (b) surface a similarity *score/badge* to the reviewer rather than
  auto-collapsing. **Recommend (b) or skip**, not silent auto-merge.

### Finding B — RC-1 cannot rely on a pure gap threshold for the table
Measured the table visual's on-canvas leaves: they form 2 vertical bands
(y=367..1048 and y=1049..2883) separated by only **~1px**. The unrelated
section sits almost flush against the table, while the table's own cells also
touch (~0px). A single gap threshold therefore **cannot** separate
table-from-section without also shattering the table's cells. RC-1 needs a
**structural signal** (e.g. split on the largest relative vertical gutter /
distinct container subtree), not just `gap <= k`. This raises RC-1 effort and
risk; it must be verified per-item against the regression anchor (page 2).

### Recommended order (answer to decision 3)
Highest-value / lowest-risk first; defer the risky/ambiguous parts:
1. **RC-3** (kill group/card twin) — trivial, removes the obvious duplicate
   (feature-step g03). Do first.
2. **RC-4** (strip full-canvas bg children) — isolated, de-bloats, stabilizes
   dedup. 
3. **RC-2a** (exact translate-invariant dedup) — fixes the avatar duplicates
   (the true-duplicate case). Clean + testable.
4. **RC-1** (overlap-only + structural-gutter split) — fixes g02 card/photo
   and the table/section glue; the knock-on shape-class drift (g02↔g03) then
   resolves. Medium-high; verify table stays whole.
5. **RC-2b** (perceptual similarity for raster cards) — LAST, and only as a
   reviewer-facing similarity hint, not auto-merge, unless you explicitly want
   similar-icon cards collapsed.

### Still-open decisions
- RC-2b: skip / show-similarity-badge / auto-merge similar raster cards?
- Confirm whether 1-4 should ship before RC-2b is decided (recommended: yes).

---

## Implementation result 2026-06-25 (user chose RC-2b = auto-merge "c")

Shipped in `classify_page_components.py` + `build_component_catalog.py`:
- **RC-3** — single-member group no longer writes a byte-identical `-card-01`
  twin; catalog shows ONE preview for it. (feature-step g03, contributor g02/g03
  fixed.)
- **RC-2 (a+b unified)** — replaced the brittle md5 pixel-hash dedup with a
  perceptual signature (PIL 32×32 alpha-flattened thumbnail) + mean-absolute-
  error threshold (`--dedup-mae`, default 3.0). Empirically: identical avatars
  MAE 0.09–0.18, similar orange hexagons 0.63, orange↔blue 111, distinct Level
  cards 47–171 → threshold 3.0 has a 16× margin. Collapses true duplicates AND
  near-identical "tương tự" cards while keeping different colour/icon distinct.
  Pillow is sanctioned by `REQUIREMENTS.md` (compare_renders/export stack).
- **RC-1** — added `_split_on_gutter`: after `_cluster_spatial`, split an
  instance when a clean empty band wider than `--split-gutter-px` (default 16)
  divides its LARGE leaves; tiny bridging leaves don't block the gutter and are
  assigned to the nearer side. Un-glues the card↔photo (21px gutter bridged by
  icon bits) without shattering single components or the page-2 anchor.
- Tests: `_collapse_duplicates` now distance-injected (+ threshold-merge test);
  `_split_on_gutter` separates-bridged + keeps-intact tests. `test_gates` 50/50.

Verified outcomes (render-checked):
- contributor g01: 3 avatars → 1 distinct ×3. g02 → the photo alone. g03 → 2
  blue cards reunited → 1 distinct ×2. (bugs 1, 2, 3 fixed.)
- feature-step g02: GOAL+KEY orange → 1 ×2, blue TASK kept. g03: single preview.
- page-2 anchor unchanged (3 groups / 11 distinct, no false merge).

**Limitation — comparison table "section below" not split.** Measured: the
table's big leaves form a contiguous cell grid; the largest vertical gap is
**1px**. The "completely different section below" the user sees is not present as
separable geometry in the text-free `visual.svg` (it is text-only content,
stripped, or only looks distinct in the original PDF). Geometry-only RC-1 cannot
separate it. Options if needed: (a) user supplies the section's region in the
extraction-request and extract it as its own item; (b) drive the split off the
text-slots layer; (c) accept table-whole. Needs user input.

RC-4 deferred: with perceptual dedup robust to the baked background, RC-4's only
remaining value is fragment de-bloat (7 redundant page rects); low priority.
