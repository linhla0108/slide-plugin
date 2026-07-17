# Session Log — 2026-07-16

Branch: `feature/shape-aware-retrieval`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` → "Task Logging").

---

## 2026-07-16.1 — Close review findings: batch validator parity, catalog review-only UX, retired vocabulary

**Request:** Fix the final findings from an independent review of the
component-selection changes: (1) P1 — the batch input validator accepts data the
schema forbids and then crashes (`content_shape: ["flow"]` →
`TypeError: unhashable type: 'list'` in `_common.shape_eligible`); schema and
hand-written validator are two drifting sources of truth. (2) Review-only
components (`auto_reuse.eligible: false`) are invisible in the catalog UI, so a
non-technical user can copy their prompt and hit a later fidelity failure.
(3) Remove remaining retired `adapt-local` vocabulary. No commit/push.

**Actions:**
- F1 route decision: checked for a declared `jsonschema` dependency first. The repo
  has **no Python dependency manifest at all** (no pyproject/requirements/setup.py/
  Pipfile; `package.json` declares only Playwright), and no repo script imports
  `jsonschema`. Per the brief, took the no-new-dependency route: made
  `validate_batch_request()` enforce every field/type the schema declares
  (`content_shape`/`density`/`brand`/`prefer_type` string-or-null, `query` string,
  `recommend_extraction` bool, top-level `brief`/`note` strings — all previously
  unchecked) and added
  `test_batch_request_validator_matches_schema_field_by_field`, which READS
  `schemas/visual-requests.schema.json` and asserts (a) the validator's field
  vocabulary equals the schema's, and (b) each declared type is actually rejected
  when violated. A schema property the validator forgets now fails the test instead
  of reaching the scorer.
- F1 truthfulness: nothing evaluates the file as JSON Schema at runtime, so removed
  that implication from the schema `description`, `select-visual-items.md`, and
  `SKILL.md`; each now says the contract is enforced in code and held in lockstep by
  the parity test. Documented the two deliberately code-only checks (duplicate
  `request_id`, blank-only strings — stricter than `minLength: 1`).
- F2: `build_component_catalog.py` already copies the whole registry item
  (`item = dict(pub_item)`), so `auto_reuse` needed **no** builder change — but the
  tracked `catalog-data.json` was a 2026-07-06 projection, so the UI never saw the
  flag. Refreshed the published projection from the current registry (91 items, none
  added/removed) while preserving the 4 tracked Draft rows verbatim: a plain rebuild
  would have swapped them for this machine's 149 local (gitignored) drafts.
- F2 UI (`catalog.js`/`catalog.css`): added `compIsReviewOnly()` keyed on
  `auto_reuse.eligible === false`; a red `Review-only` badge NEXT TO `Published` in
  both tile and modal; the stored reason as the FIRST Info row; Copy prompt disabled
  with the reason in its tooltip (matching the existing blocked-Publish convention);
  Copy ID and preview left available. Reset both ways on modal render — the button is
  a persistent node reused across items.
- F3: removed behaviour-facing `adapt-local`. Real dead code found:
  `_validate_occurrence` only ever runs for `action == "reuse"`, so
  `threshold = REUSE_MIN if action == "reuse" else ADAPT_MIN` was unreachable —
  deleted `ADAPT_MIN` and the now-unused `action` parameter from
  `_check_slot_contract`/`_validate_occurrence` (reuse threshold unchanged at 0.70).
  Six fidelity tests had been passing the retired `"adapt-local"` action, i.e.
  asserting against a 40% bar the real gate can never use; and
  `test_strict_shape_rejects_unknown_shape_on_non_selecting_decisions` looped over the
  retired `"blocked"` action — now `needs_component`. Corrected user-visible strings
  (`component_fidelity: … reuse/adapt occurrence(s)` → `reuse`; the design-plan
  rejection reason), the stale prefer-set band comment, and the stale decision tables
  in `rules/visual-selection.md`, `docs/flows/component-selection-flow.md`, and
  `docs/flows/slide-generator-workflow.md`. Left `slide-system/docs/PLAN-component-fidelity.md`
  and `docs/specs/component-metadata-quality-spec.md` alone: both pin their own
  context ("Status: PLAN — code/flow-docs not yet touched", "as read today (v3.1.0)"),
  so they are dated design records, not current-behaviour docs. Every surviving
  `adapt-local` mention is an explicit "is retired" statement.

**Result:** `test_gates.py` **241/241** (6 new: schema/validator parity, duplicate
request_id, the exact `content_shape: ["flow"]` no-traceback repro, catalog data
projection, shipped catalog snapshot, catalog UI wiring). RED verified first: the
repro test failed with the real `TypeError` traceback and parity failed on
`brief=3`. py_compile clean; `validate_registry` 91 items; `build_registry --check`
clean; retrieval index `--check` clean 91; `build_log_index --write/--check` up to
date; `git diff --check` clean. Strict selection validation PASS for both
`nine-slide-brief` and `distinct-deck`. Real-deck fidelity
`--render --require-render` still PASS (3 reuse) after the signature change. CLI
repro now prints `slides[0]: content_shape must be one piece of text (or omitted),
got ['flow']`, exit 1, no report written. Catalog smoke (real `catalog_server.py` +
Playwright): hexagon-diagram renders `Published` + `Review-only`, badge computed
visible, reason in Info, Copy prompt disabled / Copy ID enabled / preview intact; a
normal published component shows one badge, no note, Copy prompt enabled, and state
resets when navigating between them. No publish-semantics, threshold, or brand-asset
change; no dependency added. `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/resolve_style_profile.py, slide-system/scripts/test_gates.py, slide-system/schemas/visual-requests.schema.json, slide-system/catalog/catalog.js, slide-system/catalog/catalog.css, slide-system/catalog/catalog-data.json, slide-system/rules/visual-selection.md, slide-system/rules/style-profiles.md, slide-system/workflows/select-visual-items.md, docs/flows/component-selection-flow.md, docs/flows/slide-generator-workflow.md, .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl
**Symbols:** score_visual_items.validate_batch_request, score_visual_items._NULLABLE_TEXT_FIELDS, validate_component_fidelity._check_slot_contract, validate_component_fidelity._validate_occurrence, validate_component_fidelity.REUSE_MIN, resolve_style_profile.resolve, catalog.compIsReviewOnly, catalog.compStatusBadges, catalog.compReviewReason, catalog.compRenderInfoPanel, catalog.compRenderModal, catalog.compCreateTile
**State:** Not committed

---

## 2026-07-16.2 — Deterministic catalog projection, dependency-claim fix, QA deck + PPTX

**Request:** (1) Make the tracked `catalog-data.json` deterministic — a normal rebuild
imported machine-local gitignored Drafts, so any developer's regeneration replaced the
tracked Draft rows with their own. (2) Correct the inaccurate claim that `jsonschema`
is not installed. (3) Run a real end-to-end component-reuse QA build producing a PPTX
for manual review. No commit/push.

**Actions:**
- Fix A — split ownership in `build_component_catalog.py`: `build_published_items()`
  (tracked projection, pure function of the tracked registry) and `collect_draft_items()`
  (machine-local live scan). `main()` now writes published-only and no longer accepts
  `--extractions` at all — that flag WAS the contamination vector. Replaced wall-clock
  `generated_at` with `registry_updated_at` (the source registry's own timestamp), so
  the same tracked state yields byte-identical output; nothing read `generated_at`.
  Drafts moved to the existing server/API surface: `catalog_server.py` gained
  `GET /api/drafts` (+ a `do_GET` router that leaves static serving untouched) and
  `catalog.js` merges them over the published projection, degrading to published-only
  when no control server is running. `extract_pdf_components.py` dropped `--extractions`.
  This also removes last session's copy-forward-the-Draft-rows workaround.
- Fix B — verified, then corrected: `jsonschema` 4.26.0 IS installed, but in an
  unrelated interpreter on PATH (the Hermes agent venv), NOT in the project venv these
  scripts pin, and no repo script imports it, and no Python dependency manifest exists.
  Removed the "not even installed" claim from entry .1 and sharpened the scorer
  docstring. The parity route is unchanged (nothing declares the dependency).
- QA build (`outputs/slide-jobs/catalog-determinism-qa-20260716/runs/qa-01`): authored
  Vietnamese requests, scored, scaffolded, materialized and exported through the real
  path. Visual QA drove three real repairs: (i) `top1` copy measured 396px in a 343px
  box -> shortened (fit policy is hard, never shrink); (ii) `agent-networks`' declared
  box overruns its card artwork (x=1503 vs card edge ~1410) so copy that "fits" still
  spilled — kept the copy inside the card; (iii) the personas card-set
  (`translator-strategist-driver-coach-card-set`) MISALIGNS: artwork has 2 cards but the
  contract declares 4 title groups, so columns 3-4 land on card 2 and column 1 clips off
  the edge. Fidelity passed it (each text fits its declared box) — artwork-vs-slot drift
  the render gate cannot see. Re-targeting that slide at team/contributors returned
  `needs_component`, so the deck ships 4 slides rather than an implicit custom build.
- Bug found and fixed en route (`scaffold_slide_from_component.py`): published
  `preview.html` files write their source family INSIDE a double-quoted style attribute
  (`style="...font-family:"ProximaNova-Bold", ...;font-size:120px;..."`). The inner
  quotes close the attribute, so the browser dropped every later declaration — the
  cover's 120px hero title rendered at the default 32px and the brand-font gate read the
  wreckage as bogus families. `_blank_text` now strips the source family, applying the
  rule `_slot_text_css` already used for slot-contract components (brand pack outranks a
  component's foundry font). 51 published previews carry the malformed markup; they were
  NOT modified.

**Result:** `test_gates.py` **244/244** (3 new: tracked-projection determinism, runtime
Draft API, template-scaffold font-family). Determinism proven on the real repo with 472
local Draft dirs present: two default rebuilds -> identical sha256
`c382074864de31d8...`, 91 published items, 0 Drafts; previously the same command
injected 149. All 91 published ids preserved, both review-only flags intact.
`GET /api/drafts` serves 149 local Drafts; catalog UI shows 149 Drafts + published, and
review-only still renders. py_compile clean; `validate_registry` 91;
`build_registry --check` clean; retrieval index `--check` clean 91; `build_log_index
--write/--check` up to date; `git diff --check` clean. QA deck: 4 slides, all automatic
`reuse`, all distinct, none review-only — strict selection PASS, brand PASS, fidelity
`--render --require-render` PASS (4 reuse), template-slot fit probe 0/11 overflowing,
PPTX layered export `pass: true` (tier1+tier2 parity), PDF rendered, 4 screenshots
reviewed. No dependency added; no threshold, publish-semantics, brand-asset or library
artifact change. `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/build_component_catalog.py, slide-system/catalog/catalog_server.py, slide-system/catalog/catalog.js, slide-system/catalog/catalog-data.json, slide-system/scripts/extract_pdf_components.py, slide-system/scripts/scaffold_slide_from_component.py, slide-system/scripts/score_visual_items.py, slide-system/scripts/test_gates.py, docs/flows/catalog-publish.md, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/catalog-determinism-qa-20260716/ (ignored)
**Symbols:** build_component_catalog.build_published_items, build_component_catalog.collect_draft_items, build_component_catalog.main, catalog_server.action_drafts, catalog_server.GET_ROUTES, catalog_server.Handler.do_GET, catalog.compLoadDrafts, catalog.compLoadData, scaffold_slide_from_component._blank_text, scaffold_slide_from_component._SOURCE_FONT_FAMILY_RE, extract_pdf_components.run_workflow
**State:** Not committed

---

## 2026-07-16.3 — Component-safety fixes: review-only backfill, immutable_text gate, template render fidelity

**Request:** Fix the component-safety failures real visual QA found — (A) record the
confirmed full-slide QA failures via `auto_reuse`; (B) stop semantically wrong reuse of
components whose artwork bakes in source-specific text (the Performance Review closing
auto-selected into an AI 2026 deck); (C) make `--require-render` measure template
`data-slot-id` slots, not just `data-component-slot` — then generate a new automatic-reuse
PPTX/PDF deck for manual review. No commit/push.

**Actions:**
- Fix A: backfilled `auto_reuse: {eligible:false, reason}` on
  `spicy-autocomplete-autonomous-levels-strip` (cropped by the canvas: the level-1 card
  loses its left edge and its binary glyph is sliced to '1 1'; the Cap-4 `agent-networks`
  slot also over-declares its box to x=1503 vs a card edge near x=1410) and
  `translator-strategist-driver-coach-card-set` (artwork has 2 cards, contract declares 4
  title groups -> columns 3-4 land on card 2, column 1 clips off the edge). Both stay
  published/browseable; regression tests use the real ids + the requests that previously
  picked them.
- Fix B: new generic `immutable_text: {terms, reason}` on a library item — schema-declared,
  enforced by `validate_registry`, carried through compact/retrieval/catalog. `terms` are
  matched against the request's intent/tags through the scorer's existing canonicalization
  and ALSO join the item's own matchable vocabulary (the baked copy is genuinely part of
  what the item says — that is what lets a deck about that context still reuse it at full
  confidence). No overlap -> `_immutable_text_ok` bars AUTOMATIC reuse (item stays
  published + scored); explicit selection still wins but is warned and records
  `immutable_text_conflict` on the decision, which `check_fidelity` fails closed before any
  geometry check. Nothing keys on an id or a phrase. Backfilled the Performance Review
  closing (its lockup is NOT among its 4 editable slots).
- Fix C: `measure_deck_slots.js` now walks BOTH slot dialects per instance, tagged
  `kind: component|template`; the template branch of `_validate_occurrence` gained the
  visibility/zero-size checks the component branch had. RED proved first: with the template
  dialect removed the measurer returns `{}` and the new test fails.
- Turning the gate on immediately failed the real cover/closing: their ink escaped the
  wrapper (`interview` measured 646x135 inside a 728x146 box yet still read as outside).
  Cause: preview slots are copied top-aligned at line-height 1.0 with boxes sized to the
  SOURCE ink, so Vietnamese diacritics (Ứ/Ụ) overshoot the top. Fixed generically in
  `scaffold_slide_from_component._blank_text` by centring template slot text — the same
  rule `build_slot_scaffold` already applies to slot-contract components. No type shrinking.
- QA deck (`outputs/slide-jobs/component-safety-qa-20260716/runs/qa-01`, ignored): visual
  QA rejected a third component mid-run — `lorem-ipsum-circle-badge-set` (badge circles
  cover-cropped at the canvas edges; caption slots sit outside the circle artwork, so white
  caption text landed on the white background, e.g. 'Chọn việc lặp' spilled out of the 01
  circle). Flagged it with the same generic mechanism + its own regression case, and the
  re-score then returned `needs_component` for that slide — proof the gate works — so the
  slide was re-targeted at a checklist template. A builder bug also surfaced: 7 checklist
  slots wrap text in `<li>`, which the fill regex missed, so they shipped EMPTY and the
  render gate still passed them (an empty slot cannot overflow) — coverage is not
  correctness.

**Result:** `test_gates.py` **252/252** (8 new: 5 immutable_text, template render
measurement, template centring, plus the review-only set pinned to exact ids so a future
backfill cannot quietly mark unrelated components). py_compile clean; `validate_registry`
91; `build_registry --check` clean; retrieval index `--check` clean 91; `build_log_index
--write/--check` up to date; `git diff --check` clean. Review-only is now 5 items, all
still published. QA deck: 4 slides, all AUTOMATIC reuse, distinct, none review-only, and
the closing is no longer the Performance Review one — strict selection PASS, brand PASS,
fidelity `--render --require-render` PASS (4 reuse, template slots now measured), PPTX
layered export `pass: true` (tier1+tier2 parity), PDF rendered, 4 screenshots reviewed
individually. Known cosmetic: on the checklist slide one continuation line's slot shares
the checkbox column (left=1075), so its first glyph touches the checkbox — the template's
own geometry, which the build must not move. No dependency, no threshold change, no
publish-semantics change, no component deleted/unpublished, no brand-asset or library
artifact change. `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/schemas/visual-item.schema.json, slide-system/schemas/selection-report.schema.json, slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/validate_registry.py, slide-system/scripts/validate_selection_report.py, slide-system/scripts/build_registry.py, slide-system/scripts/build_component_retrieval_index.py, slide-system/scripts/measure_deck_slots.js, slide-system/scripts/scaffold_slide_from_component.py, slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, slide-system/catalog/catalog-data.json, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/component-safety-qa-20260716/ (ignored)
**Symbols:** score_visual_items._immutable_text_ok, score_visual_items.score_request, score_visual_items._explicit_decision, score_visual_items._reuse_ready_ids, validate_component_fidelity.check_fidelity, validate_component_fidelity._validate_occurrence, validate_registry.main, build_registry.COMPACT_KEYS, build_component_retrieval_index.build_record, scaffold_slide_from_component._blank_text, scaffold_slide_from_component._TOP_ALIGN_RE
**State:** Not committed

---

## 2026-07-16.4 — Empty-slot immutable-text audit: 91 items audited, 22 source-locked

**Request:** Close the source-specific baked-text gap in automatic reuse — build a
deterministic audit of text visible in artifacts but not represented by an editable
slot, record it as schema-validated 3-state metadata, backfill from evidence, and ship
a new automatic-reuse QA deck. The brief named `05-prep` as still carrying baked
`quý 1` / HR-admin source text.

**Actions:**
- Disproved the stated premise before building on it. Rendered `05-prep` with EVERY
  slot empty: **zero words** — all 25 source strings are editable slots. The `quý 1`
  and `Phòng HR & Admin` on the previous QA slide were copy I authored into the slots
  named `s-t-a-r` and `hra-department` in entry .3; an authoring error, not a system
  gap. Also disproved the specified audit method: a census showed **0 of 91** published
  items have live `<text>` in `visual.svg` (the pipeline strips it), so "text in the
  artifact with no slot" finds nothing on every item — including the one real case. The
  genuine baked text is OUTLINED VECTOR PATHS, invisible to XML and unreadable without
  OCR (a forbidden dependency). Asked the user; they chose the empty-slot audit with no
  library-wide fail-closed default, and to keep `05-prep` auto-selectable.
- New `audit_immutable_text.py`: scaffolds each published item, leaves every slot
  empty, renders 1920x1080 on the existing Playwright, and emits `audit-report.json`
  plus contact sheets. The render IS the evidence (deterministic, reproducible); a
  human classifies whether surviving ink is a word; the verdict is recorded on the
  item. Also keeps the one check that IS decidable from markup — every source `<text>`
  node is slot-covered — scoped to templates, since a component's evidence is the whole
  source PAGE it was cropped from.
- `immutable_text` became 3-state `{audit: clean|immutable|unresolved, terms?, reason}`.
  clean/absent -> normal automatic reuse; immutable -> requires a request/context term
  match (terms also join the item's matchable vocabulary); unresolved -> fails closed.
  ABSENT stays current behaviour, so no item is disabled by omission. `validate_registry`
  enforces terms iff audit==immutable, and rejects terms on any other verdict.
- Audited all 91, reviewed 8 contact sheets, backfilled from the renders: **22
  immutable, 69 clean**. The finding the brief was reaching for: the "Performance
  Review 2025" lockup is a DECK-LEVEL element on all ~20 `sun-studio-performance-review-2025.*`
  slides — only 1 was flagged in entry .3, so ~19 were still auto-selectable into any
  brief. Also `goal-setting-2026.01-cover` / `.09-thanks` bake a "GOAL SETTING" lockup
  (+ giant "2026"). Everything else is clean; surviving marks are canonical brand
  (SUN.STUDIO / SUN.RISER lockups) or decorative.
- Renamed `test_s7_generic_howto_selects_custom_local_not_domain_timeline` ->
  `..._is_needs_component_not_domain_timeline_reuse`: it always asserted
  `needs_component`, which the scorer has never reached via automatic custom-local.

**Result:** `test_gates.py` **255/255** (4 new: audited-clean keeps normal behaviour on
the real `05-prep`; unresolved fails closed + is warned on explicit selection; the audit
tells editable slot text apart from baked semantic text on the two real templates;
plus the existing immutable/review-only/template-render suites green). py_compile clean;
`validate_registry` 91; `build_registry --check` clean; retrieval index `--check` clean
91; `build_log_index --write/--check` up to date; `git diff --check` clean. Proof on real
data: a generic AI/workshop closing request now selects `sun-presentation.17-closing-thank-you`
and records the PR closing as `matched: false`, while a performance-review request still
selects the PR closing automatically. QA deck (`outputs/slide-jobs/immutable-text-qa-20260716/runs/qa-01`,
ignored): 4 slides, all AUTOMATIC reuse, distinct, all `audit: clean`, none review-only —
strict selection PASS, brand PASS, fidelity `--render --require-render` PASS (the gate
caught and rejected my first "Ứng dụng AI 2026" footer as overflow), PPTX layered export
`pass: true`, PDF rendered, 4 screenshots reviewed. A mechanical dump of every rendered
string found NO source-specific text (no quý/HR/Admin/Performance/Review/2025/GOAL SETTING).
Open classification: the cover bakes "SUN.RISER" (brand lockup + artwork tile) — recorded
clean as canonical brand; if SUN.RISER is a programme name it should be re-audited as
immutable. No dependency, no threshold change, no publish-semantics change, nothing
deleted/unpublished. `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/audit_immutable_text.py (new), slide-system/schemas/visual-item.schema.json, slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_registry.py, slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, slide-system/catalog/catalog-data.json, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/immutable-text-qa-20260716/ (ignored)
**Symbols:** audit_immutable_text.main, audit_immutable_text.source_text_nodes, audit_immutable_text.source_text_uncovered, audit_immutable_text.empty_scaffold, audit_immutable_text.contact_sheets, score_visual_items._immutable_text_ok, score_visual_items.score_request, score_visual_items._explicit_decision, validate_registry.main
**State:** Not committed

---
## 2026-07-16.5 — Immutable-text: context groups, audit-evidence contract, artifact binding

**Request:** Fix three proven defects in the immutable-text audit/reuse work from entry
.4: (A) the immutable gate accepted ANY matching term, so a closing request whose only
context word was `2025` auto-selected the Performance Review 2025 lockup; (B) the stored
full-library audit report claimed 91 audited with `"rendered": 0` and every
`empty_render: null` — a `--no-render` pass had overwritten real evidence; (C) verdicts
were not bound to the artifact, so re-extracted artwork kept a stale `clean`. Generic
fixes only, no component-specific conditions, no new dependency.

**Actions:**
- **A — context groups.** `immutable_text.terms` (OR-of-terms) became
  `immutable_text.contexts`: a list of groups, ALL-OF within a group, ANY-OF across.
  `_immutable_contexts` / `_immutable_context_matched` in `score_visual_items.py` are
  pure metadata — a synthetic `zephyr-summit/2031` item behaves identically, so nothing
  is keyed to an id, phrase or year. Backfilled 22 immutable items with complete
  contexts (PR: `[["performance-review","2025"],["performance","review","2025"]]`;
  Goal Setting: `[["goal-setting","2026"],["goal","setting","2026"]]`), so neither
  unlocks on a bare year. `unresolved` still fails closed; `clean` still reuses
  normally; explicit selection still wins but records `immutable_text_conflict` and
  fails closed at the fidelity gate.
- **B — audit artifact contract.** `audit-report.json` (mode=rendered) and
  `audit-report.static.json` (mode=static-only) are now separate files, so `--no-render`
  can neither overwrite nor downgrade real evidence; it prints a NOTE naming the report
  it preserved. Every report carries `mode`, `status` (`complete` only when EVERY
  renderable item rendered), `usable_as_verdict_evidence`, and per-record
  `render.{status,path,reason}` distinguishing rendered/failed/skipped/not-applicable.
  Render evidence paths are relative to the REPORT, so the audit folder stays a
  self-contained bundle with no absolute machine paths.
- **C — artifact binding.** `build_registry.immutable_text_fingerprint` content-hashes
  the inputs that decide the empty-slot render (visual + slot contract; the preview
  raster for items with no `paths.visual`) — sha256 only, no mtimes, no machine paths.
  `gate_immutable_text` applies at `project_compact`, the single choke point the scorer
  reads: never audited -> unresolved, no fingerprint -> unresolved, drift -> unresolved.
  `publish_extraction.py` now calls that projection instead of re-deriving compact, which
  closed a bypass where a freshly published item projected as immediately reusable.
- Found en route: `sun.asset.logo` renders BLANK when scaffolded (it is composed onto
  slides, not reused as one) and had no `paths.visual`, so its verdict was bound to
  nothing. Fixed generically by fingerprinting the preview raster — 90/91 verdicts are
  now bound. `sun.character.dio` remains exempt: its paths name a DIRECTORY, so there is
  no artifact file to hash and it cannot be scaffolded at all.

- **Tester pass (independent, post-implementation) found two defects of my own, both
  fixed with RED->GREEN tests before this entry was finalised:**
  1. `renders_as_slide` had been refactored to `bool(immutable_text_fingerprint(item))`,
     which silently EXEMPTED an item whose declared `paths.visual` was missing from disk
     — a deleted visual.svg turned "unverifiable" into "clean" instead of failing
     closed. It now asks what the item DECLARES, and exempts only a path naming a
     directory (Dio). Caught by `test_declared_artwork_that_is_missing_fails_closed_not_exempt`.
  2. The `needs_component` reason claimed "below the high-confidence reuse bar" for
     candidates that cleared BOTH bars (the real 2025 case: 88.0 total / 28.0 semantic
     against bars of 78 / 24.5) — the reader was sent to raise a score that could never
     unblock it. `_reuse_blocker` now returns the reason and `_reuse_ready` is
     `_reuse_blocker(...) is None`, so the gate and its explanation cannot drift.
     Caught by `test_needs_component_reason_names_the_real_blocker`.
  Also checked and NOT defective: an immutable-blocked candidate does not shadow a
  lower-scoring clean one (`reuse_ready[0]` is chosen from the filtered list).

**Result:** `test_gates.py` **265/265** (10 new, all 11 required regressions covered; 3
tests migrated off the retired `terms` key; the `terms`-era test that asserted a generic
synthetic item was folded into the stronger all-of/any-of matrix test). py_compile clean;
`validate_registry` 91; `build_registry --check` clean; retrieval index `--check` 91;
`build_log_index --write/--check` up to date; `git diff --check` clean. Proof on real
data: a closing whose only context is `2025` now returns `needs_component` (was: the PR
lockup) and says why — "carries fixed source text that does not fit this deck [audit:
immutable]"; a generic closing still reuses a different clean component
(`sun.salary-benefits-2026.18-thanks`); and the real 2025 performance-review closing
still auto-selects. Full 91-item RENDERED audit
(`outputs/slide-jobs/immutable-audit-20260716-rendered/`, ignored): mode=rendered,
status=complete, 90 rendered + 1 not-applicable, zero absolute paths, every rendered
record has a PNG on disk, and all 90 bound verdicts match the artwork just audited. A
`--no-render` pass against that same directory left `audit-report.json` byte-identical
and wrote `audit-report.static.json` with `usable_as_verdict_evidence: false`.
QA deck (`outputs/slide-jobs/immutable-context-qa-20260716/runs/qa-01`, ignored): 3
slides, all AUTOMATIC reuse, distinct, published, audited clean — strict selection PASS,
brand PASS, fidelity `--render --require-render` PASS, PPTX layered `pass: true`, PDF
rendered, 3 screenshots reviewed. A mechanical dump of all 774 rendered characters found
NO source-specific text. The deliberately-baited closing request (tags carrying BOTH
`2025` and `2026`) correctly returned `needs_component` rather than the PR lockup — the
library's only closing-shaped template IS the PR-2025 one, so declining is the honest
answer.
**Found, not fixed (out of scope):** `sun.goal-setting-2026.05-process` cannot
round-trip its OWN source strings — "BOD" renders 75.1px in its 74px box, "team" 54.8px
in 52px — because the scaffold strips the source font and Proxima Nova is wider. It
scores 86.25 and is audited clean, so it auto-selects and then fails the render gate. It
was dropped from the QA deck and left unchanged; it needs its own fix.
No dependency, no threshold change, no publish-semantics change, nothing deleted or
unpublished. `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/score_visual_items.py, slide-system/scripts/build_registry.py, slide-system/scripts/validate_registry.py, slide-system/scripts/audit_immutable_text.py, slide-system/scripts/publish_extraction.py, slide-system/scripts/test_gates.py, slide-system/schemas/visual-item.schema.json, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/immutable-audit-20260716-rendered/ (ignored), outputs/slide-jobs/immutable-context-qa-20260716/ (ignored)
**Symbols:** score_visual_items._immutable_contexts, score_visual_items._immutable_context_matched, score_visual_items._immutable_text_ok, score_visual_items._reuse_blocker, score_visual_items._needs_component_decision, score_visual_items.score_request, score_visual_items._explicit_decision, build_registry.immutable_text_fingerprint, build_registry.renders_as_slide, build_registry.immutable_text_drift, build_registry.gate_immutable_text, build_registry.project_compact, audit_immutable_text.main, audit_immutable_text._rel, audit_immutable_text.contact_sheets, validate_registry.main, publish_extraction.main
**State:** Not committed

---
## 2026-07-16.6 — Enforce audit freshness at selection time; slot-coherent authoring rule

**Request:** Close the last two immutable-text review findings. (1) "Artifact changes
invalidate audit status" was not true end-to-end: `gate_immutable_text` only ran when the
compact projection was REBUILT, and the scorer consumed the existing compact without
proving it fresh — so an artifact could change after projection and the old `clean`
verdict still auto-reused. A full-registry `--registry` input bypassed the gate entirely.
(2) The latest QA tier slide was technically safe but visually weak: copy fragmented
across disconnected slots ("Nền tảng" split from "riêng"), not manager-ready.

**Actions:**
- **Reproduced finding 1 first.** With one byte appended to a real `visual.svg`:
  `build_registry --check` DID report drift (exit 1) and `validate_registry` DID report
  the stale verdict — but `score_visual_items` scored anyway and auto-reused the stale
  item. The detection existed; the enforcement did not.
- **Enforcement model — one shared predicate, three layers, no new fingerprint logic.**
  `--check`'s own compact/retrieval comparison became
  `build_registry.generated_projection_staleness()` (plus `live_registry_items()` and
  `REFRESH_HINT`), and `--check` now calls it. It needs no fingerprint code of its own:
  recomputing the projection runs `gate_immutable_text`, which re-hashes every artifact,
  so changed artwork surfaces as compact drift. Then:
  1. `score_visual_items.scoring_items()` — the single door from a `--registry` path to
     scoring items. The CANONICAL compact (the default, what the workflow runs) is
     preflighted against that predicate and REFUSED when stale (exit 1, no report
     written, plain remediation naming `--write`). A FULL registry input (items carry
     `paths`) is projected through the same `gate_immutable_text` IN MEMORY — same rule,
     no file writes, registry never rewritten by scoring.
  2. `validate_component_fidelity.check_fidelity` — the pre-build/export gate — re-checks
     `immutable_text_drift` for every selected item against the bytes on disk NOW, so a
     report scored before an artifact change cannot reach build. Uses `drift` (not the
     whole gate) so a never-audited synthetic item is left to selection-time rules.
  Layer 3 is what makes "compact, explicit `--registry`, and pre-build cannot disagree"
  true: even a hand-built compact that fakes a verdict is caught before the deck builds.
  Nothing keyed to an item id, source deck or year.
- **Finding 2 — measured the metadata before designing.** `read_text_slots --slots-only`
  + the source evidence render show the tier component is rank -> category -> a STACKED
  headline ("FOUNDATION"/"BUILT", "MICROSOFT"/"&"/"XIAOMI"), and 05-prep is a 2-line
  title, a 2-line quote and exactly TWO outline groups (x=.560) whose sub-headings sit
  at x=.577 with `•` bullets. Census: **0 of 1821** declared slots are `required: true`
  and **no group/continuation field exists anywhere**. So requirement 4's precondition
  ("only if the current metadata can support it reliably") is NOT met — a coherence check
  needs NLP (forbidden) and a required-slot check would never fire. **No validator was
  added**; the deliverable is the authoring rule in `workflows/build-html-deck.md` +
  `slide-generator/SKILL.md`: every filled slot reads as a complete unit, never split a
  phrase across slots, leave continuation/decorative slots empty (`allow_empty` is const
  true), read hierarchy off role/html_tag/example_value/bounds (the slot array is NOT in
  reading order), and if the geometry cannot carry the content, pick another component or
  leave it `needs_component` — the overflow gate proves text fits its box, never that the
  slide reads.
- **Rebuilt the deck against that rule.** Tier: each circle now reads
  `01 / Trợ lý AI / NỀN TẢNG`, `02 / Quy trình nhóm / GIỎI`, `03 / Sản phẩm AI / DẪN DẮT`;
  the 4 continuation slots (`built`, `fb-instant-games`, `text-13` "&", `xiaomi`) are
  deliberately empty. 05-prep: mirrors the source's real hierarchy — an earlier draft put
  "Bước 3" into an INDENTED sub-heading slot (it rendered nested inside Bước 2) and "3
  việc" into `s-t-a-r`, which is the bolded TAIL of the bullet beside it, not a note.
  Both fixed; `s-t-a-r` now empty. The builder was changed so a deliberate blank must be
  declared with a reason and any unaccounted slot raises — empty stays a decision, not
  the accident that once shipped 7 blank checklist rows past the render gate.

**Result:** `test_gates.py` **269/269** (4 new: default compact CLI refuses a stale
projection; the refreshed projection makes the changed item `unresolved` and unselectable
while the other 90 stay reusable; a full-registry input with wrong evidence cannot
auto-reuse and is not rewritten; a report scored before an artifact change is rejected
pre-build). py_compile clean; `validate_registry` 91; `build_registry --check` clean;
retrieval index `--check` clean 91; `build_log_index --write/--check` up to date; `git
diff --check` clean. End-to-end on the REAL CLI with one byte appended to
`05-prep/visual.svg` (restored byte-exact after; tests use a context manager that restores
even on failure): default scoring exits 1 with the remediation and writes NO report; the
explicit full-registry path returns `needs_component` for that item; pre-build fidelity
FAILs it by name with the sha delta. `2025`-only closing still returns `needs_component`,
never the PR-2025 lockup. QA deck (`immutable-context-qa-20260716/runs/qa-01`, ignored):
3 slides, all AUTOMATIC reuse, published, distinct — strict selection PASS, brand PASS,
fidelity `--render --require-render` PASS, PPTX layered `pass: true`, PDF, 3 screenshots
inspected, all 702 rendered characters free of source-specific text.
**Found, not fixed (component-level, reported):** 05-prep's
`h-nh-dung…` slot bound is extracted at x=.560 — 33px LEFT of its sibling checkbox item
at x=.577 — so any left-aligned copy touches the artwork's checkbox glyph; leaving it
empty is worse (the checkbox is background, so it renders orphaned). Slide 3 therefore
still carries that one overlap: NOT claimed pixel-clean. Slot-contract components also
default to `justify-content:flex-start` when typography declares no alignment (it declares
none here), so replacement copy shorter than the source's ink box sits off the artwork's
optical centre — the template path already centres, so the two scaffold paths disagree.
No dependency, no threshold change, no scorer special case, nothing deleted. `.mcp.json`/
`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/build_registry.py, slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/test_gates.py, slide-system/workflows/build-html-deck.md, .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/immutable-context-qa-20260716/ (ignored)
**Symbols:** build_registry.generated_projection_staleness, build_registry.live_registry_items, build_registry.REFRESH_HINT, build_registry.main, score_visual_items.scoring_items, score_visual_items.main, validate_component_fidelity.check_fidelity
**State:** Not committed

---
## 2026-07-16.7 — Component contracts: whitespace-inflated slot bounds, asymmetric-hero metadata

**Request:** Fix two manager-readiness defects in published component contracts. (1) On
05-prep the checkbox glyph collided with "Ghi rõ đầu vào…" and leaving the slot blank
left an orphan checkbox, so copy could not solve it. (2) The three-circle component was
being used as a balanced tier ladder although its geometry is asymmetric, and its
replacement copy defaulted left-aligned.

**Actions:**
- **P1 — found a GENERIC extraction bug, not a one-off.** The source evidence settles it:
  05-prep's two sibling checkbox rows differ only in how the SOURCE happened to emit a
  leading space. `Đọc lại JD` put it in its own tspan, so the visible tspan starts at
  x=1107.84 and its bound is right (0.5770). `Hình dung…` kept the space INSIDE the
  tspan, so the tspan starts at x=1074.55 and the bound swallowed it (0.5597) — 33.3px,
  a whole checkbox indent, left of its sibling. The first INKED glyph is at 1107.82 —
  0.5770, matching the sibling exactly. `extract_editable_text_slots.split_runs` measured
  `run_xs` including whitespace glyphs while the caller recorded `example_value` as
  `run_text.strip()`, so the box and the value described DIFFERENT glyphs. Fixed
  generically: runs are trimmed to their inked glyphs before measuring (interior spaces
  untouched). **82 of 91 published items carry at least one whitespace-inflated box**, so
  this is systemic; per the brief the DATA repair is scoped to 05-prep, whose two slots
  were recomputed from its own evidence with the corrected rule (x .5597->.5770 and
  .5597->.5746; widths tighten correspondingly, right edges preserved).
- **The render comes from a second artifact.** 05-prep is a TEMPLATE, so
  `scaffold_slide_from_component.py` builds from `preview/preview.html`, which had the
  same bad geometry baked in independently of `text-slots.json` — repairing the contract
  alone did NOT fix the render. Regenerated `preview.html` + `thumbnail.png` through the
  repo's own `generate_template_preview.py` (mirroring the staging layout it expects);
  the diff is exactly the two repaired slots plus the generator's title/timestamp.
- **P2 — the metadata was internally inconsistent.** Measured heroes: circle 2 is h1 at
  134.02px against h2 at 61.11px and 53.44px (~2.2x). One hero flanked by two supports —
  which its own `use_cases` always said ("3 ranked highlights", "company track-record").
  The tier vocabulary in `intent`/`tags` contradicted both, and `"steps"` contradicted its
  own anti_use_case about sequences. Corrected truthfully: dropped
  ranking/levels/tiers/cap-do/thang-bac/xep-hang/steps, added achievements/track-record,
  restated `visual_summary` with the measured asymmetry, and added an anti_use_case
  naming the balanced-tier exclusion with its numbers. No scorer branch knows this id.
- **P2 alignment — the capability already existed; only the data was wrong.** Within each
  circle every slot's box CENTRE agrees to 6-18px across 4-5 slots: the design centres
  text on the circle's axis. `horizontal_align` was `left`, derived from the source's
  `text-anchor="start"` — meaningless when the source places every glyph at an absolute
  x. `scaffold_slide_from_component` already maps `horizontal_align: center` to
  `justify-content/text-align: center`, so the fix is 13 data values on this component
  only. The global default stays `left`; a test pins that.
- Both slot-contract edits correctly invalidated their immutable-text audits
  (`slots_sha256` drift). Re-audited each item, confirmed from the fresh empty-slot
  renders that both remain `clean` (05-prep: zero words, only folder art + checkbox
  glyphs; circles: zero words), and re-recorded the fingerprints.
- Added `build_component_catalog.py --check` — the verification loop calls it and it did
  not exist. Same gate `build_registry --check` applies to its own projections; verified
  it detects real drift and passes when clean.

**Result:** `test_gates.py` **273/273** (4 new: whitespace-glyph trimming keeps the box
and example_value describing the same glyphs; an end-to-end extraction where two sibling
rows — one space-prefixed — land on the same left edge; the asymmetric component is not
tier-shaped yet stays timeline/milestone-reusable; the slot-contract alignment is honoured
where evidence supports it and the default is untouched). py_compile clean;
`validate_registry` 91; `build_registry --check` clean; retrieval index `--check` 91;
`build_component_catalog --check` clean 91; `build_log_index --write/--check` up to date;
`git diff --check` clean. QA deck (`component-contract-qa-20260716/runs/qa-01`, ignored):
3 slides, all AUTOMATIC reuse, published, no custom-local — strict selection PASS, brand
PASS, fidelity `--render --require-render` PASS, PPTX layered `pass: true`, PDF, 3
screenshots inspected, 714 rendered characters with no source-specific text. Selection
proof: the balanced `tiers` request now filters the circle component OUT of the pool
(`shape_eligible=false`) and returns `needs_component` rather than forcing a weak reuse,
while a `milestones` request — what the component actually is — selects it at 95.0 and
renders centred on each circle's axis.
**Found while testing, kept:** the overflow gate cannot see a WRAP when the box is taller
than one line ("Thử nghiệm" wrapped inside a 67px box and passed). Caught it with a
line-count check in the QA loop and shortened the copy; the gate itself is unchanged.

**Tester pass (independent) — no blocking defect; the repair verified from three angles:**
- The width change looked wrong at first (x moved +33.28px but width shrank 49.66px). The
  evidence explains it exactly: the run is `' Hình dung … từng '` — leading AND trailing
  space — so the right edge legitimately pulls in 16.38px. 33.28 + 16.38 = 49.66. Not a
  bug.
- `validate_text_slots.py` CONSUMES `character_range`, which the fix shifts, so it was the
  obvious break candidate. It passes ("valid") because its coverage check already skips
  `character.isspace()`: the repo's own contract model ALREADY says whitespace is not
  content — the extractor's box was the only thing that disagreed. That is the strongest
  evidence the fix matches intent rather than merely satisfying a new test.
- The repair is reproducible from the evidence, not hand-typed: the sibling gap that was
  33.28px is now 0.01px, and `h-nh-dung` x = 0.5770 = the evidence's first-inked glyph.
- Known limitation (not fixed): `split_runs` cannot trim when a tspan carries one x for
  the whole string, because the space's advance is unknowable without font metrics (a
  dependency the repo does not have). Measured with the extractor's own entity-decoding:
  **0 of 2203** source tspans take that path, so it is theoretical here. An earlier
  measurement of mine said 77/17 — that was my analysis script failing to decode `&amp;`,
  not a real exposure; corrected. The trimmable, whitespace-padded population is 648 runs
  across 82 items.
No dependency, no scorer special case, no canonical brand asset touched, nothing deleted.
`.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/extract_editable_text_slots.py, slide-system/scripts/build_component_catalog.py, slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, slide-system/catalog/catalog-data.json, slide-system/library/templates/interview-workshop-sunriser/05-prep/text-slots.json, slide-system/library/templates/interview-workshop-sunriser/05-prep/preview/preview.html, slide-system/library/templates/interview-workshop-sunriser/05-prep/preview/thumbnail.png, slide-system/library/components/diagrams/sun.component.foundation-top1-microsoft-overlap-circle-set/text-slots.json, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/component-contract-qa-20260716/ (ignored)
**Symbols:** extract_editable_text_slots.split_runs, extract_editable_text_slots.extract_item, build_component_catalog.main, scaffold_slide_from_component.build_slot_scaffold, generate_template_preview.generate_preview_html
**State:** Not committed

---
## 2026-07-16.8 — Fingerprint preview.html (P1 audit bypass); render-fitness guard (P2 milestone crop)

**Request:** Fix two verified findings. P1: the immutable-text fingerprint hashed only
visual.svg + text-slots.json, but scaffold_slide_from_component.py reads preview.html at
build time for a template's slot markup/geometry — so editing preview.html alone left the
fingerprint unchanged and the verdict `clean` (a real audit bypass). P2: the latest
milestone QA slide's "3/3 manager-ready" was not supported — the three-circle component's
outer circles are cropped off the 1920x1080 frame and its outer labels sit on light
gradient; fidelity cov=1.0 proves geometry, not readability. Also review the whitespace
split_runs repair.

**P1 — one shared render-input set, fail closed on any of them.**
- Reproduced first: with only preview.html changed, `immutable_text_drift` was None and
  `gate_immutable_text` returned `clean`. Confirmed the scaffold reads paths.preview for
  `.slot` markup + geometry, so preview.html decides the render.
- Added `build_registry.RENDER_INPUT_FIELDS` (visual, preview, text_slots) + `render_input_files()`
  as the SINGLE place that answers "which files decide the render"; `immutable_text_fingerprint`
  now hashes every one that is a real file. A visual+preview+slots template gets a 3-key
  fingerprint; a raster-only asset still binds via preview; Dio (directory preview) still
  exempt. `immutable_text_drift` already covered preview_sha256, so scorer preflight,
  compact staleness, full-registry in-memory projection, and pre-build fidelity all fail
  closed on preview drift automatically — no per-module re-derivation.
- The change flipped all 89 published visual-items to `unresolved` (evidence lacked
  preview_sha256) — the correct fail-closed consequence. Re-audited through the real
  workflow: full rendered audit of 91 items (90 rendered + 1 not-applicable) into
  `outputs/slide-jobs/component-contract-qa-20260716/reaudit-20260716/`, mode=rendered
  status=complete. Confirmed NO verdict-relevant change (0 items with uncovered source
  text; spot-checked the PR-2025 immutable render still shows its baked lockup; every
  audit fingerprint now carries preview_sha256 and matches the live function). Backfilled
  evidence = `immutable_text_fingerprint(item)` (real bytes, not hand-typed) on 89 items,
  preserving verdicts; rebuilt registry/compact/retrieval/catalog.

**P2 — render fitness is distinct from contract fidelity.**
- Root cause: the circle component's artwork is a wide band (aspect 3.23:1); the scaffold's
  `background-size:cover` scales it to fill the 1080px height, so 45% of its width — the
  outer two circles — is cropped off the frame (pure geometry: viewBox aspect vs canvas).
  Corroborating: outer-circle white labels measured WCAG ~2.2-3.9 on the light gradient.
- Added deterministic, dependency-free helpers to validate_component_fidelity.py:
  `cover_crop_fraction()` (arithmetic) and `render_fitness(item)` (flags >30% cover-crop,
  the wide gap between the library's near-16:9 items <=16% and its wide-band strips >=33%).
  Surfaced per reused item in the fidelity report as `render_fitness_advisories` and a
  `[FITNESS]` stderr line — ADVISORY, distinct from the contract pass/fail (which stays
  geometry-only), because intentional edge-bleed layouts must be confirmed by a human, not
  auto-rejected.
- Disposition for the one component I visually confirmed unfit: recorded
  `auto_reuse: {eligible: false, reason: <measured crop + contrast evidence>}`. The scorer
  already reads that flag, so it is now blocked from automatic selection while staying
  published and browseable in the catalog + retrieval index. Made the fidelity-vs-fitness
  distinction explicit in build-html-deck.md.

**Whitespace split_runs:** reviewed and KEPT — it trims leading/trailing whitespace glyphs
before measuring so the box and `example_value` describe the same glyphs; interior spaces
untouched; char ranges stay consistent. Regressions retained/confirmed (leading, trailing,
interior, line-wrap, and the end-to-end sibling-alignment case).

**Result:** `test_gates.py` **278/278** (5 new: preview.html is a fingerprinted render
input; preview-only drift invalidates a real template end-to-end via all three CLIs;
cover_crop_fraction math; render_fitness flags severe crop not normal components; the
severe-crop component is review-only + not auto-selected but stays browseable. Updated 3
pinned tests: REVIEW_ONLY_IDS gained the circle component; the bare-marker fidelity test
now picks an eligible slot-contract component dynamically). py_compile clean;
validate_registry 91; build_registry --check clean; retrieval --check 91; catalog --check
clean 91; build_log_index --write/--check up to date; git diff --check clean. Fresh QA
deck (`component-contract-qa2-20260716/runs/qa-01`, ignored): the milestone request now
correctly returns `needs_component` (citing the review-only evidence) rather than
auto-placing the cropped component; the deck's two reuse slides (cover + repaired prep)
pass strict selection, brand, fidelity --render --require-render, PPTX layered pass:true,
PDF; both screenshots inspected manager-ready (prep's two checkboxes share one left edge
after the whitespace fix; no collision/clipping); 629 rendered chars, no source-specific
text.
**Residual risk:** 9 other wide-band components also exceed the crop advisory threshold;
they are surfaced by render_fitness but NOT auto-flipped (only the one visually confirmed
was blocked) — they await human review. No dependency added, no canonical brand asset
touched, no scorer special-case, nothing deleted. `.mcp.json`/`opencode.jsonc` untouched.
Not committed.

**Files:** slide-system/scripts/build_registry.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, slide-system/catalog/catalog-data.json, slide-system/workflows/build-html-deck.md, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/component-contract-qa-20260716/reaudit-20260716/ (ignored), outputs/slide-jobs/component-contract-qa2-20260716/ (ignored)
**Symbols:** build_registry.RENDER_INPUT_FIELDS, build_registry.render_input_files, build_registry.immutable_text_fingerprint, validate_component_fidelity.cover_crop_fraction, validate_component_fidelity.render_fitness, validate_component_fidelity._visual_viewbox, validate_component_fidelity.main
**State:** Not committed

---
## 2026-07-16.9 — Fingerprint visual.svg local image deps (P1 deeper); crop-advisory axis (P2)

**Request:** Independent review found P1 still open one level down: `RENDER_INPUT_FIELDS`
covers the three declared `paths.*` files but not the local image assets that
`materialize_component_visual.inline_external_images` base64-inlines from `visual.svg`
(`<image href="assets/tile.png">`). 24 published visuals reference such assets; mutating
only `tile.png` left `immutable_text_drift` None and the verdict `clean` — same bypass
class, deeper. Also: `render_fitness` always says "width" cropped even for portrait
artwork.

**P1-deep — one shared dependency model, fail closed on any referenced asset.**
- Reproduced first on real data (`sun.sun-presentation.01-cover`): mutating one referenced
  raster left the audit `clean`.
- Extracted the ref classifier `_classify_ref` + `image_dependencies(svg, base_dir)` in
  `materialize_component_visual.py` (returns `(safe=[(ref, Path)], unresolved=[ref])`);
  refactored `inline_external_images` to use `_classify_ref`, so the inlined set is exactly
  `image_dependencies(...)[0]` — materialization and the audit can never disagree on which
  refs are safe/local/resolved (data:/http/# external, absolute/traversal/missing unsafe).
- `build_registry.visual_dependencies(item)` reuses that helper.
  `immutable_text_fingerprint` now adds `deps_sha256`: a sha256 over sorted
  `<reference-identity>\t<content-hash>` lines for the safe local deps (content-only,
  machine-independent, no mtimes/abs paths). `immutable_text_drift` iterates it;
  `gate_immutable_text` additionally fails closed when a visual references any
  missing/unsafe local dep (it cannot be materialized). Evidence schema + validator
  whitelist gained `deps_sha256`.
- The change flipped exactly the 24 dep items to `unresolved` (evidence lacked
  deps_sha256); 0 items had pre-existing unsafe/missing deps. Re-audited those 24 through
  the real workflow (24 rendered, mode=rendered/status=complete,
  `outputs/slide-jobs/component-contract-qa2-20260716/reaudit-deps-20260716/`); confirmed
  NO verdict change (0 uncovered source text; every audit fingerprint now carries
  deps_sha256 and matches the live function). Backfilled evidence from
  `immutable_text_fingerprint` (real bytes) on the 24, rebuilt registry/compact/retrieval/
  catalog.

**P2 — crop advisory names the real axis.** `render_fitness` now derives the cropped axis
from the aspect: a WIDE artwork loses width off the left+right edges, a TALL one loses
height off the top+bottom. `cover_crop_fraction` is unchanged (it already measured either
axis). The circle component's advisory is unchanged in substance (still WIDTH / left-right)
and its review-only status is untouched.

**Result:** `test_gates.py` **284/284** (6 new: local raster dep is fingerprinted;
mutating it alone → unresolved; missing/unsafe dep fails closed; data:/http/# are not deps;
build_registry and materialization agree on the ref set; dependency-only drift fails closed
end-to-end on real data through all four gates; plus the tall-artwork axis-wording test and
a stronger assertion on the wide one). py_compile clean; validate_registry 91;
build_registry --check clean; retrieval --check 91; catalog --check clean 91;
build_log_index --write/--check up to date; git diff --check clean. Isolated real-CLI
reproduction on `sun.sun-presentation.01-cover`: mutate only the referenced
`image-01-*.png` → fresh projection marks it unresolved (deps_sha256 changed); `--check`
reports DRIFT and the canonical compact scorer refuses (no report written); full-registry
scoring projects it unresolved without writing; pre-build fidelity rejects a report that
selected it; restoring the asset returns everything to clean. (An accidental 13-byte junk
file created by a mangled shell path in a first repro attempt was removed; the real 22751-
byte asset is intact and unmodified.)
**Dependency-fingerprint contract:** evidence gains `deps_sha256` =
sha256(sorted("<ref>\t<sha256(file)>" for each safe local <image> ref)); absent when the
visual references no safe local image; a missing/unsafe referenced dep makes the item
`unresolved` (fail closed), matching materialization's refusal.
No dependency added, no canonical brand asset modified, no scorer special-case, preview.html
and whitespace repairs retained. `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Files:** slide-system/scripts/materialize_component_visual.py, slide-system/scripts/build_registry.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/validate_registry.py, slide-system/schemas/visual-item.schema.json, slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, slide-system/catalog/catalog-data.json, docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/component-contract-qa2-20260716/reaudit-deps-20260716/ (ignored)
**Symbols:** materialize_component_visual._classify_ref, materialize_component_visual.image_dependencies, materialize_component_visual.inline_external_images, build_registry.visual_dependencies, build_registry._visual_dependency_fingerprint, build_registry.immutable_text_fingerprint, build_registry.immutable_text_drift, build_registry.gate_immutable_text, validate_component_fidelity.render_fitness
**State:** Not committed

---

## 2026-07-16.10 — RC QA: layered PPTX export silently shipped a broken deck; fail-closed geometry guard

**Request:** Independent end-to-end release-candidate QA on the dirty branch. Pick a real
6–9 slide brief (not the small component-contract QA brief), stand up an isolated job, run the
current selection + generation pipeline (published-only, no explicit IDs / override /
custom-local), export a real editable PPTX + PDF, and QA every slide grounded in the
screenshots. Fix any pipeline regression found with a focused test + smallest generic fix.
Do not mutate the shared library/registry or `.mcp.json`/`opencode.jsonc`; do not commit.

**Brief + selection (unchanged from .88/.89):** `docs/intent/ai-workflow-deck-brief.md`
(canonical 9-slide SUN.STUDIO "AI WORKFLOW"). Job
`outputs/slide-jobs/release-candidate-qa-20260716/runs/rc-01`. Faithful per-slide requests
scored through the normal pipeline → **1 reuse + 8 needs_component**, 0 custom-local, 0
override. s1-title-hook → `sun.interview-workshop-sunriser.01-cover` (95.0, published,
auto-eligible); s2–s9 needs_component, each reason naming the real best candidate + score.
Strict selection validation PASS.

**Defect found (severe, pre-existing — NOT introduced by this RC): the layered PPTX export
silently shipped a broken deck, and the parity gate passed it.** Tester pass on the first
export found the PPTX carried, on EVERY slide, the whole deck's text (39 `<a:t>` runs) and
slide-1's background, at a 1.45in×7.5in sliver slide size. Root cause traced from source:
`capture-slides.js` has no per-slide navigation unless `--showJs`/`<deck-stage>` is given
(`showJs = a.showJs || (hasDeckStage ? … : null)`), so a deck whose slides are all visible at
once is captured with `root = document.body` → every slide records the full-deck scroll height
as `canvasH` (RC: 9912 = 9×1080 + 8×24px margins) and the whole deck's text. `build_layered`
then blindly trusted that `canvasH`, so `slide_dimensions(1920, 9912)` → (1.45, 7.5) and every
base PNG was slide-1. The parity gate never caught it because it compares the export's OWN
composed PNG (base+text) against the same-frame reference — slide-1-vs-slide-1 nine times
(0.17% "match"). Confirmed pervasive: every stacked-section QA deck since 2026-07-13 qa-05
shows the `width × slide_count ≈ 13.3in` signature; the 2026-07-10/13 qa-01..04 decks (which
paginate one slide per frame) are correct.

**Fix (TDD, generic).** Added `resolve_layered_geometry(manifest)` to `build_hybrid_pptx.py`:
each slide's captured canvas must not exceed the declared capture viewport (manifest
`canvasW/canvasH`) beyond a 2% tolerance; otherwise the deck was captured un-paginated and the
build FAILS CLOSED with a message naming the fix. `build_layered` now derives the slide size
from that guard. 3 focused tests (accept a 1080 single-slide canvas; reject a 3×-stacked
whole-deck canvas; tolerate 1px rounding). Red→green on the RC manifest itself (rejects
1920×9912). Documented the deck pagination contract in `slide-generator/SKILL.md` step 10 —
the root-cause guidance gap that let non-paginated decks be authored.

**Corrected deliverable.** Regenerated the RC deck with the proven `.slide`/`.slide.active` +
`goToSlide(n)` pagination contract (+ `@media print` un-pagination for the PDF); re-exported
with `--showJs "goToSlide({n})" --selector ".slide.active"`. Corrected PPTX: sldSz
13.33×7.5in, distinct per-slide backgrounds, per-slide `<a:t>` runs [7,4,4,4,4,4,4,4,4], native
editable text per-slide-correct with intact Vietnamese diacritics. tier1 parity 0.0 on all 9;
tier2 7/9 pass. **Residual (minor, sub-visual):** tier2 parity marginally fails slide-03
(changed-ratio 1.12%) and slide-05 (1.55%) vs the 1% budget (mean_err 0.55/0.77 ≪ the 1.0
budget) — text-edge anti-aliasing from the transparent-text-layer compose on the two most
text-dense placeholders; visually clean, not a manager-visible defect. Not gamed (no diagnostic
content trimmed, no threshold relaxed). PDF: 9 distinct pages. Brand OK (1 WARN: `#e9e9e9` page
backdrop, below fail threshold). Fidelity PASS (s1 reuse cov=100%). All 9 slides visually
inspected at 1920×1080 — no overlap/clip, correct diacritics, honest needs_component gates.
Honest reuse caveat: on s1 the brief's hook renders as the cover's small subtitle and the
visual anchor is the component's icon-grid/SUN.RISER lockup, not the brief's requested DIO
character.

**Result:** `test_gates.py` **287/287** (3 new geometry-guard tests); `test_export_stack.py`
full layered chain PASS (guard has no false positive on a paginated deck). py_compile clean;
validate_registry 91; build_registry --check clean; retrieval --check 91; catalog --check
clean 91; strict selection validation PASS; git diff --check clean (LF/CRLF warnings only).
Shared library/registry, canonical brand assets, `.mcp.json`/`opencode.jsonc` untouched. Not
committed.

**Files:** slide-system/scripts/build_hybrid_pptx.py, slide-system/scripts/test_gates.py, .agents/skills/slide-generator/SKILL.md, outputs/slide-jobs/release-candidate-qa-20260716/ (ignored), docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl
**Symbols:** build_hybrid_pptx.resolve_layered_geometry, build_hybrid_pptx.build_layered, build_hybrid_pptx.slide_dimensions
**State:** Not committed

---

## 2026-07-16.11 — Default export path: auto-detect capture navigation, cache + parity fixes, fresh RC deck

**Request.** Independent review reproduced that the DEFAULT export command (no
`--showJs`/`--selector`) still shipped a broken PPTX on the corrected paginated deck: exit 0,
`pass: true`, but all 9 slides had the same background SHA and slide 1's 7 text runs. The
`resolve_layered_geometry` guard from .10 only catches whole-document canvas height — not a
paginated `.slide.active` deck captured with no navigation, where every frame stays on slide 1.
Also flagged: `capture_fingerprint` omitted `showJs`/`selector`; and two text-dense slides
false-failed the tier2 changed-ratio budget on pure text-edge AA. Then run a fresh E2E RC deck
through the PUBLIC/default command.

**Reproduced first (not trusted).** `export_pptx.py … --mode layered` (no nav flags) on
`release-candidate-qa-20260716` deck → 9 identical base SHAs (`bffb2703…`), 7 identical runs,
canvasH=1080 on every slide (so the geometry guard passed it). Confirmed the gap.

**Root causes + fixes (generic, no hardcoded job/slide/component):**
- **P1 default capture (capture-slides.js).** `showJs`/`selector` resolved to `null` when
  neither flag nor a `<deck-stage>` was present, so the per-slide loop never navigated. Added
  auto-detection: for `--slides > 1` with no explicit nav, probe the page for a global
  `goToSlide(n)` over a `.slide` collection; if present, drive `goToSlide({n})` + `.slide.active`;
  otherwise `die()` with an actionable message (never capture slide 1 N times and report
  success). Explicit flags and `<deck-stage>` unchanged.
- **P1 build backstop (build_hybrid_pptx.assert_capture_navigated).** Fail closed when a
  multi-slide manifest has ONE background SHA AND identical text on every slide (slide-1-repeated
  signature). Distinct text on a shared solid background (the needs_component placeholders) is
  allowed — a legitimate repeated background, explained from source.
- **P1b cache (export_pptx.capture_fingerprint).** Added `showjs`/`selector` so a nav/selector
  change invalidates the capture cache (auto-resolved nav stays covered by the existing
  `capture_script_sha` + `html_sha`).
- **P2 parity (compare_renders + validate_export_objects + export-qa-thresholds.json).** Added
  `significant_changed_pixel_ratio` = changed pixels surviving a 1px erosion (`MinFilter(3)`).
  The secondary edge-coverage guard now compares that instead of the raw changed_ratio (threshold
  value UNCHANGED at 0.01); `mean_err` stays the primary guard; pre-erosion reports fall back to
  the raw ratio. Calibrated on real slide-05: faithful worst significant 0.000014, mean ≤ 0.77;
  2px shift 0.0143 / mean 6.3; wrong slide 0.0242 / mean 9.5; 1-missing-word mean 1.26 (caught by
  mean). No threshold relaxed, no content trimmed, no report marked pass — text-AA now passes
  while every real displacement/missing/wrong/duplicate still fails.

**Tests (TDD).** test_gates.py +7: build backstop rejects slide-1-repeat / accepts shared-solid-bg
distinct-text / accepts distinct bg; capture_fingerprint invalidates on nav+selector; significant
ratio drops thin edges keeps solid blocks; parity gate passes AA-halo but fails 2px shift; parity
falls back to raw ratio pre-erosion. test_export_stack.py +Job F: F1 DEFAULT command auto-detects
goToSlide → distinct slides; F2 stacked deck (no navigator) fails closed. Both wired into the
verdict/exit code.

**Fresh E2E RC deck (`release-candidate-qa2-20260716`, PUBLIC/default command).** Canonical
9-slide brief `docs/intent/ai-workflow-deck-brief.md`. Scored via the normal pipeline (published
retrieval index, no explicit IDs, no override): 1 reuse (`sun.interview-workshop-sunriser.01-cover`
95.0, published + auto-eligible + immutable-clean) + 8 needs_component; 0 custom-local. Strict
selection validation PASS. Exported with `export_pptx.py --html … --slides 9 --out-dir … --output …
--mode layered` (NO `--showJs`/`--selector`/`--no-cache`) → exit 0. Raw-artifact proof: PPTX sldSz
13.333×7.5in 16:9, 9 slides, 9/9 DISTINCT per-slide `<a:t>` sets, runs [7,4,4,4,4,4,4,4,4], 2
distinct backgrounds (cover + one shared solid placeholder bg — explained), tier1+tier2 parity all
9 PASS (significant 0.0). PDF 9 pages. Brand OK (1 WARN `#e9e9e9` backdrop). Fidelity --require-render
PASS (s1 reuse cov=100%). All 9 screenshots inspected at 1920×1080: no overlap/clip, correct
Vietnamese diacritics, honest needs_component gates. Honest reuse caveat on s1 (brief hook renders
as the cover's subtitle; anchor is the component's icon-grid/SUN.RISER lockup, not the brief's DIO).

**Result.** py_compile clean (Python) + `node --check` (capture-slides.js); test_gates.py
**294/294**; test_export_stack.py --json all 7 jobs PASS incl F1/F2; validate_registry 91;
build_registry --check clean; retrieval --check 91; catalog --check clean 91; strict selection
PASS; brand + fidelity PASS; git diff --check clean (LF/CRLF advisories only, on pre-existing
files). Shared library/registry/canonical brand assets and `.mcp.json`/`opencode.jsonc` untouched.
Not committed.

**Residual risks.** (1) No `<deck-stage>` fixture in test_export_stack — deck-stage validity rests
on the unchanged "showJs is set → auto-detect skipped" branch (exercised by Jobs A/D explicit
flags). (2) PDF↔HTML agreement is by-construction (same deck.html, print media) + verified page
count, not pixel-diffed (no PDF rasterizer installed). (3) The 8 needs_component slides are honest
UNRESOLVED gates, not finished business slides — the deck is a pipeline-correctness artifact, not a
delivered client deck.

**Files:** slide-system/scripts/capture-slides.js, slide-system/scripts/build_hybrid_pptx.py,
slide-system/scripts/export_pptx.py, slide-system/scripts/compare_renders.py,
slide-system/scripts/validate_export_objects.py, slide-system/registries/export-qa-thresholds.json,
slide-system/scripts/test_gates.py, slide-system/scripts/test_export_stack.py,
.agents/skills/slide-generator/SKILL.md, outputs/slide-jobs/release-candidate-qa2-20260716/ (ignored),
docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl
**Symbols:** capture-slides.js:main (nav auto-detect), build_hybrid_pptx.assert_capture_navigated,
export_pptx.capture_fingerprint, compare_renders._compare_images, validate_export_objects.check_parity
**State:** Not committed

---

## 2026-07-16.12 — DECISION NOTE: semantic concept-group scoring (before implementation)

**Problem (live data).** `score_request` computes `semantic = |canon(intent+tags) ∩ item| / |canon(intent+tags)|`
— every distinct canonical concept in intent AND tags is an AND requirement. Measured on the canonical
9-slide brief: timeline s7 vs `02-timeline` = 2/3 (missing orphan tag `flow`), closing s9 vs `18-thanks`
= 2/3 (missing descriptor `cta`) — both 23.33, narrowly under the 24.5 (70%×35) bar despite total 83.33.
The dilution terms sit in DIFFERENT fields (s7 tags, s9 intent), so neither "intent-only" nor
"tags-optional" denominator fixes both.

**Rejected — derive the required concept from `content_shape` (SHAPE_TYPE_MAP).** Prototyped: too coarse.
The shape family is broad (`profile` ⊇ roles/personas/team; `timeline` ⊇ process/instructions), so a single
shape-concept group flips ALL 9 slides to reuse — including forcing an action-items list onto the role-cards
slide and one prep component onto two slides. That is exactly the "force all slides to reuse" the task forbids.

**Chosen — Option 1a: optional `concepts` field = list of OR-groups, AND across (smallest backward-compatible
representation).** A request MAY declare `concepts`: `[[t1,t2,…], …]` where terms in a group are OR
alternatives and groups are AND requirements. When present, `semantic = matched_groups / total_groups`
(a group matches if the item's canonical terms intersect any group term); `intent`/`tags` stay RETRIEVAL-only
(prefilter, capped secondary enrichment, ranking) and no longer inflate the required denominator. When ABSENT,
the exact current `canon(intent+tags)` behaviour is unchanged — legacy requests are byte-identical. Terms are
canonicalized (reusing `_canonicalize`), so within-group synonyms already fold; the model adds only the
AND/OR grouping the flat set cannot express.

Why smaller/safer than lowering `SEMANTIC_CONFIDENCE_FRAC`: the 70% bar and every safety gate stay UNCHANGED.
A lower fraction would loosen EVERY request uniformly (including keyword-lucky matches); concept groups instead
let the author state which concepts are essential (OR-equivalents count once; descriptors like `flow`/`cta`
become optional tags, not requirements) and ADD discrimination beyond shape (a role-cards slide requires role
AND card-layout → an action-items list with `roles` but no card layout scores 1/2 = 0.5 < 0.70 and stays
`needs_component`; a principles slide requires `principle`/`rule` → a prep checklist that is shape-eligible but
declares neither scores 0/1 and stays `needs_component`). Prototype on the canonical brief with faithful
specific concepts: cover + timeline(02-timeline) + process(05-process) + closing(18-thanks) reuse; roles,
app-choice, tiers, principles, tips stay `needs_component`; review-only (spicy-autocomplete) stays blocked by
the unchanged `auto_reuse` gate. No embeddings/vector DB/LLM/new deps; no taxonomy framework (groups are
per-request data, reusing the existing SYNONYMS for folding).

**Scope.** (1) scorer: group-coverage semantic + capped secondary over unmatched groups; explanation with
required/matched/missing groups. (2) needs_component: ranked SAFE shortlist with per-candidate missing concepts;
never auto-selects. (3) schema + `validate_batch_request` parity for the optional `concepts` field. (4)
content_shape: prefer the existing generic derivation (shape_eligible) — add a deterministic
`derive_content_shape` helper for explanation only; NO mass registry backfill. (5) TDD fixture on canonical
vocabulary (not slide text). Gates (published-only, auto_reuse, immutable, shape, slots, dedup) UNCHANGED.

---

## 2026-07-16.13 — Semantic concept-group scoring: implementation, tests, canonical-brief eval

**Implemented** the concept-group model from the .12 decision note (retrieval/scoring quality, independent
of the export fixes).

- **score_visual_items.py** — `_concept_groups(request)` reads the optional `concepts` field (list of
  OR-groups, AND across); `_concept_coverage(groups, item_terms, record)` returns
  matched_groups/total_groups plus a required/matched/missing report, with the SAME capped, below-floor
  secondary credit on unmatched groups. `score_request` uses it when `concepts` is present and falls back to
  the exact flat `intent+tags` denominator when absent (legacy requests byte-identical). Added `concepts` to
  `_SLIDE_REQUEST_FIELDS` + validation. Every safety gate (published-only, `auto_reuse`, immutable, shape,
  slot, dedup) and the 78/24.5 bars are UNCHANGED.
- **needs_component shortlist** — `_safe_shortlist()` surfaces up to 3 SAFE published near-matches
  (auto-reuse-eligible + immutable-clean + slot-ready), each with its missing concept groups. Advisory only;
  never selects. Added `shortlist` to DECISION_FIELDS (validate_selection_report) + the report schema.
- **content_shape metadata quality** — `_common.derive_content_shape(tokens)` reverse-maps SHAPE_TYPE_MAP so
  the scorer reports each candidate's inferred shape(s) for auditability; NO label invented/stored on the 91
  registry items (generic derivation preferred over churn).
- **schemas** — `concepts` added to visual-requests.schema.json; `shortlist` to selection-report.schema.json;
  both kept in lockstep with the code validators (parity test passes).

**Tests (TDD).** test_gates.py +12: dilution no longer blocks a true timeline match; closing matches without
CTA; optional tags are not semantic requirements; AND-across blocks a 1/2 partial (role but no card);
zero-group match is needs_component; report lists required/matched/missing; review-only + published-only
boundaries hold under concepts; shortlist is safe and never selects; legacy (no concepts) keeps flat
dilution; a canonical-vocabulary eval fixture (positive timeline/closing + keyword-lucky + partial-AND
negatives); derive_content_shape generic + reported. Suite **306/306**.

**Canonical-brief E2E (`scoring-eval-20260716`, published-only, no IDs, no override, no custom-local).**
Same 9-slide `docs/intent/ai-workflow-deck-brief.md`; intent/tags retained, `concepts` authored faithfully
from the canonical vocabulary. BEFORE (flat): **1 reuse + 8 needs_component**. AFTER (concepts):
**4 reuse decisions + 5 needs_component**, strict-validation PASS:

| slide | before | after (concept decision) | why |
| s1-cover | reuse | reuse `01-cover` | cover concept 1/1 |
| s2-roles | needs | needs | best card-set is REVIEW-ONLY (2-card art vs 4-card contract) |
| s3-example-flow | needs | reuse `02-timeline` | process concept matched |
| s4-app-choice | needs | needs | no `choice/option` component (semantic 0) |
| s5-model-tiers | needs | needs | best `tiers` candidate is IMMUTABLE (`Performance Review 2025`) |
| s6-principles | needs | needs | no `principle/rule` component (below bar) |
| s7-skills-flow | needs | reuse `05-process` | process concept matched |
| s8-tips | needs | needs | no `tip/advice` component (semantic 0) |
| s9-closing | needs | reuse `18-thanks` | closing concept 1/1 |

The dilution is fixed (timeline/closing/process now semantic-match); review-only + immutable stay blocked by
the UNCHANGED gates; roles/app-choice/tiers/principles/tips stay needs_component (no matching concept). During
QA a too-broad s7 concept first matched a rollout-summary GRID (`16-update-summary`, tagged `timeline` but no
`process/steps`); tightening s7 to the faithful process concept fixed it → `05-process`. Not a code change.

**Honest finding (deck build).** The 3 new reuse matches (`02-timeline`, `05-process`, `18-thanks`) are
SOURCE-SPECIFIC published slides — their scaffolds carry 23 / 27 / 9 content slots of interview dates, 2026
goal-setting cascade, and salary-benefits policy copy. Their text is in EDITABLE slots (so immutable-clean),
but faithfully reusing them for the AI-workflow brief would require inventing business copy for ~20 surplus
slots each — the "forcing" the task forbids. A semantic-concept match is NOT the same as a fillable template.
Per "do not force / honest needs_component acceptable", the delivered deck builds only the genuine template
reuse (s1 `01-cover`, fidelity cov=100%) and marks s3/s7/s9 as honest "REUSE MATCH · NOT BUILT (source-
specific)" placeholders. Component-fidelity therefore FAILs by design (4 reuse decided, 1 built) — the gate
correctly flags the 3 unbuilt; that failure IS the finding, not a defect. Export via the DEFAULT command
(no `--showJs`/`--selector`/`--no-cache`): PPTX 13.33×7.5in 16:9, 9 slides, 9/9 distinct text, PDF 9 pages,
brand OK. All 9 screenshots inspected: clean, correct Vietnamese diacritics, no overlap/clip.

**Result.** py_compile clean; test_gates **306/306**; validate_registry 91; build_registry --check clean;
retrieval --check 91; catalog --check clean; strict selection PASS; brand OK; git diff --check clean.
Shared library/registry, canonical brand assets, `.mcp.json`/`opencode.jsonc` untouched. Not committed.

**Residual risks.** (1) Template-vs-source-specific: the scorer semantic-reuses source-specific slides with
editable slots as if templates — a real future-work signal (a "reusable-template" flag or slot-genericity
heuristic), out of scope here. (2) Concept authoring is per-request data (like intent/tags); a too-broad
group over-matches (seen + corrected for s7) — the canonical vocabulary + AND-across + the unchanged gates
bound the risk, but authoring quality still matters. (3) Deck fidelity FAILs by design (documented).

**Files:** slide-system/scripts/score_visual_items.py, slide-system/scripts/_common.py,
slide-system/scripts/validate_selection_report.py, slide-system/scripts/test_gates.py,
slide-system/schemas/visual-requests.schema.json, slide-system/schemas/selection-report.schema.json,
outputs/slide-jobs/scoring-eval-20260716/ (ignored), docs/logs/SESSION-LOG-2026-07-16.md, docs/logs/INDEX.jsonl
**Symbols:** score_visual_items._concept_groups, ._concept_coverage, .score_request, ._safe_shortlist,
_common.derive_content_shape
**State:** Not committed

---
