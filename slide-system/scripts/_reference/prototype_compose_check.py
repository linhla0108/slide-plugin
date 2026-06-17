#!/usr/bin/env python3
"""prototype_compose_check.py — verdict half of the P1 step-0 gate.

Re-composes the layers captured by prototype_overlay_capture.js with pure PIL
(no browser) and diffs against the references, exactly like the future
orchestrator step (c) will (EXPORT-PPTX-3LAYER-PLAN.md §10.1):

  tier-1: base + overlays (at recorded clips)        vs ref-notext.png
  tier-2: tier-1 + text layer                        vs ref-full.png

Gates (§10.2 starting thresholds):
  tier-1: mean_err <= 0.5, changed_ratio <= 0.001
  tier-2: mean_err <= 1.0, changed_ratio <= 0.005

Exit 0 = GATE PASS (build capture v2), exit 1 = GATE FAIL (take the
pre-decided fallback: C5 bake-with-background, or rethink).

Usage: python3 prototype_compose_check.py --dir outputs/prototype-3layer
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import write_json


def diff_metrics(reference, candidate, threshold: int = 24) -> dict:
    from PIL import ImageChops, ImageStat

    diff = ImageChops.difference(reference.convert("RGB"), candidate.convert("RGB"))
    stat = ImageStat.Stat(diff)
    mean_err = sum(stat.mean) / 3
    pixels = list(diff.get_flattened_data())
    changed = sum(max(px) > threshold for px in pixels)
    return {
        "mean_err": round(mean_err, 4),
        "changed_ratio": round(changed / len(pixels), 8),
        "changed_pixels": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="prototype output directory")
    parser.add_argument("--threshold", type=int, default=24)
    args = parser.parse_args()
    out = Path(args.dir)

    from PIL import Image

    manifest = json.loads((out / "proto-manifest.json").read_text(encoding="utf-8"))
    composed = Image.open(out / "base.png").convert("RGBA")
    for ov in manifest["overlays"]:
        layer = Image.open(out / ov["png"]).convert("RGBA")
        clip = ov["clip"]
        composed.alpha_composite(layer, dest=(int(clip["x"]), int(clip["y"])))

    tier1 = diff_metrics(Image.open(out / "ref-notext.png"), composed, args.threshold)
    composed.save(out / "composed-tier1.png")

    full = composed.copy()
    full.alpha_composite(Image.open(out / "text.png").convert("RGBA"), dest=(0, 0))
    tier2 = diff_metrics(Image.open(out / "ref-full.png"), full, args.threshold)
    full.save(out / "composed-tier2.png")

    gates = {
        "tier1": {"max_mean_err": 0.5, "max_changed_ratio": 0.001},
        "tier2": {"max_mean_err": 1.0, "max_changed_ratio": 0.005},
    }
    verdict = {
        "tier1": {**tier1, "pass": tier1["mean_err"] <= gates["tier1"]["max_mean_err"]
                  and tier1["changed_ratio"] <= gates["tier1"]["max_changed_ratio"]},
        "tier2": {**tier2, "pass": tier2["mean_err"] <= gates["tier2"]["max_mean_err"]
                  and tier2["changed_ratio"] <= gates["tier2"]["max_changed_ratio"]},
        "gates": gates,
    }
    verdict["gate_pass"] = verdict["tier1"]["pass"] and verdict["tier2"]["pass"]
    write_json(out / "gate-verdict.json", verdict)
    print(json.dumps(verdict, indent=2))

    if not verdict["gate_pass"]:
        from PIL import ImageChops, ImageEnhance
        for tier, cand in (("tier1", composed), ("tier2", full)):
            ref = Image.open(out / ("ref-notext.png" if tier == "tier1" else "ref-full.png"))
            diff = ImageChops.difference(ref.convert("RGB"), cand.convert("RGB"))
            ImageEnhance.Contrast(diff).enhance(6).save(out / f"diff-{tier}.png")
        print("[proto] GATE FAIL — diff images saved for inspection")
        return 1
    print("[proto] GATE PASS — transparent-overlay capture technique proven")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
