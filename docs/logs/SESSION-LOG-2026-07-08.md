## 2026-07-08.1 — Backfill component metadata

**Request:** Open the metadata gate PR and continue with the next step: clean legacy component metadata so published components are ready for retrieval/RAG.
**Actions:**
- Created ready stacked PR #3 for `feature/component-metadata-quality-gate` against `feature/hybrid-rag-slide-retrieval`.
- Created follow-up branch `feature/component-metadata-backfill` from the metadata gate branch.
- Backfilled English retrieval metadata for the 10 published components that failed `validate_component_metadata.py`, replacing empty fields, auto-stage/Docling placeholder phrases, and OCR-like intent terms while preserving source, artifact paths, and text contracts.
- Rebuilt `slide-system/registries/component-retrieval-index.jsonl` after registry metadata changes.
- Added `test_component_metadata_live_registry_all_components_pass` so `test_gates.py` now enforces strict metadata validation across all published components.
**Result:** `python slide-system/scripts/validate_component_metadata.py --registry slide-system/registries/visual-library.json --strict` passes for all 13 published components; `python slide-system/scripts/test_gates.py` passes 149/149; registry and retrieval index checks pass.
**Files:** `slide-system/registries/visual-library.json`, `slide-system/registries/component-retrieval-index.jsonl`, `slide-system/scripts/test_gates.py`, `docs/logs/SESSION-LOG-2026-07-08.md`, `docs/logs/INDEX.jsonl`
**Symbols:** `test_component_metadata_live_registry_all_components_pass`
**State:** Not committed

## 2026-07-08.2 — Fix PR #4 review findings (stale compact, drift gate, metadata shape)

**Request:** Address tester findings on PR #4 so the backfill actually improves production retrieval: (P1) regenerate the stale `visual-library-compact.json`; (P2) make `build_registry.py --check` detect compact drift; (P2) normalize backfilled `intent`/`content_structure` to short canonical tokens.
**Actions:**
- `build_registry.py`: added `compact_text()` and a compact-staleness comparison to the `--check` path (parallel to the existing retrieval-index check), so a full-registry edit that forgets to regenerate the projection now fails `--check` with a clear `STALE ... (compact projection out of date — run --write)` message; added `_rel()` so STALE display is robust for out-of-repo paths (needed for tests). No publish-behavior change.
- Normalized `intent`/`content_structure` for the 10 backfilled components in `visual-library.json` to short retrieval tokens / slot-role vocab matching the style of the strong existing components (kept richer prose in `visual_summary`/`use_cases`/`anti_use_cases`/`retrieval_notes`/`quality_notes`; preserved set-of-N tokens, source, paths, text contracts, approval, status). Only `intent`/`content_structure` changed, on exactly 10 items.
- Ran `build_registry.py --write` to regenerate `visual-library-compact.json` and `component-retrieval-index.jsonl` deterministically from the authority registry.
- Added `test_build_registry_check_detects_stale_compact`, `test_build_registry_write_regenerates_stale_compact`, and `test_build_registry_live_compact_projection_is_clean` to `test_gates.py`.
- Retrieval eval (existing `score_visual_items.py` CLI, 9 queries, component-only): expected component is top-1 for **8/8** positive queries (q1 revenue-strip 73 adapt, q2 spicy-levels 86 reuse, q3 team-circles 73 adapt, q4 brand-icon 83 reuse, q5 checklist-manager 92 reuse, q6 translator 96 reuse, q7 recognition 75 adapt, q8 ai-team 92 reuse); control q9 (financial pie chart) stays `custom-local` (below reuse, no confident false positive). q1/q2 misses from the prior review were caused by the stale compact + phrase-shaped metadata, not inventory/magnet behavior.
**Result:** `--strict` metadata gate passes all 13; `test_gates.py` 152/152; `build_registry.py --check` clean (now including compact); `build_component_retrieval_index.py --check` clean (91); `validate_registry.py` 91 valid; `build_log_index.py --check` clean; `git diff --check` clean.
**Files:** `slide-system/scripts/build_registry.py`, `slide-system/registries/visual-library.json`, `slide-system/registries/visual-library-compact.json`, `slide-system/registries/component-retrieval-index.jsonl`, `slide-system/scripts/test_gates.py`, `docs/logs/SESSION-LOG-2026-07-08.md`, `docs/logs/INDEX.jsonl`
**Symbols:** `build_registry.compact_text`, `build_registry._rel`, `build_registry.main`, `test_build_registry_check_detects_stale_compact`, `test_build_registry_write_regenerates_stale_compact`, `test_build_registry_live_compact_projection_is_clean`
**State:** Not committed

## 2026-07-08.3 — Type-intent bias: components not out-ranked by templates in all-types mode

**Request:** After merging the retrieval stack to master, fix template-vs-component ranking in all-types mode so component-intent queries are not dominated by full-slide templates; smallest correct change, tests, no scoring redesign.
**Actions:**
- Updated local `master` to `origin/master` (`b232d194`) after discarding only the two named local log edits (`docs/logs/INDEX.jsonl`, `docs/logs/SESSION-LOG-2026-07-07.md`); branched `feature/template-component-ranking`.
- Baseline all-types eval (10 queries) reproduced the failure at `q3` (team contributor circles): template `sun.sun-presentation.04-contributors-layout` (81.0) out-ranked component `sun.component.team-contributor-circles.g01` (72.75) — the component actually had the higher semantic_intent (22.75) but lost the −10 zero-slot buildability penalty. 7/8 component top-1; both template controls won.
- `score_visual_items.py`: added `request_type_intent()` (reads `prefer_type`, else scans free-text `query`+intent+tags for component/template markers; template intent wins ties) and a bounded `TEMPLATE_DEMOTION = 15` applied in `score_request` only to `type == "template"` items when the request explicitly wants a component. One-directional; surfaced in `reasons` and `retrieval.type_bias`. No threshold/weight/floor/registry/publish changes; no new dependency.
- Added 6 focused tests in `test_gates.py` (detection; component-intent ranks component over a higher-raw-score template; template intent leaves templates; neutral applies no bias; components unchanged / component-only path unaffected; component-intent query with no fit does not become a confident reuse false-positive).
- Minimal doc note in `workflows/select-visual-items.md`.
**Result:** After all-types eval: **8/8** positive component top-1 (q3 flipped to the component), template controls **2/2**, neutral query unbiased (template still 81.0), negative pie-chart query stays `custom-local` (no component false-positive). `test_gates.py` 158/158; `validate_component_metadata --strict` all 13; `validate_registry` 91; `build_registry --check` clean; `build_component_retrieval_index --check` clean; `build_log_index --check` clean; `git diff --check` clean.
**Files:** `slide-system/scripts/score_visual_items.py`, `slide-system/scripts/test_gates.py`, `slide-system/workflows/select-visual-items.md`, `docs/logs/SESSION-LOG-2026-07-08.md`, `docs/logs/INDEX.jsonl`
**Symbols:** `score_visual_items.request_type_intent`, `score_visual_items.score_request`, `test_request_type_intent_detection`, `test_type_intent_component_query_ranks_component_over_template`, `test_type_intent_template_query_lets_template_win`, `test_type_intent_neutral_query_applies_no_bias`, `test_type_intent_leaves_components_unchanged`, `test_type_intent_no_component_false_positive_when_nothing_fits`
**State:** Not committed
