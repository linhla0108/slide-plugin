#!/usr/bin/env python3
"""Preflight a PDF, detect reusable regions, stage Drafts, and rebuild catalog data."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from _common import REPO_ROOT, ProjectPythonError, require_project_python

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "component-extractions"
DEFAULT_HISTORY = REPO_ROOT / "slide-system" / "registries" / "extraction-history.json"
DEFAULT_REGISTRY = REPO_ROOT / "slide-system" / "registries" / "visual-library.json"
DEFAULT_CATALOG = REPO_ROOT / "slide-system" / "catalog" / "catalog-data.json"
DEFAULT_MARKER = REPO_ROOT / "slide-system" / "registries" / "extract-readiness.json"


class WorkflowError(RuntimeError):
    """Raised when a workflow step fails before Draft review."""


def _run_step(name: str, cmd: list[str], runner: Callable[..., subprocess.CompletedProcess]) -> dict:
    result = runner(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        raise WorkflowError(f"{name} failed: {detail}")
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {"status": "ok"}
    except json.JSONDecodeError:
        return {"status": "ok", "output": result.stdout.strip()}


def run_workflow(*, pdf: Path, extraction_id: str, output_root: Path,
                 history: Path, registry: Path, catalog_output: Path,
                 marker: Path, python: Path,
                 pages: str | None = None,
                 runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    """Run the non-publishing PDF-to-Draft workflow in the required order."""
    python_str = str(python)
    preflight = _run_step("preflight", [
        python_str, str(SCRIPTS / "check_base_requirements.py"),
        "--input", "pdf", "--json", "--marker", str(marker),
    ], runner)

    analyze_cmd = [
        python_str, str(SCRIPTS / "analyze_with_docling.py"),
        "--source", str(pdf), "--extraction-id", extraction_id,
        "--output-root", str(output_root),
    ]
    if pages:
        analyze_cmd += ["--pages", pages]
    analysis = _run_step("analysis", analyze_cmd, runner)

    staging = _run_step("Draft staging", [
        python_str, str(SCRIPTS / "auto_stage_candidates.py"), extraction_id,
        "--output-root", str(output_root),
        "--history", str(history),
        "--registry", str(registry),
        "--no-catalog",
    ], runner)
    catalog = _run_step("catalog rebuild", [
        python_str, str(SCRIPTS / "build_component_catalog.py"),
        "--registry", str(registry),
        "--extractions", str(output_root),
        "--output", str(catalog_output),
    ], runner)
    return {
        "status": "drafts-ready",
        "python": python_str,
        "preflight": preflight,
        "analysis": analysis,
        "staging": staging,
        "catalog": catalog,
        "published": False,
        "review_url": "http://127.0.0.1:8799/slide-system/catalog/",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--extraction-id", required=True)
    parser.add_argument("--pages", help="Optional 1-based page or range, for example 1 or 2-4")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--catalog-output", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--marker", type=Path, default=DEFAULT_MARKER)
    args = parser.parse_args()

    if not args.pdf.is_file() or args.pdf.suffix.lower() != ".pdf":
        print(f"ERROR: --pdf must name an existing PDF file: {args.pdf}", file=sys.stderr)
        return 2
    try:
        python = require_project_python(REPO_ROOT, required_modules=("fitz",))
        summary = run_workflow(
            pdf=args.pdf.resolve(), extraction_id=args.extraction_id,
            output_root=args.output_root.resolve(), history=args.history.resolve(),
            registry=args.registry.resolve(), catalog_output=args.catalog_output.resolve(),
            marker=args.marker.resolve(), python=python, pages=args.pages,
        )
    except (ProjectPythonError, WorkflowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
