#!/usr/bin/env node
/**
 * prototype_overlay_capture.js — P1 step 0 GATE for the 3-layer export plan.
 *
 * Proves (or disproves) the transparent-overlay capture technique on ONE slide
 * before any capture-v2 code is written (EXPORT-PPTX-3LAYER-PLAN.md §9 P1 step 0):
 *   hide siblings + hide the slide root's own CSS background + omitBackground
 *   → per-overlay transparent PNG whose PIL re-composition matches the original
 *   render pixel-for-pixel within the tier thresholds.
 *
 * Emits into --out-dir:
 *   ref-full.png      full slide, text intact      (tier-2 reference)
 *   ref-notext.png    full slide, text stripped    (tier-1 reference)
 *   base.png          base only (overlays + text hidden)
 *   ov-<id>.png       one transparent PNG per [data-export-layer="overlay"]
 *   text.png          text layer only, transparent
 *   proto-manifest.json  overlay clip bounds for composition
 *
 * Then run prototype_compose_check.py for the verdict.
 *
 * Usage: node prototype_overlay_capture.js --html <slide.html> --out-dir <dir>
 */

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const a = { html: null, outDir: null, pad: 96 };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--html") { a.html = argv[++i]; }
    else if (argv[i] === "--out-dir") { a.outDir = argv[++i]; }
    else if (argv[i] === "--pad") { a.pad = parseInt(argv[++i], 10); }
  }
  if (!a.html || !a.outDir) {
    console.error("usage: node prototype_overlay_capture.js --html <slide.html> --out-dir <dir>");
    process.exit(2);
  }
  return a;
}

// Style mutations are applied per pass on a freshly reloaded page, so no
// restore logic is needed — reload IS the restore.
const STRIP_TEXT = `
  (function () {
    var st = document.createElement("style");
    st.textContent = "h1,h2,h3,h4,h5,h6,p,span,li,td,th,label,a,div.__txt__ " +
      "{ color: transparent !important; text-shadow: none !important; }";
    document.head.appendChild(st);
  })()`;

const HIDE_TEXT = `
  (function () {
    document.querySelectorAll("h1,h2,h3,h4,h5,h6,p,span,li").forEach(function (el) {
      el.style.setProperty("visibility", "hidden", "important");
    });
  })()`;

const HIDE_OVERLAYS = `
  (function () {
    document.querySelectorAll("[data-export-layer='overlay']").forEach(function (el) {
      el.style.setProperty("visibility", "hidden", "important");
    });
  })()`;

// The risky part the prototype exists to test: kill every painted background
// behind the target so omitBackground yields true alpha.
const TRANSPARENT_CANVAS = `
  (function () {
    [document.documentElement, document.body, document.getElementById("slide")]
      .forEach(function (el) {
        el.style.setProperty("background", "none", "important");
        el.style.setProperty("background-color", "transparent", "important");
      });
  })()`;

async function main() {
  const a = parseArgs(process.argv);
  const { chromium } = require("playwright");
  fs.mkdirSync(a.outDir, { recursive: true });
  const url = "file://" + path.resolve(a.html);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });

  const fresh = async () => {
    await page.goto(url, { waitUntil: "load" });
    await page.evaluate("document.fonts.ready.then(() => true)");
    await page.waitForTimeout(150);
  };
  const shot = (name, opts = {}) =>
    page.screenshot({ path: path.join(a.outDir, name), type: "png", ...opts });

  // Inventory first (fresh DOM, real geometry).
  await fresh();
  const overlays = await page.evaluate(`
    Array.from(document.querySelectorAll("[data-export-layer='overlay']")).map(function (el) {
      var r = el.getBoundingClientRect();
      return { id: el.getAttribute("data-export-id"),
               x: r.left, y: r.top, w: r.width, h: r.height };
    })`);

  // Pass REF-FULL — everything intact.
  await shot("ref-full.png");

  // Pass REF-NOTEXT — text stripped, all layers visible (the v1-style bg render).
  await fresh();
  await page.evaluate(STRIP_TEXT);
  await shot("ref-notext.png");

  // Pass BASE — overlays hidden + text stripped: passive canvas only.
  await fresh();
  await page.evaluate(STRIP_TEXT);
  await page.evaluate(HIDE_OVERLAYS);
  await shot("base.png");

  // Pass OVERLAY — one at a time: hide text, hide other overlays, kill canvas
  // backgrounds, omitBackground, clip expanded by --pad for shadow bleed (C4).
  const manifest = { overlays: [] };
  for (const ov of overlays) {
    await fresh();
    await page.evaluate(HIDE_TEXT);
    await page.evaluate(`
      document.querySelectorAll("[data-export-layer='overlay']").forEach(function (el) {
        if (el.getAttribute("data-export-id") !== ${JSON.stringify(ov.id)})
          el.style.setProperty("visibility", "hidden", "important");
      })`);
    await page.evaluate(TRANSPARENT_CANVAS);
    const clip = {
      x: Math.max(0, Math.floor(ov.x - a.pad)),
      y: Math.max(0, Math.floor(ov.y - a.pad)),
    };
    clip.width = Math.min(1920 - clip.x, Math.ceil(ov.w + (ov.x - clip.x) + a.pad));
    clip.height = Math.min(1080 - clip.y, Math.ceil(ov.h + (ov.y - clip.y) + a.pad));
    await shot(`ov-${ov.id}.png`, { omitBackground: true, clip });
    manifest.overlays.push({ id: ov.id, png: `ov-${ov.id}.png`, clip, bbox: ov });
    console.log(`[proto] overlay ${ov.id}: clip ${clip.width}x${clip.height}@${clip.x},${clip.y}`);
  }

  // Pass TEXT-LAYER — only text, transparent canvas.
  await fresh();
  await page.evaluate(HIDE_OVERLAYS);
  await page.evaluate(TRANSPARENT_CANVAS);
  await shot("text.png", { omitBackground: true });

  await browser.close();
  fs.writeFileSync(path.join(a.outDir, "proto-manifest.json"),
    JSON.stringify(manifest, null, 2));
  console.log(`[proto] captured ${overlays.length} overlays + base + text + 2 refs → ${a.outDir}`);
}

main().catch((err) => { console.error("[proto] FATAL:", err.message || err); process.exit(1); });
