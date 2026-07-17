#!/usr/bin/env node
/**
 * export-pdf.js — Standalone HTML-deck → PDF exporter (no Claude Code required).
 *
 * Opens the deck URL in a headless Chromium browser via Playwright and prints it
 * to PDF with background graphics, on a page the exact size of the deck itself
 * (--width x --height, default 1920x1080 => a 1440x810pt landscape sheet).
 * For multi-slide HTML decks, iterates through all slides before printing.
 *
 * Usage:
 *   node export-pdf.js --url <deck-url> --output <file.pdf> [options]
 *
 * Options:
 *   --url        URL of the HTML deck (required)
 *   --output     Output .pdf path (default: deck.pdf)
 *   --deck       Path to the run's deck.html. Used to run the delivery gate
 *                (delivery_gate.py) before producing the PDF: an UNRESOLVED run
 *                (any needs_component slide in its sibling selection-report) is
 *                NOT a deliverable and no PDF is produced. Auto-derived from a
 *                file:// --url when omitted. A deck with no sibling
 *                analysis/selection-report.json (external/custom) is not gated.
 *   --skip-delivery-gate  Deliberately export an UNTRACKED external/custom deck
 *                (one with NO sibling analysis/selection-report.json) without the
 *                gate. It can NEVER bypass a tracked job: if a sibling
 *                selection-report exists next to the deck, this flag is refused
 *                and the gate still runs fail-closed.
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
const { fileURLToPath } = require("url");
const { spawnSync } = require("child_process");

// slide-system/scripts/export-pdf.js -> repo root is two levels up.
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DELIVERY_GATE = path.join(__dirname, "delivery_gate.py");

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = {
    url: null,
    output: "deck.pdf",
    deck: null,
    skipDeliveryGate: false,
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
    else if (key === "--deck") { args.deck = val; i++; }
    else if (key === "--skip-delivery-gate") { args.skipDeliveryGate = true; }
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
// Delivery gate — reuse delivery_gate.py (never reimplement its policy here) so
// the PDF output boundary refuses an UNRESOLVED run exactly like PPTX export.
// ---------------------------------------------------------------------------

// URL schemes are case-insensitive (RFC 3986) and the browser normalizes them, so
// this test MUST be too: a case-sensitive `startsWith("file://")` let `FILE:///…`
// look like "not a file URL", which skipped the deck/url match below and allowed a
// resolved --deck to vouch for a DIFFERENT deck that the browser then printed.
const FILE_URL_RE = /^file:\/\//i;

function isFileUrl(url) {
  return FILE_URL_RE.test(url || "");
}

// Absolute local path for a file:// URL.
//   string  -> a file URL we resolved
//   null    -> not a file URL at all
//   false   -> IS a file URL but unresolvable; callers must fail closed rather
//              than treat it as "no file URL" and skip the deck/url match.
function fileUrlDeckPath(url) {
  if (!isFileUrl(url)) return null;
  try { return path.resolve(fileURLToPath(url)); }
  catch { return false; }
}

// The run's deck.html, from --deck or a file:// --url. null => not a run we can
// locate (e.g. an http:// served URL with no --deck), so it cannot be gated.
function resolveDeckPath(args) {
  if (args.deck) return path.resolve(args.deck);
  const fromUrl = fileUrlDeckPath(args.url);
  return typeof fromUrl === "string" ? fromUrl : null;
}

// Windows paths are case-insensitive, so `E:\job\deck.html` and `e:\job\deck.html`
// are the SAME file; comparing them case-sensitively would falsely reject a
// legitimate export. POSIX stays case-sensitive.
function samePath(a, b) {
  return process.platform === "win32"
    ? a.toLowerCase() === b.toLowerCase()
    : a === b;
}

function siblingSelectionReport(deckPath) {
  return path.join(path.dirname(deckPath), "analysis", "selection-report.json");
}

function projectPython() {
  const candidates = process.platform === "win32"
    ? [path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")]
    : [path.join(REPO_ROOT, ".venv", "bin", "python3"),
       path.join(REPO_ROOT, ".venv", "bin", "python")];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

// Fail closed: an UNRESOLVED run must never produce a PDF through this route.
// A "tracked" job is one whose deck has a sibling selection-report — that report
// is authoritative and can NEVER be bypassed (not even with --skip-delivery-gate).
// Only an UNTRACKED deck (no sibling report) may be exported ungated.
function enforceDeliveryGate(args) {
  const fileUrlDeck = fileUrlDeckPath(args.url);
  const httpUrl = /^https?:\/\//i.test(args.url || "");

  // A file:// URL we cannot resolve must fail closed: treating it as "no file URL"
  // would skip the deck/url match and let --deck vouch for a different deck.
  if (fileUrlDeck === false) {
    die("--url is a file:// URL that could not be resolved to a local deck path. "
      + "Pass a well-formed file:// URL (file:///C:/... on Windows) so the delivery "
      + "gate can verify the exact deck being exported.");
  }
  // --deck names the deck being exported, so the browser MUST load that same deck.
  // Pairing --deck with any non-file URL (http://, data:, about:, ...) would let a
  // resolved deck gate the run while a different payload is printed.
  if (args.deck && fileUrlDeck === null) {
    die("--deck must be paired with the matching file:// --url of that same deck, so "
      + "the delivery gate verifies exactly what is exported. HTTP/other-scheme URLs "
      + "are external-only: drop --deck and pass --skip-delivery-gate for an "
      + "explicitly untracked external deck.");
  }
  if (httpUrl && !args.skipDeliveryGate) {
    die("tracked job PDFs must use a file:// --url so the delivery gate can verify "
      + "the exact deck. HTTP URLs are external-only and require explicit "
      + "--skip-delivery-gate.");
  }
  const deckPath = resolveDeckPath(args);
  if (deckPath && fileUrlDeck && !samePath(deckPath, fileUrlDeck)) {
    die("--deck must match the file:// --url so a tracked job cannot gate one "
      + "deck while exporting another.");
  }
  if (!deckPath && !args.skipDeliveryGate) {
    die("--deck is required for a non-file URL so the delivery gate can verify "
      + "the run. Use --skip-delivery-gate only for an explicitly untracked "
      + "external deck.");
  }
  const report = deckPath ? siblingSelectionReport(deckPath) : null;
  const tracked = report !== null && fs.existsSync(report);

  if (!tracked) {
    // Untracked/external/served deck: nothing to gate here. --skip-delivery-gate
    // is the deliberate, visible acknowledgement for this case only.
    if (args.skipDeliveryGate) {
      console.warn("[export-pdf] WARNING: --skip-delivery-gate set — exporting an "
        + "UNTRACKED external deck (no sibling selection-report) without the gate.");
    }
    return;
  }

  // Tracked job: the selection-report decides. The skip flag cannot bypass it.
  if (args.skipDeliveryGate) {
    die("--skip-delivery-gate cannot bypass a tracked job — a selection-report "
      + "exists next to the deck (" + report + "). Resolve every slide and export "
      + "via the normal pipeline; the gate is enforced.");
  }
  const python = projectPython();
  if (!python) {
    die("a selection-report exists next to the deck but the project Python "
      + "(.venv) was not found to run the delivery gate. Resolve the run and "
      + "export via the normal pipeline.");
  }
  const gate = spawnSync(python, [DELIVERY_GATE, "--deck", deckPath],
                         { cwd: REPO_ROOT, encoding: "utf-8" });
  if (gate.status !== 0) {
    const msg = (gate.stderr || gate.stdout || "delivery gate blocked this run").trim();
    die(msg);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const args = parseArgs(process.argv);
  if (!args.url) die("--url is required");

  // Delivery gate BEFORE launching a browser: an unresolved run produces no PDF.
  enforceDeliveryGate(args);

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
  // NO `landscape` here: --width/--height already describe the deck's own page
  // (1920x1080 => a landscape 1440x810pt sheet). Passing `landscape: true` as well
  // made Chromium apply the orientation a SECOND time and swap the paper to
  // 810x1440 portrait, which cropped the deck to ~56% of its width and left two
  // thirds of every page empty. The deck's dimensions are the orientation.
  await page.pdf({
    path: outputPath,
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
