# Export PDF

## Delivery gate (all PDF routes)

A PDF is a final deliverable, so the same unresolved-delivery rule as PPTX
applies: if the run's `analysis/selection-report.json` still holds any
`needs_component` slide, the job is UNRESOLVED and **no PDF is produced** —
resolve every slide first. This rule binds **every** PDF route below (the
standalone Node exporter AND the Playwright MCP `browser_pdf` route), because the
gate lives in `delivery_gate.py`, not in any one exporter.

**Route A — standalone Node exporter.** It runs `delivery_gate.py` itself before
it opens a browser:

```bash
node slide-system/scripts/export-pdf.js \
    --url file://<run>/deck.html \
    --deck <run>/deck.html \
    --slides N --showJs "goToSlide({n})" \
    --output <run>/exports/<name>.pdf
```

Pass `--deck <run>/deck.html` so the gate can find the sibling selection-report
(auto-derived when `--url` is a `file://` URL). For an `http(s)` URL, `--deck`
is required unless the caller explicitly confirms an untracked external deck with
`--skip-delivery-gate`.

**Route B — Playwright MCP `browser_pdf`.** This route does NOT go through the
Node exporter, so you MUST run the same gate as a preflight yourself (see the
step-by-step below) before calling `browser_pdf`.

**Tracked vs untracked (both routes).** A deck WITH a sibling
`analysis/selection-report.json` is a *tracked* job: the gate is enforced and can
never be bypassed. A deck with NO sibling report is an external/custom deck and is
not gated. `--skip-delivery-gate` (Node route only) is a deliberate, visible
acknowledgement for an untracked deck ONLY — it is refused for a tracked job.

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

0. **Delivery-gate preflight (required, fail-closed).** BEFORE navigating or
   calling `browser_pdf`, run the shared gate on the run's deck:

   ```bash
   .venv/Scripts/python.exe slide-system/scripts/delivery_gate.py --deck <run>/deck.html
   ```

   - **Tracked job** (a sibling `analysis/selection-report.json` exists): the
     command exits **non-zero** when any slide is unresolved/malformed and prints
     a catalog-safe message (never the internal `reason`). **STOP — do NOT call
     `browser_pdf`; produce no PDF.** Take the job to the user for library review.
     It exits `0` only when every slide is resolved; only then continue to step 1.
   - **Untracked/external deck** (no sibling report): the command exits `0`
     (`"gated": false`) and there is nothing to block — continue to step 1.

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
