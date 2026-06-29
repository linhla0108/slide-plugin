#!/usr/bin/env python3
"""Auto-stage Docling candidates as catalog Draft items.

This is the automation bridge from the Docling analysis pre-step to the existing
Draft review/publish surface:

  analysis/candidate-extraction-request.json
      -> deterministic semantic metadata
      -> approved single-item extraction requests
      -> scaffold_extraction.py
      -> optional core PDF artifact build
      -> catalog Drafts

It never publishes and never writes the shared registry. Publish remains a
human click from the Draft card.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _common import REPO_ROOT, load_json, resolve_repo_path, write_json

import candidate_review as cr
import scaffold_extraction as scaffold


SCRIPT_DIR = Path(__file__).resolve().parent
STOPWORDS = {
    "a", "an", "and", "by", "candidate", "detected", "docling", "draft",
    "for", "from", "in", "of", "on", "or", "region", "the", "this", "to",
    "with",
}
LABEL_COMPONENT_TYPE = {
    "picture": "visual",
    "figure": "visual",
    "table": "table",
    "chart": "chart",
    "form": "form",
}


class AutoStageError(Exception):
    """Auto-stage request cannot be completed safely."""


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _tokens(*values: object, limit: int = 7) -> list[str]:
    out: list[str] = []
    for value in values:
        for raw in re.findall(r"[A-Za-z0-9]+", str(value or "").lower()):
            if raw in STOPWORDS or len(raw) < 2:
                continue
            if raw not in out:
                out.append(raw)
            if len(out) >= limit:
                return out
    return out


def semantic_item_id(source_path: str, item: dict, used: set[str]) -> str:
    label = str(item.get("item_id", "")).split("-", 1)[0] or "visual"
    source_stem = Path(source_path).stem
    intent = " ".join(str(v) for v in item.get("semantic_intent", []))
    notes = item.get("notes", "")
    parts = _tokens(source_stem, intent, notes, label)
    if label not in parts:
        parts.append(label)
    base = slug("-".join(parts)) or "detected-visual"
    # Make sure the generated id passes the same scaffold gate as human names.
    if scaffold._BANNED_ID.match(base) or scaffold._DOCLING_DRAFT_ID.match(base):
        base = f"{slug(source_stem) or 'source'}-{label}-visual"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def metadata_for(source_path: str, item: dict, item_id: str) -> dict:
    label = str(item.get("item_id", "")).split("-", 1)[0] or "visual"
    component_type = LABEL_COMPONENT_TYPE.get(label, label)
    intent_values = [
        str(v).strip()
        for v in item.get("semantic_intent", [])
        if str(v).strip()
    ] or [f"{component_type} from {Path(source_path).stem}"]
    keywords = _tokens(Path(source_path).stem, " ".join(intent_values), label, limit=8)
    tags = [component_type, label, "docling", "auto-staged"]
    display = item_id.replace("-", " ").title()
    return {
        "item_id": item_id,
        "display_name": display,
        "requested_type": item.get("requested_type", "component"),
        "component_type": component_type,
        "layout_role": f"detected {component_type} region",
        "visual_summary": (
            f"Auto-staged {component_type} candidate from {Path(source_path).name}, "
            f"page {item.get('slide_or_page')}."
        ),
        "semantic_intent": intent_values,
        "content_structure": [component_type, "detected region"],
        "tags": tags,
        "keywords": keywords or [component_type],
        "use_cases": [f"Review and publish this {component_type} as a reusable Draft component."],
        "anti_use_cases": ["Do not use before the Draft preview and metadata are reviewed."],
        "quality_notes": "Auto-generated metadata; final approval happens in Draft.",
        "retrieval_notes": "Generated from Docling label, source name, page, and detected text.",
    }


def _run_script(args: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    return proc.returncode == 0, (output + ("\n" + error if error else "")).strip()


def _scaffold_request(request_path: Path, output_root: Path, history: Path,
                      registry: Path) -> None:
    old_argv = sys.argv[:]
    sys.argv = [
        "scaffold_extraction.py",
        "--request", str(request_path),
        "--output-root", str(output_root),
        "--history", str(history),
        "--registry", str(registry),
    ]
    try:
        scaffold.main()
    finally:
        sys.argv = old_argv


def _augment_mapping(item_dir: Path, review: dict, run_id: str,
                     original_item: dict) -> None:
    mapping_path = item_dir / "mapping.json"
    mapping = load_json(mapping_path)
    mapping["name"] = review["display_name"]
    mapping["component_type"] = review["component_type"]
    mapping["layout_role"] = review["layout_role"]
    mapping["visual_summary"] = review["visual_summary"]
    mapping["content_structure"] = review["content_structure"]
    mapping["tags"] = review["tags"]
    mapping["keywords"] = review["keywords"]
    mapping["use_cases"] = review["use_cases"]
    mapping["anti_use_cases"] = review["anti_use_cases"]
    mapping["quality_notes"] = review["quality_notes"]
    mapping["retrieval_notes"] = review["retrieval_notes"]
    mapping.setdefault("source", {})
    mapping["source"]["candidate_id"] = review["candidate_id"]
    mapping["source"]["docling_run_id"] = run_id
    mapping["source"]["docling_label"] = str(original_item.get("item_id", "")).split("-", 1)[0]
    mapping["review"] = {
        "mode": "auto-staged",
        "status": "draft_final_review_required",
        "review_surface": "catalog Draft",
    }
    write_json(mapping_path, mapping)


def _build_pdf_artifacts(item_dir: Path, source_path: str, page: int | str) -> tuple[str, str]:
    source = resolve_repo_path(source_path)
    if source.suffix.lower() != ".pdf":
        return "skipped", "Core artifact build currently supports PDF sources."
    commands = [
        ["slide-system/scripts/convert_pdf_source.py", "--pdf", str(source), "--page", str(page), "--item-dir", str(item_dir)],
        ["slide-system/scripts/extract_editable_text_slots.py", "--item-dir", str(item_dir)],
        ["slide-system/scripts/crop_svg_region.py", "--item-dir", str(item_dir)],
        ["slide-system/scripts/externalize_svg_images.py", "--batch", str(item_dir.parents[1])],
        ["slide-system/scripts/optimize_svg.py", "--batch", str(item_dir.parents[1])],
        ["slide-system/scripts/apply_text_contract.py", "--batch", str(item_dir.parents[1])],
        ["slide-system/scripts/validate_text_slots.py", "--item-dir", str(item_dir)],
        ["slide-system/scripts/generate_item_preview.py", "--item-dir", str(item_dir)],
    ]
    logs: list[str] = []
    for cmd in commands:
        ok, log = _run_script(cmd)
        logs.append(f"{Path(cmd[0]).name}: {'ok' if ok else 'failed'}")
        if log:
            logs.append(log)
        if not ok:
            return "failed", "\n".join(logs)
    return "ready", "\n".join(logs)


def stage_run(
    extraction_id: str,
    *,
    root: Path | None = None,
    output_root: Path | None = None,
    history: Path | None = None,
    registry: Path | None = None,
    rebuild_catalog: bool = True,
    build_artifacts: bool = True,
) -> dict:
    """Auto-stage every non-rejected Docling candidate in one analysis run."""
    root = (root or cr.extractions_root()).resolve()
    output_root = (output_root or cr.extractions_root()).resolve()
    history = (history or (REPO_ROOT / "slide-system/registries/extraction-history.json")).resolve()
    registry = (registry or (REPO_ROOT / "slide-system/registries/visual-library.json")).resolve()
    adir = cr._analysis_dir(extraction_id, root)
    request = cr._load_request(adir)
    source_path = request.get("source_path", "")
    used_ids: set[str] = set()
    summary = {
        "extraction_id": extraction_id,
        "source_path": source_path,
        "staged": 0,
        "skipped": 0,
        "items": [],
    }
    items_by_id = {item.get("item_id"): item for item in request.get("items", [])}
    for original_id, item in items_by_id.items():
        if not original_id:
            continue
        existing = (cr._load_reviews(adir).get(original_id) or {})
        if existing.get("review_status") == "rejected":
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "status": "skipped",
                "reason": "candidate rejected",
            })
            continue
        item_id = semantic_item_id(source_path, item, used_ids)
        metadata = metadata_for(source_path, item, item_id)
        review = cr.save_review(extraction_id, original_id, metadata,
                                reviewer="auto-stage", root=root)
        result = cr.approve(extraction_id, original_id, reviewer="auto-stage", root=root)
        request_path = root / result["approved_request_path"]
        if not request_path.exists():
            request_path = Path(result["approved_request_path"])
        approved_request = load_json(request_path)
        staged_extraction_id = approved_request["extraction_id"]
        item_dir = output_root / staged_extraction_id / "items" / review["item_id"]
        if (item_dir / "mapping.json").is_file():
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "item_id": review["item_id"],
                "extraction_id": staged_extraction_id,
                "item_dir": str(item_dir),
                "status": "already_staged",
            })
            continue
        _scaffold_request(request_path, output_root, history, registry)
        _augment_mapping(item_dir, review, extraction_id, item)
        artifact_status = "skipped"
        artifact_log = ""
        if build_artifacts:
            artifact_status, artifact_log = _build_pdf_artifacts(
                item_dir, source_path, item.get("slide_or_page", 1))
        summary["staged"] += 1
        summary["items"].append({
            "candidate_id": original_id,
            "item_id": review["item_id"],
            "stable_id": load_json(item_dir / "mapping.json")["candidate_stable_id"],
            "extraction_id": staged_extraction_id,
            "item_dir": str(item_dir),
            "artifact_status": artifact_status,
            "artifact_log": artifact_log,
        })
    if rebuild_catalog:
        ok, log = _run_script(["slide-system/scripts/build_component_catalog.py"])
        summary["catalog_rebuilt"] = ok
        if log:
            summary["catalog_log"] = log
    return summary


def list_runs() -> list[dict]:
    return cr.list_runs()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extraction_id", help="Docling analysis run to auto-stage.")
    parser.add_argument("--output-root", default=str(cr.extractions_root()))
    parser.add_argument("--history", default=str(REPO_ROOT / "slide-system/registries/extraction-history.json"))
    parser.add_argument("--registry", default=str(REPO_ROOT / "slide-system/registries/visual-library.json"))
    parser.add_argument("--no-artifacts", action="store_true",
                        help="Only scaffold Draft folders; do not run the PDF artifact chain.")
    parser.add_argument("--no-catalog", action="store_true",
                        help="Do not rebuild catalog-data.json after staging.")
    args = parser.parse_args(argv)
    try:
        summary = stage_run(
            args.extraction_id,
            output_root=Path(args.output_root),
            history=Path(args.history),
            registry=Path(args.registry),
            rebuild_catalog=not args.no_catalog,
            build_artifacts=not args.no_artifacts,
        )
    except (cr.CandidateError, cr.CandidateValidationError, AutoStageError, SystemExit) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
