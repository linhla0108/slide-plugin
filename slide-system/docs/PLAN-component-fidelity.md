# PLAN — Component Fidelity & Flow/Docs Audit (v2)

> Goal: a pipeline that **sticks to the real component** instead of copying the
> layout by eye or faking reuse with a data-attribute. Philosophy:
> **correct-by-construction** (make getting it wrong impossible), not
> **check-after** (let the agent build it and then go hunt for errors).
>
> Status: **PLAN — code/flow-docs not yet touched.** Awaiting scope sign-off to code.
> v2 fixed 5 errors raised by the agent review (see the Changelog at the end of the file).

---

## 0. Root causes (verified against the code)

| # | Root cause | Evidence |
|---|---|---|
| RC1 | The force-use-component gate is **bypassable** — it only checks the `item_id` substring | `validate_brand_compliance.py:113` `check_template_assets` |
| RC2 | The "use the real component" step is **prose**, with no gate | SKILL step 10; `build-html-deck.md` |
| RC3 | **No gate** links `deck.html` ↔ component structure | script missing |
| RC4 | **Docs use the wrong path (doubly wrong)**: they point to `<item>/artifact/visual.svg`, treating `artifact/` as a subfolder containing `visual.svg`. In reality, in the registry `paths.artifact` = **the item directory itself** (`.../01-cover`), while `paths.visual` = `<item-dir>/visual.svg`. The correct path is `<item-dir>/visual.svg`. | `build-html-deck.md:58,94,102`; SKILL:133; registry `paths` |
| RC5 | **No build doc treats `preview.html` as the source for building a slide.** `preview.html` is what actually contains the real design (gradient, `.bg`, `.slot`); `visual.svg` is only a decorative vector. (`save-as-template.md:36` does mention `preview.html`, but only as a generated artifact, not as a build source.) | agenda `preview.html` = **13,877 bytes** (has CSS/slot) vs `visual.svg` = 1,479 bytes (vector only) |
| RC6 | The scorer produces semantically wrong matches **without warning** (timeline→agenda); a request with poor tags is not flagged | the first scoring run on v6 |

**Conclusion:** the current docs + gate **actively lead the agent astray** (wrong path,
missing the `preview.html` concept) and the gate cannot catch fake reuse. This is not
just an agent error.

---

## 1. Architecture change: defensive → correct-by-construction (3 tiers)

Separate the **two problems** that used to be lumped together:
- **SELECTION** = pick the RIGHT component (a timeline must yield a timeline, not an agenda).
- **FIDELITY** = USE the chosen component correctly (no hand-drawing / faking).

Instead of "let the agent build it and then scan for fakes", enforce both up front with 3
tiers — **none of which need a human eye during the build**:

| Tier | Name | Error it blocks | Mechanism |
|------|-----|-------------|--------|
| **T1** | **Selection-lock** | Picking the wrong component type | Each slide declares `content_shape` (enum) → a hard-coded `shape → valid component type` map → gate **FAILs** if mismatched |
| **T2** | **Generative build (mandatory)** | Hand-drawing / faking | A script generates the slide frame **from `preview.html`** (keeping `.bg`+`.slot`); the agent **only fills text into slots** |
| **T3** | **Fidelity (safety net)** | Someone skips T2 | Gate compares the **automatic class-signature** between slide ↔ `preview.html` |

The only "judgment" left = **mapping content → shape** (structured, checkable via enum +
map). Picking the specific component and building both become **mechanical**.

---

## 2. Audit of the whole flow (per-step)

| Step | Current state | Gap | Fix (tier) |
|------|-----------|-----|------------|
| 1 Intake/triage | prose | — | keep |
| 2 Recap gate | manual | — | keep |
| 4 check_requirements | script ✓ | — | keep |
| 7 score_visual_items | script ✓ | RC6 | **T1+D**: add `content_shape`; guard low score / poor tags |
| 8 validate_selection_report | script ✓ | does not lock type; does not force review | **T1**: shape→type gate; **D**: `preview_reviewed` |
| 9 Approval | prose | — | display the decision + thumbnail (registry path already exists) |
| 10 Build HTML reuse | **prose, WRONG path** | RC2/RC4/RC5 | **T2**: scaffold from `preview.html` (mandatory) |
| 11 validate_brand_compliance | bypassable | RC1 | **B**: remove false-positive |
| 11.5 **(NEW) fidelity** | missing | RC3 | **T3**: safety gate |
| 12 export_pptx | script ✓ | — | insert T3 before export |
| 13 cleanup_run | script ✓ | — | keep |

---

## 3. Docs audit (file → issue → action)

| Doc | Issue | Action |
|-----|--------|-----------|
| `SKILL.md` (`.agents/skills/slide-generator/`, symlinked from `~/.claude`) | wrong `artifact/visual.svg` path; no mention of `preview.html`; missing fake-reuse Prohibition | fix path → `<item-dir>/visual.svg`; treat `preview.html` as the build source; add Prohibition #5; wire T1/T2/T3 |
| `workflows/build-html-deck.md` | lines 58/94/102 use WRONG `artifact/` path; flow revolves around decomposing `visual.svg` (wrong source) | rewrite: **reuse = scaffold from `preview.html`**; decompose only for real artwork-SVG |
| `workflows/select-visual-items.md` | missing `content_shape`, score/tag guard, review | add T1 + D |
| `rules/content-fidelity.md` (thin) | does not define what "fidelity" is measured by | define = class-signature/asset of `preview.html` |
| `rules/component-composition.md` | sync the preview.html flow | update |
| `rules/approval-gates.md` | does not list the T1/T3 gates | add |
| **Registry caveat (new)** | **the scorer reads `visual-library-compact.json` by default — this file strips out `paths`** | every gate that needs a path **must read the full `visual-library.json`**, NOT the compact one |

---

## 4. T1 — Selection-lock gate

**Where applied:** extend `validate_selection_report.py` (or a new script `validate_shape_lock.py`).

**Add to each slide in `visual-requests.json`:** a mandatory `content_shape` field
(enum). A **hard-coded map** of `shape → valid component type/intent`, for example:

| content_shape | valid intent/type |
|---|---|
| `cover` | cover, hero, title |
| `stats` | statistics, data, metrics; grid |
| `comparison` | comparison, do-dont, what-how |
| `timeline` | timeline, schedule, roadmap, process |
| `checklist` | checklist, preparation, steps |
| `two-column` | two-column, split |

**Logic:** for each slide, read the `intent`/`tags` of the chosen component (from the
**full registry**) → if it **does not intersect** the valid set for `content_shape` → **FAIL**.
→ Catches "timeline mistakenly chose agenda" **mechanically**, not with an empty warning.

---

## 5. T2 — Generative scaffold (MANDATORY) — `scaffold_slide_from_component.py`

**File:** `slide-system/scripts/scaffold_slide_from_component.py`
**CLI:** `--item-id <id> --registry slide-system/registries/visual-library.json --out <fragment.html>`

**Logic:**
1. Read the **full registry** → get `paths.preview` of `item_id` (do NOT guess the dir, do NOT glob — the registry already has the path).
2. Parse `preview.html` → keep `.bg` + all `.slot` (including position/bounds), replace
   `example_value` with an empty placeholder carrying `data-slot-id`.
3. Export the slide fragment so the agent **only fills text into slots**.

→ When the slide is *generated from* `preview.html`, it matches the component **by
construction** → fidelity is guaranteed, not measured. This is the **backbone** of the solution.

---

## 6. T3 — Fidelity gate (safety net) — `validate_component_fidelity.py`

**File:** `slide-system/scripts/validate_component_fidelity.py`
**CLI:** `--html <deck> --selection-report <json> --registry slide-system/registries/visual-library.json [--warn]`

**Status (2026-06-24):** implemented + unit-tested, and now **wired in `--warn`
mode** into the slide-generator build path —
`.agents/skills/slide-generator/SKILL.md` step 11 and
`slide-system/workflows/build-html-deck.md` Post-Build Gate. It still exits 0 on
failure (rollout). Switching to BLOCKING (drop `--warn`) is rollout step 4,
pending a sample deck rebuilt from scaffold confirming PASS. Belongs to the
slide-generator pipeline, not the component-extractor.

**Logic (simpler than plan v1 thanks to the registry having paths):**
1. Read the **full `visual-library.json`** → map `item_id → paths.preview`.
   *(NO heuristic resolver, NO glob fallback — removed in v2.)*
2. For each slide with `action ∈ {reuse, adapt-local}`:
   - Load `paths.preview` → signature = set of class names (`.bg`, `.slot`, …).
   - Get the slide fragment by `data-export-id`.
   - **Evidence of real use** (≥1 must hold):
     - (a) decompose asset: `href/src` matches `*/assets/page-NN/*`;
     - (b) **class-signature**: reuse needs ≥ **70%**, adapt-local needs ≥ **45%** of `preview.html`'s class names to appear;
     - (c) `background-image` points to the component's `paths.visual`.
   - Only `data-base-component` → **FAIL**.
3. **Do NOT use slot-id text as a signal** (slot id is an English slug, a VN deck won't match → false-fail).
4. Output `qa/component-fidelity-report.json`; FAIL → exit 1 (except with `--warn`).

---

## 7. B — Patch `validate_brand_compliance.py`
`check_template_assets`: stop accepting the bare `data-base-component` substring as
evidence; move the "actually used" responsibility to T3. This gate only keeps the
color/font/emoji checks.

## 8. D — Scorer guardrail
- `score_visual_items.py`: top score `< 65` → force `action="custom-local"` + `recommend_extraction=true` + warning "no strong match".
- `validate_selection_report.py`: WARN if the request has `< 3 tags`; FAIL if `content_shape` (T1) or `preview_reviewed` is missing.

---

## 9. Tests
- `test_scaffold_slide_from_component.py`: generates a fragment with `.bg`+`.slot` from `paths.preview`; clear error when item_id is not in the full registry.
- `test_validate_component_fidelity.py`:
  - FAIL: deck has only `data-base-component`.
  - PASS reuse: ≥70% class-signature; PASS adapt: ≥45%.
  - **Reads the full registry** (separate test: if pointed at compact → must report error "registry missing paths", NOT fail silently).
- `test_shape_lock.py`: shape↔type match/mismatch.
- ~~`test_resolve_component_dir`~~ — **removed** (no resolver anymore).
- Regression: run T3 `--warn` on one deck built-from-scaffold to ensure no false-fail.

---

## 10. Implementation order & rollout
1. **T1 selection-lock** (+ `content_shape` into requests) → block wrong selection at the root.
2. **T2 scaffold** (backbone) + test.
3. **B** remove false-positive.
4. **T3 fidelity** `--warn` → rebuild one sample deck from scaffold → confirm PASS → switch to **BLOCKING**.
5. **C** fix SKILL + workflows (path, preview.html, prohibition, wire gate, registry caveat).
6. **D** scorer guardrail.
- **Breaking:** after T3 is BLOCKING, every old hand-copied deck fails until rebuilt from scaffold.

---

## 11. Open questions (recommendations applied, need your sign-off)
1. Class-signature thresholds **reuse 70% / adapt 45%** — ok or tune?
2. Is the `content_shape` enum in section 4 complete enough? (add: `divider`, `quote`, `faq`, `image-text`?)
3. Code scope: **T1+T2+T3+B** (core) or **full T1–T3 + B + C + D**?
4. Clean up the remaining stale job-level files of `company-trip-2026` (`analysis/`, `approval/`, `requirements/`, `slide-content-plan.md`)?

---

## Changelog v1 → v2 (5 errors fixed, from the agent review)
1. **Removed the heuristic resolver + glob** (old RC): the full registry already has `paths` for 127/127 items → the gate reads `paths.preview` directly. Also dropped `test_resolve_component_dir`.
2. **Added a registry caveat**: the scorer uses `visual-library-compact.json` by default (paths=0); every gate that needs a path must read the **full `visual-library.json`**.
3. **RC4 corrected to doubly-wrong**: `paths.artifact`=the item directory, `paths.visual`=`<item-dir>/visual.svg`; the correct path = `<item-dir>/visual.svg`.
4. **RC5 figures corrected**: agenda `preview.html` = **~14K (13,877 bytes)**, not 44K (44K is `06-two-column`).
5. **RC5 overstated claim fixed**: → *"no build doc treats `preview.html` as the source for building a slide"* (save-as-template.md:36 does mention it as a generated artifact).
