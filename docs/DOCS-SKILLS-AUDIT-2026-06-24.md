# SUN.RISER 2026 — Docs & Skills Audit Report

**Date:** 2026-06-24  
**Auditor:** 3 subagents + synthesizer  
**Scope:** All documentation, skills, workflows, rules, scripts, schemas, registries

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Documentation Status](#2-documentation-status)
3. [Skills Status](#3-skills-status)
4. [Workflows Status](#4-workflows-status)
5. [Rules Status](#5-rules-status)
6. [Scripts & Schemas Status](#6-scripts--schemas-status)
7. [Registries Status](#7-registries-status)
8. [Issues Found](#8-issues-found)
9. [Action Plan](#9-action-plan)
10. [Scoring](#10-scoring)

---

## 1. Executive Summary

**Overall Readiness: 8.5/10 — Production-ready with caveats**

The SUN.RISER 2026 slide system has comprehensive documentation, 13 well-structured skills, 48 production scripts, 8 valid schemas, and 7 active registries. The core pipeline (slide generation) is solid. Two missing brand assets and one threshold contradiction need fixing before full production use.

---

## 2. Documentation Status

### Core Docs

| File | Path | Lines | Status | Quality |
|------|------|-------|--------|---------|
| AGENTS.md | `/AGENTS.md` | 147 | ✅ Complete | Excellent |
| README.md | `/README.md` | — | ✅ Complete | Good |
| System README | `/slide-system/README.md` | 216 | ✅ Complete | Excellent |

### Flow Docs (`docs/flows/`)

| File | Purpose | Status |
|------|---------|--------|
| `flow-slide-generation.md` | Full slide gen pipeline | ✅ Present |
| `flow-component-extraction.md` | Component extraction pipeline | ✅ Present |
| `flow-export-pptx.md` | PPTX export flow | ✅ Present |
| `flow-export-pdf.md` | PDF export flow | ✅ Present |
| `flow-visual-selection.md` | Visual item selection | ✅ Present |
| `flow-brand-compliance.md` | Brand compliance checking | ✅ Present |

### Session Logs (`docs/logs/`)

| File | Lines | Status |
|------|-------|--------|
| `SESSION-LOG-2026-06-24.md` | 333 | ✅ Active, detailed |

---

## 3. Skills Status

### Slide System Skills (8 skills)

| Skill | Path | Lines | Pipeline | Issues |
|-------|------|-------|----------|--------|
| slide-generator | `.agents/skills/slide-generator/SKILL.md` | 202 | ✅ Complete | Step 12 export cmd missing args |
| component-extractor | `.agents/skills/component-extractor/SKILL.md` | 210 | ✅ Complete | crop_svg_region unit bug |
| export-as-editable-pptx | `.agents/skills/export-as-editable-pptx/SKILL.md` | 86 | ✅ Complete | — |
| extract-preflight | `.agents/skills/extract-preflight/SKILL.md` | 170 | ✅ Complete | — |
| pptx-html-fidelity-audit | `.agents/skills/pptx-html-fidelity-audit/SKILL.md` | 254 | ✅ Complete | Orphaned (no workflow refs) |
| sun-studio-design-system | `.agents/skills/sun-studio-design-system/SKILL.md` | 109 | ✅ Complete | — |
| svg-extractor | `.agents/skills/svg-extractor/SKILL.md` | 58 | ✅ Complete | — |
| pptx | `.agents/skills/pptx/SKILL.md` | 232 | ✅ Complete | — |

### Standalone Skills (5 skills)

| Skill | Path | Lines | Purpose |
|-------|------|-------|---------|
| ppt-master | `.agents/skills/ppt-master/SKILL.md` | 561 | SVG content generation |
| make-a-deck | `.agents/skills/make-a-deck/SKILL.md` | 60 | HTML deck builder |
| make-tweakable | `.agents/skills/make-tweakable/SKILL.md` | 8 | Config panel |
| hi-fi-design | `.agents/skills/hi-fi-design/SKILL.md` | 23 | UI design |
| send-to-canva | `.agents/skills/send-to-canva/SKILL.md` | 23 | Canva import |

---

## 4. Workflows Status

### Thorough (7 workflows)

| Workflow | Lines | Key Strengths |
|----------|-------|---------------|
| `intake-and-triage.md` | 132 | 7-case triage matrix, persona guidelines |
| `build-html-deck.md` | 143 | Pre/post-build gates, exact script invocations |
| `select-visual-items.md` | 40 | Score thresholds, validation gate |
| `save-as-template.md` | 73 | Artifact table, validation commands |
| `export-editable-pptx.md` | 36 | Layered vs flat modes, QA checks |
| `export-pdf.md` | 51 | Renderer selection table, QA checklist |
| `extract-components.md` | 54 | 13-step pipeline, approval gate |

### Adequate (6 workflows)

| Workflow | Lines | Gap |
|----------|-------|-----|
| `check-requirements.md` | 16 | Less specific about validation steps |
| `plan-slide-deck.md` | 31 | Needs more output format guidance |
| `verify-render-parity.md` | 16 | Brief but covers essentials |
| `resume-job.md` 7 | 7 | Minimal, for experienced operators |
| `rebuild-catalog.md` 18 | 18 | Adequate |
| `package-delivery.md` | 8 | Needs delivery report format detail |

### Minimal (2 workflows)

| Workflow | Lines | Gap |
|----------|-------|-----|
| `publish-components.md` | 14 | Missing script invocations |
| `run-ppt-master.md` | 10 | Pointer to SKILL.md, minimal |

---

## 5. Rules Status

### Thorough (4 rules)

| Rule | Lines | Coverage |
|------|-------|----------|
| `component-complacement.md` | 74 | Logo/dio/shape placement, size constraints |
| `editable-text-slots.md` | 49 | Text slot contract, review rules |
| `background-rendering.md` | 36 | Three-layer model, z-order |
| `extraction-methods.md` | 34 | 12 artifact type matrix |

### Good (4 rules)

| Rule | Lines | Notes |
|------|-------|-------|
| `export-compatibility.md` | 23 | Support values, layered approach |
| `content-fidelity.md` | 14 | 8 clear rules |
| `source-authority.md` | 18 | 6-level authority hierarchy |
| `icon-selection.md` | 29 | Emoji ban, 5-level priority |

### Adequate (3 rules)

| Rule | Lines | Notes |
|------|-------|-------|
| `naming-versioning.md` | 21 | Clear ID format |
| `visual-selection.md` | 28 | Threshold contradiction with workflow |
| `approval-gates.md` | 21 | Two approval models |

---

## 6. Scripts & Schemas Status

### Scripts by Category (48 total, ~10,051 lines)

| Category | Count | Lines | Key Scripts |
|----------|-------|-------|-------------|
| Validation | 13 | ~2,372 | validate_registry, validate_brand_compliance, validate_export_objects, validate_component_fidelity, validate_text_slots, validate_selection_report, check_requirements, check_base_requirements, test_export_stack, test_gates, test_build_brochure_v3_deck, compare_renders, prototype_compose_check |
| Export | 5 | ~1,116 | export_pptx, build_hybrid_pptx, build_clone_deck, build_brochure_v3_deck, build_v3_hybrid_editable |
| Extraction | 5 | ~803 | extract_editable_text_slots, publish_extraction, scaffold_extraction, scaffold_slide_from_component, convert_pdf_source |
| Scoring | 2 | ~567 | score_visual_items, apply_text_contract |
| Utility | 10 | ~643 | _common, build_registry, build_component_catalog, build_template_picker_data, build_text_slot_gallery, update_capabilities, cleanup_run, package_job, prune_empty_dirs, read_text_slots |
| SVG Manipulation | 6 | ~1,088 | decompose_svg_objects, flatten_svg_background, crop_svg_region, optimize_svg, externalize_svg_images, generate_item_preview |
| Rendering | 1 | ~645 | generate_template_preview |
| JavaScript | 4 | ~1,093 | capture-slides.js, export-pdf.js, measure_svg_groups.js, render_svg.js |
| Shell | 2 | ~236 | setup.sh, export-pure-plugin.sh |

### Code Quality Checklist

- [x] All Python scripts have `#!/usr/bin/env python3` shebang
- [x] All use `from __future__ import annotations`
- [x] All have module-level docstrings
- [x] All use `argparse` for CLI
- [x] All use `if __name__ == "__main__": raise SystemExit(main())`
- [x] Shared `_common.py` module with `load_json`, `write_json`, `sha256_file`, `now_iso`
- [x] No hardcoded absolute paths (all relative via `Path(__file__)`)
- [x] Error handling via `raise SystemExit(message)`
- [x] Type hints throughout

### Schemas (8 files)

| Schema | Draft | Status |
|--------|-------|--------|
| `capabilities.schema.json` | 2020-12 | ✅ Valid |
| `extraction-report.schema.json` | 2020-12 | ✅ Valid |
| `extraction-request.schema.json` | 2020-12 | ✅ Valid |
| `job-requirements.schema.json` | 2020-12 | ✅ Valid |
| `run-manifest.schema.json` | 2020-12 | ✅ Valid |
| `selection-report.schema.json` | 2020-12 | ✅ Valid |
| `text-slots.schema.json` | 2020-12 | ✅ Valid |
| `visual-item.schema.json` | 2020-12 | ✅ Valid |

---

## 7. Registries Status

| Registry | Size | Items | Status |
|----------|------|-------|--------|
| `visual-library.json` | 483KB | 79 items | ✅ Active |
| `visual-library-compact.json` | 83KB | 79 items | ✅ Projection |
| `extraction-history.json` | 131KB | — | ✅ History |
| `capabilities.json` | 113 lines | 11 tools | ✅ Active |
| `export-qa-thresholds.json` | — | — | ✅ Active |
| `extract-readiness.json` | 4KB | — | ✅ Active |
| `aliases.json` | — | Empty | ✅ Clean |

---

## 8. Issues Found

### 🔴 Critical (must fix before production)

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| C1 | Icon library asset missing | `sun.asset.guideline-icon-library` | Referenced 8 times, no physical files, not in registry. Slides using brand icons will fail brand compliance gate |
| C2 | Shape variants asset missing | `sun.style.guideline-shape-variants` | Referenced in rules/skills, extracted twice but never published to visual library |
| C3 | Score threshold contradiction | `rules/visual-selection.md` vs `workflows/select-visual-items.md` | adapt-local boundary: 55 vs 65 (10-point gap). Different behavior depending on which doc is followed |

### 🟡 Medium (should fix soon)

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| M1 | Export command missing args | `slide-generator/SKILL.md` step 12 | Missing `--slides` and `--out-dir` flags |
| M2 | `--prefer-set` +5 bonus undocumented | `slide-generator/SKILL.md` | Feature exists in code but not in skill docs |
| M3 | crop_svg_region unit assumption | `crop_svg_region.py` | Assumes normalized regions but schema allows pt/px/in — silent garbage crop |
| M4 | crop → validate ordering conflict | `crop_svg_region.py` vs `validate_text_slots.py` | Cropped components structurally cannot pass validation |

### 🟢 Low (fix when convenient)

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| L1 | Vietnamese text in docs | `build-html-deck.md` line 56 | Unfinished translation |
| L2 | Orphaned skill | `pptx-html-fidelity-audit` | Not referenced by any workflow |
| L3 | `cleanup_run.py` wording | `cleanup_run.py` lines 41-46 | Implies export-result.json kept but it's deleted |
| L4 | `--brand-pack` not consumed | `validate_brand_compliance.py` | Flag parsed but never used |
| L5 | `publish-components.md` minimal | `workflows/publish-components.md` | Missing script invocations |
| L6 | `compare_renders.py` deprecated | `compare_renders.py` line 36 | `diff.get_flattened_data()` deprecated in Pillow |

---

## 9. Action Plan

### Phase 1: Critical Fixes (Priority: HIGH)

#### Task 1.1: Re-extract and publish icon library asset

**Target:** `sun.asset.guideline-icon-library`

**Steps:**
1. Check `extraction-history.json` for the original extraction source
2. Locate the source slide/document
3. Run extraction pipeline on the icon library page
4. Run `publish_extraction.py` to add to visual library
5. Run `build_registry.py` to update compact registry
6. Verify the asset appears in `visual-library.json`
7. Test brand compliance gate with a slide using brand icons

**Verification:**
```bash
python3 slide-system/scripts/validate_registry.py
python3 slide-system/scripts/build_registry.py
```

**Acceptance Criteria:**
- `sun.asset.guideline-icon-library` exists in `visual-library.json` with `status: published`
- Physical files exist in `slide-system/library/assets/`
- `validate_brand_compliance.py` passes for slides using brand icons

---

#### Task 1.2: Re-extract and publish shape variants asset

**Target:** `sun.style.guideline-shape-variants`

**Steps:**
1. Check `extraction-history.json` for the original extraction source
2. Locate the source slide/document
3. Run extraction pipeline on the shape variants page
4. Run `publish_extraction.py` to add to visual library
5. Run `build_registry.py` to update compact registry
6. Verify the asset appears in `visual-library.json`
7. Test `component-composition.md` rules reference

**Verification:**
```bash
python3 slide-system/scripts/validate_registry.py
python3 slide-system/scripts/build_registry.py
```

**Acceptance Criteria:**
- `sun.style.guideline-shape-variants` exists in `visual-library.json` with `status: published`
- Physical files exist in `slide-system/library/`
- Component composition rules can resolve the asset

---

#### Task 1.3: Fix score threshold contradiction

**Target:** `rules/visual-selection.md` AND `workflows/select-visual-items.md`

**Steps:**
1. Read both files to confirm the discrepancy
2. Determine which threshold is correct (likely 65 from workflow, since it's more conservative)
3. Update `rules/visual-selection.md` to match `workflows/select-visual-items.md`
4. Also verify `slide-generator/SKILL.md` consistency
5. Update any scoring logic in `score_visual_items.py` if needed

**Files to edit:**
- `/slide-system/rules/visual-selection.md` (line ~15: change 55 to 65)
- Verify: `/slide-system/workflows/select-visual-items.md`
- Verify: `/slide-system/rules/visual-selection.md`

**Acceptance Criteria:**
- Both files show adapt-local boundary as 65-74
- `score_visual_items.py` thresholds match documentation

---

### Phase 2: Medium Fixes (Priority: MEDIUM)

#### Task 2.1: Update slide-generator SKILL.md export command

**Target:** `.agents/skills/slide-generator/SKILL.md` step 12

**Steps:**
1. Read the SKILL.md to find step 12
2. Check the actual `export_pptx.py` script for required args
3. Update the export command to include `--slides` and `--out-dir`

**Acceptance Criteria:**
- Export command in SKILL.md matches actual script requirements

---

#### Task 2.2: Document --prefer-set bonus

**Target:** `.agents/skills/slide-generator/SKILL.md`

**Steps:**
1. Find where `--prefer-set` is used in the codebase
2. Add documentation about the +5 scoring bonus to the skill

**Acceptance Criteria:**
- `--prefer-set` behavior is documented in SKILL.md

---

#### Task 2.3: Fix crop_svg_region.py unit handling

**Target:** `slide-system/scripts/crop_svg_region.py`

**Steps:**
1. Read the current implementation
2. Check the extraction-request.schema.json for allowed units
3. Add unit conversion logic (pt, px, in → normalized)
4. Update `validate_text_slots.py` ordering if needed

**Acceptance Criteria:**
- Script handles pt/px/in units correctly
- No silent garbage crops

---

### Phase 3: Low Priority Fixes (Priority: LOW)

#### Task 3.1: Translate Vietnamese text

**Target:** `slide-system/workflows/build-html-deck.md` line 56

**Steps:**
1. Read the line
2. Translate to English
3. Update the file

---

#### Task 3.2: Add script invocations to publish-components.md

**Target:** `slide-system/workflows/publish-components.md`

**Steps:**
1. Read the current minimal workflow
2. Add explicit `publish_extraction.py` and `build_registry.py` commands
3. Add validation steps

---

#### Task 3.3: Fix cleanup_run.py wording

**Target:** `slide-system/scripts/cleanup_run.py`

**Steps:**
1. Read lines 41-46
2. Fix the wording about export-result.json

---

#### Task 3.4: Fix compare_renders.py deprecation

**Target:** `slide-system/scripts/compare_renders.py`

**Steps:**
1. Replace `diff.get_flattened_data()` with `list(diff.getdata())`

---

## 10. Scoring

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Documentation completeness | 9.0/10 | 15% | 1.35 |
| Skill coverage | 9.5/10 | 15% | 1.43 |
| Code quality | 9.0/10 | 20% | 1.80 |
| Schema & Registry | 9.5/10 | 10% | 0.95 |
| Workflow clarity | 8.0/10 | 10% | 0.80 |
| Cross-reference integrity | 7.5/10 | 15% | 1.13 |
| Production readiness | 8.5/10 | 15% | 1.28 |
| **TOTAL** | | **100%** | **8.73/10** |

---

## Appendix A: Cross-Reference Verification

### All Script References (Workflows → Scripts)

| Workflow | Script Referenced | Exists |
|----------|-------------------|--------|
| build-html-deck | validate_brand_compliance.py | ✅ |
| build-html-deck | validate_component_fidelity.py | ✅ |
| select-visual-items | score_visual_items.py | ✅ |
| select-visual-items | validate_selection_report.py | ✅ |
| export-editable-pptx | export_pptx.py | ✅ |
| export-editable-pptx | validate_export_objects.py | ✅ |
| extract-components | decompose_svg_objects.py | ✅ |
| extract-components | crop_svg_region.py | ✅ |
| extract-components | extract_editable_text_slots.py | ✅ |
| extract-components | validate_text_slots.py | ✅ |
| publish-components | publish_extraction.py | ✅ |
| publish-components | build_registry.py | ✅ |
| rebuild-catalog | build_component_catalog.py | ✅ |
| rebuild-catalog | build_template_picker_data.py | ✅ |
| check-requirements | check_requirements.py | ✅ |
| check-requirements | check_base_requirements.py | ✅ |
| verify-render-parity | compare_renders.py | ✅ |
| package-delivery | package_job.py | ✅ |
| resume-job | cleanup_run.py | ✅ |

### Broken References

| Reference | Referenced By | Issue |
|-----------|---------------|-------|
| `sun.asset.guideline-icon-library` | icon-selection.md, slide-generator/SKILL.md | Physical files missing |
| `sun.style.guideline-shape-variants` | component-composition.md, slide-generator/SKILL.md | Not in registry |

---

## Appendix B: File Inventory

| Directory | File Count | Total Lines |
|-----------|------------|-------------|
| slide-system/scripts/ | 48 | ~10,051 |
| slide-system/workflows/ | 15 | ~525 |
| slide-system/rules/ 11 | 11 | ~325 |
| slide-system/schemas/ | 8 | — |
| slide-system/registries/ | 7 | — |
| slide-system/boilerplates/ | 5 | — |
| .agents/skills/ | 13 | ~2,095 |
| docs/flows/ | 6 | — |
| **Total** | **113** | ~13,000+ |
