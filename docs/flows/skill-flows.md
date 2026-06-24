# Skill flow simulation: /component-extractor & /slide-generator

> A simple summary, modeled after `.agents/skills/*/SKILL.md` (updated 2026-06-23).

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
        ▼
[4] Write mapping.json (the main record) + evidence/notes.md
        │   artifact/ = visual.svg + text-slots.json (do not copy source images, no per-item README)
        ▼
[5] Build one gallery.html for the whole batch + update catalog staging + extraction history
        ▼
[6] User reviews each item → publish only approved items
            (publish_extraction.py: create preview/, confirm evidence/
             + gate: a component-level item without source.region_crop → block publish)
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
