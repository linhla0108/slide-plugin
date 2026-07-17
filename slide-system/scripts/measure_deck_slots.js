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

const nextFrame = (page) => page.evaluate(() => new Promise((done) =>
  requestAnimationFrame(() => requestAnimationFrame(done))));

/**
 * Measure every instance while ITS OWN slide is visible.
 *
 * A deck follows the paginated contract (`.slide{display:none}` /
 * `.slide.active`, global `goToSlide(n)`), so measuring the page as loaded only
 * ever sees slide 0. Every later instance then measured bg 0x0 / loaded:false
 * and slot rects 0x0 — reported as "artwork did not load/render" for artwork
 * that is fine, and, worse, silently VACUOUS readability checks (`overflowX` is
 * `scrollW > clientW` = `0 > 0` = false; a 0-width text rect skips the overlap
 * and visibility tests). So this drives the deck's own navigator, exactly like
 * capture-slides.js, and fails closed when it cannot.
 */
async function measureNavigated(page, measureInstances) {
  const plan = await page.evaluate(() => {
    const slides = Array.from(document.querySelectorAll('.slide'));
    const instances = Array.from(document.querySelectorAll('[data-component-instance]'))
      .map((inst) => {
        const slide = inst.closest('.slide');
        const r = inst.getBoundingClientRect();
        return {
          id: inst.getAttribute('data-component-instance'),
          slide: slide ? slides.indexOf(slide) : -1,
          visible: r.width > 0 && r.height > 0,
        };
      });
    return {
      instances,
      hasGoToSlide: typeof window.goToSlide === 'function',
    };
  });

  // Nothing hidden (single-page deck, or every slide already visible): the
  // as-loaded state is already each instance's real state.
  const hidden = plan.instances.filter((i) => !i.visible);
  if (!hidden.length) return measureInstances(null);

  // Hidden instances exist, so the deck MUST expose navigation we can drive —
  // otherwise we would emit zeros that read as a component defect.
  const unreachable = hidden.filter((i) => i.slide < 0);
  if (unreachable.length) {
    console.error('[measure_deck_slots] FATAL: instance(s) are not rendered and are not '
      + `inside a .slide, so they cannot be made visible to measure: `
      + `${unreachable.map((i) => i.id).join(', ')}`);
    process.exit(2);
  }
  if (!plan.hasGoToSlide) {
    console.error('[measure_deck_slots] FATAL: this deck hides '
      + `${hidden.length} component instance(s) on inactive slides but exposes no `
      + 'goToSlide(n) navigator, so their text fit / artwork cannot be measured. '
      + 'Give the deck the documented .slide/.slide.active + goToSlide(n) contract.');
    process.exit(2);
  }

  // One navigation per slide that actually holds instances.
  const bySlide = new Map();
  for (const i of plan.instances) {
    if (!bySlide.has(i.slide)) bySlide.set(i.slide, []);
    bySlide.get(i.slide).push(i.id);
  }
  const instances = [];
  for (const [idx, ids] of [...bySlide.entries()].sort((a, b) => a[0] - b[0])) {
    if (idx > -1) {
      await page.evaluate((n) => window.goToSlide(n), idx);
      await nextFrame(page);
    }
    const part = await measureInstances(ids);
    instances.push(...part.instances);
  }
  return { instances };
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
    // Measure the instances named by `wanted` (null = all) in the CURRENT visual
    // state of the page. The caller is responsible for making each instance's
    // slide visible first — see measureNavigated.
    const measureInstances = (wanted) => page.evaluate((ids) => {
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
        const iid = inst.getAttribute('data-component-instance');
        if (ids && ids.indexOf(iid) === -1) continue;
        const slots = [];
        // Scoped to THIS instance, so a template slot is always attributed to the
        // occurrence it renders in (never pooled across two uses of a component).
        for (const { attr, kind } of KINDS) {
          for (const box of inst.querySelectorAll(`[${attr}]`)) {
            slots.push(measureSlot(box, attr, kind));
          }
        }
        instances.push({
          instance: iid,
          component: inst.getAttribute('data-base-component'),
          bg: bgState(inst),
          slots,
        });
      }
      return { instances };
    }, wanted);

    const result = await measureNavigated(page, measureInstances);
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
