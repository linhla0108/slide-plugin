# Export PDF

## Renderer Selection

Pick the first renderer that is available and matches the source:

| Priority | Renderer | When to use | Requires |
|----------|----------|-------------|---------|
| 1 | **Playwright MCP** (`playwright-pdf`) | HTML-source deck → PDF. Default for all Claude Code environments including non-tech users. | Claude Code built-in — no installation |
| 2 | **LibreOffice** (`libreoffice`) | PPTX-source deck → PDF only; when the PDF must faithfully represent the PPTX object layout. | System install (`brew install libreoffice`). Check `capabilities.json → libreoffice.status` before use. |
| 3 | **Cannot render** | Both unavailable. | Record as a blocker in the QA report. Do not claim PDF parity. |

Check `slide-system/registries/capabilities.json` for current tool status before choosing.
Never attempt LibreOffice when its status is `unavailable`.

## Playwright MCP — Step-by-step

Use this path for every HTML-source deck, including all non-tech user sessions.

1. Serve the HTML deck via the Claude Code preview MCP (preferred) or a local
   static server using the bundled Node.js:
   `node -e "require('http').createServer(require('fs').createReadStream).listen(8080)"`
2. Navigate to the deck's first slide URL with `browser_navigate`.
3. Set the deck to presentation mode / full-screen if the deck supports it, or
   set the viewport to 1920×1080 so the layout matches the design canvas.
4. Call `browser_pdf` (Playwright MCP) with:
   ```json
   { "format": "A4", "landscape": true, "printBackground": true,
     "path": "outputs/<job-id>/<run-id>/exports/<deck-name>.pdf" }
   ```
   For a multi-slide HTML deck, iterate slides with `browser_evaluate` / `showJs`
   before each capture if single-call PDF does not cover all slides.
5. Verify page count matches the approved slide count.

## LibreOffice — Step-by-step

Use only when `libreoffice.status == "available"` and source is a PPTX file.

```bash
soffice --headless --convert-to pdf --outdir exports/ deck.pptx
```

## QA (both renderers)

1. Record: renderer name and version, font availability, page size, failures.
2. Verify: page count, dimensions, text visibility, image crop, base
   backgrounds, complex overlay images, and z-order.
3. Do not claim parity when the selected renderer cannot run or produces
   incorrect output.
4. Delete intermediate render images after parity check; keep only
   `qa-report.md`, metrics, and checksums.
