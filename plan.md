# Master Plan - Polish SUN.RISER 2026 Deck

> Legacy contract: this file describes the historical SUN.RISER production
> job. New AI slide jobs use `.agents/skills/slide-generator/SKILL.md` and
> `slide-system/`.

## Purpose

This is the source of truth for polishing the 28-slide SUN.STUDIO deck. Work is
executed in three phases defined in `plan_per_phase.md`. Each phase uses the
same extraction, mapping, approval, build, export, and QA workflow.

The deliverables are:

- One navigable HTML deck at `1920x1080`, with directly editable static content.
- One editable PPTX, prioritizing native text and shapes.
- One PPT Master PPTX, prioritizing visual quality.
- Analysis, mapping, divergence, copy, export-limit, QA, and phase reports.

A full-bleed image PPTX is an optional fallback only when explicitly requested.

## Canonical Input

Use only the files under `input/`:

```text
input/
|-- SUN.RISER 2026 - Be professional at SUN.STUDIO.pptx
|-- SUN.RISER 2026 - Be professional at SUN.STUDIO.pdf
|-- SUN.RISER 2026 - Be professional at SUN.STUDIO (PNG)/
|   `-- 1.png ... 28.png
`-- SUN.RISER 2026 - Be professional at SUN.STUDIO (SVG)/
    `-- 1.svg ... 28.svg
```

The input inventory is confirmed as 1 PPTX, 1 PDF, 28 PNG files, and 28 SVG
files. Files outside `input/` are not valid sources for this workflow.

Before each phase, verify that its numbered PNG/SVG pairs exist and validate
their checksums in the phase manifest. If the four source formats disagree in
content or composition, create a divergence summary and ask the user which
source version is authoritative. Do not infer authority from timestamps.

## Source Authority

- **PPTX:** input content, object structure, original geometry, layer order, and
  editability.
- **SVG:** vector geometry, paths, transforms, layering, reusable vector assets,
  and vector effects.
- **PNG:** final input appearance and composition.
- **PDF:** render, font, line-break, and cross-source validation.
- **HTML:** source of truth for the polished output design after approval.

Text always comes from the PPTX. SVG text is cross-check evidence only. If SVG
text has been converted to paths, do not use OCR or path inference to replace
PPTX content. Prefer SVG geometry when its render agrees with the PNG.

## Required Skills

Load only the skills needed for the current step:

1. `.agents/skills/sun-studio-design-system/SKILL.md`
2. `.agents/skills/pptx/SKILL.md`
3. `.agents/skills/svg-extractor/SKILL.md`
4. `.agents/skills/make-a-deck/SKILL.md`
5. `.agents/skills/export-as-editable-pptx/SKILL.md`
6. `.agents/skills/ppt-master/SKILL.md`
7. Browser testing skill during visual QA

Use `hi-fi-design` only for deliberate visual exploration. Use
`interactive-prototype`, `make-tweakable`, or `send-to-canva` only when the user
explicitly requests those capabilities.

## Locked Requirements

- Preserve verbatim Vietnamese copy and existing English keywords.
- Preserve content grouping, hierarchy, relationships, reading order, and IA.
- Stay close to the PNG composition. Re-layout is limited to component
  substitution and small spacing/alignment corrections.
- Record copy improvements separately; never silently change approved content.
- Build with canonical SUN.STUDIO tokens and Proxima Nova.
- Use canonical blue `#3333FF`; flag `#3531FF` instead of silently mixing it.
- Use Dio, XO, and brand washes selectively and only when supported by the
  source or approved mapping.
- Export static slides unless animation is explicitly requested.

## Component Selection

Separate structure from treatment:

1. Consider `component-from-slide/` first.
2. Use a canonical design-system component when semantic fit or export
   reliability is clearly better; explain why the extracted component lost.
3. Apply a compatible treatment from `style-from-slide/` independently.
4. If nothing fits, stop and present:
   - the closest canonical component,
   - a slide-local adaptation of an existing component, and
   - a new reusable component proposal.

Do not create or modify a public reusable component without user approval.

## Multi-Source Extraction

For every slide:

1. Extract PPTX text, runs, paragraph/bullet order, shapes, groups, bounding
   boxes, z-order, fills, fonts, charts, and relationships. Inspect raw OOXML
   for SmartArt, group transforms, theme inheritance, SVG/EMF/WMF, and effects.
2. Validate and inspect SVG using `svg-extractor`:
   - `viewBox`, dimensions, aspect ratio;
   - IDs, groups, tree order, transforms, and z-order;
   - text/tspan and text-as-path warnings;
   - shapes, paths, fill, stroke, opacity, inline CSS, and presentation attrs;
   - gradients, patterns, clip paths, masks, filters, markers, symbols, and use;
   - embedded data URIs and external references.
3. Render or open the SVG in a browser and compare it with the PNG.
4. Use the PDF to validate font rendering, line breaks, and occluded content.
5. Merge the evidence into `content-manifest.json` and
   `wireframe-content-map.json`.

The content manifest stores exact Unicode text, paragraph/run order, bullet
hierarchy, and meaningful line breaks. Comparison tooling may normalize
Unicode/whitespace, but output content must not be silently normalized.

## Mapping And Approval Gate

Create both slide-level and region-level mapping.

Slide-level mapping records composition, global reading path, layering,
component relationships, and why the proposal remains faithful to the PNG.

Each region records:

```text
region_id
reading_order_index
parent_child
semantic_role
verbatim_text
visual_cues
candidate_components
proposed_component
reason_chosen_and_rejected
visual_treatment
confidence
source_evidence
svg_source
svg_element_ids
vector_asset_candidates
svg_text_mode
unsupported_features
editable_pptx_risk
editable_pptx_vector_strategy
ppt_master_strategy
approval_status
```

Present the mapping report before building. Build only after explicit user
approval. Unmatched or low-confidence regions are blocking decisions.

## Build And Export

### HTML

- Use static HTML in a navigable `<deck-stage width="1920" height="1080">`.
- Keep each editable text item in a leaf element.
- Use canonical tokens and self-contained, resolvable font/asset paths.
- Do not depend on `../project/fonts` or external workspace paths.

### Editable PPTX

Use `export-as-editable-pptx` through its `gen_pptx` tool call:

- `width: 1920`, `height: 1080`
- `resetTransformSelector: "deck-stage"`
- `showJs: "document.querySelector('deck-stage').goTo(N)"`
- `selector: "deck-stage > [data-deck-active]"`

Keep Proxima Nova unless the user approves a fallback. On font timeout, first
repair paths/CORS, wait for `document.fonts.ready`, and retry. All content text
and primary structural shapes must remain editable. Only complex decoration may
fall back to SVG/image, and every fallback must be documented. Never rasterize
the whole slide.

### PPT Master PPTX

Treat PPT Master as an independent SVG pipeline, not an HTML converter. Supply
a working package containing the approved HTML screenshot, content manifest,
approved mapping, SUN.STUDIO tokens/fonts/assets, and design constraints.

Never move the canonical files from `input/`. Create a disposable working copy,
then satisfy PPT Master's required `import-sources --move` workflow on that
copy. Follow all PPT Master blocking confirmations, sequential SVG generation,
quality checks, visual review, finalization, and export requirements.

## Divergence Categories

Record differences as:

- `intentional-polish`
- `unintended-mismatch`
- `export-degradation`
- `accepted-limitation`

Each record includes slide/region, affected output, severity, evidence, cause,
resolution, and approval status. Intentional approved polish is not an error.

## Artifact Structure

```text
reports/
|-- phase_1.md
|-- phase_2.md
`-- phase_3.md
outputs/
|-- phase-01-slides-01-10/
|-- phase-02-slides-11-20/
`-- phase-03-slides-21-28/
```

Each phase output contains:

```text
manifest.json
inputs/
analysis/
  content-manifest.json
  wireframe-content-map.json
  component-mapping-report.md
  divergence-review.md
  copy-improvements.md
  export-limitations.md
  svg/
html/
pptx/
qa/
```

The phase manifest records input filenames/checksums, authoritative source
decisions, slide IDs, component/style checksums, approvals, outputs, font
strategy, QA results, and accepted limitations.

## QA And Completion

Run a bounded render-review-fix loop of at most three iterations per output.
Render HTML and both PPTX outputs to images and check content, overflow,
collisions, line wrapping, font substitution, composition, and export fidelity.

If significant errors remain at the iteration cap, do not mark the phase
complete. Record the blocker, provide comparison evidence, and ask the user to
accept the limitation or approve another approach.

A phase is complete only when:

- its mapping is approved;
- content diff passes;
- PNG/SVG coverage and SVG validation pass;
- HTML renders correctly at `1920x1080`;
- editable PPTX meets the native-object contract;
- PPT Master output passes its quality and visual checks;
- remaining limitations are explicitly accepted;
- its phase report is current; and
- the user approves the phase.

The next phase cannot start before the current phase is approved.
