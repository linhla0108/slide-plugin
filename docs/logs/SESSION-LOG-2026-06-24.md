# Session Log — 2026-06-23 → 2026-06-24

A record of everything done in this working session on branch
`feat/harness-enforcement-and-component-recognition`. Grouped by task in the
order the user requested it. **Nothing in this session has been committed yet.**

---

## 1. Document the `crop_svg_region.py` component-cropping fix

Updated docs / skill / flow-simulation files to reflect the crop step completed
in the prior session (the PDF→SVG path emits a whole page, so a component-level
item must be cropped to its `source.region`).

- **`docs/flows/skill-flows.md`** — added crop step `b2` to pipeline `[3]`, a
  publish-gate note to `[6]`, a hard rule, and bumped the date.
- **`slide-system/README.md`** — added the `crop_svg_region.py` command block and
  explained it rewrites `visual.svg`'s viewBox + re-normalizes `text-slots.json`,
  is a no-op for full-page regions, idempotent (marker `source.region_crop`), and
  that `publish_extraction.py` blocks publishing a component-level item missing
  this marker.
- **`docs/flows/slide-generator-workflow.md`** — added a `crop_svg_region.py` row
  and marked `publish_extraction.py` as gating the component crop.
- **`.agents/skills/component-extractor/SKILL.md`** and
  **`slide-system/workflows/extract-components.md`** — added the crop step to the
  pipeline (SKILL step 3 / workflow step 8b).

---

## 2. Delete extracted "slide-dupe" components + redesign the agent-facing index

The library had too many large, full-page "components." Per the user's choice
("Chỉ xóa slide-dupe" — delete only slide-duplicates):

- **Deleted 47 slide-dupe full-page components** (registry 127 → 80 items,
  ~55.7 MB freed). A non-template item is a slide-dupe when its (source file,
  slide) matches a published template's. Kept genuinely reusable items:
  `guideline-shape-variants`, `guideline-board-layouts`, logo, Dio.
- **Deleted 15 junk orphan folders** (folders with a `visual.svg` but no registry
  entry), including `sun.component.long-term-benefits` and
  `sun.component.salary-benefits-thanks` found by the drift check.
- **Registered the orphaned-but-used `guideline-icon-library`** so it stops being
  an orphan.

### New self-healing registry tooling

- **`slide-system/scripts/build_registry.py`** (NEW) — reconcile + projection tool.
  - `--check`: exits 1 on registry↔disk drift (gate).
  - `--write`: drops dangling registry entries (entry but no folder) and rebuilds
    `visual-library-compact.json`; reports orphans but never deletes folders.
  - `COMPACT_KEYS` defines the 10-key projection the scorer reads.
- **`slide-system/scripts/publish_extraction.py`** — now imports `COMPACT_KEYS`
  from `build_registry` and regenerates `visual-library-compact.json` on every
  publish.
- **`slide-system/catalog/catalog_server.py`** — added `regen_compact()` (runs
  `build_registry.py --write`) and calls it in the published-delete branch before
  `regen_catalog()`, so the scorer's compact registry stays in lockstep after a
  delete from the catalog UI.
- **`slide-system/scripts/test_gates.py`** — repointed a test off a deleted item
  to `sun.component.guideline-board-layouts`; added
  `test_build_registry_projection_and_compact_keys` and
  `test_build_registry_live_is_clean`. Suite now 16/16.

Architecture note: published library folders do **not** retain `mapping.json`, so
`visual-library.json` is the metadata authority and cannot be rebuilt from disk —
`build_registry.py` *reconciles* rather than rebuilds.

---

## 3. Diagnose "Request failed (405)" on catalog Delete + serving guidance

- **Root cause:** the catalog Publish/Delete buttons POST to origin-relative
  `/api/publish` and `/api/delete`, which only `catalog_server.py` (port 8799)
  implements. Opening the page from another origin breaks the POST:
  - `python3 -m http.server` → **501** ("control server not running", view-only).
  - VS Code **Live Server** (:5500) → **405 Method Not Allowed** ← what the user hit.
  - `catalog_server.py` → 404 only for unknown endpoints, never 405.
- **Killed Live Server on port 5500** (PID 98032); confirmed control server still
  up on 8799.
- **Added agent-facing serving guidance** so an agent starts the catalog correctly
  for preview/manage and auto-serves after extraction:
  - `.agents/skills/component-extractor/SKILL.md` (pipeline step 5)
  - `slide-system/workflows/extract-components.md` (step 12)
  - `slide-system/README.md` (replaced the old `http.server` instruction; added a
    blockquote on the 501/405 traps and the origin-relative `fetch`)
  - `docs/flows/catalog-publish.md` (Hard rules: origin-relative fetch, 501/405,
    must open from `127.0.0.1:8799`)

Note: the `deletable` flag is only true for artifacts under
`slide-system/library/`; brand assets (logo, Dio under `.agents/…`) are
non-deletable by design, with a server-side 403 guard.

---

## 4. Translate all Vietnamese docs to English

Faithful translation (no rewrites, no added/invented content), preserving every
code block, path, command, URL, ID, port, status code, and Markdown structure.
Final scan confirmed **zero Vietnamese remaining** across all 9 files.

| File | Notes |
|---|---|
| `docs/how-to-use.md` | User guide; ASCII boxes re-padded for alignment |
| `docs/images/README.md` | Cross-reference marker updated to `<!-- INSERT IMAGE ... -->` |
| `docs/flows/skill-flows.md` | |
| `docs/flows/catalog-publish.md` | `Luật cứng` → "Hard rules"; `[GIỮ]/[MỚI]` → `[KEEP]/[NEW]` |
| `docs/flows/component-selection-flow.md` | |
| `docs/flows/template-picker-flows.md` | |
| `docs/flows/3layer-export.md` | Diagram annotations also translated; markers normalized |
| `slide-system/docs/PLAN-component-fidelity.md` | |
| `slide-system/workflows/save-as-template.md` | One Vietnamese blockquote |

Notation markers are now consistent: `[KEEP]` / `[FIX]` / `[NEW]`.

Deliberately left untouched: the vendored `.agents/skills/ppt-master/` tree — its
"Vietnamese" matches were false positives (stray accented characters and
Chinese deck names), not authored prose.

---

## 5. Add a mandatory task-logging rule to the repo

**Request:** "update your rule in this repo, log detail any task that u did."

**Actions:**
- **`AGENTS.md`** — added a "## Task Logging (required)" section (before
  "Product Direction") defining where to log (`docs/SESSION-LOG-<YYYY-MM-DD>.md`,
  append-only, one file per day), when (as each task completes), what to record
  (request → actions → result + verification → commit state), and a faithfulness
  rule (log only what happened, ground claims in real command output).
- **`.claude/CLAUDE.md`** — added a short "## Task Logging (required)" pointer so
  Claude Code auto-loads the rule each session, referencing the full rule in
  `AGENTS.md`.
- Logged this task here, demonstrating the rule.

**Result:** Future sessions in this repo are instructed to keep a detailed
per-task log. **Not committed.**

---

## Net file changes (uncommitted)

- **Modified:** 19 tracked files (docs, skill/workflow files, `catalog_server.py`,
  `publish_extraction.py`, `test_gates.py`, registries, catalog/picker data).
- **Deleted:** 479 files (the 47 slide-dupe components + 15 junk orphans, each a
  multi-file folder).
- **New (untracked):** `slide-system/scripts/build_registry.py`,
  `slide-system/scripts/crop_svg_region.py`,
  `slide-system/registries/visual-library-compact.json`, `slide-system/docs/`,
  and assorted config files (`.claude/`, `.mcp.json`, `opencode.jsonc`, etc.).

## Verification run

- `test_gates.py`: 16/16 passing.
- `build_registry.py --check`: clean (no registry↔disk drift).
- Vietnamese scan across all 9 translated docs: 0 matches.

---

## N. Simulate `component-extractor` and `slide-generator` skill workflows (read-only audit)

User asked for a detailed, ground-truth walkthrough of both skills' workflows
(stating the docs are stale). No code changed — analysis only, read directly
from the scripts (the authority), not the docs.

- Read `.agents/skills/component-extractor/SKILL.md` and
  `.agents/skills/slide-generator/SKILL.md`.
- Read the real implementation of every pipeline script and recorded exact
  CLI args, files read/written, JSON shapes, and non-zero exit (gate)
  conditions for: `scaffold_extraction.py`, `convert_pdf_source.py`,
  `crop_svg_region.py`, `extract_editable_text_slots.py`,
  `externalize_svg_images.py`, `flatten_svg_background.py`, `optimize_svg.py`,
  `apply_text_contract.py`, `validate_text_slots.py`, `publish_extraction.py`,
  `generate_item_preview.py`, `build_component_catalog.py`, `catalog_server.py`,
  `check_base_requirements.py`, `prune_empty_dirs.py`, `score_visual_items.py`,
  `check_requirements.py`, `scaffold_slide_from_component.py`,
  `decompose_svg_objects.py`, `read_text_slots.py`, `export_pptx.py`,
  `validate_export_objects.py`, `cleanup_run.py`, `setup.sh`, plus the gate
  scripts `validate_selection_report.py`, `validate_brand_compliance.py`,
  `validate_component_fidelity.py`, and `test_gates.py`.
- Confirmed current `extract-readiness.json` = `status: ready`; PDF provider
  (PyMuPDF) available; PPTX provider (LibreOffice) missing → blocks PPTX-sourced
  jobs only.

**Result:** delivered two detailed workflow simulations in chat. Flagged
doc-vs-code discrepancies worth fixing later (NOT yet fixed):
- `scaffold_extraction.py` requires a `--request <json>` file (SKILL.md omits this).
- extractor naming gate regex is narrower than SKILL.md prose (`_BANNED_ID`).
- `optimize_svg.py --max-dimension` default is 1920, docstring says 2560.
- slide-generator SKILL step 12 export command omits required `--slides` and
  `--out-dir` (would argparse-error as written).
- `cleanup_run.py` deletes `export-result.json` (SKILL wording implies kept).
- `validate_brand_compliance.py --brand-pack` value is never consumed.
- `validate_component_fidelity.py` (T3) exists + unit-tested but is not wired
  into any workflow/skill/rule.
- `--prefer-set` +5 bonus can flip a scorer decision across 65/75 thresholds;
  undocumented in SKILL.md.

**Committed:** no.

---

## 6. Verify another agent's doc-vs-code report + fix items 1–4

**Request:** "check lại report của agent khác" then "fix 1 to 4" — verify a
6-point discrepancy report against the code, then fix the first four.

**Verification:** confirmed all 6 claims true against the code (no false
positives), with two nuances: (#1) `README.md` already documents `--request`, so
the gap is SKILL.md-only; (#5) the *publish* path is genuinely server-enforced
via `catalog_server.py` → `publish_extraction.py`, only the upstream pipeline is
honor-system.

**Fixes applied:**
1. **`.agents/skills/component-extractor/SKILL.md`** — documented the mandatory
   extraction-request JSON interface (`scaffold_extraction.py --request <file>`,
   required), pointing to `schemas/extraction-request.schema.json` +
   `boilerplates/extraction-request.json` and the required item fields.
2. **`slide-system/scripts/scaffold_extraction.py`** — tightened `_BANNED_ID` to
   actually enforce the documented contract: now also blocks purely-numeric ids
   (`42`) and positional-only ids (`top-left`, `center`), while still allowing
   semantic names that start with a direction word (`left-rail`). Updated
   SKILL.md's prohibited-pattern list to match the regex exactly. Verified with
   block/allow test cases.
3. **`slide-system/scripts/optimize_svg.py`** — docstring default corrected
   2560 → 1920 (matches argparse).
4. **`validate_component_fidelity.py` (T3)** — wired into the slide-generator
   build path in `--warn` mode (rollout step 4): added to
   `slide-system/workflows/build-html-deck.md` Post-Build Gate and
   `.agents/skills/slide-generator/SKILL.md` step 11; recorded status in
   `slide-system/docs/PLAN-component-fidelity.md`. Verified its CLI before
   wiring (`--html`, `--selection-report`, `--registry`, `--warn`).

**Regression found + fixed (not part of the report):** running `test_gates.py`
surfaced a failure — `sun.component.guideline-board-layouts` had been
over-deleted in this session's earlier deletion pass (it is a reusable diagram
component, not a slide-dupe, and was explicitly meant to be kept). Restored the
folder from HEAD (`git checkout HEAD -- …`) and re-inserted its registry entry
from HEAD; ran `build_registry.py --write`.

**Result:** `test_gates.py` 16/16; `build_registry.py --check` clean (79 valid
items, 0 dangling, 0 orphan). Items 5–6 of the report are accurate observations,
not bugs, so left as-is. Other discrepancies from task N (export command
`--slides`/`--out-dir`, `cleanup_run.py` deleting `export-result.json`,
`--brand-pack` unused, `--prefer-set` bonus undocumented) were **not** in scope
and remain open. **Not committed.**

---

## 7. Move logs to `docs/logs/`, classify the diff, and commit

**Request:** "phân loại file trong git diff và commit giúp tôi … log phải bỏ
trong folder log."

**Actions:**
- Moved this log to `docs/logs/SESSION-LOG-2026-06-24.md`; updated the
  Task-Logging rule in `AGENTS.md` + `.claude/CLAUDE.md` to require all logs under
  `docs/logs/`.
- Flagged `backup.cswap` as a **sensitive wallet/account backup** (emails,
  `encrypted: false`); did NOT commit it — added `*.cswap` + local `.claude`
  state to `.gitignore`. Recommended removing it from the repo dir.
- Classified the accumulated diff (since 2026-06-23) into 7 thematic commits on
  `feat/harness-enforcement-and-component-recognition`:
  1. `chore:` codegraph MCP/tooling config + gitignore
  2. `feat:` component-region crop + extraction/catalog docs
  3. `feat:` prune slide-dupe components + self-healing registry (472 deletions)
  4. `docs:` translate Vietnamese docs to English
  5. `fix:` naming gate / optimize_svg default / wire T3 gate
  6. `docs:` slide-generator token-efficiency plan
  7. `chore:` task-logging rule + this session log

**Result:** working tree clean (only git-ignored files remain); `test_gates.py`
16/16; `build_registry.py --check` clean (79 items). **Committed** (this entry
folded into commit 7 via amend).

---

## 8. End-to-end test of the `component-extractor` skill on `input/GUIDLINE_PRESENTATION_SUN.pdf`

**Request:** run the skill and test the component-extraction workflow on the
guideline PDF to verify it works end-to-end and matches intent.

**What ran (real commands, ground truth):**
- PDF preflight `check_base_requirements.py --input pdf` → READY (PyMuPDF
  1.27.2.3). The deck is **5 pages** (the harness's "551 pages" estimate was
  wrong); page 2 = the CARD page.
- Picked one component: **Level 1–5 progression cards**, region verified by
  rendering crops with PyMuPDF (region pt `[450,415,w1840,h525]`).
- Built an extraction-request JSON; `scaffold_extraction.py --request` →
  staging item `sun.component.level-progression-cards` with well-formed
  `mapping.json` (fingerprints, candidate id). ✅
- `convert_pdf_source.py --page 2` → `source-page.svg` + reference PNG;
  `extract_editable_text_slots.py` → 57 slots / 21 source text elements. ✅
- `crop_svg_region.py` → ran the rest of the pipeline
  (`externalize_svg_images`, `optimize_svg`, `apply_text_contract`).

**Two real defects found (not yet fixed):**

1. **Unit bug in `crop_svg_region.py` — silent garbage crop, no gate.**
   The extraction-request **schema allows `unit: ["px","pt","in","normalized"]`**
   and `scaffold_extraction.py` writes `source.region` verbatim, but
   `crop_svg_region.py`'s `region_fraction()` **assumes the region is normalized
   0–1** (only special-cases percent) and ignores `unit`. A schema-valid `pt`
   region (450/415/1840/525) was multiplied by page size → viewBox
   `5.40745e6 × 1.37716e6` (≈2900× too large), **all 57 slots dropped**, and the
   step still exited 0 (`status: cropped`). Re-running with a **normalized**
   region (0.15312/0.15821/0.6261/0.20014) produced the correct
   `crop_window [449.99,415.01,1840,525]`, viewBox `0 0 1840 525`, 16 slots kept
   / 41 dropped, and a geometrically-correct render (5 cards, icons + arrow
   buttons in place). → The pipeline only works with normalized regions; the
   `pt`/`px`/`in` units the schema advertises are unhandled and fail silently.

2. **`crop_svg_region.py` vs `validate_text_slots.py` ordering conflict — a
   cropped component can never pass validation.** The SKILL pipeline runs crop
   *before* `validate_text_slots.py`. Crop drops out-of-region slots, but
   `validate_text_slots.py` parses the **full-page** `evidence/source-with-text.svg`
   (21 text elements) and requires **every** source character to map to a slot.
   After crop only in-region text is covered, so validation **exits 1** with ~41
   "Unmapped source text characters" errors for every out-of-region string.
   Crop never rewrites/crops the evidence source SVG, so this fails structurally
   for any component-level PDF item. Consistent with there being **0 published
   items carrying a `region_crop` marker** — this component path has apparently
   never been driven to completion before. (`publish_extraction.py` only checks
   the `region_crop` marker exists; it does not itself run
   `validate_text_slots.py`, so the QA failure wouldn't block a publish — but the
   documented pipeline's own final gate fails.)

**Verification:** all command outputs above are real (PyMuPDF, the pipeline
scripts). The geometric crop was visually confirmed against the source crop.

**Committed:** no.

---

## 9. Fix both defects found in task 8

**Request:** "sửa cả 2" — fix both the unit bug and the crop-vs-validate conflict.

**Fix 1 — `crop_svg_region.py` now honors `region.unit`.**
- Rewrote `region_fraction()` to take `(region, page_w, page_h)` and convert per
  unit: `normalized`/`fraction` (0-1), `percent`/`%` (÷100), `pt`/`px`
  (÷ page extent), `in` (×72→pt, ÷ page extent). Any other unit now raises
  `SystemExit` (fail loud instead of silently mis-scaling).
- Reordered `crop_item()` so the viewBox (page extent) is parsed *before*
  resolving the region, since absolute units need it.

**Fix 2 — cropped-out source text no longer fails validation.**
- `crop_svg_region.py` now records every dropped slot's source-text refs into
  `source.region_crop.dropped_source_refs` (text intentionally outside the
  component region).
- `validate_text_slots.py` reads that list and excludes those characters from
  the full-page coverage requirement. In-region text is still fully required.

**Verification (real runs):**
- Fresh `pt`-unit extraction of the same Level 1–5 cards → crop_window
  `[450,415,1840,525]`, viewBox `0 0 1840 525`, 16 slots kept (identical to the
  normalized run). ✅ Fix 1.
- Full pipeline + `validate_text_slots.py` on that item → **`valid`, exit 0**
  (was exit 1 with 41 unmapped-text errors); 41 dropped refs recorded, 16 kept. ✅ Fix 2.
- Added two regression tests to `test_gates.py`:
  `test_crop_region_honors_absolute_units` (pt == normalized crop; unknown unit
  raises) and `test_validate_excludes_cropped_out_source_text` (passes with the
  marker, fails without). Suite now **18/18**.

Only caller of `region_fraction` is `crop_item` (updated). `outputs/` is
gitignored; left one verified test batch
`outputs/component-extractions/guideline-card-ptfix-2026-06-24/` as evidence.

**Committed:** no.

---

## 10. Complete physical asset inventory of slide-system/library/

**Request:** thorough inventory of all physical assets in slide-system/library/
cross-referenced against slide-system/registries/visual-library.json, with
orphaned files and mismatches identified.

**Actions:**
- Listed all 598 files in slide-system/library/ recursively
- Read all 79 items from slide-system/registries/visual-library.json (79 total)
- Verified .agents/skills/sun-studio-design-system/assets/system/ contains
  canonical assets: logo.png, 9 Dio character poses, 14 Proxima-Nova fonts,
  colors_and_type.css
- Cross-referenced all 465 unique registry paths against disk
- Ran comprehensive analysis via Python script to identify mismatches

**Result:**
- **598 files** on disk in slide-system/library/
- **79 registry items** in visual-library.json (schema_version 1, all status: published)
- **465 unique paths** referenced in registry — all 465 exist on disk (100% match)
- **0 missing paths** (registry references non-existent files)
- **213 orphaned files** on disk but not in registry:
  - 13 README.md placeholder files (directory docs, not assets)
  - 56 preview/thumbnail.png files (generated slide snapshots, not tracked in registry paths)
  - 24 evidence/notes.md files (alongside tracked external-images.json)
  - 120 template asset images (PNGs/JPGs in sun-presentation and
    sun-studio-performance-review-2025)
- **Canonical design system assets**: 22 files under
  .agents/skills/sun-studio-design-system/assets/system/ (logo, dio, fonts, CSS)
- **6 template decks found**: goal-setting-2026, interview-workshop-sunriser,
  salary-benefits-2026, sun-presentation, sun-studio-performance-review-2025
- **1 component**: diagrams/guideline-board-layouts

**Verification:** inventory complete, all 79 registry items listed with
id/type/status/paths, all orphans classified by category.

**Committed:** no.

---

## Task: Remove dangling references to deleted icon-library & shape-variants assets

**Request:** User deleted `guideline-icon-library` and `guideline-shape-variants`
from the catalog preview HTML; local files still referenced them. User chose
"remove all references" (not re-extract).

**Actions:**
- Confirmed both assets absent on disk (`library/assets/`, `library/styles/` =
  README-only) and in both registries (0 matches); no scripts reference them.
- Removed references from 5 files:
  - `slide-system/rules/icon-selection.md` — dropped brand-icon tier (now 4-tier
    ladder) + removed "Where to Find Brand Icons".
  - `slide-system/rules/component-composition.md` — removed shape-variants section
    + its layer-order entry (now 4 layers).
  - `.agents/skills/slide-generator/SKILL.md` — reworded prohibition #1 + removed
    shapes/icon-library composition bullets.
  - `slide-system/workflows/build-html-deck.md` — icon source reworded.
  - `docs/slide-generator-token-efficiency-plan.md` — marked "P2 — Icon library"
    OBSOLETE.
- Kept `extraction-history.json` (audit log) and gitignored request JSON untouched.

**Verification:** `git grep` of tracked source/docs (excl. history/audit/log) =
0 remaining references. No scripts referenced the assets, so no gate behavior changed.

**Committed:** no.

---

## Task: Fix scaffold_extraction.py false-duplicate bug

**Request:** User forwarded a bug found in another agent's testing —
`sun.component.level-progression-cards` was hidden from the catalog because
scaffold marked it "duplicate".

**Actions:**
- Root cause: `scaffold_extraction.py:120` set `duplicate` from `exact OR
  registry_match`, where `exact` = any prior history attempt with a matching
  region hash regardless of publication. A never-published prior attempt forced
  `duplicate` → no `artifact/` folder + hidden by catalog (shows staging/qa only).
- Fix: drive `duplicate` off `registry_match` only (registry = sole publication
  authority); still reuse `exact.stable_id` for stable identity. Added explanatory
  comment. Also tightened `duplicate_of` to `candidate_id if registry_match else None`.

**Verification:** `py_compile` OK; `exact` still used for stable_id (no dead var);
no tests assert old behavior (test_gates targets `scaffold_slide_from_component`).

**Committed:** no.

---

## Task: Verify & correct LOG-2026-06-24-zombie-audit.md

**Request:** User asked to check the zombie-audit log and fix problems.

**Actions:**
- Verified claims vs live state: library counts (78 items, 76 tpl/1 asset/1 char,
  all published) ✓; 250 attempts / 174 unique ✓; 3 zombies absent from
  registry+disk ✓; `aliases.json` empty ✓; 5 empty library subdirs ✓.
- Corrected line 24: the "139/29/6" figures are deduped per-unique-id final status
  (=174), not attempt counts; raw attempt status is 145 published / 96 staging /
  9 duplicate (=250). Noted 96→29 staging collapse = re-scaffold duplication pattern.
- Corrected line 53: "0 broken references in active code" was FALSE at audit time —
  icon-library + shape-variants were live in 5 files (also flagged by DOCS-SKILLS-
  AUDIT); now true post-cleanup. Third zombie (card-variants) only ever in history.
- Determined the 3 ghost-`published` history records are append-only audit artifacts
  (shape-variants pruned by commit 0981cbc5; icon-library never committed to
  registry). `extraction-history.json` has no schema/validator; `validate_registry.py`
  passes (78 items, 0 broken). Did NOT rewrite history — rewriting point-in-time
  events would reduce audit accuracy, not improve it.

**Verification:** `validate_registry.py` exit 0; `git grep` confirms 0 active-code
zombie references remain.

**Committed:** no.

---

## 11. Zombie component root cause fix + extraction-history reconciliation

**Request:** "tôi cần bạn tìm solution cho phần này" — fix the root cause of
ghost published items in extraction-history and reconcile the registry.

**Root cause analysis:**
- `build_registry.py` had `reconcile_history()` function (line 91) that appends
  corrective `unpublished` records to extraction-history.json when dropping
  dangling entries. BUT it was only called for DANGLING items (in registry but
  folder missing), NOT for items completely absent from the registry.
- 5 items from `guideline-presentation-sun-pages-1-5` extraction batch were
  marked "published" in extraction-history but had NO physical files and NO
  visual-library entries. These were "ghost published" zombies.
- Additionally, 54 old-style IDs (e.g., `sun.cover.cover-hero`,
  `sun.chart.mix-chart-layout`) were "published" in history but mapped to
  different canonical IDs in visual-library (e.g., `sun.sun-presentation.01-cover`).

**Fix applied to `build_registry.py`:**
- Added call to `reconcile_history(ghosts)` in the `--write` branch (after the
  existing dangling reconciliation) to also correct ghost-published items that
  are completely absent from the registry.
- Ghost detection was already implemented in `history_published_not_in_registry()`
  (line 73-88) but only used for informational printing in `--check` mode.

**Reconciliation results:**
- Ran `build_registry.py --write` → reconciled 63 history records to `unpublished`
- 5 genuine ghosts (guideline-icon-library, guideline-shape-variants,
  guideline-card-variants, guideline-board-layouts, guideline-image-layouts)
- 58 old-style IDs that were published under different canonical names
- extraction-history.json now has: 145 published, 97 staging, 9 duplicate,
  63 unpublished (total 314 records)

> ⚠️ **SUPERSEDED (see §13).** The "5 ghosts / 58 renames" counts are WRONG —
> fingerprint verification shows **10 ghosts / 53 renames**. The tombstone
> approach was also replaced: §13 PURGES the 63 dead ids outright (no
> `unpublished` records, no aliases).

**Verification:**
- `build_registry.py --check` → "clean: 0 dangling, 0 orphan, 78 valid items"
- `test_gates.py` → 17/18 passed (1 pre-existing failure unrelated to this fix)
- Zero remaining ghost published items (published in history, not in registry)

**Decision:** User chose to skip re-extracting the 5 guideline items.
Source PDF (`input/GUIDLINE_PRESENTATION_SUN.pdf`) still exists if needed later.

**Committed:** no.

---

## 12. End-to-end test of component extraction workflow on GUIDLINE_PRESENTATION_SUN.pdf

**Request:** test workflow skill component extraction trên file
`input/GUIDLINE_PRESENTATION_SUN.pdf` xem đã hoạt động đúng chưa.

**Actions:**
- Đọc skill `component-extractor`, kiểm tra preflight (READY, PyMuPDF 1.27.2.3)
- Tạo extraction-request JSON cho Level 1–5 cards (page 2, region pt-unit
  `[450,415,1840,525]`)
- Chạy đầy đủ pipeline:
  1. `scaffold_extraction.py --request` → staging item `level-progression-cards`
  2. `convert_pdf_source.py --page 2` → source-page.svg + reference.png
  3. `extract_editable_text_slots.py` → 57 slots, 21 source text elements
  4. `crop_svg_region.py` → crop_window `[450,415,1840,525]`, 16 kept / 41 dropped
  5. `externalize_svg_images.py` + `optimize_svg.py` + `apply_text_contract.py`
  6. `validate_text_slots.py` → **valid** (exit 0)

**Two fixes verified:**
1. **Fix #1 (pt unit):** `crop_svg_region.py` correctly converts pt-unit region.
   Before fix: viewBox ~5.4M × 1.4M (2900× too large), 0 slots kept.
   After fix: crop_window `[450,415,1840,525]`, 16 slots kept, geometrically
   correct render.
2. **Fix #2 (crop-vs-validate):** `validate_text_slots.py` excludes cropped-out
   source text via `dropped_source_refs`. Before fix: exit 1 with 41 unmapped
   errors. After fix: exit 0, valid.

**Catalog bug found and fixed:**
- Item appeared as `status: "duplicate"` in catalog → hidden from Draft tab
- Root cause: `scaffold_extraction.py` HEAD code `if exact or registry_match`
  triggered "duplicate" from history attempts, not just registry matches
- Fix (working tree): `if registry_match:` only — registry is sole publication
  authority
- After fix: `status: staging`, `publish_readiness: True`, item visible in
  catalog Draft tab

**Verification:**
- `test_gates.py`: 18/18 ✅
- `build_registry.py --check`: clean (78 items) ✅
- Catalog: 79 items (78 published + 1 staging) ✅
- `validate_text_slots.py`: valid ✅

**Files created:**
- `outputs/component-extractions/level-cards-pt-test-2026-06-24/` (test batch)
- `outputs/component-extractions/_requests/level-cards-pt-test.request.json`

**Committed:** no.

---

## 13. Hardening around the zombie fix (publish guard, drift note, test repoint)

**Request:** "commit it and create solution for this critical bug" — complete and
commit the history↔registry drift solution (continuation of §11).

**Actions (mine, complementing §11's `build_registry.py` reconcile-all-ghosts):**
- `build_registry.py` — added `history_published_not_in_registry()` + a non-gating
  drift note in `--check` so the divergence is visible, not silent (§11 then wired
  the ghost set into `--write`).
- `publish_extraction.py` — defense in depth: after `copytree`, abort before
  writing the registry/history if the destination folder ended up empty, so a
  failed publish can never create a new ghost-published entry.
- `test_gates.py` — `test_read_text_slots_projection` was hardcoded to the pruned
  `guideline-board-layouts` folder (the 17/18 failure noted in §11). Repointed it
  to resolve the slots path **from the registry** (`ITEM_WITH_SLOTS` = a live item),
  so a pruned/renamed item can never re-break it. Suite now **18/18**.
- Note on §11's approach: marking all 63 not-in-registry ids `unpublished` is
  functionally fine (history is unvalidated metadata nothing reads for pipeline
  decisions) and enforces the invariant "history `published` ⇒ registry member."
  The 58 renamed-id records carry the dangling `reason` text, which is imprecise
  for renames; a precise follow-up would populate `aliases.json` (old→canonical)
  via `region_identity_sha256` matching instead. Left for the user to decide.

**Verification:** `test_gates.py` 18/18; `build_registry.py --check` clean
(0 dangling, 0 orphan, 78 valid); `validate_registry.py` 78 items 0 broken;
all touched scripts `py_compile` OK.

**Committed:** see commits below.

---

## §13 — Drop `compatibility` field + purge data sources (2026-06-24)

**Request:** (1) Remove the per-item `compatibility` data (html/pptx/pdf/canva) —
unnecessary noise. (2) Unify the 3 data sources by deleting dead records and
aliases (no tombstones, no new status vocab). User confirmed export scripts/skills
stay. Two scopes are logically independent but share 2 files, so done sequentially.

### Scope 1 — Remove `compatibility` field (commit ec20b6ff)
- Stripped the `compatibility` block from `visual-library.json` +
  `visual-library-compact.json` (78 items each) via `_common.write_json`.
- Removed it from 6 code sites: `validate_registry.py` (validation loop +
  `VALID_SUPPORT`), `score_visual_items.py` (export-eligibility check; the
  `export_compatibility` scoring dimension now always passes), `build_registry.py`
  (compact projection keys + docstring), `publish_extraction.py`,
  `scaffold_extraction.py`, `build_component_catalog.py`, `test_gates.py` fixture.
- **Verify:** `test_gates.py` 18/18; `validate_registry.py` clean;
  `build_registry.py --check` clean.

### Scope 2 — Purge dead data (this entry; commit below)
- **Classification (fingerprint-verified):** of 63 dead ids → **53 renames /
  10 ghosts** (corrects §11's "5 ghosts / 58 renames").
- **Purged** all attempts of the 63 dead ids from `extraction-history.json`:
  **195 attempts removed, 119 remain** (76 published, 30 staging, 5 duplicate;
  every published id now in the registry; 0 zombies, 0 tombstones).
- **Deleted** `aliases.json` (empty; old ids unreferenced) + its only consumer
  in `validate_registry.py`; scrubbed doc refs (`naming-versioning.md`,
  `flows/slide-generator-workflow.md`).
- **Rewrote `build_registry.py`:** `reconcile_history` (tombstone appender) →
  `purge_history`; `history_published_not_in_registry` → `history_zombie_ids`
  (ever-published, not latest); `--check` now GATES on zombies (exit 1), `--write`
  purges them.
- **Verify:** `build_registry.py --check` → `clean: 0 dangling, 0 orphan, 0 zombie,
  78 valid items` (exit 0). Negative test: inject published-not-in-registry →
  `--check` exit 1 → `--write` purges → `--check` exit 0. `test_gates.py` 18/18.

**Plan files:** `tasks/plan.md`, `tasks/todo.md` (two-scope plan; the earlier
"remove HTML/PPTX export scripts/skills" idea was a misread and cancelled).

**Committed:** see commits below.

### §13b — build_registry canonical JSON (commit 234e846a)
- Follow-up: `build_registry.py` was the only writer using raw
  `json.dumps(ensure_ascii=False)` for the registry/compact/history files, while
  `publish_extraction.py` + `scaffold_extraction.py` use `_common.write_json`
  (ensure_ascii=True). Harmless now (files pure ASCII, unicode already
  `\u`-escaped) but a future Vietnamese string would reflow the whole file.
- Routed all three writes through `write_json`; dropped the unused `json` import.
- **Verify:** `--write` produces zero diff; `test_gates.py` 18/18; `--check` clean.

### Commit summary (this session)
- `ec20b6ff` drop per-item compatibility field
- `a64e43d5` purge zombie history + drop aliases
- `db37667f` correct zombie counts in logs + add plan files
- `49a875c2` restore input/*.extraction-request.json (swept in by mistake)
- `234e846a` build_registry writes canonical JSON
- All local, not yet pushed.

### §14 — Catalog draft-delete sync bugs (found via browser test)

**Request:** delete a draft item via the catalog UI (http://127.0.0.1:8799/
slide-system/catalog/) and verify disk/data/history stayed in sync; if not, find
the cause and fix #1, #2.

**Browser test:** deleted draft `sun.component.level-progression-cards` (typed
DELETE to confirm). API `POST /api/delete` → 200, UI Draft 1→0. But verification
found desync:
- **#1 (disk):** the id had 2 extraction folders on disk; delete removed only 1,
  leaving `outputs/.../guideline-card-ptfix-2026-06-24/.../level-progression-cards`
  orphaned. Cause: `catalog_server.py find_staging()` returns the FIRST match only.
- **#2 (history):** 5 extraction-history records (3 staging + 2 duplicate) for the
  id survived. Cause: the draft branch of `action_delete` only `rmtree`+regen,
  never touched extraction-history; no gate catches staging/duplicate orphans.
- (#3, not fixed here: catalog.js/index.html still reference the removed
  `compatibility` field — a Scope-1 front-end leftover.)

**Fix (catalog_server.py):**
- Added `find_all_staging(item_id)` → returns ALL matching folders; draft delete
  now loops and `prune_staging`s every one (rmtree + prune emptied items/batch).
- Added `purge_draft_history(item_id)` → removes every NON-published history
  record for the id (keeps a `published` record if the id was also promoted).
- Draft delete returns `removed: [..]` + `history_purged: N`.

**Verify (new code, in-process):** re-ran `action_delete` on the leftover →
`{removed: [guideline-card-ptfix...], history_purged: 5}`; AFTER: 0 disk folders,
0 history records, catalog staging 0. history 119→114. `test_gates.py` 18/18,
`validate_registry.py` clean, `build_registry --check` clean.

> NOTE: the running catalog server still has the old code in memory — **restart it**
> (`python3 slide-system/catalog/catalog_server.py`) for the fix to apply live.

### §15 — Catalog front-end: drop `compatibility` UI (#3) + server restart + no-store

**Request:** restart the catalog server (user couldn't), then fix #3 (front-end
still referenced the removed `compatibility` field).

- **Server restart:** killed the old in-memory instance(s) and relaunched
  `catalog_server.py` so #1/#2 are live.
- **#3 (front-end):** removed every `compatibility` reference:
  - `catalog.js`: `compatFilter`/`panelCompat` DOM refs, `compCompatMatches` +
    its filter call, `compRenderCompatPanel` + `compCompatIcon`, and all filter
    arrays/clear/listeners.
  - `index.html`: the "Filter by compatibility" `<select>`, the "Compatibility"
    sub-tab, and `#panel-compat`.
  - `catalog.css`: `.compat-grid`/`.compat-cell`/`.compat-*` rules + responsive rule.
- **Caching bug found & fixed:** `SimpleHTTPRequestHandler` sent no cache headers,
  so the browser kept serving the OLD `catalog.js` against the NEW HTML
  (`#compat-filter` null → `addEventListener` TypeError). Added
  `Cache-Control: no-store` to the server's `end_headers`, and version-bumped the
  asset refs (`catalog.css?v=2`, `catalog.js?v=2`) to flush the stale entry.

**Verify (live browser):** reloaded → 0 console errors; only "Filter by type" +
"Filter by brand" remain; item detail shows only Preview/Info tabs; counts load
(Components 2, Templates 5). All three desyncs (#1 disk, #2 history, #3 UI) resolved.

### §16 — Housekeeping: close out plan + relocate stray log

- Marked `tasks/plan.md` + `tasks/todo.md` DONE (both scopes + catalog sync), with
  commit refs per task.
- Moved `docs/LOG-2026-06-24-zombie-audit.md` → `docs/logs/` (AGENTS.md rule: all
  logs live under `docs/logs/`; it was the only stray). `docs/flows/catalog-publish.md`
  is a flow doc, not a log — left in place. References to the file are prose
  (bare filename), so the move broke no links.
