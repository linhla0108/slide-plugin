#!/usr/bin/env node
/**
 * export-pdf.js — Standalone HTML-deck → PDF exporter (no Claude Code required).
 *
 * Opens the deck URL in a headless Chromium browser via Playwright and prints
 * it to PDF with background graphics, landscape orientation, and A4 page size.
 * For multi-slide HTML decks, iterates through all slides before printing.
 *
 * Usage:
 *   node export-pdf.js --url <deck-url> --output <file.pdf> [options]
 *
 * Options:
 *   --url        URL of the HTML deck (required)
 *   --output     Output .pdf path (default: deck.pdf)
 *   --slides     Number of slides (if omitted, prints the page as-is)
 *   --showJs     JS expression to navigate to slide N — use {n} as placeholder.
 *                Example: "goToSlide({n})"
 *   --delay      ms to wait after navigation (default: 600)
 *   --width      Viewport width in px (default: 1920)
 *   --height     Viewport height in px (default: 1080)
 *   --no-headless  Show browser window (for debugging)
 *
 * Requirements (run `npm install` in repo root first):
 *   - playwright  (npm package)
 *   Then: npx playwright install chromium
 *
 * Examples:
 *   # Single-page or print-ready deck
 *   node slide-system/scripts/export-pdf.js \
 *     --url http://localhost:8080 \
 *     --output outputs/my-job/run-001/exports/deck.pdf
 *
 *   # Multi-slide deck with navigation
 *   node slide-system/scripts/export-pdf.js \
 *     --url http://localhost:8080 \
 *     --slides 12 \
 *     --showJs "goToSlide({n})" \
 *     --output outputs/my-job/run-001/exports/deck.pdf
 */

const path = require("path");
const fs = require("fs");

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = {
    url: null,
    output: "deck.pdf",
    slides: null,
    showJs: null,
    delay: 600,
    width: 1920,
    height: 1080,
    headless: true,
  };
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i];
    const val = argv[i + 1];
    if (key === "--url") { args.url = val; i++; }
    else if (key === "--output") { args.output = val; i++; }
    else if (key === "--slides") { args.slides = parseInt(val, 10); i++; }
    else if (key === "--showJs") { args.showJs = val; i++; }
    else if (key === "--delay") { args.delay = parseInt(val, 10); i++; }
    else if (key === "--width") { args.width = parseInt(val, 10); i++; }
    else if (key === "--height") { args.height = parseInt(val, 10); i++; }
    else if (key === "--no-headless") { args.headless = false; }
  }
  return args;
}

function die(msg) {
  console.error(`[export-pdf] ERROR: ${msg}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const args = parseArgs(process.argv);
  if (!args.url) die("--url is required");

  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch {
    die("playwright not found. Run: npm install && npx playwright install chromium");
  }

  const outputPath = path.resolve(args.output);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  console.log(`[export-pdf] Launching browser → ${args.url}`);
  const browser = await chromium.launch({ headless: args.headless });
  const context = await browser.newContext({
    viewport: { width: args.width, height: args.height },
  });
  const page = await context.newPage();

  await page.goto(args.url, { waitUntil: "networkidle" });

  // For multi-slide decks: navigate to last slide so the full layout has rendered
  // at least once before PDF capture. Chromium PDF captures current DOM state.
  if (args.slides && args.showJs) {
    for (let i = 0; i < args.slides; i++) {
      const expr = args.showJs.replace("{n}", String(i));
      await page.evaluate(expr).catch(() => {});
      await page.waitForTimeout(args.delay);
    }
    // Return to first slide for the actual PDF capture
    const first = args.showJs.replace("{n}", "0");
    await page.evaluate(first).catch(() => {});
    await page.waitForTimeout(args.delay);
  }

  console.log("[export-pdf] Printing to PDF…");
  await page.pdf({
    path: outputPath,
    landscape: true,
    printBackground: true,
    width: `${args.width}px`,
    height: `${args.height}px`,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });

  await browser.close();
  console.log(`[export-pdf] Done → ${outputPath}`);
}

main().catch((err) => {
  console.error("[export-pdf] Fatal:", err.message || err);
  process.exit(1);
});
