---
description: Extract reviewable component Drafts from a PDF
---

Load the `component-extractor` skill and follow it for this request:

$ARGUMENTS

For PDF auto-detection, use `slide-system/scripts/extract_pdf_components.py` so
preflight runs before analysis and Draft staging. Never publish automatically.
Serve review and publish actions only through
`slide-system/catalog/catalog_server.py`.
