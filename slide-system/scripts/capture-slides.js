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
               keepBgText: false,
               // v2 (3-layer plan). "flat" = the frozen v1 behaviour below;
               // "layered" = multi-pass base/overlay/text capture + manifest.
               mode: "flat", overlayScale: 2, pad: 96, requireFont: null };
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
    else if (k === "--mode")     { a.mode = v; i++; }
    else if (k === "--overlay-scale") { a.overlayScale = parseFloat(v); i++; }
    else if (k === "--pad")      { a.pad = parseInt(v, 10); i++; }
    else if (k === "--require-font") { a.requireFont = v; i++; }
  }
  if (a.mode !== "flat" && a.mode !== "layered") {
    die(`--mode must be "flat" or "layered", got "${a.mode}"`);
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

// =========================================================================
// LAYERED MODE (v2 — EXPORT-PPTX-3LAYER-PLAN.md §3.1)
// Everything below is layered-only. The flat loop in main() is the frozen v1
// code path and must not change (isolation rule #1).
// =========================================================================

const ANTI_ANIMATION = `
  (function() {
    if (document.getElementById('__export_no_anim__')) return true;
    var st = document.createElement('style');
    st.id = '__export_no_anim__';
    st.textContent = '*{animation:none !important;transition:none !important;caret-color:transparent !important;}';
    document.head.appendChild(st);
    return true;
  })()`;

// Kill every painted background behind the target so omitBackground yields
// true alpha (proven by the P1 step-0 prototype gate).
function transparentCanvasScript(selector) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  return `
    (function() {
      var els = [document.documentElement, document.body];
      var root = ${root};
      for (var n = root; n && n.nodeType === 1; n = n.parentElement) els.push(n);
      els.forEach(function(el) {
        el.style.setProperty('background', 'none', 'important');
        el.style.setProperty('background-color', 'transparent', 'important');
      });
      return true;
    })()`;
}

// Isolation by visibility-flip: visibility:hidden on the root unpaints
// EVERYTHING inside it (backgrounds included, wherever they live — the bug a
// background-killing approach hits when the canvas lives on a child of the
// capture root), then visibility:visible re-paints exactly the target subtree.
// No reflow (visibility, not display).
function isolateOverlayScript(selector, key) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  return `
    (function() {
      var root = ${root};
      root.style.setProperty('visibility', 'hidden', 'important');
      var n = 0;
      root.querySelectorAll('[data-export-layer="overlay"],[data-export-group],[data-export-native]').forEach(function(el) {
        var k = el.getAttribute('data-export-group') || el.getAttribute('data-export-id');
        if (k !== ${JSON.stringify(key)}) return;
        el.style.setProperty('visibility', 'visible', 'important');
        n++;
      });
      return n;
    })()`;
}

function isolateTextScript(selector) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  return `
    (function() {
      var root = ${root};
      var TEXT_TAGS = new Set(['p','h1','h2','h3','h4','h5','h6','span','li','td','th','label','strong','em','div','a','b','i']);
      function inOverlay(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType === 1 && (n.getAttribute('data-export-layer') === 'overlay' || n.hasAttribute('data-export-group'))) return true;
        }
        return false;
      }
      root.style.setProperty('visibility', 'hidden', 'important');
      var n = 0;
      root.querySelectorAll('*').forEach(function(el) {
        if (!TEXT_TAGS.has(el.tagName.toLowerCase())) return;
        if (inOverlay(el)) return;  // text inside an overlay bakes into that overlay (C7b)
        var hasText = false;
        for (var i = 0; i < el.childNodes.length; i++) {
          if (el.childNodes[i].nodeType === 3 && el.childNodes[i].textContent.trim()) { hasText = true; break; }
        }
        if (!hasText) return;
        el.style.setProperty('visibility', 'visible', 'important');
        n++;
      });
      return n;
    })()`;
}

function hideOverlaysScript(selector, exceptKey) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  return `
    (function() {
      var root = ${root};
      var except = ${JSON.stringify(exceptKey || null)};
      var n = 0;
      root.querySelectorAll('[data-export-layer="overlay"],[data-export-group],[data-export-native]').forEach(function(el) {
        var key = el.getAttribute('data-export-group') || el.getAttribute('data-export-id');
        if (except !== null && key === except) return;
        el.style.setProperty('visibility', 'hidden', 'important');
        n++;
      });
      return n;
    })()`;
}

// ONE evaluate per slide: text layout + object inventory from the same DOM
// state, both carrying a shared document-order z so build can interleave (C8).
function extractLayeredScript(selector) {
  const root = selector
    ? `document.querySelector(${JSON.stringify(selector)})`
    : `document.body`;
  return `
    (function() {
      var root = ${root};
      if (!root) return { canvasW: 0, canvasH: 0, text: [], objects: [] };
      var rootRect = root.getBoundingClientRect();
      var order = new Map();
      var idx = 0;
      root.querySelectorAll('*').forEach(function(el) { order.set(el, idx++); });

      var TEXT_TAGS = new Set(['p','h1','h2','h3','h4','h5','h6','span','li','td','th','label','strong','em','div','a','b','i']);
      function hasSkipAncestor(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType === 1 && n.hasAttribute && n.hasAttribute('data-export-skip')) return true;
        }
        return false;
      }
      function inOverlay(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType === 1 && (n.getAttribute('data-export-layer') === 'overlay' || n.hasAttribute('data-export-group'))) return n;
        }
        return null;
      }
      // Placement contract: every text item on a slide is a native component
      // slot, declared slide chrome, or free external text. Only a native slot
      // is allowed to sit on its component's own artwork — the component drew
      // that box for that copy. Anything undeclared is treated as external,
      // which is the checked (conservative) class, so forgetting the attribute
      // can never buy a text item an exemption.
      function placementOf(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType !== 1) continue;
          if (n.hasAttribute('data-slot-id')) {
            return { placement: 'slot', slotId: n.getAttribute('data-slot-id') };
          }
          var declared = n.getAttribute('data-placement');
          if (declared) return { placement: declared, slotId: null };
        }
        return { placement: 'external', slotId: null };
      }

      // Inline rich text must export as one native PowerPoint textbox. Exporting
      // a parent paragraph and its <b>/<span> children as independent boxes puts
      // both at the parent's origin and makes the runs visibly collide.
      function hasInlineTextChild(el) {
        for (var i = 0; i < el.childNodes.length; i++) {
          var node = el.childNodes[i];
          if (node.nodeType !== 1 || node.tagName === 'BR') continue;
          var childStyle = window.getComputedStyle(node);
          if ((childStyle.display === 'inline' || childStyle.display === 'inline-block') &&
              node.textContent && node.textContent.trim()) return true;
        }
        return false;
      }

      function isInlineRunOfCapturedAncestor(el) {
        for (var parent = el.parentElement; parent && parent !== root.parentElement; parent = parent.parentElement) {
          if (hasInlineTextChild(parent)) return true;
        }
        return false;
      }

      function inlineRuns(el, fallbackStyle) {
        var runs = [];
        for (var i = 0; i < el.childNodes.length; i++) {
          var node = el.childNodes[i];
          var style = fallbackStyle;
          var value = '';
          if (node.nodeType === 3) value = node.textContent;
          else if (node.nodeType === 1 && node.tagName === 'BR') value = '\\n';
          else if (node.nodeType === 1) {
            value = node.textContent;
            style = window.getComputedStyle(node);
          }
          if (!value) continue;
          runs.push({ text: value, fontWeight: style.fontWeight, color: style.color,
            fontFamily: style.fontFamily, fontSize: style.fontSize,
            letterSpacing: style.letterSpacing });
        }
        return runs;
      }

      var text = [];
      root.querySelectorAll('*').forEach(function(el) {
        if (!TEXT_TAGS.has(el.tagName.toLowerCase())) return;
        if (hasSkipAncestor(el)) return;
        if (isInlineRunOfCapturedAncestor(el)) return;
        var t = '';
        var sawText = false;
        var aggregateInlineRuns = hasInlineTextChild(el);
        for (var i = 0; i < el.childNodes.length; i++) {
          var node = el.childNodes[i];
          if (node.nodeType === 3) { t += node.textContent; sawText = sawText || !!node.textContent.trim(); }
          else if (node.nodeType === 1 && node.tagName === 'BR') t += '\\n';  // keep explicit line breaks
          else if (aggregateInlineRuns && node.nodeType === 1) {
            t += node.textContent;
            sawText = sawText || !!node.textContent.trim();
          }
        }
        t = t.replace(/[ \\t]*\\n[ \\t]*/g, '\\n').trim();
        if (!sawText || !t) return;
        var r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return;
        var cs = window.getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) return;
        var fontPx = parseFloat(cs.fontSize) || 16;
        var lh = parseFloat(cs.lineHeight);
        if (!lh || isNaN(lh)) lh = fontPx * 1.2;
        var ovl = inOverlay(el);
        var place = placementOf(el);
        text.push({
          tag: el.tagName.toLowerCase(),
          text: t,
          placement: place.placement,
          slotId: place.slotId,
          x: r.left - rootRect.left, y: r.top - rootRect.top,
          w: r.width, h: r.height,
          z: order.get(el) || 0,
          fontSize: cs.fontSize, fontWeight: cs.fontWeight,
          color: cs.color, align: cs.textAlign,
          lineHeight: cs.lineHeight,
          textTransform: cs.textTransform,
          letterSpacing: cs.letterSpacing,
          fontFamily: cs.fontFamily,
          runs: aggregateInlineRuns ? inlineRuns(el, cs) : null,
          lineCount: Math.max(1, Math.round(r.height / lh)),
          inOverlay: ovl ? (ovl.getAttribute('data-export-group') || ovl.getAttribute('data-export-id')) : null
        });
      });

      // Overlays: single elements (data-export-id) or groups (data-export-group)
      // → one entry per key with the union bbox of its members. css_effects
      // flags filter/shadow/blend: the source SVG no longer matches the
      // rendered look, so svgBlip embedding must be skipped (plan round 5).
      function effectsOf(el) {
        var cs = window.getComputedStyle(el);
        return (cs.filter && cs.filter !== 'none')
            || (cs.boxShadow && cs.boxShadow !== 'none')
            || (cs.mixBlendMode && cs.mixBlendMode !== 'normal');
      }
      var groups = {};
      root.querySelectorAll('[data-export-layer="overlay"],[data-export-group]').forEach(function(el) {
        var key = el.getAttribute('data-export-group') || el.getAttribute('data-export-id');
        if (!key) return;
        var r = el.getBoundingClientRect();
        var g = groups[key] || (groups[key] = {
          id: key, left: r.left, top: r.top, right: r.right, bottom: r.bottom,
          z: order.get(el) || 0,
          vectorSource: el.getAttribute('data-export-vector-source') || null,
          cssEffects: false
        });
        g.left = Math.min(g.left, r.left); g.top = Math.min(g.top, r.top);
        g.right = Math.max(g.right, r.right); g.bottom = Math.max(g.bottom, r.bottom);
        g.z = Math.min(g.z, order.get(el) || 0);
        g.cssEffects = g.cssEffects || effectsOf(el);
      });
      var objects = Object.values(groups).map(function(g) {
        return { id: g.id, z: g.z, vectorSource: g.vectorSource, cssEffects: g.cssEffects,
                 x: g.left - rootRect.left, y: g.top - rootRect.top,
                 w: g.right - g.left, h: g.bottom - g.top,
                 absX: g.left, absY: g.top };
      });

      // Native shape candidates (P2): simple solid geometry → real PPTX
      // autoshapes. Gradient fill or css effects can NOT be a native shape —
      // those are DEMOTED to raster overlay with a warning.
      var natives = [];
      root.querySelectorAll('[data-export-native]').forEach(function(el) {
        var id = el.getAttribute('data-export-id');
        if (!id) return;
        var r = el.getBoundingClientRect();
        var cs = window.getComputedStyle(el);
        natives.push({
          id: id, shape: el.getAttribute('data-export-native'),
          z: order.get(el) || 0,
          x: r.left - rootRect.left, y: r.top - rootRect.top,
          w: r.width, h: r.height, absX: r.left, absY: r.top,
          fill: cs.backgroundColor,
          radius: parseFloat(cs.borderTopLeftRadius) || 0,
          borderColor: cs.borderTopColor,
          borderWidth: parseFloat(cs.borderTopWidth) || 0,
          demote: effectsOf(el) || (cs.backgroundImage && cs.backgroundImage !== 'none'),
          opacity: parseFloat(cs.opacity)
        });
      });

      // Untagged visual candidates — the tagging-contract gate (plan §1):
      // svg/img/canvas/video outside any data-export-* subtree will be baked
      // into the base PNG. That is safe but almost never what a layered
      // export wants, so they are reported and the validator fails on them
      // unless explicitly allowed.
      function inTagged(el) {
        for (var n = el; n && n !== root.parentNode; n = n.parentElement) {
          if (n.nodeType === 1 && (n.getAttribute('data-export-layer')
              || n.hasAttribute('data-export-group')
              || n.hasAttribute('data-export-native')
              || n.hasAttribute('data-export-skip'))) return true;
        }
        return false;
      }
      var untagged = [];
      root.querySelectorAll('svg,img,canvas,video').forEach(function(el) {
        if (untagged.length >= 30) return;
        if (el.parentElement && el.parentElement.closest('svg')) return; // nested svg internals
        if (inTagged(el)) return;
        var r = el.getBoundingClientRect();
        if (r.width < 24 || r.height < 24) return;
        var cls = typeof el.className === 'string' ? el.className
                : (el.className && el.className.baseVal) || '';
        untagged.push({ tag: el.tagName.toLowerCase(), cls: cls,
                        x: Math.round(r.left - rootRect.left), y: Math.round(r.top - rootRect.top),
                        w: Math.round(r.width), h: Math.round(r.height) });
      });

      return { canvasW: Math.round(rootRect.width), canvasH: Math.round(rootRect.height),
               rootX: rootRect.left, rootY: rootRect.top,
               text: text, objects: objects, natives: natives, untagged: untagged };
    })()`;
}

async function runLayered(a, browser, page, hasDeckStage, showJs, selector) {
  const crypto = require("crypto");
  const sha256 = (p) => crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
  const out = (name) => path.resolve(a.outDir, name);
  const nn = (i) => String(i + 1).padStart(2, "0");

  // Dedicated 2x context for overlay passes (scale is just deviceScaleFactor —
  // clip stays in CSS px). Plan §5: 2x so user scaling to ~200% stays sharp.
  const ctx2x = await browser.newContext({
    viewport: { width: a.width, height: a.height },
    deviceScaleFactor: a.overlayScale,
  });
  const page2x = await ctx2x.newPage();

  // Every pass starts from a clean page state: goto IS the restore.
  const prepare = async (pg, slideIdx) => {
    await pg.goto(a.url, { waitUntil: "networkidle" });
    await pg.evaluate("document.fonts.ready.then(() => true)");
    if (hasDeckStage) {
      await pg.evaluate(`document.querySelector('deck-stage').setAttribute('noscale','')`);
      await pg.evaluate(`(function(){
        var ds = document.querySelector('deck-stage');
        if (!ds || !ds.shadowRoot) return false;
        if (ds.shadowRoot.getElementById('__export_chrome_hide__')) return true;
        var st = document.createElement('style');
        st.id = '__export_chrome_hide__';
        st.textContent = '.export-hidden{display:none !important;}';
        ds.shadowRoot.appendChild(st);
        return true;
      })()`);
    }
    await pg.evaluate(ANTI_ANIMATION);
    if (showJs) {
      await pg.evaluate(showJs.replace("{n}", String(slideIdx))).catch(() => {});
    }
    await pg.waitForTimeout(a.delay);
    if (a.requireFont) {
      const okFont = await pg.evaluate(
        `document.fonts.check('16px ' + ${JSON.stringify(JSON.stringify(a.requireFont))})`);
      if (!okFont) die(`required font not loaded: ${a.requireFont} (capture operational error)`);
    }
  };

  const shoot = async (pg, name, opts = {}) => {
    if (selector) {
      const el = await pg.$(selector);
      if (!el) die(`Selector "${selector}" not found`);
      await el.screenshot({ path: out(name), type: "png", ...opts });
    } else {
      await pg.screenshot({ path: out(name), type: "png", fullPage: false, ...opts });
    }
  };

  const manifest = { manifest_version: 2, mode: "layered",
                     canvasW: a.width, canvasH: a.height, slides: [] };

  for (let i = 0; i < a.slides; i++) {
    // Inventory + text layout: ONE evaluate on a fresh page.
    await prepare(page, i);
    const inv = await page.evaluate(extractLayeredScript(selector));

    // Pass REF-FULL (before any strip — real text colors). QA-ephemeral.
    await shoot(page, `slide-${nn(i)}-ref-full.png`);

    // Pass REF-NOTEXT — the v1-style render, tier-1 reference. QA-ephemeral.
    await prepare(page, i);
    await page.evaluate(stripTextScript(selector));
    await shoot(page, `slide-${nn(i)}-ref-notext.png`);

    // Pass BASE — passive canvas only.
    await prepare(page, i);
    await page.evaluate(stripTextScript(selector));
    await page.evaluate(hideOverlaysScript(selector, null));
    await shoot(page, `slide-${nn(i)}-bg.png`);

    // Native shapes with effects/gradient cannot be real autoshapes — demote
    // them to raster overlays (warning) so nothing is silently lost.
    const demoted = (inv.natives || []).filter((n) => n.demote);
    for (const dn of demoted) {
      console.warn(`  [capture-slides] WARN slide ${i + 1}: native '${dn.id}' has `
        + `effects/gradient → demoted to raster overlay`);
      inv.objects.push({ id: dn.id, z: dn.z, vectorSource: null, cssEffects: true,
                         x: dn.x, y: dn.y, w: dn.w, h: dn.h,
                         absX: dn.absX, absY: dn.absY });
    }
    const keptNatives = (inv.natives || []).filter((n) => !n.demote);

    // Pass OVERLAY — one per id/group, on the 2x page: visibility-flip leaves
    // ONLY the target subtree painted; transparent canvas kills html/body +
    // ancestor backgrounds OUTSIDE the root.
    const objects = [];
    for (const ov of inv.objects) {
      await prepare(page2x, i);
      await page2x.evaluate(isolateOverlayScript(selector, ov.id));
      await page2x.evaluate(transparentCanvasScript(selector));
      // A clean vector_source must use its exact visual bounds. Padding the
      // PNG capture but attaching an unpadded SVG to that larger PPTX shape
      // stretches the vector in Office/LibreOffice. Raster/effect overlays
      // still need padding so shadows, blur, and glow are not clipped.
      const overlayPad = ov.vectorSource && !ov.cssEffects ? 0 : a.pad;
      const clipX = Math.max(0, Math.floor(ov.absX - overlayPad));
      const clipY = Math.max(0, Math.floor(ov.absY - overlayPad));
      const clip = {
        x: clipX, y: clipY,
        width: Math.min(
          a.width - clipX,
          Math.ceil(ov.w + (ov.absX - clipX) + overlayPad),
        ),
        height: Math.min(
          a.height - clipY,
          Math.ceil(ov.h + (ov.absY - clipY) + overlayPad),
        ),
      };
      const png = `slide-${nn(i)}-ov-${ov.id}.png`;
      await page2x.screenshot({ path: out(png), type: "png", omitBackground: true, clip });
      if (ov.vectorSource && ov.cssEffects) {
        console.warn(`  [capture-slides] WARN slide ${i + 1}: overlay '${ov.id}' has `
          + `vector_source but CSS effects alter its rendered look — svgBlip must be skipped`);
      }
      objects.push({
        id: ov.id, role: "complex-overlay", png,
        bounds: { x: clip.x - (inv.rootX || 0), y: clip.y - (inv.rootY || 0),
                  w: clip.width, h: clip.height,
                  unit: `px@${a.width}x${a.height}` },
        visual_bounds: { x: ov.x, y: ov.y, w: ov.w, h: ov.h },
        z: ov.z, transparent: true, rotation: 0,
        scale_factor: a.overlayScale,
        vector_source: ov.vectorSource,
        css_effects: !!ov.cssEffects,
        sha256: sha256(out(png)),
      });
    }

    // Pass NATIVE-QA — natives become real PPTX autoshapes (not pictures), but
    // the compose-check still needs their pixels: capture a 1x QA-ephemeral
    // PNG per native, same visibility-flip isolation.
    const natives = [];
    for (const nv of keptNatives) {
      await prepare(page, i);
      await page.evaluate(isolateOverlayScript(selector, nv.id));
      await page.evaluate(transparentCanvasScript(selector));
      const clip = {
        x: Math.max(0, Math.floor(nv.absX)), y: Math.max(0, Math.floor(nv.absY)),
        width: Math.ceil(nv.w), height: Math.ceil(nv.h),
      };
      const png = `slide-${nn(i)}-native-${nv.id}.png`;
      await page.screenshot({ path: out(png), type: "png", omitBackground: true, clip });
      natives.push({
        id: nv.id, role: "native-shape", shape: nv.shape,
        bounds: { x: nv.x, y: nv.y, w: nv.w, h: nv.h,
                  unit: `px@${a.width}x${a.height}` },
        z: nv.z,
        fill: nv.fill, radius: nv.radius,
        border_color: nv.borderColor, border_width: nv.borderWidth,
        opacity: nv.opacity,
        qa_png: png,
      });
    }

    // Pass TEXT-LAYER — text only, transparent canvas. QA-ephemeral.
    // visibility-flip hides the root element itself, so element.screenshot
    // would wait forever — clip a page screenshot to the root rect instead.
    await prepare(page, i);
    await page.evaluate(isolateTextScript(selector));
    await page.evaluate(transparentCanvasScript(selector));
    await page.screenshot({
      path: out(`slide-${nn(i)}-text.png`), type: "png", omitBackground: true,
      clip: { x: Math.max(0, Math.round(inv.rootX || 0)),
              y: Math.max(0, Math.round(inv.rootY || 0)),
              width: Math.min(a.width, inv.canvasW || a.width),
              height: Math.min(a.height, inv.canvasH || a.height) },
    });

    manifest.slides.push({
      slide: i + 1,
      canvasW: inv.canvasW, canvasH: inv.canvasH,
      base: { png: `slide-${nn(i)}-bg.png`, sha256: sha256(out(`slide-${nn(i)}-bg.png`)) },
      qa: { ref_full: `slide-${nn(i)}-ref-full.png`,
            ref_notext: `slide-${nn(i)}-ref-notext.png`,
            text_layer: `slide-${nn(i)}-text.png` },
      objects,
      natives,
      untagged_visuals: inv.untagged || [],
      text: inv.text.filter((t) => !t.inOverlay || t.inOverlay === null),
    });
    for (const u of inv.untagged || []) {
      console.warn(`  [capture-slides] WARN slide ${i + 1}: untagged visual `
        + `<${u.tag}${u.cls ? ` class="${u.cls}"` : ""}> ${u.w}x${u.h}@${u.x},${u.y} `
        + `— will be BAKED into the background (tag it data-export-layer/native)`);
    }
    console.log(`  [capture-slides] layered slide ${i + 1}/${a.slides}: `
      + `${objects.length} overlays, ${natives.length} natives, ${inv.text.length} text items`
      + ((inv.untagged || []).length ? `, ${inv.untagged.length} UNTAGGED visuals` : ""));
  }

  await ctx2x.close();
  // Isolation rule #3: layered NEVER emits export-layout.json (a v1 build fed
  // that shim plus a base-only bg.png would silently drop every overlay).
  const manifestPath = out("export-manifest.json");
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log(`[capture-slides] layered done → ${manifestPath}`);
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

  // v2: layered mode takes its own multi-pass path. The loop below stays the
  // frozen v1 (flat) behaviour — isolation rule #1 of the 3-layer plan.
  if (a.mode === "layered") {
    await runLayered(a, browser, page, hasDeckStage, showJs, selector);
    await browser.close();
    return;
  }

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

  // Flat mode ALSO writes the v2 manifest as an ADDITIVE artifact (isolation
  // rule: its existence does not count as "v1 output changed"; bg.png and
  // export-layout.json above are byte-for-byte the frozen v1 outputs).
  {
    const crypto = require("crypto");
    const sha256 = (p) => crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
    const manifest = {
      manifest_version: 2, mode: "flat",
      canvasW: a.width, canvasH: a.height,
      slides: layout.map((s) => {
        const png = `slide-${String(s.slide).padStart(2, "0")}-bg.png`;
        return { slide: s.slide, canvasW: s.canvasW, canvasH: s.canvasH,
                 base: { png, sha256: sha256(path.resolve(a.outDir, png)) },
                 objects: [], text: s.items };
      }),
    };
    fs.writeFileSync(path.resolve(a.outDir, "export-manifest.json"),
      JSON.stringify(manifest, null, 2));
  }
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
