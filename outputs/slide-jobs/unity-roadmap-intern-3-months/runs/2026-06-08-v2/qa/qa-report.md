# QA Report: LEVEL UP: UNITY ROADMAP v2

## Scope

- Output checked: `html/index.html`
- Format: static HTML deck, 1920x1080, 8 slides
- Source: `input/Prompt.md`
- Source checksum: `48fb72080a24c04eee3b0a48a935e1d61df52d3d7c4f7a75cdd50d600e10fb50`
- Variant: polished v2 of `2026-06-08-v1`

## Automated Checks

- Local HTML sanity script: passed
- Slide count: 8
- Local asset references checked: 13
- Missing assets: none
- VS Code diagnostics for `html/index.html`: no errors found
- HTML deck SHA-256: `e739fbb84cfc165b4303d96882e8b698f4bd2449d44203869d2a80339d7ce5ba`
- Deck-stage SHA-256: `eac2199dccb470b7ee752c62808131ede4f54ce3990d79a87336e67f53e7f30f`

## Browser Checks

- Opened `html/index.html#1` in the integrated browser; cover renders with title, Unity icon, CSS isometric motif, HUD copy, audience line, and SUN.STUDIO logo.
- Opened direct hash snapshots for slides 3, 5, 7, and 8 after polish.
- Verified slide 3 week grid content, slide 5 ownership staircase content, slide 7 Q&A prompt chips, and slide 8 Dio/closing content are present.
- Deck-stage overlay displayed correct counters for checked slides.

## Polish Verification

- Confirmed the v2 CSS keeps all checked slide text present in browser snapshots.
- Confirmed the ziczac week-card animation now preserves the intended offset after animation.
- Confirmed no local asset paths were broken by the v2 changes.

## Known Limitations

- This run exports HTML only.
- No real Unity 3D model asset is provided; cover uses local Unity/gamepad iconography and CSS geometry.
- Browser interaction with deck-stage overlay buttons can be intercepted by the stage in the integrated browser tool; direct hash navigation was used for slide-by-slide checks.