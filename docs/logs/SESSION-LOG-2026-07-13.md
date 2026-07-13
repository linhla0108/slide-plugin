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
