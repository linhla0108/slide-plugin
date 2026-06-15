#!/usr/bin/env node
/**
 * measure_svg_groups.js — Measure per-object-group bounding boxes of a
 * full-page SVG in real Chromium layout.
 *
 * Why a browser: extraction SVGs (convert_pdf_source.py output) carry matrix
 * transforms on every path and full-page clipPaths, so static parsing cannot
 * recover object bounds. getBoundingClientRect resolves transforms the same
 * way the deck render will.
 *
 * Groups measured: the children of each Inkscape layer (<g
 * inkscape:groupmode="layer">), excluding <defs>. When the SVG has no layers,
 * the direct children of the root <svg> are measured instead.
 *
 * Usage:
 *   node measure_svg_groups.js --svg <visual.svg> --out <groups.json>
 *
 * Output: { width, height, groups: [{ index, x, y, w, h, tags }] }
 * (coordinates in SVG user units == CSS px at natural size).
 */
const fs = require('fs');
const path = require('path');

function arg(name) {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : undefined;
}

(async () => {
  const svgPath = arg('--svg');
  const outPath = arg('--out');
  if (!svgPath || !outPath) {
    console.error('usage: node measure_svg_groups.js --svg <visual.svg> --out <groups.json>');
    process.exit(2);
  }
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: 2200, height: 1300 },
      deviceScaleFactor: 1,
    });
    // file:// keeps relative hrefs (externalized raster assets) resolvable.
    await page.goto('file://' + path.resolve(svgPath), { waitUntil: 'load' });
    await page.evaluate(() => new Promise((done) =>
      requestAnimationFrame(() => requestAnimationFrame(done))));
    const result = await page.evaluate(() => {
      const svg = document.querySelector('svg');
      const INK = 'http://www.inkscape.org/namespaces/inkscape';
      const layers = [...svg.querySelectorAll('g')]
        .filter((g) => g.getAttributeNS(INK, 'groupmode') === 'layer');
      const parents = layers.length ? layers : [svg];
      const groups = [];
      for (const parent of parents) {
        for (const el of parent.children) {
          if (el.tagName.toLowerCase() === 'defs') continue;
          const r = el.getBoundingClientRect();
          const tags = {};
          for (const d of el.querySelectorAll('*')) {
            tags[d.tagName] = (tags[d.tagName] || 0) + 1;
          }
          if (!el.children.length) tags[el.tagName] = (tags[el.tagName] || 0) + 1;
          // Child bboxes let the decomposer split a single source group that
          // packs several disjoint objects (e.g. all timeline arrows in one <g>).
          const children = [...el.children].map((ch, ci) => {
            const cr = ch.getBoundingClientRect();
            return { index: ci, x: cr.x, y: cr.y, w: cr.width, h: cr.height };
          });
          groups.push({
            index: groups.length,
            x: r.x, y: r.y, w: r.width, h: r.height,
            tags, children,
          });
        }
      }
      const vb = svg.viewBox.baseVal;
      return {
        width: vb && vb.width ? vb.width : svg.getBoundingClientRect().width,
        height: vb && vb.height ? vb.height : svg.getBoundingClientRect().height,
        groups,
      };
    });
    fs.writeFileSync(outPath, JSON.stringify(result, null, 1));
    console.log(`measured ${result.groups.length} groups -> ${outPath}`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
