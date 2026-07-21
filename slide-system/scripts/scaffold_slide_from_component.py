#!/usr/bin/env python3
"""T2 — generate a slide scaffold from a component's preview.html.

preview.html is the real design source: a 1920x1080 stage with one `.bg` layer
(the inlined visual.svg) and N absolutely-positioned `.slot` divs. This script
keeps the `.slot` structure verbatim — including each `data-slot-id` and its
inline positioning — but blanks the example text and replaces the heavy inlined
`.bg` SVG with a lightweight placeholder. The agent then fills text into slots
and sets the background from `decompose_svg_objects.py` output.

Because the scaffold preserves the original `data-slot-id` set, the T3 fidelity
gate can match the deck against the component without depending on slot text
(which would differ once filled with Vietnamese copy).

Reading preview.html may pull a multi-MB file into THIS script's memory — that
is fine; scripts read heavy files, the agent never does. Output is small.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import load_json

SLOT_OPEN_RE = re.compile(r'<div\b[^>]*class="[^"]*\bslot\b[^"]*"[^>]*>', re.IGNORECASE)
DIV_TOKEN_RE = re.compile(r'<div\b|</div>', re.IGNORECASE)
TEXT_NODE_RE = re.compile(r'>\s*([^<>]+?)\s*<')


def _preview_path(item_id: str, registry_path: str) -> Path:
    reg = load_json(registry_path)
    for entry in reg.get("items", []):
        if entry.get("id") == item_id:
            preview = (entry.get("paths") or {}).get("preview")
            if not preview:
                raise SystemExit(
                    f"ERROR: item {item_id!r} has no paths.preview — pass the FULL "
                    f"registry (visual-library.json), not the compact one."
                )
            return Path(preview)
    raise SystemExit(f"ERROR: item_id {item_id!r} not found in {registry_path}")


def _extract_slots(html: str) -> list[str]:
    """Return each `.slot` element's full HTML, depth-aware on nested <div>."""
    slots: list[str] = []
    for m in SLOT_OPEN_RE.finditer(html):
        start = m.start()
        depth = 0
        pos = start
        for tok in DIV_TOKEN_RE.finditer(html, start):
            if tok.group(0).lower() == "</div>":
                depth -= 1
                if depth == 0:
                    pos = tok.end()
                    break
            else:
                depth += 1
        else:
            continue  # unbalanced; skip
        slots.append(html[start:pos])
    return slots


def _blank_text(slot_html: str) -> str:
    """Remove visible text nodes, keep all tags/attributes (incl. data-slot-id)."""
    return TEXT_NODE_RE.sub("><", slot_html)


def build_scaffold(item_id: str, slots: list[str]) -> str:
    body = "\n    ".join(_blank_text(s) for s in slots)
    return f"""<!-- scaffold generated from {item_id} preview.html — fill text into slots only.
     Do NOT move, restyle, or delete slots. Set .bg background-image from the
     decompose_svg_objects.py artwork output. -->
<style>
  .slide-scaffold {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; }}
  .slide-scaffold > .bg {{ position: absolute; inset: 0; width: 1920px; height: 1080px; }}
  .slide-scaffold .slot {{ z-index: 20; }}
  .slide-scaffold .slot > * {{ margin: 0; }}
</style>
<div class="slide-scaffold" data-base-component="{item_id}" data-content-shape="">
  <div class="bg" data-base-component="{item_id}"
       style="background-size:cover;background-position:center"><!-- set background-image: url(assets/page-NN/visual.svg) --></div>
    {body}
</div>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a slide scaffold from a component's preview.html.")
    ap.add_argument("--item-id", required=True)
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--out", default=None, help="Write fragment here (default: stdout).")
    args = ap.parse_args()

    preview = _preview_path(args.item_id, args.registry)
    if not preview.exists():
        print(f"ERROR: preview.html not found: {preview}", file=sys.stderr)
        return 1

    html = preview.read_text(encoding="utf-8", errors="replace")
    slots = _extract_slots(html)
    if not slots:
        # Raster-only components (text baked into the PNG) have no positioned
        # slots. Emit a .bg-only scaffold so the agent still gets the background
        # placeholder + data-base-component marker; T3 matches on that marker.
        print(f"WARN: no .slot elements in {preview.name} — emitting .bg-only scaffold "
              f"(raster component; fill the background via decompose only).", file=sys.stderr)

    fragment = build_scaffold(args.item_id, slots)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(fragment, encoding="utf-8")
        print(f"scaffold: {len(slots)} slot(s) from {args.item_id} -> {args.out}")
    else:
        print(fragment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
