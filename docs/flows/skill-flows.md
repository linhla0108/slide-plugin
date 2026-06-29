# Skill flow simulation: /component-extractor & /slide-generator

> A simple summary, modeled after `.agents/skills/*/SKILL.md` (updated 2026-06-26).

---

## 1. /component-extractor — extract a component from a slide

**When to use:** the user explicitly specifies the region to extract (source file + page number + bounds/object ID). Never auto-scan the whole deck.

```
Input (PDF/PPTX/SVG + page + region)
        │
        ▼
[0] Preflight (marker-first)
        │   grep "ready" in extract-readiness.json → proceed, do NOT run the script
        │   For PDF/PPTX only: run check_base_requirements.py --input pdf|pptx (PyMuPDF/LibreOffice gate)
        ▼
[1] Validate request + fingerprint the region + check for duplicates
        │   (extraction-history, aliases, shared registry)
        ▼
[2] Scaffold staging item in outputs/component-extractions/
        │   classify artifact → choose extraction method by type
        ▼
[3] Run the standard script chain (do NOT hand-write visual.svg / text-slots.json):
        │   a. convert_pdf_source.py        ← PDF→SVG, PyMuPDF, the only allowed path
        │   b. extract_editable_text_slots.py ← split out text-free visual.svg + text-slots.json + evidence
        │   b2. crop_svg_region.py          ← crop visual.svg down to the exact source.region (component-level)
        │                                     PDF→SVG produces the whole page; skipping this step = the artifact is still the whole slide
        │                                     no-op when region = full-page; idempotent (marker source.region_crop)
        │   c. externalize_svg_images.py    ← extract images into shared assets/
        │   d. flatten_svg_background.py    ← merge PDF background strips into a single PNG (pixel-diff gated)
        │   e. externalize_svg_images.py    ← run again to refresh the manifest after flatten
        │   f. optimize_svg.py
        │   g. apply_text_contract.py
        │   h. validate_text_slots.py       ← final gate, fail means stop
        │
        │   [conditional decomposition — runs after h when the region contains sub-components]
        │   i. classify_page_components.py  ← decompose cropped region into distinct component groups
        │      measures every group in real Chromium layout (matrix/clipPath resolved),
        │      drops off-canvas leaves (crop leaves vector junk behind), then:
        │        • spatial clustering (2D bbox-overlap union-find, NOT document order)
        │        • shape-class classification (congruent w×h within tolerance)
        │        • proximity-run splitting (same-shape instances nearby → one group)
        │      emits one fragment SVG per group (whole run, each member's real color preserved)
        │      and per-card source/text-free variants when a strip contains repeat cards
        │      + artifact/components/components-manifest.json
        │      auto-stage strip Drafts use --manifest-only:
        │        • parent Draft remains visible in Components → Draft
        │        • carousel = full component, text-free full component,
        │          each card with text, each card text-free
        │      manual materialize_groups() → create a real .gNN staging item per detected group
        │        • shape-class dedup: keep one representative per class (skip duplicate runs)
        │        • 10% coverage guard: if all groups together cover < 10% of canvas area,
        │          they are sub-elements of a larger diagram — skip materialization
        │        • each .gNN item runs crop→externalize→optimize→apply_text_contract
        │        • each .gNN item includes fragment SVGs → per-card variant carousel in Draft
        │      manual parent item → decomposed_into: [list of .gNN names] written to mapping.json
        │                            hidden from catalog staging (build_component_catalog skips it)
        │
        │   j. split_icon_sheet.py  ← icon_sheet type ONLY (dedicated splitter, not classify_page_components
        │      which drops small icons as below area-floor and cannot handle dense regular grids)
        │      snaps each icon cluster to its grid cell, produces one SVG per icon
        │      → artifact/icons/ + icons-manifest.json
        │      → catalog shows ONE tile with a searchable icon grid (not hundreds of separate tiles)
        ▼
[4] Write mapping.json (the main record) + evidence/notes.md
        │   artifact/ = visual.svg + text-slots.json (do not copy source images, no per-item README)
        ▼
[5] Build one gallery.html for the whole batch + update catalog staging + extraction history
        ▼
[6] User reviews each item → publish only approved items
            (publish_extraction.py: create preview/, confirm evidence/
             + gate: approval.status must equal "approved" in mapping.json before publish
             + gate: a component-level item without source.region_crop → block publish
             + audit trail: approved_by / approved_at from mapping.json approval block
               persisted into visual-library registry on publish)
```

**Hard rules:**
- Do not render a PDF/PPTX page to PNG as the visual → text gets "baked" into pixels, the validator can't catch it, and the gallery shows double text.
- A component-level item MUST be cropped to its `source.region` (`crop_svg_region.py`) before publishing — PDF→SVG produces the whole page, and without cropping the artifact is the whole slide with text removed, not a single component. The publish gate blocks if the `source.region_crop` marker is missing.
- A reusable SVG must not contain semantic `<text>`/`<tspan>`.
- Complex backgrounds (blur/shadow/mask/multi-stop gradient) → background-only PNG, **zero text**.
- The allowed libraries are decided by `REQUIREMENTS.md` — no tool-shopping.

---

## 2. /slide-generator — generate a slide deck from a prompt/file

**When to use:** the default entry point for every new slide-creation job.

```
Input (prompt / file / mixed)
        │
        ▼
[1] Intake & triage
        │   new user = non-technical: ask one question at a time, each with a guess,
        │   up to ~5-6 questions, lock in the export format here
        ▼
[2] Recap the brief in plain language → user CONFIRMS before building
        │   (recap = job requirements + export contract)
        ▼
[3] Create job + versioned run under outputs/slide-jobs/<job-id>/
        ▼
[4] Run the requirement checker (using the cached capability registry)
        ▼
[5] Blocking requirement present → STOP, unless the user approves an override
        ▼
[6] Analyze content + source authority
        ▼
[7] Draft the slide plan + score the PUBLISHED visual items in the library
        │   (do not select staging / deprecated / export-incompatible items)
        ▼
[8] Present one approval package → user reviews
        ▼
[9] Build HTML (only after approval)
        ▼
[10] Export to the exact format chosen in step 1 + 4-layer QA:
        │    content / object / render / parity
        ▼
[11] Package the run: checksums + reports + manifest
```

**Hard rules:**
- Export only the format locked in at intake — do not generate extra formats.
- Assets are referenced in place (brand pack, `<job-id>/assets/`) — the run does not re-copy assets.
- One `analysis/visual-requests.json` + one `analysis/selection-report.json` per run (not split per-section).
- `qa/export-renders/` is intermediate — delete it after parity passes.
- Do not extract components inline — to reuse, hand off to `/component-extractor`.
- Default brand: SUN.STUDIO.

---

## 3. Relationship between the two skills + current state

```
/component-extractor ──publish──▶ slide-system/library/ ──select──▶ /slide-generator
        (staging → approve)         (published items)        (only selects published)
```

- **Extraction side: ALREADY optimized (2026-06-11)** — flattened background, shared assets, 1920px reference. Do not re-optimize.
- **Export side: P1 3-layer ALREADY implemented (2026-06-12).** `export_pptx.py` orchestrates the chain capture→build→compose→compare→validate. `--mode layered` (default) splits base + overlay + native text. Details: see `docs/flows/3layer-export.md` and `docs/flows/slide-generator-workflow.md`.
