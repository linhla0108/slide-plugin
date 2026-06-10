#!/usr/bin/env python3
"""Preflight the base toolchain for the component-extract + HTML-preview pipeline.

Run this ONCE before starting extraction work. It probes the tools the pipeline
needs, classifies each as a blocker / warning / optional, and writes a readiness
marker at `registries/extract-readiness.json`. The marker records the environment
fingerprint, so a later run with the same environment short-circuits and does NOT
re-probe or prompt for re-install:

    python3 slide-system/scripts/check_base_requirements.py          # check / reuse marker
    python3 slide-system/scripts/check_base_requirements.py --force  # re-probe ignoring marker
    python3 slide-system/scripts/check_base_requirements.py --json   # machine-readable summary

Requirement levels:
  - required:    pipeline cannot run without it (blocker).
  - recommended: pipeline runs but skips an optimization (warning).
  - optional:    only needed by the downstream export job (deferred, no block).
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from _common import SYSTEM_ROOT, environment_fingerprint, now_iso, run_version


MARKER_PATH = SYSTEM_ROOT / "registries" / "extract-readiness.json"

# (id, level, [candidate executables], version-args, capability sentence)
REQUIREMENTS = [
    ("python3", "required", ["python3"], ["--version"],
     "Run every slide-system/scripts/ step."),
    ("xmllint", "required", ["xmllint"], ["--version"],
     "Validate that visual.svg / source-with-text.svg stay well-formed XML."),
    ("raster-optimizer", "recommended", ["sips", "magick", "convert"], ["--version"],
     "Downsample / recompress embedded rasters (optimize_svg.py). Without it the "
     "SVG is still precision-trimmed but large images are left at source size."),
    ("svg-renderer", "optional", ["rsvg-convert", "resvg", "inkscape", "cairosvg"], ["--version"],
     "Render SVG -> PNG/PDF at export time in the consuming job. Not needed to "
     "extract or preview components. Provision when you wire up export."),
    # Export tools — optional at preflight; required at job time when exporting.
    # Claude Code users: gen_pptx and playwright-pdf are built-in (no install).
    # Non-Claude users: run ./slide-system/scripts/setup.sh to install the
    # standalone deps (Node.js + Playwright, and python-pptx + Pillow). Then
    # capture-slides.js, build_hybrid_pptx.py and export-pdf.js become available.
    ("node", "optional", ["node"], ["--version"],
     "Required for standalone capture-slides.js and export-pdf.js (non-Claude "
     "path). Claude Code bundles its own Node.js; external users need Node 18+."),
]

# Repo root — two levels up from this script (scripts/ → slide-system/ → repo)
_REPO_ROOT = Path(__file__).resolve().parents[2]

def _npm_deps_installed() -> bool:
    """Return True when npm install has been run in the repo root."""
    return (_REPO_ROOT / "node_modules").is_dir()

def _standalone_script_available(rel: str) -> bool:
    return (_REPO_ROOT / rel).exists() and _npm_deps_installed()


def probe(candidates: list[str], version_args: list[str]) -> tuple[str | None, str | None]:
    for name in candidates:
        path = shutil.which(name)
        if path:
            ok, line = run_version(path, version_args)
            return path, (line if ok else f"present (version probe failed: {line})")
    return None, None


def evaluate() -> dict:
    fingerprint = environment_fingerprint(
        [shutil.which(c) for _id, _lvl, cands, _v, _d in REQUIREMENTS for c in cands]
    )
    requirements = []
    blockers: list[str] = []
    warnings: list[str] = []
    for req_id, level, candidates, version_args, capability in REQUIREMENTS:
        path, version = probe(candidates, version_args)
        available = path is not None
        requirements.append({
            "id": req_id,
            "level": level,
            "status": "available" if available else "missing",
            "path": path,
            "version": version,
            "candidates": candidates,
            "capability": capability,
        })
        if not available:
            if level == "required":
                blockers.append(f"{req_id}: install one of {candidates}")
            elif level == "recommended":
                warnings.append(f"{req_id}: install one of {candidates} for raster optimization")
    # Standalone export scripts (non-Claude path)
    standalone = []
    for script_rel, tool_id, label in [
        ("slide-system/scripts/capture-slides.js",    "capture-slides",    "capture-slides.js"),
        ("slide-system/scripts/build_hybrid_pptx.py", "build-hybrid-pptx", "build_hybrid_pptx.py"),
        ("slide-system/scripts/export-pdf.js",        "playwright-pdf",    "export-pdf.js"),
    ]:
        ok = _standalone_script_available(script_rel)
        standalone.append({
            "id": tool_id,
            "label": label,
            "status": "available" if ok else "not-installed",
            "install_hint": "Run ./slide-system/scripts/setup.sh (requires Node.js 18+)",
        })

    return {
        "schema_version": 1,
        "status": "blocked" if blockers else "ready",
        "environment_fingerprint": fingerprint,
        "checked_at": now_iso(),
        "requirements": requirements,
        "blockers": blockers,
        "warnings": warnings,
        "standalone_export_scripts": standalone,
    }


def load_marker() -> dict | None:
    if MARKER_PATH.exists():
        try:
            return json.loads(MARKER_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def write_marker(result: dict) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def print_summary(result: dict, reused: bool) -> None:
    tag = "REUSED marker" if reused else "checked"
    print(f"[extract-preflight] {result['status'].upper()} ({tag}) — {MARKER_PATH.name}")
    for req in result["requirements"]:
        mark = "OK " if req["status"] == "available" else "-- "
        print(f"  [{mark}] {req['level']:<11} {req['id']:<17} {req['version'] or req['status']}")
    for blocker in result["blockers"]:
        print(f"  BLOCKER: {blocker}")
    for warning in result["warnings"]:
        print(f"  warning: {warning}")
    # Standalone export scripts (non-Claude path)
    sa = result.get("standalone_export_scripts", [])
    if sa:
        print(f"  --- standalone export scripts (non-Claude path) ---")
        for s in sa:
            mark = "OK " if s["status"] == "available" else "-- "
            hint = "" if s["status"] == "available" else f"  ← {s['install_hint']}"
            print(f"  [{mark}] optional     {s['id']:<17} {s['status']}{hint}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-probe even if a matching marker exists")
    parser.add_argument("--json", action="store_true", help="Print the readiness JSON only")
    args = parser.parse_args()

    current_fp = environment_fingerprint(
        [shutil.which(c) for _id, _lvl, cands, _v, _d in REQUIREMENTS for c in cands]
    )
    marker = load_marker()
    reused = (
        not args.force
        and marker is not None
        and marker.get("environment_fingerprint") == current_fp
        and marker.get("status") == "ready"
    )

    result = marker if reused else evaluate()
    if not reused:
        write_marker(result)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_summary(result, reused)

    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
