#!/usr/bin/env python3
"""Extract an auditable SVG structure manifest using only the standard library."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET


XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
GEOMETRY_ATTRS = {
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "points", "d", "transform", "viewBox",
}
STYLE_ATTRS = {
    "style", "class", "fill", "fill-opacity", "stroke", "stroke-width",
    "stroke-opacity", "opacity", "clip-path", "mask", "filter",
    "marker-start", "marker-mid", "marker-end", "font-family", "font-size",
    "font-style", "font-weight", "text-anchor", "display", "visibility",
}
DIRECT_REFERENCE_ATTRS = {"href", XLINK_HREF}
URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)")


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))", value)
    return float(match.group(1)) if match else None


def summarize_data_uri(value: str) -> dict:
    header, _, payload = value.partition(",")
    media = header[5:].split(";", 1)[0] or "text/plain"
    is_base64 = ";base64" in header
    if is_base64:
        estimated = max(0, len(payload) * 3 // 4 - payload.count("="))
    else:
        estimated = len(unquote(payload).encode("utf-8"))
    return {
        "kind": "embedded-data",
        "media_type": media,
        "encoding": "base64" if is_base64 else "url-encoded",
        "estimated_bytes": estimated,
    }


def classify_reference(raw: str, source_dir: Path) -> dict:
    value = raw.strip()
    if value.startswith("data:"):
        result = summarize_data_uri(value)
    elif value.startswith("#"):
        result = {"kind": "fragment", "target": value[1:]}
    else:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            result = {"kind": "external-url", "target": value}
        elif parsed.scheme and parsed.scheme != "file":
            result = {"kind": "external-scheme", "target": value}
        else:
            path_value = unquote(parsed.path)
            resolved = (source_dir / path_value).resolve()
            result = {
                "kind": "local-file",
                "target": value,
                "resolved": str(resolved),
                "exists": resolved.exists(),
            }
    return result


def selected_attributes(element: ET.Element, include_path_data: bool) -> dict:
    attrs = {}
    for raw_name, value in element.attrib.items():
        name = local_name(raw_name)
        if name in GEOMETRY_ATTRS or name in STYLE_ATTRS or raw_name == XLINK_HREF or name == "href":
            if name == "d" and not include_path_data:
                attrs["d_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()
                attrs["d_length"] = len(value)
            elif value.startswith("data:"):
                attrs[name] = summarize_data_uri(value)
            else:
                attrs[name] = value
    return attrs


def collect_references(element: ET.Element, source_dir: Path, node_index: int) -> list[dict]:
    found = []
    for raw_name, value in element.attrib.items():
        name = local_name(raw_name)
        candidates = []
        if raw_name in DIRECT_REFERENCE_ATTRS or name in DIRECT_REFERENCE_ATTRS:
            candidates.append(value)
        candidates.extend(URL_RE.findall(value))
        for candidate in candidates:
            record = classify_reference(candidate, source_dir)
            record.update({"node_index": node_index, "attribute": name, "raw": candidate})
            found.append(record)
    return found


def build_manifest(source: Path, include_path_data: bool) -> dict:
    tree = ET.parse(source)
    root = tree.getroot()
    tag_counts: Counter[str] = Counter()
    nodes: list[dict] = []
    texts: list[dict] = []
    references: list[dict] = []

    def walk(element: ET.Element, parent_index: int | None) -> None:
        tag = local_name(element.tag)
        index = len(nodes)
        tag_counts[tag] += 1
        text = "".join(element.itertext()).strip() if tag in {"text", "tspan"} else ""
        node = {
            "index": index,
            "parent_index": parent_index,
            "tag": tag,
            "id": element.attrib.get("id"),
            "attributes": selected_attributes(element, include_path_data),
        }
        if text:
            node["text"] = text
            texts.append({"node_index": index, "tag": tag, "text": text})
        nodes.append(node)
        references.extend(collect_references(element, source.parent, index))
        for child in list(element):
            walk(child, index)

    walk(root, None)

    width = root.attrib.get("width")
    height = root.attrib.get("height")
    view_box = root.attrib.get("viewBox")
    vb_numbers = []
    if view_box:
        try:
            vb_numbers = [float(value) for value in re.split(r"[\s,]+", view_box.strip())]
        except ValueError:
            vb_numbers = []

    numeric_width = parse_number(width)
    numeric_height = parse_number(height)
    if len(vb_numbers) == 4 and vb_numbers[3]:
        aspect_ratio = vb_numbers[2] / vb_numbers[3]
    elif numeric_width is not None and numeric_height:
        aspect_ratio = numeric_width / numeric_height
    else:
        aspect_ratio = None

    warnings = []
    ids = {node["id"] for node in nodes if node["id"]}
    for reference in references:
        if reference["kind"] == "fragment" and reference["target"] not in ids:
            warnings.append(f"Missing fragment reference: #{reference['target']}")
        if reference["kind"] == "local-file" and not reference["exists"]:
            warnings.append(f"Missing local file: {reference['target']}")
        if reference["kind"] in {"external-url", "external-scheme"}:
            warnings.append(f"External reference requires runtime access: {reference['target']}")

    native_text = tag_counts["text"] + tag_counts["tspan"]
    if native_text:
        text_mode = "native-text"
    elif tag_counts["path"]:
        text_mode = "probable-path-text"
        warnings.append("No native text elements found; paths may include converted text.")
    else:
        text_mode = "no-text-detected"

    return {
        "source": str(source.resolve()),
        "sha256": sha256(source),
        "valid_xml": True,
        "width": width,
        "height": height,
        "viewBox": view_box,
        "preserveAspectRatio": root.attrib.get("preserveAspectRatio"),
        "aspect_ratio": aspect_ratio,
        "tag_counts": dict(sorted(tag_counts.items())),
        "id_count": len(ids),
        "text_mode": text_mode,
        "texts": texts,
        "nodes": nodes,
        "references": references,
        "warnings": sorted(set(warnings)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument("--omit-path-data", action="store_true")
    args = parser.parse_args()

    try:
        manifest = build_manifest(args.svg, include_path_data=not args.omit_path_data)
    except (ET.ParseError, OSError) as error:
        print(f"SVG extraction failed: {error}", file=sys.stderr)
        return 1

    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
