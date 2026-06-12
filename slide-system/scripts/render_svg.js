#!/usr/bin/env node
/**
 * render_svg.js — Render local SVG files to PNG via Playwright Chromium.
 *
 * One browser instance serves every job, so batch callers (e.g.
 * flatten_svg_background.py) pay the launch cost once.
 *
 * Usage:
 *   node render_svg.js --jobs <jobs.json>
 *
 * jobs.json is an array of:
 *   { "svg": "/abs/path/file.svg", "output": "/abs/path/out.png",
 *     "width": 1920, "height": 1080 }
 */
const fs = require('fs');
const path = require('path');

function arg(name) {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : undefined;
}

(async () => {
  const jobsPath = arg('--jobs');
  if (!jobsPath) {
    console.error('usage: node render_svg.js --jobs <jobs.json>');
    process.exit(2);
  }
  const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf-8'));
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  try {
    for (const job of jobs) {
      const page = await browser.newPage({
        viewport: { width: job.width, height: job.height },
        deviceScaleFactor: 1,
      });
      await page.goto('file://' + path.resolve(job.svg), { waitUntil: 'load' });
      // file:// subresources do not show up as network activity; give the
      // raster decode a couple of frames before capturing.
      await page.evaluate(
        () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
      );
      await page.waitForTimeout(150);
      const buffer = await page.screenshot({
        clip: { x: 0, y: 0, width: job.width, height: job.height },
      });
      fs.writeFileSync(job.output, buffer);
      await page.close();
      console.log(`rendered ${path.basename(job.svg)} -> ${job.output}`);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
