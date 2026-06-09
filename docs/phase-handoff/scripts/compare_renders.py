#!/usr/bin/env python3
"""Create repeatable visual evidence for two directories of slide PNGs."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageStat


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--changed-threshold", type=int, default=24)
    return parser.parse_args()


def slide_map(folder):
    return {path.name: path for path in sorted(folder.glob("slide-*.png"))}


def metrics(baseline, candidate, changed_threshold):
    diff = ImageChops.difference(baseline, candidate)
    stats = ImageStat.Stat(diff)
    samples = max(1, len(stats.mean))
    normalized_mae = sum(stats.mean) / samples / 255
    normalized_rmse = math.sqrt(
        sum(value * value for value in stats.rms) / samples
    ) / 255

    gray = diff.convert("L")
    histogram = gray.histogram()
    pixels = baseline.width * baseline.height
    exact_mismatch = 1 - (histogram[0] / pixels)
    changed = sum(histogram[changed_threshold + 1 :]) / pixels

    return {
        "normalized_mae": round(normalized_mae, 6),
        "normalized_rmse": round(normalized_rmse, 6),
        "exact_mismatch_ratio": round(exact_mismatch, 6),
        "changed_pixel_ratio": round(changed, 6),
    }, diff


def save_evidence(name, baseline, candidate, diff, output):
    for folder in ("side-by-side", "overlay", "diff"):
        (output / folder).mkdir(parents=True, exist_ok=True)

    side = Image.new("RGB", (baseline.width * 2, baseline.height), "white")
    side.paste(baseline, (0, 0))
    side.paste(candidate, (baseline.width, 0))
    side.save(output / "side-by-side" / name)

    Image.blend(baseline, candidate, 0.5).save(output / "overlay" / name)
    ImageEnhance.Brightness(diff).enhance(4).save(output / "diff" / name)


def policy_status(values, policy):
    checks = {
        "normalized_mae": values["normalized_mae"]
        <= policy["max_normalized_mae"],
        "normalized_rmse": values["normalized_rmse"]
        <= policy["max_normalized_rmse"],
        "changed_pixel_ratio": values["changed_pixel_ratio"]
        <= policy["max_changed_pixel_ratio"],
    }
    return all(checks.values()), checks


def main():
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    baseline = slide_map(args.baseline)
    candidate = slide_map(args.candidate)
    names = sorted(set(baseline) | set(candidate))
    policy = json.loads(args.policy.read_text()) if args.policy else None

    slides = []
    for name in names:
        if name not in baseline or name not in candidate:
            slides.append(
                {
                    "slide": name,
                    "status": "missing-pair",
                    "baseline": name in baseline,
                    "candidate": name in candidate,
                }
            )
            continue

        base_image = Image.open(baseline[name]).convert("RGB")
        candidate_image = Image.open(candidate[name]).convert("RGB")
        if base_image.size != candidate_image.size:
            slides.append(
                {
                    "slide": name,
                    "status": "dimension-mismatch",
                    "baseline_size": base_image.size,
                    "candidate_size": candidate_image.size,
                }
            )
            continue

        values, diff = metrics(
            base_image, candidate_image, args.changed_threshold
        )
        save_evidence(
            name, base_image, candidate_image, diff, args.output
        )
        item = {
            "slide": name,
            "status": "measured",
            "size": base_image.size,
            **values,
        }
        if policy:
            passed, checks = policy_status(values, policy)
            item["status"] = "pass" if passed else "fail"
            item["checks"] = checks
        slides.append(item)

    comparable = [item for item in slides if "normalized_mae" in item]
    overall = {
        "status": (
            "unverified"
            if not policy
            else "pass"
            if slides and all(item["status"] == "pass" for item in slides)
            else "fail"
        ),
        "baseline_count": len(baseline),
        "candidate_count": len(candidate),
        "pair_count": len(comparable),
        "changed_threshold": args.changed_threshold,
        "policy": str(args.policy) if args.policy else None,
        "slides": slides,
    }
    (args.output / "pixel-parity-report.json").write_text(
        json.dumps(overall, indent=2) + "\n"
    )
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
