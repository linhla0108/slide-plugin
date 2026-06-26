#!/usr/bin/env python3
"""Split semantic SVG text into editable normalized text-slot contracts."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
SVG = f"{{{SVG_NS}}}"
XLINK_HREF = f"{{{XLINK_NS}}}href"
NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
MATRIX = re.compile(r"matrix\(([^)]+)\)")
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


def numbers(value: str | None) -> list[float]:
    return [float(item) for item in NUMBER.findall(value or "")]


def matrix(value: str | None) -> tuple[float, float, float, float, float, float]:
    match = MATRIX.search(value or "")
    values = numbers(match.group(1)) if match else []
    return tuple(values) if len(values) == 6 else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def transform_point(
    x: float, y: float, transform: tuple[float, float, float, float, float, float]
) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    return a * x + c * y + e, b * x + d * y + f


def inherited(element: ET.Element, parent: ET.Element, name: str, default: str = "") -> str:
    return element.attrib.get(name, parent.attrib.get(name, default))


def clean_font_family(value: str) -> str:
    family = value.split("+", 1)[-1]
    aliases = {
        "ArialMT": "Arial",
        "Arial-BoldMT": "Arial",
        "ProximaNova-Extrabld": "Proxima Nova",
        "ProximaNova-BoldIt": "Proxima Nova",
        "ProximaNova-SemiboldIt": "Proxima Nova",
    }
    return aliases.get(family, family or "Arial")


def font_weight(raw_family: str, explicit: str) -> str:
    if explicit and explicit != "400":
        return explicit
    lowered = raw_family.lower()
    if any(token in lowered for token in ("extrabld", "extrabold", "black")):
        return "800"
    if "bold" in lowered:
        return "700"
    if "semibold" in lowered:
        return "600"
    return explicit or "400"


def semantic_role(text: str, font_size: float, font_weight: str) -> tuple[str, str]:
    stripped = text.strip()
    upper = stripped.upper() == stripped and any(char.isalpha() for char in stripped)
    if font_size >= 70:
        return "title", "h1"
    if font_size >= 42 or (upper and font_size >= 30):
        return "heading", "h2"
    if font_size >= 28 and ("bold" in font_weight.lower() or upper):
        return "subheading", "h3"
    if stripped.startswith(("□", "•", "-", "–")):
        return "list-item", "li"
    if len(stripped) <= 24:
        return "label", "span"
    return "body", "p"


def slug(text: str, fallback: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (value[:48].rstrip("-") or fallback)


def split_runs(
    text: str, xs: list[float], font_size: float = 0.0
) -> list[tuple[str, list[float], int, int]]:
    if len(xs) != len(text) or len(xs) < 2:
        return [(text, xs, 0, len(text))]
    # A single <tspan> can carry glyphs for several spatially-separated words on
    # the same baseline (e.g. three column headings "STRATEGIST", "DRIVER",
    # "COACH" concatenated into one tspan). Split on two signals:
    #   - a BACKWARD jump (x resets left)        -> a line wrap;
    #   - a large FORWARD gap between glyphs      -> a new word/column.
    # The forward-gap threshold is well above a normal glyph advance (and any
    # word space) so ordinary phrases stay intact.
    advances = sorted(xs[i] - xs[i - 1] for i in range(1, len(xs)) if xs[i] > xs[i - 1])
    median_adv = advances[len(advances) // 2] if advances else 0.0
    fwd_gap = max(median_adv * 3.0, font_size) if median_adv else float("inf")
    breaks = [0]
    for index in range(1, len(xs)):
        delta = xs[index] - xs[index - 1]
        if delta < -10 or delta > fwd_gap:
            breaks.append(index)
    breaks.append(len(text))
    result = []
    for start, end in zip(breaks, breaks[1:]):
        value = text[start:end]
        if value.strip():
            result.append((value, xs[start:end], start, end))
    return result or [(text, xs, 0, len(text))]


def rewrite_evidence_asset_paths(root: ET.Element) -> None:
    for element in root.iter():
        for attribute in ("href", XLINK_HREF):
            value = element.attrib.get(attribute)
            if value and value.startswith("assets/"):
                element.set(attribute, f"../artifact/{value}")


def rewrite_visual_asset_paths(root: ET.Element) -> None:
    for element in root.iter():
        for attribute in ("href", XLINK_HREF):
            value = element.attrib.get(attribute)
            if value and value.startswith("../artifact/assets/"):
                element.set(attribute, value.removeprefix("../artifact/"))


def extract_item(item_dir: Path, input_name: str) -> dict:
    artifact_dir = item_dir / "artifact"
    evidence_dir = item_dir / "evidence"
    input_svg = (artifact_dir / input_name).resolve()
    if not input_svg.exists():
        raise SystemExit(f"Missing SVG: {input_svg}")

    tree = ET.parse(input_svg)
    root = tree.getroot()
    view_box = numbers(root.attrib.get("viewBox"))
    if len(view_box) != 4 or not view_box[2] or not view_box[3]:
        raise SystemExit(f"SVG requires a valid viewBox: {input_svg}")
    min_x, min_y, canvas_width, canvas_height = view_box

    evidence_path = evidence_dir / "source-with-text.svg"
    if input_svg != evidence_path.resolve():
        source_root = copy.deepcopy(root)
        rewrite_evidence_asset_paths(source_root)
        evidence_tree = ET.ElementTree(source_root)
        evidence_tree.write(evidence_path, encoding="unicode", xml_declaration=True)

    rewrite_visual_asset_paths(root)

    parents = {child: parent for parent in root.iter() for child in parent}
    slots = []
    used_ids: dict[str, int] = {}
    text_elements = list(root.iter(f"{SVG}text"))

    for text_index, text_element in enumerate(text_elements):
        transform = matrix(text_element.attrib.get("transform"))
        rotation = round(math.degrees(math.atan2(transform[1], transform[0])), 4)
        tspans = list(text_element.findall(f"{SVG}tspan"))
        if not tspans:
            tspans = [text_element]

        for tspan_index, tspan in enumerate(tspans):
            value = "".join(tspan.itertext())
            if not value.strip():
                continue
            font_size = float(inherited(tspan, text_element, "font-size", "16"))
            xs = numbers(inherited(tspan, text_element, "x"))
            ys = numbers(inherited(tspan, text_element, "y"))
            base_x = xs[0] if xs else 0.0
            base_y = ys[0] if ys else 0.0

            for run_index, (run_text, run_xs, char_start, char_end) in enumerate(
                split_runs(value, xs, font_size)
            ):
                x_values = run_xs or [base_x]
                source_x = min(x_values)
                source_y = base_y
                actual_x, baseline_y = transform_point(source_x, source_y, transform)
                if len(x_values) > 1:
                    width = max(x_values) - min(x_values) + font_size * 0.72
                else:
                    width = max(font_size * 0.72, len(run_text) * font_size * 0.52)
                height = font_size * 1.22
                top_y = baseline_y - font_size * 0.92

                nx = max(0.0, min(1.0, (actual_x - min_x) / canvas_width))
                ny = max(0.0, min(1.0, (top_y - min_y) / canvas_height))
                nw = max(0.0001, min(1.0 - nx, width / canvas_width))
                nh = max(0.0001, min(1.0 - ny, height / canvas_height))

                raw_family = inherited(tspan, text_element, "font-family", "Arial")
                weight = font_weight(
                    raw_family,
                    inherited(tspan, text_element, "font-weight", "400"),
                )
                role, html_tag = semantic_role(run_text, font_size, weight)
                base_id = slug(run_text, f"text-{text_index + 1}")
                used_ids[base_id] = used_ids.get(base_id, 0) + 1
                slot_id = (
                    base_id
                    if used_ids[base_id] == 1
                    else f"{base_id}-{used_ids[base_id]}"
                )
                anchor = inherited(tspan, text_element, "text-anchor", "start")
                align = {"start": "left", "middle": "center", "end": "right"}.get(
                    anchor, "left"
                )
                fill = inherited(tspan, text_element, "fill", "#171717")
                family = clean_font_family(raw_family)
                style = inherited(tspan, text_element, "font-style", "normal")
                letter_spacing = inherited(tspan, text_element, "letter-spacing", "normal")

                slots.append(
                    {
                        "id": slot_id,
                        "role": role,
                        "html_tag": html_tag,
                        "example_value": run_text.strip(),
                        "editable": True,
                        "allow_empty": True,
                        "bounds": {
                            "x": round(nx, 7),
                            "y": round(ny, 7),
                            "width": round(nw, 7),
                            "height": round(nh, 7),
                        },
                        "anchor": anchor,
                        "horizontal_align": align,
                        "vertical_align": "top",
                        "rotation": rotation,
                        "z_order": len(slots) + 1,
                        "typography": {
                            "font_family": family,
                            "font_size": round(font_size, 4),
                            "font_size_unit": "source-unit",
                            "font_weight": weight,
                            "font_style": style,
                            "line_height": 1.0,
                            "letter_spacing": letter_spacing,
                            "color": fill,
                        },
                        "source_refs": [
                            {
                                "text_index": text_index,
                                "tspan_index": tspan_index,
                                "run_index": run_index,
                                "character_range": [char_start, char_end],
                            }
                        ],
                        "style_overrides": [
                            "example_value",
                            "bounds",
                            "font_family",
                            "font_size",
                            "font_weight",
                            "font_style",
                            "line_height",
                            "letter_spacing",
                            "color",
                            "horizontal_align",
                            "vertical_align",
                            "rotation",
                        ],
                    }
                )

    for text_element in text_elements:
        parent = parents.get(text_element)
        if parent is not None:
            parent.remove(text_element)

    visual_path = artifact_dir / "visual.svg"
    ET.ElementTree(root).write(visual_path, encoding="unicode", xml_declaration=True)
    if input_svg.parent == artifact_dir.resolve() and input_svg != visual_path.resolve():
        input_svg.unlink()

    contract = {
        "schema_version": 1,
        "coordinate_space": {"unit": "normalized", "width": 1, "height": 1},
        "source": {
            "svg": "../evidence/source-with-text.svg",
            "view_box": view_box,
            "canvas_width": canvas_width,
            "canvas_height": canvas_height,
        },
        "artwork_text_exemptions": [],
        "slots": slots,
    }
    slots_path = artifact_dir / "text-slots.json"
    slots_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "slot_count": len(slots),
        "source_text_element_count": len(text_elements),
        "visual": "artifact/visual.svg",
        "slots": "artifact/text-slots.json",
        "evidence": "evidence/source-with-text.svg",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-dir", action="append", type=Path, required=True)
    parser.add_argument("--input-name", default="source-page.svg")
    args = parser.parse_args()
    results = {}
    for item_dir in args.item_dir:
        results[item_dir.name] = extract_item(item_dir, args.input_name)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
