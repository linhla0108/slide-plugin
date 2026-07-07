
## 12:03 — AI-workflow deck: component metadata remediation + component-first selection

**Request:** Run /slide-generator on ai-workflow-deck-brief.md; agent must auto-select, component-first (not template), with a mechanism to detect bad picks / non-standard metadata.

**Actions:**
- Edited brief: removed alternating cam/trắng background rule → 'theo brand guideline' (component-driven bg). Updated structure table, 9 slide headers, per-slide color notes, checklist.
- Ran scorer (all types) → picked templates (rich metadata) with 3 duplicate collisions. Detected as quality risk.
- Diagnosed root cause: component-only scoring maxed 45/100 (all < floor 65). Components had empty/garbage metadata (tags=0/cs=0 or docling OCR noise) → scorer blind → fell back to foreign-deck templates.
- Verified slot structure via read_text_slots --slots-only for 6 components (no heavy reads).
- Authored honest semantic metadata (intent/tags/content_structure) for 5 reusable components in visual-library.json (authority per build_registry header): circle-badge-set, overlap-circle-set, hexagon-diagram, goal-setting-checklist-table, translator-...-coach-card-set. Script: scratchpad/fix_component_metadata.py.
- Rebuilt registry (build_registry.py --write): regenerated compact + retrieval; purged 4 zombie history records.
- Re-scored component-first: components now 75-100 (S2=100, S4=91, S6=85, S7=78, S5=77, S3=75, S8=75); S1/S9 custom-local (no cover/closing component).

**Result:** selection-report.json = component-first, gate PASS (7 non-blocking content_shape warns). Metadata-fix mechanism proven. Awaiting build approval.
**Committed:** no (registry metadata + brief edits uncommitted).

### ROOT CAUSE vs patch (flagged by user 12:08)

The 5-component metadata edit is a TEMPORARY PATCH (hand-authored so this deck builds), NOT the root cause.

**Root cause:** the extraction/publish pipeline (auto_stage_candidates.py / publish_extraction.py) emits components with substandard semantic metadata — empty intent/tags/content_structure for manual extractions, OCR-noise for docling auto-staged — and NO gate enforces metadata quality at publish. The scorer needs canonical-vocab overlap (semantic floor 10.5/35) to select an item; empty/noise metadata pins every component at the 45-pt no-metadata floor (< adapt floor 65), so components are structurally unselectable and the scorer falls back to foreign-deck templates.

**Scope still broken after patch:** ~8 components unpatched; all future extractions inherit the same defect.

**Tasks opened:** #1 spec metadata-quality fix (do first) → #2 publish-time metadata gate (root cause, blocked by #1) → #3 backfill/triage remaining components (blocked by #1,#2). #4 build deck HTML on current patched state for review (independent).

**Next:** write spec (#1), then build HTML (#4) for user review before further root-cause work.

### ROOT CAUSE #2 — components are non-editable raster (found during build 12:12)

Scaffolding for the build revealed a deeper blocker than metadata:
- Every component preview.html has 0 wired .slot elements (scaffold_slide_from_component emits bg-only 'raster component' warning for all).
- visual.svg contains 0 vector <text>; artwork is external PNG <image> refs with text rasterized into the pixels.
- decompose_svg_objects reports '0 base-candidate' — no text-free base layer exists; every object is artwork-with-text.
- text-slots.json has slot coordinates but nothing to overlay onto (base still shows original text).

**Implication:** metadata fix made components SELECTABLE but they remain NOT FILLABLE. Reusing any component renders its original baked text (LOREM IPSUM / GOAL·KEY·RESULT / TRANSLATOR / Vietnamese OKR), so it cannot carry AI-workflow content. True component-first reuse is impossible with current published artifacts.

**Task #5 opened** (root cause #2): publish/extraction must emit a text-free base + wired editable slots, not flatten text into raster.

**Build decision:** for a reviewable deck now, build all 9 slides CUSTOM-LOCAL from brand tokens (editable, correct VN content), with layouts echoing the selected component structures (numbered badges, flow, tier ladder, checklist, role cards). Not preference — the only path to a correct-content deck until #5 is fixed.

### Build complete — deck.html for review (12:18)
- Built 9-slide custom-local deck: outputs/slide-jobs/ai-workflow-deck/runs/20260707-114700/deck.html. Brand tokens only, editable, layouts echo scorer-selected component structures (role cards, chevron flow, tier ladder, numbered, checklist, skills timeline). DIO wink (S1) + dancing (S9), logo badge.
- Selection-report rewritten reuse→custom-local with scorer_action/scorer_score preserved + curation_note (raster block). Selection gate PASS (warns: score>=75 but custom-local, expected).
- Brand compliance gate PASS (emoji OK, fonts OK after replacing var(--font-*) with literal Proxima Nova, colors 4<5 threshold, template_assets OK). Fidelity gate WARN-mode exits 0 (custom, no component markers — expected).
- Found gate bug: brand_fonts flags var(--font-*) tokens as non-brand (no CSS var resolution) → Task #6.
- Render verified via preview server :8100 — 9 slides, Proxima Nova loaded, logo+2 DIO images resolve, 0 overflow (all exactly 1080h). Screenshots S1 + S9 confirm on-brand.
- NOT exported to PPTX yet (user reviewing HTML first). No cleanup run yet.
**Committed:** no.

### Audit + fix pass (12:28)
User asked to re-check rules/workflow vs the generated deck. Findings fixed:
- A1 Colors→brand tokens only: gradient=var(--dio-highlight/sun-orange/sun-orange-dark); Do/Don't=var(--green)/var(--red); glass overlays via color-mix(var(--sun-white)); page bg=var(--line-strong). Brand gate now PASS 'All colors within brand palette' (0 warnings, was 4).
- A2 DIO resized 520/460 → 340/320px (user chose ~300-360 anchor; was violating 80-140 rule, now compromise).
- A3 Export tags: added data-export-layer/data-export-id to ALL visuals (65 tagged: cards, steps, tiers, numbered rows, strips, capsule, dio, logo, text blocks). Was only ~10.
- A4 Restored altered content: S7 golden rule full ('...để tối ưu performance và hạn chế agent overwhelm'); S3 title back to 'VÍ DỤ THẬT TỪ CHÚNG TA' + subline.
- A5 Logo added to closing S9 (rule: cover+closing). Logo width 239→167px (rule 120-180).
- B6 Backgrounds content-driven (user decision, no alternating): cam only S1/S3/S9 (hook+đinh+bookend); white S2/4/5/6/7/8. Restyled S5 ladder + S7 timeline for light bg.
- Verified: brand gate PASS, 0 overflow (9x1080), DIO 340/320, logo 167, 65 export tags, color-mix renders, Proxima loaded, images resolve. Screenshots S1/S7/S9.
**Committed:** no. PPTX export + cleanup still pending user go.

### CORRECTION — components ARE reusable (13:50)
User pushed back: not using brand icon set (hand-drew check/X) + not using card/timeline COMPONENTS (custom instead).
Rendered component visual.svg files in browser to verify my earlier 'baked text' claim:
- hexagon visual.svg → orange hexagon shapes + '+' connector, NO text.
- overlap-circle visual.svg → blue gradient circles, NO text.
=> visual.svg is a TEXT-FREE base; text lives in text-slots.json as an overlay layer. My ROOT-CAUSE #2 'text baked into PNG' was WRONG. Components ARE reusable via visual.svg background + text-slots overlay. Task #5 corrected: real issue is preview.html has no wired .slot elements (scaffold emits bg-only, misleading), but manual overlay path works.
- Brand icons: 417 individual vector SVGs exist at brand-icon-reference-sheet/icons/icon-*.svg (real <path>), but UNLABELED (manifest = geometry clusters, no names) — a discoverability gap. I violated the icon rule by hand-drawing check/X.
**Next:** rebuild component-fitting slides reusing real component base art + text-slots overlay; replace hand-drawn icons with brand icons.

### Component reuse + brand icons (14:06)
Acted on user's 2 rule complaints (hand-drawn icons; custom instead of components):
- Reuse method fixed: raw visual.svg as CSS background fails (external PNG/mask refs sandboxed); decompose per-object SVGs render EMPTY (lost #mask defs — pipeline defect). Working path = <object data=visual.svg type=image/svg+xml> (repo catalog uses same) + absolutely-positioned text overlay at text-slots fractions.
- S2 roles → lorem-ipsum-circle-badge-set (3 radial circles; scorer top was card-set 4-card, swapped for 3-count fit, documented). S5 tiers → foundation overlap-circle-set (3 blue circles). S7 skills → goal-keyresult hexagon (3 nodes + / x connectors). All via <object> + overlay, data-base-component marked.
- S1/S3/S4/S6/S8/S9 remain custom-local (no fitting published component; rule fallback 'no item fits -> slide-local').
- Icons: replaced hand-drawn check/X. Verified all 417 brand icons (3 contact sheets) — office/facilities domain, unlabeled, NO checkmark exists. Used brand icon-144 (magnifier=verify) for Do, icon-242 (X) for Don't on S6.
- Gates: brand compliance PASS (colors within palette, fonts ok, assets ok), component_fidelity PASS (3/3 matched on data-base-component), selection PASS, 0 overflow. Verified renders S2/S5/S7.
- Corrected earlier wrong finding: components NOT baked-text; they are reusable (task #5 already corrected).
**Committed:** no. PPTX export + cleanup_run still pending user go.

## LESSONS (14:10) — AI-workflow deck session

### Process
1. RENDER the artifact before concluding it's unusable. I claimed components had 'baked-in text' from grep (0 <text>) + scaffold warning (no .slot) and pivoted to full custom — WRONG. One <object> render showed text-free base art. WHEN a library artifact 'looks unusable' THEN render it (<object data=visual.svg>) before deciding; static signals mislead.
2. Audit against the skill's rules BEFORE building, not after. User caught icon + component-reuse violations post-build. WHEN starting a build THEN re-read standalone-item + component-build + icon rules and map each slide reuse/custom explicitly first.
3. Don't alter supplied copy. I truncated the golden rule + reworded S3 title. WHEN filling slots THEN paste brief text verbatim unless the user approves an edit.
4. Don't hand-make an asset before checking the library. I hand-drew check/X; a 417-icon set existed (though no checkmark).

### Technical (component reuse)
5. Reuse path that WORKS: <object data=visual.svg type=image/svg+xml> (loads external PNG + masks; same as repo catalog.js) + absolutely-positioned text overlay at text-slots fractional bounds x canvas. FAILS: (a) visual.svg as CSS background-image (external refs sandboxed, blank); (b) decompose per-object SVGs (render empty — mask defs lost).
6. Component canvases are wide bands (viewBox ~1999x640), not full slides — place as a band + scale, overlay in the component's own coord space.

### Systemic (library not fit)
7. The visual library is sourced from HR/office decks (interview, salary, performance, goal-setting). For a NEW-domain deck: templates=other decks' slides, components=fixed OKR/HR geometry+colors+slot-count, icons=facilities pictograms (no checkmark). Only 3/9 slides had a count-fitting component. Rules/gates DON'T detect domain mismatch; scorer selects on metadata, not usability/fit.
8. Selection score != buildability. Fixing metadata made components selectable but geometry/count/decompose issues remained.

### Defect tasks opened: #7 decompose mask-def loss, #8 icon labels + UI set, #9 scorer usability/domain-fit. (Prior: #1 metadata spec, #2 metadata gate, #3 backfill, #5 wire slots, #6 brand-gate var fonts.)
