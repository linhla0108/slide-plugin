#!/usr/bin/env python3
"""Build a batch review gallery from visual.svg and editable text slots."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-dir", required=True, type=Path)
    args = parser.parse_args()
    batch = args.extraction_dir.resolve()

    manifest_path = batch / "manifest.json"
    title = batch.name
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        title = manifest.get("extraction_id", title)

    cards = []
    for mapping_path in sorted(batch.glob("items/*/mapping.json")):
        item_dir = mapping_path.parent
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        slots_path = item_dir / "artifact" / "text-slots.json"
        visual_path = item_dir / "artifact" / "visual.svg"
        if not slots_path.exists() or not visual_path.exists():
            continue
        contract = json.loads(slots_path.read_text(encoding="utf-8"))
        slots = []
        for slot in contract["slots"]:
            bounds = slot["bounds"]
            typography = slot["typography"]
            # Source bounds are advisory only: they describe the original glyph
            # extent, NOT a hard render box. Each slot is a single source line, so
            # we expose the extent as min-width/min-height (keeps a sensible click
            # target) but never as a fixed width — combined with `white-space:pre`
            # this stops the web font from wrapping the last glyph (e.g. "BOAR D").
            style = (
                f"left:{bounds['x'] * 100:.7f}%;"
                f"top:{bounds['y'] * 100:.7f}%;"
                f"min-width:{bounds['width'] * 100:.7f}%;"
                f"min-height:{bounds['height'] * 100:.7f}%;"
                f"--source-font-size:{typography['font_size']};"
                f"font-family:{html.escape(typography['font_family'])},Arial,sans-serif;"
                f"font-weight:{html.escape(str(typography['font_weight']))};"
                f"font-style:{html.escape(typography['font_style'])};"
                f"line-height:{typography['line_height']};"
                f"letter-spacing:{html.escape(str(typography['letter_spacing']))};"
                f"color:{html.escape(typography['color'])};"
                f"text-align:{slot['horizontal_align']};"
                f"transform:rotate({slot['rotation']}deg);"
                f"z-index:{slot['z_order']};"
            )
            slots.append(
                f'<{slot["html_tag"]} class="text-slot" '
                f'data-slot-id="{html.escape(slot["id"])}" '
                f'contenteditable="true" spellcheck="false" style="{style}">'
                f'{html.escape(slot["example_value"])}</{slot["html_tag"]}>'
            )
        relative = item_dir.relative_to(batch)
        cards.append(
            f"""
<article class="item">
  <header>
    <div><span>Page {mapping['source']['slide_or_page']}</span>
      <b>{html.escape(mapping.get('name', mapping['item_id']))}</b></div>
    <code>{html.escape(mapping['candidate_stable_id'])}</code>
    <small>{len(contract['slots'])} editable text slots</small>
  </header>
  <div class="stage" data-canvas-width="{contract['source']['canvas_width']}"
    style="aspect-ratio:{contract['source']['canvas_width']}/{contract['source']['canvas_height']}">
    <object type="image/svg+xml" data="{relative}/artifact/visual.svg"></object>
    <div class="text-layer">{''.join(slots)}</div>
  </div>
</article>"""
        )

    gallery = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Editable text-slot extraction gallery</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; padding:32px; background:#f3f3f0; color:#171717;
      font-family:Inter,Arial,sans-serif; }}
    h1 {{ margin:0 0 8px; }}
    .lead {{ margin:0 0 28px; color:#666; }}
    main {{ display:grid; gap:28px; }}
    .item {{ overflow:hidden; border:1px solid #ddd; border-radius:16px; background:#fff; }}
    .item header {{ display:grid; grid-template-columns:1fr auto; gap:6px 20px;
      padding:16px 20px; border-bottom:1px solid #eee; }}
    .item header div {{ display:flex; gap:14px; }}
    .item header span {{ color:#ff5533; font-weight:700; }}
    .item header small {{ grid-column:1/-1; color:#777; }}
    .stage {{ position:relative; width:100%; overflow:hidden; background:#fff; }}
    .stage > object,.text-layer {{ position:absolute; inset:0; width:100%; height:100%; }}
    .stage > object {{ pointer-events:none; }}
    .text-layer {{ pointer-events:none; }}
    .text-slot {{ position:absolute; margin:0; padding:0; overflow:visible;
      white-space:pre; pointer-events:auto; outline:0;
      font-size:calc(var(--source-font-size) * var(--scale, .4) * 1px);
      transform-origin:top left; }}
    .text-slot:focus {{ background:rgba(255,85,51,.09); outline:1px dashed #ff5533; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="lead">Visual-only SVG + editable HTML text slots. Click any text to edit it.</p>
  <main>{''.join(cards)}</main>
  <script>
    const resize = stage => {{
      stage.style.setProperty('--scale', stage.clientWidth / Number(stage.dataset.canvasWidth));
    }};
    const observer = new ResizeObserver(entries => entries.forEach(entry => resize(entry.target)));
    document.querySelectorAll('.stage').forEach(stage => {{ resize(stage); observer.observe(stage); }});
  </script>
</body>
</html>
"""
    (batch / "gallery.html").write_text(gallery, encoding="utf-8")
    print(f"Gallery: {len(cards)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
