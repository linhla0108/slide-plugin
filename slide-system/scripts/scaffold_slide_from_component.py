#!/usr/bin/env python3
"""T2 — generate a slide scaffold from a component's published slot contract.

preview.html normally is the real design source: a 1920x1080 stage with one `.bg` layer
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

Some older published previews are raster-only even though their companion
``text-slots.json`` contains the canonical editable geometry. For those items,
the scaffold is reconstructed from that contract rather than pretending the
component has no editable copy surface.
"""

from __future__ import annotations

import argparse
import html
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


def _text_slots_path(item_id: str, registry_path: str) -> Path | None:
    reg = load_json(registry_path)
    for entry in reg.get("items", []):
        if entry.get("id") == item_id:
            slots = (entry.get("paths") or {}).get("text_slots")
            return Path(slots) if slots else None
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


def _slots_from_contract(contract: dict) -> list[str]:
    """Rebuild positioned editable slots from normalized published metadata."""
    source = contract.get("source") or {}
    view_box = source.get("view_box") or []
    try:
        source_height = float(view_box[3])
    except (IndexError, TypeError, ValueError):
        source_height = 1080.0
    if source_height <= 0:
        source_height = 1080.0

    tags = {"h1", "h2", "h3", "h4", "p", "span", "li", "div"}
    slots: list[str] = []
    for slot in contract.get("slots") or []:
        if not isinstance(slot, dict) or slot.get("editable") is False or not slot.get("id"):
            continue
        bounds = slot.get("bounds") or {}
        try:
            x, y = float(bounds.get("x", 0)), float(bounds.get("y", 0))
            width, height = float(bounds.get("width", 0)), float(bounds.get("height", 0))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        typography = slot.get("typography") or {}
        try:
            font_size = float(typography.get("font_size") or 0) * 1080.0 / source_height
        except (TypeError, ValueError):
            font_size = 18.0
        tag = str(slot.get("html_tag") or "p").lower()
        tag = tag if tag in tags else "p"
        align = {"start": "left", "end": "right"}.get(
            str(slot.get("horizontal_align") or "left").lower(),
            str(slot.get("horizontal_align") or "left").lower(),
        )
        vertical = {"middle": "center", "center": "center", "bottom": "flex-end"}.get(
            str(slot.get("vertical_align") or "top").lower(), "flex-start"
        )
        slot_id = html.escape(str(slot["id"]), quote=True)
        family = html.escape(str(typography.get("font_family") or "Proxima Nova"), quote=True)
        color = html.escape(str(typography.get("color") or "#171717"), quote=True)
        weight = html.escape(str(typography.get("font_weight") or "400"), quote=True)
        style = html.escape(str(typography.get("font_style") or "normal"), quote=True)
        line_height = html.escape(str(typography.get("line_height") or "1.1"), quote=True)
        slots.append(
            f'<div class="slot" data-slot-id="{slot_id}" '
            f'style="position:absolute;left:{x * 100:.4f}%;top:{y * 100:.4f}%;'
            f'width:{width * 100:.4f}%;height:{height * 100:.4f}%;display:flex;'
            f'justify-content:flex-start;align-items:{vertical};box-sizing:border-box;'
            f'overflow:visible;margin:0;padding:0">'
            f'<{tag} style="margin:0;padding:0;display:block;white-space:pre-wrap;'
            f"font-family:{family}, 'Proxima Nova', sans-serif;font-size:{font_size:.4f}px;"
            f'font-weight:{weight};font-style:{style};line-height:{line_height};color:{color};'
            f'text-align:{align}"></{tag}></div>'
        )
    return slots


def build_scaffold(item_id: str, slots: list[str]) -> str:
    body = "\n    ".join(_blank_text(s) for s in slots)
    return f"""<!-- scaffold generated from {item_id} published slot contract — fill text into slots only.
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
    source = "preview.html"
    if not slots:
        slots_path = _text_slots_path(args.item_id, args.registry)
        if slots_path and slots_path.exists():
            try:
                slots = _slots_from_contract(load_json(slots_path))
            except (OSError, ValueError):
                slots = []
            if slots:
                source = "text-slots.json"
        if not slots:
            print(f"WARN: no editable slots in {preview.name} or its published contract — "
                  "emitting .bg-only scaffold.", file=sys.stderr)

    fragment = build_scaffold(args.item_id, slots)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(fragment, encoding="utf-8")
        print(f"scaffold: {len(slots)} slot(s) from {source} for {args.item_id} -> {args.out}")
    else:
        print(fragment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
