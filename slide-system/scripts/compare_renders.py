#!/usr/bin/env python3
"""Create repeatable visual evidence for two equal-size slide renders."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import now_iso, write_json

DEFAULT_PIXEL_DELTA_THRESHOLD = 36


def _compare_images(reference, candidate, threshold: int) -> tuple[object, dict[str, float]]:
    from PIL import ImageChops, ImageStat

    diff = ImageChops.difference(reference.convert("RGBA"), candidate.convert("RGBA")).convert("RGB")
    stat = ImageStat.Stat(diff)
    mean_error = sum(stat.mean) / 3
    rms_error = (sum(value * value for value in stat.rms) / 3) ** 0.5
    pixels = list(diff.get_flattened_data())
    changed = sum(max(pixel) > threshold for pixel in pixels)
    return diff, {
        "mean_absolute_error": mean_error,
        "rms_error": rms_error,
        "changed_pixel_ratio": changed / len(pixels),
    }


def compute_metrics(reference, candidate,
                    threshold: int = DEFAULT_PIXEL_DELTA_THRESHOLD) -> dict[str, float]:
    """Measure render drift while ignoring low-delta anti-aliasing edge noise."""
    return _compare_images(reference, candidate, threshold)[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--threshold", type=int, default=DEFAULT_PIXEL_DELTA_THRESHOLD)
    args = parser.parse_args()

    try:
        from PIL import Image, ImageEnhance
    except ImportError as error:
        raise SystemExit(f"Pillow is required: {error}")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reference = Image.open(args.reference).convert("RGBA")
    candidate = Image.open(args.candidate).convert("RGBA")
    if reference.size != candidate.size:
        raise SystemExit(f"Render sizes differ: {reference.size} vs {candidate.size}")

    diff, metrics = _compare_images(reference, candidate, args.threshold)

    side = Image.new("RGBA", (reference.width * 2, reference.height), "white")
    side.paste(reference, (0, 0))
    side.paste(candidate, (reference.width, 0))
    side.save(output / "side-by-side.png")
    Image.blend(reference, candidate, 0.5).save(output / "overlay.png")
    ImageEnhance.Contrast(diff).enhance(4).save(output / "diff.png")

    report = {
        "generated_at": now_iso(),
        "reference": str(Path(args.reference).resolve()),
        "candidate": str(Path(args.candidate).resolve()),
        "size": {"width": reference.width, "height": reference.height},
        "threshold": args.threshold,
        "metrics": {
            "mean_absolute_error": round(metrics["mean_absolute_error"], 4),
            "rms_error": round(metrics["rms_error"], 4),
            "changed_pixel_ratio": round(metrics["changed_pixel_ratio"], 8),
        },
        "evidence": ["side-by-side.png", "overlay.png", "diff.png"],
    }
    write_json(output / "report.json", report)
    print(f"changed_pixel_ratio={metrics['changed_pixel_ratio']:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
