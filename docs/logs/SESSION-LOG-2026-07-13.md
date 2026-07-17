## 2026-07-13.1 — Audit plugin delivery readiness

**Request:** Assess the current slide-plugin progress and identify the remaining work required to complete it.
**Actions:**
- Inspected branch and pull-request state, the system README, registry/retrieval inventory, and the current export-QA commit.
- Ran the focused gate suite plus registry and retrieval projection integrity checks.
**Result:** The current branch passed `test_gates.py` (156/156), registry validation (91 items), registry drift check, and retrieval-index check (91 records). PR #5 remains open and clean; the current export-QA commit is one commit ahead of `master` without a pull request.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md
**Symbols:** none
**State:** Not committed

## 2026-07-13.4 — Review and correct Windows setup guidance

**Request:** Review the OpenCode release-readiness implementation against the live worktree and fix any remaining findings.
**Actions:**
- Re-ran the gate suite and full export stack with the repository virtual environment; ran an isolated real PDF-to-Draft workflow and validated its catalog schema.
- Reviewed the plugin command contract against official OpenCode documentation and checked the catalog publish error boundary.
- Replaced remaining active Windows-incompatible setup hints in export smoke, capability reporting, manual PDF conversion, and primary slide workflow documentation.
**Result:** `test_gates.py` passed 164/164 and the editable PPTX, PDF, read-back, layered export, object-separation, and decomposition smoke all passed with `.venv\\Scripts\\python.exe`. The isolated PDF workflow produced one `staging` Draft in catalog data and did not publish. Active user-facing setup guidance now directs Windows users to `setup.ps1`; remaining POSIX paths are explicitly macOS/Linux references.
**Files:** docs/flows/3layer-export.md, docs/flows/slide-generator-workflow.md, docs/logs/SESSION-LOG-2026-07-13.md, slide-system/scripts/convert_pdf_source.py, slide-system/scripts/test_export_stack.py, slide-system/scripts/update_capabilities.py, slide-system/workflows/build-html-deck.md, slide-system/workflows/save-as-template.md, slide-system/workflows/select-visual-items.md
**Symbols:** test_export_stack.SETUP_HINT, update_capabilities.SETUP_HINT, convert_pdf_source.INSTALL_HINT
**State:** Not committed

## 2026-07-13.2 — Identify Windows export-runtime mismatch

**Request:** Determine what still needs to be completed before the slide plugin can be released.
**Actions:**
- Ran the real `test_export_stack.py --json` smoke and compared its interpreter with the repository virtual environment.
- Verified imports directly with `.venv\\Scripts\\python.exe` and inspected the base requirements report.
**Result:** HTML-to-PDF and SVG decomposition passed, but editable PPTX and layered-export checks were skipped because the smoke uses the WindowsApps `python3` launcher rather than the project virtual environment. The project `.venv` itself has python-pptx 1.0.2, Pillow 12.3.0, and PyMuPDF 1.28.0. This is a Windows portability release blocker, not a missing local dependency.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md
**Symbols:** none
**State:** Not committed

## 2026-07-13.3 — Complete slide plugin release readiness

**Request:** Complete the remaining Standard PR release-readiness work so a non-technical Windows user can install/discover the skills, extract PDF components into review-only Drafts, review/publish through the catalog, reuse published items, and export editable PPTX/PDF reliably.
**Actions:**
- Confirmed branch `fix/export-parity-qa-cache` at `7c608a99` over `master` `b232d194`; preserved the existing `.mcp.json` and `opencode.jsonc` changes without editing them.
- Researched official Claude Code, Codex, and OpenCode skill/plugin/command conventions. Added a Claude plugin manifest and marketplace over the existing `.agents/skills` source, retained native Codex/OpenCode repo discovery, and added only the officially supported OpenCode `/component` command alias.
- Added a shared project-Python resolver for `.venv\Scripts\python.exe` on Windows and `.venv/bin/python3` on POSIX, then routed preflight, export orchestration, export smoke, and catalog subprocesses through it with platform-specific setup errors.
- Added the local Windows `setup.ps1`, updated setup and user documentation, and added `extract_pdf_components.py` to run PDF preflight, analysis, Draft staging, and catalog rebuild in order without publishing. When optional Docling is absent, PDF analysis now uses the approved PyMuPDF fallback.
- Added focused regression tests for Windows/POSIX resolver paths, missing/invalid venv hints, shared interpreter agreement, distribution entrypoints, preflight-before-staging order, and MarkItDown CLI fallback.
- Ran an isolated real PDF smoke on page 1 of `input/GUIDLINE_PRESENTATION_SUN.pdf` under `E:\Temp\opencode`: preflight was ready, PyMuPDF fallback found one candidate, one artifact-ready `staging` Draft appeared in isolated catalog data, and the canonical registry remained 91 items with no automatic publish.
**Result:** PASS. Python compile succeeded for all changed Python files. `python slide-system/scripts/test_gates.py` passed 164/164. Registry validation reported 91 items; registry and retrieval projections were clean. `python slide-system/scripts/test_export_stack.py --json` passed editable PPTX creation, native editable text, HTML-to-PDF, MarkItDown read-back, layered export, object separation, and SVG decomposition with project Python `E:\slide-plugin\.venv\Scripts\python.exe`. `setup.ps1 -Check`, strict Claude plugin/marketplace validation, Codex/OpenCode skill discovery, and OpenCode command discovery passed. No dependency was installed and no canonical registry/library/output artifact was changed.
**Files:** .agents/.claude-plugin/plugin.json, .agents/skills/component-extractor/SKILL.md, .agents/skills/extract-preflight/SKILL.md, .agents/skills/slide-generator/SKILL.md, .claude-plugin/marketplace.json, .gitignore, .opencode/commands/component.md, docs/how-to-use.md, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl, slide-system/README.md, slide-system/catalog/catalog_server.py, slide-system/scripts/_common.py, slide-system/scripts/analyze_with_docling.py, slide-system/scripts/check_base_requirements.py, slide-system/scripts/export_pptx.py, slide-system/scripts/extract_pdf_components.py, slide-system/scripts/setup.ps1, slide-system/scripts/setup.sh, slide-system/scripts/test_export_stack.py, slide-system/scripts/test_gates.py
**Symbols:** _common.ProjectPythonError, _common.project_python_path, _common.project_python_install_hint, _common.require_project_python, check_base_requirements.selected_python, check_base_requirements.probe_fitz, check_base_requirements.fingerprint_paths, check_base_requirements.evaluate, check_base_requirements.load_marker, check_base_requirements.write_marker, check_base_requirements.print_summary, check_base_requirements.main, test_export_stack.selected_python, test_export_stack.py_mod, test_export_stack.markitdown_command, test_export_stack.main, export_pptx.selected_python, analyze_with_docling.main, extract_pdf_components.WorkflowError, extract_pdf_components._run_step, extract_pdf_components.run_workflow, extract_pdf_components.main, catalog_server.selected_python
**State:** Not committed

## 2026-07-13.5 — Block historical selection curation in new slide jobs

**Request:** Investigate why a tester reported that a generated 9-slide deck used no published components and appeared to reuse old component decisions after deletion.
**Actions:**
- Traced the historical `ai-workflow-deck-eval-20260710` job, its raw and curated selection reports, validation output, rendered deck references, current registry entries, and the slide-generator instructions.
- Added a regression test that recreates a post-scorer `reuse` to `custom-local` override and requires the selection gate to fail; added a skill-contract regression test for new-job isolation.
- Hardened `validate_selection_report.py` to reject non-scorer curation fields and to fail when an action conflicts with the selected candidate score band; updated the slide-generator skill to prohibit reading historical logs/jobs for a new brief and editing scorer output.
- Compared the historical raw report and curated report with the hardened gate, then re-ran the full gate suite and registry/retrieval checks.
**Result:** The historical raw scorer report passes without shape-lock input; the curated report now fails with the injected curation fields and six `custom-local` overrides. The current registry still contains the two components referenced by that historical deck, so they were not deleted from this worktree. `test_gates.py` passed 166/166; registry validation and compact/retrieval index checks passed; `git diff --check` passed with line-ending warnings only.
**Files:** .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl, slide-system/scripts/test_gates.py, slide-system/scripts/validate_selection_report.py
**Symbols:** validate_selection_report._validate_report_fields, validate_selection_report._validate_decision_band, test_selection_report_rejects_manual_curation_override, test_slide_generator_requires_fresh_selection_for_new_jobs
**State:** Not committed

## 2026-07-13.6 — Independent QA: retrieval freshness + curation block

**Request:** Re-test the reported "all 9 slides custom-local" retrieval failure without editing implementation code; prove the historical curation is now blocked and that a fresh scorer run still produces published-component reuse.
**Actions:**
- Test A (regression proof, no code change): ran `validate_selection_report.py` on the historical `ai-workflow-deck-eval-20260710/runs/eval-01` reports. Raw scorer report `selection-report.raw.json` → PASS (exit 0). Curated `selection-report.json` → FAIL (exit 1) with band-conflict errors (`custom-local` conflicts with scorer band `reuse`/`adapt-local`) plus non-scorer field rejections (`curated_by`, and per-decision `curation_note`/`scorer_action`/`scorer_item_id`/`scorer_score`). Confirms the hardened gate blocks the exact historical override path.
- Test B (fresh, no historical state): created new ignored job `outputs/slide-jobs/retrieval-freshness-qa-20260713/runs/qa-01` with two brand-new component-fit requests (3-step workflow; 3-tier ranking). Real scorer → fq1 `reuse sun.component.goal-keyresult-task-hexagon-diagram` (88.33), fq2 `reuse sun.component.foundation-top1-microsoft-overlap-circle-set` (95.0); `validate_selection_report.py --visual-requests` → PASS. Report carries generated_by=score_visual_items.py, scorer_version 3.2.0, zero curation fields, both IDs present in the current registry. Directly refutes the "all custom-local" symptom.
- Test C (component-use smoke): scaffolded both reuse items via `scaffold_slide_from_component.py` (both are wired-slot-free → `.bg` + `data-base-component` fallback), built a minimal isolated 2-slide deck referencing only the two selected IDs (0 references to any prior job path), and ran `validate_component_fidelity.py` WITHOUT `--warn` (blocking) → PASS 2/2 (matched on data-base-component).
- Test D (regression/integrity, project venv `.venv\Scripts\python.exe`): py_compile PASS; test_gates 166/166; validate_registry 91; build_registry --check clean; retrieval index --check 91 clean; git diff --check clean (line-ending notes only).
- No implementation code changed; no registry/library/index/catalog mutated; no old log/job/deck used as generation input (only the two named historical reports for Test A regression verification).
**Result:** PASS. Historical curation is blocked by the current validator; a fresh scorer run produces genuine published-component `reuse` and passes selection + blocking fidelity gates. The reported "all 9 custom-local" was an artifact of the manually-curated historical report, not current scorer/retrieval behavior.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl (new ignored QA output under outputs/slide-jobs/retrieval-freshness-qa-20260713/)
**Symbols:** none (QA-only; no code changed)
**State:** Not committed

## 2026-07-13.7 — Audit new brief against fresh nine-slide selection

**Request:** Fetch and read newly pushed docs, then investigate a new evaluation claiming all nine AI-workflow slides became `custom-local` because the library is HR/office-only.
**Actions:**
- Fetched remote refs without pulling over the dirty worktree; inspected `origin/feature/template-component-ranking` commit `61ffbe55` directly.
- Read the updated `docs/intent/ai-workflow-deck-brief.md`; confirmed the commit only simplified the brief and removed an obsolete plan, with no new library-fit evaluation.
- Created a fresh ignored nine-request QA run derived from the new brief, ran the current scorer and selection gate, and preserved the output for review.
**Result:** The fresh scorer returned `reuse` or `adapt-local` for all nine taxonomy-based requests, disproving the ungrounded `9/9 custom-local` claim. The selection gate correctly failed one semantically wrong generic match: the Chat/Cowork/Code comparison was selected as a numbered badge set. The new brief also says not to render yet, so a build/export pipeline should not have been started. No registry, library, catalog, or source code was changed by this QA run.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl, outputs/slide-jobs/retrieval-freshness-manual-20260713/runs/qa-01/analysis/visual-requests.json, outputs/slide-jobs/retrieval-freshness-manual-20260713/runs/qa-01/analysis/selection-report.json, outputs/slide-jobs/retrieval-freshness-manual-20260713/runs/qa-01/analysis/selection-validation.json
**Symbols:** score_visual_items.score_request, validate_selection_report._validate_shape_lock
**State:** Not committed

## 2026-07-13.8 — Qualify independent retrieval QA conclusion

**Request:** Review Claude's independent QA output for the reported component-reuse failure.
**Actions:**
- Read the QA report and compared its stated Test A/B/C coverage with the existing fresh nine-slide selection audit.
- Separated evidence that proves the historical curation regression is blocked from evidence needed to establish retrieval quality for a real multi-slide brief.
**Result:** Claude's Test A/B/C proves that curated historical reports are rejected and that two deliberately exact requests can reuse published components with blocking fidelity validation. It does not prove general retrieval quality for the new nine-slide brief. The fresh nine-slide audit still exposes a scorer defect: a comparison request can select a generic numbered-badge component before the downstream shape lock rejects it. The next implementation priority is content-shape filtering inside scoring, ahead of preview-slot wiring.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md
**Symbols:** score_visual_items.score_request, validate_selection_report._validate_shape_lock
**State:** Not committed

## 2026-07-13.9 — Publish portable PDF Draft workflow for review

**Request:** Review the accumulated uncommitted implementation, commit the in-scope changes, push the branch, and create a pull request.
**Actions:**
- Reviewed the staged plugin, setup, extraction, export, selection-validation, test, and documentation changes; intentionally excluded pre-existing local runtime configuration diffs in `.mcp.json` and `opencode.jsonc`.
- Re-ran the full gate suite, registry and retrieval checks, export stack, Windows setup check, Claude plugin validation, OpenCode discovery, and an isolated page-1 PDF-to-Draft smoke.
- Committed the implementation as `75351da9`, pushed `fix/export-parity-qa-cache`, and opened ready PR #6 against `master`.
**Result:** PASS. `test_gates.py` passed 166/166; registry reported 91 valid items; registry/retrieval projections were clean; editable PPTX/PDF/layered export passed. The isolated PDF workflow created one review-only `staging` Draft and did not publish. PR: https://github.com/linhla0108/slide-plugin/pull/6
**Files:** docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl
**Symbols:** none
**State:** Not committed

## 2026-07-13.10 — Rebase template-component ranking on current master

**Request:** Rebase PR #5 after the portable PDF Draft workflow merged, preserve both retrieval behaviors, and verify the result before updating the pull request.
**Actions:**
- Rebasing `feature/template-component-ranking` onto `origin/master` required resolving derived log-index, daily-log, and test-suite conflicts.
- Retained component-intent template demotion, component-first strict shape coverage, anti-curation validation, and fresh-job isolation; regenerated `INDEX.jsonl` instead of hand-merging it.
- Used temporary ignored junctions for `.venv`, `input`, and `node_modules` in the isolated rebase worktree so the repository's integration tests could access the existing local toolchain.
**Result:** PASS. Python compile, `test_gates.py` (173/173), registry validation, registry/retrieval index checks, log-index check, and diff check passed. No registry/library/runtime config changes were introduced.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl, slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_selection_report.py, slide-system/scripts/test_gates.py, slide-system/workflows/select-visual-items.md
**Symbols:** score_visual_items.request_type_intent, validate_selection_report.SHAPE_TYPE_MAP, test_shape_lock_covers_component_first_shapes
**State:** Not committed

## 2026-07-13.11 — Shape-aware candidate eligibility in the scorer

**When:** 2026-07-13
**Request:** On a fresh branch from current master, re-run the AI-workflow brief
in a brand-new ignored baseline job with no code edits, confirm the root cause
from evidence, then (only if confirmed) fix it by making `content_shape` affect
candidate eligibility inside the scorer — shared canonical vocabulary with the
validator, auditable rejects, custom-local + extraction when nothing fits — via
a red-green test loop; re-run the brief and QA. Do not mutate the registry/
library/index/catalog, add dependencies, hardcode brief IDs, or commit.
**Actions:**
- Branched `feature/shape-aware-retrieval` from `origin/master` (7a740310). An
  external process advanced master to `f1d57a4c` (merged PR #5 template-component
  ranking) and rebased this branch onto it; re-read the current 560-line scorer +
  updated 10-shape validator vocab and re-ran the baseline against them (identical
  results — the new `request_type_intent`/`TEMPLATE_DEMOTION` is a no-op for these
  shape-only requests). The repo `.venv` had been emptied and its base Python 3.11
  removed; restored `.venv` as a bare 3.11.9 venv (setup-sanctioned) — the brief
  says do not render, so pptx/PIL/fitz are not needed for selection.
- Phase 1 (no code edits): ignored job
  `outputs/slide-jobs/ai-workflow-shape-baseline-20260713/runs/baseline-01`. Authored
  9 `visual-requests.json` from the brief only (no historical job/report/log used).
  Scored (`score_visual_items.py`) + validated (`validate_selection_report.py
  --visual-requests`) → PASS. Evidence: the scorer never reads `content_shape`, so
  s2 (profile) and s4 (comparison) ranked the shape-incompatible generic
  `lorem-ipsum-circle-badge-set` above the genuine role-card component
  `translator-strategist-driver-coach-card-set` (won via a broadened retrieval-index
  "comparison" hit); s9 (closing) shape is absent from the vocabulary. Confirmed
  structural mismatch → proceed to fix.
- Phase 2 (red-green TDD): added the single shared `SHAPE_TYPE_MAP` + `shape_eligible()`
  to `_common.py`; the scorer now computes per-candidate shape eligibility, keeps
  incompatible items in the report but marked `shape_eligible: false` with a
  "Shape mismatch" reason, and selects only shape-compatible candidates; when no
  published component fits the requested shape (including a shape outside the
  vocabulary) it returns `custom-local`, no `item_id`, `extraction_recommended:
  true`. The validator now imports the shared vocab (local copy removed) and its
  decision-band recompute honors `shape_eligible` so it cannot falsely reject a
  valid shape-filtered custom-local; `_validate_shape_lock` stays as defense in
  depth. 6 new tests added (5 new-behavior RED→GREEN + 1 anti-curation guard).
- Phase 3: second ignored job
  `outputs/slide-jobs/ai-workflow-shape-postfix-20260713/runs/postfix-01` with the
  identical requests. Post-fix: s2 → `translator…coach-card-set` (59.17, custom-local,
  extraction), s4 → same (53.34), s9 → no id (custom-local, extraction); s5 (tiers)
  and s7 (timeline) genuine matches preserved as adapt-local; s1/s3/s6/s8 unchanged.
**Result:** PASS. Post-fix validate PASS. `py_compile` clean;
`test_gates.py` 179/179 (from repo root — the 2 transient failures were a CWD
artifact of running inside `scripts/`); `validate_registry.py` 91 valid;
`build_registry.py --check` clean (registry untouched); retrieval index `--check`
clean 91; `git diff --check` clean (CRLF notes only). Scope: only the 4 scripts +
these logs changed; registry/library/catalog/canonical assets and `.mcp.json`/
`opencode.jsonc` untouched; no new dependencies; no hardcoded brief/component IDs.
Residual: s7 still reuses the over-tagged `foundation-…-overlap-circle-set` for a
step timeline (metadata-quality, not shape-fixable here); `closing` remains outside
the shape vocabulary; most arbitrary briefs still fall to custom-local (library
domain-bias). Not committed.
**Files:** slide-system/scripts/_common.py, slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_selection_report.py, slide-system/scripts/test_gates.py, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl (ignored job outputs under outputs/slide-jobs/ai-workflow-shape-baseline-20260713/ and ai-workflow-shape-postfix-20260713/)
**Symbols:** _common.SHAPE_TYPE_MAP, _common.shape_eligible, score_visual_items.score_request, validate_selection_report._validate_decision_band, validate_selection_report._validate_shape_lock, test_shape_filter_excludes_incompatible_generic_for_comparison, test_shape_filter_no_compatible_returns_custom_local_extraction, test_unknown_content_shape_forces_custom_local_extraction, test_validator_band_agrees_with_shape_filtered_custom_local
**State:** Not committed

## 2026-07-13.12 — Activate shape-aware selection in the normal flow + restore runtime

**When:** 2026-07-13
**Request:** Finish the shape-aware branch safely: restore the broken project
runtime through the repo-supported setup path; make shape-aware selection
actually active in the normal /slide-generator flow (content_shape mandatory,
validate with --strict-shape); add a `closing` shape grounded in real metadata;
audit the over-tagged timeline component without new heuristics; re-run the
9-slide selection-only brief. No render/build/export.
**Actions:**
- (A) Verified the bare `.venv` failed `import fitz, PIL, pptx`. Restored via the
  repo path: invoked `slide-system/scripts/setup.ps1` in-session (no
  `-ExecutionPolicy Bypass` flag — the ambient policy was already Bypass and the
  documented flag was blocked by the sandbox as a security-weakening arg). It
  pip-installed the declared deps into the existing `.venv` (python-pptx 1.0.2,
  Pillow 12.3.0, PyMuPDF 1.28.0) and `npm install` + Playwright Chromium. Proved
  `import fitz(1.28.0), PIL(12.3.0), pptx(1.0.2)`. No deps beyond what setup.ps1
  declares; installs land in gitignored `.venv`/`node_modules`.
- (B) Made `content_shape` REQUIRED in `.agents/skills/slide-generator/SKILL.md`
  (step 7) and `slide-system/workflows/select-visual-items.md` (step 3), pointing
  at the single shared `_common.SHAPE_TYPE_MAP` (not duplicated). Added
  `--strict-shape` to both documented validate commands. Strengthened
  `validate_selection_report._validate_shape_lock` so `--strict-shape` requires a
  `content_shape` on EVERY scored request (not only reuse/adapt), while the
  scorer API stays lenient for direct shape-less callers. Red→green tests:
  strict-requires-content_shape, shapeless-scorer-legacy guard, and a doc-contract
  test asserting both docs keep `--strict-shape` + `content_shape`.
- (C) Added `closing` to the shared `_common.SHAPE_TYPE_MAP` as
  `{closing, thank-you, farewell, conclusion, outro}` — every token verified
  present in real published thank-you/closing template intent/tags. Red→green
  tests: vocabulary discriminative check + evidence-based "a published closing
  item is closing-eligible". Updated the prior `closing`-as-unknown fixture to a
  genuinely-unknown shape (`mindmap`).
- (D) Audited `sun.component.foundation-top1-microsoft-overlap-circle-set`. Its
  authored descriptors are self-consistent (component_type `milestone-set`,
  layout_role "three-item overlapping gradient circle milestone row",
  visual_summary = ranked overlapping circles 01/02/03, use_cases
  milestone/achievement). The token that makes it timeline-eligible is
  `milestones`, which is accurate — so the metadata is DEFENSIBLE and was NOT
  changed. Registry/index untouched.
- (E) Fresh gitignored job `ai-workflow-strict-eval-20260713/runs/strict-01`:
  9 requests authored from the brief only, `content_shape` on all. Strict score +
  `validate --strict-shape` → PASS. s2/s4 (profile/comparison) select the genuine
  `translator-strategist-driver-coach-card-set`, not the generic badge; s9
  (closing) now resolves to `sun.goal-setting-2026.09-thanks` (48.75, was None);
  s5/s7 tier/timeline reuse preserved; s1/s3/s6/s8 unchanged. Negative check:
  dropping one `content_shape` → `--strict-shape` FAIL (exit 1).
**Result:** PASS. Runtime restored — imports OK; `test_export_stack.py --json`
5/5 jobs PASS (exit 0); `setup.ps1 -Check` passes. `py_compile` clean;
`test_gates.py` 184/184 (repo root); `validate_registry.py` 91;
`build_registry.py --check` clean; retrieval index `--check` clean 91;
`git diff --check` clean (CRLF notes only). No registry/library/catalog/brand
mutation; no dependency-manifest change (declared deps installed into gitignored
`.venv`/`node_modules` only). D = defensible, no metadata change; s7 milestone↔
process match reported as a known selection limitation. Not committed.
**Files:** .agents/skills/slide-generator/SKILL.md, slide-system/workflows/select-visual-items.md, slide-system/scripts/_common.py, slide-system/scripts/validate_selection_report.py, slide-system/scripts/test_gates.py, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl (runtime restored in gitignored .venv/node_modules; ignored eval under outputs/slide-jobs/ai-workflow-strict-eval-20260713/)
**Symbols:** _common.SHAPE_TYPE_MAP (closing), validate_selection_report._validate_shape_lock (strict content_shape), test_strict_shape_requires_content_shape_on_every_request, test_shapeless_direct_scorer_request_preserves_legacy, test_workflow_docs_enforce_strict_shape_contract, test_closing_shape_vocabulary_present_and_discriminative, test_published_closing_item_is_closing_eligible
**State:** Not committed

## 2026-07-13.13 — Fix --strict-shape unknown-shape bypass on non-selecting decisions

**When:** 2026-07-13
**Request:** Fix one confirmed strict-shape validation bug without broadening
scope: under `--strict-shape`, a request with an unknown `content_shape` still
passed when its decision was `custom-local` (or `blocked`), because
`_validate_shape_lock` early-returned on `action not in (reuse, adapt-local) or
not item_id` before checking vocabulary membership. This contradicted the
documented "missing OR unknown content_shape is a hard failure" contract.
**Actions:**
- Reproduced on-branch: `v._validate_shape_lock({"decision":{"action":
  "custom-local","item_id":None}}, False, {"s1":"not-a-real-shape"}, {}, True)`
  returned `([], [])`.
- Added focused RED test `test_strict_shape_rejects_unknown_shape_on_non_selecting_decisions`
  (unknown shape + custom-local AND blocked + strict → error; non-strict stays
  lenient with no error/warning). Confirmed RED.
- Minimal local fix in `validate_selection_report._validate_shape_lock`: added
  `if strict_shape and shape not in SHAPE_TYPE_MAP` (hard error) immediately after
  the existing strict missing-shape check and BEFORE the action/item_id
  early-return, so an unknown `content_shape` now fails for every decision
  (reuse, adapt-local, custom-local, blocked) under `--strict-shape`. Non-strict
  behavior and `score_visual_items.py` are untouched; known shapes still proceed
  to the existing selected-item token lock. No doc change — the existing wording
  is now accurate.
**Result:** PASS. Repro now returns an unknown-shape error; new test GREEN.
`py_compile` clean; `test_gates.py` 185/185 (repo root); `validate_registry.py`
91; `build_registry.py --check` clean; retrieval index `--check` clean 91; the
strict 9-slide eval (`ai-workflow-strict-eval-20260713/runs/strict-01`) still
`validate --strict-shape` PASS (all nine shapes known); `git diff --check` clean
(CRLF notes only). No change to thresholds/scoring/SHAPE_TYPE_MAP entries/
registry/library/catalog/brand/dependency manifests/score_visual_items.py. Not
committed.
**Files:** slide-system/scripts/validate_selection_report.py, slide-system/scripts/test_gates.py, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl
**Symbols:** validate_selection_report._validate_shape_lock, test_strict_shape_rejects_unknown_shape_on_non_selecting_decisions
**State:** Not committed

## 2026-07-13.14 — End-to-end manual-review build of the AI-workflow deck (strict shape-aware)

**When:** 2026-07-13
**Request:** Run the 9-slide AI-workflow brief through the real slide-generator
pipeline with the current strict shape-aware retrieval changes; produce a
reviewable HTML deck + editable PPTX + PDF for manual inspection. QA run, not a
publish. Do not mutate the registry/library or commit.
**Actions:**
- Preflight: `import fitz, PIL, pptx` OK; `setup.ps1 -Check` pass.
  `check_requirements.py` reported `blocked`, but it was a STALE capabilities
  cache (records macOS/codex host paths for node/python that don't exist here);
  the tools are verified present, so it is a false positive — did NOT mutate
  `registries/capabilities.json`.
- Fresh gitignored job `outputs/slide-jobs/shape-aware-manual-qa-20260713`.
  Authored 9 `visual-requests.json` from the brief only, `content_shape` on every
  request. Scored batch (all types) → `validate_selection_report --strict-shape`
  PASS. Selection (deterministic, matches the strict eval): s5 tiers + s7 timeline
  = adapt-local `foundation-top1-microsoft-overlap-circle-set`; the other seven =
  custom-local with genuine near-misses.
- Built the 1920×1080 SUN.STUDIO deck (runs qa-01 → qa-02 → qa-03): seven
  custom-local brand-native slides (CSS-var colours, Proxima Nova, no emoji,
  faithful Vietnamese copy, export-layer tags) + s5/s7 scaffolded from the
  selected component (`data-base-component` marker + its artwork). Brand
  compliance PASS, component fidelity PASS (2/2 on the marker).
- Repair loop (P0/P1 found in the generated run):
  1. qa-02 — brand gate wanted the literal `"Proxima Nova"` (it does not resolve
     `var(--font-*)`); component names were white/invisible on paper; the cover
     logo `<img>` was untagged; s7 rank was redundant. Fixed all four.
  2. qa-03 — the component circles rendered blank: `visual.svg` references
     external masked PNGs which a browser refuses to load through `<img>` (SVG
     secure-static mode) and which fitz cannot composite. Base64-embedded the
     images into a self-contained SVG and rendered it via `<object>` baked into
     the base layer (so tier1 export parity matches) → circles render. Then a
     follow-on correctness fix: the deck had no `<meta charset="utf-8">`, so an
     http-served render showed mojibake — added the charset (file bytes were
     always valid UTF-8; the export loader already handled it).
- Export: layered PPTX (`deck.pptx`, `validate_export_objects` pass:true) + PDF
  (`deck.pdf`, Playwright). Captured all nine slides at 1920×1080 to
  `qa/full/` and inspected them: correct Vietnamese diacritics throughout, no
  clipping / overlapping text / missing fonts / blank slides; s5/s7 circles
  render.
**Result:** PASS. Brand PASS, fidelity PASS, export layered pass:true, PDF
exported. Verification: `test_gates.py` 185/185; `validate_registry.py` 91;
`build_registry.py --check` clean; retrieval index `--check` clean 91;
`test_export_stack.py --json` lightweight_replaces_heavy true; `git diff --check`
clean. No tracked repo file changed — registry/library/catalog/brand assets and
`capabilities.json` untouched; all output is gitignored. Remaining limitation:
s7 (skills 3-step process) reuses the overlap-circle MILESTONE component per the
scorer's adapt-local pick — a known milestone-vs-procedural-timeline library-fit
gap; its large gradient circles are visually heavy and slightly overlap s7's
bottom tags/capsule. The component needed base64-embedding + `<object>` to render
at all (masked, external-image raster artwork = a buildability limitation —
"score != buildability"). Not committed.
**Files:** outputs/slide-jobs/shape-aware-manual-qa-20260713/** (gitignored: deck.html, deck.pptx, deck.pdf, analysis/, assets/, qa/, export/), dev/capture_full.js (untracked QA helper), docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl
**Symbols:** none
**State:** Not committed

## 2026-07-13.15 — Slot-aware component reuse + fidelity gate that rejects bare markers

**When:** 2026-07-13
**Request:** Fix the real component-reuse readability failure from the qa-03 QA:
the deck "reused" the overlap-circle component via generic fixed overlays instead
of the component's declared text slots, and the fidelity gate accepted a bare
`data-base-component` marker as proof. Make reuse honor the slot contract and be
readable; strengthen the gate; correct S7 retrieval and QA provenance.
**Actions:**
- Root cause confirmed: `validate_component_fidelity.py` fell back to matching
  only `data-base-component` presence when a component had no `.slot` in
  preview.html (lines ~80-86) — but the overlap-circle is a text-slot contract
  (`text_contract.semantic_text_in_visual: false`, 13 slots in text-slots.json),
  so a marker + generic `.comp-col` overlays passed. Confirmed by running the
  strengthened gate on the old qa-03 deck → both S5/S7 now FAIL (cov 0%).
- P3 retrieval correction (no new heuristic): added a procedural/sequential
  `anti_use_cases` sentence to `sun.component.foundation-top1-microsoft-overlap-circle-set`
  in visual-library.json and rebuilt the compact + retrieval index. The existing
  ANTI_USE_CASE_PENALTY now drops it for S7's `sequence` term (67.91→52.91); S7
  re-scores to `sun.interview-workshop-sunriser.02-timeline` (65.0), S5 tiers
  unchanged (66.67).
- P1 slot-aware materialization: extended `scaffold_slide_from_component.py` — when
  preview.html has no `.slot` but the component declares an editable text-slot
  contract, emit positioned `data-component-slot="<id>"` boxes from each slot's
  normalized bounds/role (not a generic overlay). Generic; no hardcoded ids.
- P2 self-contained visual: new `materialize_component_visual.py` inlines a
  visual.svg's external image refs as base64 data URIs into a job-local SVG
  (canonical asset untouched) with a nonblank guard — replaces the one-off
  `<object>`/embedded-svg workaround.
- P4 fidelity gate: `validate_component_fidelity.py` now, for a text-slot-contract
  reuse/adapt-local, requires real `data-component-slot` bindings (coverage ≥
  adapt/reuse threshold), verifies each bound box stays inside its declared
  bounds (±0.03) and adds no overlap beyond the component's own design, and
  requires a nonblank base artifact. Bare-marker-only now fails. 8 focused tests
  (bare-marker reject, bound-slot pass, text-outside-slot, overlap, designed-
  overlap-tolerated, missing-artifact, real-component end-to-end, materialize).
- P5 provenance + QA: fresh qa-04 with its OWN generated selection-report +
  selection-validation (validation.report_path points to qa-04, not qa-01).
  Rebuilt S5 slot-aware over the materialized circles (9/13 declared slots bound,
  strict fidelity PASS cov 69%, readable white-on-circle tier text) and S7 as a
  clean brand-native custom-local 3-step timeline (the scorer's interview-timeline
  pick is an interview-specific 23-slot template — a poor fit for a generic
  3-step process). Exported layered PPTX (pass:true) + PDF; captured all nine
  1920x1080 screenshots and inspected them.
**Result:** PASS on the target fix. `test_gates.py` 193/193; `py_compile` clean;
`validate_registry.py` 91; `build_registry.py --check` clean; retrieval index
`--check` clean 91; `test_export_stack.py --json` lightweight_replaces_heavy true;
qa-04 export layered pass:true; `git diff --check` clean. S5 (tiers) is now a
genuine slot-bound reuse passing the STRICT gate. S7 no longer selects the
milestone component; built custom-local, and the strengthened gate + brand
template-assets check HONESTLY flag the adapt-local(report)-vs-custom(build)
mismatch — the intended safety signal that the scorer's borderline 65.0
interview-timeline pick should not be forced ("score != buildability"). Registry
data changed only for the anti_use_cases correction (+ rebuilt index); no publish
status/semantics change, no canonical brand asset touched. Not committed.
**Files:** slide-system/scripts/scaffold_slide_from_component.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/materialize_component_visual.py (new), slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/component-retrieval-index.jsonl, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl (gitignored qa-04 output; untracked dev/capture_full.js)
**Symbols:** scaffold_slide_from_component.text_slot_contract, scaffold_slide_from_component.build_slot_scaffold, validate_component_fidelity.declared_text_slots, validate_component_fidelity.deck_slot_boxes, validate_component_fidelity._check_slot_contract, materialize_component_visual.inline_external_images, materialize_component_visual.is_nonblank
**State:** Not committed

## 2026-07-13.16 — Close component-reuse release blockers A–D (E: QA regen NOT done)
**When:** 2026-07-13
**Request:** Close the remaining component-reuse release blockers: (A) make S7
selection honestly custom-local via smallest metadata change; (B) wire generic
materialization into the real reuse path and fail on missing/unsafe/unresolved
local visual refs; (C) slot-aware readable rendering with contract typography +
deterministic no-shrink fit policy; (D) make fidelity instance-scoped and
render-aware (Playwright DOM measurement); (E) regenerate QA05 through the real
plugin flow with fresh selection/HTML/PPTX/PDF/screenshots + render-aware
fidelity, S5 slot-bound readable, S7 selection AND render both custom-local. No
vector RAG / new deps / publish change / canonical-asset mutation. Never touch
.mcp.json/opencode.jsonc. No commit.
**What (A):** Added accurate `anti_use_cases` to the 4 domain timelines that tied
at the adapt floor for S7 (interview-workshop-sunriser.02-timeline,
goal-setting-2026.05-process, goal-setting-2026.03-timeline,
sun-studio-performance-review-2025.12-review-timeline) — each is a domain-locked
slide (interview schedule / goal-setting / performance review), not a generic
find-install-use 3-step. Wording carries the single-word tokens (sequence,
horizontal, three-step) that intersect S7's UNDECLARED request terms, so the
existing ANTI_USE_CASE_PENALTY drops them 65.0→50.0 and S7 becomes custom-local
(next candidate a hexagon diagram at 58.34 < 65). Rebuilt compact + retrieval
index only. S7 is the ONLY changed decision across the 9 (S5 stays adapt-local
overlap-circle 66.67 — no adapt/reuse silently replaced). Verified the 4 stay
eligible (adapt-local, zero anti_hits) for real interview/goal/review requests.
2 regression tests.
**What (B):** `materialize_component_visual.main(argv)` now FAILS (rc=1, no write)
on any missing/unsafe/unresolved local image ref (added path-traversal/absolute
detection) instead of warn+writing an incomplete "successful" SVG. Wired
materialization into the real reuse path: `scaffold_slide_from_component.main`,
when writing to a file and the component ships `paths.visual`, materializes a
self-contained job-local `assets/comp/<id>.svg` and points `.bg` at it, failing
the whole scaffold if the visual can't be made complete/nonblank. Smoke: real S5
overlap-circle → 6 images inlined into 75KB self-contained SVG, 0 external refs,
13-slot scaffold wired. 5 tests.
**What (C):** `build_slot_scaffold` now emits each slot's OWN contract typography
(font family/weight/style, colour, line-height, letter-spacing, text-align) and
flex alignment from horizontal/vertical_align. Font size is the source-unit size
scaled to the deck canvas by the vertical ratio (`_source_vscale` reads the
component's text-slots `source.canvas_height`); it is FIXED — never auto-shrunk.
Documented ceiling: bounds map source→full-1920x1080 (anisotropic for non-16:9
components); overflow is caught by the render gate, not silently resized. 2 tests.
**What (D):** Fidelity is now instance-scoped: `_instance_subtrees`/`_instance_scope`
validate INSIDE each `.slide-scaffold[data-base-component]` subtree, so a slide
can't borrow slot bindings pooled from a different component elsewhere on the
deck. Render-aware: new `measure_deck_slots.js` (Chromium via Playwright, mirrors
measure_svg_groups.js) measures every `[data-component-slot]`'s scrollWidth/
scrollHeight overflow + nonzero rendered dims; `measure_rendered_slots` +
`--render` feed it into `_check_slot_contract`, which fails on overflow (fit
policy: fall back to custom-local, do not shrink) or non-render. Degrades to
static checks with a warning when node/playwright are absent; report records
`render_measured`. Smoke: real materialized S5 deck → 13 slots measured,
instance-attributed, all rendered nonzero. 3 tests (instance-scope,
fit-policy integration, real-Chromium overflow detection — the last ran, not
skipped).
**What (E):** NOT DONE. Generating QA05 through the real agent-orchestrated flow
(author all 9 slides incl. filled Vietnamese S5 slot copy, export layered PPTX +
PDF, capture 9 screenshots, run strict `--render` fidelity, visual-QA all 9) is a
large deck-authoring+validation step that exceeds this session's remaining
budget. Per the explicit constraint I did NOT copy/edit qa-04 to manufacture a
QA05, and I am NOT representing the deck as release-validated. The A–D machinery
E depends on is now in place and tested; E is a clean follow-up (steps in report).
**Result:** A–D COMPLETE + verified. `test_gates.py` 205/205 (12 new); `py_compile`
+ `node --check` clean; `validate_registry.py` 91; `build_registry.py --check`
clean 91; retrieval index `--check` clean 91; `test_export_stack.py` A–E PASS
(no export regression from scaffold/materialize edits); `git diff --check` clean.
Registry data changed only for the anti_use_cases correction (+ rebuilt compact/
index); no publish status/semantics change; no canonical brand asset touched.
E (QA05 regen + visual QA) remains — deck NOT yet regenerated/release-validated.
**Files:** slide-system/scripts/scaffold_slide_from_component.py, slide-system/scripts/materialize_component_visual.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/measure_deck_slots.js (new), slide-system/scripts/test_gates.py, slide-system/registries/visual-library.json, slide-system/registries/component-retrieval-index.jsonl, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl (visual-library-compact.json unchanged — anti_use_cases is not a compact key)
**Symbols:** materialize_component_visual.inline_external_images, materialize_component_visual.main, scaffold_slide_from_component._materialize_bg, scaffold_slide_from_component.build_slot_scaffold, scaffold_slide_from_component._slot_text_css, scaffold_slide_from_component._source_vscale, validate_component_fidelity._instance_subtrees, validate_component_fidelity._instance_scope, validate_component_fidelity.measure_rendered_slots, validate_component_fidelity._check_slot_contract, measure_deck_slots.js
**Note:** `.mcp.json` and `opencode.jsonc` show as pre-existing working-tree modifications (codegraph→codeindex/context7 MCP config) unrelated to this task; per instruction left untouched — not modified, not reverted, not staged.
**State:** Not committed

## 2026-07-13.17 — Decision record: per-user style-profile design (Phase 1 research)
**When:** 2026-07-13
**Request:** Before implementing a per-user design-preference capability, do a
bounded local research pass and record a decision (storage, what counts as a
user-owned style preference, privacy/scope, what it may influence, what it must
never override), under YAGNI (no DB/embeddings/memory-service/tracking/cloud/new
dep/home-dir memory/CSS injection/second brand system).
**Actions (research):**
- Mapped the normal `/slide-generator` orchestration (SKILL.md): intake → recap →
  job setup → check_requirements → content analysis → score (visual-requests.json
  → selection-report.json, scorer-OWNED) → strict validate → approval → build
  (reuse/adapt scaffold vs custom-local) → brand + component-fidelity gates →
  export. Artifacts: `outputs/slide-jobs/<job>/requirements/job-requirements.json`,
  `runs/<run>/analysis/{visual-requests,selection-report}.json`.
- Found the extension points: `slide-system/schemas/*.schema.json` (JSON
  contracts), `slide-system/boilerplates/job-requirements.json`, the design plan
  from `workflows/plan-slide-deck.md`, `slide-system/brand-packs/sun-studio/`
  (manifest + selection-rules), `slide-system/rules/` (content-fidelity,
  visual-selection, component-composition, source-authority). No pre-existing
  style-profile / user-preference pattern exists — this is net-new but rides the
  schemas + job-requirements JSON-contract pattern (no new system).
- CodeGraph confirmed fidelity instance-scoping currently keys by
  `data-base-component`=item id (pooling risk), and scaffold `.bg`/slot emission.
**Decision (chosen minimal design):**
- STORAGE: `slide-system/style-profiles/<profile-id>.json`, project-local,
  versioned, human-editable, validated by new `schemas/style-profile.schema.json`.
  Chosen because it mirrors the existing schemas/boilerplates JSON-contract
  pattern; no DB/home-dir/cloud/new dependency; explicit per-profile selection.
- EXPLICIT USER-OWNED PREFERENCE = only whitelisted enum fields: information
  density, heading/body hierarchy, spacing, visual rhythm / layout families,
  preferred & avoided published component intents, restrained↔expressive,
  image-led↔diagram-led, optional language/tone. Nothing free-form.
- PRIVACY/SCOPE: only the explicitly-named profile id/path is loaded; never
  another user's profile implicitly; no home-dir memory; no auto-learning from
  private decks; no tracking/inferred data.
- MAY INFLUENCE: (a) within-band tie-breaking among already-selectable, equally
  scored published candidates; (b) custom-local composition (density/hierarchy/
  spacing/rhythm/layout-family/tone) and a soft preferred/avoided intent bias.
  Recorded (id/version/sha256 + applied + rejected-with-reasons) in the job
  design-plan artifact.
- MUST NEVER OVERRIDE: approved source content/wording/numbers/order/language;
  SUN.STUDIO canonical brand tokens; accessibility/readability (contrast, no
  overlap, projection legibility); canvas 1920×1080 bounds; published-only
  retrieval; content fidelity + component slot contracts + the fidelity gate. It
  can NOT force an incompatible component reuse (cannot cross reuse/adapt/custom
  thresholds) and can NOT inject CSS/HTML/JS.
- PRECEDENCE (high→low): approved content/source authority → brand pack +
  accessibility/layout safety → component contracts + fidelity → explicit user
  style profile → agent taste/defaults. (Full doc to be added under
  `slide-system/rules/` in Phase 3.)
**Result:** Research complete; decision recorded. No code changed in this entry.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md
**Symbols:** none
**State:** Not committed

## 2026-07-13.18 — Instance-scoped render-aware fidelity + per-user style profile (Phase 2 & 3)
**When:** 2026-07-13
**Request:** Finish component-fidelity release blockers (unique per-occurrence
instances; render-aware fidelity proving readability; fail-closed --require-render)
and add a minimal, safe design-rules + per-user style-memory capability. TDD;
no vector DB / new dep; never touch .mcp.json/opencode.jsonc; no commit.
**Actions (Phase 2 — fidelity, TDD):**
- P2A unique instances: `scaffold_slide_from_component.py` now emits a
  deterministic, unique `data-component-instance` = `<item-id>#<suffix>` per
  occurrence (`_instance_id`/`_instance_suffix`; suffix from --instance-id, else
  the slide dir like `page-05`, else a short path hash). Fresh scaffolds always
  carry it. `validate_component_fidelity._instance_occurrences` scopes validation
  per unique occurrence (not by shared item id), so two uses of one component
  never pool slots/artifacts/measurements.
- P2B render-aware + fail-closed: rewrote `measure_deck_slots.js` to measure PER
  `data-component-instance` — each slot's ACTUAL text ink box (Range), wrapper
  overflow, text-outside-wrapper, visibility, and the `.bg` artifact's rendered
  size + load state (img.naturalWidth / inline svg / object / non-empty
  background-image). `_check_slot_contract` now fails on overflow/clip/spill,
  non-render, cross-slot rendered-text overlap beyond the source-declared overlap
  (`_rendered_text_overlaps`), and unloaded base artwork. Added `--require-render`
  (release): measurement MUST run (exit 1 if node/playwright missing/errors) and
  every reused occurrence MUST have a unique instance id; legacy (no id) tolerated
  only in non-release. No silent shrink — overflow → custom-local.
- P2C tests: 9 required cases + 2 gated real-Chromium tests (two-instance
  no-borrow; measurements not pooled; text outside wrapper; actual text overlap;
  long-Vietnamese clip [real browser]; broken artwork despite an unrelated SVG;
  --require-render fails closed without node; source-designed overlap allowed;
  legacy warn-only vs release requires ids; instance-keyed measurement [real
  browser]).
**Actions (Phase 3 — style profile, minimal/deterministic):**
- New `schemas/style-profile.schema.json` (versioned, additionalProperties:false,
  whitelisted enum-only preferences), example `style-profiles/example-restrained.json`
  (NOT a default), hand-rolled `validate_style_profile.py` (rejects unknown keys,
  non-enum values, and any markup/CSS/URL/script), precedence doc
  `rules/style-profiles.md`.
- `resolve_style_profile.py` reads the profile + scorer-owned selection-report
  (READ ONLY) + registry and writes `analysis/design-plan.json` recording the
  profile id/version/sha256, applied preferences (custom-local composition +
  within-band tie-break), and rejected preferences with reasons — e.g. an
  `avoided_component_intents` value that a scorer-selected reuse/adapt component
  declares is REJECTED (fidelity outranks profile; a profile can never drop a
  selected component or force an incompatible reuse). Never mutates the report.
- Wired into the contract: optional `style_profile` in `job-requirements.schema.json`;
  steps 8b + 11 (release `--render --require-render`) documented in slide-generator
  SKILL.md.
**Result:** `test_gates.py` 215/215 (14 new: P2C 9 + 2 gated real-browser + P3 3);
`py_compile` + `node --check` clean; `validate_registry` 91; `build_registry --check`
clean; retrieval index --check clean 91; new JSON all valid; example profile
validates; resolver smoke shows provenance + 11 applied / 1 rejected / report
unmutated. Real-data smoke: real S5 scaffold emits instance id `...#page-05`,
Chromium measurement instance-keyed with bg loaded (1920×1080), 13 slots. Phase 4
(QA05) not yet run. No registry/publish/canonical-asset change in Phase 2/3.
**Files:** slide-system/scripts/scaffold_slide_from_component.py, slide-system/scripts/measure_deck_slots.js, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/validate_style_profile.py (new), slide-system/scripts/resolve_style_profile.py (new), slide-system/scripts/test_gates.py, slide-system/schemas/style-profile.schema.json (new), slide-system/schemas/job-requirements.schema.json, slide-system/style-profiles/example-restrained.json (new), slide-system/rules/style-profiles.md (new), .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-13.md
**Symbols:** scaffold_slide_from_component._instance_id, scaffold_slide_from_component._instance_suffix, scaffold_slide_from_component.build_slot_scaffold, validate_component_fidelity._instance_occurrences, validate_component_fidelity.measure_rendered_slots, validate_component_fidelity._validate_occurrence, validate_component_fidelity._check_slot_contract, validate_component_fidelity._rendered_text_overlaps, validate_component_fidelity.check_fidelity, validate_style_profile.validate_profile, resolve_style_profile.resolve, measure_deck_slots.js
**State:** Not committed

## 2026-07-13.19 — QA05 through the real flow (Phase 4) + isotropic font fix
**When:** 2026-07-13
**Request:** Generate a fresh QA05 deck through the normal /slide-generator flow
(no qa-04 HTML copy), using one example style profile recorded in the job
artifacts, and pass the release gates: strict selection validation, brand, and
component fidelity with `--render --require-render` (no --warn). Manually inspect
all nine slides. No commit.
**Actions:**
- Job: `outputs/slide-jobs/shape-aware-manual-qa-20260713/runs/qa-05/`. Authored
  the 9 same-brief visual-requests, scored fresh → selection-report tied to qa-05,
  `validate_selection_report --strict-shape` PASS. S5 = adapt-local overlap-circle
  (66.67); S7 = custom-local hexagon (58.34) — no interview timeline / milestone
  circle. Resolved the example profile → `analysis/design-plan.json` (id/version/
  sha256, 11 applied composition prefs, 1 rejected: avoid `statistics` refused
  because S5's selected reuse declares it; report unmutated).
- Built `deck.html`: S5 via the real reuse scaffold (`--instance-id s5`,
  materialized self-contained bg, min-scale typography) with short Vietnamese tier
  labels; the other 8 slides brand-native custom-local applying the profile
  (airy/bold/restrained/diagram-led/vi/coaching, grid/columns/centered), tokens +
  Proxima Nova via the canonical `colors_and_type.css` @import.
- QA loop: the FIRST release fidelity run FAILED — 5 S5 slots' Vietnamese text
  overshot their boxes (`textOutsideWrapper`) because contract `line-height:1` +
  top-alignment let normal glyph ascent (diacritics) clip against boxes that are
  actually taller than the text. Generic fix (not a shrink): vertically CENTER
  single-line slot text so the ample vertical room absorbs ascent/descent
  (`build_slot_scaffold`), and changed the source→canvas font scale to the
  ISOTROPIC min of both axes (`_source_font_scale`, was vertical-only → labels no
  longer overflow wide-but-short source strips). Rebuilt → fidelity PASS.
- Exported layered PPTX (tier1/tier2 parity pass:true) + PDF; captured all nine
  1920×1080 screenshots; manually inspected each.
**Result (release gates, QA05):** strict selection validation PASS; brand
compliance ALL OK (no non-brand colour, Proxima Nova, no emoji); component
fidelity `--render --require-render` PASS (valid, require_render+render_measured
true, warn_only false) — S5 instance `...#s5` adapt-local cov 100%, readable, bg
loaded, no clip/overflow/overlap. S7 selection AND rendered action both
custom-local. Manual review of all 9: readable, on-brand, full Vietnamese
diacritics, no clipping/overlap; S9's orange highlight is visually tight but fully
legible (cosmetic, brand gate passed). `test_gates.py` 215/215; export-stack A–E
PASS; `validate_registry` 91; `build_registry --check` clean; retrieval index
--check clean; `git diff --check` clean. Artifacts: qa-05/{deck.html, qa05.pptx,
qa05.pdf}, analysis/{visual-requests,selection-report,design-plan}.json,
qa/component-fidelity-report.json, qa/full/full-s1..s9.png. No registry/publish/
canonical-asset change. `.mcp.json`/`opencode.jsonc` untouched (pre-existing mods
only). Not committed.
**Files:** slide-system/scripts/scaffold_slide_from_component.py (isotropic font scale + vertical-center slot text), docs/logs/SESSION-LOG-2026-07-13.md; QA05 run artifacts under outputs/slide-jobs/shape-aware-manual-qa-20260713/runs/qa-05/ (gitignored job output)
**Symbols:** scaffold_slide_from_component._source_font_scale, scaffold_slide_from_component.build_slot_scaffold
**State:** Not committed

## 2026-07-13.20 — Decision record: high-confidence reuse / needs_component / no-duplicate
**When:** 2026-07-13
**Request:** Revise the component-selection product decision — auto-reuse only when
confidence is genuinely high; otherwise present the slide as unresolved
(`needs_component`) and let the user pick a component from the web library (copy
ID / copy prompt) or explicitly approve custom-local; the same published component
must not be auto-reused twice per deck. Remove `adapt-local` as an automatic
action. Record the decision before editing.
**Research (CodeGraph + reads):** decision bands live in
`score_visual_items._decide` region (blocked / no-shape custom-local / low-semantic
custom-local / >=75 reuse / >=65 adapt-local / else custom-local); the batch loop
scores each slide independently (no deck awareness). `validate_selection_report`
holds `VALID_ACTIONS` + a band recompute (reuse>=75/adapt>=65) + score-band error
checks; `validate_component_fidelity` acts on reuse/adapt-local. The catalog
already ships Copy ID (copies `item.id`) and Copy prompt
(`compBuildPrompt`: `Use the published <type> component "<name>" (<id>) from the
SUN.STUDIO visual library.`), so the stable id is recoverable from the prompt's
`(id)`. No existing explicit-selection/needs_component/allow_component_reuse.
**Decision:**
- CONFIDENCE THRESHOLD — auto `reuse` requires BOTH `total >= 78` AND
  `semantic_intent >= 0.7 * weight(semantic_intent) = 24.5`. Evidence
  (`scratchpad/calibrate.py` against the real compact registry + retrieval index):
  the 45-pt baseline (density+brand+export+accessibility) inflates the total, so
  the total alone cannot separate a genuine match from a keyword-lucky one — the
  semantic sub-score does. Genuine strong matches land at total>=78 / semantic>=24.5
  with 3-4 PRIMARY intent matches (model-tiers 78/28, role-cards 79.5/24.5);
  mediocre "matches" fall below on semantic (interview 74/14, perf-review
  70.83/17.5, goal-checklist 71.88/21.88) and now become `needs_component`. This is
  materially stricter than the old adapt band (65) and the old reuse band (75).
- UNRESOLVED BEHAVIOR — `needs_component`: build nothing; decision carries a
  plain-language `reason`, `suggested_search` terms (from intent/tags), `candidates`
  (top safe ranked items, if any), and the exact `next_action`.
- EXPLICIT SELECTION CONTRACT — a request may set `component_id` (a bare stable id
  OR the catalog Copy-prompt text; resolved deterministically to the `(id)`). It
  bypasses the score threshold but still validates published + shape/type-compatible
  + has editable slots (+ render fidelity at build). On failure the slide stays
  `needs_component` with a reason; never a silent substitute.
- NO-DUPLICATE — selection is deck-aware: a component assigned to an earlier slide
  is unavailable to later AUTOMATIC selection. Assignment orders slides
  most-constrained-first (fewest valid reuse candidates) so a generic early slide
  cannot consume the only component a later slide needs; duplicate-only remaining
  -> `needs_component`. A per-slide `allow_component_reuse: true` override is
  honoured only when present, recorded in the job artifacts, and surfaced in review.
- CUSTOM-LOCAL — permitted only via an explicit per-slide/job
  `unresolved_policy: "custom-local"` set by the user after the library-review
  step; never automatic; visibly marked and never reported as reuse.
**Result:** Decision recorded; no code changed in this entry.
**Files:** docs/logs/SESSION-LOG-2026-07-13.md
**Symbols:** none
**State:** Not committed

## 2026-07-13.21 — Implement high-confidence reuse / needs_component / no-duplicate + QA
**When:** 2026-07-13
**Request:** Revise the component-selection product decision per 2026-07-13.20:
auto-reuse only at genuinely high confidence; otherwise `needs_component`
(unresolved — user picks from the web library or approves custom); remove
`adapt-local` as an automatic action; custom-local only on explicit user
approval; no published component auto-reused twice per deck; explicit selection
by stable id/prompt. TDD; no new deps/RAG; never touch .mcp.json/opencode.jsonc;
no commit.
**Actions (A-F, scorer/validator/fidelity, TDD):**
- `score_visual_items.py`: new `AUTO_REUSE_MIN=78` + `SEMANTIC_CONFIDENCE_FRAC=0.7`
  (=24.5). `_reuse_ready` gates reuse on total>=78 AND semantic>=24.5 AND
  published+shape+slot-ready. New actions: `reuse` (auto or explicit),
  `needs_component` (reason + suggested_search + top safe candidates +
  next_action), `custom-local` ONLY on `unresolved_policy:"custom-local"`.
  `resolve_component_id` accepts a bare id or the catalog Copy-prompt text
  (deterministic `(id)`); `_explicit_decision` validates published/shape/slots,
  else stays needs_component (never substitutes). `assign_deck_components` makes
  the batch deck-aware: explicit selections reserve first, automatic reuse is
  assigned most-constrained-first, duplicate-only -> needs_component unless
  `allow_component_reuse:true` (recorded).
- `validate_selection_report.py`: VALID_ACTIONS={reuse,needs_component,custom-local};
  imports the bar from the scorer; band recompute now rejects auto reuse below the
  bar and any non-user custom-local; retired the 65/75 score-band checks and the
  adapt-local/blocked vocabulary. `validate_component_fidelity.py` checks `reuse`
  only. `resolve_style_profile.py` locked-intent check -> reuse only.
- Docs/schema: selection-report.schema action enum + needs_component fields;
  optional per-slide component_id/unresolved_policy/allow_component_reuse
  documented; SKILL.md steps 4/9/10/11 + workflows/select-visual-items.md rewritten
  for high-confidence reuse / needs_component / library-review (Copy ID/prompt) /
  explicit custom-local / no-duplicate + override. Catalog already ships
  filter/preview + Copy ID + Copy prompt (no second UI).
- Scaffold: `_slot_text_css` no longer emits the contract's raw source foundry
  font-family (slot text inherits the deck brand font; brand pack outranks
  component styling) — keeps the brand-font gate.
- Tests: 227/227. Updated 11 old-vocabulary tests (65-74 -> needs_component,
  no-shape/unknown-shape -> needs_component, domain timelines stay eligible
  candidates, fidelity/style report actions -> reuse) + 12 new selection-contract
  tests covering all 10 required F cases (prev-adapt-band, low-confidence,
  high-confidence, explicit-below-threshold, explicit prompt resolve,
  invalid/unpublished/incompatible explicit, no-auto-duplicate, duplicate-only,
  most-constrained-first, allow_component_reuse override, explicit-only
  custom-local, published-only).
**Actions (G, real QA):**
- G.1: original 9-slide AI-workflow brief scored under the new contract -> ALL 9
  `needs_component` (none clears the bar), strict selection validation PASS; no
  deck fabricated (unresolved slides need user selection).
  `runs/nine-slide-brief/`.
- G.2-G.6: authored a distinct-component QA brief (2 explicit cover/closing via
  Copy-prompt + automatic content components). Built through the real reuse
  scaffold. The render-aware release gate + visual QA rejected two wide-diagram
  components whose artwork does not map to 16:9 (metric-strip text overflowed;
  hexagon artwork cover-cropped with misaligned headings) -> dropped them (fit
  policy). Final deck = 3 distinct high-confidence reuse slides (cover =
  sun.sun-presentation.01-cover [explicit], ai-tiers =
  sun.component.foundation-top1-microsoft-overlap-circle-set [auto], closing =
  sun.sun-presentation.17-closing-thank-you [explicit]); all reuse, no id repeats,
  no adapt-local, no unapproved custom-local. `runs/distinct-deck/`.
**Result:** `test_gates.py` 227/227; `py_compile` clean; `validate_registry` 91;
`build_registry --check` clean; retrieval index --check clean; export-stack 13/13
PASS; `git diff --check` clean. QA deck: strict selection validation PASS; brand
compliance PASS (no emoji / brand fonts / brand colours); component fidelity
`--render --require-render` PASS (3 reuse instances, cov 100%, no clip/overflow/
overlap, bg loaded); PPTX layered tier1/tier2 parity pass:true (HTML<->PPTX match);
PDF exported; 3 screenshots manually inspected — all readable, on-brand, full
Vietnamese diacritics. No registry data / publish / canonical-asset change.
`.mcp.json`/`opencode.jsonc` untouched. Not committed.
**Files:** slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_selection_report.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/scaffold_slide_from_component.py, slide-system/scripts/resolve_style_profile.py, slide-system/scripts/test_gates.py, slide-system/schemas/selection-report.schema.json, slide-system/workflows/select-visual-items.md, .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-13.md; QA outputs under outputs/slide-jobs/selection-revision-20260715/ (gitignored)
**Symbols:** score_visual_items.AUTO_REUSE_MIN, score_visual_items.resolve_component_id, score_visual_items._explicit_decision, score_visual_items._needs_component_decision, score_visual_items._reuse_ready_ids, score_visual_items.assign_deck_components, validate_selection_report._validate_decision_band, validate_selection_report.VALID_ACTIONS, scaffold_slide_from_component._slot_text_css
**State:** Not committed

## 2026-07-13.22 — Close selection gaps: full candidate pool, auto-reuse eligibility, batch schema
**When:** 2026-07-13
**Request:** Fix three release-blocking gaps in the selection engine: (A) deck
allocation only saw the `--top-n` slice; (B) components with known failed
full-slide QA could still be auto-selected; (C) the per-slide user selection
inputs had no validated schema. Minimal changes; no deps; no commit.
**Actions:**
- A: `score_request(top_n=None)` now returns the FULL scored pool and the report
  slice moved to a new `report_candidates()`. The batch path scores with the full
  pool, runs `assign_deck_components` over it, and only then compacts each slide's
  candidates — so `--top-n` is presentation-only and the selected item is always
  surfaced even below the cut. `main(argv)` added for testing.
- B: new registry field `auto_reuse: {eligible, reason}` (absent == eligible) —
  declared in `visual-item.schema.json`, shape-enforced in `validate_registry.py`,
  carried into `COMPACT_KEYS` (scorer) and the retrieval index (catalog stays
  browseable/review-only). `_auto_reuse_ok()` bars flagged items from `_reuse_ready`
  and `_reuse_ready_ids`; `_explicit_decision` records the QA warning instead of
  passing silently; `validate_component_fidelity._validate_occurrence` fails ANY
  reuse of a flagged item closed. Chose a new small field over `compatibility`
  (null on all 91 items, export-format-scoped, `additionalProperties:false`) and
  over `limitations` (free text, no structured flag). Backfilled exactly two items
  with their real QA findings: `goal-keyresult-task-hexagon-diagram` (cover-cropped
  at 1920x1080, GOAL/TASK lobes outside frame, slot text misaligned) and
  `revenue-team-size-metric-strip` (text overflows its own boxes: '+30%' 507px in a
  478px box).
- C: new `schemas/visual-requests.schema.json` for the `--batch-request` artifact +
  `validate_batch_request()` enforced in `main` BEFORE scoring (plain errors, exit 1,
  no report written). `job-requirements.schema.json` untouched — it never claimed
  slide selections. Workflow/SKILL now name the exact artifact
  (`<run>/analysis/visual-requests.json`) with an example.
- Scope: retired live automatic `adapt-local` references (validate_brand_compliance
  template_assets check, fidelity/validator docstrings, build-html-deck workflow);
  corrected overstated style-profile wording (the scorer does not read the profile;
  tie-break entries are non-binding notes) without changing its behaviour.
**Result:** `test_gates.py` 235/235 (7 new: full-pool 6th-candidate regression,
4 eligibility-gate, 3 batch-schema). py_compile clean; `validate_registry` 91;
`build_registry --check` clean; retrieval index `--check` clean 91;
`build_log_index --check` up to date; `git diff --check` clean. Strict selection
validation PASS for both nine-slide-brief and distinct-deck; existing distinct-deck
fidelity `--render --require-render` still PASS (3 reuse). Disposable QA batch
(scratchpad, 6 competing cover slides + 2 unsafe-targeting): 6 distinct auto
reuses with no duplicates, `cover-5` took a pick at ranked index 5 (below report
top-N — impossible before Fix A), both unsafe components stayed needs_component
despite scoring 95.0/75.0, no adapt-local, no implicit custom-local. No publish
semantics change; no deck built this task. `.mcp.json`/`opencode.jsonc` untouched.
Not committed.
**Files:** slide-system/scripts/score_visual_items.py, slide-system/scripts/validate_component_fidelity.py, slide-system/scripts/validate_registry.py, slide-system/scripts/validate_brand_compliance.py, slide-system/scripts/validate_selection_report.py, slide-system/scripts/build_registry.py, slide-system/scripts/build_component_retrieval_index.py, slide-system/scripts/resolve_style_profile.py, slide-system/scripts/test_gates.py, slide-system/schemas/visual-item.schema.json, slide-system/schemas/visual-requests.schema.json (new), slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/component-retrieval-index.jsonl, slide-system/rules/style-profiles.md, slide-system/workflows/select-visual-items.md, slide-system/workflows/build-html-deck.md, .agents/skills/slide-generator/SKILL.md, docs/logs/SESSION-LOG-2026-07-13.md, docs/logs/INDEX.jsonl
**Symbols:** score_visual_items.report_candidates, score_visual_items.validate_batch_request, score_visual_items._auto_reuse_ok, score_visual_items.score_request, score_visual_items.main, validate_component_fidelity._validate_occurrence, validate_registry.main, build_registry.COMPACT_KEYS, build_component_retrieval_index.build_record
**State:** Not committed
