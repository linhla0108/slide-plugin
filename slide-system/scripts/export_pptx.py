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
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _common import (
    SCRIPT_DIR,
    REPO_ROOT,
    ProjectPythonError,
    load_json,
    require_project_python,
    sha256_file,
    write_json,
)

CAPTURE = SCRIPT_DIR / "capture-slides.js"
BUILD = SCRIPT_DIR / "build_hybrid_pptx.py"
COMPARE = SCRIPT_DIR / "compare_renders.py"
VALIDATE = SCRIPT_DIR / "validate_export_objects.py"
THRESHOLDS = REPO_ROOT / "slide-system" / "registries" / "export-qa-thresholds.json"
EXPORT_PDF = SCRIPT_DIR / "export-pdf.js"
VALIDATE_SELECTION = SCRIPT_DIR / "validate_selection_report.py"
VALIDATE_STAGE = SCRIPT_DIR / "validate_deck_stage_runtime.py"
VALIDATE_BRAND = SCRIPT_DIR / "validate_brand_compliance.py"
VALIDATE_FIDELITY = SCRIPT_DIR / "validate_component_fidelity.py"
VALIDATE_SLOT_PLAN = SCRIPT_DIR / "validate_slot_content_plan.py"
VALIDATE_ASSETS = SCRIPT_DIR / "validate_deck_assets.py"
BRAND_MANIFEST = REPO_ROOT / "slide-system" / "brand-packs" / "sun-studio" / "manifest.json"
PARITY_FINGERPRINT = ".parity-fingerprint.json"

# What "editable" actually means per mode, so the output contract cannot be
# read as "every shape is editable in PowerPoint".
EDITABILITY_TIERS = {
    "layered": {
        "tier": "text-editable",
        "text": "native PowerPoint text boxes",
        "graphics": "rasterised background image per slide",
        "limitation": ("Visual elements (cards, badges, rules, artwork) are baked into the "
                       "slide background PNG and cannot be moved or restyled in PowerPoint. "
                       "Only text is editable."),
    },
    "flat": {
        "tier": "image-only",
        "text": "rasterised",
        "graphics": "rasterised full-slide image",
        "limitation": "Nothing is editable; each slide is a single image.",
    },
}

# MediaBox is `[llx lly urx ury]`; the last two are the page size in points.
MEDIABOX_RE = re.compile(rb"/MediaBox\s*\[\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s*\]")
PDF_PAGE_RE = re.compile(rb"/Type\s*/Page[^s]")


PDF_HISTORY = ".pdf-deliverables.json"
SUPERSEDED_DIR = "superseded"


def quarantine_superseded_pdfs(run_dir: Path, canonical: Path,
                               out_dir: Path) -> tuple[list[str], list[str]]:
    """Leave exactly one PDF in the run directory. Never delete anything.

    A run directory holding several PDFs is a delivery hazard — the reader
    cannot tell the canonical artifact from a superseded one, and last time
    that shipped a 1-page file under the name the contract advertised.

    PDFs THIS job emitted before (tracked in `.pdf-deliverables.json`) are
    moved into `superseded/`; they are ours to tidy. Anything else is someone
    else's file: it is reported so the caller can fail the delivery, never
    moved or removed. Returns (quarantined, foreign).
    """
    history_path = out_dir / PDF_HISTORY
    try:
        history = set(json.loads(history_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        history = set()
    history.add(canonical.name)
    write_json(history_path, sorted(history))

    quarantined: list[str] = []
    foreign: list[str] = []
    for pdf in sorted(run_dir.glob("*.pdf")):
        if pdf.resolve() == canonical.resolve():
            continue
        if pdf.name in history:
            target = run_dir / SUPERSEDED_DIR
            target.mkdir(exist_ok=True)
            shutil.move(str(pdf), str(target / pdf.name))
            quarantined.append(str(target / pdf.name))
        else:
            foreign.append(pdf.name)
    return quarantined, foreign


def pdf_geometry(pdf: Path) -> tuple[int, tuple[float, float]]:
    """(page count, (width_pt, height_pt)) read straight from the PDF bytes.

    Deliberately dependency-free: the exporter must be able to prove the
    geometry of what it just produced without importing a PDF library.
    """
    blob = pdf.read_bytes()
    pages = len(PDF_PAGE_RE.findall(blob))
    boxes = {(round(float(m[2]) - float(m[0]), 2), round(float(m[3]) - float(m[1]), 2))
             for m in MEDIABOX_RE.findall(blob)}
    return pages, (max(boxes) if boxes else (0.0, 0.0))


def selected_python(required_modules: tuple[str, ...] = ()) -> Path:
    return require_project_python(REPO_ROOT, required_modules=required_modules)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--html", required=True, help="Deck HTML file (served via file://)")
    p.add_argument("--slides", required=True, type=int)
    p.add_argument("--out-dir", required=True, help="Capture/QA working directory")
    p.add_argument("--output", required=True, help="Output .pptx path")
    p.add_argument("--pdf-output", default=None,
                   help="Also export the canonical PDF here and verify its geometry")
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


def generation_gate_commands(html: Path) -> list[tuple[list[str], str]]:
    """Return required pre-export gates for a normal slide-job run.

    Standalone HTML exports intentionally have no job analysis folder and keep
    the existing export-only path. A generated job, however, must prove its
    scorer decision, runtime scaling, brand rules, and reused-component
    fidelity before capture can produce a PPTX.
    """
    analysis_dir = html.parent / "analysis"
    report = analysis_dir / "selection-report.json"
    if not report.is_file():
        return []

    python = str(selected_python())
    commands: list[tuple[list[str], str]] = [
        ([python, str(VALIDATE_SELECTION), "--selection-report", str(report)], "selection report"),
        ([python, str(VALIDATE_ASSETS), "--html", str(html), "--out",
          str(html.parent / "qa" / "deck-assets-report.json")], "deck asset resolution"),
        ([python, str(VALIDATE_STAGE), "--html", str(html)], "deck stage runtime"),
        ([
            python, str(VALIDATE_BRAND), "--html", str(html),
            "--selection-report", str(report), "--brand-pack", str(BRAND_MANIFEST),
        ], "brand compliance"),
        ([
            python, str(VALIDATE_FIDELITY), "--html", str(html),
            "--selection-report", str(report), "--registry",
            str(REPO_ROOT / "slide-system" / "registries" / "visual-library.json"),
        ], "component fidelity"),
    ]
    report_data = load_json(report)
    report_entries = report_data.get("slides", []) if isinstance(report_data.get("slides"), list) else [report_data]
    has_reuse = any(
        (entry.get("decision") or {}).get("action") == "reuse"
        for entry in report_entries if isinstance(entry, dict)
    )
    if has_reuse:
        plan = analysis_dir / "slot-content-plan.json"
        commands.insert(1, ([
            python, str(VALIDATE_SLOT_PLAN), "--plan", str(plan),
            "--selection-report", str(report), "--out",
            str(html.parent / "qa" / "slot-content-plan-report.json"),
        ], "slot content capacity"))
        commands[-1][0].extend(["--slot-content-plan", str(plan)])
    requests = analysis_dir / "visual-requests.json"
    if requests.is_file():
        commands[0][0].extend(["--visual-requests", str(requests)])
    return commands


def run_generation_gates(html: Path) -> bool:
    commands = generation_gate_commands(html)
    for command, label in commands:
        run(command, label)
    return bool(commands)


def selection_identity(html: str | Path) -> list | None:
    """Stable identity of the selection inputs behind this deck, or None.

    `html_sha` alone does not bound a run: a diagnostic re-score (for example
    with `--reject-item`) can change which published items were chosen and
    which were excluded while leaving byte-identical deck HTML — and the cached
    capture, parity reports and gate verdicts would then be reused under
    selection inputs they were never produced for.

    Only the DECISION identity is fingerprinted — the per-slide (request_id,
    action, item_id) plus `rejected_items`. Hashing the report file instead
    would fold in `generated_at`, so every re-score would invalidate the cache
    and the reuse path would be dead code rather than merely conservative.
    """
    report_path = Path(html).parent / "analysis" / "selection-report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # An unreadable report must not silently authorise cache reuse.
        return ["unreadable-selection-report"]
    entries = report.get("slides")
    if not isinstance(entries, list):
        entries = [report]
    decisions = []
    for entry in entries:
        decision = entry.get("decision") or {}
        decisions.append([
            entry.get("request_id"),
            decision.get("action"),
            decision.get("item_id"),
        ])
    return [decisions, sorted(report.get("rejected_items") or [])]


def capture_fingerprint(args: argparse.Namespace) -> dict:
    return {
        "capture_script_sha": sha256_file(CAPTURE),
        "html_sha": sha256_file(args.html),
        # Inherited by qa_fingerprint(), so a changed selection invalidates both
        # capture reuse and parity-report reuse from this one place.
        "selection": selection_identity(args.html),
        "playwright": playwright_version(),
        "mode": args.mode,
        "slides": args.slides,
        "width": args.width,
        "height": args.height,
        "overlay_scale": args.overlay_scale,
        "pad": args.pad,
    }


def qa_fingerprint(args: argparse.Namespace) -> dict:
    return {
        **capture_fingerprint(args),
        "export_script_sha": sha256_file(__file__),
        "compare_script_sha": sha256_file(COMPARE),
        "validator_script_sha": sha256_file(VALIDATE),
        "thresholds_sha": sha256_file(THRESHOLDS),
    }


def expected_parity_reports(parity_dir: Path, manifest: dict) -> list[Path]:
    return [
        parity_dir / f"slide-{int(entry['slide']):02d}" / tier / "report.json"
        for entry in manifest.get("slides", [])
        for tier in ("tier1", "tier2")
    ]


def write_parity_fingerprint(parity_dir: Path, manifest: dict, fingerprint: dict) -> None:
    reports = expected_parity_reports(parity_dir, manifest)
    if not all(path.is_file() for path in reports):
        raise RuntimeError("cannot fingerprint incomplete parity reports")
    write_json(parity_dir.parent / PARITY_FINGERPRINT, {
        "fingerprint": fingerprint,
        "reports": [
            {
                "path_parts": list(path.relative_to(parity_dir).parts),
                "sha256": sha256_file(path),
            }
            for path in reports
        ],
    })


def parity_cache_valid(parity_dir: Path, manifest: dict, fingerprint: dict) -> bool:
    marker = parity_dir.parent / PARITY_FINGERPRINT
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("fingerprint") != fingerprint:
        return False

    expected = expected_parity_reports(parity_dir, manifest)
    expected_parts = {path.relative_to(parity_dir).parts for path in expected}
    actual_parts = {path.relative_to(parity_dir).parts for path in parity_dir.rglob("report.json")}
    records = {
        tuple(record.get("path_parts", [])): record.get("sha256")
        for record in payload.get("reports", [])
    }
    if actual_parts != expected_parts or set(records) != expected_parts:
        return False
    return all(path.is_file() and sha256_file(path) == records[path.relative_to(parity_dir).parts]
               for path in expected)


def invalidate_stale_artifacts(out_dir: Path, output: Path, capture_stale: bool) -> None:
    for path in (out_dir / "export-result.json", output.with_suffix(".validation.json")):
        path.unlink(missing_ok=True)
    if not capture_stale:
        return
    for name in (".capture-fingerprint.json", PARITY_FINGERPRINT, "export-manifest.json"):
        (out_dir / name).unlink(missing_ok=True)
    parity_dir = out_dir / "parity"
    if parity_dir.exists():
        shutil.rmtree(parity_dir)


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
    output = Path(args.output).resolve()

    result = {"mode": args.mode, "steps": {}, "pass": False}

    # A failing step raises SystemExit, which used to leave the run with no
    # machine-readable evidence at all — indistinguishable from "never ran".
    # Every exit now lands an export-result.json carrying pass:false.
    try:
        return _run_export(args, out_dir, html, output, result)
    except SystemExit as exc:
        result["pass"] = False
        result.setdefault("failures", []).append(str(exc))
        write_json(out_dir / "export-result.json", result)
        raise


def _run_export(args, out_dir: Path, html: Path, output: Path, result: dict) -> int:
    if run_generation_gates(html):
        result["steps"]["generation_gates"] = "passed"

    # (a) capture — skipped only on a FULL fingerprint match AND usable QA
    # state: either the QA renders still exist (fresh compose possible) or the
    # parity report.json files survived cleanup (verdict reusable). Without
    # either, the cache is stale and capture must re-run.
    fp = capture_fingerprint(args)
    fp_path = out_dir / ".capture-fingerprint.json"
    manifest_path = out_dir / "export-manifest.json"
    parity_dir = out_dir / "parity"
    try:
        prev_fp = json.loads(fp_path.read_text(encoding="utf-8"))
        prev = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        prev_fp, prev = None, None
    cached = not args.no_cache and prev_fp == fp and prev is not None
    if cached and args.mode == "layered" and prev is not None:
        qa_present = all((out_dir / name).exists()
                         for entry in prev["slides"]
                         for name in (list(entry.get("qa", {}).values())
                                      + [nv["qa_png"] for nv in entry.get("natives", [])
                                         if nv.get("qa_png")]))
        reports_reusable = parity_cache_valid(parity_dir, prev, qa_fingerprint(args))
        if not qa_present and not reports_reusable:
            cached = False
    invalidate_stale_artifacts(out_dir, output, capture_stale=not cached)
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

    # (a2) render legibility — the capture is the first artifact that knows what
    # the deck actually looks like. Reusing a published component only counts if
    # the result is readable: no copy overlapping its neighbour, no text on a
    # background it cannot be seen against, no overlay placed off the canvas.
    # Standalone HTML exports have no job analysis folder and keep the
    # export-only path, matching generation_gate_commands().
    if (html.parent / "analysis" / "selection-report.json").is_file():
        run([str(selected_python()), str(VALIDATE_FIDELITY),
             "--export-manifest", str(manifest_path), "--renders", str(out_dir)],
            "(a2) render legibility")
        result["steps"]["render_legibility"] = "passed"

    # (b) build
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
            if parity_dir.exists():
                shutil.rmtree(parity_dir)
            (out_dir / PARITY_FINGERPRINT).unlink(missing_ok=True)
            jobs = compose_candidates(out_dir, manifest)
            result["steps"]["compose"] = f"{len(jobs)} slides"
            for job in jobs:
                for tier in ("tier1", "tier2"):
                    report_dir = parity_dir / f"slide-{job['slide']:02d}" / tier
                    run([sys.executable, str(COMPARE),
                         "--reference", str(job[tier]["reference"]),
                         "--candidate", str(job[tier]["candidate"]),
                         "--output-dir", str(report_dir)], f"(d) compare {tier}")
            write_parity_fingerprint(parity_dir, manifest, qa_fingerprint(args))
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
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        detail = gate.stderr.strip() or gate.stdout.strip() or "validator produced no current report"
        validation = {"pass": False, "failures": [detail]}
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

    # (f) canonical deliverables. The PPTX is layered: native editable text on
    # a rasterised background, NOT fully editable vector shapes. Recording the
    # tier here stops a downstream reader from promising more than we ship.
    result["editability"] = EDITABILITY_TIERS[args.mode]
    deliverables = {"pptx": str(output)}
    if result["pass"] and args.pdf_output:
        pdf = Path(args.pdf_output).resolve()
        run(["node", str(EXPORT_PDF), "--url", f"file://{html}",
             "--slides", str(args.slides), "--showJs", args.showJs or "goToSlide({n})",
             "--width", str(args.width), "--height", str(args.height),
             "--output", str(pdf)], "(f) pdf")
        pages, box = pdf_geometry(pdf)
        result["steps"]["pdf"] = {
            "path": str(pdf), "pages": pages,
            "page_width_pt": box[0], "page_height_pt": box[1],
            "landscape": box[0] > box[1],
        }
        problems = []
        if pages != args.slides:
            problems.append(f"PDF has {pages} page(s), expected {args.slides}")
        if not box[0] > box[1]:
            problems.append(f"PDF page {box[0]}x{box[1]}pt is not landscape")
        if problems:
            result["pass"] = False
            result.setdefault("failures", []).extend(problems)
        else:
            deliverables["pdf"] = str(pdf)
    result["deliverables"] = deliverables

    if "pdf" in deliverables:
        quarantined, foreign = quarantine_superseded_pdfs(
            output.parent, Path(deliverables["pdf"]), out_dir)
        if quarantined:
            result["steps"]["superseded_pdfs"] = quarantined
        if foreign:
            # Never touch a file this job did not create — but never call the
            # delivery successful while the run directory is ambiguous either.
            result["pass"] = False
            result.setdefault("failures", []).append(
                "Ambiguous PDF delivery: unrecognised PDF(s) alongside the "
                f"canonical artifact: {', '.join(foreign)}. Remove or rename "
                "them, then re-run.")

    # (g) one machine-readable result.
    write_json(out_dir / "export-result.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    try:
        python = selected_python(("pptx", "PIL"))
    except ProjectPythonError as exc:
        raise SystemExit(f"[export_pptx] {exc}") from exc
    if Path(sys.executable).resolve() != python.resolve():
        raise SystemExit(subprocess.run(
            [str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=REPO_ROOT,
        ).returncode)
    raise SystemExit(main())
