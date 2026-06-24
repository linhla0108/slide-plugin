#!/usr/bin/env python3
"""Trim extraction artifact weight: round SVG coordinate precision and
downsample oversized embedded rasters.

Reusable batch post-step. Run against any extraction batch:

    python3 slide-system/scripts/optimize_svg.py --batch <batch-dir>

SVG: every decimal number with magnitude >= 1 in `artifact/visual.svg` and
`evidence/source-with-text.svg` is rounded to `--precision` decimals (default 2).
Sub-1 values (opacity, tiny deltas) keep up to 3 decimals so faint elements never
collapse. Geometry stays sub-pixel accurate at slide scale.

Raster: each file under `artifact/assets/` whose longest side exceeds
`--max-dimension` (default 1920) is downsampled in place with `sips`, keeping the
original format (safe, no reference rewrite). Pass `--raster-to-jpeg` to also
convert opaque (no-alpha) rasters to JPEG and rewrite the referencing SVGs — a
larger but lossy/format-changing win, so it is opt-in.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


NUMBER = re.compile(r"-?\d+\.\d+")
# Round numbers only inside geometry attribute values (path/polygon data and
# transforms). This is where ~all decimal tokens and bytes live, and it can never
# corrupt structural tokens like the XML prolog `version="1.0"` or `encoding`.
GEOMETRY_ATTR = re.compile(r"\b(d|points|transform)\s*=\s*(\"[^\"]*\"|'[^']*')")


def round_numbers(text: str, precision: int) -> str:
    def round_token(match: re.Match[str]) -> str:
        value = float(match.group(0))
        digits = precision if abs(value) >= 1 else max(precision, 3)
        rounded = round(value, digits)
        out = f"{rounded:.{digits}f}".rstrip("0").rstrip(".")
        return out if out not in ("", "-0") else "0"

    def round_attr(match: re.Match[str]) -> str:
        name, value = match.group(1), match.group(2)
        quote = value[0]
        inner = NUMBER.sub(round_token, value[1:-1])
        return f"{name}={quote}{inner}{quote}"

    return GEOMETRY_ATTR.sub(round_attr, text)


def optimize_svgs(batch: Path, precision: int) -> tuple[int, int, int]:
    targets: list[Path] = []
    targets += list((batch / "items").glob("*/artifact/visual.svg"))
    targets += list((batch / "items").glob("*/evidence/source-with-text.svg"))
    before = after = 0
    for svg in sorted(targets):
        original = svg.read_text(encoding="utf-8")
        optimized = round_numbers(original, precision)
        before += len(original.encode("utf-8"))
        after += len(optimized.encode("utf-8"))
        if optimized != original:
            svg.write_text(optimized, encoding="utf-8")
    return len(targets), before, after


def sips(*args: str) -> None:
    subprocess.run(["sips", *args], check=True, capture_output=True, text=True)


def sips_get(path: Path, key: str) -> str:
    result = subprocess.run(
        ["sips", "-g", key, str(path)], check=False, capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if key in line:
            return line.rsplit(":", 1)[-1].strip()
    return ""


def longest_side(path: Path) -> int:
    w = sips_get(path, "pixelWidth")
    h = sips_get(path, "pixelHeight")
    return max(int(w or 0), int(h or 0))


def to_webp(src: Path, quality: int) -> Path | None:
    """Transcode to WebP via cwebp if available. Returns the new path or None.

    WebP is the smallest format for large-screen display, but it is NOT embedded
    by the PPTX export path (older PowerPoint cannot display WebP) — the export
    recompose step transcodes it back to PNG/JPEG. Only used when libwebp/cwebp
    is installed; otherwise the caller falls back to JPEG.
    """
    if shutil.which("cwebp") is None:
        return None
    dest = src.with_suffix(".webp")
    subprocess.run(
        ["cwebp", "-quiet", "-q", str(quality), str(src), "-o", str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def optimize_rasters(
    batch: Path, max_dimension: int, raster_format: str, quality: int
) -> tuple[int, int, int]:
    if shutil.which("sips") is None:
        print("  (sips not available — skipping raster optimization)")
        return 0, 0, 0
    assets = sorted(
        path
        for path in (batch / "items").glob("*/artifact/assets/*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    count = before = after = 0
    for asset in assets:
        before_size = asset.stat().st_size
        if longest_side(asset) > max_dimension:
            sips("--resampleHeightWidthMax", str(max_dimension), str(asset))
        # Only recompress opaque images; alpha must stay PNG (lossless transparency).
        opaque = asset.suffix.lower() == ".png" and sips_get(asset, "hasAlpha") == "no"
        if opaque and raster_format in {"jpeg", "webp"}:
            converted: Path | None = None
            if raster_format == "webp":
                converted = to_webp(asset, quality)
            if converted is None:  # webp unavailable or jpeg requested
                converted = asset.with_suffix(".jpg")
                sips("-s", "format", "jpeg", "-s", "formatOptions", str(quality),
                     str(asset), "--out", str(converted))
            if converted != asset:
                asset.unlink()
                rewrite_reference(batch, asset.name, converted.name)
                asset = converted
        before += before_size
        after += asset.stat().st_size
        count += 1
    return count, before, after


def rewrite_reference(batch: Path, old_name: str, new_name: str) -> None:
    for svg in (batch / "items").glob("*/*/*.svg"):
        text = svg.read_text(encoding="utf-8")
        if old_name in text:
            svg.write_text(text.replace(old_name, new_name), encoding="utf-8")
    for manifest in (batch / "items").glob("*/evidence/external-images.json"):
        text = manifest.read_text(encoding="utf-8")
        if old_name in text:
            manifest.write_text(text.replace(old_name, new_name), encoding="utf-8")


def kb(num: int) -> str:
    return f"{num / 1024:.0f}KB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=Path, help="Extraction batch directory")
    parser.add_argument("--precision", type=int, default=2, help="SVG decimal places (default 2)")
    parser.add_argument("--max-dimension", type=int, default=1920, help="Raster longest-side cap")
    parser.add_argument(
        "--raster-format",
        choices=["jpeg", "webp", "keep"],
        default="jpeg",
        help="Opaque raster recompression: jpeg (default, PPTX-safe), webp (needs "
        "cwebp; export transcodes back), or keep (downsample only, no format change)",
    )
    parser.add_argument("--raster-quality", type=int, default=85, help="Recompression quality")
    args = parser.parse_args()
    batch = args.batch.resolve()
    if not (batch / "items").is_dir():
        parser.error(f"{batch} has no items/ — not an extraction batch")

    n_svg, svg_before, svg_after = optimize_svgs(batch, args.precision)
    print(f"SVG: {n_svg} file(s) {kb(svg_before)} -> {kb(svg_after)}")

    n_ras, ras_before, ras_after = optimize_rasters(
        batch, args.max_dimension, args.raster_format, args.raster_quality
    )
    if n_ras:
        print(f"Raster: {n_ras} file(s) {kb(ras_before)} -> {kb(ras_after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
