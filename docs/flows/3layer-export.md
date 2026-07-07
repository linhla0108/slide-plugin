# Simulation of the /slide-generator flow AFTER the 3-layer fix (export phase)

> A simulation of the **fixes / additions** to the workflow tree in `SKILL-FLOWS.md`,
> following the `EXPORT-PPTX-3LAYER-PLAN.md` plan (2026-06-11→12, after 6 review rounds:
> ① fixed 5 points; ② unified the flow — 1 manifest, 1 evaluate, 1 QA gate after compare, 3 phases;
> ③ isolate v1↔v2 — mode table, 6 rules, flat regression; ④ closed open issues — compose-check,
> 2-tier thresholds, quality first, fixture; ⑤ vector_source keeps the vector through the pipeline;
> ⑥ full-trace audit — capture produces 3 reference QA images, compose is step (c), regression
> is "structural equivalence"). **P1 implemented 2026-06-12.** P2 (autoshape, svgBlip) and P3 (REQUIREMENTS.md, smoke-test) not yet.
>
> Notation: `[KEEP]` unchanged · `[FIX]` modifies existing behavior · `[NEW]` newly added

---

## 1. /component-extractor — UNCHANGED

Extraction was already optimized on 2026-06-11 (flatten background, shared assets, reference 1920px).
The 3-layer plan **does not touch** this tree. The `visual.svg` output already preserves separation
(1 background image + separate foreground `<path>` elements) — which is exactly the raw material for svgBlip in P2.

---

## 2. /slide-generator — new tree with the fix points

```
Input (prompt / file / mixed)
        │
        ▼
[1] Intake & triage                                          [KEEP]
        ▼
[2] Recap brief → user confirms                              [KEEP]
        ▼
[3] Create job + versioned run                               [KEEP]
        ▼
[4] Requirement checker                                      [FIX] check_base_requirements.py
        │                                                          add export-chain gate:
        │                                                          node + playwright chromium
        │                                                          + python-pptx + Pillow
        ▼
[5] Blocking requirement → STOP                              [KEEP]
        ▼
[6] Analyze content + source authority                       [KEEP]
        ▼
[7] Slide plan + score visual items                          [KEEP]
        ▼
[8] Approval package → user approves                         [KEEP]
        ▼
[9] Build HTML                                               [FIX] add LAYER TAGGING contract:
        │     data-export-layer="base"      → passive background (sits in the base PNG)
        │     data-export-layer="overlay"   → complex object, + data-export-id
        │     data-export-group="<name>"    → group semantically into 1 overlay
        │     data-export-native="rect|…"   → native autoshape          (P2)
        │     data-export-skip              → text baked into raster   [KEEP]
        │     no tag → validator FAIL (B10) unless --allow-untagged
        │     1 tag covering ≥85% canvas → validator FAIL (B11, full-bleed)
        │
        │   [9b] Full-page artwork (visual.svg from extraction)      [NEW] decompose REQUIRED:
        │        python3 slide-system/scripts/decompose_svg_objects.py
        │                --svg <item>/artifact/visual.svg --out-dir <job>/assets/page-NN
        │        │  measure_svg_groups.js → bbox of each group (Chromium, resolve transform)
        │        │  cluster consecutive overlapping bboxes → 1 object (card = image+shadow+face)
        │        │  group ≥50% canvas wide, children separate → AUTO-SPLIT into child objects
        │        │  cluster ≥85% canvas → base-candidate (CSS background, no tag)
        │        └─ output: fragment SVGs + snippet.html (divs pre-tagged) + manifest
        ▼
[10] Export PPTX — BEFORE: 2 separate commands, 1 full-slide PNG + text box
     Export PPTX — AFTER:  1 orchestrator command, 3-layer PPTX
        │
        │   python3 slide-system/scripts/export_pptx.py             [NEW] the ONLY entry point
        │           --html <run>/deck.html --slides <N>                   (forbid ad-hoc generator)
        │           --out-dir <run> --output <run>/deck.pptx
        │           [--mode layered|flat]
        │           │
        │           ├─ (0) cache: key = sha(capture-slides.js)       [NEW] missing 1 of the 3 components
        │           │       + sha(HTML+assets)                             means the cache returns a "ghost render";
        │           │       + version pin Playwright/Chromium              --no-cache = escape hatch;
        │           │       match → skip capture, use old render           done right at P1
        │           │
        │           ├─ (a) capture-slides.js v2                      [FIX] multi-pass, 1 browser session
        │           │       │   wait for document.fonts.ready; brand    [NEW] an operational error of CAPTURE
        │           │       │   font fails to load → capture exits             (not of build —
        │           │       │   non-zero + disable animation                   font loads when Playwright shoots)
        │           │       │   (reuse the strip/restore text,          [KEEP] data-export-skip +
        │           │       │    chrome-hide infrastructure)                  export-hidden already work
        │           │       ├─ ONE page.evaluate returns {text[],     [FIX] merge text layout + object inventory
        │           │       │     objects[]}                               from the same DOM state (extend the
        │           │       │     · text: + real lineHeight,               existing evaluate at capture-slides.js:268,
        │           │       │       text-transform, letter-spacing,        saving 1 round-trip/slide)
        │           │       │       fontFamily per-item, real line count
        │           │       │     · objects: data-export-*: id, bbox,
        │           │       │       global z, transform, filter-extent
        │           │       ├─ pass REF-FULL: shoot full text+layers  [NEW] → slide-XX-ref-full.png — reference for
        │           │       │     (before strip, real text color)          tier-2 parity (QA ephemeral, deleted after pass)
        │           │       ├─ pass REF-NOTEXT: strip text,           [NEW] → slide-XX-ref-notext.png — reference for
        │           │       │     all layers visible                        tier-1 (= bg.png of v1; flat mode writes
        │           │       │                                              straight to bg.png, no double shoot)
        │           │       ├─ pass BASE: hide text + all overlays    [NEW] → slide-XX-bg.png (1920×1080,
        │           │       │                                              KEEP the current file name)
        │           │       ├─ pass OVERLAY (loop each group):        [NEW] show exactly 1 group, omitBackground,
        │           │       │     rect expanded by blur/shadow extent       → slide-XX-ov-<id>.png (transparent;
        │           │       │     (case C4)                                 2× is just the deviceScaleFactor param,
        │           │       │                                               not a new subsystem — P2 svgBlip replaces it)
        │           │       ├─ pass TEXT-LAYER: only text visible,    [NEW] → slide-XX-text.png — material for
        │           │       │     omitBackground                           tier-2 compose (QA ephemeral)
        │           │       └─ write export-manifest.json            [NEW] ONE file {manifest_version: 2, mode,
        │           │              (checkable JSON schema;                  slide, base, objects[], text[]} —
        │           │               each overlay records vector_source      z already merged; PNG is a temporary embed,
        │           │               → P2 svgBlip need not reverse-engineer) the vector is not lost across the pipeline;
        │           │                                                       the export-layout.json shim is emitted ONLY in
        │           │                                                       flat mode (layered emitting the shim = v1 build
        │           │                                                       picks it up by mistake → deck silently loses
        │           │                                                       overlays — forbidden)
        │           │
        │           ├─ (b) build_hybrid_pptx.py v2                   [FIX] composition from ONE manifest:
        │           │       ├─ 1 base picture at the slide bottom
        │           │       ├─ N overlay pictures, separate EMU      [NEW] shape.name = "Overlay: <id>"
        │           │       │     bounds, inserted by the merged z    [FIX] text can sit BELOW an object (C8);
        │           │       │     ALREADY in the manifest (no file          no more 2-JSON merge step
        │           │       │     merge)
        │           │       ├─ text box: drop the h×1.35 hack        [FIX] accurate line_spacing,
        │           │       │     + apply text-transform: uppercase  [P1!] wrong-character bug, not polish
        │           │       │     (letter-spacing, per-item font      (P2) the latin + cs/ea brand-pack
        │           │       │      map for accented Vietnamese)             is still in P2
        │           │       ├─ (P2) native autoshape + svgBlip       [NEW] simple shapes & vector scale ∞
        │           │       └─ build crashes ONLY on operational     [FIX] missing render / UNPARSEABLE manifest
        │           │             errors: it issues no quality             → crash; valid manifest but PPTX
        │           │             verdict (the text-run audit stays         mismatch → verdict of (e),
        │           │             print-form)                               NOT of build
        │           │
        │           ├─ (c) compose candidate (in the orchestrator)   [NEW] pure PIL, no second browser:
        │           │        · tier-1 = bg + ov-*.png by bounds/z          the material is already available from (a);
        │           │        · tier-2 = tier-1 + text.png                  LibreOffice PPTX→PNG = fallback option,
        │           │                                                       added only if the user re-approves
        │           │
        │           ├─ (d) compare_renders.py (parity)               [KEEP] pure measurement script — always exits 0,
        │           │        · tier-1 candidate vs ref-notext.png           only emits report.json + evidence
        │           │        · tier-2 candidate vs ref-full.png            (NOT a gate)
        │           │
        │           ├─ (e) validate_export_objects.py                [NEW] the ONLY QA gate — runs AFTER compare
        │           │        · PPTX zip+XML vs manifest: shape count       because it consumes report.json:
        │           │          (FAIL if 1 picture but manifest declares     every pass/fail verdict funnels into
        │           │          an overlay) / bounds ±0.02in / z / name      a single exit code
        │           │        · report.json vs configured thresholds
        │           │          (mean_err / changed_ratio, 2 tiers)
        │           │        · manifest vs JSON Schema
        │           │
        │           └─ (f) print machine-readable JSON result        [NEW] the LLM only reads metrics,
        │                   (pass/fail + metrics)                          does not open screenshots
        ▼
[11] Package the run (package_job.py)                         [KEEP] auto-prune of empty folders already present
```

---

## 3. Case table at the capture/build step (deciding the layer for each element)

```
Element on the slide
        │
        ├─ full-slide gradient/texture background ────────► BASE                (C1)
        ├─ vector decor / blob ──────────────────────────► separate OVERLAY    (C2)
        ├─ chart / diagram ──────────────────────────────► OVERLAY group       (C3)
        ├─ shadow/glow overflowing the bbox ─────────────► OVERLAY, expanded rect (C4)
        ├─ backdrop-filter (frosted glass)
        │       ├─ only base behind it ──────────────────► opaque OVERLAY (with background) (C5a)
        │       └─ another overlay behind it ────────────► bake into BASE + warn  (C5b)
        ├─ mix-blend-mode ───────────────────────────────► bake into BASE + warn  (C6)
        ├─ text inside an overlay (chart label)
        │       ├─ user needs to edit it ────────────────► NATIVE TEXT, strip from PNG (C7a)
        │       └─ decorative ───────────────────────────► data-export-skip → bake into overlay (C7b)
        ├─ text sitting BELOW an object ─────────────────► merged z, build respects it (C8)
        ├─ plain rotate(θ) ──────────────────────────────► record angle, PPTX rot (C9a)
        ├─ complex skew/matrix ──────────────────────────► bake into BASE + warn (C9b)
        ├─ rounded/masked photo image ───────────────────► transparent OVERLAY PNG (C10)
        ├─ intentional full-image deck ──────────────────► --keep-bg-text       (C11)
        │       (independent capture flag, combinable with --mode flat;
        │        NOT the definition of flat mode — flat = v1 hybrid strip-text)
        ├─ solid-fill card/pill/line ────────────────────► (P2) NATIVE autoshape (C12)
        └─ two overlays overlapping the same area ───────► allowed, z recorded correctly (C13)
                (the top one's shadow sits in its own PNG — accepted
                 because the compose order is preserved)
```

---

## 4. Hard rules — changes relative to SKILL-FLOWS.md

Keep all the old rules, **add**:

- `export_pptx.py` is the only PPTX export path — do not write a per-job generator
  (same spirit as "PyMuPDF is the only PDF→SVG provider").
- **v1↔v2 isolation** (the 6 full rules are in plan §1): `--mode flat` = frozen v1
  (strip text + text box, output unchanged); `--keep-bg-text` = a separate full-image flag,
  not a mode. Running the old script directly keeps the v1 default — the `layered` default is ONLY in
  the new orchestrator. The manifest must declare `manifest_version` + `mode`; the semantics of
  `slide-XX-bg.png` are read from the manifest, not inferred from the file name; the validator is mode-aware.
  The flat-mode regression test is fixed in `test_export_stack.py` — P1/P2 must not
  change the v1 output.
- `compare_renders.py` is not a gate (always exits 0) — `validate_export_objects.py` is the **only**
  QA gate, runs **after** compare, reads `report.json` + applies thresholds + checks count/bounds.
- Error boundaries: capture fails when fonts do not load; build crashes when a render is missing / the manifest
  is unparseable; a valid-manifest-but-mismatched-PPTX is the validator's verdict. No script
  other than the validator may issue a quality verdict.
- Capture FAILS (not a warning) when a brand font does not load — a fallback font corrupts
  both the base PNG and the text metrics.
- A slide that declares overlays but whose PPTX contains only 1 picture is a FAIL — caught at validator (e),
  after compare (the validator consumes report.json so it cannot run before parity).
- Flat-mode regression = "structural equivalence" (PNG compared by pixel, PPTX compared by XML/shape/geometry,
  layout.json compared by content) — NOT byte-level, because a PPTX is a zip with timestamps; the manifest
  is an additional artifact, not counted as a changed output.
- Overlay PNGs render at 2× display size (scale up to ~200% without breaking); the source vector
  → svgBlip in P2 (the manifest already keeps `vector_source` from P1).
- "Never describe a full-slide image deck as editable" [KEEP] — now enforceable by
  gate (e).

## 5. Additions to REQUIREMENTS.md (for LLMs outside the Claude app)

**No new row added** — the stack is identical to the existing "Standalone machine (no Claude app)" row
(`REQUIREMENTS.md:44`). Only **update that row** to name the export flow explicitly:

```
| Standalone machine (no Claude app) / Export editable 3-layer PPTX — export_pptx.py
| Node.js 18+ → ./slide-system/scripts/setup.sh (installs Playwright, python-pptx, Pillow) |
```

+ pin the Playwright/chromium version in setup.sh so the render is deterministic across agents.

## 6. Roadmap (3 phases — verify round 2 merged the doc-only P0 into P1)

Canonical fixture for the whole roadmap: a deck generated from `input/Interview_Workshop_Sunriser.pdf`
(12 pages, 1920×1080, pure vector + Vietnamese text — serves prototyping, flat regression,
threshold calibration; plan §10.4).

```
P1  step 0: PROTOTYPE transparent-overlay 1 slide   ◄── GATE before any other code:
    │       prove hide-siblings + omitBackground            also hide the slide root's CSS background,
    │       yields a pixel-correct transparent PNG          the recompose must match pixel-for-pixel
    │       FAIL → predefined fallback:
    │         (a) all overlays take the C5 bake-with-background path
    │             (opaque PNG with background — still a separate object on a static base), or
    │         (b) stop, rethink the layered approach
    │       — do not build capture v2 on an unproven technique
    └─► P1 MVP: manifest schema + fix rules/docs + capture v2 (1 evaluate, multi-pass)
                + build v2 + validator (the only gate, after compare) + orchestrator
                + cache fingerprint (key of 3 components) + fix uppercase
                + flat-mode regression test (v1 output UNCHANGED — isolation rule #5)
                → pull the overlay off the slide → base stays intact
        ──► P2 (autoshape, svgBlip replacing the 2× PNG for vector-source overlays,
                remaining rich text: letter-spacing / per-item font / multi-run)
        ──► P3 (update REQUIREMENTS.md:44, test_export_stack,
                smoke-test agent outside Claude)
```
