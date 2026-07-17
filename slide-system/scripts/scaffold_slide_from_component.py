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
import hashlib
import re
import sys
from pathlib import Path

from _common import load_json
import materialize_component_visual as materialize

_SLIDE_DIR_RE = re.compile(r"(?i)^(?:page|slide|s)[-_]?\d+$")


def _instance_suffix(out_path: "Path | None", explicit: "str | None") -> str:
    """A deterministic, unique-per-occurrence suffix. Explicit wins; otherwise a
    human-readable slide-dir name (page-07 / slide-3) when the output path has one,
    else a short stable hash of the resolved output path; stdout is a single '1'."""
    if explicit:
        return re.sub(r"[^A-Za-z0-9_.-]", "-", explicit)
    if out_path is None:
        return "1"
    p = Path(out_path).resolve()
    for part in (p.parent.name, p.stem):
        if _SLIDE_DIR_RE.match(part):
            return part.lower()
    return hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:8]


def _instance_id(item_id: str, out_path: "Path | None", explicit: "str | None") -> str:
    """Stable, globally-unique-per-occurrence id: `<item-id>#<suffix>`. Reusing the
    same component on two slides yields two distinct ids, so fidelity/measurement
    never pool slots or artifacts across occurrences."""
    return f"{item_id}#{_instance_suffix(out_path, explicit)}"


def _instance_attr(instance_id: "str | None") -> str:
    return f' data-component-instance="{instance_id}"' if instance_id else ""

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


# A published preview.html writes its source family straight into a double-quoted
# style attribute: style="...;font-family:"ProximaNova-Bold", "Proxima Nova",
# sans-serif;font-size:120px;...". Those inner quotes CLOSE the attribute, so the
# browser drops every declaration after them — a 120px hero title silently rendered
# at the default 32px, and the brand-font gate read the wreckage as bogus families.
# Dropping the declaration both repairs the attribute and applies the rule the
# slot-contract path already follows (see `_slot_text_css`): the brand pack outranks
# a component's foundry family, so slot text inherits the deck's brand font.
_SOURCE_FONT_FAMILY_RE = re.compile(r"font-family:[^;>]*;")

# Preview slots are authored TOP-aligned at the contract's tight line-height (often
# 1.0), with the box sized to the SOURCE copy's ink. Replacement copy in an accented
# script has taller ink — Vietnamese Ứ/Ụ — so its box escapes the wrapper's top even
# when the text fits by width and height (a real cover measured 646x135 ink inside a
# 728x146 box and still read as outside). Centre the text in the room the box already
# has, exactly as the slot-contract path does (`build_slot_scaffold`), so accented
# scripts render un-clipped WITHOUT shrinking the type. Horizontal placement is
# contract-owned and left alone.
_TOP_ALIGN_RE = re.compile(r"align-items:flex-start")


def _blank_text(slot_html: str) -> str:
    """Remove visible text nodes, keep all tags/attributes (incl. data-slot-id), drop
    the source font-family (`_SOURCE_FONT_FAMILY_RE`) and vertically centre the slot
    text (`_TOP_ALIGN_RE`)."""
    html = _SOURCE_FONT_FAMILY_RE.sub("", TEXT_NODE_RE.sub("><", slot_html))
    return _TOP_ALIGN_RE.sub("align-items:center", html)


def _bg_style(bg_url: str | None) -> str:
    """Style for the `.bg` layer. When the self-contained visual has already been
    materialized (bg_url set), wire it in directly so the reuse path produces a
    complete slide; otherwise leave it for the caller to set."""
    prefix = f"background-image:url('{bg_url}');" if bg_url else ""
    return prefix + "background-size:cover;background-position:center"


def build_scaffold(item_id: str, slots: list[str], bg_url: str | None = None,
                   instance_id: str | None = None) -> str:
    body = "\n    ".join(_blank_text(s) for s in slots)
    bg_note = ("" if bg_url else
               "<!-- set background-image: url(assets/page-NN/visual.svg) -->")
    return f"""<!-- scaffold generated from {item_id} preview.html — fill text into slots only.
     Do NOT move, restyle, or delete slots. The .bg background is the materialized
     self-contained visual (materialize_component_visual.py). -->
<style>
  .slide-scaffold {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; }}
  .slide-scaffold > .bg {{ position: absolute; inset: 0; width: 1920px; height: 1080px; }}
  .slide-scaffold .slot > * {{ margin: 0; }}
</style>
<div class="slide-scaffold" data-base-component="{item_id}"{_instance_attr(instance_id)} data-content-shape="">
  <div class="bg" data-base-component="{item_id}"
       style="{_bg_style(bg_url)}">{bg_note}</div>
    {body}
</div>
"""


CANVAS_W, CANVAS_H = 1920, 1080


def _item_entry(item_id: str, registry_path: str) -> dict:
    reg = load_json(registry_path)
    for entry in reg.get("items", []):
        if entry.get("id") == item_id:
            return entry
    raise SystemExit(f"ERROR: item_id {item_id!r} not found in {registry_path}")


def text_slot_contract(entry: dict) -> list[dict] | None:
    """Return the declared editable text slots when the component is a text-FREE
    base whose contract puts the copy in positioned slots (semantic_text_in_visual
    is False) and text-slots.json carries per-slot normalized bounds. Otherwise
    None. This is what lets a raster/vector component with no `.slot` markup in
    preview.html still be materialized against its real layout contract instead
    of a generic overlay. Nothing here is component-specific."""
    contract = entry.get("text_contract") or {}
    if contract.get("semantic_text_in_visual") is not False:
        return None
    if contract.get("editable") is False:
        return None
    ts_path = (entry.get("paths") or {}).get("text_slots")
    if not ts_path or not Path(ts_path).exists():
        return None
    data = load_json(ts_path)
    slots = data.get("slots", []) if isinstance(data, dict) else data
    usable = [s for s in slots
              if isinstance(s, dict) and s.get("id") and isinstance(s.get("bounds"), dict)]
    return usable or None


_JUSTIFY = {"left": "flex-start", "start": "flex-start", "center": "center",
            "middle": "center", "right": "flex-end", "end": "flex-end"}


def _num(x: float) -> str:
    return f"{float(x):g}"


def _slot_text_css(typo: dict, h_align: str, vscale: float) -> str:
    """Deterministic text style from the slot's OWN typography contract — family,
    weight, style, size, line-height, letter-spacing, colour and alignment. The
    font size is the source-unit size scaled to the deck canvas by the vertical
    ratio (`vscale`); it is FIXED. Text is never auto-shrunk to fit: a slot whose
    copy overflows is caught by the render-aware fidelity gate and the slide falls
    back to custom-local, rather than being silently resized here."""
    parts = ["margin:0"]
    if typo:
        # Deliberately DO NOT emit the contract's raw source font-family (e.g.
        # "ProximaNova-Bold"): the brand pack + accessibility layer outranks
        # component styling, so slot text inherits the deck's brand font (weight
        # and style below still come from the contract). Emitting the foundry name
        # would trip the brand-font gate and is not the brand family.
        size = typo.get("font_size")
        if isinstance(size, (int, float)):
            parts.append(f"font-size:{round(float(size) * vscale, 1)}px")
        if typo.get("font_weight"):
            parts.append(f"font-weight:{typo['font_weight']}")
        if typo.get("font_style"):
            parts.append(f"font-style:{typo['font_style']}")
        lh = typo.get("line_height")
        if isinstance(lh, (int, float)):
            parts.append(f"line-height:{_num(lh)}")
        ls = typo.get("letter_spacing")
        if ls and ls != "normal":
            parts.append(f"letter-spacing:{ls}")
        if typo.get("color"):
            parts.append(f"color:{typo['color']}")
    ta = {"center": "center", "middle": "center", "right": "right",
          "end": "right"}.get(h_align, "left")
    parts.append(f"text-align:{ta}")
    return ";".join(parts)


def build_slot_scaffold(item_id: str, slots: list[dict], bg_url: str | None = None,
                        vscale: float = 1.0, instance_id: str | None = None) -> str:
    """Emit one absolutely-positioned `data-component-slot` box per declared slot,
    placed at the slot's normalized bounds and styled with the slot's own
    typography + alignment (see `_slot_text_css`). The agent fills editable text
    into each box; the T3 fidelity gate then verifies the copy stayed inside its
    slot. Not a generic fixed-width/fixed-style overlay — geometry AND type come
    from the contract. `vscale` maps source-unit font sizes onto the deck canvas.

    Known ceiling: bounds map source space onto the full 1920x1080 canvas, so a
    component whose native aspect ratio differs is stretched anisotropically and
    the single-scalar font size favours vertical fidelity. Native-aspect
    sub-region placement is the upgrade trigger if that stretch is unacceptable."""
    rows: list[str] = []
    for s in slots:
        b = s["bounds"]
        try:
            left = round(float(b["x"]) * CANVAS_W)
            top = round(float(b["y"]) * CANVAS_H)
            width = round(float(b["width"]) * CANVAS_W)
            height = round(float(b["height"]) * CANVAS_H)
        except (KeyError, TypeError, ValueError):
            continue
        sid = str(s["id"])
        role = str(s.get("role") or "")
        tag = str(s.get("html_tag") or "div")
        justify = _JUSTIFY.get(str(s.get("horizontal_align") or "left"), "flex-start")
        # Vertically CENTER the text in its box: these boxes are typically taller
        # than a single line, and top-alignment at the contract's tight line-height
        # (often 1.0) lets a glyph's normal ascent — e.g. Vietnamese diacritics —
        # overshoot the line-box top and clip against the box. Centering uses the
        # available vertical room so accented scripts render un-clipped, WITHOUT
        # shrinking the type. Horizontal placement still follows the contract.
        align = "center"
        text_css = _slot_text_css(s.get("typography") or {},
                                  str(s.get("horizontal_align") or "left"), vscale)
        rows.append(
            f'  <div class="component-slot" data-component-slot="{sid}" data-slot-role="{role}"'
            f' style="position:absolute;left:{left}px;top:{top}px;width:{width}px;height:{height}px;'
            f'display:flex;justify-content:{justify};align-items:{align};overflow:hidden">'
            f'<{tag} class="slot-text" style="{text_css}"><!-- fill slot {sid} --></{tag}></div>'
        )
    body = "\n".join(rows)
    return f"""<!-- slot-aware scaffold from {item_id} text-slots.json — bind editable text to
     each data-component-slot and keep it inside the box. Set the `.bg`
     background from the self-contained visual (materialize_component_visual.py).
     Do NOT move/resize the slot boxes; the T3 fidelity gate checks their geometry. -->
<style>
  .slide-scaffold {{ position: relative; width: {CANVAS_W}px; height: {CANVAS_H}px; overflow: hidden; }}
  .slide-scaffold > .bg {{ position: absolute; inset: 0; width: {CANVAS_W}px; height: {CANVAS_H}px; }}
  .slide-scaffold .component-slot > * {{ margin: 0; }}
</style>
<div class="slide-scaffold" data-base-component="{item_id}"{_instance_attr(instance_id)} data-content-shape="" data-slot-contract="1">
  <div class="bg" data-base-component="{item_id}"
       style="{_bg_style(bg_url)}">{"" if bg_url else "<!-- set background-image from the materialized self-contained visual -->"}</div>
{body}
</div>
"""


BG_REL_DIR = "assets/comp"  # job-local home for materialized component visuals


def _source_font_scale(entry: dict) -> float:
    """The ISOTROPIC source-unit -> deck-canvas font scale: min(CANVAS_W/source_w,
    CANVAS_H/source_h). The scaffold places slot boxes with the anisotropic
    normalized×canvas mapping, so a component whose native aspect ratio differs is
    stretched unevenly. A single font size can only honour one scale; using the
    MIN keeps text within BOTH the box width and height (readable, fits), instead
    of the vertical-only scale which overflows wide-but-short source strips. Falls
    back to 1.0 when source dims are unavailable. Generic — reads text-slots.json."""
    ts_path = (entry.get("paths") or {}).get("text_slots")
    if not ts_path or not Path(ts_path).exists():
        return 1.0
    src = (load_json(ts_path) or {}).get("source") or {}
    w = src.get("canvas_width")
    h = src.get("canvas_height")
    vb = src.get("view_box")
    if isinstance(vb, list) and len(vb) == 4:
        w = w or vb[2]
        h = h or vb[3]
    try:
        scales = [s for s in (CANVAS_W / float(w) if w else None,
                              CANVAS_H / float(h) if h else None) if s]
        return min(scales) if scales else 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 1.0


def _materialize_bg(item_id: str, visual_src: Path, out_dir: Path) -> str | None:
    """Materialize the component's visual into a self-contained, job-local SVG next
    to the scaffold and return its RELATIVE url for the `.bg` layer. Returns None
    (and explains why) when the visual is missing, cannot be made self-contained
    (missing/unsafe local refs), or is blank — the reuse path then fails rather
    than emit a slide with a broken/blank background. Generic: no hardcoded ids."""
    if not visual_src.exists():
        print(f"ERROR: component visual not found: {visual_src}", file=sys.stderr)
        return None
    svg_text = visual_src.read_text(encoding="utf-8", errors="replace")
    out_svg, unresolved = materialize.inline_external_images(svg_text, visual_src.parent)
    if unresolved:
        print(f"ERROR: cannot materialize {item_id} visual — {len(unresolved)} "
              f"unresolved/unsafe local ref(s): {unresolved[:5]}", file=sys.stderr)
        return None
    if not materialize.is_nonblank(out_svg):
        print(f"ERROR: materialized {item_id} visual is blank (no images or shapes).",
              file=sys.stderr)
        return None
    rel = f"{BG_REL_DIR}/{item_id}.svg"
    dest = out_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out_svg, encoding="utf-8")
    print(f"materialize: {len(materialize.DATA_URI_RE.findall(out_svg))} embedded "
          f"image(s) -> {dest}", file=sys.stderr)
    return rel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a slide scaffold from a component's preview.html.")
    ap.add_argument("--item-id", required=True)
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--out", default=None, help="Write fragment here (default: stdout).")
    ap.add_argument("--instance-id", default=None,
                    help="Explicit unique occurrence suffix (default: derived from --out). "
                         "Lets the same component appear on multiple slides without pooling.")
    args = ap.parse_args(argv)

    entry = _item_entry(args.item_id, args.registry)
    # Every fresh scaffold carries a unique per-occurrence instance id so the
    # render-aware fidelity gate scopes slots/artifacts/measurements to THIS
    # placement, never pooling across two uses of the same component.
    instance_id = _instance_id(args.item_id,
                               Path(args.out) if args.out else None, args.instance_id)
    preview = (entry.get("paths") or {}).get("preview")
    slots: list[str] = []
    if preview and Path(preview).exists():
        slots = _extract_slots(Path(preview).read_text(encoding="utf-8", errors="replace"))

    # Wire generic materialization into the reuse path: when writing to a file and
    # the component ships a visual, produce a self-contained job-local background
    # and fail hard if it cannot be made complete (Part B). stdout mode stays a
    # pure fragment (no sidecar location), keeping the placeholder note.
    bg_url: str | None = None
    visual = (entry.get("paths") or {}).get("visual")
    if args.out and visual:
        bg_url = _materialize_bg(args.item_id, Path(visual), Path(args.out).parent)
        if bg_url is None:
            return 1  # do not emit a scaffold that references a broken/blank .bg

    if slots:
        fragment = build_scaffold(args.item_id, slots, bg_url, instance_id=instance_id)
        count = len(slots)
    else:
        # No wired `.slot` markup. If the component declares an editable text-slot
        # contract (semantic_text_in_visual False), materialize positioned
        # data-component-slot boxes from its real bounds rather than a generic
        # fixed overlay. Otherwise fall back to a .bg-only scaffold as before.
        contract_slots = text_slot_contract(entry)
        if contract_slots:
            fragment = build_slot_scaffold(args.item_id, contract_slots, bg_url,
                                           vscale=_source_font_scale(entry),
                                           instance_id=instance_id)
            count = len(contract_slots)
            print(f"note: no `.slot` in preview.html — built slot-aware scaffold from "
                  f"text-slots.json ({count} slot(s)).", file=sys.stderr)
        else:
            print(f"WARN: no `.slot` and no editable text-slot contract for "
                  f"{args.item_id} — emitting .bg-only scaffold (raster component; "
                  f"fill the background via decompose only).", file=sys.stderr)
            fragment = build_scaffold(args.item_id, [], bg_url, instance_id=instance_id)
            count = 0

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(fragment, encoding="utf-8")
        print(f"scaffold: {count} slot(s) from {args.item_id} -> {args.out}")
    else:
        print(fragment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
