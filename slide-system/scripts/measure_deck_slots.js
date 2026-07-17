#!/usr/bin/env node
/**
 * measure_deck_slots.js — Render-aware measurement of a deck's component slots.
 *
 * Why a browser: the slot boxes carry contract typography (font family/size,
 * line-height) and the copy is real (often Vietnamese) text. Whether that text
 * actually fits its box, clips, or overlaps a neighbour, and whether the
 * component's background artwork actually loaded, can only be known from the
 * final laid-out DOM. This measures, PER unique component instance
 * (`data-component-instance`, not the shared component id, so two uses of the
 * same component never pool), for BOTH slot dialects — slot-contract components
 * (`data-component-slot`) and full-slide template previews (`data-slot-id`),
 * tagged by `kind` — because either can clip real copy:
 *   - each slot wrapper's size + scroll overflow;
 *   - each slot's ACTUAL rendered text ink box (via a Range over its contents),
 *     so we can detect text that spills its wrapper or overlaps another slot;
 *   - the `.bg` artifact's rendered size and load state (img.naturalWidth,
 *     inline <svg>/<object> presence, or a non-empty CSS background-image).
 * The fidelity gate uses this to fail a slide whose reused-component text does
 * not fit / overlaps / is unreadable, or whose base artwork did not render,
 * instead of silently shrinking or shipping a blank.
 *
 * Usage:  node measure_deck_slots.js --html <deck.html> --out <slots.json>
 * Output: { instances: [ { instance, component, bg:{present,w,h,loaded},
 *            slots:[ { slot, kind:"component"|"template",
 *                      wrapperX/Y/W/H, scrollW/H, clientW/H,
 *                      overflowX, overflowY, textX/Y/W/H, textOutsideWrapper,
 *                      textVisible, rendered } ] } ] }
 * Sizes are CSS px in the 1920x1080 deck canvas.
 */
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

function arg(name) {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : undefined;
}

(async () => {
  const htmlPath = arg('--html');
  const outPath = arg('--out');
  if (!htmlPath || !outPath) {
    console.error('usage: node measure_deck_slots.js --html <deck.html> --out <slots.json>');
    process.exit(2);
  }
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: 1920, height: 1080 },
      deviceScaleFactor: 1,
    });
    // file:// keeps relative asset hrefs (materialized .bg svg) resolvable.
    await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: 'load' });
    await page.evaluate(() => (document.fonts && document.fonts.ready) || Promise.resolve());
    await page.evaluate(() => new Promise((done) =>
      requestAnimationFrame(() => requestAnimationFrame(done))));
    const result = await page.evaluate(() => {
      const TOL = 1; // px slack so sub-pixel rounding is not an overflow.
      const r4 = (r) => ({ x: r.x, y: r.y, w: r.width, h: r.height });
      function textRect(el) {
        if (!el) return { x: 0, y: 0, w: 0, h: 0 };
        try {
          const rng = document.createRange();
          rng.selectNodeContents(el);
          return r4(rng.getBoundingClientRect());
        } catch (e) { return r4(el.getBoundingClientRect()); }
      }
      function visible(el) {
        if (!el) return false;
        const s = getComputedStyle(el);
        return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity || '1') > 0;
      }
      function bgState(inst) {
        const bg = inst.querySelector('.bg');
        if (!bg) return { present: false, w: 0, h: 0, loaded: false };
        const r = bg.getBoundingClientRect();
        const img = bg.querySelector('img');
        const obj = bg.querySelector('object');
        const svg = bg.querySelector('svg');
        const cs = getComputedStyle(bg);
        let loaded;
        if (img) loaded = img.complete && img.naturalWidth > 0;
        else if (svg) loaded = svg.getBoundingClientRect().width > 0;
        else if (obj) loaded = !!obj.contentDocument;
        else loaded = cs.backgroundImage && cs.backgroundImage !== 'none' && r.width > 0 && r.height > 0;
        return { present: true, w: Math.round(r.width), h: Math.round(r.height), loaded: !!loaded };
      }
      // Two slot dialects, one measurement. Slot-contract components scaffold
      // `data-component-slot`; full-slide TEMPLATE previews scaffold `data-slot-id`.
      // Both carry real copy in a positioned box, so both can clip — measuring only
      // the first meant a template's cover/closing text was never render-checked.
      const KINDS = [
        { attr: 'data-component-slot', kind: 'component' },
        { attr: 'data-slot-id', kind: 'template' },
      ];
      function measureSlot(box, attr, kind) {
        const textEl = box.querySelector('.slot-text') || box.firstElementChild || box;
        const wr = box.getBoundingClientRect();
        const tr = textRect(textEl);
        const outside = tr.w > 0 && (
          tr.x < wr.x - TOL || tr.y < wr.y - TOL ||
          tr.x + tr.w > wr.x + wr.width + TOL || tr.y + tr.h > wr.y + wr.height + TOL);
        return {
          slot: box.getAttribute(attr),
          kind,
          wrapperX: wr.x, wrapperY: wr.y,
          wrapperW: Math.round(wr.width), wrapperH: Math.round(wr.height),
          scrollW: box.scrollWidth, scrollH: box.scrollHeight,
          clientW: box.clientWidth, clientH: box.clientHeight,
          overflowX: box.scrollWidth > box.clientWidth + TOL,
          overflowY: box.scrollHeight > box.clientHeight + TOL,
          textX: tr.x, textY: tr.y, textW: Math.round(tr.w), textH: Math.round(tr.h),
          textOutsideWrapper: outside,
          textVisible: visible(textEl),
          rendered: wr.width > 0 && wr.height > 0,
        };
      }
      const instances = [];
      for (const inst of document.querySelectorAll('[data-component-instance]')) {
        const slots = [];
        // Scoped to THIS instance, so a template slot is always attributed to the
        // occurrence it renders in (never pooled across two uses of a component).
        for (const { attr, kind } of KINDS) {
          for (const box of inst.querySelectorAll(`[${attr}]`)) {
            slots.push(measureSlot(box, attr, kind));
          }
        }
        instances.push({
          instance: inst.getAttribute('data-component-instance'),
          component: inst.getAttribute('data-base-component'),
          bg: bgState(inst),
          slots,
        });
      }
      return { instances };
    });
    fs.writeFileSync(outPath, JSON.stringify(result, null, 1));
    const nslots = result.instances.reduce((a, i) => a + i.slots.length, 0);
    console.log(`measured ${result.instances.length} instance(s), ${nslots} slot(s) -> ${outPath}`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
