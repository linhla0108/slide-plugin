# Visual Library Catalog — Handoff

## Overview

Internal catalog UI for browsing all extracted visual components (published + staging/draft). Vanilla HTML/CSS/JS, no build step.

**URL**: Open `slide-system/catalog/index.html` via any local HTTP server rooted at the project directory.

```bash
# Quick start
python3 -c "
import http.server, os
os.chdir('/Users/home/Documents/work-space/sun-riser-2026')
s = http.server.HTTPServer(('',8766), http.server.SimpleHTTPRequestHandler)
s.serve_forever()
" &
open http://localhost:8766/slide-system/catalog/
```

## Architecture

```
slide-system/catalog/
├── index.html          # Page shell (toolbar, grid, modal structure)
├── catalog.css         # Design system + all component styles
├── catalog.js          # Rendering, state, carousel, slots overlay
└── catalog-data.json   # Generated data (DO NOT EDIT manually)
```

### Data Generation

```bash
python3 slide-system/scripts/build_component_catalog.py
```

- Reads from: `slide-system/registries/visual-library.json` (published items) + `outputs/component-extractions/*/items/*/mapping.json` (staging items)
- Outputs: `slide-system/catalog/catalog-data.json`
- Handles two mapping schemas (v1 with `candidate_stable_id`/`text_contract` and v2 with `artifact`/`evidence` dicts)
- All paths are **project-root-relative** (e.g., `outputs/component-extractions/.../artifact/background.png`)
- Collects all available images per item into an `images[]` array

## Features

| Feature | Description |
|---------|-------------|
| **Tabs** | Published / Draft with live counts |
| **Search** | Fuzzy match on name, id, type, brand, intent, tags |
| **Filters** | Type, Brand, Compatibility dropdowns |
| **Grid** | Responsive tile cards with lazy-loaded preview images |
| **Detail Modal** | Full-size preview with image carousel |
| **Image Carousel** | Prev/next arrows, dot indicators, image label counter |
| **Text Slots Overlay** | Toggle to show editable regions on the preview; click a slot to see typography details |
| **Compatibility Grid** | 4-column status matrix (HTML/PPTX/PDF/Canva) |
| **Keyboard Nav** | Arrow keys navigate items in modal; Escape closes |

## Image Resolution

The catalog resolves images in this priority:

1. `item.images[0].path` — pre-collected during data generation
2. Fallback text if no images available

In the modal, all images in `item.images[]` are displayed as a carousel with labels (e.g., "Preview", "Source with text", "Reference", variant names).

## CSS Design Tokens

```css
--bg: #faf9f7       /* page background */
--surface: #ffffff  /* card/modal backgrounds */
--ink: #1a1a1a      /* primary text */
--muted: #6b6560    /* secondary text */
--line: #e8e4de     /* borders */
--blue: #3333ff     /* accent, active states */
--orange: #ff5533   /* brand, draft status */
--green: #22a867    /* published status */
```

## Adding New Items

1. Run the extraction pipeline to produce `mapping.json` in `outputs/component-extractions/<batch>/items/<id>/`
2. Regenerate: `python3 slide-system/scripts/build_component_catalog.py`
3. Reload the catalog page

## Known Gaps

- 9 items from `sunriser-2026-slides-1-5` batch have only HTML artifacts (no image preview) — they show a fallback type label
- Source paths in the Info panel still show absolute filesystem paths for some items (cosmetic only, doesn't affect functionality)
- No pagination — all items render in one grid (fine for current ~93 items)
