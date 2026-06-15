#!/usr/bin/env python3
"""export_pptx.py — the ONE entry point for PPTX export (plan §3.4).

Runs the full chain in the mandated order and prints ONE machine-readable JSON
result, so an LLM session never stitches the pipeline by hand:

  (a) capture-slides.js        multi-pass capture (layered) / frozen v1 (flat)
  (b) build_hybrid_pptx.py     manifest composition (layered) / v1 (flat)
  (c) compose candidate        pure PIL from captured layers (layered only)
  (d) compare_renders.py       metrics only, per slide per tier (layered only)
  (e) validate_export_objects  the single QA gate
  (f) export-result.json       pass/fail + metrics

Cache: capture is skipped when sha(capture-slides.js) + sha(html) + the pinned
Playwright version all match the previous run (--no-cache overrides). A partial
key would serve stale "ghost" renders — never trim it.

Usage:
    export_pptx.py --html <deck.html> --slides N --out-dir <dir> --output <deck.pptx>
                   [--mode layered|flat] [--showJs JS] [--selector CSS]
                   [--font NAME] [--require-font NAME] [--no-cache] [--keep-qa]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _common import SCRIPT_DIR, REPO_ROOT, sha256_file, write_json

CAPTURE = SCRIPT_DIR / "capture-slides.js"
BUILD = SCRIPT_DIR / "build_hybrid_pptx.py"
COMPARE = SCRIPT_DIR / "compare_renders.py"
VALIDATE = SCRIPT_DIR / "validate_export_objects.py"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--html", required=True, help="Deck HTML file (served via file://)")
    p.add_argument("--slides", required=True, type=int)
    p.add_argument("--out-dir", required=True, help="Capture/QA working directory")
    p.add_argument("--output", required=True, help="Output .pptx path")
    p.add_argument("--mode", choices=("layered", "flat"), default="layered")
    p.add_argument("--showJs")
    p.add_argument("--selector")
    p.add_argument("--width", type=int, default=1920,
                   help="Capture viewport/canvas width (default: 1920)")
    p.add_argument("--height", type=int, default=1080,
                   help="Capture viewport/canvas height (default: 1080)")
    p.add_argument("--overlay-scale", type=float, default=2,
                   help="Layered overlay capture scale (default: 2)")
    p.add_argument("--pad", type=int, default=96,
                   help="Transparent selection padding around overlays (default: 96)")
    p.add_argument("--font", default="Proxima Nova")
    p.add_argument("--require-font")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--keep-qa", action="store_true",
                   help="Keep QA-ephemeral renders even after a passing gate")
    p.add_argument("--allow-untagged", action="store_true",
                   help="Accept layered decks with untagged visuals (they bake into the background)")
    p.add_argument("--allow-full-bleed", action="store_true",
                   help="Accept overlays covering (almost) the whole canvas "
                        "(their contents stay glued into one picture)")
    return p.parse_args()


def playwright_version() -> str:
    pkg = REPO_ROOT / "node_modules" / "playwright" / "package.json"
    try:
        return json.loads(pkg.read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, json.JSONDecodeError):
        return "unknown"


def run(cmd: list[str], label: str) -> None:
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise SystemExit(f"[export_pptx] step failed: {label} (exit {result.returncode})")


def capture_fingerprint(args: argparse.Namespace) -> dict:
    return {
        "capture_script_sha": sha256_file(CAPTURE),
        "html_sha": sha256_file(args.html),
        "playwright": playwright_version(),
        "mode": args.mode,
        "slides": args.slides,
        "width": args.width,
        "height": args.height,
        "overlay_scale": args.overlay_scale,
        "pad": args.pad,
    }


def compose_candidates(out_dir: Path, manifest: dict) -> list[dict]:
    """Step (c): PIL-only composition from captured layers (plan §10.1)."""
    from PIL import Image

    jobs = []
    for entry in manifest["slides"]:
        nn = f"{entry['slide']:02d}"
        composed = Image.open(out_dir / entry["base"]["png"]).convert("RGBA")
        # Overlays AND native shapes interleave by z — natives compose from
        # their QA-ephemeral 1x renders (the PPTX itself holds real autoshapes).
        layers = sorted(
            [("png", ov) for ov in entry.get("objects", [])]
            + [("qa_png", nv) for nv in entry.get("natives", [])],
            key=lambda t: int(t[1].get("z", 0)))
        for png_key, item in layers:
            img = Image.open(out_dir / item[png_key]).convert("RGBA")
            b = item["bounds"]
            if img.size != (int(b["w"]), int(b["h"])):
                img = img.resize((int(b["w"]), int(b["h"])), Image.LANCZOS)
            composed.alpha_composite(img, dest=(int(b["x"]), int(b["y"])))
        tier1 = out_dir / f"slide-{nn}-composed-tier1.png"
        composed.save(tier1)

        full = composed.copy()
        full.alpha_composite(
            Image.open(out_dir / entry["qa"]["text_layer"]).convert("RGBA"), dest=(0, 0))
        tier2 = out_dir / f"slide-{nn}-composed-tier2.png"
        full.save(tier2)

        jobs.append({
            "slide": entry["slide"],
            "tier1": {"reference": out_dir / entry["qa"]["ref_notext"], "candidate": tier1},
            "tier2": {"reference": out_dir / entry["qa"]["ref_full"], "candidate": tier2},
        })
    return jobs


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    html = Path(args.html).resolve()
    if not html.exists():
        raise SystemExit(f"Deck HTML not found: {html}")
    args.html = str(html)

    result = {"mode": args.mode, "steps": {}, "pass": False}

    # (a) capture — skipped only on a FULL fingerprint match AND usable QA
    # state: either the QA renders still exist (fresh compose possible) or the
    # parity report.json files survived cleanup (verdict reusable). Without
    # either, the cache is stale and capture must re-run.
    fp = capture_fingerprint(args)
    fp_path = out_dir / ".capture-fingerprint.json"
    manifest_path = out_dir / "export-manifest.json"
    parity_dir = out_dir / "parity"
    cached = (not args.no_cache and fp_path.exists() and manifest_path.exists()
              and json.loads(fp_path.read_text(encoding="utf-8")) == fp)
    if cached and args.mode == "layered":
        prev = json.loads(manifest_path.read_text(encoding="utf-8"))
        qa_present = all((out_dir / name).exists()
                         for entry in prev["slides"]
                         for name in (list(entry.get("qa", {}).values())
                                      + [nv["qa_png"] for nv in entry.get("natives", [])
                                         if nv.get("qa_png")]))
        reports_present = bool(list(parity_dir.rglob("report.json"))) if parity_dir.exists() else False
        if not qa_present and not reports_present:
            cached = False
    if cached:
        result["steps"]["capture"] = "cached"
        print("[export_pptx] (a) capture: fingerprint match → using cached renders")
    else:
        cmd = ["node", str(CAPTURE), "--url", f"file://{html}",
               "--slides", str(args.slides), "--out-dir", str(out_dir),
               "--mode", args.mode, "--width", str(args.width),
               "--height", str(args.height),
               "--overlay-scale", str(args.overlay_scale),
               "--pad", str(args.pad)]
        if args.showJs:
            cmd += ["--showJs", args.showJs]
        if args.selector:
            cmd += ["--selector", args.selector]
        if args.require_font:
            cmd += ["--require-font", args.require_font]
        run(cmd, "(a) capture")
        write_json(fp_path, fp)
        result["steps"]["capture"] = "ran"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # (b) build
    output = Path(args.output).resolve()
    if args.mode == "layered":
        run([sys.executable, str(BUILD), "--manifest", str(manifest_path),
             "--renders", str(out_dir), "--output", str(output),
             "--font", args.font,
             "--vector-root", str(html.parent)], "(b) build layered")
    else:
        run([sys.executable, str(BUILD), "--layout", str(out_dir / "export-layout.json"),
             "--renders", str(out_dir), "--slides", str(args.slides),
             "--output", str(output), "--font", args.font], "(b) build flat (v1)")
    result["steps"]["build"] = str(output)

    # (c)+(d) compose + compare — layered only (flat has no layers to verify).
    if args.mode == "layered":
        qa_present = all((out_dir / name).exists()
                         for entry in manifest["slides"]
                         for name in (list(entry.get("qa", {}).values())
                                      + [nv["qa_png"] for nv in entry.get("natives", [])
                                         if nv.get("qa_png")]))
        if qa_present:
            jobs = compose_candidates(out_dir, manifest)
            result["steps"]["compose"] = f"{len(jobs)} slides"
            for job in jobs:
                for tier in ("tier1", "tier2"):
                    report_dir = parity_dir / f"slide-{job['slide']:02d}" / tier
                    run([sys.executable, str(COMPARE),
                         "--reference", str(job[tier]["reference"]),
                         "--candidate", str(job[tier]["candidate"]),
                         "--output-dir", str(report_dir)], f"(d) compare {tier}")
            result["steps"]["compare"] = str(parity_dir)
        else:
            # Cached run after cleanup: renders are gone by design; the kept
            # report.json metrics carry the verdict for identical inputs.
            result["steps"]["compose"] = "skipped (cached, QA renders cleaned)"
            result["steps"]["compare"] = "reusing previous report.json metrics"

    # Surface capture warnings in the result JSON — the agent reading this
    # must see untagged visuals without scrolling capture logs.
    warnings = []
    for entry in manifest.get("slides", []):
        for u in entry.get("untagged_visuals", []):
            warnings.append(f"slide {entry['slide']}: untagged <{u['tag']}> "
                            f"{u['w']}x{u['h']} baked into background")
    if warnings:
        result["warnings"] = warnings

    # (e) validate — the single gate.
    cmd = [sys.executable, str(VALIDATE), "--pptx", str(output),
           "--manifest", str(manifest_path)]
    if args.mode == "layered":
        cmd += ["--parity-dir", str(parity_dir)]
    if args.allow_untagged:
        cmd += ["--allow-untagged"]
    if args.allow_full_bleed:
        cmd += ["--allow-full-bleed"]
    gate = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    validation_path = output.with_suffix(".validation.json")
    validation = (json.loads(validation_path.read_text(encoding="utf-8"))
                  if validation_path.exists() else {"pass": False, "failures": [gate.stderr.strip()]})
    result["steps"]["validate"] = validation
    result["pass"] = gate.returncode == 0 and validation.get("pass", False)

    # QA renders are ephemeral once the gate passes (Output Discipline) — but
    # verify-render-parity.md mandates keeping the METRICS: every report.json
    # stays, only images go.
    if result["pass"] and not args.keep_qa:
        removed = 0
        for entry in manifest["slides"]:
            nn = f"{entry['slide']:02d}"
            for name in (list(entry.get("qa", {}).values())
                         + [nv["qa_png"] for nv in entry.get("natives", []) if nv.get("qa_png")]
                         + [f"slide-{nn}-composed-tier1.png", f"slide-{nn}-composed-tier2.png"]):
                target = out_dir / name
                if target.exists():
                    target.unlink()
                    removed += 1
        if parity_dir.exists():
            for evidence in parity_dir.rglob("*.png"):
                evidence.unlink()
                removed += 1
        result["steps"]["qa_cleanup"] = (f"removed {removed} ephemeral renders/evidence "
                                         "(report.json metrics kept)")

    # (f) one machine-readable result.
    write_json(out_dir / "export-result.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
