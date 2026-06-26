# Session Log — 2026-06-23 → 2026-06-24

Branch: `feat/harness-enforcement-and-component-recognition`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` → "Task Logging").

---

## 1 — Document the `crop_svg_region.py` component-cropping fix

**Request:** Update docs to reflect the crop step done in the prior session (the
PDF→SVG path emits a whole page, so a component-level item must be cropped to its
`source.region`).
**Actions:**
- `docs/flows/skill-flows.md` — added crop step `b2` to pipeline `[3]`, a publish-gate note to `[6]`, a hard rule, bumped the date.
- `slide-system/README.md` — added the `crop_svg_region.py` command block; explained it rewrites `visual.svg`'s viewBox + re-normalizes `text-slots.json`, is a no-op for full-page regions, idempotent (marker `source.region_crop`), and that `publish_extraction.py` blocks a component-level item missing this marker.
- `docs/flows/slide-generator-workflow.md` — added a `crop_svg_region.py` row; marked `publish_extraction.py` as gating the component crop.
- `.agents/skills/component-extractor/SKILL.md` + `slide-system/workflows/extract-components.md` — added the crop step (SKILL step 3 / workflow step 8b).
**Result:** Docs now describe the crop step consistently.
**State:** Committed in entry 8's thematic batch.

---

## 2 — Prune slide-dupe components + self-healing registry tooling

**Request:** Library had too many large full-page "components"; user chose "Chỉ xóa slide-dupe" (delete only slide-duplicates).
**Actions:**
- Deleted **47 slide-dupe full-page components** (registry 127 → 80 items, ~55.7 MB freed). A non-template item is a slide-dupe when its (source file, slide) matches a published template's. Kept genuinely reusable items (`guideline-shape-variants`, `guideline-board-layouts`, logo, Dio).
- Deleted **15 junk orphan folders** (a `visual.svg` but no registry entry), incl. `sun.component.long-term-benefits`, `sun.component.salary-benefits-thanks`.
- Registered the orphaned-but-used `guideline-icon-library`.
- NEW `slide-system/scripts/build_registry.py` — reconcile + projection tool: `--check` exits 1 on registry↔disk drift; `--write` drops dangling entries + rebuilds `visual-library-compact.json`, reports (never deletes) orphans; `COMPACT_KEYS` defines the scorer projection.
- `publish_extraction.py` — imports `COMPACT_KEYS`, regenerates compact on every publish.
- `catalog_server.py` — added `regen_compact()` (runs `build_registry --write`) in the published-delete branch.
- `test_gates.py` — repointed a test off a deleted item; added `test_build_registry_projection_and_compact_keys` + `test_build_registry_live_is_clean`.
**Result:** Suite 16/16. Architecture note: published folders don't retain `mapping.json`, so `visual-library.json` is the metadata authority — `build_registry.py` reconciles, never rebuilds.
**State:** Committed in entry 8's thematic batch.

---

## 3 — Diagnose "Request failed (405)" on catalog Delete + serving guidance

**Request:** Investigate the catalog Delete button error and document correct serving.
**Actions:**
- Root cause: Publish/Delete POST to origin-relative `/api/publish`,`/api/delete`, only implemented by `catalog_server.py` (:8799). Wrong origin breaks it: `http.server` → 501; VS Code Live Server (:5500) → **405** (what the user hit); `catalog_server.py` → 404 only for unknown endpoints.
- Killed Live Server on :5500 (PID 98032); confirmed control server up on :8799.
- Added serving guidance to `component-extractor/SKILL.md` (step 5), `workflows/extract-components.md` (step 12), `slide-system/README.md` (501/405 trap blockquote), `docs/flows/catalog-publish.md` (hard rules).
**Result:** Documented; `deletable` is true only for `slide-system/library/` artifacts (brand assets 403-guarded).
**State:** Committed in entry 8's thematic batch.

---

## 4 — Translate all Vietnamese docs to English

**Request:** Faithfully translate VN docs (no rewrites, no invented content), preserving code/paths/commands/IDs/structure.
**Actions:** Translated 9 files: `docs/how-to-use.md`, `docs/images/README.md`, `docs/flows/{skill-flows,catalog-publish,component-selection-flow,template-picker-flows,3layer-export}.md`, `slide-system/docs/PLAN-component-fidelity.md`, `slide-system/workflows/save-as-template.md`. Normalized markers to `[KEEP]`/`[FIX]`/`[NEW]`. Left the vendored `.agents/skills/ppt-master/` tree untouched (false-positive matches).
**Result:** Final scan = **0 Vietnamese remaining** across all 9 files.
**State:** Committed in entry 8's thematic batch.

---

## 5 — Add a mandatory task-logging rule to the repo

**Request:** "update your rule in this repo, log detail any task that u did."
**Actions:**
- `AGENTS.md` — added "## Task Logging (required)": where (`docs/logs/SESSION-LOG-<YYYY-MM-DD>.md`, append-only, one/day), when (as each task completes), what (Request→Actions→Result+verification→State), faithfulness rule.
- `.claude/CLAUDE.md` — added a pointer so Claude Code auto-loads the rule.
**Result:** Future sessions are instructed to keep a per-task log.
**State:** Committed in entry 8's thematic batch.

> _Mid-session snapshot (after entry 5, before any commit):_ Modified 19 tracked
> files; deleted 479 files (47 slide-dupes + 15 orphan folders, multi-file each);
> new untracked `build_registry.py`, `crop_svg_region.py`,
> `visual-library-compact.json`, `slide-system/docs/`, config files. Verification at
> that point: `test_gates.py` 16/16; `build_registry --check` clean; VN scan 0.

---

## 6 — Read-only audit: simulate component-extractor & slide-generator workflows

**Request:** Ground-truth walkthrough of both skills' workflows (docs are stale). Analysis only.
**Actions:** Read both SKILL.md files and the real implementation of every pipeline + gate script; recorded exact CLI args, files read/written, JSON shapes, and gate (exit≠0) conditions. Confirmed `extract-readiness.json` = ready; PyMuPDF available; LibreOffice (PPTX) missing → blocks PPTX-sourced jobs only.
**Result:** Delivered two workflow simulations in chat. Flagged doc-vs-code gaps (not yet fixed): `scaffold_extraction.py --request` undocumented in SKILL; `_BANNED_ID` regex narrower than prose; `optimize_svg.py --max-dimension` default 1920 vs docstring 2560; slide-gen export step omits required `--slides`/`--out-dir`; `cleanup_run.py` deletes `export-result.json`; `--brand-pack` unused; T3 fidelity validator unwired; `--prefer-set` +5 bonus can flip a decision, undocumented.
**State:** No changes (read-only).

---

## 7 — Verify another agent's doc-vs-code report + fix items 1–4

**Request:** "check lại report của agent khác" then "fix 1 to 4".
**Actions:** Confirmed all 6 claims true (nuances: #1 README already documents `--request`; #5 publish path IS server-enforced, only upstream is honor-system). Fixed 1–4:
1. `component-extractor/SKILL.md` — documented the mandatory `--request <file>` interface + schema/boilerplate refs.
2. `scaffold_extraction.py` — tightened `_BANNED_ID` (blocks numeric `42`, positional `top-left`/`center`; allows `left-rail`); synced SKILL prose; tested block/allow.
3. `optimize_svg.py` — docstring default 2560 → 1920.
4. T3 `validate_component_fidelity.py` — wired into build path in `--warn` (build-html-deck.md gate, slide-generator SKILL step 11, PLAN-component-fidelity.md).
- Regression fixed: `guideline-board-layouts` had been over-deleted in entry 2; restored folder + registry entry from HEAD; ran `build_registry --write`.
**Result:** `test_gates.py` 16/16; `--check` clean (79 items). Report items 5–6 are accurate observations, left as-is.
**State:** Committed in entry 8's thematic batch.

---

## 8 — Move logs to `docs/logs/`, classify the diff, and commit

**Request:** "phân loại file trong git diff và commit … log phải bỏ trong folder log."
**Actions:**
- Moved the log to `docs/logs/SESSION-LOG-2026-06-24.md`; updated the Task-Logging rule (AGENTS.md + CLAUDE.md) to require all logs under `docs/logs/`.
- Flagged `backup.cswap` as a sensitive wallet backup (`encrypted: false`); did NOT commit; added `*.cswap` + local `.claude` state to `.gitignore`.
- Classified the diff into **7 thematic commits**: (1) codegraph/tooling config; (2) crop + extraction/catalog docs; (3) prune slide-dupes + registry (472 deletions); (4) VN→EN docs; (5) naming gate / optimize_svg / T3; (6) token-efficiency plan; (7) task-logging rule + this log.
**Result:** Working tree clean; `test_gates.py` 16/16; `--check` clean (79 items).
**State:** Committed (7 commits; this entry folded into commit 7 via amend).

---

## 9 — E2E test of `component-extractor` on `input/GUIDLINE_PRESENTATION_SUN.pdf`

**Request:** Run the skill end-to-end on the guideline PDF and verify it matches intent.
**Actions:** Preflight READY (PyMuPDF 1.27.2.3); deck is **5 pages** (harness "551" was wrong), page 2 = CARD page. Picked Level 1–5 progression cards (region pt `[450,415,1840,525]`). `scaffold_extraction.py --request` → staging `sun.component.level-progression-cards`; `convert_pdf_source.py --page 2`; `extract_editable_text_slots.py` → 57 slots/21 text els; ran crop + rest of pipeline.
**Result:** Found **2 real defects (not yet fixed):**
1. **Unit bug in `crop_svg_region.py`:** schema allows `unit: px/pt/in/normalized` but `region_fraction()` assumed normalized 0–1. A valid `pt` region → viewBox ~2900× too large, all 57 slots dropped, still exit 0. Normalized region produced the correct crop.
2. **crop vs `validate_text_slots.py` ordering:** crop runs before validation; validation parses the full-page evidence SVG and requires every char mapped, so cropped-out text → exit 1 (~41 errors). Structural for any component-level PDF item (0 published items carry `region_crop`).
**State:** Not committed (test/diagnosis).

---

## 10 — Fix both defects from entry 9

**Request:** "sửa cả 2."
**Actions:**
- **Fix 1:** rewrote `region_fraction()` to take `(region, page_w, page_h)` and convert per unit (normalized/fraction, percent, pt/px, in→pt); unknown unit raises `SystemExit`. Reordered `crop_item()` to parse viewBox before resolving the region.
- **Fix 2:** `crop_svg_region.py` records dropped slots' source refs into `source.region_crop.dropped_source_refs`; `validate_text_slots.py` excludes those from the coverage requirement (in-region text still required).
- Added regression tests `test_crop_region_honors_absolute_units` + `test_validate_excludes_cropped_out_source_text`.
**Result:** pt-unit run == normalized crop; full pipeline + validate → **valid, exit 0** (41 dropped recorded, 16 kept). Suite **18/18**.
**State:** Not committed.

---

## 11 — Physical asset inventory of `slide-system/library/`

**Request:** Thorough inventory cross-referenced against `visual-library.json`, with orphans/mismatches identified.
**Actions:** Listed 598 files; read 79 registry items; verified canonical design-system assets; cross-referenced 465 unique registry paths against disk via a Python script.
**Result:** 598 files; 79 items (all published); 465 unique paths all exist (100%, 0 missing); 213 orphans on disk (13 README, 56 preview/thumbnail, 24 evidence/notes, 120 template asset images); 22 canonical files under `.agents/.../system/`; 6 template decks; 1 component (guideline-board-layouts).
**State:** Not committed (inventory only).

---

## 12 — Zombie component audit (full resource check)

**Request:** Full check of all resources/components/references to ensure no zombie components exist.
**Actions:** Three sub-checks (library inventory, repo-wide references, history + outputs); verified with grep + Python; checked `aliases.json`, `visual-library.json`, `extraction-history.json`.
**Result (findings):**
- Visual library: 78 items, all valid + present (76 templates, 1 asset, 1 character).
- Extraction history: 250 attempts / 174 unique. Per-unique-id final status (dedup) 139 published / 29 staging / 6 duplicate; raw attempt-level 145/96/9. The 96→29 staging gap = re-scaffold duplication.
- **Zombies first spotted (3, no files):** `guideline-icon-library`, `guideline-shape-variants`, `guideline-card-variants`. _(Under-counted — see corrected total in entry 19: 10 ghosts / 63 dead ids.)_
- ID-mapping gap: 63 ids "published" in history but absent from the registry (later verified 53 renames + 10 ghosts).
- 29 staging never promoted; 6 duplicate dead-ends; 5 empty library subdirs (README-only).
- Reference integrity correction: original "0 broken references" was FALSE — icon-library + shape-variants were live in 5 files (fixed in entry 13); card-variants only ever in history metadata.
**Result:** No zombies that break functionality; they exist only in history metadata. Root cause + fix tracked in entries 15, 16, 18, 19.
**State:** Audit only (fixes in later entries).

---

## 13 — Remove dangling references to deleted icon-library & shape-variants

**Request:** User deleted both assets from the catalog preview HTML but local files still referenced them; chose "remove all references" (not re-extract).
**Actions:** Confirmed both absent on disk + in both registries; removed references from 5 files: `rules/icon-selection.md` (4-tier ladder), `rules/component-composition.md` (4 layers), `slide-generator/SKILL.md`, `workflows/build-html-deck.md`, `docs/slide-generator-token-efficiency-plan.md` (P2 marked OBSOLETE). Left history + gitignored request JSON untouched.
**Result:** `git grep` of tracked source/docs = 0 remaining references; no gate behavior changed.
**State:** Committed (7831d328).

---

## 14 — Fix `scaffold_extraction.py` false-duplicate bug

**Request:** Forwarded bug — `sun.component.level-progression-cards` hidden from the catalog because scaffold marked it "duplicate".
**Actions:** Root cause: `scaffold_extraction.py` set `duplicate` from `exact OR registry_match`, where `exact` = any prior history attempt with a matching region hash regardless of publication → a never-published prior attempt forced `duplicate` (no `artifact/`, hidden). Fix: drive `duplicate` off `registry_match` only (registry = sole publication authority); still reuse `exact.stable_id`; tightened `duplicate_of`.
**Result:** `py_compile` OK; no test asserted old behavior.
**State:** Committed (43dd659f).

---

## 15 — Verify & correct the zombie audit (entry 12)

**Request:** Check the zombie-audit findings and fix problems.
**Actions:** Verified counts vs live state. Corrected the deduped-vs-attempt status figures; corrected the false "0 broken references" claim (5 files were live at audit time). Determined the 3 ghost-`published` records are append-only artifacts; `extraction-history.json` has no schema/validator; `validate_registry.py` passes. Did NOT rewrite history (rewriting point-in-time events reduces audit accuracy).
**Result:** `validate_registry.py` exit 0; `git grep` confirms 0 active-code zombie references.
**State:** Committed (folded with the audit corrections).

---

## 16 — Zombie root-cause fix + history reconciliation (first attempt — SUPERSEDED)

**Request:** "tôi cần bạn tìm solution cho phần này" — fix ghost-published items and reconcile.
**Actions:** `build_registry.py` had `reconcile_history()` but only called it for DANGLING items, not items fully absent from the registry. Added `reconcile_history(ghosts)` to `--write`. Ran it → appended 63 corrective `unpublished` records.
**Result:** Reported "5 ghosts / 58 renames" and history 145/97/9/63. `--check` clean; `test_gates.py` 17/18 (one unrelated failure).
> ⚠️ **SUPERSEDED by entry 19:** counts were wrong (real: **10 ghosts / 53 renames**, fingerprint-verified) and the tombstone approach was replaced by an outright **purge** (no `unpublished` records, no aliases).
**State:** Committed (43dd659f).

---

## 17 — E2E test of extraction workflow on GUIDLINE_PRESENTATION_SUN.pdf

**Request:** Re-test the component-extraction workflow end-to-end.
**Actions:** Preflight READY; built request for Level 1–5 cards (page 2, pt `[450,415,1840,525]`); ran full pipeline (scaffold → convert → text-slots → crop 16 kept/41 dropped → externalize/optimize/apply → validate).
**Result:** Both entry-10 fixes verified live (pt-unit crop correct; validate exit 0). Also re-confirmed the scaffold false-duplicate fix (entry 14): item now `status: staging`, visible in Draft. `test_gates.py` 18/18; `--check` clean (78); catalog 79 (78+1 staging). Test batches left under gitignored `outputs/`.
**State:** Not committed (test).

---

## 18 — Hardening around the zombie fix (publish guard, drift note, test repoint)

**Request:** "commit it and create solution for this critical bug" — complete/commit the history↔registry drift solution.
**Actions:**
- `build_registry.py` — added `history_published_not_in_registry()` + a non-gating drift note in `--check`.
- `publish_extraction.py` — defense in depth: after `copytree`, abort before writing registry/history if the destination ended up empty.
- `test_gates.py` — repointed `test_read_text_slots_projection` to resolve the slots path from the registry (a live item), fixing the 17/18 failure.
**Result:** `test_gates.py` 18/18; `--check` clean (78); `validate_registry.py` 78 items; `py_compile` OK.
**State:** Committed (43dd659f).

---

## 19 — Drop `compatibility` field + purge data sources (two scopes)

**Request:** (1) Remove per-item `compatibility` (html/pptx/pdf/canva) — noise; (2) unify the 3 data sources by deleting dead records + aliases (no tombstones, no new status vocab). Export scripts/skills KEPT. Done sequentially (shared files).
**Actions:**
- **Scope 1 (ec20b6ff):** stripped `compatibility` from both registries (78 each) via `write_json`; removed from 6 code sites (`validate_registry.py` loop + `VALID_SUPPORT`; `score_visual_items.py` export-eligibility, `export_compatibility` dimension now always passes; `build_registry.py` projection keys + docstring; `publish_extraction.py`; `scaffold_extraction.py`; `build_component_catalog.py`; `test_gates.py` fixture).
- **Scope 2 (a64e43d5, db37667f):** fingerprint-verified classification = **53 renames / 10 ghosts** (corrects entry 16). Purged all attempts of the 63 dead ids from `extraction-history.json` (**195 removed, 119 remain** = 76 published / 30 staging / 5 duplicate). Deleted `aliases.json` (empty) + its only consumer in `validate_registry.py`; scrubbed doc refs. Rewrote `build_registry.py`: `reconcile_history`→`purge_history`, `history_published_not_in_registry`→`history_zombie_ids` (ever-published), `--check` now GATES on zombies (exit 1), `--write` purges.
- **Follow-up (234e846a):** routed `build_registry.py`'s 3 file writes through `write_json` (was the lone `ensure_ascii=False` writer); dropped unused `json` import.
- Restored `input/*.extraction-request.json` swept into ec20b6ff by an already-staged deletion (49a875c2).
**Result:** `build_registry --check` → `clean: 0 dangling, 0 orphan, 0 zombie, 78 valid` (exit 0). Negative test: inject published-not-in-registry → `--check` exit 1 → `--write` purge → exit 0. `test_gates.py` 18/18; `validate_registry.py` clean. `--write` produces zero diff. Plan: `tasks/plan.md`, `tasks/todo.md` (earlier "remove export scripts/skills" idea was a misread, cancelled).
**State:** Committed (ec20b6ff, a64e43d5, db37667f, 234e846a, 49a875c2).

---

## 20 — Catalog draft-delete sync bugs #1 & #2

**Request:** Delete a draft via the catalog UI and verify disk/data/history stay in sync; fix the causes.
**Actions:** Browser-deleted draft `sun.component.level-progression-cards` (typed DELETE; API 200; UI Draft 1→0). Found desync: **#1** the id had 2 extraction folders, delete removed only 1 (cause: `find_staging()` returns first match); **#2** 5 history records survived (cause: draft branch only `rmtree`+regen, never touched history; no gate catches staging/duplicate orphans). Fixed `catalog_server.py`: added `find_all_staging()` (loops + `prune_staging`s every folder) and `purge_draft_history()` (removes non-published records for the id); response now reports `removed: [..]` + `history_purged: N`.
**Result:** Re-ran on the leftover → removed orphan folder + purged 5 records; AFTER: 0 folders, 0 records, catalog staging 0; history 119→114; `test_gates.py` 18/18; `--check` clean.
**State:** Committed (8f19ea23).

---

## 21 — Catalog front-end: drop `compatibility` UI (#3) + restart + no-store

**Request:** Restart the catalog server (user couldn't), then fix #3 (front-end still referenced the removed field).
**Actions:** Killed the old in-memory server instance(s) and relaunched so #1/#2 are live. Removed every `compatibility` reference: `catalog.js` (`compatFilter`/`panelCompat` refs, `compCompatMatches`, `compRenderCompatPanel`+`compCompatIcon`, filter arrays/clear/listeners); `index.html` (filter `<select>`, "Compatibility" sub-tab, `#panel-compat`); `catalog.css` (`.compat-*` rules + responsive). Found & fixed a caching bug: `SimpleHTTPRequestHandler` sent no cache headers → browser served OLD `catalog.js` against NEW HTML (`#compat-filter` null → `addEventListener` TypeError). Added `Cache-Control: no-store` to `end_headers`; version-bumped asset refs (`catalog.css?v=2`, `catalog.js?v=2`).
**Result:** Live browser reload → 0 console errors; only Type/Brand filters; item detail shows only Preview/Info; counts load. All three desyncs (#1 disk, #2 history, #3 UI) resolved.
**State:** Committed (113a12e8).

---

## 22 — Housekeeping: close out the cleanup plan + relocate stray log

**Request:** Mark the done plan complete; check for logs outside the log folder.
**Actions:** Marked `tasks/plan.md` + `tasks/todo.md` DONE with per-task commit refs. `git mv docs/LOG-2026-06-24-zombie-audit.md docs/logs/` (only stray; `docs/flows/catalog-publish.md` is a flow doc, not a log).
**Result:** `docs/logs/` holds only `SESSION-LOG-*` + the moved audit (later folded — see entry 23).
**State:** Committed (0090a561).

---

## 23 — Standardize log format + naming

**Request:** "tôi cần format log chuẩn hơn thay vì log lung tung và đặt tên lung tung."
**Actions:** Defined one standard: file naming `SESSION-LOG-<YYYY-MM-DD>.md` only; per-entry single-integer numbering with uniform **Request / Actions / Result / State** (+ optional **When**). Rewrote this whole file to that standard (renumbered 1–23, removed the mixed `§`/`Task:`/`N.` schemes and stray non-task sections). Folded the standalone `LOG-2026-06-24-zombie-audit.md` into entry 12 and deleted it. Added `docs/logs/_TEMPLATE.md` and an explicit template block in `AGENTS.md` → "Task Logging".
**Result:** `docs/logs/` now contains exactly one log type (`SESSION-LOG-<date>.md`) plus `_TEMPLATE.md`; every entry shares one structure.
**State:** Committed (this entry).

---

## 24 — E2E retest of `component-extractor` on the guideline PDF (intent check)

**Request:** "check log … test workflow skill component extraction … test thử file `input/GUIDLINE_PRESENTATION_SUN.pdf`" — verify the workflow works end-to-end and matches intent.
**Actions:** Preflight `--input pdf` READY (PyMuPDF 1.27.2.3). Rendered all 5 pages: p1 ICON, p2 CARD, p3 OKR circles/hexagons, p4 BOARD table, p5 IMAGE. Located the Level 1-5 cards on p2 via `get_image_info` (5 images x448-2408 y450-926 pt) instead of guessing. Built request `input/GUIDLINE-level-cards.extraction-request.json` (item `level-progression-cards`, region pt `[440,440,1975,495]`). Ran the full pipeline: `scaffold_extraction.py --request` (→ staging, not duplicate); `convert_pdf_source.py --page 2`; `extract_editable_text_slots.py` (57 slots / 21 text els); `crop_svg_region.py`; externalize → flatten (skipped, 0 leading raster) → externalize → optimize → apply_text_contract → `validate_text_slots.py`; `build_text_slot_gallery.py`; `build_component_catalog.py`. Served via running catalog server on :8799.
**Result:** Workflow works and matches intent. Verified: pt-unit crop correct (viewBox `0 0 1975 495`, 16 kept / 41 dropped — entry-10 Fix 1 holds); `validate_text_slots.py` exit 0 (entry-10 Fix 2 holds); item `status: staging` not duplicate (entry-14 fix holds); 0 semantic `<text>` nodes; 16 kept slots = exactly the in-region Level 1-5 labels + descriptions with typography (ProximaNova-ExtrabldIt etc.) preserved; inline-render confirms the visible artifact is the 5 text-free level-card backgrounds; catalog data 79 (78 published + 1 staging draft). **New finding (not fixed):** `crop_svg_region.py` rewrites the viewBox and wraps content in `translate(-440,-440)` but does NOT prune `<image>`/elements wholly outside the crop window — so `externalize_svg_images.py` bundles all 11 page images into `artifact/assets/`, of which 6 are off-canvas (the metric bars + other strips at translated y 1382-1975). Result: **59% of the raster payload (59 KB of 100 KB) is dead/invisible** in every component-level PDF extraction. Output renders correctly (clipped by viewBox); this is an efficiency/cleanliness defect, not a correctness bug.
**State:** Not committed (test/diagnosis). Staging draft + request JSON left under gitignored `outputs/` and `input/`.

---

## 26 — Fix the off-canvas `<image>` defect (crop prune + evidence crop + asset GC)

**Request:** "check plan này và update những phần còn thiếu" then "triển khai fix" — review `tasks/plan-crop-prune-offcanvas-images.md`, correct it, and implement.
**Actions:**
- **Plan review:** verified line refs + image classification against live code (all accurate); corrected the impact table with fingerprint-verified sizes (101 KB total; 41 KB/5 keep, 49 KB/4 prune, 11 KB/2 defs → **48% prunable**, not the stale "59%"); pinned the undecided transform-space question (work in page space, exclude wrapper translate); listed all 4 existing crop tests in the no-regression item.
- **Implement (crop_svg_region.py):** added affine-transform parser (`parse_transform` — translate/scale/matrix only; rotate/skew/junk → None → keep) + `_prune_offcanvas_images` (page-space bbox vs window, fail-safe on missing geometry / defs ancestor / unparseable transform; sweeps empty non-id `<g>`). Refactored the inline wrap into `_apply_geometry_crop` and reused it.
- **Discovery mid-implement:** pruning `visual.svg` alone reclaimed **0 KB** — `externalize_svg_images.py` harvests assets from `visual.svg` **and** `evidence/source-with-text.svg` (full page) into one shared store, and `publish_extraction.py` ships the evidence SVG, so it pins the 4 off-canvas rasters. Surfaced the tradeoff to the user; they chose **crop evidence + GC**.
- **Implement (cont.):** `_crop_evidence_svg` crops the evidence SVG to the same window (geometry + image prune, **text retained** — safe because validate's `<text>` enumeration is order-preserving under the wrapper `<g>`; fail-safe skip if viewBox extent ≠ page). Added `gc_unreferenced_assets` to `externalize_svg_images.py` (deletes assets no SVG references). Recorded `images_pruned` + `evidence_images_pruned` in the `region_crop` marker and return.
- **Tests:** +6 in `test_gates.py` (prune body / keep defs / fail-safe transform / affine honored / evidence crop preserves text / GC).
**Result:** Live e2e on the Level cards: `images_pruned: 4`, `evidence_images_pruned: 4`; raster **11 files/101 KB → 7 files/52 KB** (49 KB reclaimed); `visual.svg` 7 image refs, **0** semantic text; evidence viewBox `0 0 1975 495` with **21 `<text>` preserved**; `validate_text_slots.py` **valid exit 0**; `test_gates.py` **24/24**; `build_registry --check` clean (78). Updated `crop_svg_region.py` docstring + `tasks/plan-crop-prune-offcanvas-images.md` (status IMPLEMENTED + premise correction).
**State:** Not committed (awaiting review).

---

## 28 — Fix: cropped component Draft still previewed the full slide

**Request:** "tại sao extract component nhưng trong draft thì vẫn hiển thị full page?" — the catalog Draft showed the whole slide, not the extracted component.
**Actions:** Root-caused in `build_component_catalog.py` → `collect_images()`: a staging item's preview list was built from evidence images — `source-with-text.svg` then **`reference.png`** — and the cropped reusable `visual.svg` was only a last-resort fallback. `reference.png` is the WHOLE-page QA raster (1920×1714, never cropped), so it (and, before §26, the then-uncropped `source-with-text.svg`) made the Draft render the full slide. The front-end tile uses `images[0]` and the modal shows all images in a carousel, so the full page surfaced regardless. Fix: in `collect_images`, detect a cropped item via the `source.region_crop` marker in `artifact/text-slots.json` and **skip `reference.png`** for it (kept for non-cropped full-page templates, where it is correct). `reference.png` is staging-only QA dropped at publish, so this loses nothing. The §26 evidence crop already made `source-with-text.svg` region-scoped, so it is now a faithful region+text preview.
**Result:** Rebuilt catalog → staging item previews exactly `[Source with text]` (cropped, viewBox `0 0 1975 495`, 21 text / 7 images); server serves it. Browser-verified: Draft modal renders the 5 Level cards (the component), not the slide. `test_gates.py` **25/25** (+`test_catalog_preview_skips_fullpage_reference_when_cropped`). Side note (not fixed, separate from §21): the live catalog still shows a "Compatibility" filter/sub-tab; only console error is a favicon 404.
**State:** Not committed (awaiting review).

---

## 25 — E2E retest of `component-extractor` on the guideline PDF (re-verify intent)

**Request:** "check log … test workflow skill component extraction … test thử file `input/GUIDLINE_PRESENTATION_SUN.pdf`" — re-run the skill end-to-end and confirm it still matches intent.
**Actions:** Invoked the `component-extractor` skill. Preflight `--input pdf` READY (PyMuPDF 1.27.2.3; pptx-provider missing but irrelevant). Deleted the leftover staging from entry 24 and re-scaffolded clean from the existing request `input/GUIDLINE-level-cards.extraction-request.json` (item `level-progression-cards`, page 2, region pt `[440,440,1975,495]`). Ran the full pipeline: `scaffold_extraction.py --request` (→ staging, not duplicate) → `convert_pdf_source.py --page 2` → `extract_editable_text_slots.py` (57 slots/21 els) → `crop_svg_region.py` (16 kept / 41 dropped) → externalize → flatten (skipped: 0 leading raster) → externalize → optimize → apply_text_contract → `validate_text_slots.py`. Built `build_text_slot_gallery.py --extraction-dir` (1 item) + `build_component_catalog.py`; reused the running catalog server on :8799 (HTTP 200).
**Result:** Workflow works and matches intent — all prior fixes hold. Verified: viewBox `0 0 1975 495` (entry-10 Fix 1 pt-unit crop correct); `validate_text_slots.py` → **valid** exit 0 (entry-10 Fix 2); `status: staging` not duplicate (entry-14 fix); **0** semantic `<text>`/`<tspan>` nodes; 16 kept slots = in-region Level 1-5 labels/descriptions; catalog 79 (78 published + 1 staging `sun.component.level-progression-cards`); `build_registry --check` clean (78 valid). **Re-confirmed the entry-24 off-canvas defect (still unfixed):** `visual.svg` carries 11 `<image>` refs; with the `translate(-440,-440)` only the 5 level-card images (orig y=450 → translated y≈10, inside the 0-495 window) are visible — the other 6 (orig y 1822-2189 → translated >1380) sit wholly below the viewBox yet are still bundled into `artifact/assets/` (132 KB on disk). Renders correctly (clipped by viewBox); efficiency/cleanliness defect only.
**State:** Not committed (test/diagnosis).

---

## 2026-06-24.27 — Research + build agent-efficient log system (level B)

**Request:** "nghiên cứu hệ thống log, cho hiệu quả, agent đọc hiệu quả hiểu context, sử dụng cả codegraph và codebase memory mcp để tối ưu đọc file, sử dụng cả rtk" — chọn: index repo bằng codebase-memory rồi triển khai mức B.
**Actions:**
- Khảo sát: log hiện tại 282 dòng/26.8KB/ngày, số chạy toàn cục đã vỡ (thiếu 6/21/22), prose không query-được, số liệu cũ dễ bị tin nhầm. Verify: codegraph đã index; codebase-memory `list_projects` rỗng; rtk 0.42.1 có grep/json/log.
- `mcp__codebase-memory-mcp__index_repository` (moderate) → indexed 7216 nodes / 7640 edges (loại trừ `slide-system/scripts`, `docs`).
- NEW `slide-system/scripts/build_log_index.py` — derive `docs/logs/INDEX.jsonl` (1 JSON/entry: id,date,title,status,commit,files,symbols,supersedes,log) từ các SESSION-LOG; `--write`/`--check`; stdlib only; parse được cả số cũ lẫn `<date>.<n>`.
- NEW `docs/logs/INDEX.jsonl`.
- `AGENTS.md` + `docs/logs/_TEMPLATE.md` — đổi đánh số sang per-day `<date>.<n>`; thêm trường bắt buộc `Files:`/`Symbols:`; thêm mục "Reading the log efficiently" (rtk grep INDEX → đọc đúng entry → `codegraph node` lấy source hiện tại).
- NEW `tasks/research-log-system.md` — report nghiên cứu.
**Result:** `build_log_index.py --write` parse toàn bộ entry; `--check` exit 0; `rtk grep registry INDEX.jsonl` cô lập đúng entry. Giao thức đọc đã verify. (Lưu ý: một agent khác vừa thêm entry `## 26` trong lúc làm — đây là entry thứ 27 của ngày.)
**Files:** slide-system/scripts/build_log_index.py, docs/logs/INDEX.jsonl, AGENTS.md, docs/logs/_TEMPLATE.md, tasks/research-log-system.md
**Symbols:** build_log_index.parse_log, build_log_index.build_index, build_log_index.main
**State:** Not committed.

---

## 2026-06-24.29 — Decompose a region into DISTINCT components + classify/dedup (preview each + source)

**Request:** "loop cho tới khi nào đạt được output … browser để tự check … tìm chỗ khiến agent hiểu sai" — output spec: extract 1 page → tách từng component riêng biệt, phân loại; giống nhau → 1; cùng hình khác màu → gộp 1; preview hiển thị svg của TỪNG component riêng biệt + 1 ảnh source gốc để so sánh.
**Root cause (where the agent misunderstood):** the pipeline only crops ONE region per request item → `visual.svg` is a single glued artwork (the 5-card strip), never broken into its components. `decompose_svg_objects.py` exists but is tuned for PPTX layer export and over-fragments a layer-organized SVG (32 confetti objects here) because it clusters in document/painter order — wrong when the SVG stores all gradients in one group, all shadows in another, all faces in a third.
**Actions:**
- NEW `slide-system/scripts/classify_page_components.py`. Measures every group+child bbox in real Chromium (`measure_svg_groups.js`); drops off-canvas leaves (crop residue); **spatially** (2D bbox-overlap union-find, NOT document order) clusters on-canvas leaves into component instances; classifies instances into shape-CLASSES (congruent w×h within tol) so identical / same-shape-different-color collapse to ONE representative each; emits `artifact/components/<item>-class-NN.svg` + `components-manifest.json` (records `instance_count` per class).
- Three bugs found + fixed via browser/render self-check (the loop): (1) `wide()` bridging-guard used `h ≥ 0.55·H`, which flagged the tall 96%-height cards as "wide" and orphaned their icons → re-gated on **aspect ratio ≥ 8** (a divider is elongated; a card is not). (2) representative fragment rendered **blank** — measured bboxes are in final rendered space but the copied elements sit under the crop's `<g translate(-440 -440)>`; added `_ancestor_transform()` to capture the root→parent transform chain and re-apply it in the fragment. (3) `_SVG` name collision in the test file clobbered the crop tests' Clark-notation constant → renamed.
- `build_component_catalog.py` `collect_images()`: when `components-manifest.json` exists, surface one SVG per distinct class (label `… (×N)`) followed by ONE `Source (original region)` image; tile = first component (no longer the glued strip).
- Ran classifier on the staging item; rebuilt catalog; updated skill `SKILL.md` pipeline + `slide-system/workflows/extract-components.md` (step 10b) so future extractions run it.
- +5 pure-logic tests in `test_gates.py` (off-canvas drop / tall-card-absorbs-icon / divider-no-bridge / same-shape dedup / ancestor-transform+fragment).
**Result:** Classifier on `level-progression-cards`: **5 instances → 1 distinct class (×5), 0 dropped**; representative fragment renders a clean blue card (face+robot icon+arrow badge). Browser-verified on http://127.0.0.1:8799/slide-system/catalog/ Draft: tile shows the single deduped card (not the strip); modal carousel = [1/2] `Level Progression Cards Class 01 (×5)` + [2/2] `Source (original region)` showing all 5 colored Level cards for comparison — exactly the requested output. `test_gates.py` **30/30**.
**Files:** slide-system/scripts/classify_page_components.py, slide-system/scripts/build_component_catalog.py, slide-system/scripts/test_gates.py, slide-system/workflows/extract-components.md
**Symbols:** classify_page_components.process_item, classify_page_components._cluster_spatial, classify_page_components._shape_classes, classify_page_components._ancestor_transform, classify_page_components._build_fragment, build_component_catalog.collect_images
**State:** Not committed (awaiting review).
