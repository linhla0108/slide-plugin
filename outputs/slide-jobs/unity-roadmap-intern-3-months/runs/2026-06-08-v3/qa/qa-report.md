# QA Report: LEVEL UP: UNITY ROADMAP v3

## Scope

- Outputs checked: `html/index.html`, editable PPTX, PDF
- Format: static HTML deck, 1920x1080, 8 slides; hybrid editable PPTX; visual PDF
- Source: `input/Prompt.md`
- Source checksum: `48fb72080a24c04eee3b0a48a935e1d61df52d3d7c4f7a75cdd50d600e10fb50`
- Variant: creative Game HUD redesign based on `2026-06-08-v2`

## Automated Checks

- Local HTML sanity script: passed
- Slide count: 8
- Local asset references checked: 13
- Missing assets: none
- VS Code diagnostics for `html/index.html`: no errors found
- HTML deck SHA-256: `b0bbe652b1f12e9905d3ab00a05d2c093c32f8076569ef0f9dbafa84cdbdfa93`
- Deck-stage SHA-256: `eac2199dccb470b7ee752c62808131ede4f54ce3990d79a87336e67f53e7f30f`
- Requested CSS removal verified: `.support-zone.primary::before { display: none; }`

## Export Checks

- Rendered 8 HTML slide captures at 1920x1080 for export evidence.
- Editable PPTX built with native PowerPoint text boxes over HTML-rendered slide backgrounds because the skill's preferred `gen_pptx` tool is unavailable in this environment.
- PPTX ZIP integrity: passed.
- PPTX slide count: 8.
- PPTX native text runs: 158/158 matched the browser-measured layout export.
- PPTX media backgrounds: 8.
- PDF page objects: 8.
- PDF SHA-256: `1f340594fb051a0df924bb0b193f4745f95988ad2bad79d7602f5dd55bd227c9`
- PPTX SHA-256: `404ddadc61ede7d62b08ab234c3006158ee2b87fdc46430e2ea0cfc4208e0495`

## Browser Checks

- Opened direct hash snapshots for slides 2 through 8 after redesign.
- Verified slide 2 skill tree, slide 3 mission board, slide 4 production pipeline, slide 5 launch pad, slide 6 support radar, slide 7 Definition of Done, and slide 8 closing/Q&A hooks are present.
- Captured a screenshot of slide 6 support radar, the densest new layout, and confirmed no obvious text overlap in the rendered view.
- After the final polish pass, captured screenshots for slide 2 skill tree, slide 4 production pipeline, slide 6 support radar, and slide 7 Definition of Done.
- Verified slide 2 connectors now use SVG paths plus node ports, slide 4 uses a balanced pipeline console, slide 6 uses connected radar beams, and slide 7 uses a graduation gate checklist.
- Deck-stage overlay displayed correct counters for checked slides.

## Redesign Verification

- Confirmed the v3 CSS keeps all checked slide text present in browser snapshots.
- Confirmed all 8 requested creative ideas are represented in the deck structure.
- Confirmed no local asset paths were broken by the v3 changes.
- Confirmed the four user-flagged slides were repolished in place without changing the overall 8-slide structure.

## Known Limitations

- PDF is the visual-authority export generated from the HTML slide renders.
- PPTX uses a hybrid editable strategy: native editable text overlays on top of HTML-rendered backgrounds. This preserves visual fidelity better than a full manual rebuild while keeping slide copy editable.
- Three small support-role chips on slide 6 remain visually embedded in the rendered background to preserve exact card styling; the rest of the checked text is represented by native PPTX text boxes.
- No real Unity 3D model asset is provided; cover uses local Unity/gamepad iconography and CSS geometry.
- Browser interaction with deck-stage overlay buttons can be intercepted by the stage in the integrated browser tool; direct hash navigation was used for slide-by-slide checks.