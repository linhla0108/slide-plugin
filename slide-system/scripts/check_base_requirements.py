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
  - required:     pipeline cannot run without it (blocker).
  - recommended:  pipeline runs but skips an optimization (warning).
  - optional:     only needed by the downstream export job (deferred, no block).
  - input-scoped: source-to-SVG providers (PyMuPDF for PDF, LibreOffice for
                  PPTX). Recorded in the marker under `source_providers` with a
                  warning when missing, but NEVER a global blocker — jobs whose
                  input is already SVG do not need them. A job that must
                  normalize that input type treats the matching missing
                  provider as its own blocker.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _common import SYSTEM_ROOT, environment_fingerprint, now_iso, run_version


MARKER_PATH = SYSTEM_ROOT / "registries" / "extract-readiness.json"

# Bump when the marker shape changes so stale markers are re-evaluated.
SCHEMA_VERSION = 2

# (id, level, [candidate executables], version-args, capability sentence)
REQUIREMENTS = [
    ("python3", "required", ["python3"], ["--version"],
     "Run every slide-system/scripts/ step."),
    ("xmllint", "required", ["xmllint", r"C:\msys64\usr\bin\xmllint.exe"], ["--version"],
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

# Source-to-SVG providers (REQUIREMENTS.md allowed-library policy). These are
# input-type-scoped: missing ones never block jobs whose input is already SVG,
# but they DO block jobs that need to normalize that input type first.
# Install goes into the repo-local .venv — PEP 668 (Homebrew/Debian) blocks
# `pip install` into the system interpreter, so the venv is the portable path.
_PDF_INSTALL_HINT = (
    "python3 -m venv .venv && .venv/bin/pip install PyMuPDF "
    "(or run ./slide-system/scripts/setup.sh)"
)
_SOFFICE_CANDIDATES = [
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
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


def _venv_python() -> Path:
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python3"
    return _REPO_ROOT / ".venv" / sub


def probe_fitz() -> tuple[str | None, str | None, str | None]:
    """Locate PyMuPDF: current interpreter first, then the repo-local .venv.

    Returns (python_executable, fitz_module_path, version). The executable is
    what downstream conversion steps must invoke — system pythons are often
    PEP 668 externally-managed, so the install lands in <repo>/.venv instead.
    """
    try:
        spec = importlib.util.find_spec("fitz")
    except (ImportError, ValueError):
        spec = None
    if spec is not None and spec.origin is not None:
        try:
            import fitz  # noqa: PLC0415 — version is best-effort, availability is the probe

            version = f"PyMuPDF {fitz.pymupdf_version}"
        except Exception:
            version = "present (version unavailable)"
        return sys.executable, spec.origin, version

    venv_python = _venv_python()
    if venv_python.exists():
        try:
            result = subprocess.run(
                [str(venv_python), "-c",
                 "import fitz; print(fitz.__file__); print(fitz.pymupdf_version)"],
                check=False, capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            module_path = lines[0] if lines else str(venv_python)
            version = f"PyMuPDF {lines[1]} (.venv)" if len(lines) > 1 else "present (.venv)"
            return str(venv_python), module_path, version
    return None, None, None


def probe_source_providers() -> list[dict]:
    fitz_python, fitz_path, fitz_version = probe_fitz()
    soffice_path, soffice_version = probe(_SOFFICE_CANDIDATES, ["--version"])
    return [
        {
            "id": "pdf-provider",
            "level": "input-scoped",
            "input_types": ["pdf", "pptx"],
            "provider": "PyMuPDF (fitz)",
            "status": "available" if fitz_path else "missing",
            "python": fitz_python,
            "path": fitz_path,
            "version": fitz_version,
            "install_hint": _PDF_INSTALL_HINT,
            "capability": "Convert PDF pages to text-preserving source.svg "
                          "(page.get_svg_image) and reference.png (page.get_pixmap). "
                          "The only approved PDF->SVG provider per REQUIREMENTS.md. "
                          "Blocks PDF/PPTX-sourced jobs only; SVG-package jobs are unaffected. "
                          "Run conversion steps with the interpreter recorded in `python` "
                          "(may be the repo-local .venv, not the system python3).",
        },
        {
            "id": "pptx-provider",
            "level": "input-scoped",
            "input_types": ["pptx"],
            "provider": "LibreOffice (soffice --headless)",
            "status": "available" if soffice_path else "missing",
            "path": soffice_path,
            "version": soffice_version,
            "install_hint": "brew install --cask libreoffice",
            "capability": "Convert PPTX to PDF before the PyMuPDF PDF->SVG step "
                          "(also needs pdf-provider). Blocks PPTX-sourced jobs only.",
        },
    ]


def fingerprint_paths() -> list[str | None]:
    """Every path whose presence affects readiness — base tools plus source providers."""
    paths: list[str | None] = [
        shutil.which(c) for _id, _lvl, cands, _v, _d in REQUIREMENTS for c in cands
    ]
    _python, fitz_path, _version = probe_fitz()
    paths.append(fitz_path)
    paths.extend(shutil.which(c) for c in _SOFFICE_CANDIDATES)
    return paths


def evaluate() -> dict:
    fingerprint = environment_fingerprint(fingerprint_paths())
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

    # Source-to-SVG providers — input-type-scoped, never global blockers.
    source_providers = probe_source_providers()
    for provider in source_providers:
        if provider["status"] == "missing":
            warnings.append(
                f"{provider['id']}: missing — blocks "
                f"{'/'.join(provider['input_types'])} input only; "
                f"install with: {provider['install_hint']}"
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked" if blockers else "ready",
        "environment_fingerprint": fingerprint,
        "checked_at": now_iso(),
        "requirements": requirements,
        "source_providers": source_providers,
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
    # Source-to-SVG providers (input-type-scoped — never global blockers)
    providers = result.get("source_providers", [])
    if providers:
        print(f"  --- source-to-SVG providers (input-type-scoped) ---")
        for p in providers:
            mark = "OK " if p["status"] == "available" else "-- "
            detail = p["version"] if p["status"] == "available" else f"missing  ← {p['install_hint']}"
            print(f"  [{mark}] {p['level']:<11} {p['id']:<17} {detail}")
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
    parser.add_argument("--input", action="append", choices=["pdf", "pptx"],
                        help="Input type the upcoming job must normalize; the matching "
                             "source provider becomes a blocker for this invocation")
    args = parser.parse_args()

    current_fp = environment_fingerprint(fingerprint_paths())
    marker = load_marker()
    reused = (
        not args.force
        and marker is not None
        and marker.get("schema_version") == SCHEMA_VERSION
        and marker.get("environment_fingerprint") == current_fp
        and marker.get("status") == "ready"
    )

    result = marker if reused else evaluate()
    if not reused:
        write_marker(result)

    # Per-invocation input gate: a missing source provider blocks ONLY when the
    # upcoming job declared that input type. Never written into the marker.
    input_types = set(args.input or [])
    input_blockers = [
        f"{p['id']}: required for {'/'.join(sorted(input_types & set(p['input_types'])))} "
        f"input — install with: {p['install_hint']}"
        for p in result.get("source_providers", [])
        if p["status"] == "missing" and input_types & set(p["input_types"])
    ]

    if args.json:
        payload = dict(result)
        if input_types:
            payload["input_gate"] = {
                "input_types": sorted(input_types),
                "status": "blocked" if input_blockers else "ready",
                "blockers": input_blockers,
            }
        print(json.dumps(payload, indent=2))
    else:
        print_summary(result, reused)
        for blocker in input_blockers:
            print(f"  BLOCKER (input gate): {blocker}")

    return 1 if result["status"] == "blocked" or input_blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
