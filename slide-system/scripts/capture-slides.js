#!/usr/bin/env node
/**
 * capture-slides.js — Render each slide to PNG and extract DOM text layout.
 *
 * Produces two outputs in --out-dir:
 *   slide-01-bg.png, slide-02-bg.png … — TEXT-FREE background renders (1920x1080)
 *   export-layout.json                  — DOM text positions for build_hybrid_pptx.py
 *
 * Each background is captured AFTER hiding the slide's editable text (boxes /
 * pills / cards stay), so build_hybrid_pptx.py can overlay native editable text
 * without doubling it. Mark text PowerPoint can't reproduce (gradient /
 * background-clip:text / SVG glyphs) with [data-export-skip] to keep it baked in
 * the PNG. Pass --keep-bg-text to disable stripping entirely.
 *
 * This replaces the manual QA render + by-hand text-strip Claude Code did in the
 * browser for Phase 1. Run this first, then build_hybrid_pptx.py.
 *
 * Usage:
 *   node capture-slides.js --url <deck-url> --slides <count> --out-dir <dir> [options]
 *
 * Options:
 *   --url        URL of the HTML deck served locally (required)
 *   --slides     Total number of slides (required)
 *   --out-dir    Output directory for PNGs + export-layout.json (required)
 *   --showJs     JS expression to navigate to slide N — use {n} as 0-based index.
 *                For deck-stage: "document.querySelector('deck-stage').goTo({n})"
 *                For goToSlide: "goToSlide({n})"
 *   --selector   CSS selector for the active slide element (captures that element only)
 *                For deck-stage: "deck-stage > [data-deck-active]"
 *   --delay      ms to wait after navigation (default: 600)
 *   --width      Viewport width px (default: 1920)
 *   --height     Viewport height px (default: 1080)
 *   --keep-bg-text  Do NOT strip text from the background PNG (default: strip).
 *                Use for decks intended to ship as full-image backgrounds.
 *
 * Text extraction:
 *   Queries all visible text-bearing elements inside the active slide and
 *   records tag, class, text, bounding box, fontSize, fontWeight, color, align.
 *   These become the native text boxes in the PPTX.
 *
 * Requirements: npm install && npx playwright install chromium
 */

const path = require("path");
const fs = require("fs");

function parseArgs(argv) {
  const a = { url: null, slides: null, outDir: null, showJs: null,
               selector: null, delay: 600, width: 1920, height: 1080,
               keepBgText: false };
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    if (k === "--url")      { a.url = v; i++; }
    else if (k === "--slides")   { a.slides = parseInt(v, 10); i++; }
    else if (k === "--out-dir")  { a.outDir = v; i++; }
    else if (k === "--showJs")   { a.showJs = v; i++; }
    else if (k === "--selector") { a.selector = v; i++; }
    else if (k === "--delay")    { a.delay = parseInt(v, 10); i++; }
    else if (k === "--width")    { a.width = parseInt(v, 10); i++; }
    else if (k === "--height")   { a.height = parseInt(v, 10); i++; }
    else if (k === "--keep-bg-text") { a.keepBgText = true; }
  }
  return a;
}

function die(msg) { console.error(`[capture-slides] ERROR: ${msg}`); process.exit(1); }

// DOM query that runs inside the page — extract text layout from active slide.
function extractLayoutScript(selector) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  // Returns { canvasW, canvasH, items[] }.
  // - Coordinates are RELATIVE to the slide root (root.left/top subtracted), so
  //   the output is independent of where the slide sits in the viewport.
  // - canvasW/canvasH = the root's own rendered size. With deck-stage `noscale`
  //   this is the authored design size (1920x1080), and fontSize (unscaled CSS
  //   px) is in the SAME space — so build_hybrid_pptx can scale both with one
  //   factor. (Verified against Phase 1: 960pt / 1920px = 0.5.)
  // - LEAF text only (direct text-node children). A heading whose text lives in
  //   child <span>s yields the spans, NOT the parent — this avoids the
  //   parent/child duplication the Phase 1 build had to patch with should_skip.
  // - Elements with [data-export-skip] (or any ancestor with it) are EXCLUDED;
  //   they stay baked into the PNG background (use for gradient/SVG-styled text
  //   that PowerPoint cannot reproduce as a plain text box).
  return `
    (function() {
      var root = ${root};
      if (!root) return { canvasW: 0, canvasH: 0, items: [] };
      var rootRect = root.getBoundingClientRect();
      var TEXT_TAGS = new Set(['p','h1','h2','h3','h4','h5','h6','span','li','td','th','label','strong','em','div','a','b','i']);
      var results = [];
      function hasSkipAncestor(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType === 1 && n.hasAttribute && n.hasAttribute('data-export-skip')) return true;
        }
        return false;
      }
      var all = root.querySelectorAll('*');
      all.forEach(function(el) {
        if (!TEXT_TAGS.has(el.tagName.toLowerCase())) return;
        if (hasSkipAncestor(el)) return;
        // Leaf text: only direct text-node children of this element.
        var text = '';
        for (var i = 0; i < el.childNodes.length; i++) {
          if (el.childNodes[i].nodeType === 3) text += el.childNodes[i].textContent;
        }
        text = text.trim();
        if (!text) return;
        var r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return;
        var cs = window.getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) return;
        results.push({
          tag: el.tagName.toLowerCase(),
          cls: (typeof el.className === 'string' ? el.className : ''),
          text: text,
          x: r.left - rootRect.left,
          y: r.top - rootRect.top,
          w: r.width, h: r.height,
          fontSize: cs.fontSize,
          fontWeight: cs.fontWeight,
          color: cs.color,
          align: cs.textAlign,
          lineHeight: cs.lineHeight
        });
      });
      return {
        canvasW: Math.round(rootRect.width),
        canvasH: Math.round(rootRect.height),
        items: results
      };
    })()
  `;
}

// In-page script: hide the SAME leaf text that extractLayoutScript captured,
// while keeping each element's box geometry and any styled container (pill,
// bar, card) intact — so the -bg.png becomes a TEXT-FREE background onto which
// build_hybrid_pptx.py overlays native editable text. This automates the manual
// text-strip Phase 1 did by hand in the browser (the proven build only ever
// CONSUMED pre-stripped -bg.png; it never produced them).
//
// Selection mirrors extractLayoutScript exactly: TEXT_TAGS, leaf text nodes,
// and [data-export-skip] elements are LEFT baked (use that attribute for
// gradient / background-clip:text / SVG-glyph text PowerPoint cannot reproduce
// — color:transparent does not hide those, which is why they must stay in PNG).
function stripTextScript(selector) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  return `
    (function() {
      var root = ${root};
      if (!root) return 0;
      var TEXT_TAGS = new Set(['p','h1','h2','h3','h4','h5','h6','span','li','td','th','label','strong','em','div','a','b','i']);
      function hasSkipAncestor(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType === 1 && n.hasAttribute && n.hasAttribute('data-export-skip')) return true;
        }
        return false;
      }
      if (!document.getElementById('__export_strip_style__')) {
        var st = document.createElement('style');
        st.id = '__export_strip_style__';
        st.textContent = '.__export_strip_target__{color:transparent !important;text-shadow:none !important;-webkit-text-fill-color:transparent !important;caret-color:transparent !important;}';
        document.head.appendChild(st);
      }
      var n = 0;
      root.querySelectorAll('*').forEach(function(el) {
        if (!TEXT_TAGS.has(el.tagName.toLowerCase())) return;
        if (hasSkipAncestor(el)) return;
        var hasText = false;
        for (var i = 0; i < el.childNodes.length; i++) {
          if (el.childNodes[i].nodeType === 3 && el.childNodes[i].textContent.trim()) { hasText = true; break; }
        }
        if (!hasText) return;
        el.classList.add('__export_strip_target__');
        n++;
      });
      return n;
    })()
  `;
}

// Undo stripTextScript so the next slide's extraction sees real colors again.
function restoreTextScript() {
  return `
    (function() {
      var st = document.getElementById('__export_strip_style__');
      if (st) st.remove();
      document.querySelectorAll('.__export_strip_target__').forEach(function(el) {
        el.classList.remove('__export_strip_target__');
      });
      return true;
    })()
  `;
}

async function main() {
  const a = parseArgs(process.argv);
  if (!a.url)    die("--url is required");
  if (!a.slides) die("--slides must be a positive integer");
  if (!a.outDir) die("--out-dir is required");

  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch { die("playwright not found. Run: npm install && npx playwright install chromium"); }

  fs.mkdirSync(path.resolve(a.outDir), { recursive: true });

  console.log(`[capture-slides] ${a.slides} slides → ${a.outDir}`);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: a.width, height: a.height },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.goto(a.url, { waitUntil: "networkidle" });

  // Detect deck-stage. If present, set `noscale` so DOM capture sees authored
  // 1:1 geometry (deck-stage.js: _fit() drops transform:scale + rail offset
  // when noscale is set — this is exactly what the proven PPTX exporter does).
  const hasDeckStage = await page.evaluate(
    `!!document.querySelector('deck-stage')`
  );
  if (hasDeckStage) {
    console.log(`[capture-slides] deck-stage detected → setting noscale + hiding chrome for 1:1 capture`);
    await page.evaluate(
      `document.querySelector('deck-stage').setAttribute('noscale','')`
    );
    // noscale hides the rail but NOT the bottom overlay (page counter), which
    // Playwright's element.screenshot still captures as pixels in the box. All
    // deck-stage chrome (overlay, rail, menu, resize, confirm) carries the
    // `export-hidden` class, so one style rule injected into the OPEN shadow
    // root removes every chrome element from the background render — the
    // codified version of the manual chrome-hide Phase 1 did before capture.
    await page.evaluate(`(function(){
      var ds = document.querySelector('deck-stage');
      if (!ds || !ds.shadowRoot) return false;
      if (ds.shadowRoot.getElementById('__export_chrome_hide__')) return true;
      var st = document.createElement('style');
      st.id = '__export_chrome_hide__';
      st.textContent = '.export-hidden{display:none !important;}';
      ds.shadowRoot.appendChild(st);
      return true;
    })()`);
    await page.waitForTimeout(200);
  }

  // Resolve navigation + selector defaults for deck-stage when not overridden.
  const showJs = a.showJs || (hasDeckStage
    ? "document.querySelector('deck-stage').goTo({n})" : null);
  const selector = a.selector || (hasDeckStage
    ? "deck-stage > [data-deck-active]" : null);

  const layout = [];

  for (let i = 0; i < a.slides; i++) {
    if (showJs) {
      const expr = showJs.replace("{n}", String(i));
      await page.evaluate(expr).catch(() => {});
      await page.waitForTimeout(a.delay);
    }

    // 1. Extract text layout FIRST, while the DOM still has its real text and
    //    colors (the strip below would zero out `color`).
    const result = await page.evaluate(extractLayoutScript(selector));
    layout.push({
      slide: i + 1,
      canvasW: result.canvasW,
      canvasH: result.canvasH,
      items: result.items,
    });

    // 2. Strip the captured text so the background PNG holds no glyphs (boxes
    //    stay). Skipped with --keep-bg-text (e.g. decks meant to ship as
    //    full-image backgrounds).
    let stripped = 0;
    if (!a.keepBgText) {
      stripped = await page.evaluate(stripTextScript(selector));
    }

    // 3. Capture the now text-free background PNG.
    const pngPath = path.resolve(a.outDir, `slide-${String(i + 1).padStart(2, "0")}-bg.png`);
    if (selector) {
      const el = await page.$(selector);
      if (!el) die(`Selector "${selector}" not found on slide ${i + 1}`);
      await el.screenshot({ path: pngPath, type: "png" });
    } else {
      await page.screenshot({ path: pngPath, type: "png", fullPage: false });
    }

    // 4. Restore so the next slide's extraction sees real colors again.
    if (!a.keepBgText) {
      await page.evaluate(restoreTextScript());
    }

    const stripNote = a.keepBgText ? "text kept" : `${stripped} stripped`;
    process.stdout.write(`  [capture-slides] Captured slide ${i + 1}/${a.slides} (${result.items.length} text items, ${stripNote}, canvas ${result.canvasW}x${result.canvasH})  \r`);
  }
  console.log();

  await browser.close();

  const layoutPath = path.resolve(a.outDir, "export-layout.json");
  fs.writeFileSync(layoutPath, JSON.stringify(layout, null, 2));
  console.log(`[capture-slides] Done`);
  console.log(`  renders  → ${a.outDir}/slide-XX-bg.png`);
  console.log(`  layout   → ${layoutPath}`);
  console.log(`\nNext: python3 slide-system/scripts/build_hybrid_pptx.py \\`);
  console.log(`        --layout ${layoutPath} \\`);
  console.log(`        --renders ${path.resolve(a.outDir)} \\`);
  console.log(`        --slides ${a.slides} \\`);
  console.log(`        --output <your-deck.pptx>`);
}

main().catch((err) => { console.error("[capture-slides] Fatal:", err.message || err); process.exit(1); });
