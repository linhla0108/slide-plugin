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
import contextlib
import io
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from _common import REPO_ROOT, load_json, resolve_repo_path, write_json

import candidate_review as cr
import check_base_requirements as base_req
import scaffold_extraction as scaffold


SCRIPT_DIR = Path(__file__).resolve().parent
STOPWORDS = {
    "add", "approval", "approve", "auto",
    "a", "an", "and", "by", "candidate", "detected", "docling", "draft",
    "detect", "descriptor", "for", "from", "in", "item", "of", "on", "or",
    "publish", "region", "rename", "required", "semantic", "the", "this",
    "to", "with",
    "cac", "cho", "cua", "cung", "duoc", "muc", "nhung", "noi", "va",
    "van",
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
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _tokens(*values: object, limit: int = 7) -> list[str]:
    out: list[str] = []
    for value in values:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        for raw in re.findall(r"[A-Za-z0-9]+", ascii_value.lower()):
            if raw in STOPWORDS or len(raw) < 2:
                continue
            if raw not in out:
                out.append(raw)
            if len(out) >= limit:
                return out
    return out


def _clean_lines(value: str) -> list[str]:
    lines: list[str] = []
    for raw in re.split(r"[\n|]+", value or ""):
        line = re.sub(r"\s+", " ", raw).strip()
        if line and line not in lines:
            lines.append(line)
    return lines


def _role_suffix(item: dict, label: str) -> str:
    if label in {"table", "chart", "form"}:
        return label
    region = item.get("region", {})
    try:
        ratio = float(region.get("width", 0)) / max(float(region.get("height", 0)), 0.0001)
        area = float(region.get("width", 0)) * float(region.get("height", 0))
    except (TypeError, ValueError):
        ratio = 1.0
        area = 0.0
    if area < 0.008:
        return "icon"
    if ratio >= 2.4:
        return "strip"
    if ratio <= 1.35:
        return "card"
    return "visual"


def _semantic_core(item: dict, suffix: str) -> list[str]:
    text = str(item.get("region_text") or "")
    lines = _clean_lines(text)
    upper_labels = [
        line
        for line in lines
        if len(line) <= 28
        and re.search(r"[A-Za-z]", line)
        and line.upper() == line
        and line.lower() not in STOPWORDS
    ]
    if upper_labels:
        return _tokens(upper_labels[-1], limit=4)
    if re.search(r"\bAI\s+Coding\b", text, re.I) and len(re.findall(r"\bLevel\s+\d", text, re.I)) >= 2:
        return ["ai", "coding", "maturity", "levels"]
    if re.search(r"\bRevenue\b", text, re.I):
        return ["revenue", "metric"]
    if re.search(r"\bTeam\s+Size\b", text, re.I):
        return ["team", "size", "metric"]
    return _tokens(" ".join(lines[:4]), limit=5) or [suffix]


def semantic_item_id(source_path: str, item: dict, used: set[str]) -> str:
    original_id = str(item.get("item_id", ""))
    label = original_id.split("-", 1)[0] or "visual"
    source_stem = Path(source_path).stem
    source_slug = slug(source_stem) or "source"
    docling_match = re.match(
        r"^(?P<label>picture|figure|table|chart|form)-p(?P<page>[a-z0-9]+)-(?P<n>\d+)$",
        original_id,
    )
    if docling_match:
        if str(item.get("region_text") or "").strip():
            suffix = _role_suffix(item, label)
            core = _semantic_core(item, suffix)
            base = slug("-".join([*core, suffix]))
        else:
            page = slug(str(item.get("slide_or_page") or docling_match.group("page")))
            ordinal = docling_match.group("n")
            base = f"{source_slug}-p{page}-{label}-{ordinal}"
    else:
        intent = " ".join(str(v) for v in item.get("semantic_intent", []))
        notes = item.get("notes", "")
        parts = _tokens(source_stem, intent, notes, label)
        if label not in parts:
            parts.append(label)
        page = slug(str(item.get("slide_or_page") or ""))
        if page and f"p{page}" not in parts:
            parts.append(f"p{page}")
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
    role_suffix = _role_suffix(item, label)
    component_type = role_suffix if role_suffix != "visual" else LABEL_COMPONENT_TYPE.get(label, label)
    region_text = str(item.get("region_text") or "").strip()
    intent_values = [
        str(v).strip()
        for v in item.get("semantic_intent", [])
        if str(v).strip()
    ]
    if region_text:
        intent_values = [item_id.replace("-", " ")]
    elif not intent_values:
        intent_values = [f"{component_type} from {Path(source_path).stem}"]
    keywords = _tokens(item_id, region_text, " ".join(intent_values), label, limit=8)
    tags = [component_type, label, "docling", "auto-staged"]
    display = item_id.replace("-", " ").title()
    text_note = f" Contains text: {_clean_lines(region_text)[:4]}." if region_text else ""
    return {
        "item_id": item_id,
        "display_name": display,
        "requested_type": item.get("requested_type", "component"),
        "component_type": component_type,
        "layout_role": f"{component_type} extracted from source region",
        "visual_summary": (
            f"Auto-staged {component_type} from page {item.get('slide_or_page')} "
            f"of {Path(source_path).name}.{text_note}"
        ),
        "semantic_intent": intent_values,
        "content_structure": [component_type, "text-bearing region" if region_text else "detected region"],
        "tags": tags,
        "keywords": keywords or [component_type],
        "use_cases": [f"Review and publish this {component_type} as a reusable component."],
        "anti_use_cases": ["Do not use before the Draft preview and metadata are reviewed."],
        "quality_notes": "Auto-generated from PDF text and Docling region; final approval happens in Draft.",
        "retrieval_notes": "Generated from region text, Docling label, source name, and page.",
    }


def _tool_python() -> str:
    fitz_python, _fitz_path, _fitz_version = base_req.probe_fitz()
    return fitz_python or sys.executable


def _run_script(args: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        [_tool_python(), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    return proc.returncode == 0, (output + ("\n" + error if error else "")).strip()


def _extract_region_texts(source_path: str, items: list[dict]) -> dict[str, str]:
    source = resolve_repo_path(source_path)
    if source.suffix.lower() != ".pdf":
        return {}
    payload = {"source": str(source), "items": items}
    code = r"""
import json
import sys
import fitz

payload = json.loads(sys.stdin.read())
doc = fitz.open(payload["source"])
out = {}
for item in payload.get("items", []):
    try:
        page_no = int(item.get("slide_or_page", 1)) - 1
        page = doc[page_no]
        region = item["region"]
        if region.get("unit") == "normalized":
            rect = fitz.Rect(
                float(region["x"]) * page.rect.width,
                float(region["y"]) * page.rect.height,
                (float(region["x"]) + float(region["width"])) * page.rect.width,
                (float(region["y"]) + float(region["height"])) * page.rect.height,
            )
        else:
            rect = fitz.Rect(
                float(region["x"]),
                float(region["y"]),
                float(region["x"]) + float(region["width"]),
                float(region["y"]) + float(region["height"]),
            )
        text = page.get_text("text", clip=rect)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        out[str(item.get("item_id"))] = "\n".join(lines)
    except Exception:
        out[str(item.get("item_id"))] = ""
print(json.dumps(out, ensure_ascii=True))
"""
    try:
        proc = subprocess.run(
            [_tool_python(), "-c", code],
            cwd=str(REPO_ROOT),
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


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
        with contextlib.redirect_stdout(io.StringIO()):
            scaffold.main()
    finally:
        sys.argv = old_argv


def _existing_stable_ids(output_root: Path) -> set[str]:
    stable_ids: set[str] = set()
    for mapping_path in output_root.glob("*/items/*/mapping.json"):
        try:
            mapping = load_json(mapping_path)
        except Exception:
            continue
        stable_id = mapping.get("candidate_stable_id")
        if stable_id:
            stable_ids.add(str(stable_id))
    return stable_ids


def _used_item_ids(output_root: Path, registry: Path) -> set[str]:
    used: set[str] = set()
    for stable_id in _existing_stable_ids(output_root):
        if stable_id.startswith("sun.component."):
            used.add(stable_id.removeprefix("sun.component."))
    try:
        registry_data = load_json(registry)
    except Exception:
        registry_data = {"items": []}
    for item in registry_data.get("items", []):
        stable_id = str(item.get("id", ""))
        if stable_id.startswith("sun.component."):
            used.add(stable_id.removeprefix("sun.component."))
    return used


def _history_stable_id_for_item(history_data: dict, source_hash: str | None,
                                item: dict) -> str | None:
    if not source_hash:
        return None
    try:
        region = scaffold.normalized_bounds(item["region"])
        region_hash = scaffold.region_identity_hash(
            source_hash,
            item["slide_or_page"],
            region,
            item.get("object_ids", []),
        )
    except Exception:
        return None
    for attempt in history_data.get("attempts", []):
        if (
            attempt.get("region_identity_sha256") == region_hash
            and attempt.get("stable_id")
        ):
            return str(attempt["stable_id"])
    return None


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
    request_items = request.get("items", [])
    region_texts = _extract_region_texts(source_path, request_items) if build_artifacts else {}
    used_ids = _used_item_ids(output_root, registry)
    summary = {
        "extraction_id": extraction_id,
        "source_path": source_path,
        "staged": 0,
        "skipped": 0,
        "items": [],
    }
    existing_stable_ids = _existing_stable_ids(output_root)
    history_data = load_json(history) if history.exists() else {"attempts": []}
    try:
        source_hash = scaffold.sha256_file(resolve_repo_path(source_path))
    except Exception:
        source_hash = None
    items_by_id = {item.get("item_id"): item for item in request_items}
    for original_id, item in items_by_id.items():
        if not original_id:
            continue
        item = dict(item)
        item["region_text"] = region_texts.get(str(original_id), "")
        existing = (cr._load_reviews(adir).get(original_id) or {})
        if existing.get("review_status") == "rejected":
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "status": "skipped",
                "reason": "candidate rejected",
            })
            continue
        history_stable_id = _history_stable_id_for_item(
            history_data, source_hash, item)
        if history_stable_id and history_stable_id in existing_stable_ids:
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "stable_id": history_stable_id,
                "status": "already_staged_region",
                "reason": "matching source/page/region already has a Draft",
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
        history_data = load_json(history) if history.exists() else {"attempts": []}
        stable_id = load_json(item_dir / "mapping.json")["candidate_stable_id"]
        existing_stable_ids.add(stable_id)
        artifact_status = "skipped"
        artifact_log = ""
        if build_artifacts:
            artifact_status, artifact_log = _build_pdf_artifacts(
                item_dir, source_path, item.get("slide_or_page", 1))
        summary["staged"] += 1
        summary["items"].append({
            "candidate_id": original_id,
            "item_id": review["item_id"],
            "stable_id": stable_id,
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
